"""014 — ai_providers and ai_usage_logs tables

Adds the multi-provider AI configuration tables that were defined in
the model layer but never included in a migration.

Revision ID: 014_ai_providers
Revises: 013_sem_config_threshold_calibration
Create Date: 2026-04-11
"""

import sqlalchemy as sa
from alembic import op

revision = "014_ai_providers"
down_revision = "013_sem_config_threshold_calibration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_providers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column(
            "provider",
            sa.Enum(
                "anthropic", "openai", "gemini", "deepseek",
                "ollama", "groq", "mistral", "azure",
                name="aiprovidertype",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("active", "inactive", "error", name="aiproviderstatus"),
            nullable=False,
            server_default="active",
        ),
        sa.Column("api_key", sa.String(500), nullable=True),
        sa.Column("api_base_url", sa.String(500), nullable=True),
        sa.Column("api_version", sa.String(50), nullable=True),
        sa.Column("default_model", sa.String(100), nullable=True),
        sa.Column("available_models", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("max_tokens", sa.Integer(), nullable=False, server_default="2000"),
        sa.Column("temperature", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("total_requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens_in", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens_out", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )

    op.create_table(
        "ai_usage_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider_id", sa.String(36), nullable=True),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("module", sa.String(50), nullable=False, index=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("prompt_preview", sa.Text(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("error_msg", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"], ["ai_providers.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )


def downgrade() -> None:
    op.drop_table("ai_usage_logs")
    op.drop_table("ai_providers")
