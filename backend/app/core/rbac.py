"""
RBAC Permission System
Roles: platform_admin | brand_manager | location_manager | analyst
"""
from enum import Enum
from functools import wraps

from fastapi import Depends, HTTPException, status

from app.core.deps import get_current_user


class Role(str, Enum):
    PLATFORM_ADMIN = "platform_admin"
    BRAND_MANAGER = "brand_manager"
    LOCATION_MANAGER = "location_manager"
    ANALYST = "analyst"


# Role hierarchy — higher index = more permissions
ROLE_HIERARCHY = [
    Role.ANALYST,
    Role.LOCATION_MANAGER,
    Role.BRAND_MANAGER,
    Role.PLATFORM_ADMIN,
]


def role_level(role: Role) -> int:
    """Returns numeric level of a role for comparison."""
    try:
        return ROLE_HIERARCHY.index(role)
    except ValueError:
        return -1


# ─── Permission Definitions ───────────────────────────────────────────────────

PERMISSIONS = {
    # Tenant management
    "tenant:create": [Role.PLATFORM_ADMIN],
    "tenant:read": [Role.PLATFORM_ADMIN, Role.BRAND_MANAGER],
    "tenant:update": [Role.PLATFORM_ADMIN],
    "tenant:delete": [Role.PLATFORM_ADMIN],

    # Brand management
    "brand:create": [Role.PLATFORM_ADMIN, Role.BRAND_MANAGER],
    "brand:read": [Role.PLATFORM_ADMIN, Role.BRAND_MANAGER, Role.LOCATION_MANAGER],
    "brand:update": [Role.PLATFORM_ADMIN, Role.BRAND_MANAGER],
    "brand:delete": [Role.PLATFORM_ADMIN],

    # Location management
    "location:create": [Role.PLATFORM_ADMIN, Role.BRAND_MANAGER, Role.LOCATION_MANAGER],
    "location:read": [Role.PLATFORM_ADMIN, Role.BRAND_MANAGER, Role.LOCATION_MANAGER, Role.ANALYST],
    "location:update": [Role.PLATFORM_ADMIN, Role.BRAND_MANAGER, Role.LOCATION_MANAGER],
    "location:delete": [Role.PLATFORM_ADMIN, Role.BRAND_MANAGER],

    # Reviews
    "review:read": [Role.PLATFORM_ADMIN, Role.BRAND_MANAGER, Role.LOCATION_MANAGER, Role.ANALYST],
    "review:respond": [Role.PLATFORM_ADMIN, Role.BRAND_MANAGER, Role.LOCATION_MANAGER],
    "review:delete": [Role.PLATFORM_ADMIN],

    # Analytics
    "analytics:read": [Role.PLATFORM_ADMIN, Role.BRAND_MANAGER, Role.LOCATION_MANAGER, Role.ANALYST],
    "analytics:export": [Role.PLATFORM_ADMIN, Role.BRAND_MANAGER],

    # Connectors
    "connector:create": [Role.PLATFORM_ADMIN, Role.BRAND_MANAGER, Role.LOCATION_MANAGER],
    "connector:read": [Role.PLATFORM_ADMIN, Role.BRAND_MANAGER, Role.LOCATION_MANAGER],
    "connector:delete": [Role.PLATFORM_ADMIN, Role.BRAND_MANAGER],

    # Alerts
    "alert:create": [Role.PLATFORM_ADMIN, Role.BRAND_MANAGER, Role.LOCATION_MANAGER],
    "alert:read": [Role.PLATFORM_ADMIN, Role.BRAND_MANAGER, Role.LOCATION_MANAGER, Role.ANALYST],
    "alert:update": [Role.PLATFORM_ADMIN, Role.BRAND_MANAGER, Role.LOCATION_MANAGER],
    "alert:delete": [Role.PLATFORM_ADMIN, Role.BRAND_MANAGER],

    # User management
    "user:create": [Role.PLATFORM_ADMIN, Role.BRAND_MANAGER],
    "user:read": [Role.PLATFORM_ADMIN, Role.BRAND_MANAGER],
    "user:update": [Role.PLATFORM_ADMIN, Role.BRAND_MANAGER],
    "user:delete": [Role.PLATFORM_ADMIN],
}


def has_permission(user_role: str, permission: str) -> bool:
    """Check if a role has a specific permission."""
    allowed_roles = PERMISSIONS.get(permission, [])
    return Role(user_role) in allowed_roles


# ─── FastAPI Dependencies ─────────────────────────────────────────────────────

def require_roles(*roles: Role):
    """Dependency factory — requires one of the specified roles."""
    def dependency(current_user=Depends(get_current_user)):
        if Role(current_user["role"]) not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required roles: {[r.value for r in roles]}"
            )
        return current_user
    return dependency


def require_permission(permission: str):
    """Dependency factory — requires a specific permission."""
    def dependency(current_user=Depends(get_current_user)):
        if not has_permission(current_user["role"], permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission}"
            )
        return current_user
    return dependency


# ─── Shortcut Dependencies ────────────────────────────────────────────────────

require_platform_admin = require_roles(Role.PLATFORM_ADMIN)
require_brand_manager = require_roles(Role.PLATFORM_ADMIN, Role.BRAND_MANAGER)
require_location_manager = require_roles(Role.PLATFORM_ADMIN, Role.BRAND_MANAGER, Role.LOCATION_MANAGER)
require_any_role = require_roles(Role.PLATFORM_ADMIN, Role.BRAND_MANAGER, Role.LOCATION_MANAGER, Role.ANALYST)
