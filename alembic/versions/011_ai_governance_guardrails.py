"""
Migration: AI Governance — Guardrail Policies & Audit Logs

Creates tables for PII-aware guardrail policies and per-evaluation audit records.

Revision ID: 011_ai_governance_guardrails
Revises: 010_security_observability
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "011_ai_governance_guardrails"
down_revision = "010_security_observability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_guardrail_policies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("applies_to_modules", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("applies_to_roles", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("scope", sa.String(10), nullable=False, server_default="both"),
        sa.Column("action", sa.String(10), nullable=False, server_default="log"),
        sa.Column("pii_entity_types", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("redact_strategy", sa.String(10), nullable=False, server_default="mask"),
        sa.Column("forbidden_keywords", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("max_prompt_tokens", sa.Integer, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index(
        "idx_guardrail_org_active",
        "ai_guardrail_policies",
        ["org_id", "is_active"],
    )

    op.create_table(
        "ai_guardrail_audit_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("module", sa.String(40), nullable=False),
        sa.Column("scope", sa.String(10), nullable=False),
        sa.Column("policy_id", sa.String(36), nullable=True),
        sa.Column("request_id", sa.String(36), nullable=True),
        sa.Column("action_taken", sa.String(10), nullable=False),
        sa.Column("pii_types_found", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("was_blocked", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("blocked_reason", sa.Text, nullable=True),
        sa.Column("original_length", sa.Integer, nullable=True),
        sa.Column("warnings", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index(
        "idx_guardrail_audit_org_ts",
        "ai_guardrail_audit_logs",
        ["org_id", "evaluated_at"],
    )
    op.create_index(
        "idx_guardrail_audit_blocked",
        "ai_guardrail_audit_logs",
        ["org_id", "was_blocked"],
    )
    op.create_index(
        "idx_guardrail_audit_user",
        "ai_guardrail_audit_logs",
        ["user_id", "evaluated_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_guardrail_audit_user", table_name="ai_guardrail_audit_logs")
    op.drop_index("idx_guardrail_audit_blocked", table_name="ai_guardrail_audit_logs")
    op.drop_index("idx_guardrail_audit_org_ts", table_name="ai_guardrail_audit_logs")
    op.drop_table("ai_guardrail_audit_logs")
    op.drop_index("idx_guardrail_org_active", table_name="ai_guardrail_policies")
    op.drop_table("ai_guardrail_policies")
