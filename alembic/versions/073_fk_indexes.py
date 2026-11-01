"""Add missing indexes on foreign-key columns (service_desk + billing + collab)

Revision ID: 073_fk_indexes
Revises: 072_dev_plans
Create Date: 2026-05-11

Rationale: 55 ForeignKey columns across service_desk, billing_reports and
collaboration lacked `index=True`. Postgres planners will still pick FK joins
via seq-scan when no index exists, which becomes O(n) at production volume
and amplifies lock contention on cascade deletes.

This migration is idempotent (CREATE INDEX IF NOT EXISTS), so safe to run
multiple times. On Postgres we issue CONCURRENTLY to avoid blocking writers
on tables with substantial traffic.
"""
from alembic import op
import sqlalchemy as sa


revision = "073_fk_indexes"
down_revision = "072_dev_plans"
branch_labels = None
depends_on = None


# (table, column) pairs that need an index
INDEXES = [
    # service_desk
    ("sd_service_items", "approval_user_id"),
    ("sd_configuration_items", "project_id"),
    ("sd_configuration_items", "sla_policy_id"),
    ("sd_agent_group_members", "user_id"),
    ("sd_tickets", "requester_user_id"),
    ("sd_tickets", "contract_id"),
    ("sd_tickets", "service_item_id"),
    ("sd_tickets", "parent_ticket_id"),
    ("sd_tickets", "kb_article_id"),
    ("sd_ticket_comments", "author_client_id"),
    ("sd_ticket_time_logs", "user_id"),
    ("sd_problems", "project_id"),
    ("sd_kb_articles", "category_id"),
    ("sd_kb_articles", "service_item_id"),
    ("sd_kb_articles", "author_id"),
    ("sd_announcements", "ci_id"),
    ("sd_sla_events", "created_by"),
    ("sd_change_requests", "requester_id"),
    ("sd_change_requests", "approver_id"),
    ("sd_change_requests", "approved_by"),
    ("sd_change_requests", "related_problem_id"),
    ("sd_major_incidents", "communication_lead_id"),
    ("sd_ticket_templates", "default_group_id"),
    ("sd_ticket_templates", "auto_assign_to_id"),
    ("sd_canned_responses", "created_by"),
    ("sd_oncall_entries", "user_id"),
    ("sd_ticket_watchers", "user_id"),
    ("sd_ticket_merges", "merged_id"),
    ("sd_ticket_merges", "merged_by_user"),
    ("sd_sla_holidays", "sla_policy_id"),
    ("sd_assets", "managed_by_user_id"),
    ("sd_status_components", "ci_id"),
    ("sd_status_incidents", "ticket_id"),
    ("sd_known_errors", "published_by"),
    ("sd_problem_rca_templates", "created_by"),
    # billing_reports
    ("sla_breach_logs", "agent_id"),
    ("automation_workflows", "created_by"),
    ("invoices", "contract_id"),
    ("invoices", "created_by"),
    ("report_definitions", "created_by"),
    ("approval_groups", "created_by"),
    ("approval_steps", "approver_user_id"),
    ("grc_role_permissions", "updated_by"),
    ("grc_audit_log", "user_id"),
    ("grc_sod_violations", "user_id"),
    # collaboration
    ("collaboration_teams", "created_by"),
    ("collaboration_group_conversations", "created_by"),
    ("collaboration_message_versions", "edited_by_user_id"),
    ("collaboration_mentions", "mentioned_channel_id"),
    ("collaboration_attachments", "uploaded_by_user_id"),
    ("collaboration_notifications", "message_id"),
    ("collaboration_legal_holds", "created_by"),
    ("collaboration_pinned_messages", "pinned_by"),
    ("collaboration_drafts", "parent_message_id"),
    ("collaboration_bot_executions", "triggered_by_user_id"),
]


def _index_name(table: str, column: str) -> str:
    # Truncamos a 63 chars (límite de Postgres)
    name = f"ix_{table}_{column}"
    return name[:63]


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    is_postgres = bind.dialect.name == "postgresql"

    existing_tables = set(insp.get_table_names())

    # En Postgres usamos CONCURRENTLY para no bloquear writers en producción.
    # CONCURRENTLY no funciona dentro de una transacción. Antes se lanzaba un
    # COMMIT a pelo: el resto de la cadena corría sin transacción, un fallo
    # dejaba la base guardada a medias (en la 074) y los errores que tragaba
    # un try/except no abortaban nada, así que una pasada de principio a fin
    # los escondía. autocommit_block() cierra la transacción, ejecuta fuera de
    # ella y abre una nueva al salir.
    with op.get_context().autocommit_block():
        for table, column in INDEXES:
            if table not in existing_tables:
                continue
            existing_idx = {ix["name"] for ix in insp.get_indexes(table)}
            idx_name = _index_name(table, column)
            if idx_name in existing_idx:
                continue
            if is_postgres:
                op.execute(
                    f'CREATE INDEX CONCURRENTLY IF NOT EXISTS '
                    f'"{idx_name}" ON "{table}" ("{column}")'
                )
            else:
                # SQLite: CONCURRENTLY no soportado; IF NOT EXISTS sí.
                op.execute(
                    f'CREATE INDEX IF NOT EXISTS "{idx_name}" ON "{table}" ("{column}")'
                )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    with op.get_context().autocommit_block():
        for table, column in INDEXES:
            idx_name = _index_name(table, column)
            if is_postgres:
                op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS "{idx_name}"')
            else:
                op.execute(f'DROP INDEX IF EXISTS "{idx_name}"')
