"""
Trustpilot Connector
"""
from datetime import datetime
from typing import Optional

import httpx

from app.models.review import ReviewAuthor, ReviewCreate
from app.services.connectors.base import ConnectorBase

TRUSTPILOT_REVIEWS_URL = "https://api.trustpilot.com/v1/business-units/{business_unit_id}/reviews"


class TrustpilotConnector(ConnectorBase):
    platform = "trustpilot"

    def __init__(self, connector_id, location_id, tenant_id, credentials):
        super().__init__(connector_id, location_id, tenant_id, credentials)
        self.api_key = credentials.get("api_key", "")
        self.business_unit_id = credentials.get("business_unit_id", "")

    def _get_headers(self):
        return {"apikey": self.api_key}

    async def validate_connection(self) -> bool:
        try:
            url = f"https://api.trustpilot.com/v1/business-units/{self.business_unit_id}"
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(url, headers=self._get_headers())
                return r.status_code == 200
        except Exception:
            return False

    async def refresh_tokens(self) -> dict:
        return self.credentials

    async def fetch_reviews(self, since=None, limit=100) -> list[ReviewCreate]:
        url = TRUSTPILOT_REVIEWS_URL.format(business_unit_id=self.business_unit_id)
        all_reviews = []
        page = 1

        async with httpx.AsyncClient(timeout=30) as client:
            while len(all_reviews) < limit:
                params = {"perPage": min(20, limit), "page": page}
                if since:
                    params["startDateTime"] = since.isoformat() + "Z"
                r = await client.get(url, headers=self._get_headers(), params=params)
                r.raise_for_status()
                data = r.json()

                reviews = data.get("reviews", [])
                if not reviews:
                    break

                for raw in reviews:
                    review = self._normalize(raw, since)
                    if review:
                        all_reviews.append(review)

                has_next = any(l.get("rel") == "next-page" for l in data.get("links", []))
                if not has_next:
                    break
                page += 1

        self.log.info("Trustpilot fetch complete", total=len(all_reviews))
        return all_reviews

    def _normalize(self, raw, since):
        try:
            published_at = datetime.fromisoformat(
                raw.get("createdAt", "").replace("Z", "+00:00")
            ).replace(tzinfo=None)
            if since and published_at <= since:
                return None
            consumer = raw.get("consumer", {})
            reply = raw.get("companyReply")
            owner_reply = reply.get("message") if reply else None
            owner_reply_at = None
            if reply and reply.get("createdAt"):
                owner_reply_at = datetime.fromisoformat(
                    reply["createdAt"].replace("Z", "+00:00")
                ).replace(tzinfo=None)
            return ReviewCreate(
                tenant_id=self.tenant_id,
                location_id=self.location_id,
                platform=self.platform,
                external_id=raw.get("id", ""),
                rating=float(raw.get("stars", 3)),
                title=raw.get("title"),
                content=raw.get("text", ""),
                language=raw.get("language", "en"),
                author=ReviewAuthor(
                    name=consumer.get("displayName", "Trustpilot User"),
                    profile_url=consumer.get("profileUrl"),
                ),
                published_at=published_at,
                owner_reply=owner_reply,
                owner_reply_at=owner_reply_at,
            )
        except Exception as e:
            self.log.warning("Normalize failed", error=str(e))
            return None
