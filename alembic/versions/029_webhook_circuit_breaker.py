"""029 — Add circuit-breaker columns to webhooks table

Adds consecutive_failures (INTEGER, default 0) and suspended_at (DATETIME)
to support automatic webhook suspension after repeated delivery failures.

Revision ID: 029_webhook_circuit_breaker
Revises: 028_sd_tickets_sla_metrics
Create Date: 2026-04-22
"""
from alembic import op
import sqlalchemy as sa

revision = "029_webhook_circuit_breaker"
down_revision = "028_sd_tickets_sla_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name

    if dialect == "sqlite":
        existing = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(webhooks)"))}
        if "consecutive_failures" not in existing:
            op.execute(sa.text(
                "ALTER TABLE webhooks ADD COLUMN consecutive_failures INTEGER NOT NULL DEFAULT 0"
            ))
        if "suspended_at" not in existing:
            op.execute(sa.text(
                "ALTER TABLE webhooks ADD COLUMN suspended_at DATETIME"
            ))
    else:
        # PostgreSQL / other — use has_column check via information_schema
        for col, definition in [
            ("consecutive_failures", "INTEGER NOT NULL DEFAULT 0"),
            ("suspended_at", "TIMESTAMP WITH TIME ZONE"),
        ]:
            exists = conn.execute(sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'webhooks' AND column_name = :col"
            ), {"col": col}).fetchone()
            if not exists:
                op.execute(sa.text(f"ALTER TABLE webhooks ADD COLUMN {col} {definition}"))


def downgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name

    if dialect == "sqlite":
        # SQLite does not support DROP COLUMN before 3.35 — recreate the table
        op.execute(sa.text("""
            CREATE TABLE webhooks_backup AS
            SELECT id, name, url, secret, events, is_active, project_id,
                   total_deliveries, failed_deliveries, last_triggered_at,
                   created_by, created_at, updated_at
            FROM webhooks
        """))
        op.execute(sa.text("DROP TABLE webhooks"))
        op.execute(sa.text("ALTER TABLE webhooks_backup RENAME TO webhooks"))
    else:
        op.drop_column("webhooks", "suspended_at")
        op.drop_column("webhooks", "consecutive_failures")
