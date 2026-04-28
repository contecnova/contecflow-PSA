"""040 – ITSM-P04: CMDB Drift Detection + per-provider scan cadence

Adds to cmdb_items:
  - config_hash         — SHA-256 of attributes JSON (detects config drift)
  - drift_detected_at   — when drift was last detected for this CI
  - baseline_attributes — JSON snapshot of attributes at last manual approval

Adds to cmdb_discovery_providers:
  - scan_interval_minutes — how often to run this provider (default 60)
  - next_run_at           — next scheduled run (set by Celery after each run)

Revision ID: 040_cmdb_drift_detection
Revises: 039_itsm_problem_kedb
Create Date: 2026-04-28
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "040_cmdb_drift_detection"
down_revision = "039_itsm_problem_kedb"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return any(c["name"] == column for c in insp.get_columns(table))


def _table_exists(table: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return table in insp.get_table_names()


def upgrade() -> None:
    # ── cmdb_items: drift detection fields ──────────────────────────────────
    if _table_exists("cmdb_items"):
        if not _column_exists("cmdb_items", "config_hash"):
            op.add_column(
                "cmdb_items",
                sa.Column("config_hash", sa.String(64), nullable=True),
            )
        if not _column_exists("cmdb_items", "drift_detected_at"):
            op.add_column(
                "cmdb_items",
                sa.Column("drift_detected_at", sa.DateTime(timezone=True), nullable=True),
            )
        if not _column_exists("cmdb_items", "baseline_attributes"):
            op.add_column(
                "cmdb_items",
                sa.Column("baseline_attributes", sa.Text(), nullable=True),
            )

    # ── cmdb_discovery_providers: cadence control ────────────────────────────
    if _table_exists("cmdb_discovery_providers"):
        if not _column_exists("cmdb_discovery_providers", "scan_interval_minutes"):
            op.add_column(
                "cmdb_discovery_providers",
                sa.Column(
                    "scan_interval_minutes",
                    sa.Integer(),
                    nullable=False,
                    server_default="60",
                ),
            )
        if not _column_exists("cmdb_discovery_providers", "next_run_at"):
            op.add_column(
                "cmdb_discovery_providers",
                sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
            )


def downgrade() -> None:
    if _table_exists("cmdb_discovery_providers"):
        if _column_exists("cmdb_discovery_providers", "next_run_at"):
            op.drop_column("cmdb_discovery_providers", "next_run_at")
        if _column_exists("cmdb_discovery_providers", "scan_interval_minutes"):
            op.drop_column("cmdb_discovery_providers", "scan_interval_minutes")

    if _table_exists("cmdb_items"):
        if _column_exists("cmdb_items", "baseline_attributes"):
            op.drop_column("cmdb_items", "baseline_attributes")
        if _column_exists("cmdb_items", "drift_detected_at"):
            op.drop_column("cmdb_items", "drift_detected_at")
        if _column_exists("cmdb_items", "config_hash"):
            op.drop_column("cmdb_items", "config_hash")
