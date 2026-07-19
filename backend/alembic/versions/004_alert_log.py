"""Add alerts.alert_log table for full alert context storage

Revision ID: 004_alert_log
Revises: 003_workflow_cases
Create Date: 2026-06-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '004_alert_log'
down_revision = '003_workflow_cases'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'alert_log',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('alert_id', sa.String(255), nullable=False),
        sa.Column('tenant_id', UUID(as_uuid=True), nullable=False),
        sa.Column('rule_name', sa.String(255), nullable=True),
        sa.Column('severity', sa.String(20), nullable=False, server_default='low'),
        sa.Column('location_name', sa.String(255), nullable=True),
        sa.Column('brand_name', sa.String(255), nullable=True),
        sa.Column('risk_level', sa.String(20), nullable=True),
        sa.Column('risk_flags', JSONB(), nullable=False, server_default='[]'),
        sa.Column('topics', JSONB(), nullable=False, server_default='[]'),
        sa.Column('trigger_values', JSONB(), nullable=False, server_default='{}'),
        sa.Column('fired_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        schema='alerts',
    )
    op.create_index('ix_alert_log_tenant', 'alert_log', ['tenant_id'], schema='alerts')
    op.create_unique_constraint('uq_alert_log_alert_id', 'alert_log', ['alert_id'], schema='alerts')


def downgrade() -> None:
    op.drop_table('alert_log', schema='alerts')
