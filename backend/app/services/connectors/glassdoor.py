"""
Glassdoor Connector
"""
from datetime import datetime
from typing import Optional

import httpx

from app.models.review import ReviewAuthor, ReviewCreate
from app.services.connectors.base import ConnectorBase

GLASSDOOR_REVIEWS_URL = "https://api.glassdoor.com/api/api.htm"


class GlassdoorConnector(ConnectorBase):
    platform = "glassdoor"

    def __init__(self, connector_id, location_id, tenant_id, credentials):
        super().__init__(connector_id, location_id, tenant_id, credentials)
        self.partner_id = credentials.get("partner_id", "")
        self.api_key = credentials.get("api_key", "")
        self.employer_id = credentials.get("employer_id", "")

    def _base_params(self):
        return {
            "v": "1",
            "format": "json",
            "t.p": self.partner_id,
            "t.k": self.api_key,
            "action": "employers",
            "employerId": self.employer_id,
        }

    async def validate_connection(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(GLASSDOOR_REVIEWS_URL, params={**self._base_params(), "ps": 1, "pg": 1})
                return r.status_code == 200
        except Exception:
            return False

    async def refresh_tokens(self) -> dict:
        return self.credentials

    async def fetch_reviews(self, since=None, limit=100) -> list[ReviewCreate]:
        all_reviews = []
        page = 1
        page_size = min(10, limit)

        async with httpx.AsyncClient(timeout=30) as client:
            while len(all_reviews) < limit:
                params = {**self._base_params(), "action": "reviews", "ps": page_size, "pg": page}
                r = await client.get(GLASSDOOR_REVIEWS_URL, params=params)
                r.raise_for_status()
                data = r.json()

                employers = data.get("response", {}).get("employers", [{}])
                reviews = employers[0].get("reviews", []) if employers else []
                if not reviews:
                    break

                for raw in reviews:
                    review = self._normalize(raw, since)
                    if review:
                        all_reviews.append(review)

                total = employers[0].get("numberOfRatings", 0) if employers else 0
                if page * page_size >= total:
                    break
                page += 1

        self.log.info("Glassdoor fetch complete", total=len(all_reviews))
        return all_reviews

    def _normalize(self, raw, since):
        try:
            published_at = datetime.fromisoformat(
                raw.get("reviewDateTime", "").replace("Z", "+00:00")
            ).replace(tzinfo=None)
            if since and published_at <= since:
                return None
            pros = raw.get("pros", "")
            cons = raw.get("cons", "")
            content = f"Pros: {pros}\nCons: {cons}".strip() if pros or cons else raw.get("headline", "")
            job_title = raw.get("jobTitle", {})
            author_name = job_title.get("title", "Employee") if isinstance(job_title, dict) else "Employee"
            return ReviewCreate(
                tenant_id=self.tenant_id,
                location_id=self.location_id,
                platform=self.platform,
                external_id=str(raw.get("id", "")),
                rating=float(raw.get("overallRating", 3.0)),
                title=raw.get("headline"),
                content=content,
                language="en",
                author=ReviewAuthor(name=author_name),
                published_at=published_at,
            )
        except Exception as e:
            self.log.warning("Normalize failed", error=str(e))
            return None
