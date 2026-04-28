"""Merge heads + portal_conversations tables

Merges the c4e5f2a83d17 (scheduled_report_bi_fields) branch with the
039_itsm_problem_kedb branch, and creates all portal_conversation* tables.

Revision ID: d2a3b8e7f041
Revises: c4e5f2a83d17, 039_itsm_problem_kedb
Create Date: 2026-04-28

"""
from alembic import op
import sqlalchemy as sa

revision = 'd2a3b8e7f041'
down_revision = ('c4e5f2a83d17', '039_itsm_problem_kedb')
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── portal_conversation_policies ─────────────────────────────────────────
    op.create_table(
        "portal_conversation_policies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("topic_type", sa.String(50), nullable=False, index=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("requires_client_message_approval", sa.Boolean(), nullable=False, default=False),
        sa.Column("requires_team_message_approval", sa.Boolean(), nullable=False, default=False),
        sa.Column("redact_sensitive_content", sa.Boolean(), nullable=False, default=True),
        sa.Column("allow_legacy_federation", sa.Boolean(), nullable=False, default=True),
        sa.Column("assignment_mode", sa.String(30), nullable=False, default="manual"),
        sa.Column("default_group_id", sa.String(36), sa.ForeignKey("sd_agent_groups.id"), nullable=True),
        sa.Column("default_role_key", sa.String(50), nullable=True),
        sa.Column("first_response_hours", sa.Integer(), nullable=False, default=8),
        sa.Column("escalation_hours", sa.Integer(), nullable=False, default=24),
        sa.Column("approval_role_key", sa.String(50), nullable=True),
        sa.Column("approval_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("sensitive_keywords", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── portal_conversations ──────────────────────────────────────────────────
    op.create_table(
        "portal_conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("client_org_id", sa.String(36), sa.ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("topic_type", sa.String(50), nullable=False, default="general"),
        sa.Column("source", sa.String(30), nullable=False, default="native", index=True),
        sa.Column("legacy_thread_id", sa.String(36), nullable=True, index=True),
        sa.Column("source_resource_type", sa.String(50), nullable=True),
        sa.Column("source_resource_id", sa.String(36), nullable=True, index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, default="active", index=True),
        sa.Column("assignment_mode", sa.String(30), nullable=False, default="manual"),
        sa.Column("visibility_policy_key", sa.String(100), nullable=True),
        sa.Column("sla_policy_id", sa.String(36), sa.ForeignKey("sd_sla_policies.id"), nullable=True),
        sa.Column("policy_id", sa.String(36), sa.ForeignKey("portal_conversation_policies.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("assigned_group_id", sa.String(36), sa.ForeignKey("sd_agent_groups.id"), nullable=True),
        sa.Column("assigned_role_key", sa.String(50), nullable=True),
        sa.Column("first_response_due_at", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column("first_response_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_by_client_id", sa.String(36), sa.ForeignKey("client_users.id"), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── portal_conversation_participants ──────────────────────────────────────
    op.create_table(
        "portal_conversation_participants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("portal_conversations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("participant_type", sa.String(30), nullable=False, index=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("client_user_id", sa.String(36), sa.ForeignKey("client_users.id"), nullable=True, index=True),
        sa.Column("client_org_id", sa.String(36), sa.ForeignKey("clients.id"), nullable=True, index=True),
        sa.Column("role_key", sa.String(50), nullable=True),
        sa.Column("role_in_conversation", sa.String(30), nullable=False, default="agent"),
        sa.Column("can_read", sa.Boolean(), nullable=False, default=True),
        sa.Column("can_write", sa.Boolean(), nullable=False, default=True),
        sa.Column("can_invite", sa.Boolean(), nullable=False, default=False),
        sa.Column("can_close", sa.Boolean(), nullable=False, default=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("added_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    )

    # ── portal_conversation_messages ──────────────────────────────────────────
    op.create_table(
        "portal_conversation_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("portal_conversations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("parent_message_id", sa.String(36), sa.ForeignKey("portal_conversation_messages.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("sender_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("sender_client_id", sa.String(36), sa.ForeignKey("client_users.id"), nullable=True, index=True),
        sa.Column("legacy_message_id", sa.String(36), sa.ForeignKey("client_messages.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("approval_request_id", sa.String(36), sa.ForeignKey("approval_requests.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("message_type", sa.String(30), nullable=False, default="text"),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("raw_body", sa.Text(), nullable=True),
        sa.Column("moderation_notes", sa.Text(), nullable=True),
        sa.Column("is_internal_note", sa.Boolean(), nullable=False, default=False),
        sa.Column("is_redacted", sa.Boolean(), nullable=False, default=False),
        sa.Column("classification", sa.String(30), nullable=False, default="public_client"),
        sa.Column("grc_status", sa.String(30), nullable=False, default="allowed", index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── portal_conversation_audits ────────────────────────────────────────────
    op.create_table(
        "portal_conversation_audits",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("portal_conversations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("actor_client_id", sa.String(36), sa.ForeignKey("client_users.id"), nullable=True, index=True),
        sa.Column("action_type", sa.String(100), nullable=False, index=True),
        sa.Column("target_type", sa.String(50), nullable=True),
        sa.Column("target_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, default="success"),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("portal_conversation_audits")
    op.drop_table("portal_conversation_messages")
    op.drop_table("portal_conversation_participants")
    op.drop_table("portal_conversations")
    op.drop_table("portal_conversation_policies")
