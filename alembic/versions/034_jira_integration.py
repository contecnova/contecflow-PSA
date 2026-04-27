"""Alembic migration — Jira SM bidirectional integration tables.

Revision ID: 034_jira_integration
Revises: 033_itsm_phase3
Create Date: 2026-04-27
"""
from alembic import op
import sqlalchemy as sa

revision = "034_jira_integration"
down_revision = "033_itsm_phase3"
branch_labels = None
depends_on = None


def _table_exists(table: str) -> bool:
    """Return True when table already exists (defensive upgrade)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def upgrade() -> None:
    if not _table_exists("sd_jira_configs"):
        op.create_table(
            "sd_jira_configs",
            sa.Column("id",                             sa.String(36),  primary_key=True),
            sa.Column("name",                           sa.String(100), nullable=False),
            sa.Column("jira_base_url",                  sa.String(500), nullable=False),
            sa.Column("jira_email",                     sa.String(255), nullable=False),
            sa.Column("jira_api_token_enc",             sa.Text(),      nullable=False),
            sa.Column("jira_project_key",               sa.String(50),  nullable=False),
            sa.Column("jira_issue_type_incident",       sa.String(100), server_default="Incident"),
            sa.Column("jira_issue_type_service_request",sa.String(100), server_default="Service Request"),
            sa.Column("jira_issue_type_change",         sa.String(100), server_default="Change"),
            sa.Column("jira_issue_type_problem",        sa.String(100), server_default="Problem"),
            sa.Column("sync_direction",                 sa.String(40),  server_default="bidirectional"),
            sa.Column("sync_comments",                  sa.Boolean(),   server_default="1"),
            sa.Column("sync_status_changes",            sa.Boolean(),   server_default="1"),
            sa.Column("sync_priority_changes",          sa.Boolean(),   server_default="1"),
            sa.Column("sync_assignments",               sa.Boolean(),   server_default="0"),
            sa.Column("sync_interval_minutes",          sa.Integer(),   server_default="5"),
            sa.Column("status_map_json",                sa.Text(),      nullable=True),
            sa.Column("priority_map_json",              sa.Text(),      nullable=True),
            sa.Column("is_active",                      sa.Boolean(),   server_default="1"),
            sa.Column("last_full_sync_at",              sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at",                     sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at",                     sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by_user_id",             sa.String(36),  sa.ForeignKey("users.id"), nullable=True),
        )

    if not _table_exists("sd_jira_sync_map"):
        op.create_table(
            "sd_jira_sync_map",
            sa.Column("id",                     sa.String(36), primary_key=True),
            sa.Column("config_id",              sa.String(36), sa.ForeignKey("sd_jira_configs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("ticket_id",              sa.String(36), sa.ForeignKey("sd_tickets.id", ondelete="CASCADE"), nullable=False),
            sa.Column("jira_issue_key",         sa.String(50), nullable=False),
            sa.Column("jira_issue_id",          sa.String(50), nullable=True),
            sa.Column("sync_status",            sa.String(20), server_default="pending"),
            sa.Column("last_synced_at",         sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_jira_updated_at",   sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_ticket_updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("sync_error",             sa.Text(), nullable=True),
            sa.Column("created_at",             sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_sd_jira_sync_map_config_id",      "sd_jira_sync_map", ["config_id"])
        op.create_index("ix_sd_jira_sync_map_ticket_id",      "sd_jira_sync_map", ["ticket_id"])
        op.create_index("ix_sd_jira_sync_map_jira_issue_key", "sd_jira_sync_map", ["jira_issue_key"])

    if not _table_exists("sd_jira_sync_log"):
        op.create_table(
            "sd_jira_sync_log",
            sa.Column("id",               sa.String(36), primary_key=True),
            sa.Column("config_id",        sa.String(36), sa.ForeignKey("sd_jira_configs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("ticket_id",        sa.String(36), sa.ForeignKey("sd_tickets.id", ondelete="SET NULL"), nullable=True),
            sa.Column("jira_issue_key",   sa.String(50), nullable=True),
            sa.Column("event_type",       sa.String(40), nullable=False),
            sa.Column("direction",        sa.String(40), nullable=False),
            sa.Column("payload_json",     sa.Text(), nullable=True),
            sa.Column("response_json",    sa.Text(), nullable=True),
            sa.Column("success",          sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("error_message",    sa.Text(), nullable=True),
            sa.Column("occurred_at",      sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_sd_jira_sync_log_config_id",  "sd_jira_sync_log", ["config_id"])
        op.create_index("ix_sd_jira_sync_log_ticket_id",  "sd_jira_sync_log", ["ticket_id"])
        op.create_index("ix_sd_jira_sync_log_occurred_at","sd_jira_sync_log", ["occurred_at"])

    op.create_table(
        "sd_jira_field_map",
        sa.Column("id",                 sa.String(36), primary_key=True),
        sa.Column("config_id",          sa.String(36), sa.ForeignKey("sd_jira_configs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contecflow_field",   sa.String(100), nullable=False),
        sa.Column("jira_field_id",      sa.String(100), nullable=False),
        sa.Column("transform_fn",       sa.String(50), nullable=True),
        sa.Column("is_active",          sa.Boolean(), server_default="1"),
    )
    op.create_index("ix_sd_jira_field_map_config_id", "sd_jira_field_map", ["config_id"])


def downgrade() -> None:
    op.drop_index("ix_sd_jira_field_map_config_id",  table_name="sd_jira_field_map")
    op.drop_table("sd_jira_field_map")
    op.drop_index("ix_sd_jira_sync_log_occurred_at", table_name="sd_jira_sync_log")
    op.drop_index("ix_sd_jira_sync_log_ticket_id",   table_name="sd_jira_sync_log")
    op.drop_index("ix_sd_jira_sync_log_config_id",   table_name="sd_jira_sync_log")
    op.drop_table("sd_jira_sync_log")
    op.drop_index("ix_sd_jira_sync_map_jira_issue_key", table_name="sd_jira_sync_map")
    op.drop_index("ix_sd_jira_sync_map_ticket_id",   table_name="sd_jira_sync_map")
    op.drop_index("ix_sd_jira_sync_map_config_id",   table_name="sd_jira_sync_map")
    op.drop_table("sd_jira_sync_map")
    op.drop_table("sd_jira_configs")
