"""Add analytics schema and reputation_scores table

Revision ID: 002_reputation_scores
Revises: 001_phase1_foundation
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '002_reputation_scores'
down_revision = '001_phase1_foundation'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create analytics schema
    op.execute("CREATE SCHEMA IF NOT EXISTS analytics")

    # Create reputation_scores table
    op.create_table(
        'reputation_scores',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', UUID(as_uuid=True),
                  sa.ForeignKey('tenant_mgmt.tenants.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('brand_id', UUID(as_uuid=True),
                  sa.ForeignKey('tenant_mgmt.brands.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('region_id', UUID(as_uuid=True),
                  sa.ForeignKey('tenant_mgmt.regions.id', ondelete='CASCADE'),
                  nullable=True),
        sa.Column('location_id', UUID(as_uuid=True),
                  sa.ForeignKey('tenant_mgmt.locations.id', ondelete='CASCADE'),
                  nullable=True),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('rating_avg', sa.Float(), nullable=False),
        sa.Column('sentiment_avg', sa.Float(), nullable=False),
        sa.Column('review_count', sa.Integer(), default=0),
        sa.Column('positive_count', sa.Integer(), default=0),
        sa.Column('negative_count', sa.Integer(), default=0),
        sa.Column('neutral_count', sa.Integer(), default=0),
        sa.Column('scope', sa.String(20), nullable=False, server_default='location'),
        sa.Column('last_review_id', sa.String(255), nullable=True),
        sa.Column('last_review_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        schema='analytics',
    )

    # Indexes for fast lookups
    op.create_index('ix_rep_scores_tenant', 'reputation_scores',
                    ['tenant_id'], schema='analytics')
    op.create_index('ix_rep_scores_brand', 'reputation_scores',
                    ['brand_id'], schema='analytics')
    op.create_index('ix_rep_scores_location', 'reputation_scores',
                    ['location_id'], schema='analytics')
    op.create_index('ix_rep_scores_scope', 'reputation_scores',
                    ['scope', 'tenant_id'], schema='analytics')

    # Unique constraint: one score row per scope entity
    op.create_unique_constraint(
        'uq_rep_scores_location',
        'reputation_scores',
        ['location_id', 'scope'],
        schema='analytics',
    )


def downgrade() -> None:
    op.drop_table('reputation_scores', schema='analytics')
    op.execute("DROP SCHEMA IF EXISTS analytics CASCADE")
