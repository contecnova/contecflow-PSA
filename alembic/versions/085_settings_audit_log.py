"""Append-only audit log for runtime flag + integration credential changes.

Stores who/when/from where/what changed. For secrets we keep only SHA-256
hashes so the table never contains plaintext credentials. See model
:class:`app.models.settings.SettingsAuditLog`.

Revision ID: 085_settings_audit_log
Revises: 084_integration_credentials
Create Date: 2026-05-17
"""

from alembic import op
import sqlalchemy as sa


revision = "085_settings_audit_log"
down_revision = "084_integration_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "settings_audit_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("actor_id", sa.String(36), nullable=True),
        sa.Column("actor_ip", sa.String(64), nullable=True),
        sa.Column("actor_ua", sa.String(255), nullable=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("provider", sa.String(40), nullable=True),
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("is_secret", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("old_value_hash", sa.String(64), nullable=True),
        sa.Column("new_value_hash", sa.String(64), nullable=True),
    )
    op.create_index("ix_settings_audit_log_created_at", "settings_audit_log", ["created_at"])
    op.create_index("ix_settings_audit_log_actor_id", "settings_audit_log", ["actor_id"])
    op.create_index("ix_settings_audit_log_organization_id", "settings_audit_log", ["organization_id"])
    op.create_index("ix_settings_audit_log_scope", "settings_audit_log", ["scope"])
    op.create_index("ix_settings_audit_log_provider", "settings_audit_log", ["provider"])
    op.create_index("ix_settings_audit_log_key", "settings_audit_log", ["key"])
    op.create_index("ix_settings_audit_scope_key", "settings_audit_log", ["scope", "key"])
    op.create_index("ix_settings_audit_created_at_desc", "settings_audit_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_settings_audit_created_at_desc", table_name="settings_audit_log")
    op.drop_index("ix_settings_audit_scope_key", table_name="settings_audit_log")
    op.drop_index("ix_settings_audit_log_key", table_name="settings_audit_log")
    op.drop_index("ix_settings_audit_log_provider", table_name="settings_audit_log")
    op.drop_index("ix_settings_audit_log_scope", table_name="settings_audit_log")
    op.drop_index("ix_settings_audit_log_organization_id", table_name="settings_audit_log")
    op.drop_index("ix_settings_audit_log_actor_id", table_name="settings_audit_log")
    op.drop_index("ix_settings_audit_log_created_at", table_name="settings_audit_log")
    op.drop_table("settings_audit_log")
