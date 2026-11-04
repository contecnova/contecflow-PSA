"""
v12 models:
  - SLABreachLog  : Immutable SLA breach events
  - AutomationWorkflow / WorkflowStep / WorkflowExecution: multi-step workflows
  - ImportJob     : Bulk CSV/Excel import tracking
  - Invoice / InvoiceLine : Basic invoicing from timesheets
  - ReportDefinition / ScheduledReport: saved + scheduled reports
  - ResourceMatch : SmartMatch recommendations cache
"""
from sqlalchemy import (
    Column, String, Float, DateTime, ForeignKey, Text,
    Boolean, Integer, Enum, Date
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.money import Money
import enum
import uuid
from app.db.base import Base
from app.core.config import settings


# ── SLA Breach Log ────────────────────────────────────────────────────────────

class SLABreachLog(Base):
    """Immutable record of every SLA breach event."""
    __tablename__ = "sla_breach_logs"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    ticket_id   = Column(String(36), ForeignKey("sd_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    breach_type = Column(String(20), nullable=False)  # response | resolution
    sla_due_at  = Column(DateTime(timezone=True), nullable=False)
    breached_at = Column(DateTime(timezone=True), server_default=func.now())
    breach_minutes = Column(Integer, nullable=True)   # How late
    agent_id    = Column(String(36), ForeignKey("users.id"), nullable=True)
    group_id    = Column(String(36), ForeignKey("sd_agent_groups.id"), nullable=True)
    priority    = Column(String(20), nullable=True)
    category    = Column(String(100), nullable=True)

    ticket = relationship("Ticket")
    agent  = relationship("User", foreign_keys=[agent_id])


# ── Automation Workflows (multi-step) ─────────────────────────────────────────

class WorkflowStatus(str, enum.Enum):
    draft   = "draft"
    active  = "active"
    paused  = "paused"
    archived = "archived"


class StepType(str, enum.Enum):
    action    = "action"      # Execute an action
    condition = "condition"   # Branch: yes/no
    wait      = "wait"        # Wait N hours/days
    webhook   = "webhook"     # Call external URL
    notify    = "notify"      # Send notification


class AutomationWorkflow(Base):
    """Multi-step workflow with branching, waits and conditions."""
    __tablename__ = "automation_workflows"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    name        = Column(String(255), nullable=False)
    description = Column(String(500), nullable=True)
    project_id  = Column(String(36), ForeignKey("projects.id"), nullable=True)
    is_global   = Column(Boolean, default=False)
    status      = Column(Enum(WorkflowStatus), default=WorkflowStatus.draft, index=True)

    # Entry trigger (same as automation rules)
    trigger_type       = Column(String(100), nullable=False, index=True)
    trigger_conditions = Column(Text, nullable=True)   # JSON

    # Stats
    run_count     = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    error_count   = Column(Integer, default=0)
    last_run_at   = Column(DateTime(timezone=True), nullable=True)

    created_by  = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())

    steps       = relationship("WorkflowStep", back_populates="workflow",
                               cascade="all, delete-orphan",
                               order_by="WorkflowStep.order")
    executions  = relationship("WorkflowExecution", back_populates="workflow",
                               cascade="all, delete-orphan",
                               order_by="WorkflowExecution.started_at.desc()")
    project     = relationship("Project")
    creator     = relationship("User", foreign_keys=[created_by])


class WorkflowStep(Base):
    """One step in a multi-step workflow."""
    __tablename__ = "workflow_steps"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    workflow_id  = Column(String(36), ForeignKey("automation_workflows.id", ondelete="CASCADE"), nullable=False, index=True)
    order        = Column(Integer, nullable=False, default=0)
    step_type    = Column(Enum(StepType), nullable=False)
    name         = Column(String(255), nullable=True)
    config       = Column(Text, nullable=False)       # JSON: action params, condition, wait duration
    # Branching
    next_step_yes = Column(String(36), nullable=True) # Step ID if condition true / after action
    next_step_no  = Column(String(36), nullable=True) # Step ID if condition false

    workflow = relationship("AutomationWorkflow", back_populates="steps")


class WorkflowExecution(Base):
    """Full execution log for a workflow instance."""
    __tablename__ = "workflow_executions"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    workflow_id  = Column(String(36), ForeignKey("automation_workflows.id", ondelete="CASCADE"), nullable=False, index=True)
    trigger_context = Column(Text, nullable=True)  # JSON
    status       = Column(String(20), default="running")   # running | completed | failed | waiting
    current_step = Column(Integer, default=0)
    steps_log    = Column(Text, nullable=True)             # JSON array of step results
    error        = Column(String(500), nullable=True)
    started_at   = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    wait_until   = Column(DateTime(timezone=True), nullable=True)

    workflow = relationship("AutomationWorkflow", back_populates="executions")


# ── Import Jobs ───────────────────────────────────────────────────────────────

class ImportStatus(str, enum.Enum):
    pending    = "pending"
    processing = "processing"
    completed  = "completed"
    failed     = "failed"
    partial    = "partial"


class ImportJob(Base):
    """Tracks bulk import progress."""
    __tablename__ = "import_jobs"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    entity_type  = Column(String(50), nullable=False, index=True)  # projects|tasks|users|imputations|expenses
    filename     = Column(String(255), nullable=True)
    status       = Column(Enum(ImportStatus), default=ImportStatus.pending, index=True)
    total_rows   = Column(Integer, default=0)
    processed    = Column(Integer, default=0)
    succeeded    = Column(Integer, default=0)
    failed_rows  = Column(Integer, default=0)
    errors       = Column(Text, nullable=True)    # JSON array of {row, field, error}
    warnings     = Column(Text, nullable=True)    # JSON array
    result_data  = Column(Text, nullable=True)    # JSON: created IDs
    created_by   = Column(String(36), ForeignKey("users.id"), nullable=True)
    started_at   = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    creator = relationship("User", foreign_keys=[created_by])


# ── Invoicing ─────────────────────────────────────────────────────────────────

class InvoiceStatus(str, enum.Enum):
    draft    = "draft"
    sent     = "sent"
    paid     = "paid"
    overdue  = "overdue"
    cancelled = "cancelled"


class Invoice(Base):
    """Client invoice generated from timesheets/expenses/milestones."""
    __tablename__ = "invoices"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    number      = Column(String(30), nullable=False, unique=True)   # INV-2025-001
    project_id  = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    client_id   = Column(String(36), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)
    contract_id = Column(String(36), ForeignKey("contracts.id"), nullable=True)

    # Client info (snapshot)
    client_name    = Column(String(255), nullable=True)
    client_address = Column(Text, nullable=True)
    client_vat     = Column(String(50), nullable=True)
    client_email   = Column(String(255), nullable=True)

    # Amounts
    subtotal    = Column(Money, default=0)
    tax_rate    = Column(Float, default=settings.DEFAULT_TAX_RATE)    # % IVA (ratio, not money)
    tax_amount  = Column(Money, default=0)
    total       = Column(Money, default=0)
    currency    = Column(String(3), default=settings.DEFAULT_CURRENCY)

    # Dates
    issue_date  = Column(Date, nullable=False)
    due_date    = Column(Date, nullable=True)
    paid_date   = Column(Date, nullable=True)

    status      = Column(Enum(InvoiceStatus), default=InvoiceStatus.draft, index=True)
    notes       = Column(Text, nullable=True)
    internal_notes = Column(Text, nullable=True)
    # Decision del cliente en el portal: None, approved o rejected (auditoria 2026-11).
    client_approval_status = Column(String(20), nullable=True)
    po_reference = Column(String(100), nullable=True)

    # Period
    period_from = Column(Date, nullable=True)
    period_to   = Column(Date, nullable=True)

    created_by  = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())
    # Stripe payment gateway fields (v23.8)
    stripe_payment_intent_id = Column(String(255), nullable=True, index=True)
    stripe_payment_link_url  = Column(String(500), nullable=True)
    stripe_payment_link_id   = Column(String(255), nullable=True)
    stripe_paid_at           = Column(DateTime(timezone=True), nullable=True)

    project  = relationship("Project")
    contract = relationship("Contract")
    creator  = relationship("User", foreign_keys=[created_by])
    lines    = relationship("InvoiceLine", back_populates="invoice",
                            cascade="all, delete-orphan",
                            order_by="InvoiceLine.order")


class InvoiceLine(Base):
    """Single line item on an invoice."""
    __tablename__ = "invoice_lines"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    invoice_id  = Column(String(36), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    order       = Column(Integer, default=0)
    description = Column(String(500), nullable=False)
    quantity    = Column(Float, default=1)  # count, not money
    unit        = Column(String(20), default="h")   # h, día, unidad, servicio
    unit_price  = Column(Money, nullable=False)
    discount_pct = Column(Float, default=0)  # % ratio, not money
    amount      = Column(Money, nullable=False)     # qty * price * (1 - discount)

    # Source reference
    source_type  = Column(String(20), nullable=True)   # timesheet | expense | milestone | manual
    source_ids   = Column(Text, nullable=True)         # JSON array of source IDs

    invoice = relationship("Invoice", back_populates="lines")


# ── Report Definitions ────────────────────────────────────────────────────────

class ReportDefinition(Base):
    """Saved report configuration (builder output)."""
    __tablename__ = "report_definitions"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    name        = Column(String(255), nullable=False)
    description = Column(String(500), nullable=True)
    category    = Column(String(50), nullable=True)    # financial | utilization | delivery | itsm
    icon        = Column(String(10), default="📊")
    is_public   = Column(Boolean, default=False)       # visible to all managers
    is_system   = Column(Boolean, default=False)       # built-in, not deletable

    # Config
    data_source = Column(String(100), nullable=False)  # timesheets|projects|tickets|expenses...
    filters     = Column(Text, nullable=True)          # JSON
    columns     = Column(Text, nullable=True)          # JSON array of {field, label, type, aggregate}
    group_by    = Column(String(100), nullable=True)
    sort_by     = Column(String(100), nullable=True)
    sort_dir    = Column(String(4), default="desc")
    chart_type  = Column(String(30), nullable=True)    # bar|line|pie|table
    chart_x     = Column(String(100), nullable=True)
    chart_y     = Column(String(100), nullable=True)

    # Schedule
    schedule_cron   = Column(String(50), nullable=True)    # cron expression
    schedule_emails = Column(Text, nullable=True)          # JSON array of emails

    created_by  = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())

    creator = relationship("User", foreign_keys=[created_by])


# ── Scheduled Reports (persistentes) ──────────────────────────────────────────
class ScheduledReport(Base):
    __tablename__ = "scheduled_reports"
    id            = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    name          = Column(String(255), nullable=False)
    metric        = Column(String(100))           # métrca de analytics (hours_by_month, etc.)
    frequency     = Column(String(20), default="weekly")  # daily | weekly | monthly
    recipients    = Column(Text, default="[]")    # JSON array de emails
    is_active     = Column(Boolean, default=True)
    include_pdf   = Column(Boolean, default=True)
    filters_json  = Column(Text, default="{}")    # JSON: project_id, date_range, etc.
    last_run_at   = Column(DateTime(timezone=True), nullable=True)
    next_run_at   = Column(DateTime(timezone=True), nullable=True)
    created_by    = Column(String(36))
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    # ── BI Report extensions ──────────────────────────────────────────────────
    report_type       = Column(String(50), default="custom")
    # executive_summary | utilization | pipeline | portfolio | custom
    include_narrative = Column(Boolean, default=False)   # embed AI narrative in PDF
    day_of_week       = Column(Integer, nullable=True)   # 0=Mon … 6=Sun (weekly reports)
    day_of_month      = Column(Integer, nullable=True)   # 1-31 (monthly reports)
    send_hour         = Column(Integer, default=8)       # UTC hour to send (0-23)
    recipients_extra  = Column(Text, default="[]")       # JSON extra emails (CC)
    slack_webhook     = Column(String(500), nullable=True)  # Slack incoming webhook URL
    last_status       = Column(String(20), nullable=True)   # success | error
    last_error        = Column(Text, nullable=True)          # last error message


# ── Approval Workflows — Multi-nivel configurables ─────────────────────────────
class ApprovalGroup(Base):
    """Grupo reutilizable de aprobadores para asignar a pasos."""
    __tablename__ = "approval_groups"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    name        = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    member_ids  = Column(Text, nullable=False, default="[]")  # JSON list of user IDs
    created_by  = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    creator = relationship("User", foreign_keys=[created_by])


class ApprovalWorkflow(Base):
    """Flujo de aprobación configurable con N niveles para timesheets, gastos, cambios."""
    __tablename__ = "approval_workflows"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    name        = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    entity_type = Column(String(50), nullable=False)
    is_active   = Column(Boolean, default=True)
    is_default  = Column(Boolean, default=False)
    # Condiciones de activación (JSON): {"amount_gt": 1000, "department": "IT"}
    trigger_conditions = Column(Text, default="{}")
    # Encadenamiento: lanzar otro flujo al aprobar
    chain_on_approval_workflow_id = Column(String(36), ForeignKey("approval_workflows.id"), nullable=True)
    # Bloqueo duro al superar SLA
    sla_block_on_breach = Column(Boolean, default=False)
    # Reglas de auto-aprobación (JSON): [{"conditions": {...}, "action": "auto_approve"}]
    auto_approval_rules = Column(Text, nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    steps = relationship("ApprovalStep", back_populates="workflow",
                         order_by="ApprovalStep.step_order",
                         cascade="all, delete-orphan")


class ApprovalStep(Base):
    """Un nivel del flujo de aprobación."""
    __tablename__ = "approval_steps"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    workflow_id  = Column(String(36), ForeignKey("approval_workflows.id", ondelete="CASCADE"), nullable=False)
    step_order   = Column(Integer, nullable=False)     # 1, 2, 3...
    name         = Column(String(100), nullable=False)  # "Manager directo", "Director", "CFO"
    approver_type = Column(String(30), nullable=False)  # role | user | manager | any_in_department
    approver_role = Column(String(50), nullable=True)   # si approver_type = role
    approver_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    approver_department = Column(String(100), nullable=True)
    # Comportamiento
    is_optional     = Column(Boolean, default=False)
    timeout_hours   = Column(Integer, default=72)
    on_timeout      = Column(String(20), default="escalate")  # escalate | auto_approve | reject
    escalate_to_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    # Enterprise v2
    parallel_quorum    = Column(Boolean, default=False)   # múltiples aprobadores en paralelo
    required_approvals = Column(Integer, default=1)        # quórum: cuántos votos positivos se necesitan
    step_condition     = Column(Text, nullable=True)       # JSON: condición para activar el paso
    requires_attachment = Column(Boolean, default=False)   # la decisión debe incluir adjunto
    reminder_hours     = Column(Integer, nullable=True)    # recordatorio tras N horas
    approver_group_id  = Column(String(36), ForeignKey("approval_groups.id"), nullable=True)

    workflow       = relationship("ApprovalWorkflow", back_populates="steps")
    approver       = relationship("User", foreign_keys=[approver_user_id])
    escalatee      = relationship("User", foreign_keys=[escalate_to_user_id])
    approver_group = relationship("ApprovalGroup", foreign_keys=[approver_group_id])


class ApprovalRequest(Base):
    """Instancia de una solicitud de aprobación en curso."""
    __tablename__ = "approval_requests"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    workflow_id  = Column(String(36), ForeignKey("approval_workflows.id"), nullable=True)
    entity_type  = Column(String(50), nullable=False)   # timesheet | expense | milestone...
    entity_id    = Column(String(36), nullable=False)   # ID del objeto a aprobar
    entity_summary = Column(String(500), nullable=True) # Descripción legible
    requested_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    current_step = Column(Integer, default=1)
    status       = Column(String(30), default="pending")  # pending | approved | rejected | cancelled
    # Timeout tracking: set when a step becomes active, reset on step advance
    step_started_at = Column(DateTime(timezone=True), nullable=True)
    # Resultado final
    final_decision = Column(String(20), nullable=True)
    final_note     = Column(Text, nullable=True)
    completed_at   = Column(DateTime(timezone=True), nullable=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    requester = relationship("User", foreign_keys=[requested_by])
    workflow  = relationship("ApprovalWorkflow", foreign_keys=[workflow_id])
    decisions = relationship("ApprovalDecision", back_populates="request",
                             order_by="ApprovalDecision.step_order",
                             cascade="all, delete-orphan")


class ApprovalDecision(Base):
    """Decisión de un aprobador en un paso concreto."""
    __tablename__ = "approval_decisions"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    request_id   = Column(String(36), ForeignKey("approval_requests.id", ondelete="CASCADE"), nullable=False)
    step_order   = Column(Integer, nullable=False)
    approver_id  = Column(String(36), ForeignKey("users.id"), nullable=False)
    decision     = Column(String(20), nullable=False)   # approved | rejected | delegated
    note           = Column(Text, nullable=True)
    attachment_url = Column(Text, nullable=True)
    decided_at     = Column(DateTime(timezone=True), server_default=func.now())

    request  = relationship("ApprovalRequest", back_populates="decisions")
    approver = relationship("User", foreign_keys=[approver_id])


class FinancialApprovalAuditLog(Base):
    """Immutable audit trail for approvals that have financial impact."""
    __tablename__ = "financial_approval_audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    request_id = Column(String(36), ForeignKey("approval_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_type = Column(String(50), nullable=False, index=True)
    entity_id = Column(String(36), nullable=False, index=True)
    action = Column(String(30), nullable=False)  # requested | approved | rejected | delegated | cancelled
    decision = Column(String(20), nullable=True)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    step_order = Column(Integer, nullable=True)
    note = Column(Text, nullable=True)
    metadata_ = Column("metadata", Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    request = relationship("ApprovalRequest", foreign_keys=[request_id])
    actor = relationship("User", foreign_keys=[actor_user_id])


# ── GRC — Governance, Risk & Compliance ───────────────────────────────────────

class RolePermission(Base):
    """
    Matriz de permisos por rol — persistente en DB, editable por admins.
    Columnas: role, module, action → allowed (bool).
    """
    __tablename__ = "grc_role_permissions"

    id      = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    role    = Column(String(50),  nullable=False)   # admin | pm | team_lead | employee | hr | client
    module  = Column(String(80),  nullable=False)   # projects | tasks | timesheets | invoices...
    action  = Column(String(30),  nullable=False)   # ver | crear | editar | eliminar | aprobar | exportar
    allowed = Column(Boolean, default=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by = Column(String(36), ForeignKey("users.id"), nullable=True)

    editor = relationship("User", foreign_keys=[updated_by])


class SodRule(Base):
    """
    Regla de Segregación de Funciones (SoD).
    Define un par de (módulo/acción) que no debe recaer en la misma persona/rol.
    """
    __tablename__ = "grc_sod_rules"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    module_a    = Column(String(80),  nullable=False)
    action_a    = Column(String(30),  nullable=False)
    module_b    = Column(String(80),  nullable=False)
    action_b    = Column(String(30),  nullable=False)
    risk        = Column(String(20),  default="high")   # critical | high | medium | low
    description = Column(Text,        nullable=True)
    is_active   = Column(Boolean,     default=True)
    # JSON list of role ids with known conflict: ["pm", "hr"]
    roles_conflict = Column(Text, default="[]")
    # Mitigation: link to a required approval workflow
    mitigated_by_workflow_id = Column(String(36), ForeignKey("approval_workflows.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    created_by  = Column(String(36), ForeignKey("users.id"), nullable=True)

    mitigating_workflow = relationship("ApprovalWorkflow", foreign_keys=[mitigated_by_workflow_id])
    creator = relationship("User", foreign_keys=[created_by])


class GrcAuditLog(Base):
    """
    Registro inmutable de eventos relevantes para GRC: cambios de permisos,
    violaciones SoD detectadas, aprobaciones críticas, cambios de configuración.
    """
    __tablename__ = "grc_audit_log"

    id            = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    timestamp     = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    user_id       = Column(String(36), ForeignKey("users.id"), nullable=True)
    action_type   = Column(String(80),  nullable=False)   # permission_changed | sod_violation | approval_override | ...
    resource_type = Column(String(80),  nullable=True)    # role_permission | sod_rule | approval | ...
    resource_id   = Column(String(36),  nullable=True)
    detail        = Column(Text,        nullable=True)    # JSON detail blob
    ip_address    = Column(String(45),  nullable=True)
    severity      = Column(String(20),  default="info")   # info | warning | critical

    actor = relationship("User", foreign_keys=[user_id])


class SodViolation(Base):
    """
    Instancia concreta de una violación SoD detectada en el sistema.
    La plataforma puede detectarlas en tiempo real y registrarlas aquí.
    """
    __tablename__ = "grc_sod_violations"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    rule_id     = Column(String(36), ForeignKey("grc_sod_rules.id"), nullable=False)
    user_id     = Column(String(36), ForeignKey("users.id"), nullable=True)
    role        = Column(String(50),  nullable=True)
    # Context: what triggered the violation check
    context_type = Column(String(80),  nullable=True)   # approval_request | task_assignment | ...
    context_id   = Column(String(36),  nullable=True)
    detected_at  = Column(DateTime(timezone=True), server_default=func.now())
    resolved     = Column(Boolean, default=False)
    resolved_at  = Column(DateTime(timezone=True), nullable=True)
    resolution_note = Column(Text, nullable=True)

    rule = relationship("SodRule", foreign_keys=[rule_id])
    user = relationship("User", foreign_keys=[user_id])
