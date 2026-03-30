"""Create all Phase 1 schemas and tables

Revision ID: 001_phase1_foundation
Revises: 
Create Date: 2026-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '001_phase1_foundation'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ─── Extensions ───────────────────────────────────────────────
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')

    # ─── Schemas ──────────────────────────────────────────────────
    op.execute("CREATE SCHEMA IF NOT EXISTS tenant_mgmt")
    op.execute("CREATE SCHEMA IF NOT EXISTS auth")
    op.execute("CREATE SCHEMA IF NOT EXISTS alerts")

    # ─── Tenants ──────────────────────────────────────────────────
    op.create_table(
        "tenants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), unique=True, nullable=False),
        sa.Column("plan", sa.String(50), nullable=False, server_default="starter"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("settings", JSONB, nullable=False, server_default="{}"),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("max_locations", sa.Integer, nullable=False, server_default="5"),
        sa.Column("max_users", sa.Integer, nullable=False, server_default="10"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="tenant_mgmt",
    )

    # ─── Brands ───────────────────────────────────────────────────
    op.create_table(
        "brands",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenant_mgmt.tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="tenant_mgmt",
    )

    # ─── Regions ──────────────────────────────────────────────────
    op.create_table(
        "regions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("brand_id", UUID(as_uuid=True), sa.ForeignKey("tenant_mgmt.brands.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("country", sa.String(100), nullable=False, server_default="US"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="tenant_mgmt",
    )

    # ─── Locations ────────────────────────────────────────────────
    op.create_table(
        "locations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("region_id", UUID(as_uuid=True), sa.ForeignKey("tenant_mgmt.regions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("address", sa.Text, nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state", sa.String(100), nullable=True),
        sa.Column("country", sa.String(100), nullable=False, server_default="US"),
        sa.Column("postal_code", sa.String(20), nullable=True),
        sa.Column("timezone", sa.String(100), nullable=False, server_default="UTC"),
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("website", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="tenant_mgmt",
    )

    # ─── Connectors ───────────────────────────────────────────────
    op.create_table(
        "connectors",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("location_id", UUID(as_uuid=True), sa.ForeignKey("tenant_mgmt.locations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("encrypted_credentials", JSONB, nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("last_synced", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("sync_error", sa.String(500), nullable=True),
        sa.Column("sync_frequency_minutes", sa.Integer, nullable=False, server_default="60"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="tenant_mgmt",
    )

    # ─── Users ────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenant_mgmt.tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("role", sa.String(50), nullable=False, server_default="analyst"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="auth",
    )
    op.create_unique_constraint("uq_users_tenant_email", "users", ["tenant_id", "email"], schema="auth")

    # ─── Alert Rules ──────────────────────────────────────────────
    op.create_table(
        "alert_rules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenant_mgmt.tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("conditions", JSONB, nullable=False),
        sa.Column("channels", JSONB, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("cooldown_minutes", sa.Integer, nullable=False, server_default="60"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="alerts",
    )

    # ─── Indexes ──────────────────────────────────────────────────
    op.create_index("idx_brands_tenant", "brands", ["tenant_id"], schema="tenant_mgmt")
    op.create_index("idx_regions_brand", "regions", ["brand_id"], schema="tenant_mgmt")
    op.create_index("idx_locations_region", "locations", ["region_id"], schema="tenant_mgmt")
    op.create_index("idx_connectors_location", "connectors", ["location_id"], schema="tenant_mgmt")
    op.create_index("idx_connectors_platform", "connectors", ["platform"], schema="tenant_mgmt")
    op.create_index("idx_users_tenant", "users", ["tenant_id"], schema="auth")
    op.create_index("idx_alert_rules_tenant", "alert_rules", ["tenant_id"], schema="alerts")


def downgrade() -> None:
    op.drop_table("alert_rules", schema="alerts")
    op.drop_table("users", schema="auth")
    op.drop_table("connectors", schema="tenant_mgmt")
    op.drop_table("locations", schema="tenant_mgmt")
    op.drop_table("regions", schema="tenant_mgmt")
    op.drop_table("brands", schema="tenant_mgmt")
    op.drop_table("tenants", schema="tenant_mgmt")
    op.execute("DROP SCHEMA IF EXISTS alerts")
    op.execute("DROP SCHEMA IF EXISTS auth")
    op.execute("DROP SCHEMA IF EXISTS tenant_mgmt")
