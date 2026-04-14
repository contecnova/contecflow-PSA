"""
Security Observability models for SOC-ready dashboards.

Models:
- SecurityEvent: Normalized security event log (logins, anomalies, ABAC denials, etc.)
- SecurityDetection: Attack indicator detections with severity + kill-chain stage
- SecurityIncident: Aggregated incidents with MTTD/MTTR tracking
- SecurityBaseline: Per-user/IP behavioral baselines for anomaly detection
"""
from datetime import datetime
from enum import Enum
from sqlalchemy import (
    Column, String, Integer, Float, DateTime,
    ForeignKey, JSON, Boolean, Text, Index,
)
from sqlalchemy.orm import relationship
from app.db.base import Base


# ── Enumerations ──────────────────────────────────────────────────────────────

class EventCategory(str, Enum):
    AUTH        = "auth"            # login ok/fail, MFA, SSO
    AUTH_ANOMALY = "auth_anomaly"   # impossible travel, new country, cred stuffing
    SESSION     = "session"         # device registered, session revoked, concurrent sessions
    AUTHZ       = "authz"           # ABAC/RBAC deny, privilege escalation attempt
    DATA        = "data"            # mass export, sensitive data access, download spike
    API         = "api"             # rate limit hit, unusual method, unsupported verb
    SUPPLY_CHAIN= "supply_chain"    # SAST/SCA/DAST findings from CI
    ADMIN       = "admin"           # user created/disabled, role change, policy update
    SYSTEM      = "system"          # service error, config change, secret access


class EventSeverity(str, Enum):
    INFO      = "info"       # 0 — expected activity, logged for completeness
    LOW       = "low"        # 1 — minor anomaly, monitor
    MEDIUM    = "medium"     # 2 — suspicious, investigate
    HIGH      = "high"       # 3 — probable attack, alert SOC
    CRITICAL  = "critical"   # 4 — confirmed/imminent breach, page SOC


class IncidentStatus(str, Enum):
    OPEN        = "open"
    INVESTIGATING = "investigating"
    CONTAINED   = "contained"
    RESOLVED    = "resolved"
    FALSE_POS   = "false_positive"


class KillChainStage(str, Enum):
    RECON             = "reconnaissance"
    WEAPONIZATION     = "weaponization"
    DELIVERY          = "delivery"
    EXPLOITATION      = "exploitation"
    INSTALLATION      = "installation"
    C2                = "command_and_control"
    ACTIONS_ON_TARGET = "actions_on_objectives"


# ── Models ────────────────────────────────────────────────────────────────────

class SecurityEvent(Base):
    """
    Normalized, immutable security event log.

    Sources: auth endpoints, ABAC engine, session service, API middleware,
             CI/CD security jobs, admin actions.
    """
    __tablename__ = "security_events"

    id          = Column(String(36), primary_key=True)
    org_id      = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    user_id     = Column(String(36), ForeignKey("users.id"),         nullable=True,  index=True)

    # Classification
    category    = Column(String(32),  nullable=False, index=True)   # EventCategory
    severity    = Column(String(16),  nullable=False, index=True)   # EventSeverity
    event_type  = Column(String(128), nullable=False, index=True)   # e.g. "login_failed"

    # Actor context
    ip_address  = Column(String(64),  nullable=True, index=True)
    user_agent  = Column(Text,        nullable=True)
    session_id  = Column(String(36),  nullable=True, index=True)
    asn         = Column(String(64),  nullable=True)
    country     = Column(String(64),  nullable=True)
    is_vpn      = Column(Boolean,     default=False)
    is_tor      = Column(Boolean,     default=False)

    # Event payload (searchable)
    resource_type = Column(String(128), nullable=True)
    resource_id   = Column(String(256), nullable=True)
    detail        = Column(Text,        nullable=True)       # human-readable description
    raw_event     = Column(JSON,        nullable=True)       # full original payload
    indicators    = Column(JSON,        nullable=True)       # {"mitre": "T1110.001", ...}

    # Detection link
    detection_id = Column(String(36), ForeignKey("security_detections.id"), nullable=True, index=True)

    # Timestamps
    occurred_at  = Column(DateTime, default=datetime.utcnow, index=True)  # when it happened
    ingested_at  = Column(DateTime, default=datetime.utcnow)              # when we stored it

    __table_args__ = (
        Index("idx_event_org_cat",      "org_id", "category"),
        Index("idx_event_org_sev",      "org_id", "severity"),
        Index("idx_event_org_type",     "org_id", "event_type"),
        Index("idx_event_ip",           "ip_address"),
        Index("idx_event_occurred",     "occurred_at"),
        Index("idx_event_org_occurred", "org_id", "occurred_at"),
    )

    organization = relationship("Organization", backref="security_events")
    user         = relationship("User", foreign_keys=[user_id])
    detection    = relationship("SecurityDetection", back_populates="events", foreign_keys=[detection_id])


class SecurityDetection(Base):
    """
    Correlated detection raised when one or more events match an attack pattern.

    Maps to MITRE ATT&CK techniques. Status drives MTTD/MTTR tracking.
    """
    __tablename__ = "security_detections"

    id           = Column(String(36), primary_key=True)
    org_id       = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)

    # Classification
    title        = Column(String(256),  nullable=False)
    description  = Column(Text,         nullable=True)
    severity     = Column(String(16),   nullable=False, index=True)   # EventSeverity
    category     = Column(String(32),   nullable=False, index=True)
    kill_chain   = Column(String(64),   nullable=True)                # KillChainStage
    mitre_id     = Column(String(32),   nullable=True, index=True)    # e.g. "T1110.001"
    mitre_tactic = Column(String(64),   nullable=True)                # "Credential Access"

    # Scope
    user_id      = Column(String(36),  ForeignKey("users.id"), nullable=True, index=True)
    ip_address   = Column(String(64),  nullable=True, index=True)
    country      = Column(String(64),  nullable=True)

    # Context
    event_count  = Column(Integer,  default=1)   # how many raw events contributed
    raw_data     = Column(JSON,     nullable=True)
    evidence     = Column(JSON,     nullable=True)  # {"rule": "...", "matched": [...]}

    # MTTD tracking
    first_seen_at  = Column(DateTime, default=datetime.utcnow, index=True)  # oldest event  timestamp
    detected_at    = Column(DateTime, default=datetime.utcnow, index=True)  # when rule fired
    # MTTD = detected_at - first_seen_at (seconds)

    # Status
    status       = Column(String(32),  default=IncidentStatus.OPEN, index=True)
    assigned_to  = Column(String(36),  ForeignKey("users.id"), nullable=True)
    resolved_at  = Column(DateTime, nullable=True, index=True)
    # MTTR = resolved_at - detected_at (seconds)
    false_positive_reason = Column(Text, nullable=True)

    # Incident link (if escalated)
    incident_id  = Column(String(36), ForeignKey("security_incidents.id"), nullable=True, index=True)

    __table_args__ = (
        Index("idx_det_org_sev",     "org_id", "severity"),
        Index("idx_det_org_status",  "org_id", "status"),
        Index("idx_det_mitre",       "mitre_id"),
        Index("idx_det_detected",    "detected_at"),
    )

    organization = relationship("Organization",  backref="detections")
    subject_user = relationship("User",          foreign_keys=[user_id])
    assignee     = relationship("User",          foreign_keys=[assigned_to])
    incident     = relationship("SecurityIncident", back_populates="detections", foreign_keys=[incident_id])
    events       = relationship("SecurityEvent",  back_populates="detection", foreign_keys=[SecurityEvent.detection_id])


class SecurityIncident(Base):
    """
    High-level incident aggregating multiple detections.
    Owns the authoritative MTTD/MTTR values used by the SOC KPI board.
    """
    __tablename__ = "security_incidents"

    id             = Column(String(36), primary_key=True)
    org_id         = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)

    title          = Column(String(256), nullable=False)
    description    = Column(Text,        nullable=True)
    severity       = Column(String(16),  nullable=False, index=True)
    status         = Column(String(32),  default=IncidentStatus.OPEN, index=True)

    # MTTD/MTTR  (seconds as floats; NULL until respective milestone)
    mttd_seconds   = Column(Float,   nullable=True)   # set when first detected_at is known
    mttr_seconds   = Column(Float,   nullable=True)   # set on resolution

    # Timeline
    started_at     = Column(DateTime, default=datetime.utcnow, index=True)  # first event
    detected_at    = Column(DateTime, nullable=True)
    contained_at   = Column(DateTime, nullable=True)
    resolved_at    = Column(DateTime, nullable=True, index=True)

    # Team
    lead_analyst   = Column(String(36), ForeignKey("users.id"), nullable=True)
    playbook_ref   = Column(String(256), nullable=True)  # link to runbook
    tags           = Column(JSON,  default=list)         # ["brute-force", "account-takeover"]
    timeline_notes = Column(JSON,  default=list)         # [{ts, author, note}]

    # Closure
    root_cause       = Column(Text,  nullable=True)
    remediation_note = Column(Text,  nullable=True)
    lessons_learned  = Column(Text,  nullable=True)

    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_inc_org_status",   "org_id", "status"),
        Index("idx_inc_org_severity", "org_id", "severity"),
        Index("idx_inc_started",      "started_at"),
    )

    organization = relationship("Organization", backref="incidents")
    analyst      = relationship("User",         foreign_keys=[lead_analyst])
    detections   = relationship("SecurityDetection", back_populates="incident", foreign_keys=[SecurityDetection.incident_id])


class LoginAnomaly(Base):
    """
    Dedicated model for login anomaly signals (impossible travel, new device, cred stuffing).
    Drives the Anomalous-Login widget in the SOC overview.
    """
    __tablename__ = "login_anomalies"

    id           = Column(String(36), primary_key=True)
    org_id       = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    user_id      = Column(String(36), ForeignKey("users.id"),         nullable=False, index=True)

    anomaly_type = Column(String(64),  nullable=False, index=True)
    # Types: impossible_travel | new_country | new_asn | vpn_detected | tor_detected |
    #        concurrent_sessions | credential_stuffing | brute_force |
    #        mfa_bypass_attempt | session_hijack_suspected

    severity     = Column(String(16),  nullable=False)
    detail       = Column(JSON,        nullable=True)   # type-specific metadata
    ip_address   = Column(String(64),  nullable=True)
    country      = Column(String(64),  nullable=True)
    asn          = Column(String(64),  nullable=True)
    is_resolved  = Column(Boolean,     default=False, index=True)
    resolved_at  = Column(DateTime,    nullable=True)

    occurred_at  = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("idx_anomaly_org_type", "org_id", "anomaly_type"),
        Index("idx_anomaly_user",     "user_id"),
        Index("idx_anomaly_occurred", "occurred_at"),
    )

    organization = relationship("Organization", backref="login_anomalies")
    user         = relationship("User")


class SecurityMetricSnapshot(Base):
    """
    Hourly pre-aggregated KPI snapshots for instant SOC dashboard rendering.

    Values: events_by_severity, MTTD, MTTR, open_detections, open_incidents,
            auth_failure_rate, anomaly_count per hour.
    """
    __tablename__ = "security_metric_snapshots"

    id              = Column(String(36), primary_key=True)
    org_id          = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    snapshot_hour   = Column(DateTime, nullable=False, index=True)   # truncated to hour

    # Event volume
    total_events    = Column(Integer, default=0)
    events_info     = Column(Integer, default=0)
    events_low      = Column(Integer, default=0)
    events_medium   = Column(Integer, default=0)
    events_high     = Column(Integer, default=0)
    events_critical = Column(Integer, default=0)

    # Auth signals
    login_success   = Column(Integer, default=0)
    login_failed    = Column(Integer, default=0)
    mfa_challenged  = Column(Integer, default=0)
    mfa_failed      = Column(Integer, default=0)
    auth_failure_rate = Column(Float, nullable=True)  # login_failed / total login attempts

    # Detection KPIs
    new_detections  = Column(Integer, default=0)
    open_detections = Column(Integer, default=0)
    avg_mttd_seconds = Column(Float,  nullable=True)
    avg_mttr_seconds = Column(Float,  nullable=True)

    # Anomalies
    login_anomalies = Column(Integer, default=0)
    abac_denials    = Column(Integer, default=0)
    rate_limit_hits = Column(Integer, default=0)

    # Incident KPIs
    open_incidents  = Column(Integer, default=0)
    new_incidents   = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_snapshot_org_hour", "org_id", "snapshot_hour", unique=True),
    )

    organization = relationship("Organization", backref="security_snapshots")
