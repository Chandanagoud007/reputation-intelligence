"""
Authentication Endpoints
Handles register, login, logout, and token refresh.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_redis
from app.core.security import create_token_pair, decode_token, hash_password, verify_password
from app.models.tenant import Tenant
from app.models.user import User

router = APIRouter()


# ─── Schemas ──────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    tenant_name: str
    tenant_slug: str
    email: EmailStr
    password: str
    full_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    tenant_slug: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new tenant and platform admin user."""

    # Check slug is unique
    existing = await db.execute(
        select(Tenant).where(Tenant.slug == payload.tenant_slug)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant slug already exists"
        )

    # Create tenant
    tenant = Tenant(
        name=payload.tenant_name,
        slug=payload.tenant_slug,
        plan="starter",
    )
    db.add(tenant)
    await db.flush()  # Get tenant.id without committing

    # Create platform admin user
    user = User(
        tenant_id=tenant.id,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role="platform_admin",
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    tokens = create_token_pair(
        user_id=str(user.id),
        tenant_id=str(tenant.id),
        role=user.role,
    )
    return tokens


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login with email, password and tenant slug."""

    # Find tenant
    tenant_result = await db.execute(
        select(Tenant).where(Tenant.slug == payload.tenant_slug, Tenant.is_active == True)
    )
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    # Find user
    user_result = await db.execute(
        select(User).where(
            User.email == payload.email,
            User.tenant_id == tenant.id,
            User.is_active == True,
        )
    )
    user = user_result.scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    tokens = create_token_pair(
        user_id=str(user.id),
        tenant_id=str(tenant.id),
        role=user.role,
    )
    return tokens


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(payload: RefreshRequest):
    """Get a new access token using a refresh token."""
    try:
        data = decode_token(payload.refresh_token)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )

    if data.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type"
        )

    tokens = create_token_pair(
        user_id=data["sub"],
        tenant_id=data["tenant_id"],
        role=data["role"],
    )
    return tokens


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(token: str):
    """Blacklist the current access token."""
    redis = get_redis()
    try:
        data = decode_token(token)
        exp = data.get("exp", 0)
        import time
        ttl = int(exp - time.time())
        if ttl > 0:
            await redis.setex(f"blacklist:{token}", ttl, "1")
    except ValueError:
        pass
