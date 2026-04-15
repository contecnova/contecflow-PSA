"""
Migration: Multi-tenancy — add organization_id to org-level config models,
           make AppSetting tenant-aware with per-tenant overrides.

Revision ID: 011_multitenancy_org_id
Revises: 010_security_observability
Create Date: 2026-04-15 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "011_multitenancy_org_id"
down_revision = "010_security_observability"
branch_labels = None
depends_on = None


def upgrade():
    # ── maintenance_windows: tenant-scoped ─────────────────────────────────────
    with op.batch_alter_table("maintenance_windows") as batch_op:
        batch_op.add_column(
            sa.Column("organization_id", sa.String(36),
                      sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                      nullable=True, index=True)
        )

    # ── webhook_triggers: tenant-scoped ────────────────────────────────────────
    with op.batch_alter_table("webhook_triggers") as batch_op:
        batch_op.add_column(
            sa.Column("organization_id", sa.String(36),
                      sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                      nullable=True, index=True)
        )

    # ── integration_configs: tenant-scoped ─────────────────────────────────────
    with op.batch_alter_table("integration_configs") as batch_op:
        batch_op.add_column(
            sa.Column("organization_id", sa.String(36),
                      sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                      nullable=True, index=True)
        )

    # ── email_templates: tenant-scoped ─────────────────────────────────────────
    with op.batch_alter_table("email_templates") as batch_op:
        batch_op.add_column(
            sa.Column("organization_id", sa.String(36),
                      sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                      nullable=True, index=True)
        )

    # ── app_settings: add org_id + composite unique (key, org_id) ──────────────
    # 1. Drop the old unique constraint on just `key` (name varies by DB).
    #    Use op.execute for portability; batch_alter_table handles SQLite.
    with op.batch_alter_table("app_settings") as batch_op:
        batch_op.add_column(
            sa.Column("organization_id", sa.String(36),
                      sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                      nullable=True, index=True)
        )
        # Drop the old single-column unique on key and replace with composite.
        try:
            batch_op.drop_constraint("uq_app_settings_key", type_="unique")
        except Exception:
            pass  # constraint may have a different name or not exist
        batch_op.create_unique_constraint(
            "uq_app_settings_key_org", ["key", "organization_id"]
        )


def downgrade():
    with op.batch_alter_table("app_settings") as batch_op:
        batch_op.drop_constraint("uq_app_settings_key_org", type_="unique")
        batch_op.drop_column("organization_id")
        batch_op.create_unique_constraint("uq_app_settings_key", ["key"])

    with op.batch_alter_table("email_templates") as batch_op:
        batch_op.drop_column("organization_id")

    with op.batch_alter_table("integration_configs") as batch_op:
        batch_op.drop_column("organization_id")

    with op.batch_alter_table("webhook_triggers") as batch_op:
        batch_op.drop_column("organization_id")

    with op.batch_alter_table("maintenance_windows") as batch_op:
        batch_op.drop_column("organization_id")
