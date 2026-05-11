from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text, Date, Integer, Enum, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
import uuid
from app.db.base import Base


# ── Pipeline Stage Configuration ──────────────────────────────────────────────

class PipelineStageConfig(Base):
    """Configurable pipeline stages — overrides the default OpportunityStage enum per org."""
    __tablename__ = "pipeline_stage_configs"

    id            = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    stage_key     = Column(String(50), nullable=False, index=True)  # slug-like key
    label         = Column(String(100), nullable=False)
    description   = Column(Text, nullable=True)
    color         = Column(String(7), default="#6B7280")  # hex colour for kanban column
    order         = Column(Integer, default=0)
    probability_default = Column(Float, default=50)        # default win probability for this stage
    is_terminal   = Column(Boolean, default=False)         # won/lost/cancelled
    is_won        = Column(Boolean, default=False)
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())


# ── Pipeline / Opportunities ──────────────────────────────────────────────────

class OpportunityStage(str, enum.Enum):
    lead = "lead"                   # Initial contact
    qualification = "qualification" # Qualified lead
    proposal = "proposal"           # Proposal sent
    negotiation = "negotiation"     # Negotiating
    won = "won"                     # Won
    lost = "lost"                   # Lost
    cancelled = "cancelled"         # Cancelled


class Opportunity(Base):
    __tablename__ = "opportunities"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(20), unique=True, nullable=False)  # OPP-001
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Client
    client_name = Column(String(255), nullable=False)
    client_id   = Column(String(36), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)
    contact_name = Column(String(255), nullable=True)
    contact_email = Column(String(255), nullable=True)

    # Pipeline
    stage = Column(Enum(OpportunityStage), default=OpportunityStage.lead, nullable=False, index=True)
    probability = Column(Float, default=50)           # 0-100%
    expected_revenue = Column(Float, nullable=True)   # €
    expected_margin_pct = Column(Float, nullable=True) # %
    expected_hours = Column(Float, nullable=True)

    # Dates
    expected_close_date = Column(Date, nullable=True)
    expected_start_date = Column(Date, nullable=True)
    expected_duration_weeks = Column(Integer, nullable=True)

    # Assignment
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    team_required = Column(Text, nullable=True)  # JSON description of team needed

    # Billing details (used on convert → RevenueContract)
    hourly_rate     = Column(Float, nullable=True)
    contract_type   = Column(String(30), nullable=True)   # fixed_price | time_material | retainer | hourly_bag

    # Link to project if won
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True)

    # Proposal / SOW tracking
    proposal_template_id  = Column(String(36), ForeignKey("proposal_templates.id", ondelete="SET NULL"), nullable=True)
    proposal_content      = Column(Text, nullable=True)              # rendered Markdown
    proposal_generated_at = Column(DateTime(timezone=True), nullable=True)
    proposal_sent_at      = Column(DateTime(timezone=True), nullable=True)

    # Notes
    notes = Column(Text, nullable=True)
    lost_reason = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    owner = relationship("User", foreign_keys=[owner_id])
    project = relationship("Project", foreign_keys=[project_id])
    activities = relationship("OpportunityActivity", back_populates="opportunity", cascade="all, delete-orphan", order_by="OpportunityActivity.created_at.desc()")
    proposal_template = relationship("ProposalTemplate", foreign_keys=[proposal_template_id])


class OpportunityActivity(Base):
    __tablename__ = "opportunity_activities"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    opportunity_id = Column(String(36), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    type = Column(String(30), default="note")  # note | call | meeting | email | stage_change
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    opportunity = relationship("Opportunity", back_populates="activities")
    user = relationship("User", foreign_keys=[user_id])


# ── Contracts ─────────────────────────────────────────────────────────────────

class ContractStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    expired = "expired"
    cancelled = "cancelled"


class ContractType(str, enum.Enum):
    fixed_price = "fixed_price"
    time_material = "time_material"
    retainer = "retainer"
    hourly_bag = "hourly_bag"


class Contract(Base):
    __tablename__ = "contracts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(30), unique=True, nullable=False)  # CTR-001
    name = Column(String(255), nullable=False)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)

    # Client
    client_name = Column(String(255), nullable=False)
    client_id   = Column(String(36), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)
    client_contact = Column(String(255), nullable=True)

    # Contract terms
    contract_type = Column(Enum(ContractType), nullable=False)
    status = Column(Enum(ContractStatus), default=ContractStatus.draft, nullable=False, index=True)
    is_active = Column(Boolean, default=True)
    total_amount = Column(Float, nullable=True)          # € total
    hourly_rate = Column(Float, nullable=True)           # For T&M
    hours_bag = Column(Float, nullable=True)             # For hourly bag
    hours_used = Column(Float, default=0)                # Tracked automatically
    monthly_retainer = Column(Float, nullable=True)      # For retainer

    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    signed_date = Column(Date, nullable=True)

    # Documents
    document_url = Column(String(500), nullable=True)
    notes = Column(Text, nullable=True)
    payment_terms = Column(String(255), nullable=True)   # "30 days", "milestone"
    sla_policy_id = Column(String(36), ForeignKey("sd_sla_policies.id"), nullable=True)

    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    project = relationship("Project")
    creator = relationship("User", foreign_keys=[created_by])
    sla_policy = relationship("SLAPolicy", foreign_keys=[sla_policy_id])
    work_orders = relationship("WorkOrder", back_populates="contract", cascade="all, delete-orphan")


class WorkOrder(Base):
    __tablename__ = "work_orders"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(30), unique=True, nullable=False)  # WO-001
    contract_id = Column(String(36), ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True)

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    amount = Column(Float, nullable=True)
    hours = Column(Float, nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    status = Column(String(20), default="open")  # open | in_progress | completed | invoiced

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    contract = relationship("Contract", back_populates="work_orders")
    project = relationship("Project")


# ── Risk Register ─────────────────────────────────────────────────────────────

class RiskProbability(str, enum.Enum):
    very_low = "very_low"    # <10%
    low = "low"              # 10-30%
    medium = "medium"        # 30-60%
    high = "high"            # 60-80%
    very_high = "very_high"  # >80%


class RiskImpact(str, enum.Enum):
    negligible = "negligible"
    minor = "minor"
    moderate = "moderate"
    major = "major"
    critical = "critical"


class RiskStatus(str, enum.Enum):
    identified = "identified"
    analyzing = "analyzing"
    mitigating = "mitigating"
    monitoring = "monitoring"
    closed = "closed"
    materialized = "materialized"


class Risk(Base):
    __tablename__ = "risks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(20), nullable=False)  # RSK-001 (per project)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=True)  # technical | financial | schedule | resource | external

    probability = Column(Enum(RiskProbability), nullable=False)
    impact = Column(Enum(RiskImpact), nullable=False)
    risk_score = Column(Float, nullable=True)  # probability_num × impact_num

    status = Column(Enum(RiskStatus), default=RiskStatus.identified, nullable=False, index=True)
    is_active = Column(Boolean, default=True)

    # Response
    mitigation_plan = Column(Text, nullable=True)
    contingency_plan = Column(Text, nullable=True)
    response_type = Column(String(20), nullable=True)  # avoid | mitigate | transfer | accept

    # People
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    identified_by = Column(String(36), ForeignKey("users.id"), nullable=True)

    # Dates
    identified_date = Column(Date, server_default=func.current_date())
    review_date = Column(Date, nullable=True)
    closed_date = Column(Date, nullable=True)

    # Financial impact estimate
    cost_impact_min = Column(Float, nullable=True)
    cost_impact_max = Column(Float, nullable=True)
    schedule_impact_days = Column(Integer, nullable=True)

    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    project = relationship("Project")
    owner = relationship("User", foreign_keys=[owner_id])
    identifier = relationship("User", foreign_keys=[identified_by])


# ── ProposalTemplate ───────────────────────────────────────────────────────────

class ProposalTemplate(Base):
    """
    Reusable SOW/proposal template with {{variable}} placeholders.

    Supported variables:
      {{client_name}}, {{opportunity_name}}, {{expected_revenue}},
      {{expected_hours}}, {{start_date}}, {{duration_weeks}},
      {{owner_name}}, {{description}}, {{today}}
    """
    __tablename__ = "proposal_templates"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name            = Column(String(255), nullable=False)
    description     = Column(Text, nullable=True)
    # fixed_price | time_material | retainer | hourly_bag — hints for UI
    contract_type   = Column(String(30), nullable=True)
    # Markdown content with {{variable}} placeholders
    content         = Column(Text, nullable=False, default="")
    is_active       = Column(Boolean, nullable=False, default=True)
    created_by      = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at      = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
