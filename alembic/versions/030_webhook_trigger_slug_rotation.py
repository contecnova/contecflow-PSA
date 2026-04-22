"""030 — Add slug rotation columns to webhook_triggers table

Adds slug_rotated_at (DATETIME) and slug_expires_at (DATETIME) to support
manual slug rotation and optional expiry enforcement.

Revision ID: 030_webhook_trigger_slug_rotation
Revises: 029_webhook_circuit_breaker
Create Date: 2026-04-22
"""
from alembic import op
import sqlalchemy as sa

revision = "030_webhook_trigger_slug_rotation"
down_revision = "029_webhook_circuit_breaker"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name

    if dialect == "sqlite":
        existing = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(webhook_triggers)"))}
        for col, definition in [
            ("slug_rotated_at", "DATETIME"),
            ("slug_expires_at", "DATETIME"),
        ]:
            if col not in existing:
                op.execute(sa.text(f"ALTER TABLE webhook_triggers ADD COLUMN {col} DATETIME"))
    else:
        for col in ("slug_rotated_at", "slug_expires_at"):
            exists = conn.execute(sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'webhook_triggers' AND column_name = :col"
            ), {"col": col}).fetchone()
            if not exists:
                op.execute(sa.text(
                    f"ALTER TABLE webhook_triggers ADD COLUMN {col} TIMESTAMP WITH TIME ZONE"
                ))


def downgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name

    if dialect == "sqlite":
        op.execute(sa.text("""
            CREATE TABLE webhook_triggers_backup AS
            SELECT id, organization_id, name, slug, secret, workflow_id, rule_id,
                   is_active, last_fired_at, fire_count, field_mapping, created_by, created_at
            FROM webhook_triggers
        """))
        op.execute(sa.text("DROP TABLE webhook_triggers"))
        op.execute(sa.text("ALTER TABLE webhook_triggers_backup RENAME TO webhook_triggers"))
    else:
        op.drop_column("webhook_triggers", "slug_expires_at")
        op.drop_column("webhook_triggers", "slug_rotated_at")
