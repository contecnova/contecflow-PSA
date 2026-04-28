"""
Service Desk ITSM/ITIL models – full ITIL-aligned service management.
Works standalone OR linked to Contecflow projects/contracts.
"""
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text, Boolean, Integer, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
import uuid
from app.db.base import Base
from app.core.config import settings


# ── Enumerations ──────────────────────────────────────────────────────────────

class TicketType(str, enum.Enum):
    incident = "incident"
    service_request = "service_request"
    change = "change"
    problem = "problem"
    question = "question"


class TicketStatus(str, enum.Enum):
    new = "new"
    assigned = "assigned"
    in_progress = "in_progress"
    pending_client = "pending_client"
    pending_third = "pending_third"
    resolved = "resolved"
    closed = "closed"
    cancelled = "cancelled"


class TicketPriority(str, enum.Enum):
    p1_critical = "p1_critical"
    p2_high = "p2_high"
    p3_medium = "p3_medium"
    p4_low = "p4_low"


class TicketUrgency(str, enum.Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class TicketImpact(str, enum.Enum):
    enterprise = "enterprise"
    department = "department"
    user = "user"
    minimal = "minimal"


class SupportLevel(str, enum.Enum):
    l1 = "l1"
    l2 = "l2"
    l3 = "l3"


class SLAStatus(str, enum.Enum):
    ok = "ok"
    at_risk = "at_risk"
    breached = "breached"
    paused = "paused"


# ── Service Catalog ───────────────────────────────────────────────────────────

class ServiceCategory(Base):
    __tablename__ = "sd_service_categories"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(10), default="🔧")
    color = Column(String(20), default="#00d4ff")
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    services = relationship("ServiceItem", back_populates="category",
                            cascade="all, delete-orphan",
                            order_by="ServiceItem.sort_order")


class ServiceItem(Base):
    __tablename__ = "sd_service_items"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    category_id = Column(String(36), ForeignKey("sd_service_categories.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    ticket_type = Column(Enum(TicketType), default=TicketType.service_request)
    default_priority = Column(Enum(TicketPriority), default=TicketPriority.p3_medium)
    default_support_level = Column(Enum(SupportLevel), default=SupportLevel.l1)

    sla_response_hours = Column(Float, default=settings.SLA_P3_RESPONSE_HOURS)
    sla_resolution_hours = Column(Float, default=settings.SLA_P3_RESOLUTION_HOURS)

    custom_fields = Column(Text, nullable=True)

    auto_assign_group = Column(String(100), nullable=True)
    requires_approval = Column(Boolean, default=False)
    approval_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)

    is_active = Column(Boolean, default=True)
    is_visible_to_clients = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    category = relationship("ServiceCategory", back_populates="services")
    approver = relationship("User", foreign_keys=[approval_user_id])


# ── SLA Policies ──────────────────────────────────────────────────────────────

class SLAPolicy(Base):
    __tablename__ = "sd_sla_policies"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    is_default = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    p1_response_hours = Column(Float, default=settings.SLA_P1_RESPONSE_HOURS)
    p1_resolution_hours = Column(Float, default=settings.SLA_P1_RESOLUTION_HOURS)
    p2_response_hours = Column(Float, default=settings.SLA_P2_RESPONSE_HOURS)
    p2_resolution_hours = Column(Float, default=settings.SLA_P2_RESOLUTION_HOURS)
    p3_response_hours = Column(Float, default=settings.SLA_P3_RESPONSE_HOURS)
    p3_resolution_hours = Column(Float, default=settings.SLA_P3_RESOLUTION_HOURS)
    p4_response_hours = Column(Float, default=settings.SLA_P4_RESPONSE_HOURS)
    p4_resolution_hours = Column(Float, default=settings.SLA_P4_RESOLUTION_HOURS)

    business_hours_only = Column(Boolean, default=True)
    business_start = Column(Integer, default=9)
    business_end = Column(Integer, default=18)
    business_days = Column(String(20), default="1,2,3,4,5")

    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ── CMDB ──────────────────────────────────────────────────────────────────────

class CIType(str, enum.Enum):
    application = "application"
    server = "server"
    database = "database"
    network = "network"
    service = "service"
    module = "module"
    integration = "integration"
    other = "other"


class CIStatus(str, enum.Enum):
    operational = "operational"
    degraded = "degraded"
    maintenance = "maintenance"
    retired = "retired"


class ConfigurationItem(Base):
    __tablename__ = "sd_configuration_items"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(30), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    ci_type = Column(Enum(CIType), nullable=False)
    status = Column(Enum(CIStatus), default=CIStatus.operational)
    description = Column(Text, nullable=True)

    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True)
    owner_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    environment = Column(String(50), nullable=True)

    version = Column(String(50), nullable=True)
    location = Column(String(255), nullable=True)
    vendor = Column(String(100), nullable=True)

    sla_policy_id = Column(String(36), ForeignKey("sd_sla_policies.id"), nullable=True)

    criticality = Column(String(20), default="medium")
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    project = relationship("Project", foreign_keys=[project_id])
    owner = relationship("User", foreign_keys=[owner_user_id])
    sla_policy = relationship("SLAPolicy")


# ── Agent Groups ──────────────────────────────────────────────────────────────

class AgentGroup(Base):
    __tablename__ = "sd_agent_groups"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    support_level = Column(Enum(SupportLevel), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    members = relationship("AgentGroupMember", back_populates="group", cascade="all, delete-orphan")


class AgentGroupMember(Base):
    __tablename__ = "sd_agent_group_members"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    group_id = Column(String(36), ForeignKey("sd_agent_groups.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    is_lead = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    group = relationship("AgentGroup", back_populates="members")
    user = relationship("User", foreign_keys=[user_id])


# ── Tickets ───────────────────────────────────────────────────────────────────

class Ticket(Base):
    __tablename__ = "sd_tickets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    number = Column(String(20), unique=True, nullable=False, index=True)

    ticket_type = Column(Enum(TicketType), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)

    status = Column(Enum(TicketStatus), default=TicketStatus.new, nullable=False, index=True)
    priority = Column(Enum(TicketPriority), default=TicketPriority.p3_medium, nullable=False, index=True)
    urgency = Column(Enum(TicketUrgency), default=TicketUrgency.medium)
    impact = Column(Enum(TicketImpact), default=TicketImpact.user)
    support_level = Column(Enum(SupportLevel), default=SupportLevel.l1)

    requester_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    requester_client_id = Column(String(36), ForeignKey("client_users.id"), nullable=True)
    requester_name = Column(String(255), nullable=True)
    requester_email = Column(String(255), nullable=True)

    assigned_to_user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    assigned_group_id = Column(String(36), ForeignKey("sd_agent_groups.id"), nullable=True)

    # Context – all optional, works without project
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    # Empresa cliente directa (independiente del proyecto)
    client_id  = Column(String(36), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)
    # Tipo de recurso vinculado (proyecto, licencia, contrato, activo...)
    linked_resource_type = Column(String(50), nullable=True)   # project|license|contract|asset
    linked_resource_id   = Column(String(36), nullable=True)   # ID del recurso
    contract_id = Column(String(36), ForeignKey("contracts.id"), nullable=True)
    ci_id = Column(String(36), ForeignKey("sd_configuration_items.id"), nullable=True)
    service_item_id = Column(String(36), ForeignKey("sd_service_items.id"), nullable=True)

    problem_id = Column(String(36), ForeignKey("sd_problems.id"), nullable=True)
    parent_ticket_id = Column(String(36), ForeignKey("sd_tickets.id"), nullable=True)

    sla_policy_id = Column(String(36), ForeignKey("sd_sla_policies.id"), nullable=True)
    sla_response_due = Column(DateTime(timezone=True), nullable=True)
    sla_resolution_due = Column(DateTime(timezone=True), nullable=True)
    sla_response_status = Column(Enum(SLAStatus), default=SLAStatus.ok)
    sla_resolution_status = Column(Enum(SLAStatus), default=SLAStatus.ok)
    sla_paused_at = Column(DateTime(timezone=True), nullable=True)
    sla_pause_minutes = Column(Integer, default=0)

    resolution = Column(Text, nullable=True)
    resolution_code = Column(String(50), nullable=True)
    kb_article_id = Column(String(36), ForeignKey("sd_kb_articles.id"), nullable=True)

    csat_score = Column(Integer, nullable=True)
    csat_comment = Column(Text, nullable=True)
    csat_requested_at = Column(DateTime(timezone=True), nullable=True)

    time_spent_minutes = Column(Integer, default=0)

    first_response_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    first_response_minutes = Column(Integer, nullable=True)
    resolution_minutes = Column(Integer, nullable=True)
    sla_response_breached = Column(Boolean, default=False)
    sla_resolution_breached = Column(Boolean, default=False)

    # Phase 2 — Predictive Intelligence
    predicted_severity = Column(String(20), nullable=True)
    predicted_resolution_minutes = Column(Integer, nullable=True)
    escalation_risk_score = Column(Float, nullable=True)
    prediction_generated_at = Column(DateTime(timezone=True), nullable=True)

    # Phase 3 — AI Auto-Resolution
    auto_resolved = Column(Boolean, default=False, index=True)
    auto_resolved_at = Column(DateTime(timezone=True), nullable=True)
    auto_resolved_by = Column(String(100), nullable=True)  # "ai_auto_resolution" | user name
    auto_resolved_confidence = Column(Float, nullable=True)  # 0-1
    resolution_text = Column(Text, nullable=True)  # AI-suggested resolution
    root_cause = Column(String(255), nullable=True)  # AI-identified root cause
    resolution_kb_articles = Column(Text, nullable=True)  # JSON array of KB article numbers

    source = Column(String(20), default="portal")
    tags = Column(String(500), nullable=True)

    # FIX: Use server_default so SQLite sets this correctly
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)

    requester_user = relationship("User", foreign_keys=[requester_user_id])
    requester_client = relationship("ClientUser", foreign_keys=[requester_client_id])
    assigned_to = relationship("User", foreign_keys=[assigned_to_user_id])
    client       = relationship("Client", foreign_keys=[client_id])
    created_by = relationship("User", foreign_keys=[created_by_user_id])
    assigned_group = relationship("AgentGroup")
    project = relationship("Project")
    ci = relationship("ConfigurationItem")
    service_item = relationship("ServiceItem")
    sla_policy = relationship("SLAPolicy")
    kb_article = relationship("KBArticle", foreign_keys=[kb_article_id])
    comments = relationship("TicketComment", back_populates="ticket",
                            cascade="all, delete-orphan",
                            order_by="TicketComment.created_at")
    # FIX: TicketHistory uses 'changed_at', not 'created_at'
    history = relationship("TicketHistory", back_populates="ticket",
                           cascade="all, delete-orphan",
                           order_by="TicketHistory.changed_at")
    time_logs = relationship("TicketTimeLog", back_populates="ticket",
                             cascade="all, delete-orphan")
    child_tickets = relationship("Ticket", foreign_keys=[parent_ticket_id])


class TicketComment(Base):
    __tablename__ = "sd_ticket_comments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_id = Column(String(36), ForeignKey("sd_tickets.id", ondelete="CASCADE"), nullable=False, index=True)

    body = Column(Text, nullable=False)
    is_public = Column(Boolean, default=True)
    is_solution = Column(Boolean, default=False)

    author_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    author_client_id = Column(String(36), ForeignKey("client_users.id"), nullable=True)
    author_name = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    ticket = relationship("Ticket", back_populates="comments")
    author_user = relationship("User", foreign_keys=[author_user_id])
    author_client = relationship("ClientUser", foreign_keys=[author_client_id])


class TicketHistory(Base):
    """Immutable audit trail of all changes."""
    __tablename__ = "sd_ticket_history"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_id = Column(String(36), ForeignKey("sd_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    field_name = Column(String(100), nullable=False)
    old_value = Column(String(500), nullable=True)
    new_value = Column(String(500), nullable=True)
    changed_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    # NOTE: This model uses 'changed_at', NOT 'created_at' — keep consistent
    changed_at = Column(DateTime(timezone=True), server_default=func.now())

    ticket = relationship("Ticket", back_populates="history")
    changed_by = relationship("User", foreign_keys=[changed_by_user_id])


class TicketTimeLog(Base):
    __tablename__ = "sd_ticket_time_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_id = Column(String(36), ForeignKey("sd_tickets.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    minutes = Column(Integer, nullable=False)
    description = Column(String(255), nullable=True)
    billable = Column(Boolean, default=False)
    logged_at = Column(DateTime(timezone=True), server_default=func.now())

    ticket = relationship("Ticket", back_populates="time_logs")
    user = relationship("User", foreign_keys=[user_id])


# ── Problem Management ────────────────────────────────────────────────────────

class ProblemStatus(str, enum.Enum):
    open = "open"
    investigating = "investigating"
    known_error = "known_error"
    resolved = "resolved"
    closed = "closed"


class Problem(Base):
    __tablename__ = "sd_problems"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    number = Column(String(20), unique=True, nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(Enum(ProblemStatus), default=ProblemStatus.open, index=True)
    priority = Column(Enum(TicketPriority), default=TicketPriority.p2_high)

    root_cause = Column(Text, nullable=True)
    workaround = Column(Text, nullable=True)
    fix_description = Column(Text, nullable=True)

    # RCA enrichment (Fase 1 ITSM)
    rca_type = Column(String(30), nullable=True)    # hardware|software|process|human|network|unknown
    rca_ai_suggestion = Column(Text, nullable=True) # JSON with AI-generated RCA suggestion

    # RCA Wizard — ITSM-P06
    rca_template = Column(String(30), nullable=True)   # five_whys|fishbone|itil_standard|custom
    rca_wizard_state = Column(Text, nullable=True)     # JSON blob with wizard steps/answers/completion
    auto_detected = Column(Boolean, default=False)  # True when created by auto-detection task
    affected_services_json = Column(Text, nullable=True)  # JSON list of CI ids

    # RCA approval lifecycle (ITSM-P02)
    investigation_started_at = Column(DateTime(timezone=True), nullable=True)
    rca_due_date = Column(DateTime(timezone=True), nullable=True)      # SLA deadline for RCA
    rca_evidence = Column(Text, nullable=True)                          # Supporting evidence (JSON/text)
    rca_approved_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    rca_approved_at = Column(DateTime(timezone=True), nullable=True)

    # KEDB lifecycle (ITSM-P02)
    kedb_published_at = Column(DateTime(timezone=True), nullable=True)
    kedb_expires_at = Column(DateTime(timezone=True), nullable=True)   # Scheduled review/expiry
    kedb_reviewed_at = Column(DateTime(timezone=True), nullable=True)  # Last manual review
    kedb_effectiveness_score = Column(Float, nullable=True)            # 0-100 (% tickets resolved via workaround)
    kb_article_id = Column(String(36), nullable=True)                  # Auto-generated KB article

    ci_id = Column(String(36), ForeignKey("sd_configuration_items.id"), nullable=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True)

    owner_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)

    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    ci = relationship("ConfigurationItem")
    owner = relationship("User", foreign_keys=[owner_user_id])
    rca_approver = relationship("User", foreign_keys=[rca_approved_by])
    related_tickets = relationship("Ticket", foreign_keys="Ticket.problem_id")


# ── Knowledge Base ────────────────────────────────────────────────────────────

class KBStatus(str, enum.Enum):
    draft = "draft"
    published = "published"
    archived = "archived"


class KBArticle(Base):
    __tablename__ = "sd_kb_articles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    number = Column(String(20), unique=True, nullable=False)
    title = Column(String(500), nullable=False)
    body = Column(Text, nullable=False)
    summary = Column(String(500), nullable=True)
    status = Column(Enum(KBStatus), default=KBStatus.draft, index=True)

    category_id = Column(String(36), ForeignKey("sd_service_categories.id"), nullable=True)
    tags = Column(String(500), nullable=True)
    is_public = Column(Boolean, default=True)

    created_from_ticket_id = Column(String(36), nullable=True)
    service_item_id = Column(String(36), ForeignKey("sd_service_items.id"), nullable=True)

    view_count = Column(Integer, default=0)
    helpful_count = Column(Integer, default=0)
    not_helpful_count = Column(Integer, default=0)

    author_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    reviewer_id = Column(String(36), ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    published_at = Column(DateTime(timezone=True), nullable=True)

    category = relationship("ServiceCategory")
    author = relationship("User", foreign_keys=[author_id])
    reviewer = relationship("User", foreign_keys=[reviewer_id])
    versions = relationship(
        "KBArticleVersion",
        back_populates="article",
        cascade="all, delete-orphan",
        order_by="KBArticleVersion.version.desc()",
    )


class KBArticleVersion(Base):
    """Immutable KB snapshot used for audit trail and rollback."""
    __tablename__ = "sd_kb_article_versions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    article_id = Column(String(36), ForeignKey("sd_kb_articles.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    title = Column(String(500), nullable=False)
    body = Column(Text, nullable=False)
    summary = Column(String(500), nullable=True)
    tags = Column(String(500), nullable=True)
    status = Column(Enum(KBStatus), default=KBStatus.draft)
    change_note = Column(String(255), nullable=True)
    changed_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    article = relationship("KBArticle", back_populates="versions")
    changed_by = relationship("User", foreign_keys=[changed_by_user_id])


# ── Announcements / Maintenance ───────────────────────────────────────────────

class Announcement(Base):
    __tablename__ = "sd_announcements"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    type = Column(String(20), default="info")
    is_active = Column(Boolean, default=True)
    show_to_clients = Column(Boolean, default=True)
    starts_at = Column(DateTime(timezone=True), nullable=True)
    ends_at = Column(DateTime(timezone=True), nullable=True)

    ci_id = Column(String(36), ForeignKey("sd_configuration_items.id"), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    ci = relationship("ConfigurationItem")
    creator = relationship("User", foreign_keys=[created_by])


# ════════════════════════════════════════════════════════════════════════════
# AMPLIACIÓN ITIL/ITSM — Contecflow Service Desk v2
# ════════════════════════════════════════════════════════════════════════════

# ── Linked Tickets (relates-to, duplicates, parent/child, caused-by) ─────────

class TicketLinkType(str, enum.Enum):
    relates_to   = "relates_to"
    duplicates   = "duplicates"
    caused_by    = "caused_by"
    blocks       = "blocks"
    child_of     = "child_of"

class TicketLink(Base):
    __tablename__ = "sd_ticket_links"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id    = Column(String(36), ForeignKey("sd_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    target_id    = Column(String(36), ForeignKey("sd_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    link_type    = Column(Enum(TicketLinkType), nullable=False)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    created_by   = Column(String(36), ForeignKey("users.id"), nullable=True)

    source = relationship("Ticket", foreign_keys=[source_id])
    target = relationship("Ticket", foreign_keys=[target_id])


# ── Routing Rules — asignación automática de tickets ─────────────────────────

class RoutingRule(Base):
    """Regla de routing automático: si condición → asignar a grupo/agente."""
    __tablename__ = "sd_routing_rules"

    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name       = Column(String(255), nullable=False)
    is_active  = Column(Boolean, default=True)
    priority   = Column(Integer, default=100)  # menor = mayor prioridad

    # Condiciones (JSON): {"ticket_type": "incident", "priority": ["p1_critical","p2_high"], "category_id": "..."}
    conditions = Column(Text, nullable=False, default="{}")
    # Acciones (JSON): {"assign_group": "id", "assign_user": "id", "set_priority": "p1_critical", "notify": ["email"]}
    actions    = Column(Text, nullable=False, default="{}")

    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ── Routing Feedback — historial de resultados de routing ML (ITSM-P07) ──────

class RoutingFeedback(Base):
    """Records routing outcomes per ticket for ML model learning.

    Written when a ticket is assigned (routed_at + context) and updated
    when it closes (resolution_minutes, csat_score, reopened).
    """
    __tablename__ = "sd_routing_feedback"

    id                  = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_id           = Column(String(36), ForeignKey("sd_tickets.id", ondelete="SET NULL"), nullable=True, index=True)
    assigned_agent_id   = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    ticket_type         = Column(String(30), nullable=True, index=True)
    category_id         = Column(String(36), ForeignKey("sd_service_categories.id", ondelete="SET NULL"), nullable=True, index=True)
    priority            = Column(String(20), nullable=True)
    support_level       = Column(String(10), nullable=True)
    resolution_minutes  = Column(Integer, nullable=True)     # filled on close
    csat_score          = Column(Integer, nullable=True)     # 1-5, filled on CSAT submit
    reopened            = Column(Boolean, default=False, nullable=False)
    routed_at           = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    outcome_recorded_at = Column(DateTime(timezone=True), nullable=True)


# ── SLA Events — historial de breaches y pausas ───────────────────────────────

class SLAEventType(str, enum.Enum):
    paused        = "paused"
    resumed       = "resumed"
    breach_warn   = "breach_warn"    # 75% del SLA consumido
    breached      = "breached"       # SLA roto
    met           = "met"            # SLA cumplido al cerrar

class SLAEvent(Base):
    __tablename__ = "sd_sla_events"

    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_id  = Column(String(36), ForeignKey("sd_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(Enum(SLAEventType), nullable=False)
    sla_type   = Column(String(20), default="resolution")  # response | resolution
    note       = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)


# ── CMDB Relations — mapa de dependencias entre CIs ──────────────────────────

class CIRelationType(str, enum.Enum):
    depends_on   = "depends_on"     # A depende de B
    hosts        = "hosts"          # servidor aloja aplicación
    connects_to  = "connects_to"    # red
    backed_up_by = "backed_up_by"
    monitored_by = "monitored_by"
    part_of      = "part_of"

class CIRelation(Base):
    __tablename__ = "sd_ci_relations"

    id            = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_ci_id  = Column(String(36), ForeignKey("sd_configuration_items.id", ondelete="CASCADE"), nullable=False, index=True)
    target_ci_id  = Column(String(36), ForeignKey("sd_configuration_items.id", ondelete="CASCADE"), nullable=False, index=True)
    relation_type = Column(Enum(CIRelationType), nullable=False)
    notes         = Column(String(255), nullable=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())

    source_ci = relationship("ConfigurationItem", foreign_keys=[source_ci_id])
    target_ci = relationship("ConfigurationItem", foreign_keys=[target_ci_id])


# ── Change Request ITSM (completo) ───────────────────────────────────────────

class ChangeType(str, enum.Enum):
    standard  = "standard"    # pre-aprobado, bajo riesgo, procedimiento documentado
    normal    = "normal"      # requiere CAB
    emergency = "emergency"   # ECAB, urgente

class ChangeRisk(str, enum.Enum):
    low    = "low"
    medium = "medium"
    high   = "high"
    critical = "critical"

class ChangeStatus(str, enum.Enum):
    draft           = "draft"
    submitted       = "submitted"
    cab_review      = "cab_review"      # pendiente aprobación CAB
    approved        = "approved"
    scheduled       = "scheduled"
    in_progress     = "in_progress"
    implemented     = "implemented"
    post_review     = "post_review"     # PIR: Post-Implementation Review
    closed_success  = "closed_success"
    closed_failed   = "closed_failed"
    cancelled       = "cancelled"

class ITSMChangeRequest(Base):
    """Change Management ITIL completo — separado del ChangeRequest de proyectos."""
    __tablename__ = "sd_change_requests"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    number      = Column(String(20), unique=True, nullable=False, index=True)
    title       = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)

    change_type  = Column(Enum(ChangeType), nullable=False, default=ChangeType.normal)
    status       = Column(Enum(ChangeStatus), nullable=False, default=ChangeStatus.draft, index=True)
    risk         = Column(Enum(ChangeRisk), default=ChangeRisk.medium)
    priority     = Column(Enum(TicketPriority), default=TicketPriority.p3_medium)

    # Planificación
    planned_start    = Column(DateTime(timezone=True), nullable=True)
    planned_end      = Column(DateTime(timezone=True), nullable=True)
    actual_start     = Column(DateTime(timezone=True), nullable=True)
    actual_end       = Column(DateTime(timezone=True), nullable=True)

    # Plan
    implementation_plan = Column(Text, nullable=True)
    rollback_plan       = Column(Text, nullable=True)
    test_plan           = Column(Text, nullable=True)
    business_justification = Column(Text, nullable=True)

    # Impacto
    impact_description = Column(Text, nullable=True)
    affected_cis       = Column(Text, nullable=True)  # JSON: lista de CI IDs
    downtime_minutes   = Column(Integer, default=0)

    # Post-Implementation Review
    pir_notes    = Column(Text, nullable=True)
    pir_success  = Column(Boolean, nullable=True)
    pir_date     = Column(DateTime(timezone=True), nullable=True)

    # Relaciones
    requester_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    owner_id     = Column(String(36), ForeignKey("users.id"), nullable=True)
    approver_id  = Column(String(36), ForeignKey("users.id"), nullable=True)
    approved_at  = Column(DateTime(timezone=True), nullable=True)
    approved_by  = Column(String(36), ForeignKey("users.id"), nullable=True)
    rejected_reason = Column(Text, nullable=True)

    # Phase 2 — Change Impact Analysis
    auto_risk_score = Column(Float, nullable=True)
    impact_analysis_json = Column(Text, nullable=True)
    suggested_window_json = Column(Text, nullable=True)

    related_ticket_id  = Column(String(36), ForeignKey("sd_tickets.id"), nullable=True)
    related_problem_id = Column(String(36), ForeignKey("sd_problems.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    requester = relationship("User", foreign_keys=[requester_id])
    owner     = relationship("User", foreign_keys=[owner_id])
    approver  = relationship("User", foreign_keys=[approver_id])
    approver_user = relationship("User", foreign_keys=[approved_by])


# ── Major Incident ────────────────────────────────────────────────────────────

class MajorIncidentStatus(str, enum.Enum):
    active   = "active"
    resolved = "resolved"
    closed   = "closed"

class MajorIncident(Base):
    """War-room para incidentes P1/P2. Agrupa tickets, coordina respuesta."""
    __tablename__ = "sd_major_incidents"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    number      = Column(String(20), unique=True, nullable=False)
    title       = Column(String(500), nullable=False)
    status      = Column(Enum(MajorIncidentStatus), default=MajorIncidentStatus.active, index=True)
    severity    = Column(String(10), default="P1")  # P1 | P2

    declared_at   = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at   = Column(DateTime(timezone=True), nullable=True)

    incident_commander_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    communication_lead_id = Column(String(36), ForeignKey("users.id"), nullable=True)

    impact_statement  = Column(Text, nullable=True)
    resolution_summary = Column(Text, nullable=True)
    timeline          = Column(Text, nullable=True)  # JSON: [{time, action, user}]

    # Comunicaciones masivas enviadas
    notifications_sent = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    commander  = relationship("User", foreign_keys=[incident_commander_id])
    comm_lead  = relationship("User", foreign_keys=[communication_lead_id])


# ── Ticket Template (formularios dinámicos por tipo) ─────────────────────────

class TicketTemplate(Base):
    __tablename__ = "sd_ticket_templates"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name        = Column(String(255), nullable=False)
    ticket_type = Column(Enum(TicketType), nullable=False)
    category_id = Column(String(36), ForeignKey("sd_service_categories.id"), nullable=True)

    # JSON: [{field, label, type, required, options}]
    custom_fields = Column(Text, nullable=True)

    default_priority    = Column(Enum(TicketPriority), default=TicketPriority.p3_medium)
    default_group_id    = Column(String(36), ForeignKey("sd_agent_groups.id"), nullable=True)
    default_sla_id      = Column(String(36), ForeignKey("sd_sla_policies.id"), nullable=True)
    auto_assign_to_id   = Column(String(36), ForeignKey("users.id"), nullable=True)

    description_template = Column(Text, nullable=True)  # texto de ayuda para el solicitante
    is_active   = Column(Boolean, default=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

class CannedResponse(Base):
    """Respuestas rápidas predefinidas para agentes de Service Desk."""
    __tablename__ = "sd_canned_responses"
    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title       = Column(String(200), nullable=False)     # Nombre corto
    body        = Column(Text,        nullable=False)      # Texto de la respuesta
    category    = Column(String(100), nullable=True)       # Categoría para agrupar
    shortcut    = Column(String(50),  nullable=True)       # /shortcut para autocompletar
    is_active   = Column(Boolean,     default=True)
    created_by  = Column(String(36),  ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())
    creator     = relationship("User", foreign_keys=[created_by])


# ════════════════════════════════════════════════════════════════════════════
# ITSM MARKET-LEADER EXTENSIONS — Contecflow Service Desk v3
# Adds: On-Call Schedules · Ticket Watchers · Ticket Merge · Auto-Escalation
#       Asset Management (HAM/SAM) · SLA Holiday Calendar
#       Workload-Balanced Assignment · Service Status Page
# ════════════════════════════════════════════════════════════════════════════


# ── On-Call Schedules (PagerDuty-style) ──────────────────────────────────────

class OnCallRotationType(str, enum.Enum):
    weekly   = "weekly"    # cada semana rota el agente
    daily    = "daily"     # cada día rota
    custom   = "custom"    # intervalos definidos manualmente


class OnCallSchedule(Base):
    """Guardia de soporte por grupo. Define quién responde P1/P2 fuera de horario."""
    __tablename__ = "sd_oncall_schedules"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name        = Column(String(255), nullable=False)
    group_id    = Column(String(36), ForeignKey("sd_agent_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    rotation    = Column(Enum(OnCallRotationType), default=OnCallRotationType.weekly)
    timezone    = Column(String(50), default="Europe/Madrid")
    is_active   = Column(Boolean, default=True)
    description = Column(String(255), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    group   = relationship("AgentGroup")
    entries = relationship("OnCallEntry", back_populates="schedule", cascade="all, delete-orphan",
                           order_by="OnCallEntry.start_dt")


class OnCallEntry(Base):
    """Turno individual dentro de un Schedule de guardia."""
    __tablename__ = "sd_oncall_entries"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    schedule_id = Column(String(36), ForeignKey("sd_oncall_schedules.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id     = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    start_dt    = Column(DateTime(timezone=True), nullable=False)
    end_dt      = Column(DateTime(timezone=True), nullable=False)
    notes       = Column(String(255), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    schedule = relationship("OnCallSchedule", back_populates="entries")
    user     = relationship("User", foreign_keys=[user_id])


# ── Ticket Watchers (follow without assignment) ───────────────────────────────

class TicketWatcher(Base):
    """Usuario que sigue un ticket para recibir notificaciones sin ser asignado."""
    __tablename__ = "sd_ticket_watchers"

    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_id  = Column(String(36), ForeignKey("sd_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id    = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    ticket = relationship("Ticket")
    user   = relationship("User", foreign_keys=[user_id])


# ── Ticket Merge Log (duplicate management) ───────────────────────────────────

class TicketMerge(Base):
    """Registro de cuando un ticket se fusiona con otro (duplicado detectado)."""
    __tablename__ = "sd_ticket_merges"

    id             = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    primary_id     = Column(String(36), ForeignKey("sd_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    merged_id      = Column(String(36), ForeignKey("sd_tickets.id", ondelete="CASCADE"), nullable=False)
    reason         = Column(String(500), nullable=True)
    merged_by_user = Column(String(36), ForeignKey("users.id"), nullable=True)
    merged_at      = Column(DateTime(timezone=True), server_default=func.now())

    primary_ticket = relationship("Ticket", foreign_keys=[primary_id])
    merged_ticket  = relationship("Ticket", foreign_keys=[merged_id])
    merged_by      = relationship("User", foreign_keys=[merged_by_user])


# ── Auto-Escalation Rules ─────────────────────────────────────────────────────

class EscalationTrigger(str, enum.Enum):
    sla_at_risk   = "sla_at_risk"    # SLA al 75%
    sla_breached  = "sla_breached"   # SLA roto
    idle_hours    = "idle_hours"     # Sin actividad N horas
    priority      = "priority"       # Prioridad específica sin asignar
    reopened      = "reopened"       # Ticket reabierto


class EscalationAction(str, enum.Enum):
    notify_manager    = "notify_manager"     # notificar al jefe del agente
    notify_group_lead = "notify_group_lead"  # notificar al lead del grupo
    reassign_group    = "reassign_group"     # mover a otro grupo
    elevate_priority  = "elevate_priority"   # subir prioridad
    notify_custom     = "notify_custom"      # enviar a lista custom


class EscalationRule(Base):
    """Regla de escalada automática basada en tiempo o estado del SLA."""
    __tablename__ = "sd_escalation_rules"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name        = Column(String(255), nullable=False)
    is_active   = Column(Boolean, default=True)
    sort_order  = Column(Integer, default=100)

    # Condiciones
    trigger         = Column(Enum(EscalationTrigger), nullable=False)
    applies_to_priority = Column(String(100), nullable=True)   # JSON list of priorities, null = all
    idle_hours_threshold = Column(Float, nullable=True)        # for idle_hours trigger
    group_id        = Column(String(36), ForeignKey("sd_agent_groups.id"), nullable=True)  # solo esta cola

    # Acción
    action          = Column(Enum(EscalationAction), nullable=False)
    target_group_id = Column(String(36), ForeignKey("sd_agent_groups.id"), nullable=True)
    notify_user_ids = Column(Text, nullable=True)              # JSON: [user_id, ...]
    target_priority = Column(String(30), nullable=True)        # for elevate_priority

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    group        = relationship("AgentGroup", foreign_keys=[group_id])
    target_group = relationship("AgentGroup", foreign_keys=[target_group_id])


class EscalationLog(Base):
    """Registro de cada vez que se activó una regla de escalada."""
    __tablename__ = "sd_escalation_logs"

    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    rule_id    = Column(String(36), ForeignKey("sd_escalation_rules.id"), nullable=False, index=True)
    ticket_id  = Column(String(36), ForeignKey("sd_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    action_taken = Column(String(255), nullable=True)
    triggered_at = Column(DateTime(timezone=True), server_default=func.now())

    rule   = relationship("EscalationRule")
    ticket = relationship("Ticket")


# ── SLA Holiday Calendar ──────────────────────────────────────────────────────

class SDSLAHoliday(Base):
    """Festivos en los que el SLA no corre (por política de negocio)."""
    __tablename__ = "sd_sla_holidays"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name        = Column(String(255), nullable=False)
    holiday_date = Column(String(10), nullable=False)   # YYYY-MM-DD
    country     = Column(String(2), nullable=True)      # ISO 3166-1 alpha-2, null = global
    sla_policy_id = Column(String(36), ForeignKey("sd_sla_policies.id", ondelete="CASCADE"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    sla_policy = relationship("SLAPolicy")


# ── Asset Management — HAM/SAM ────────────────────────────────────────────────

class AssetType(str, enum.Enum):
    hardware    = "hardware"    # servidores, PCs, móviles, periféricos
    software    = "software"    # licencias, aplicaciones
    license     = "license"     # licencia de software específica
    consumable  = "consumable"  # fungibles (cartuchos, cables...)
    cloud       = "cloud"       # recursos cloud (VMs, storage, etc.)
    other       = "other"


class AssetStatus(str, enum.Enum):
    in_stock      = "in_stock"      # en almacén
    deployed      = "deployed"      # en uso
    in_repair     = "in_repair"     # en reparación
    retired       = "retired"       # dado de baja
    disposed      = "disposed"      # eliminado / reciclado
    loaned        = "loaned"        # prestado temporalmente
    pending_order = "pending_order" # pedido pero no recibido


class Asset(Base):
    """Activo de IT (hardware o software) con lifecycle completo."""
    __tablename__ = "sd_assets"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code        = Column(String(30), unique=True, nullable=False)   # ASSET-0001
    name        = Column(String(255), nullable=False)
    asset_type  = Column(Enum(AssetType), nullable=False)
    status      = Column(Enum(AssetStatus), default=AssetStatus.in_stock, index=True)

    # Identificación física / software
    serial_number   = Column(String(100), nullable=True, index=True)
    model           = Column(String(255), nullable=True)
    manufacturer    = Column(String(100), nullable=True)
    part_number     = Column(String(100), nullable=True)

    # Licencias de software
    license_key     = Column(String(500), nullable=True)
    license_seats   = Column(Integer, nullable=True)          # número de licencias
    license_used    = Column(Integer, default=0)              # cuántas en uso

    # Fechas del ciclo de vida
    purchase_date   = Column(String(10), nullable=True)       # YYYY-MM-DD
    warranty_expiry = Column(String(10), nullable=True)
    eol_date        = Column(String(10), nullable=True)       # End of Life
    lease_expiry    = Column(String(10), nullable=True)

    # Financiero
    purchase_price  = Column(Float, nullable=True)
    current_value   = Column(Float, nullable=True)
    currency        = Column(String(3), default="EUR")
    po_number       = Column(String(100), nullable=True)
    vendor          = Column(String(100), nullable=True)
    vendor_contract = Column(String(100), nullable=True)

    # Ubicación / Asignación
    location        = Column(String(255), nullable=True)
    assigned_user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    department      = Column(String(100), nullable=True)

    # Vínculo con CMDB
    ci_id           = Column(String(36), ForeignKey("sd_configuration_items.id"), nullable=True)

    # Metadatos
    tags            = Column(String(500), nullable=True)      # comma-separated
    notes           = Column(Text, nullable=True)
    managed_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)

    # Phase 2 — Asset Lifecycle
    depreciation_type = Column(String(20), nullable=True)   # linear|declining|none
    depreciation_rate = Column(Float, nullable=True)        # annual % for declining balance
    next_maintenance_date = Column(String(10), nullable=True)  # YYYY-MM-DD
    maintenance_contract = Column(String(255), nullable=True)

    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())

    assigned_user = relationship("User", foreign_keys=[assigned_user_id])
    managed_by    = relationship("User", foreign_keys=[managed_by_user_id])
    ci            = relationship("ConfigurationItem")
    history       = relationship("AssetHistory", back_populates="asset",
                                 cascade="all, delete-orphan", order_by="AssetHistory.changed_at")


class AssetHistory(Base):
    """Historial de cambios de un activo (asignación, estado, reparaciones...)."""
    __tablename__ = "sd_asset_history"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    asset_id    = Column(String(36), ForeignKey("sd_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    field_name  = Column(String(100), nullable=False)    # status | assigned_user_id | location...
    old_value   = Column(String(500), nullable=True)
    new_value   = Column(String(500), nullable=True)
    changed_by  = Column(String(36), ForeignKey("users.id"), nullable=True)
    note        = Column(String(255), nullable=True)
    changed_at  = Column(DateTime(timezone=True), server_default=func.now())

    asset      = relationship("Asset", back_populates="history")
    changed_by_user = relationship("User", foreign_keys=[changed_by])


# ── Phase 2 — Autonomous Playbooks ──────────────────────────────────────────

class AutonomousPlaybook(Base):
    """Configurable resolution playbooks for the autonomous agent service."""
    __tablename__ = "sd_autonomous_playbooks"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name            = Column(String(255), nullable=False)
    playbook_type   = Column(String(50), nullable=False, index=True)
    description     = Column(Text, nullable=True)
    steps_json      = Column(Text, nullable=True)       # JSON list of step dicts
    conditions_json = Column(Text, nullable=True)       # JSON trigger conditions
    is_active       = Column(Boolean, default=True)
    success_count   = Column(Integer, default=0)
    failure_count   = Column(Integer, default=0)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())


class AutonomousPlaybookExecution(Base):
    """Audit log of every autonomous playbook run."""
    __tablename__ = "sd_autonomous_playbook_executions"

    id               = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_id        = Column(String(36), ForeignKey("sd_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    playbook_type    = Column(String(50), nullable=False)
    status           = Column(String(20), default="success")   # success|failed|skipped
    confidence_score = Column(Float, nullable=True)
    resolution_note  = Column(Text, nullable=True)
    error_message    = Column(Text, nullable=True)
    executed_at      = Column(DateTime(timezone=True), server_default=func.now())
    triggered_by     = Column(String(20), default="celery")    # celery|api|manual

    ticket = relationship("Ticket", foreign_keys=[ticket_id])


# ── Phase 3 — ITSM Scale models ───────────────────────────────────────────────

class ITSMMetricSnapshot(Base):
    """Hourly ITSM KPI snapshot for trend analytics and dashboards."""
    __tablename__ = "sd_itsm_metric_snapshots"

    id                  = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    snapshot_at         = Column(DateTime(timezone=True), nullable=False, index=True)
    period_hours        = Column(Integer, default=24)
    tickets_total       = Column(Integer, default=0)
    tickets_open        = Column(Integer, default=0)
    tickets_resolved    = Column(Integer, default=0)
    sla_compliance_pct  = Column(Float, nullable=True)
    mttr_minutes        = Column(Float, nullable=True)
    fcr_pct             = Column(Float, nullable=True)
    avg_csat            = Column(Float, nullable=True)
    breached_sla        = Column(Integer, default=0)


class ComplianceReport(Base):
    """Persisted ITIL/ISO 20000 compliance report generated periodically."""
    __tablename__ = "sd_compliance_reports"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    generated_at = Column(DateTime(timezone=True), nullable=False, index=True)
    period_days  = Column(Integer, default=30)
    overall_score = Column(Integer, default=0)   # 0-100
    cmm_level    = Column(Integer, default=1)    # 1-5
    report_json  = Column(Text, nullable=True)   # full JSON report


# ServiceItem Phase 3 additions (popularity_score)
# Column added via migrate.py / alembic 033 — referenced defensively via hasattr()


# ── Service Status Page (public health dashboard) ─────────────────────────────

class StatusPageComponentStatus(str, enum.Enum):
    operational          = "operational"
    degraded_performance = "degraded_performance"
    partial_outage       = "partial_outage"
    major_outage         = "major_outage"
    maintenance          = "maintenance"


class StatusPageComponent(Base):
    """Componente visible en la página pública de estado del servicio."""
    __tablename__ = "sd_status_components"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name        = Column(String(255), nullable=False)
    description = Column(String(500), nullable=True)
    group_name  = Column(String(100), nullable=True)     # agrupación (ej: "API", "Frontend")
    sort_order  = Column(Integer, default=0)
    status      = Column(Enum(StatusPageComponentStatus), default=StatusPageComponentStatus.operational)
    is_public   = Column(Boolean, default=True)

    # Vínculo con CI (sincroniza el estado automáticamente)
    ci_id       = Column(String(36), ForeignKey("sd_configuration_items.id"), nullable=True)

    uptime_30d_pct = Column(Float, nullable=True)        # calculado periódicamente
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())

    ci = relationship("ConfigurationItem")
    incidents = relationship("StatusPageIncident", back_populates="component",
                             cascade="all, delete-orphan")


class StatusPageIncident(Base):
    """Incidente publicado en la página de estado (comunicación externa)."""
    __tablename__ = "sd_status_incidents"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    component_id = Column(String(36), ForeignKey("sd_status_components.id", ondelete="CASCADE"), nullable=False, index=True)
    title        = Column(String(500), nullable=False)
    # JSON: [{time, status, message}] — timeline de actualizaciones
    updates      = Column(Text, default="[]")
    status       = Column(String(30), default="investigating")  # investigating|identified|monitoring|resolved
    impact       = Column(Enum(StatusPageComponentStatus), default=StatusPageComponentStatus.partial_outage)
    started_at   = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at  = Column(DateTime(timezone=True), nullable=True)

    # Ticket ITSM vinculado
    ticket_id    = Column(String(36), ForeignKey("sd_tickets.id"), nullable=True)

    component = relationship("StatusPageComponent", back_populates="incidents")
    ticket    = relationship("Ticket")

