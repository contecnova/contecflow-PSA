"""v23.10.12 — Fase 2 ITSM Intelligence

Revision ID: 032_itsm_phase2
Revises: 031_itsm_phase1
Create Date: 2026-04-01

Adds:
  - sd_tickets: predicted_severity, predicted_resolution_minutes,
                escalation_risk_score, prediction_generated_at
  - sd_change_requests: auto_risk_score, impact_analysis_json,
                        suggested_window_json
  - sd_assets: depreciation_type, depreciation_rate,
               next_maintenance_date, maintenance_contract
  - NEW TABLE: sd_autonomous_playbooks
  - NEW TABLE: sd_autonomous_playbook_executions
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "032_itsm_phase2"
down_revision = "031_itsm_phase1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── sd_tickets: predictive intelligence columns ───────────────────────────
    with op.batch_alter_table("sd_tickets", schema=None) as batch_op:
        batch_op.add_column(sa.Column("predicted_severity", sa.String(20), nullable=True))
        batch_op.add_column(sa.Column("predicted_resolution_minutes", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("escalation_risk_score", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("prediction_generated_at", sa.DateTime(timezone=True), nullable=True))

    # ── sd_change_requests: impact analysis columns ───────────────────────────
    with op.batch_alter_table("sd_change_requests", schema=None) as batch_op:
        batch_op.add_column(sa.Column("auto_risk_score", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("impact_analysis_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("suggested_window_json", sa.Text(), nullable=True))

    # ── sd_assets: lifecycle columns ──────────────────────────────────────────
    with op.batch_alter_table("sd_assets", schema=None) as batch_op:
        batch_op.add_column(sa.Column("depreciation_type", sa.String(20), nullable=True))
        batch_op.add_column(sa.Column("depreciation_rate", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("next_maintenance_date", sa.String(10), nullable=True))
        batch_op.add_column(sa.Column("maintenance_contract", sa.String(255), nullable=True))

    # ── NEW TABLE: sd_autonomous_playbooks ────────────────────────────────────
    op.create_table(
        "sd_autonomous_playbooks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("playbook_type", sa.String(50), nullable=False, index=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("steps_json", sa.Text(), nullable=True),
        sa.Column("conditions_json", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("success_count", sa.Integer(), default=0),
        sa.Column("failure_count", sa.Integer(), default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── NEW TABLE: sd_autonomous_playbook_executions ──────────────────────────
    op.create_table(
        "sd_autonomous_playbook_executions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("ticket_id", sa.String(36),
                  sa.ForeignKey("sd_tickets.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("playbook_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), default="success"),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("triggered_by", sa.String(20), default="celery"),
    )


def downgrade() -> None:
    op.drop_table("sd_autonomous_playbook_executions")
    op.drop_table("sd_autonomous_playbooks")

    with op.batch_alter_table("sd_assets", schema=None) as batch_op:
        batch_op.drop_column("maintenance_contract")
        batch_op.drop_column("next_maintenance_date")
        batch_op.drop_column("depreciation_rate")
        batch_op.drop_column("depreciation_type")

    with op.batch_alter_table("sd_change_requests", schema=None) as batch_op:
        batch_op.drop_column("suggested_window_json")
        batch_op.drop_column("impact_analysis_json")
        batch_op.drop_column("auto_risk_score")

    with op.batch_alter_table("sd_tickets", schema=None) as batch_op:
        batch_op.drop_column("prediction_generated_at")
        batch_op.drop_column("escalation_risk_score")
        batch_op.drop_column("predicted_resolution_minutes")
        batch_op.drop_column("predicted_severity")
