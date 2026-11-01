"""
Client Portal models – everything needed for the external client-facing portal.
"""
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text, Boolean, Integer, Enum, Date
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
import uuid
from app.db.base import Base
from app.core.config import settings


# ── Client User ───────────────────────────────────────────────────────────────

# junction table: many-to-many ClientUser ↔ Project
from sqlalchemy import Table
client_user_projects = Table(
    "client_user_projects",
    Base.metadata,
    Column("client_user_id", String(36), ForeignKey("client_users.id", ondelete="CASCADE"), primary_key=True),
    Column("project_id",     String(36), ForeignKey("projects.id",      ondelete="CASCADE"), primary_key=True),
)


class ClientUser(Base):
    """External client contacts with portal access.
    Un ClientUser pertenece a una empresa (Client) y puede tener acceso a múltiples proyectos.
    `project_id` se mantiene como columna legacy/nullable; la relación oficial es via client_user_projects.
    """
    __tablename__ = "client_users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    # Empresa cliente (entidad central) — ahora OPCIONAL para compatibilidad
    client_org_id = Column(String(36), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)
    # Proyecto principal legacy — nullable (usar `projects` M2M)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)

    # Identity
    full_name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    job_title = Column(String(100), nullable=True)
    company = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)

    # Access
    hashed_password = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    can_approve_deliverables = Column(Boolean, default=True)
    can_request_changes = Column(Boolean, default=True)
    can_view_budget = Column(Boolean, default=True)   # Sees budget consumption, not costs
    can_view_team = Column(Boolean, default=False)    # Sees team members
    language = Column(String(10), default=settings.DEFAULT_LANGUAGE)
    avatar_initials = Column(String(5), nullable=True)

    last_login = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    project    = relationship("Project", foreign_keys=[project_id])
    client_org = relationship("Client", foreign_keys=[client_org_id])
    sessions = relationship("ClientSession", back_populates="client", cascade="all, delete-orphan")
    # Multi-project access
    projects   = relationship("Project", secondary=client_user_projects, lazy="select",
                              primaryjoin="ClientUser.id == foreign(client_user_projects.c.client_user_id)",
                              secondaryjoin="Project.id == foreign(client_user_projects.c.project_id)")

    def get_project_ids(self) -> list:
        """Returns all accessible project IDs (M2M union legacy project_id)."""
        ids = []
        seen = set()
        if self.project_id:
            ids.append(self.project_id)
            seen.add(self.project_id)
        for project in (self.projects or []):
            if project.id not in seen:
                ids.append(project.id)
                seen.add(project.id)
        return ids


class ClientSession(Base):
    __tablename__ = "client_sessions"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    client_id = Column(String(36), ForeignKey("client_users.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String(255), nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    client = relationship("ClientUser", back_populates="sessions")


# ── Feature Requests ──────────────────────────────────────────────────────────

class FeatureRequestStatus(str, enum.Enum):
    new = "new"                 # Just submitted
    reviewing = "reviewing"     # PM reviewing
    estimated = "estimated"     # Cost/time estimate provided
    approved = "approved"       # Client approved
    rejected = "rejected"       # Not going ahead
    in_development = "in_development"
    done = "done"


class FeatureRequestPriority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class FeatureRequest(Base):
    """Client-submitted feature/change requests."""
    __tablename__ = "feature_requests"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    code = Column(String(20), nullable=False)  # FR-001
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id = Column(String(36), ForeignKey("client_users.id"), nullable=True)

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    business_justification = Column(Text, nullable=True)
    affected_area = Column(String(100), nullable=True)  # Which part of the system
    priority = Column(Enum(FeatureRequestPriority), default=FeatureRequestPriority.medium)
    status = Column(Enum(FeatureRequestStatus), default=FeatureRequestStatus.new, index=True)

    # PM response
    pm_response = Column(Text, nullable=True)
    estimated_hours = Column(Float, nullable=True)
    estimated_cost = Column(Float, nullable=True)
    estimated_delivery_weeks = Column(Integer, nullable=True)

    # Client decision
    client_approved = Column(Boolean, nullable=True)
    client_approved_at = Column(DateTime(timezone=True), nullable=True)
    client_rejection_reason = Column(Text, nullable=True)

    # Link to internal CR if approved
    change_request_id = Column(String(36), ForeignKey("change_requests.id"), nullable=True)

    submitted_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    project = relationship("Project")
    client = relationship("ClientUser")
    change_request = relationship("ChangeRequest")
    comments = relationship("ClientMessage", back_populates="feature_request",
                            primaryjoin="ClientMessage.feature_request_id == FeatureRequest.id",
                            cascade="all, delete-orphan")


# ── UAT Sessions ──────────────────────────────────────────────────────────────

class UATStatus(str, enum.Enum):
    pending = "pending"         # Waiting for client testing
    in_progress = "in_progress" # Client is testing
    passed = "passed"           # Client approved
    failed = "failed"           # Client rejected with issues
    conditional = "conditional" # Passed with minor remarks


class UATSession(Base):
    """UAT test sessions linked to deliverables."""
    __tablename__ = "uat_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    code = Column(String(20), nullable=False)  # UAT-001
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    deliverable_id = Column(String(36), ForeignKey("deliverables.id"), nullable=True)

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    test_environment = Column(String(255), nullable=True)  # URL/env where to test
    test_credentials = Column(String(255), nullable=True)  # Access info
    test_guide_url = Column(String(500), nullable=True)

    status = Column(Enum(UATStatus, name='uat_session_status'), default=UATStatus.pending, index=True)

    # Dates
    available_from = Column(Date, nullable=True)
    deadline = Column(Date, nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Client result
    client_result = Column(Enum(UATStatus, name='uat_session_status'), nullable=True)
    client_notes = Column(Text, nullable=True)
    client_signed_by = Column(String(36), ForeignKey("client_users.id"), nullable=True)
    client_signed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    project = relationship("Project")
    deliverable = relationship("Deliverable")
    signer = relationship("ClientUser", foreign_keys=[client_signed_by])
    test_cases = relationship("UATTestCase", back_populates="session", cascade="all, delete-orphan")
    issues = relationship("UATIssue", back_populates="session", cascade="all, delete-orphan")


class UATTestCase(Base):
    """Individual test cases within a UAT session."""
    __tablename__ = "uat_test_cases"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    session_id = Column(String(36), ForeignKey("uat_sessions.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    steps = Column(Text, nullable=True)
    expected_result = Column(Text, nullable=True)
    actual_result = Column(Text, nullable=True)
    status = Column(String(20), default="pending")  # pending | passed | failed | skipped
    notes = Column(Text, nullable=True)
    order = Column(Integer, default=0)
    tested_at = Column(DateTime(timezone=True), nullable=True)

    session = relationship("UATSession", back_populates="test_cases")


class UATIssue(Base):
    """Issues/bugs reported during UAT."""
    __tablename__ = "uat_issues"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    session_id = Column(String(36), ForeignKey("uat_sessions.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    severity = Column(String(20), default="medium")  # low | medium | high | blocker
    status = Column(String(20), default="open")       # open | fixed | wontfix | deferred
    reported_by = Column(String(36), ForeignKey("client_users.id"), nullable=True)
    steps_to_reproduce = Column(Text, nullable=True)
    screenshot_url = Column(String(500), nullable=True)
    fixed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("UATSession", back_populates="issues")
    reporter = relationship("ClientUser", foreign_keys=[reported_by])


# ── Messaging ─────────────────────────────────────────────────────────────────

class ClientMessage(Base):
    """Threaded messages between client and team."""
    __tablename__ = "client_messages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)

    # Context – message can be linked to different entities
    feature_request_id = Column(String(36), ForeignKey("feature_requests.id"), nullable=True)
    uat_session_id = Column(String(36), ForeignKey("uat_sessions.id"), nullable=True)
    thread_id = Column(String(36), nullable=True, index=True)  # Groups messages in a thread
    parent_id = Column(String(36), ForeignKey("client_messages.id"), nullable=True)

    subject = Column(String(255), nullable=True)  # Only on first message in thread
    body = Column(Text, nullable=False)
    is_internal = Column(Boolean, default=False)   # Internal team notes not visible to client

    # Sender: either client or internal user
    sender_client_id = Column(String(36), ForeignKey("client_users.id"), nullable=True)
    sender_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)

    is_read_by_client = Column(Boolean, default=False)
    is_read_by_team = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    project = relationship("Project")
    feature_request = relationship("FeatureRequest", back_populates="comments",
                                   foreign_keys=[feature_request_id])
    sender_client = relationship("ClientUser", foreign_keys=[sender_client_id])
    sender_user = relationship("User", foreign_keys=[sender_user_id])
    replies = relationship("ClientMessage", foreign_keys=[parent_id])


# ── Satisfaction Surveys ──────────────────────────────────────────────────────

class SurveyStatus(str, enum.Enum):
    pending = "pending"
    completed = "completed"
    expired = "expired"


class ClientSurvey(Base):
    """Satisfaction surveys sent after milestones."""
    __tablename__ = "client_surveys"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    client_id = Column(String(36), ForeignKey("client_users.id"), nullable=True)
    milestone_id = Column(String(36), ForeignKey("project_milestones.id"), nullable=True)

    title = Column(String(255), nullable=False)
    status = Column(Enum(SurveyStatus), default=SurveyStatus.pending)

    # Scores 1-5
    overall_satisfaction = Column(Integer, nullable=True)
    communication_score = Column(Integer, nullable=True)
    quality_score = Column(Integer, nullable=True)
    deadline_score = Column(Integer, nullable=True)
    nps_score = Column(Integer, nullable=True)  # 0-10, Net Promoter Score

    comments = Column(Text, nullable=True)
    would_recommend = Column(Boolean, nullable=True)

    sent_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    project = relationship("Project")
    client = relationship("ClientUser")
    milestone = relationship("ProjectMilestone")


# ── Client Document Library ───────────────────────────────────────────────────

class ClientDocument(Base):
    """Documents shared with the client (deliverables, contracts, meeting notes)."""
    __tablename__ = "client_documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), default="general")  # contract | deliverable | meeting_notes | report | other
    file_url = Column(String(500), nullable=True)
    file_name = Column(String(255), nullable=True)
    file_size_kb = Column(Integer, nullable=True)

    is_visible_to_client = Column(Boolean, default=True)
    requires_signature   = Column(Boolean, default=False)
    signed_by_client     = Column(Boolean, default=False)
    signed_at            = Column(DateTime(timezone=True), nullable=True)
    signed_by_name       = Column(String(255), nullable=True)   # nombre del firmante
    signed_by_job_title  = Column(String(255), nullable=True)   # cargo del firmante
    signature_ip         = Column(String(64),  nullable=True)   # IP como evidencia
    signed_pdf_path      = Column(String(500), nullable=True)   # ruta al PDF firmado

    uploaded_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    project = relationship("Project")
    uploader = relationship("User", foreign_keys=[uploaded_by])
