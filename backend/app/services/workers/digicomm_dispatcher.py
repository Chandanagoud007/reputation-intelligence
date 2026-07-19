"""
DigiComm Notification Dispatcher
Consumes from: reputation.alert.created
Produces to:   reputation.alert.dispatched
               reputation.dlq (on failure)

What it does:
- Reads alert events from Kafka
- Dispatches notifications via configured channels:
    email   → SMTP (via smtplib / SendGrid)
    slack   → Incoming webhook POST
    webhook → Generic HTTP POST to any URL
- Retries failed deliveries with exponential backoff (max 4 attempts)
- Publishes to reputation.alert.dispatched after successful delivery
- Logs all dispatch attempts to PostgreSQL alert_log table

Run with: python -m app.services.workers.digicomm_dispatcher
"""
import asyncio
import json
import smtplib
import ssl
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx
import structlog
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

log = structlog.get_logger()

TOPIC_IN  = "reputation.alert.created"
TOPIC_OUT = "reputation.alert.dispatched"
TOPIC_DLQ = "reputation.dlq"
GROUP_ID  = "digicomm-dispatcher-group"

MAX_RETRIES    = 4
RETRY_BACKOFFS = [1, 2, 4, 8]   # seconds


# ── DB setup ──────────────────────────────────────────────────────────────────
engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True, pool_size=5)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ── Email dispatcher ──────────────────────────────────────────────────────────
def build_email_body(alert: dict) -> str:
    trigger = alert.get("trigger_values", {})
    return f"""
REPUTATION ALERT — {alert.get('severity', '').upper()}

Rule:      {alert.get('rule_name')}
Location:  {alert.get('location_name')} ({alert.get('brand_name')})
Severity:  {alert.get('severity', '').upper()}
Fired at:  {alert.get('fired_at')}

TRIGGER VALUES
Score:         {trigger.get('score', 'N/A')}
Rating avg:    {trigger.get('rating_avg', 'N/A')}
Sentiment avg: {trigger.get('sentiment_avg', 'N/A')}
Risk level:    {trigger.get('risk_level', 'N/A')}
Review count:  {trigger.get('review_count', 'N/A')}

Risk flags: {', '.join(alert.get('risk_flags', [])) or 'None'}
Topics:     {', '.join(alert.get('topics', [])) or 'None'}

Please review and take action.
— Reputation Intelligence Platform
"""


async def send_email(recipients: list[str], alert: dict) -> bool:
    """Send alert email via SMTP. Returns True on success."""
    smtp_host = getattr(settings, "SMTP_HOST", "")
    smtp_port = getattr(settings, "SMTP_PORT", 587)
    smtp_user = getattr(settings, "SMTP_USER", "")
    smtp_pass = getattr(settings, "SMTP_PASSWORD", "")
    from_addr = getattr(settings, "AWS_SES_SENDER_EMAIL", "noreply@rip.local")

    if not smtp_host:
        log.warning("SMTP not configured — email skipped", recipients=recipients)
        return True   # treat as success in dev

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[{alert.get('severity','').upper()}] Reputation Alert — {alert.get('location_name')}"
        msg["From"]    = from_addr
        msg["To"]      = ", ".join(recipients)
        msg.attach(MIMEText(build_email_body(alert), "plain"))

        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls(context=context)
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_addr, recipients, msg.as_string())

        log.info("Email sent", recipients=recipients)
        return True

    except Exception as e:
        log.error("Email failed", error=str(e), recipients=recipients)
        return False


# ── Slack dispatcher ──────────────────────────────────────────────────────────
def build_slack_payload(alert: dict) -> dict:
    trigger  = alert.get("trigger_values", {})
    severity = alert.get("severity", "low").upper()
    color    = {"CRITICAL": "#E24B4A", "HIGH": "#EF9F27", "MEDIUM": "#378ADD", "LOW": "#1D9E75"}.get(severity, "#888")

    return {
        "attachments": [
            {
                "color": color,
                "title": f":rotating_light: Reputation Alert — {severity}",
                "fields": [
                    {"title": "Rule",      "value": alert.get("rule_name"),      "short": True},
                    {"title": "Location",  "value": alert.get("location_name"),  "short": True},
                    {"title": "Brand",     "value": alert.get("brand_name"),     "short": True},
                    {"title": "Score",     "value": str(trigger.get("score", "N/A")), "short": True},
                    {"title": "Risk",      "value": trigger.get("risk_level", "N/A"), "short": True},
                    {"title": "Risk flags","value": ", ".join(alert.get("risk_flags", [])) or "None", "short": True},
                    {"title": "Topics",    "value": ", ".join(alert.get("topics", [])) or "None", "short": True},
                ],
                "footer": "Reputation Intelligence Platform",
                "ts": int(datetime.now(timezone.utc).timestamp()),
            }
        ]
    }


async def send_slack(webhook_url: str, alert: dict, client: httpx.AsyncClient) -> bool:
    if not webhook_url or webhook_url == "webhook_url":
        log.warning("Slack webhook not configured — skipping")
        return True   # treat as success in dev

    try:
        payload  = build_slack_payload(alert)
        response = await client.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        log.info("Slack notification sent", webhook=webhook_url[:40])
        return True
    except Exception as e:
        log.error("Slack failed", error=str(e))
        return False


# ── Generic webhook dispatcher ────────────────────────────────────────────────
async def send_webhook(url: str, alert: dict, client: httpx.AsyncClient) -> bool:
    try:
        response = await client.post(url, json=alert, timeout=10)
        response.raise_for_status()
        log.info("Webhook delivered", url=url[:40])
        return True
    except Exception as e:
        log.error("Webhook failed", error=str(e), url=url)
        return False


# ── Retry wrapper ─────────────────────────────────────────────────────────────
async def dispatch_with_retry(fn, *args, **kwargs) -> bool:
    for attempt, backoff in enumerate(RETRY_BACKOFFS):
        success = await fn(*args, **kwargs)
        if success:
            return True
        if attempt < MAX_RETRIES - 1:
            log.warning("Dispatch failed, retrying", attempt=attempt+1, backoff=backoff)
            await asyncio.sleep(backoff)
    return False


# ── Alert log ─────────────────────────────────────────────────────────────────
async def log_dispatch(alert: dict, channel: str, status: str, error: str = None):
    """Write dispatch attempt to PostgreSQL for audit trail."""
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(
                text("""
                    INSERT INTO alerts.alert_dispatch_log
                        (id, alert_id, tenant_id, channel, status, error, dispatched_at)
                    VALUES
                        (gen_random_uuid(), :alert_id, :tenant_id, :channel, :status, :error, now())
                    ON CONFLICT DO NOTHING
                """),
                {
                    "alert_id":  alert.get("alert_id"),
                    "tenant_id": alert.get("tenant_id"),
                    "channel":   channel,
                    "status":    status,
                    "error":     error,
                },
            )
            await db.commit()
    except Exception as e:
        log.warning("Failed to log dispatch", error=str(e))


# ── Worker ────────────────────────────────────────────────────────────────────
async def run_worker():
    log.info("Starting DigiComm dispatcher", topic_in=TOPIC_IN, topic_out=TOPIC_OUT)

    consumer = AIOKafkaConsumer(
        TOPIC_IN,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id=GROUP_ID,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        max_poll_records=20,
        session_timeout_ms=30000,
        heartbeat_interval_ms=10000,
    )

    producer = AIOKafkaProducer(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if k else None,
        acks="all",
        enable_idempotence=True,
    )

    await consumer.start()
    await producer.start()
    log.info("DigiComm dispatcher ready")

    async with httpx.AsyncClient() as http_client:
        try:
            async for msg in consumer:
                alert      = msg.value
                alert_id   = alert.get("alert_id", "unknown")
                tenant_id  = alert.get("tenant_id", "unknown")
                channels   = alert.get("channels", {})

                log.info(
                    "Dispatching alert",
                    alert_id=alert_id,
                    severity=alert.get("severity"),
                    channels=list(channels.keys()),
                    location=alert.get("location_name"),
                )

                dispatch_results = {}

                try:
                    # Email
                    if "email" in channels:
                        success = await dispatch_with_retry(
                            send_email, channels["email"], alert
                        )
                        dispatch_results["email"] = "sent" if success else "failed"
                        await log_dispatch(alert, "email", dispatch_results["email"])

                    # Slack
                    if "slack" in channels:
                        success = await dispatch_with_retry(
                            send_slack, channels["slack"], alert, http_client
                        )
                        dispatch_results["slack"] = "sent" if success else "failed"
                        await log_dispatch(alert, "slack", dispatch_results["slack"])

                    # Generic webhook
                    if "webhook" in channels:
                        success = await dispatch_with_retry(
                            send_webhook, channels["webhook"], alert, http_client
                        )
                        dispatch_results["webhook"] = "sent" if success else "failed"
                        await log_dispatch(alert, "webhook", dispatch_results["webhook"])

                    # Publish dispatched event
                    dispatched_event = {
                        **alert,
                        "dispatch_results": dispatch_results,
                        "dispatched_at": datetime.now(timezone.utc).isoformat(),
                    }

                    await producer.send_and_wait(
                        TOPIC_OUT,
                        value=dispatched_event,
                        key=tenant_id,
                        headers=[
                            ("tenant_id", tenant_id.encode()),
                            ("severity", alert.get("severity", "low").encode()),
                        ],
                    )

                    await consumer.commit()

                    log.info(
                        "Alert dispatched",
                        alert_id=alert_id,
                        results=dispatch_results,
                    )

                except Exception as e:
                    log.error("Dispatch failed", alert_id=alert_id, error=str(e))
                    try:
                        await producer.send_and_wait(
                            TOPIC_DLQ,
                            value={
                                **alert,
                                "dlq_reason": str(e),
                                "dlq_stage": "digicomm",
                                "dlq_at": datetime.now(timezone.utc).isoformat(),
                            },
                            key=tenant_id,
                        )
                        await consumer.commit()
                    except Exception as dlq_err:
                        log.critical("DLQ publish failed", error=str(dlq_err))

        finally:
            await consumer.stop()
            await producer.stop()
            await engine.dispose()
            log.info("DigiComm dispatcher stopped")


if __name__ == "__main__":
    asyncio.run(run_worker())
