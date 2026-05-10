"""
Connector Registry
Maps platform names to connector classes.
"""
import uuid
from typing import Type

from app.services.connectors.base import ConnectorBase
from app.services.connectors.google_business import GoogleBusinessConnector
from app.services.connectors.play_store import PlayStoreConnector
from app.services.connectors.trustpilot import TrustpilotConnector
from app.services.connectors.glassdoor import GlassdoorConnector

CONNECTOR_REGISTRY: dict[str, Type[ConnectorBase]] = {
    "google_business": GoogleBusinessConnector,
    "play_store": PlayStoreConnector,
    "trustpilot": TrustpilotConnector,
    "glassdoor": GlassdoorConnector,
}


def get_connector(
    platform: str,
    connector_id: uuid.UUID,
    location_id: uuid.UUID,
    tenant_id: uuid.UUID,
    credentials: dict,
) -> ConnectorBase:
    connector_class = CONNECTOR_REGISTRY.get(platform)
    if not connector_class:
        raise ValueError(
            f"No connector registered for platform '{platform}'. "
            f"Available: {list(CONNECTOR_REGISTRY.keys())}"
        )
    return connector_class(
        connector_id=connector_id,
        location_id=location_id,
        tenant_id=tenant_id,
        credentials=credentials,
    )


def list_supported_platforms() -> list[str]:
    return list(CONNECTOR_REGISTRY.keys())
