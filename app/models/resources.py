from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text, Date, Boolean, Integer, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
import uuid
from app.db.base import Base


# ── Skills & Competencies ─────────────────────────────────────────────────────

class SkillLevel(str, enum.Enum):
    basic = "basic"           # 1 - Básico
    intermediate = "intermediate"  # 2 - Intermedio
    advanced = "advanced"     # 3 - Avanzado
    expert = "expert"         # 4 - Experto


class SkillCategory(str, enum.Enum):
    technical = "technical"
    language = "language"
    methodology = "methodology"
    tool = "tool"
    soft = "soft"
    certification = "certification"


class Skill(Base):
    """Skill/competency catalog."""
    __tablename__ = "skills"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    name = Column(String(100), unique=True, nullable=False)
    category = Column(Enum(SkillCategory), nullable=False)
    description = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user_skills = relationship("UserSkill", back_populates="skill", cascade="all, delete-orphan")


class UserSkill(Base):
    """User's skill with level and years of experience."""
    __tablename__ = "user_skills"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_id = Column(String(36), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    level = Column(Enum(SkillLevel), nullable=False)
    years_experience = Column(Float, nullable=True)
    certified = Column(Boolean, default=False)
    cert_name = Column(String(255), nullable=True)
    cert_expiry = Column(Date, nullable=True)
    notes = Column(String(255), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", foreign_keys=[user_id])
    skill = relationship("Skill", back_populates="user_skills")


class SkillHistory(Base):
    """Historial de cambios de nivel por skill de un usuario."""
    __tablename__ = "skill_history"
    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    user_id     = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_id    = Column(String(36), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    old_level   = Column(Enum(SkillLevel), nullable=True)
    new_level   = Column(Enum(SkillLevel), nullable=False)
    notes       = Column(String(255), nullable=True)
    recorded_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now())
    user        = relationship("User", foreign_keys=[user_id])
    skill       = relationship("Skill", foreign_keys=[skill_id])
    recorder    = relationship("User", foreign_keys=[recorded_by])

# ── Absences & Vacations ──────────────────────────────────────────────────────

class AbsenceType(str, enum.Enum):
    vacation = "vacation"
    sick = "sick"
    personal = "personal"
    training = "training"
    maternity = "maternity"
    paternity = "paternity"
    other = "other"


class AbsenceStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"


class Absence(Base):
    """Vacation and absence requests."""
    __tablename__ = "absences"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(Enum(AbsenceType), nullable=False)
    status = Column(Enum(AbsenceStatus), default=AbsenceStatus.pending, nullable=False, index=True)
    is_active = Column(Boolean, default=True)

    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    working_days = Column(Float, nullable=True)  # Calculated

    reason = Column(Text, nullable=True)

    # Approval
    approved_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", foreign_keys=[user_id])
    approver = relationship("User", foreign_keys=[approved_by])


# ── Change Control ────────────────────────────────────────────────────────────

class ChangeRequestStatus(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"
    under_review = "under_review"
    approved = "approved"
    rejected = "rejected"
    implemented = "implemented"


class ChangeRequestImpact(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class ChangeRequest(Base):
    """Scope change requests with approval workflow."""
    __tablename__ = "change_requests"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    code = Column(String(20), nullable=False)  # CR-001
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    justification = Column(Text, nullable=True)

    # Impact assessment
    impact = Column(Enum(ChangeRequestImpact), default=ChangeRequestImpact.medium)
    cost_impact = Column(Float, nullable=True)        # € additional cost
    schedule_impact_days = Column(Integer, nullable=True)
    scope_impact = Column(Text, nullable=True)        # Description of scope change

    status = Column(Enum(ChangeRequestStatus), default=ChangeRequestStatus.draft, nullable=False, index=True)
    is_active = Column(Boolean, default=True)

    # People
    requested_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    reviewed_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    approved_by = Column(String(36), ForeignKey("users.id"), nullable=True)

    # Dates
    submitted_at = Column(Date, nullable=True)
    reviewed_at = Column(Date, nullable=True)
    approved_at = Column(Date, nullable=True)
    implemented_at = Column(Date, nullable=True)

    # Resolution
    resolution_notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    project = relationship("Project")
    requester = relationship("User", foreign_keys=[requested_by])
    reviewer = relationship("User", foreign_keys=[reviewed_by])
    approver_user = relationship("User", foreign_keys=[approved_by])


# ── Deliverables ──────────────────────────────────────────────────────────────

class DeliverableStatus(str, enum.Enum):
    planned = "planned"
    in_progress = "in_progress"
    in_review = "in_review"
    delivered = "delivered"
    accepted = "accepted"
    rejected = "rejected"


class Deliverable(Base):
    """Formal project deliverables with client acceptance."""
    __tablename__ = "deliverables"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    code = Column(String(20), nullable=False)  # DEL-001
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    phase_id = Column(String(36), ForeignKey("project_phases.id"), nullable=True)

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    format = Column(String(100), nullable=True)  # "PDF report", "Source code", "Prototype"

    status = Column(Enum(DeliverableStatus), default=DeliverableStatus.planned, nullable=False, index=True)

    # Porcentaje de facturacion asociado a la aceptacion de este entregable.
    #
    # Auditoria 2026-08 (hallazgo 22): la plantilla de proyecto lo declara
    # —`TemplateDeliverable.billing_pct`, FLOAT— y `advanced_config_service`
    # lo pasaba al construir el entregable, pero la columna **no existia**.
    # SQLAlchemy responde `TypeError` a una palabra clave que no es columna,
    # asi que **aplicar una plantilla de proyecto fallaba** en cuanto la
    # plantilla traia un entregable. Se anade la columna en vez de quitar el
    # dato: la plantilla lo declara porque el dato existe en el dominio, y
    # tirarlo dejaria la plantilla a medias.
    billing_pct = Column(Float, nullable=True)

    # Dates
    planned_date = Column(Date, nullable=True)
    delivered_date = Column(Date, nullable=True)
    accepted_date = Column(Date, nullable=True)

    # Ownership
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=True)  # Responsible

    # Client acceptance
    client_contact = Column(String(255), nullable=True)
    acceptance_criteria = Column(Text, nullable=True)
    rejection_reason = Column(Text, nullable=True)

    # Billing link
    milestone_id = Column(String(36), ForeignKey("project_milestones.id"), nullable=True)

    # Document
    document_url = Column(String(500), nullable=True)

    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True, nullable=False)  # Soft delete
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    project = relationship("Project")
    owner = relationship("User", foreign_keys=[owner_id])


# ── Resource Planning ──────────────────────────────────────────────────────

class ResourceAlertType(str, enum.Enum):
    overload_warning = "overload_warning"  # User load > 100%
    skill_gap = "skill_gap"                # Project requires skill not available
    no_utilization = "no_utilization"      # User has 0% allocation 2+ weeks


class ResourceAlert(Base):
    """Alerts for resource issues (overload, skill gaps, etc)."""
    __tablename__ = "resource_alerts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    alert_type = Column(Enum(ResourceAlertType), nullable=False, index=True)

    # Alert context (e.g., week number, project_id, etc.)
    context = Column(Text, nullable=True)  # JSON with additional context
    severity = Column(String(20), default="warning")  # info | warning | critical

    # Lifecycle
    triggered_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    acknowledger = relationship("User", foreign_keys=[acknowledged_by])


class ResourceUtilizationSnapshot(Base):
    """Weekly snapshot of resource utilization (planned vs actual)."""
    __tablename__ = "resource_utilization_snapshots"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Week identifier (ISO week number, e.g., "2024-W15")
    week_iso = Column(String(10), nullable=False, index=True)

    # Utilization data (calculated from CapacityPlan + Imputations)
    planned_hours = Column(Float, default=0.0)     # From CapacityPlan
    actual_hours = Column(Float, default=0.0)      # From Imputation sum
    billable_hours = Column(Float, default=0.0)    # From Imputation sum (is_billable=True)

    # Calculated metrics
    utilization_pct = Column(Float, nullable=True)  # (actual / planned) * 100
    billable_pct = Column(Float, nullable=True)     # (billable / actual) * 100

    # Created at end-of-day
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
