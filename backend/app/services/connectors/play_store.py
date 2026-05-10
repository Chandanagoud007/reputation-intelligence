"""
Google Play Store Connector
"""
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.models.review import ReviewAuthor, ReviewCreate
from app.services.connectors.base import ConnectorBase

PLAY_REVIEWS_URL = "https://androidpublisher.googleapis.com/androidpublisher/v3/applications/{package_name}/reviews"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
STAR_MAP = {1: 1.0, 2: 2.0, 3: 3.0, 4: 4.0, 5: 5.0}


class PlayStoreConnector(ConnectorBase):
    platform = "play_store"

    def __init__(self, connector_id, location_id, tenant_id, credentials):
        super().__init__(connector_id, location_id, tenant_id, credentials)
        self.package_name = credentials.get("package_name", "")

    def _get_headers(self):
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
            return self.credentials

    async def fetch_reviews(self, since=None, limit=100) -> list[ReviewCreate]:
        url = PLAY_REVIEWS_URL.format(package_name=self.package_name)
        all_reviews = []
        token = None

        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                params = {"maxResults": min(limit, 100)}
                if token:
                    params["pageToken"] = token
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

                token = data.get("tokenPagination", {}).get("nextPageToken")
                if not token or len(all_reviews) >= limit:
                    break

        self.log.info("Play Store fetch complete", total=len(all_reviews))
        return all_reviews

    def _normalize(self, raw, since):
        try:
            comments = raw.get("comments", [])
            if not comments:
                return None
            user_comment = comments[0].get("userComment", {})
            ts = int(user_comment.get("lastModified", {}).get("seconds", 0))
            published_at = datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
            if since and published_at <= since:
                return None
            owner_reply = None
            owner_reply_at = None
            if len(comments) > 1:
                dev = comments[1].get("developerComment", {})
                owner_reply = dev.get("text")
                reply_ts = int(dev.get("lastModified", {}).get("seconds", 0))
                if reply_ts:
                    owner_reply_at = datetime.fromtimestamp(reply_ts, tz=timezone.utc).replace(tzinfo=None)
            return ReviewCreate(
                tenant_id=self.tenant_id,
                location_id=self.location_id,
                platform=self.platform,
                external_id=raw.get("reviewId", ""),
                rating=STAR_MAP.get(user_comment.get("starRating", 3), 3.0),
                content=user_comment.get("text", ""),
                language=user_comment.get("reviewerLanguage", "en"),
                author=ReviewAuthor(name="Play Store User"),
                published_at=published_at,
                owner_reply=owner_reply,
                owner_reply_at=owner_reply_at,
            )
        except Exception as e:
            self.log.warning("Normalize failed", error=str(e))
            return None
