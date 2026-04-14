"""Incremental ADD COLUMN migrations (migrated from legacy migrate.py).

All the ALTER TABLE ADD COLUMN statements that were previously applied by the
custom migrate.py script are expressed here as proper Alembic operations.

Each op.add_column call is wrapped in a try/except so that this migration is
idempotent on databases that already have the column (e.g. fresh deployments
where create_all already created the table with all columns).

Revision ID: 002_incremental
Revises: 001_initial_tables
Create Date: 2026-04-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.exc import OperationalError

# revision identifiers, used by Alembic.
revision = '002_incremental'
down_revision = '001_initial_tables'
branch_labels = None
depends_on = None


def _add_column(table: str, col: sa.Column) -> None:
    """Add column only if it doesn't already exist (idempotent)."""
    try:
        op.add_column(table, col)
    except (OperationalError, Exception) as exc:
        if "duplicate column" in str(exc).lower() or "already exists" in str(exc).lower():
            pass  # Column already present — skip
        else:
            raise


def upgrade() -> None:
    # ── projects ──────────────────────────────────────────────────────────────
    _add_column('projects', sa.Column('department', sa.String(100), nullable=True))
    _add_column('projects', sa.Column('contract_amount', sa.Float(), nullable=True))
    _add_column('projects', sa.Column('billing_type', sa.String(20), server_default='time_material'))
    _add_column('projects', sa.Column('billing_rate', sa.Float(), nullable=True))
    _add_column('projects', sa.Column('client_name', sa.String(255), nullable=True))
    _add_column('projects', sa.Column('end_date_real', sa.Date(), nullable=True))
    _add_column('projects', sa.Column('end_date_planned', sa.Date(), nullable=True))
    _add_column('projects', sa.Column('budget_hours', sa.Float(), nullable=True))
    _add_column('projects', sa.Column('budget_amount', sa.Float(), nullable=True))
    _add_column('projects', sa.Column('currency', sa.String(10), server_default='EUR'))
    _add_column('projects', sa.Column('pm_id', sa.String(36), nullable=True))
    _add_column('projects', sa.Column('is_billable', sa.Boolean(), server_default='0'))
    _add_column('projects', sa.Column('tags', sa.String(500), nullable=True))
    _add_column('projects', sa.Column('risk_level', sa.String(20), server_default='low'))
    _add_column('projects', sa.Column('client_id', sa.String(36), nullable=True))
    _add_column('projects', sa.Column('version', sa.Integer(), server_default='1'))

    # ── users ─────────────────────────────────────────────────────────────────
    _add_column('users', sa.Column('hourly_rate', sa.Float(), nullable=True))
    _add_column('users', sa.Column('weekly_capacity_hours', sa.Float(), server_default='40'))
    _add_column('users', sa.Column('job_title', sa.String(100), nullable=True))
    _add_column('users', sa.Column('status', sa.String(20), server_default='active'))
    _add_column('users', sa.Column('is_superadmin', sa.Boolean(), server_default='0'))
    _add_column('users', sa.Column('refresh_token_jti', sa.String(36), nullable=True))
    _add_column('users', sa.Column('sso_provider', sa.String(30), nullable=True))
    _add_column('users', sa.Column('sso_subject', sa.String(255), nullable=True))
    _add_column('users', sa.Column('mfa_enabled', sa.Boolean(), server_default='0'))
    _add_column('users', sa.Column('mfa_secret', sa.String(64), nullable=True))

    # ── imputations ───────────────────────────────────────────────────────────
    _add_column('imputations', sa.Column('cost_amount', sa.Float(), nullable=True))
    _add_column('imputations', sa.Column('hourly_rate_snapshot', sa.Float(), nullable=True))
    _add_column('imputations', sa.Column('is_billable', sa.Boolean(), server_default='0'))
    _add_column('imputations', sa.Column('approved_by', sa.String(36), nullable=True))
    _add_column('imputations', sa.Column('approved_at', sa.DateTime(), nullable=True))
    _add_column('imputations', sa.Column('is_approved', sa.Boolean(), server_default='0'))
    _add_column('imputations', sa.Column('timer_session_id', sa.String(36), nullable=True))

    # ── tasks ─────────────────────────────────────────────────────────────────
    _add_column('tasks', sa.Column('blocked_reason', sa.String(255), nullable=True))
    _add_column('tasks', sa.Column('estimated_hours', sa.Float(), nullable=True))
    _add_column('tasks', sa.Column('completed_at', sa.DateTime(), nullable=True))
    _add_column('tasks', sa.Column('code', sa.String(30), nullable=True))
    _add_column('tasks', sa.Column('start_date', sa.Date(), nullable=True))
    _add_column('tasks', sa.Column('version', sa.Integer(), server_default='1'))

    # ── contracts ─────────────────────────────────────────────────────────────
    _add_column('contracts', sa.Column('monthly_retainer', sa.Float(), nullable=True))
    _add_column('contracts', sa.Column('signed_date', sa.Date(), nullable=True))
    _add_column('contracts', sa.Column('payment_terms', sa.String(100), nullable=True))
    _add_column('contracts', sa.Column('client_id', sa.String(36), nullable=True))

    # ── risks ─────────────────────────────────────────────────────────────────
    _add_column('risks', sa.Column('risk_score', sa.Float(), nullable=True))
    _add_column('risks', sa.Column('mitigation_plan', sa.Text(), nullable=True))
    _add_column('risks', sa.Column('contingency_plan', sa.Text(), nullable=True))
    _add_column('risks', sa.Column('response_type', sa.String(20), nullable=True))

    # ── change_requests ───────────────────────────────────────────────────────
    _add_column('change_requests', sa.Column('cost_impact', sa.Float(), nullable=True))
    _add_column('change_requests', sa.Column('scope_impact', sa.Text(), nullable=True))

    # ── wiki_pages ────────────────────────────────────────────────────────────
    _add_column('wiki_pages', sa.Column('visibility', sa.String(20), server_default='team'))

    # ── opportunities ─────────────────────────────────────────────────────────
    _add_column('opportunities', sa.Column('client_id', sa.String(36), nullable=True))

    # ── invoices ──────────────────────────────────────────────────────────────
    _add_column('invoices', sa.Column('client_id', sa.String(36), nullable=True))

    # ── sd_tickets ────────────────────────────────────────────────────────────
    _add_column('sd_tickets', sa.Column('client_id', sa.String(36), nullable=True))
    _add_column('sd_tickets', sa.Column('linked_resource_type', sa.String(50), nullable=True))
    _add_column('sd_tickets', sa.Column('linked_resource_id', sa.String(36), nullable=True))

    # ── client_users ──────────────────────────────────────────────────────────
    _add_column('client_users', sa.Column('client_org_id', sa.String(36), nullable=True))
    _add_column('client_users', sa.Column('phone', sa.String(50), nullable=True))
    _add_column('client_users', sa.Column('language', sa.String(10), server_default='es'))

    # ── client_portal_configs ─────────────────────────────────────────────────
    _add_column('client_portal_configs', sa.Column('default_language', sa.String(10), server_default='es'))
    _add_column('client_portal_configs', sa.Column('allow_profile_edit', sa.Boolean(), server_default='1'))
    _add_column('client_portal_configs', sa.Column('allow_pwd_change', sa.Boolean(), server_default='1'))
    _add_column('client_portal_configs', sa.Column('max_portal_users', sa.Integer(), server_default='10'))
    _add_column('client_portal_configs', sa.Column('max_open_tickets', sa.Integer(), nullable=True))
    _add_column('client_portal_configs', sa.Column('sla_tier', sa.String(50), nullable=True))
    _add_column('client_portal_configs', sa.Column('logo_url', sa.String(500), nullable=True))
    _add_column('client_portal_configs', sa.Column('accent_color', sa.String(10), nullable=True))

    # ── client_documents ──────────────────────────────────────────────────────
    _add_column('client_documents', sa.Column('signed_by_name', sa.String(255), nullable=True))
    _add_column('client_documents', sa.Column('signed_by_job_title', sa.String(255), nullable=True))
    _add_column('client_documents', sa.Column('signature_ip', sa.String(64), nullable=True))
    _add_column('client_documents', sa.Column('signed_pdf_path', sa.String(500), nullable=True))

    # ── project_milestones ────────────────────────────────────────────────────
    _add_column('project_milestones', sa.Column('billing_status', sa.String(30), server_default='pending'))
    _add_column('project_milestones', sa.Column('completed_by', sa.String(36), nullable=True))
    _add_column('project_milestones', sa.Column('approval_requested_at', sa.DateTime(), nullable=True))
    _add_column('project_milestones', sa.Column('approval_requested_by', sa.String(36), nullable=True))
    _add_column('project_milestones', sa.Column('approved_at', sa.DateTime(), nullable=True))
    _add_column('project_milestones', sa.Column('approved_by', sa.String(36), nullable=True))
    _add_column('project_milestones', sa.Column('rejected_at', sa.DateTime(), nullable=True))
    _add_column('project_milestones', sa.Column('rejected_by', sa.String(36), nullable=True))
    _add_column('project_milestones', sa.Column('rejection_reason', sa.Text(), nullable=True))
    _add_column('project_milestones', sa.Column('invoice_id', sa.String(36), nullable=True))

    # ── rate_entries ──────────────────────────────────────────────────────────
    _add_column('rate_entries', sa.Column('escalation_pct', sa.Float(), server_default='0.0'))
    _add_column('rate_entries', sa.Column('notes', sa.String(255), nullable=True))

    # ── revenue_recognition_rules ─────────────────────────────────────────────
    _add_column('revenue_recognition_rules', sa.Column('milestone_filter', sa.String(50), server_default='approved'))

    # ── alerts ────────────────────────────────────────────────────────────────
    _add_column('alerts', sa.Column('dedup_key', sa.String(200), nullable=True))

    # ── ai_kb_articles ────────────────────────────────────────────────────────
    _add_column('ai_kb_articles', sa.Column('embedding', sa.Text(), nullable=True))


def downgrade() -> None:
    """Revert the ADD COLUMN operations from upgrade().

    Uses batch_alter_table for SQLite compatibility (SQLite < 3.35 cannot
    DROP COLUMN directly). Each drop is wrapped to be idempotent.
    """
    def _drop_column(table: str, col_name: str) -> None:
        try:
            with op.batch_alter_table(table) as batch:
                batch.drop_column(col_name)
        except Exception as exc:
            if "no such column" in str(exc).lower() or "does not exist" in str(exc).lower():
                pass  # Already absent — skip
            else:
                raise

    # ── projects ──────────────────────────────────────────────────────────────
    for col in ['department', 'contract_amount', 'billing_type', 'billing_rate',
                'client_name', 'end_date_real', 'end_date_planned', 'budget_hours',
                'budget_amount', 'currency', 'pm_id', 'is_billable', 'tags',
                'risk_level', 'client_id', 'version']:
        _drop_column('projects', col)

    # ── users ─────────────────────────────────────────────────────────────────
    for col in ['hourly_rate', 'weekly_capacity_hours', 'job_title', 'status',
                'is_superadmin', 'refresh_token_jti', 'sso_provider', 'sso_subject',
                'mfa_enabled', 'mfa_secret']:
        _drop_column('users', col)

    # ── imputations ───────────────────────────────────────────────────────────
    for col in ['cost_amount', 'hourly_rate_snapshot', 'is_billable', 'approved_by',
                'approved_at', 'is_approved', 'timer_session_id']:
        _drop_column('imputations', col)

    # ── tasks ─────────────────────────────────────────────────────────────────
    for col in ['blocked_reason', 'estimated_hours', 'completed_at', 'code',
                'start_date', 'version']:
        _drop_column('tasks', col)

    # ── contracts ─────────────────────────────────────────────────────────────
    for col in ['monthly_retainer', 'signed_date', 'payment_terms', 'client_id']:
        _drop_column('contracts', col)

    # ── risks ─────────────────────────────────────────────────────────────────
    for col in ['risk_score', 'mitigation_plan', 'contingency_plan', 'response_type']:
        _drop_column('risks', col)

    # ── change_requests ───────────────────────────────────────────────────────
    for col in ['cost_impact', 'scope_impact']:
        _drop_column('change_requests', col)

    # ── wiki_pages ────────────────────────────────────────────────────────────
    _drop_column('wiki_pages', 'visibility')

    # ── opportunities ─────────────────────────────────────────────────────────
    _drop_column('opportunities', 'client_id')

    # ── invoices ──────────────────────────────────────────────────────────────
    _drop_column('invoices', 'client_id')

    # ── sd_tickets ────────────────────────────────────────────────────────────
    for col in ['client_id', 'linked_resource_type', 'linked_resource_id']:
        _drop_column('sd_tickets', col)

    # ── client_users ──────────────────────────────────────────────────────────
    for col in ['client_org_id', 'phone', 'language']:
        _drop_column('client_users', col)

    # ── client_portal_configs ─────────────────────────────────────────────────
    for col in ['default_language', 'allow_profile_edit', 'allow_pwd_change',
                'max_portal_users', 'max_open_tickets', 'sla_tier', 'logo_url',
                'accent_color']:
        _drop_column('client_portal_configs', col)

    # ── client_documents ──────────────────────────────────────────────────────
    for col in ['signed_by_name', 'signed_by_job_title', 'signature_ip', 'signed_pdf_path']:
        _drop_column('client_documents', col)

    # ── project_milestones ────────────────────────────────────────────────────
    for col in ['billing_status', 'completed_by', 'approval_requested_at',
                'approval_requested_by', 'approved_at', 'approved_by',
                'rejected_at', 'rejected_by', 'rejection_reason', 'invoice_id']:
        _drop_column('project_milestones', col)

    # ── rate_entries ──────────────────────────────────────────────────────────
    for col in ['escalation_pct', 'notes']:
        _drop_column('rate_entries', col)

    # ── revenue_recognition_rules ─────────────────────────────────────────────
    _drop_column('revenue_recognition_rules', 'milestone_filter')

    # ── alerts ────────────────────────────────────────────────────────────────
    _drop_column('alerts', 'dedup_key')
