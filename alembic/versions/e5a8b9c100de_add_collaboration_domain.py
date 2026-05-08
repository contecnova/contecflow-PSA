"""add_collaboration_domain (teams chat)

Revision ID: e5a8b9c100de
Revises: d4f1a2b3c901
Create Date: 2026-05-08 00:00:00.000000

Creates the collaboration domain tables for the Teams-like internal chat
described in chat_interno_teams_solucion_final.txt.

35 tables in total:
  - 29 tables from the document
  - 1 internal parent (`collaboration_conversations`) for FK consistency
  - 5 functional tables for pinned/saved/draft/notif rules/bot exec/slash logs
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e5a8b9c100de'
down_revision: Union[str, None] = 'd4f1a2b3c901'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _ts(server_default=True, **kw):
    """Helper to create a timezone-aware DateTime column with server now() default."""
    if server_default:
        return sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, **kw)
    return sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, **kw)


def upgrade() -> None:
    # Some Postgres deployments can use ENUM. We stick to String here so the
    # migration runs on both SQLite (dev) and Postgres (prod) without changes.

    # 1. Workspaces
    op.create_table(
        'collaboration_workspaces',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('icon_url', sa.String(500), nullable=True),
        sa.Column('primary_color', sa.String(20), nullable=True),
        sa.Column('settings', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    # 2. Teams
    op.create_table(
        'collaboration_teams',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('workspace_id', sa.String(36), sa.ForeignKey('collaboration_workspaces.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('slug', sa.String(140), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_private', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('created_by', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('workspace_id', 'slug', name='uq_team_slug_workspace'),
    )

    # 3. Team members
    op.create_table(
        'collaboration_team_members',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('team_id', sa.String(36), sa.ForeignKey('collaboration_teams.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('role', sa.String(20), nullable=False, server_default='member'),
        sa.Column('joined_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('team_id', 'user_id', name='uq_team_member'),
    )

    # internal: parent conversation
    op.create_table(
        'collaboration_conversations',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('kind', sa.String(20), nullable=False, index=True),
        sa.Column('workspace_id', sa.String(36), sa.ForeignKey('collaboration_workspaces.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('last_activity_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_message_id', sa.String(36), nullable=True),
        sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 4. Channels
    op.create_table(
        'collaboration_channels',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('workspace_id', sa.String(36), sa.ForeignKey('collaboration_workspaces.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('team_id', sa.String(36), sa.ForeignKey('collaboration_teams.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('conversation_id', sa.String(36), sa.ForeignKey('collaboration_conversations.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('slug', sa.String(140), nullable=False),
        sa.Column('topic', sa.String(500), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('channel_type', sa.String(20), nullable=False, server_default='public'),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('created_by', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('team_id', 'slug', name='uq_channel_slug_team'),
    )

    # 5. Channel members
    op.create_table(
        'collaboration_channel_members',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('channel_id', sa.String(36), sa.ForeignKey('collaboration_channels.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('role', sa.String(20), nullable=False, server_default='member'),
        sa.Column('last_read_message_id', sa.String(36), nullable=True),
        sa.Column('last_read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notify_level', sa.String(20), nullable=False, server_default='all'),
        sa.Column('is_starred', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('is_muted', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('joined_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('channel_id', 'user_id', name='uq_channel_member'),
    )

    # 6. Direct conversations
    op.create_table(
        'collaboration_direct_conversations',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('workspace_id', sa.String(36), sa.ForeignKey('collaboration_workspaces.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('conversation_id', sa.String(36), sa.ForeignKey('collaboration_conversations.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('user_a_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_b_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('client_user_a_id', sa.String(36), sa.ForeignKey('client_users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('client_user_b_id', sa.String(36), sa.ForeignKey('client_users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_direct_conv_pair', 'collaboration_direct_conversations', ['user_a_id', 'user_b_id'])

    # 7. Group conversations
    op.create_table(
        'collaboration_group_conversations',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('workspace_id', sa.String(36), sa.ForeignKey('collaboration_workspaces.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('conversation_id', sa.String(36), sa.ForeignKey('collaboration_conversations.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('title', sa.String(160), nullable=True),
        sa.Column('icon_url', sa.String(500), nullable=True),
        sa.Column('created_by', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    # 8. Conversation members
    op.create_table(
        'collaboration_conversation_members',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('conversation_id', sa.String(36), sa.ForeignKey('collaboration_conversations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('group_id', sa.String(36), sa.ForeignKey('collaboration_group_conversations.id', ondelete='CASCADE'), nullable=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True),
        sa.Column('client_user_id', sa.String(36), sa.ForeignKey('client_users.id', ondelete='CASCADE'), nullable=True),
        sa.Column('last_read_message_id', sa.String(36), nullable=True),
        sa.Column('last_read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_admin', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('is_muted', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('joined_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_conv_member_user', 'collaboration_conversation_members', ['conversation_id', 'user_id'])
    op.create_index('ix_conv_member_client', 'collaboration_conversation_members', ['conversation_id', 'client_user_id'])

    # 11. Threads
    op.create_table(
        'collaboration_threads',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('conversation_id', sa.String(36), sa.ForeignKey('collaboration_conversations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('root_message_id', sa.String(36), nullable=False),  # FK added later when messages exists
        sa.Column('title', sa.String(200), nullable=True),
        sa.Column('reply_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_reply_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_resolved', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 25. Bot apps (created early so messages can FK to it)
    op.create_table(
        'collaboration_bot_apps',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('workspace_id', sa.String(36), sa.ForeignKey('collaboration_workspaces.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('kind', sa.String(40), nullable=False),
        sa.Column('handle', sa.String(60), nullable=False),
        sa.Column('display_name', sa.String(120), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('avatar_url', sa.String(500), nullable=True),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('permissions', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('config', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('workspace_id', 'handle', name='uq_bot_handle_workspace'),
    )

    # 9. Messages
    op.create_table(
        'collaboration_messages',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('conversation_id', sa.String(36), sa.ForeignKey('collaboration_conversations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('thread_id', sa.String(36), sa.ForeignKey('collaboration_threads.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('parent_message_id', sa.String(36), nullable=True),  # self-FK; we don't enforce strict cycle FK on SQLite
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('client_user_id', sa.String(36), sa.ForeignKey('client_users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('bot_id', sa.String(36), sa.ForeignKey('collaboration_bot_apps.id', ondelete='SET NULL'), nullable=True),
        sa.Column('type', sa.String(20), nullable=False, server_default='text'),
        sa.Column('status', sa.String(20), nullable=False, server_default='visible'),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('body_html', sa.Text(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('has_attachments', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('is_pinned', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('is_redacted', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('linked_task_id', sa.String(36), sa.ForeignKey('tasks.id', ondelete='SET NULL'), nullable=True),
        sa.Column('linked_ticket_id', sa.String(36), sa.ForeignKey('sd_tickets.id', ondelete='SET NULL'), nullable=True),
        sa.Column('linked_deliverable_id', sa.String(36), nullable=True),
        sa.Column('linked_risk_id', sa.String(36), nullable=True),
        sa.Column('edited_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('scheduled_for', sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_msg_conv_sent', 'collaboration_messages', ['conversation_id', 'sent_at'])

    # 10. Message versions
    op.create_table(
        'collaboration_message_versions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('message_id', sa.String(36), sa.ForeignKey('collaboration_messages.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('body_html', sa.Text(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('edited_by_user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('edited_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 12. Reactions
    op.create_table(
        'collaboration_reactions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('message_id', sa.String(36), sa.ForeignKey('collaboration_messages.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True),
        sa.Column('client_user_id', sa.String(36), sa.ForeignKey('client_users.id', ondelete='CASCADE'), nullable=True),
        sa.Column('emoji', sa.String(60), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('message_id', 'user_id', 'emoji', name='uq_reaction_user'),
        sa.UniqueConstraint('message_id', 'client_user_id', 'emoji', name='uq_reaction_client'),
    )

    # 13. Mentions
    op.create_table(
        'collaboration_mentions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('message_id', sa.String(36), sa.ForeignKey('collaboration_messages.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('mentioned_user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True),
        sa.Column('mentioned_client_user_id', sa.String(36), sa.ForeignKey('client_users.id', ondelete='CASCADE'), nullable=True),
        sa.Column('mentioned_team_id', sa.String(36), sa.ForeignKey('collaboration_teams.id', ondelete='CASCADE'), nullable=True),
        sa.Column('mentioned_channel_id', sa.String(36), sa.ForeignKey('collaboration_channels.id', ondelete='CASCADE'), nullable=True),
        sa.Column('is_everyone', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 14. Reads
    op.create_table(
        'collaboration_reads',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('conversation_id', sa.String(36), sa.ForeignKey('collaboration_conversations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True),
        sa.Column('client_user_id', sa.String(36), sa.ForeignKey('client_users.id', ondelete='CASCADE'), nullable=True),
        sa.Column('last_message_id', sa.String(36), nullable=True),
        sa.Column('last_read_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('conversation_id', 'user_id', name='uq_read_user'),
        sa.UniqueConstraint('conversation_id', 'client_user_id', name='uq_read_client'),
    )

    # 15. Attachments
    op.create_table(
        'collaboration_attachments',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('message_id', sa.String(36), sa.ForeignKey('collaboration_messages.id', ondelete='CASCADE'), nullable=True),
        sa.Column('conversation_id', sa.String(36), sa.ForeignKey('collaboration_conversations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('uploaded_by_user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('uploaded_by_client_id', sa.String(36), sa.ForeignKey('client_users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('name', sa.String(500), nullable=False),
        sa.Column('mime_type', sa.String(160), nullable=True),
        sa.Column('size_bytes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('storage_provider', sa.String(40), nullable=False, server_default='local'),
        sa.Column('storage_key', sa.String(800), nullable=False),
        sa.Column('sha256', sa.String(64), nullable=True, index=True),
        sa.Column('av_status', sa.String(40), nullable=False, server_default='pending'),
        sa.Column('av_scanned_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('dlp_status', sa.String(40), nullable=False, server_default='pending'),
        sa.Column('dlp_findings', sa.JSON(), nullable=True),
        sa.Column('is_quarantined', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('preview_key', sa.String(800), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 16. Attachment versions
    op.create_table(
        'collaboration_attachment_versions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('attachment_id', sa.String(36), sa.ForeignKey('collaboration_attachments.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('storage_key', sa.String(800), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('sha256', sa.String(64), nullable=True),
        sa.Column('uploaded_by_user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('attachment_id', 'version', name='uq_attachment_version'),
    )

    # 17. Calls
    op.create_table(
        'collaboration_calls',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('conversation_id', sa.String(36), sa.ForeignKey('collaboration_conversations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('initiated_by', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('kind', sa.String(20), nullable=False, server_default='video'),
        sa.Column('status', sa.String(20), nullable=False, server_default='ringing'),
        sa.Column('livekit_room', sa.String(160), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_seconds', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_recorded', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('has_transcript', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('has_summary', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('metadata_json', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 18. Call participants
    op.create_table(
        'collaboration_call_participants',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('call_id', sa.String(36), sa.ForeignKey('collaboration_calls.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('client_user_id', sa.String(36), sa.ForeignKey('client_users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('joined_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('left_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('role', sa.String(20), nullable=False, server_default='participant'),
        sa.Column('is_speaker', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('network_quality', sa.String(20), nullable=True),
    )

    # 19. Recordings
    op.create_table(
        'collaboration_recordings',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('call_id', sa.String(36), sa.ForeignKey('collaboration_calls.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('storage_provider', sa.String(40), nullable=False, server_default='local'),
        sa.Column('storage_key', sa.String(800), nullable=False),
        sa.Column('duration_seconds', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('size_bytes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(40), nullable=False, server_default='processing'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 20. Transcripts
    op.create_table(
        'collaboration_transcripts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('call_id', sa.String(36), sa.ForeignKey('collaboration_calls.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('language', sa.String(20), nullable=False, server_default='es'),
        sa.Column('text', sa.Text(), nullable=False, server_default=''),
        sa.Column('segments_json', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('actions_json', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 21. Notifications
    op.create_table(
        'collaboration_notifications',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True, index=True),
        sa.Column('client_user_id', sa.String(36), sa.ForeignKey('client_users.id', ondelete='CASCADE'), nullable=True),
        sa.Column('kind', sa.String(40), nullable=False, server_default='message'),
        sa.Column('conversation_id', sa.String(36), sa.ForeignKey('collaboration_conversations.id', ondelete='CASCADE'), nullable=True, index=True),
        sa.Column('message_id', sa.String(36), sa.ForeignKey('collaboration_messages.id', ondelete='CASCADE'), nullable=True),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default=sa.text('0'), index=True),
        sa.Column('delivered_email', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('delivered_push', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    )

    # 22. Presence
    op.create_table(
        'collaboration_presence_states',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True, unique=True),
        sa.Column('client_user_id', sa.String(36), sa.ForeignKey('client_users.id', ondelete='CASCADE'), nullable=True, unique=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='offline'),
        sa.Column('custom_message', sa.String(200), nullable=True),
        sa.Column('is_in_call', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 23. Integrations
    op.create_table(
        'collaboration_integrations',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('workspace_id', sa.String(36), sa.ForeignKey('collaboration_workspaces.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('kind', sa.String(40), nullable=False),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('config', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('secret_ref', sa.String(160), nullable=True),
        sa.Column('created_by', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    # 24. Webhooks
    op.create_table(
        'collaboration_webhooks',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('workspace_id', sa.String(36), sa.ForeignKey('collaboration_workspaces.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('direction', sa.String(20), nullable=False),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('url', sa.String(800), nullable=True),
        sa.Column('secret_token', sa.String(160), nullable=False),
        sa.Column('target_channel_id', sa.String(36), sa.ForeignKey('collaboration_channels.id', ondelete='SET NULL'), nullable=True),
        sa.Column('events', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('last_called_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failure_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 26. Moderation cases
    op.create_table(
        'collaboration_moderation_cases',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('message_id', sa.String(36), sa.ForeignKey('collaboration_messages.id', ondelete='CASCADE'), nullable=True),
        sa.Column('attachment_id', sa.String(36), sa.ForeignKey('collaboration_attachments.id', ondelete='CASCADE'), nullable=True),
        sa.Column('reason', sa.String(40), nullable=False),
        sa.Column('findings', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('verdict', sa.String(40), nullable=False, server_default='pending'),
        sa.Column('reviewer_user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 27. Retention policies
    op.create_table(
        'collaboration_retention_policies',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('workspace_id', sa.String(36), sa.ForeignKey('collaboration_workspaces.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('scope', sa.String(40), nullable=False, server_default='workspace'),
        sa.Column('target_id', sa.String(36), nullable=True),
        sa.Column('retention_months', sa.Integer(), nullable=False, server_default='24'),
        sa.Column('apply_to', sa.String(40), nullable=False, server_default='all'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 28. Legal holds
    op.create_table(
        'collaboration_legal_holds',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('case_reference', sa.String(120), nullable=False, index=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('custodian_user_ids', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('custodian_client_ids', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('channel_ids', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_by', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
    )

    # 29. Audit events
    op.create_table(
        'collaboration_audit_events',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('actor_user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('actor_client_id', sa.String(36), sa.ForeignKey('client_users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('action', sa.String(80), nullable=False, index=True),
        sa.Column('entity_type', sa.String(60), nullable=False, index=True),
        sa.Column('entity_id', sa.String(36), nullable=True, index=True),
        sa.Column('payload', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('ip_address', sa.String(60), nullable=True),
        sa.Column('user_agent', sa.String(500), nullable=True),
        sa.Column('integrity_hash', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
    )

    # Functional extras
    op.create_table(
        'collaboration_pinned_messages',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('conversation_id', sa.String(36), sa.ForeignKey('collaboration_conversations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('message_id', sa.String(36), sa.ForeignKey('collaboration_messages.id', ondelete='CASCADE'), nullable=False),
        sa.Column('pinned_by', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('pinned_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('conversation_id', 'message_id', name='uq_pin_message'),
    )
    op.create_table(
        'collaboration_saved_messages',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('message_id', sa.String(36), sa.ForeignKey('collaboration_messages.id', ondelete='CASCADE'), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('saved_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('user_id', 'message_id', name='uq_saved_per_user'),
    )
    op.create_table(
        'collaboration_drafts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('conversation_id', sa.String(36), sa.ForeignKey('collaboration_conversations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('parent_message_id', sa.String(36), sa.ForeignKey('collaboration_messages.id', ondelete='SET NULL'), nullable=True),
        sa.Column('body', sa.Text(), nullable=False, server_default=''),
        sa.Column('metadata_json', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('user_id', 'conversation_id', 'parent_message_id', name='uq_draft'),
    )
    op.create_table(
        'collaboration_notification_rules',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('scope', sa.String(20), nullable=False, server_default='global'),
        sa.Column('target_id', sa.String(36), nullable=True),
        sa.Column('notify_messages', sa.String(20), nullable=False, server_default='all'),
        sa.Column('desktop_push', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('email_digest', sa.String(20), nullable=False, server_default='weekly'),
        sa.Column('do_not_disturb_from', sa.String(8), nullable=True),
        sa.Column('do_not_disturb_to', sa.String(8), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        'collaboration_bot_executions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('bot_id', sa.String(36), sa.ForeignKey('collaboration_bot_apps.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('conversation_id', sa.String(36), sa.ForeignKey('collaboration_conversations.id', ondelete='SET NULL'), nullable=True),
        sa.Column('triggered_by_user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('command', sa.String(80), nullable=True),
        sa.Column('input_payload', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('output_payload', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('status', sa.String(40), nullable=False, server_default='ok'),
        sa.Column('duration_ms', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
    )
    op.create_table(
        'collaboration_slash_command_logs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('conversation_id', sa.String(36), sa.ForeignKey('collaboration_conversations.id', ondelete='SET NULL'), nullable=True),
        sa.Column('command', sa.String(60), nullable=False, index=True),
        sa.Column('args', sa.Text(), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('response', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    for tname in [
        'collaboration_slash_command_logs',
        'collaboration_bot_executions',
        'collaboration_notification_rules',
        'collaboration_drafts',
        'collaboration_saved_messages',
        'collaboration_pinned_messages',
        'collaboration_audit_events',
        'collaboration_legal_holds',
        'collaboration_retention_policies',
        'collaboration_moderation_cases',
        'collaboration_webhooks',
        'collaboration_integrations',
        'collaboration_presence_states',
        'collaboration_notifications',
        'collaboration_transcripts',
        'collaboration_recordings',
        'collaboration_call_participants',
        'collaboration_calls',
        'collaboration_attachment_versions',
        'collaboration_attachments',
        'collaboration_reads',
        'collaboration_mentions',
        'collaboration_reactions',
        'collaboration_message_versions',
        'collaboration_messages',
        'collaboration_bot_apps',
        'collaboration_threads',
        'collaboration_conversation_members',
        'collaboration_group_conversations',
        'collaboration_direct_conversations',
        'collaboration_channel_members',
        'collaboration_channels',
        'collaboration_conversations',
        'collaboration_team_members',
        'collaboration_teams',
        'collaboration_workspaces',
    ]:
        op.drop_table(tname)
