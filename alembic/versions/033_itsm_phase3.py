"""Fase 3 ITSM Scale — Multi-provider CMDB, BI Analytics, Smart Catalog, Governance.

Revision ID: 033_itsm_phase3
Revises: 032_itsm_phase2
Create Date: 2026-04-01
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "033_itsm_phase3"
down_revision = "032_itsm_phase2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Sprint 21-22: Smart Catalog — popularity score ────────────────────────
    with op.batch_alter_table("sd_service_items") as batch_op:
        batch_op.add_column(sa.Column("popularity_score", sa.Float(), nullable=True))

    # ── Sprint 19-20: BI Analytics — metric snapshots ─────────────────────────
    op.create_table(
        "sd_itsm_metric_snapshots",
        sa.Column("id",                  sa.String(36), primary_key=True),
        sa.Column("snapshot_at",         sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_hours",        sa.Integer(), default=24),
        sa.Column("tickets_total",       sa.Integer(), default=0),
        sa.Column("tickets_open",        sa.Integer(), default=0),
        sa.Column("tickets_resolved",    sa.Integer(), default=0),
        sa.Column("sla_compliance_pct",  sa.Float(), nullable=True),
        sa.Column("mttr_minutes",        sa.Float(), nullable=True),
        sa.Column("fcr_pct",             sa.Float(), nullable=True),
        sa.Column("avg_csat",            sa.Float(), nullable=True),
        sa.Column("breached_sla",        sa.Integer(), default=0),
    )
    op.create_index("ix_sd_itsm_metric_snapshots_snapshot_at", "sd_itsm_metric_snapshots", ["snapshot_at"])

    # ── Sprint 23-24: Governance — compliance reports ─────────────────────────
    op.create_table(
        "sd_compliance_reports",
        sa.Column("id",            sa.String(36), primary_key=True),
        sa.Column("generated_at",  sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_days",   sa.Integer(), default=30),
        sa.Column("overall_score", sa.Integer(), default=0),
        sa.Column("cmm_level",     sa.Integer(), default=1),
        sa.Column("report_json",   sa.Text(), nullable=True),
    )
    op.create_index("ix_sd_compliance_reports_generated_at", "sd_compliance_reports", ["generated_at"])


def downgrade() -> None:
    op.drop_index("ix_sd_compliance_reports_generated_at", table_name="sd_compliance_reports")
    op.drop_table("sd_compliance_reports")
    op.drop_index("ix_sd_itsm_metric_snapshots_snapshot_at", table_name="sd_itsm_metric_snapshots")
    op.drop_table("sd_itsm_metric_snapshots")
    with op.batch_alter_table("sd_service_items") as batch_op:
        batch_op.drop_column("popularity_score")
