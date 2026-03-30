"""
Field-Level Data Masking
Masks sensitive fields in API responses based on user role.
"""
import re
from enum import Enum
from typing import Any


class MaskLevel(str, Enum):
    FULL = "full"        # Show everything
    PARTIAL = "partial"  # Show partial value
    HIDDEN = "hidden"    # Replace with ***


# ─── Masking Functions ────────────────────────────────────────────────────────

def mask_email(email: str, level: MaskLevel = MaskLevel.PARTIAL) -> str:
    """
    Mask an email address.
    partial: a****@example.com
    hidden:  ***@***.***
    """
    if not email or "@" not in email:
        return email
    if level == MaskLevel.FULL:
        return email
    if level == MaskLevel.HIDDEN:
        parts = email.split("@")
        domain_parts = parts[1].split(".")
        return f"***@***{'.'.join([''] + [d[-1] for d in domain_parts])}"
    # Partial
    parts = email.split("@")
    username = parts[0]
    domain = parts[1]
    masked_username = username[0] + "*" * (len(username) - 1) if len(username) > 1 else "*"
    return f"{masked_username}@{domain}"


def mask_phone(phone: str, level: MaskLevel = MaskLevel.PARTIAL) -> str:
    """
    Mask a phone number.
    partial: +1****1234
    hidden:  ***-***-****
    """
    if not phone:
        return phone
    if level == MaskLevel.FULL:
        return phone
    if level == MaskLevel.HIDDEN:
        return "***-***-****"
    # Partial — show last 4 digits
    digits_only = re.sub(r"\D", "", phone)
    if len(digits_only) >= 4:
        return "*" * (len(digits_only) - 4) + digits_only[-4:]
    return "****"


def mask_token(token: str, level: MaskLevel = MaskLevel.PARTIAL) -> str:
    """
    Mask an OAuth token or API key.
    partial: abc****xyz
    hidden:  ***
    """
    if not token:
        return token
    if level == MaskLevel.FULL:
        return token
    if level == MaskLevel.HIDDEN:
        return "***"
    # Partial — show first 3 and last 3 characters
    if len(token) <= 6:
        return "***"
    return token[:3] + "*" * (len(token) - 6) + token[-3:]


def mask_credit_card(card: str, level: MaskLevel = MaskLevel.PARTIAL) -> str:
    """Mask a credit card number — always show only last 4 digits."""
    if not card:
        return card
    if level == MaskLevel.FULL:
        return card
    digits = re.sub(r"\D", "", card)
    return "*" * (len(digits) - 4) + digits[-4:] if len(digits) >= 4 else "****"


# ─── Role-based masking policy ────────────────────────────────────────────────

ROLE_MASK_POLICY = {
    "platform_admin": MaskLevel.FULL,
    "brand_manager": MaskLevel.PARTIAL,
    "location_manager": MaskLevel.PARTIAL,
    "analyst": MaskLevel.HIDDEN,
}


def get_mask_level(role: str) -> MaskLevel:
    """Get the masking level for a given role."""
    return ROLE_MASK_POLICY.get(role, MaskLevel.HIDDEN)


def mask_user_data(data: dict[str, Any], role: str) -> dict[str, Any]:
    """
    Apply field-level masking to a user data dictionary based on role.
    """
    level = get_mask_level(role)
    masked = data.copy()

    if "email" in masked and masked["email"]:
        masked["email"] = mask_email(masked["email"], level)

    if "phone" in masked and masked["phone"]:
        masked["phone"] = mask_phone(masked["phone"], level)

    if "hashed_password" in masked:
        masked["hashed_password"] = "***"

    return masked


def mask_connector_data(data: dict[str, Any], role: str) -> dict[str, Any]:
    """
    Apply field-level masking to connector/credential data based on role.
    Always hides encrypted_credentials from non-admins.
    """
    level = get_mask_level(role)
    masked = data.copy()

    # Always mask encrypted credentials for non-admins
    if role != "platform_admin" and "encrypted_credentials" in masked:
        masked["encrypted_credentials"] = {"vault": "***"}

    if "external_id" in masked and masked["external_id"]:
        masked["external_id"] = mask_token(masked["external_id"], level)

    return masked
