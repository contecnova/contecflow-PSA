"""service_desk.problems models — split from the former 1385-LOC god-file."""

from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text, Boolean, Integer, Enum, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.db.base import Base


from app.models.service_desk._enums import MajorIncidentStatus, ProblemStatus, TicketPriority

class Problem(Base):
    __tablename__ = "sd_problems"
    __table_args__ = (UniqueConstraint("organization_id", "number", name="uq_sd_problems_org_number"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    number = Column(String(20), nullable=False)
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
    known_errors    = relationship("KnownError", back_populates="problem", cascade="all, delete-orphan")
    incident_links  = relationship("IncidentToProblem", back_populates="problem", cascade="all, delete-orphan")

class KnownError(Base):
    """KEDB entry — proper relational table for known errors (ITSM-P08).

    A KnownError is promoted from a Problem when a workaround is confirmed and
    the team decides to publish it to the Known Error Database (KEDB).
    """
    __tablename__ = "sd_known_errors"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    problem_id  = Column(String(36), ForeignKey("sd_problems.id", ondelete="CASCADE"), nullable=False, index=True)
    title       = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    workaround  = Column(Text, nullable=True)
    root_cause  = Column(Text, nullable=True)
    rca_type    = Column(String(30), nullable=True)
    # JSON list of CI ids / service names affected
    affects_json = Column(Text, nullable=True)
    category_id  = Column(String(36), ForeignKey("sd_service_categories.id", ondelete="SET NULL"), nullable=True, index=True)
    kb_article_id = Column(String(36), ForeignKey("sd_kb_articles.id", ondelete="SET NULL"), nullable=True)
    published_by  = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    published_at  = Column(DateTime(timezone=True), nullable=True)
    expires_at    = Column(DateTime(timezone=True), nullable=True)
    reviewed_at   = Column(DateTime(timezone=True), nullable=True)
    effectiveness_score = Column(Float, nullable=True)
    is_active   = Column(Boolean, default=True, nullable=False)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())

    problem    = relationship("Problem", back_populates="known_errors")
    publisher  = relationship("User", foreign_keys=[published_by])
    category   = relationship("ServiceCategory", foreign_keys=[category_id])
    kb_article = relationship("KBArticle", foreign_keys=[kb_article_id])
    affected_ticket_links = relationship("KnownErrorTicket", back_populates="known_error", cascade="all, delete-orphan")

class KnownErrorTicket(Base):
    """Formal link: KnownError -> affected Ticket (ITSM-P08 gap closure)."""
    __tablename__ = "sd_known_error_tickets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    known_error_id = Column(String(36), ForeignKey("sd_known_errors.id", ondelete="CASCADE"), nullable=False, index=True)
    ticket_id = Column(String(36), ForeignKey("sd_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    incident_link_id = Column(String(36), ForeignKey("sd_incident_to_problem.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("known_error_id", "ticket_id", name="uq_known_error_ticket"),
    )

    known_error = relationship("KnownError", back_populates="affected_ticket_links")
    ticket = relationship("Ticket", back_populates="known_error_links")
    incident_link = relationship("IncidentToProblem", foreign_keys=[incident_link_id])

class ProblemRcaTemplate(Base):
    """Reusable RCA template definitions stored relationally (ITSM-P08).

    Replaces the hard-coded template dict in rca_wizard_service.py with
    admin-managed, DB-backed templates that can be extended or customised.
    """
    __tablename__ = "sd_problem_rca_templates"

    id            = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    name          = Column(String(255), nullable=False)
    # five_whys | fishbone | itil_standard | custom
    template_type = Column(String(30), nullable=False, index=True)
    # JSON array of {step, label, prompt} objects
    steps_json    = Column(Text, nullable=False)
    description   = Column(Text, nullable=True)
    # True = built-in system template (non-deletable via API)
    is_system   = Column(Boolean, default=False, nullable=False)
    is_active   = Column(Boolean, default=True, nullable=False)
    created_by  = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    creator = relationship("User", foreign_keys=[created_by])

class IncidentToProblem(Base):
    """Rich junction table linking incidents (Tickets) to Problems (ITSM-P08).

    Replaces the bare Ticket.problem_id FK with a proper association table that
    records *who* linked the incident, *when*, whether it was the causal
    incident, and any free-text notes.  The FK on Ticket still exists for
    quick lookups; this table is the canonical record of the relationship.
    """
    __tablename__ = "sd_incident_to_problem"

    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    problem_id = Column(String(36), ForeignKey("sd_problems.id", ondelete="CASCADE"), nullable=False, index=True)
    ticket_id  = Column(String(36), ForeignKey("sd_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    # True = this ticket is considered the primary/causal incident
    is_causal  = Column(Boolean, default=False, nullable=False)
    notes      = Column(Text, nullable=True)
    linked_by  = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    linked_at  = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        # Each (problem, ticket) pair is unique
        UniqueConstraint("problem_id", "ticket_id", name="uq_incident_to_problem"),
    )

    problem    = relationship("Problem", back_populates="incident_links")
    ticket     = relationship("Ticket", foreign_keys=[ticket_id])
    linker     = relationship("User", foreign_keys=[linked_by])

class MajorIncident(Base):
    """War-room para incidentes P1/P2. Agrupa tickets, coordina respuesta."""
    __tablename__ = "sd_major_incidents"
    __table_args__ = (UniqueConstraint("organization_id", "number", name="uq_sd_major_incidents_org_number"),)

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    number      = Column(String(20), nullable=False)
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
    # Auditoria 2026-09. Los tickets que agrupa esta incidencia mayor.
    #
    # `governance_compliance_service` ya estaba escrito contra esta relacion
    # —`MajorIncident.tickets.any(id=t.id)`, detras de un `hasattr`— y como no
    # existia, la comprobacion «P1 sin incidencia mayor» quedaba declarada no
    # evaluable. Con el `major_incident_id` de `Ticket` la relacion existe y
    # esa comprobacion pasa a hacer su trabajo sin tocar una linea de ella.
    tickets = relationship(
        "Ticket", back_populates="major_incident", lazy="selectin")
