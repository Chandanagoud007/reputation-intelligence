"""
Google Business Profile Connector
"""
import uuid
from datetime import datetime
from typing import Optional

import httpx

from app.models.review import ReviewAuthor, ReviewCreate
from app.services.connectors.base import ConnectorBase

GOOGLE_REVIEWS_URL = "https://mybusiness.googleapis.com/v4/accounts/{account_id}/locations/{location_id}/reviews"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

RATING_MAP = {"ONE": 1.0, "TWO": 2.0, "THREE": 3.0, "FOUR": 4.0, "FIVE": 5.0}


class GoogleBusinessConnector(ConnectorBase):
    platform = "google_business"

    def __init__(self, connector_id, location_id, tenant_id, credentials):
        super().__init__(connector_id, location_id, tenant_id, credentials)
        self.account_id = credentials.get("account_id", "")
        self.google_location_id = credentials.get("google_location_id", "")

    def _get_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.credentials['access_token']}"}

    async def validate_connection(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(GOOGLE_USERINFO_URL, headers=self._get_headers())
                return r.status_code == 200
        except Exception:
            return False

    async def refresh_tokens(self) -> dict:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(GOOGLE_TOKEN_URL, data={
                "grant_type": "refresh_token",
                "refresh_token": self.credentials["refresh_token"],
                "client_id": self.credentials["client_id"],
                "client_secret": self.credentials["client_secret"],
            })
            r.raise_for_status()
            data = r.json()
            self.credentials["access_token"] = data["access_token"]
            if "refresh_token" in data:
                self.credentials["refresh_token"] = data["refresh_token"]
            self.log.info("Tokens refreshed")
            return self.credentials

    async def fetch_reviews(self, since=None, limit=100) -> list[ReviewCreate]:
        url = GOOGLE_REVIEWS_URL.format(
            account_id=self.account_id,
            location_id=self.google_location_id,
        )
        all_reviews = []
        page_token = None

        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                params = {"pageSize": min(limit, 50)}
                if page_token:
                    params["pageToken"] = page_token

                r = await client.get(url, headers=self._get_headers(), params=params)
                if r.status_code == 401:
                    self.credentials = await self.refresh_tokens()
                    r = await client.get(url, headers=self._get_headers(), params=params)
                r.raise_for_status()
                data = r.json()

                for raw in data.get("reviews", []):
                    review = self._normalize(raw, since)
                    if review:
                        all_reviews.append(review)

                page_token = data.get("nextPageToken")
                if not page_token or len(all_reviews) >= limit:
                    break

        self.log.info("Fetch complete", total=len(all_reviews))
        return all_reviews

    def _normalize(self, raw, since):
        try:
            published_at = datetime.fromisoformat(
                raw.get("createTime", "").replace("Z", "+00:00")
            ).replace(tzinfo=None)
            if since and published_at <= since:
                return None
            reviewer = raw.get("reviewer", {})
            reply = raw.get("reviewReply")
            owner_reply = reply.get("comment") if reply else None
            owner_reply_at = None
            if reply and reply.get("updateTime"):
                owner_reply_at = datetime.fromisoformat(
                    reply["updateTime"].replace("Z", "+00:00")
                ).replace(tzinfo=None)
            return ReviewCreate(
                tenant_id=self.tenant_id,
                location_id=self.location_id,
                platform=self.platform,
                external_id=raw.get("reviewId", ""),
                rating=RATING_MAP.get(raw.get("starRating", "THREE"), 3.0),
                content=raw.get("comment", ""),
                author=ReviewAuthor(name=reviewer.get("displayName", "Anonymous")),
                published_at=published_at,
                owner_reply=owner_reply,
                owner_reply_at=owner_reply_at,
            )
        except Exception as e:
            self.log.warning("Normalize failed", error=str(e))
            return None
