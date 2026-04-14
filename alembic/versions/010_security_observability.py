"""
Migration: Security Observability — SOC-ready event log, detections, incidents, anomalies

Revision ID: 010_security_observability
Revises: 009_abac_fine_grained_auth
Create Date: 2026-04-08 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = '010_security_observability'
down_revision = '009_abac_fine_grained_auth'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── security_incidents (no external FKs, created first) ──────────────────
    op.create_table(
        "security_incidents",
        sa.Column("id",              sa.String(36),  primary_key=True),
        sa.Column("org_id",          sa.String(36),  sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("title",           sa.String(256), nullable=False),
        sa.Column("description",     sa.Text,        nullable=True),
        sa.Column("severity",        sa.String(16),  nullable=False),
        sa.Column("status",          sa.String(32),  nullable=False, server_default="open"),
        sa.Column("mttd_seconds",    sa.Float,       nullable=True),
        sa.Column("mttr_seconds",    sa.Float,       nullable=True),
        sa.Column("started_at",      sa.DateTime,    nullable=True),
        sa.Column("detected_at",     sa.DateTime,    nullable=True),
        sa.Column("contained_at",    sa.DateTime,    nullable=True),
        sa.Column("resolved_at",     sa.DateTime,    nullable=True),
        sa.Column("lead_analyst",    sa.String(36),  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("playbook_ref",    sa.String(256), nullable=True),
        sa.Column("tags",            sa.JSON,        nullable=True),
        sa.Column("timeline_notes",  sa.JSON,        nullable=True),
        sa.Column("root_cause",      sa.Text,        nullable=True),
        sa.Column("remediation_note",sa.Text,        nullable=True),
        sa.Column("lessons_learned", sa.Text,        nullable=True),
        sa.Column("created_at",      sa.DateTime,    nullable=True),
        sa.Column("updated_at",      sa.DateTime,    nullable=True),
    )
    op.create_index("idx_inc_org_status",   "security_incidents", ["org_id", "status"])
    op.create_index("idx_inc_org_severity", "security_incidents", ["org_id", "severity"])
    op.create_index("idx_inc_started",      "security_incidents", ["started_at"])

    # ── security_detections ───────────────────────────────────────────────────
    op.create_table(
        "security_detections",
        sa.Column("id",                    sa.String(36),  primary_key=True),
        sa.Column("org_id",                sa.String(36),  sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("title",                 sa.String(256), nullable=False),
        sa.Column("description",           sa.Text,        nullable=True),
        sa.Column("severity",              sa.String(16),  nullable=False),
        sa.Column("category",              sa.String(32),  nullable=False),
        sa.Column("kill_chain",            sa.String(64),  nullable=True),
        sa.Column("mitre_id",              sa.String(32),  nullable=True),
        sa.Column("mitre_tactic",          sa.String(64),  nullable=True),
        sa.Column("user_id",               sa.String(36),  sa.ForeignKey("users.id"),  nullable=True),
        sa.Column("ip_address",            sa.String(64),  nullable=True),
        sa.Column("country",               sa.String(64),  nullable=True),
        sa.Column("event_count",           sa.Integer,     server_default="1"),
        sa.Column("raw_data",              sa.JSON,        nullable=True),
        sa.Column("evidence",              sa.JSON,        nullable=True),
        sa.Column("first_seen_at",         sa.DateTime,    nullable=True),
        sa.Column("detected_at",           sa.DateTime,    nullable=True),
        sa.Column("status",                sa.String(32),  nullable=False, server_default="open"),
        sa.Column("assigned_to",           sa.String(36),  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("resolved_at",           sa.DateTime,    nullable=True),
        sa.Column("false_positive_reason", sa.Text,        nullable=True),
        sa.Column("incident_id",           sa.String(36),  sa.ForeignKey("security_incidents.id"), nullable=True),
    )
    op.create_index("idx_det_org_sev",    "security_detections", ["org_id", "severity"])
    op.create_index("idx_det_org_status", "security_detections", ["org_id", "status"])
    op.create_index("idx_det_mitre",      "security_detections", ["mitre_id"])
    op.create_index("idx_det_detected",   "security_detections", ["detected_at"])

    # ── security_events ───────────────────────────────────────────────────────
    op.create_table(
        "security_events",
        sa.Column("id",            sa.String(36),  primary_key=True),
        sa.Column("org_id",        sa.String(36),  sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id",       sa.String(36),  sa.ForeignKey("users.id"),         nullable=True),
        sa.Column("category",      sa.String(32),  nullable=False),
        sa.Column("severity",      sa.String(16),  nullable=False),
        sa.Column("event_type",    sa.String(128), nullable=False),
        sa.Column("ip_address",    sa.String(64),  nullable=True),
        sa.Column("user_agent",    sa.Text,        nullable=True),
        sa.Column("session_id",    sa.String(36),  nullable=True),
        sa.Column("asn",           sa.String(64),  nullable=True),
        sa.Column("country",       sa.String(64),  nullable=True),
        sa.Column("is_vpn",        sa.Boolean,     server_default="0"),
        sa.Column("is_tor",        sa.Boolean,     server_default="0"),
        sa.Column("resource_type", sa.String(128), nullable=True),
        sa.Column("resource_id",   sa.String(256), nullable=True),
        sa.Column("detail",        sa.Text,        nullable=True),
        sa.Column("raw_event",     sa.JSON,        nullable=True),
        sa.Column("indicators",    sa.JSON,        nullable=True),
        sa.Column("detection_id",  sa.String(36),  sa.ForeignKey("security_detections.id"), nullable=True),
        sa.Column("occurred_at",   sa.DateTime,    nullable=True),
        sa.Column("ingested_at",   sa.DateTime,    nullable=True),
    )
    op.create_index("idx_event_org_cat",      "security_events", ["org_id", "category"])
    op.create_index("idx_event_org_sev",      "security_events", ["org_id", "severity"])
    op.create_index("idx_event_org_type",     "security_events", ["org_id", "event_type"])
    op.create_index("idx_event_ip",           "security_events", ["ip_address"])
    op.create_index("idx_event_occurred",     "security_events", ["occurred_at"])
    op.create_index("idx_event_org_occurred", "security_events", ["org_id", "occurred_at"])

    # ── login_anomalies ───────────────────────────────────────────────────────
    op.create_table(
        "login_anomalies",
        sa.Column("id",           sa.String(36), primary_key=True),
        sa.Column("org_id",       sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id",      sa.String(36), sa.ForeignKey("users.id"),         nullable=False),
        sa.Column("anomaly_type", sa.String(64), nullable=False),
        sa.Column("severity",     sa.String(16), nullable=False),
        sa.Column("detail",       sa.JSON,       nullable=True),
        sa.Column("ip_address",   sa.String(64), nullable=True),
        sa.Column("country",      sa.String(64), nullable=True),
        sa.Column("asn",          sa.String(64), nullable=True),
        sa.Column("is_resolved",  sa.Boolean,    server_default="0"),
        sa.Column("resolved_at",  sa.DateTime,   nullable=True),
        sa.Column("occurred_at",  sa.DateTime,   nullable=True),
    )
    op.create_index("idx_anomaly_org_type", "login_anomalies", ["org_id", "anomaly_type"])
    op.create_index("idx_anomaly_user",     "login_anomalies", ["user_id"])
    op.create_index("idx_anomaly_occurred", "login_anomalies", ["occurred_at"])

    # ── security_metric_snapshots ─────────────────────────────────────────────
    op.create_table(
        "security_metric_snapshots",
        sa.Column("id",               sa.String(36), primary_key=True),
        sa.Column("org_id",           sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("snapshot_hour",    sa.DateTime,   nullable=False),
        sa.Column("total_events",     sa.Integer,    server_default="0"),
        sa.Column("events_info",      sa.Integer,    server_default="0"),
        sa.Column("events_low",       sa.Integer,    server_default="0"),
        sa.Column("events_medium",    sa.Integer,    server_default="0"),
        sa.Column("events_high",      sa.Integer,    server_default="0"),
        sa.Column("events_critical",  sa.Integer,    server_default="0"),
        sa.Column("login_success",    sa.Integer,    server_default="0"),
        sa.Column("login_failed",     sa.Integer,    server_default="0"),
        sa.Column("mfa_challenged",   sa.Integer,    server_default="0"),
        sa.Column("mfa_failed",       sa.Integer,    server_default="0"),
        sa.Column("auth_failure_rate",sa.Float,      nullable=True),
        sa.Column("new_detections",   sa.Integer,    server_default="0"),
        sa.Column("open_detections",  sa.Integer,    server_default="0"),
        sa.Column("avg_mttd_seconds", sa.Float,      nullable=True),
        sa.Column("avg_mttr_seconds", sa.Float,      nullable=True),
        sa.Column("login_anomalies",  sa.Integer,    server_default="0"),
        sa.Column("abac_denials",     sa.Integer,    server_default="0"),
        sa.Column("rate_limit_hits",  sa.Integer,    server_default="0"),
        sa.Column("open_incidents",   sa.Integer,    server_default="0"),
        sa.Column("new_incidents",    sa.Integer,    server_default="0"),
        sa.Column("created_at",       sa.DateTime,   nullable=True),
    )
    op.create_index("idx_snapshot_org_hour", "security_metric_snapshots",
                    ["org_id", "snapshot_hour"], unique=True)


def downgrade() -> None:
    op.drop_table("security_metric_snapshots")
    op.drop_table("login_anomalies")
    op.drop_table("security_events")
    op.drop_table("security_detections")
    op.drop_table("security_incidents")
