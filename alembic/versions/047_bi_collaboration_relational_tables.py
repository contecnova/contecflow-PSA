"""047 – BI Collaboration relational tables

Create relational persistence for BI collaboration features previously stored
in AppSetting JSON blobs:
- dashboard_comments
- dashboard_versions
- dashboard_shares
- dashboard_notifications

Also performs best-effort backfill from these legacy keys:
- bi.phase1.comments
- bi.collab.versions.<dashboard_key>
- bi.collab.shares.<dashboard_key>

Revision ID: 047_bi_collaboration_relational_tables
Revises: 046_cmdb_agent_registrations
Create Date: 2026-04-29
"""
from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from alembic import op

revision = "047_bi_collaboration_relational_tables"
down_revision = "046_cmdb_agent_registrations"
branch_labels = None
depends_on = None

COMMENTS_KEY = "bi.phase1.comments"
VERSIONS_KEY_PREFIX = "bi.collab.versions."
SHARES_KEY_PREFIX = "bi.collab.shares."


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return table_name in insp.get_table_names()


def _create_tables() -> None:
    if not _table_exists("dashboard_comments"):
        op.create_table(
            "dashboard_comments",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True),
            sa.Column("dashboard_key", sa.String(120), nullable=False),
            sa.Column("widget_id", sa.String(120), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("author_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("author_name", sa.String(255), nullable=True),
            sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("resolved_by", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_dashboard_comments_org", "dashboard_comments", ["organization_id"])
        op.create_index("ix_dashboard_comments_dashboard", "dashboard_comments", ["dashboard_key"])
        op.create_index("ix_dashboard_comments_widget", "dashboard_comments", ["widget_id"])

    if not _table_exists("dashboard_versions"):
        op.create_table(
            "dashboard_versions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True),
            sa.Column("dashboard_key", sa.String(120), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("config", sa.Text(), nullable=False),
            sa.Column("change_log", sa.String(500), nullable=True),
            sa.Column("created_by_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_by_name", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("organization_id", "dashboard_key", "version", name="uq_dashboard_version_org_key_ver"),
        )
        op.create_index("ix_dashboard_versions_org", "dashboard_versions", ["organization_id"])
        op.create_index("ix_dashboard_versions_dashboard", "dashboard_versions", ["dashboard_key"])

    if not _table_exists("dashboard_shares"):
        op.create_table(
            "dashboard_shares",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True),
            sa.Column("dashboard_key", sa.String(120), nullable=False),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_name", sa.String(255), nullable=True),
            sa.Column("permission", sa.String(20), nullable=False),
            sa.Column("shared_by_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("shared_by_name", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("organization_id", "dashboard_key", "user_id", name="uq_dashboard_share_org_key_user"),
        )
        op.create_index("ix_dashboard_shares_org", "dashboard_shares", ["organization_id"])
        op.create_index("ix_dashboard_shares_dashboard", "dashboard_shares", ["dashboard_key"])
        op.create_index("ix_dashboard_shares_user", "dashboard_shares", ["user_id"])

    if not _table_exists("dashboard_notifications"):
        op.create_table(
            "dashboard_notifications",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True),
            sa.Column("dashboard_key", sa.String(120), nullable=False),
            sa.Column("event_type", sa.String(50), nullable=False),
            sa.Column("recipient_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
            sa.Column("payload_json", sa.Text(), nullable=False),
            sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_dashboard_notifications_org", "dashboard_notifications", ["organization_id"])
        op.create_index("ix_dashboard_notifications_dashboard", "dashboard_notifications", ["dashboard_key"])
        op.create_index("ix_dashboard_notifications_recipient", "dashboard_notifications", ["recipient_user_id"])


def _backfill_from_app_settings() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT key, organization_id, value
            FROM app_settings
            WHERE key = :comments_key
               OR key LIKE :versions_prefix
               OR key LIKE :shares_prefix
            """
        ),
        {
            "comments_key": COMMENTS_KEY,
            "versions_prefix": f"{VERSIONS_KEY_PREFIX}%",
            "shares_prefix": f"{SHARES_KEY_PREFIX}%",
        },
    ).mappings().all()

    for row in rows:
        key = row.get("key")
        org_id = row.get("organization_id")
        raw = row.get("value")
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except Exception:
            continue

        if key == COMMENTS_KEY and isinstance(payload, list):
            for item in payload:
                if not isinstance(item, dict):
                    continue
                bind.execute(
                    sa.text(
                        """
                        INSERT INTO dashboard_comments
                            (id, organization_id, dashboard_key, widget_id, message, author_id, author_name,
                             resolved, resolved_at, resolved_by, created_at)
                        VALUES
                            (:id, :organization_id, :dashboard_key, :widget_id, :message, :author_id, :author_name,
                             :resolved, :resolved_at, :resolved_by, :created_at)
                        ON CONFLICT (id) DO NOTHING
                        """
                    ),
                    {
                        "id": item.get("id") or str(uuid.uuid4()),
                        "organization_id": org_id,
                        "dashboard_key": item.get("dashboard_key") or "unknown",
                        "widget_id": item.get("widget_id") or "unknown",
                        "message": item.get("message") or "",
                        "author_id": item.get("author_id"),
                        "author_name": item.get("author_name"),
                        "resolved": bool(item.get("resolved", False)),
                        "resolved_at": item.get("resolved_at"),
                        "resolved_by": item.get("resolved_by"),
                        "created_at": item.get("created_at"),
                    },
                )

        elif key.startswith(VERSIONS_KEY_PREFIX) and isinstance(payload, list):
            dashboard_key = key[len(VERSIONS_KEY_PREFIX):] or "unknown"
            for item in payload:
                if not isinstance(item, dict):
                    continue
                bind.execute(
                    sa.text(
                        """
                        INSERT INTO dashboard_versions
                            (id, organization_id, dashboard_key, version, config, change_log,
                             created_by_id, created_by_name, created_at)
                        VALUES
                            (:id, :organization_id, :dashboard_key, :version, :config, :change_log,
                             :created_by_id, :created_by_name, :created_at)
                        ON CONFLICT (id) DO NOTHING
                        """
                    ),
                    {
                        "id": item.get("id") or str(uuid.uuid4()),
                        "organization_id": org_id,
                        "dashboard_key": item.get("dashboard_key") or dashboard_key,
                        "version": int(item.get("version") or 1),
                        "config": json.dumps(item.get("config") or {}, ensure_ascii=False, separators=(",", ":")),
                        "change_log": item.get("change_log"),
                        "created_by_id": item.get("created_by_id"),
                        "created_by_name": item.get("created_by_name"),
                        "created_at": item.get("created_at"),
                    },
                )

        elif key.startswith(SHARES_KEY_PREFIX) and isinstance(payload, list):
            dashboard_key = key[len(SHARES_KEY_PREFIX):] or "unknown"
            for item in payload:
                if not isinstance(item, dict):
                    continue
                user_id = item.get("user_id")
                if not user_id:
                    continue
                bind.execute(
                    sa.text(
                        """
                        INSERT INTO dashboard_shares
                            (id, organization_id, dashboard_key, user_id, user_name, permission,
                             shared_by_id, shared_by_name, created_at, updated_at)
                        VALUES
                            (:id, :organization_id, :dashboard_key, :user_id, :user_name, :permission,
                             :shared_by_id, :shared_by_name, :created_at, :updated_at)
                        ON CONFLICT (organization_id, dashboard_key, user_id) DO NOTHING
                        """
                    ),
                    {
                        "id": item.get("id") or str(uuid.uuid4()),
                        "organization_id": org_id,
                        "dashboard_key": item.get("dashboard_key") or dashboard_key,
                        "user_id": user_id,
                        "user_name": item.get("user_name"),
                        "permission": item.get("permission") or "view",
                        "shared_by_id": item.get("shared_by_id"),
                        "shared_by_name": item.get("shared_by_name"),
                        "created_at": item.get("created_at"),
                        "updated_at": item.get("updated_at") or item.get("created_at"),
                    },
                )


def upgrade() -> None:
    _create_tables()
    _backfill_from_app_settings()


def downgrade() -> None:
    if _table_exists("dashboard_notifications"):
        op.drop_table("dashboard_notifications")
    if _table_exists("dashboard_shares"):
        op.drop_table("dashboard_shares")
    if _table_exists("dashboard_versions"):
        op.drop_table("dashboard_versions")
    if _table_exists("dashboard_comments"):
        op.drop_table("dashboard_comments")
