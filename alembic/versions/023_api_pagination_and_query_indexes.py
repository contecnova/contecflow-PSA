"""Add composite indexes for paginated/filter-heavy API endpoints.

Revision ID: 023_api_pagination_and_query_indexes
Revises: 022_perf_composite_indexes
Create Date: 2026-04-14
"""

from alembic import op


revision = "023_api_pagination_and_query_indexes"
down_revision = "022_perf_composite_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Alerts listing: resolved/severity + org-scoped user/project filters + recency sort
    op.create_index("ix_023_alerts_resolved_created", "alerts", ["is_resolved", "created_at"], unique=False)
    op.create_index("ix_023_alerts_user_resolved_created", "alerts", ["user_id", "is_resolved", "created_at"], unique=False)
    op.create_index("ix_023_alerts_project_resolved_created", "alerts", ["project_id", "is_resolved", "created_at"], unique=False)
    op.create_index("ix_023_alerts_severity_resolved_created", "alerts", ["severity", "is_resolved", "created_at"], unique=False)

    # Documents listing by linked entities with archive filter and created_at sorting
    op.create_index("ix_023_documents_project_archived_created", "documents", ["project_id", "is_archived", "created_at"], unique=False)
    op.create_index("ix_023_documents_task_archived_created", "documents", ["task_id", "is_archived", "created_at"], unique=False)
    op.create_index("ix_023_documents_ticket_archived_created", "documents", ["ticket_id", "is_archived", "created_at"], unique=False)

    # Frequent imputation and user directory filters used in dashboards/reports
    op.create_index("ix_023_imputations_user_date", "imputations", ["user_id", "date"], unique=False)
    op.create_index("ix_023_users_org_role", "users", ["organization_id", "role"], unique=False)
    op.create_index("ix_023_users_org_department", "users", ["organization_id", "department"], unique=False)

    # Ticket filtered lists often combine status and recency ordering
    op.create_index("ix_023_sd_tickets_status_created", "sd_tickets", ["status", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_023_sd_tickets_status_created", table_name="sd_tickets")

    op.drop_index("ix_023_users_org_department", table_name="users")
    op.drop_index("ix_023_users_org_role", table_name="users")
    op.drop_index("ix_023_imputations_user_date", table_name="imputations")

    op.drop_index("ix_023_documents_ticket_archived_created", table_name="documents")
    op.drop_index("ix_023_documents_task_archived_created", table_name="documents")
    op.drop_index("ix_023_documents_project_archived_created", table_name="documents")

    op.drop_index("ix_023_alerts_severity_resolved_created", table_name="alerts")
    op.drop_index("ix_023_alerts_project_resolved_created", table_name="alerts")
    op.drop_index("ix_023_alerts_user_resolved_created", table_name="alerts")
    op.drop_index("ix_023_alerts_resolved_created", table_name="alerts")
