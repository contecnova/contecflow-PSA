"""Add composite indexes for high-volume list and filter endpoints.

Revision ID: 022_perf_composite_indexes
Revises: 021_imputation_unique_user_task_date
Create Date: 2026-04-14
"""

from alembic import op


revision = "022_perf_composite_indexes"
down_revision = "021_imputation_unique_user_task_date"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_022_sd_tickets_status_priority", "sd_tickets", ["status", "priority"], unique=False)
    op.create_index("ix_022_sd_tickets_assignee_status", "sd_tickets", ["assigned_to_user_id", "status"], unique=False)
    op.create_index("ix_022_sd_tickets_project_status", "sd_tickets", ["project_id", "status"], unique=False)

    op.create_index("ix_022_sd_problems_status_priority", "sd_problems", ["status", "priority"], unique=False)
    op.create_index("ix_022_sd_ci_project_status", "sd_configuration_items", ["project_id", "status"], unique=False)
    op.create_index("ix_022_sd_changes_status_created", "sd_change_requests", ["status", "created_at"], unique=False)

    op.create_index("ix_022_tasks_project_status", "tasks", ["project_id", "status"], unique=False)
    op.create_index("ix_022_tasks_assignee_status", "tasks", ["assignee_id", "status"], unique=False)

    op.create_index("ix_022_imputations_project_date", "imputations", ["project_id", "date"], unique=False)
    op.create_index("ix_022_invoices_status_issue_date", "invoices", ["status", "issue_date"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_022_invoices_status_issue_date", table_name="invoices")
    op.drop_index("ix_022_imputations_project_date", table_name="imputations")

    op.drop_index("ix_022_tasks_assignee_status", table_name="tasks")
    op.drop_index("ix_022_tasks_project_status", table_name="tasks")

    op.drop_index("ix_022_sd_changes_status_created", table_name="sd_change_requests")
    op.drop_index("ix_022_sd_ci_project_status", table_name="sd_configuration_items")
    op.drop_index("ix_022_sd_problems_status_priority", table_name="sd_problems")

    op.drop_index("ix_022_sd_tickets_project_status", table_name="sd_tickets")
    op.drop_index("ix_022_sd_tickets_assignee_status", table_name="sd_tickets")
    op.drop_index("ix_022_sd_tickets_status_priority", table_name="sd_tickets")
