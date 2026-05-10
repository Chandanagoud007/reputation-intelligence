"""Alert rule endpoints."""
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_tenant_id
from app.services.analytics.alert_service import alert_service

router = APIRouter()


class AlertRuleCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    conditions: dict = Field(..., examples=[{
        "rating_lte": 2.5,
        "negative_pct_gte": 50,
    }])
    channels: dict = Field(..., examples=[{
        "email": ["admin@company.com"],
        "slack": "https://hooks.slack.com/...",
    }])
    cooldown_minutes: int = Field(default=60, ge=5, le=1440)


class AlertRuleResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    description: str | None
    conditions: dict
    channels: dict
    is_active: bool
    cooldown_minutes: int
    created_at: datetime
    updated_at: datetime


@router.get("/rules", response_model=list[AlertRuleResponse])
async def list_alert_rules(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """List all alert rules for the current tenant."""
    rules = await alert_service.list_rules(db, tenant_id)
    return [AlertRuleResponse(
        id=r.id, tenant_id=r.tenant_id, name=r.name,
        description=r.description, conditions=r.conditions,
        channels=r.channels, is_active=r.is_active,
        cooldown_minutes=r.cooldown_minutes,
        created_at=r.created_at, updated_at=r.updated_at,
    ) for r in rules]


@router.post("/rules", response_model=AlertRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_alert_rule(
    payload: AlertRuleCreateRequest,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Create a new alert rule."""
    rule = await alert_service.create_rule(
        db,
        tenant_id=tenant_id,
        name=payload.name,
        description=payload.description,
        conditions=payload.conditions,
        channels=payload.channels,
        cooldown_minutes=payload.cooldown_minutes,
    )
    return AlertRuleResponse(
        id=rule.id, tenant_id=rule.tenant_id, name=rule.name,
        description=rule.description, conditions=rule.conditions,
        channels=rule.channels, is_active=rule.is_active,
        cooldown_minutes=rule.cooldown_minutes,
        created_at=rule.created_at, updated_at=rule.updated_at,
    )


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert_rule(
    rule_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Delete an alert rule."""
    rule = await alert_service.get_rule(db, rule_id, tenant_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    await alert_service.delete_rule(db, rule)


@router.get("/triggered")
async def list_triggered_alerts(
    location_id: uuid.UUID | None = None,
    limit: int = 50,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
):
    """List triggered alerts for the current tenant."""
    alerts = await alert_service.list_triggered_alerts(
        tenant_id=tenant_id,
        location_id=location_id,
        limit=limit,
    )
    return {"alerts": alerts, "total": len(alerts)}


@router.post("/triggered/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
):
    """Mark a triggered alert as resolved."""
    resolved = await alert_service.resolve_alert(alert_id)
    if not resolved:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"resolved": True}


@router.post("/evaluate")
async def evaluate_alerts(
    location_id: uuid.UUID,
    platform: str,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger alert evaluation for a location+platform."""
    triggered = await alert_service.evaluate_rules(
        db,
        tenant_id=tenant_id,
        location_id=location_id,
        platform=platform,
    )
    return {"triggered": len(triggered), "alerts": triggered}
