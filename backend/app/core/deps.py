"""
FastAPI Dependencies
Reusable dependencies for authentication and database access.
"""
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_redis
from app.core.security import decode_token

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    """
    Validates JWT token and returns the current user payload.
    Raises 401 if token is invalid or expired.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = credentials.credentials
    if token.lower().startswith("bearer "):
        token = token.split(" ", 1)[1]

    try:
        payload = decode_token(token)
    except ValueError:
        raise credentials_exception

    user_id = payload.get("sub")
    tenant_id = payload.get("tenant_id")
    role = payload.get("role")
    token_type = payload.get("type")

    if not user_id or not tenant_id or not role:
        raise credentials_exception

    if token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type — use access token",
        )

    # Check token blacklist in Redis
    redis = get_redis()
    is_blacklisted = await redis.get(f"blacklist:{token}")
    if is_blacklisted:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    return {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "role": role,
    }


async def get_current_active_user(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Returns current user, raises 400 if inactive."""
    return current_user


def get_tenant_id(current_user: dict = Depends(get_current_user)) -> uuid.UUID:
    """Extracts tenant_id from current user."""
    return uuid.UUID(current_user["tenant_id"])
