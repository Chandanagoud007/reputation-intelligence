"""Brand, region, and location hierarchy endpoints."""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from slugify import slugify
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_tenant_id
from app.models.brand import Brand
from app.models.location import Location
from app.models.region import Region

router = APIRouter()


class BrandCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: str | None = Field(default=None, max_length=100)
    extra_data: dict = Field(default_factory=dict)


class BrandResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    slug: str
    is_active: bool
    extra_data: dict
    created_at: datetime
    updated_at: datetime


class RegionCreateRequest(BaseModel):
    brand_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=255)
    slug: str | None = Field(default=None, max_length=100)
    country: str = Field(default="US", min_length=2, max_length=100)
    extra_data: dict = Field(default_factory=dict)


class RegionResponse(BaseModel):
    id: uuid.UUID
    brand_id: uuid.UUID
    name: str
    slug: str
    country: str
    is_active: bool
    extra_data: dict
    created_at: datetime
    updated_at: datetime


class LocationCreateRequest(BaseModel):
    region_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=255)
    address: str | None = None
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    country: str = Field(default="US", min_length=2, max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)
    timezone: str = Field(default="UTC", min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    website: str | None = Field(default=None, max_length=500)
    extra_data: dict = Field(default_factory=dict)


class LocationResponse(BaseModel):
    id: uuid.UUID
    region_id: uuid.UUID
    name: str
    address: str | None
    city: str | None
    state: str | None
    country: str
    postal_code: str | None
    timezone: str
    phone: str | None
    website: str | None
    is_active: bool
    extra_data: dict
    created_at: datetime
    updated_at: datetime


def _make_slug(value: str, fallback: str | None = None) -> str:
    return slugify(value or fallback or "item")[:100] or "item"


def _brand_response(brand: Brand) -> BrandResponse:
    return BrandResponse(
        id=brand.id,
        tenant_id=brand.tenant_id,
        name=brand.name,
        slug=brand.slug,
        is_active=brand.is_active,
        extra_data=brand.extra_data,
        created_at=brand.created_at,
        updated_at=brand.updated_at,
    )


def _region_response(region: Region) -> RegionResponse:
    return RegionResponse(
        id=region.id,
        brand_id=region.brand_id,
        name=region.name,
        slug=region.slug,
        country=region.country,
        is_active=region.is_active,
        extra_data=region.extra_data,
        created_at=region.created_at,
        updated_at=region.updated_at,
    )


def _location_response(location: Location) -> LocationResponse:
    return LocationResponse(
        id=location.id,
        region_id=location.region_id,
        name=location.name,
        address=location.address,
        city=location.city,
        state=location.state,
        country=location.country,
        postal_code=location.postal_code,
        timezone=location.timezone,
        phone=location.phone,
        website=location.website,
        is_active=location.is_active,
        extra_data=location.extra_data,
        created_at=location.created_at,
        updated_at=location.updated_at,
    )


async def _get_tenant_brand(
    db: AsyncSession,
    brand_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> Brand | None:
    result = await db.execute(
        select(Brand).where(Brand.id == brand_id, Brand.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def _get_tenant_region(
    db: AsyncSession,
    region_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> Region | None:
    result = await db.execute(
        select(Region)
        .join(Brand, Region.brand_id == Brand.id)
        .where(Region.id == region_id, Brand.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def _get_tenant_location(
    db: AsyncSession,
    location_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> Location | None:
    result = await db.execute(
        select(Location)
        .join(Region, Location.region_id == Region.id)
        .join(Brand, Region.brand_id == Brand.id)
        .where(Location.id == location_id, Brand.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


@router.post("/brands", response_model=BrandResponse, status_code=status.HTTP_201_CREATED)
async def create_brand(
    payload: BrandCreateRequest,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    brand = Brand(
        tenant_id=tenant_id,
        name=payload.name,
        slug=_make_slug(payload.slug or payload.name),
        extra_data=payload.extra_data,
    )
    db.add(brand)
    await db.commit()
    await db.refresh(brand)
    return _brand_response(brand)


@router.get("/brands", response_model=list[BrandResponse])
async def list_brands(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Brand).where(Brand.tenant_id == tenant_id).order_by(Brand.created_at.desc())
    )
    return [_brand_response(brand) for brand in result.scalars().all()]


@router.get("/brands/{brand_id}", response_model=BrandResponse)
async def get_brand(
    brand_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    brand = await _get_tenant_brand(db, brand_id, tenant_id)
    if not brand:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")
    return _brand_response(brand)


@router.post("/regions", response_model=RegionResponse, status_code=status.HTTP_201_CREATED)
async def create_region(
    payload: RegionCreateRequest,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    brand = await _get_tenant_brand(db, payload.brand_id, tenant_id)
    if not brand:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")

    region = Region(
        brand_id=payload.brand_id,
        name=payload.name,
        slug=_make_slug(payload.slug or payload.name),
        country=payload.country,
        extra_data=payload.extra_data,
    )
    db.add(region)
    await db.commit()
    await db.refresh(region)
    return _region_response(region)


@router.get("/regions", response_model=list[RegionResponse])
async def list_regions(
    brand_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Region)
        .join(Brand, Region.brand_id == Brand.id)
        .where(Brand.tenant_id == tenant_id)
        .order_by(Region.created_at.desc())
    )
    if brand_id:
        stmt = stmt.where(Region.brand_id == brand_id)

    result = await db.execute(stmt)
    return [_region_response(region) for region in result.scalars().all()]


@router.get("/regions/{region_id}", response_model=RegionResponse)
async def get_region(
    region_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    region = await _get_tenant_region(db, region_id, tenant_id)
    if not region:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Region not found")
    return _region_response(region)


@router.post("/", response_model=LocationResponse, status_code=status.HTTP_201_CREATED)
async def create_location(
    payload: LocationCreateRequest,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    region = await _get_tenant_region(db, payload.region_id, tenant_id)
    if not region:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Region not found")

    location = Location(
        region_id=payload.region_id,
        name=payload.name,
        address=payload.address,
        city=payload.city,
        state=payload.state,
        country=payload.country,
        postal_code=payload.postal_code,
        timezone=payload.timezone,
        phone=payload.phone,
        website=payload.website,
        extra_data=payload.extra_data,
    )
    db.add(location)
    await db.commit()
    await db.refresh(location)
    return _location_response(location)


@router.get("/", response_model=list[LocationResponse])
async def list_locations(
    region_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Location)
        .join(Region, Location.region_id == Region.id)
        .join(Brand, Region.brand_id == Brand.id)
        .where(Brand.tenant_id == tenant_id)
        .order_by(Location.created_at.desc())
    )
    if region_id:
        stmt = stmt.where(Location.region_id == region_id)

    result = await db.execute(stmt)
    return [_location_response(location) for location in result.scalars().all()]


@router.get("/{location_id}", response_model=LocationResponse)
async def get_location(
    location_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    location = await _get_tenant_location(db, location_id, tenant_id)
    if not location:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    return _location_response(location)
