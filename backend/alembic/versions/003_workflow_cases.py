"""Add workflow schema and cases/case_events tables

Revision ID: 003_workflow_cases
Revises: 002_reputation_scores
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '003_workflow_cases'
down_revision = '002_reputation_scores'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS workflow")

    # ── Cases table ──────────────────────────────────────────────────────
    op.create_table(
        'cases',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', UUID(as_uuid=True),
                  sa.ForeignKey('tenant_mgmt.tenants.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('brand_id', UUID(as_uuid=True), nullable=True),
        sa.Column('location_id', UUID(as_uuid=True), nullable=True),
        sa.Column('alert_id', sa.String(255), nullable=False),
        sa.Column('rule_name', sa.String(255), nullable=True),
        sa.Column('severity', sa.String(20), nullable=False, server_default='low'),
        # FSM state: NEW -> ASSIGNED -> IN_PROGRESS -> RESOLVED / ESCALATED
        sa.Column('status', sa.String(20), nullable=False, server_default='NEW'),
        sa.Column('assigned_to', sa.String(255), nullable=True),
        sa.Column('assignment_strategy', sa.String(50), nullable=True),
        sa.Column('sla_minutes', sa.Integer(), nullable=False, server_default='60'),
        sa.Column('sla_deadline', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sla_breached', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('context', JSONB(), nullable=False, server_default='{}'),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        schema='workflow',
    )

    op.create_index('ix_cases_tenant', 'cases', ['tenant_id'], schema='workflow')
    op.create_index('ix_cases_status', 'cases', ['status'], schema='workflow')
    op.create_index('ix_cases_sla', 'cases', ['sla_deadline', 'status'], schema='workflow')
    op.create_unique_constraint('uq_cases_alert_id', 'cases', ['alert_id'], schema='workflow')

    # ── Case events (audit trail / state transitions) ──────────────────────
    op.create_table(
        'case_events',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('case_id', UUID(as_uuid=True),
                  sa.ForeignKey('workflow.cases.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        # e.g. created, assigned, status_changed, escalated, resolved, sla_breached
        sa.Column('from_status', sa.String(20), nullable=True),
        sa.Column('to_status', sa.String(20), nullable=True),
        sa.Column('actor', sa.String(255), nullable=True),
        sa.Column('details', JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        schema='workflow',
    )

    op.create_index('ix_case_events_case', 'case_events', ['case_id'], schema='workflow')

    # ── Assignment pool (round-robin / skill-based agents) ──────────────────
    op.create_table(
        'agents',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', UUID(as_uuid=True),
                  sa.ForeignKey('tenant_mgmt.tenants.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('skills', JSONB(), nullable=False, server_default='[]'),
        # e.g. ["hygiene", "legal", "general"]
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        schema='workflow',
    )

    op.create_index('ix_agents_tenant', 'agents', ['tenant_id'], schema='workflow')


def downgrade() -> None:
    op.drop_table('agents', schema='workflow')
    op.drop_table('case_events', schema='workflow')
    op.drop_table('cases', schema='workflow')
    op.execute("DROP SCHEMA IF EXISTS workflow CASCADE")
