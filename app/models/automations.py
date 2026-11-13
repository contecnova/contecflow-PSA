"""
Automation engine — no-code rule builder for Contecflow.
Rules: IF trigger(conditions) THEN action(params)
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Boolean, Integer, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
import uuid
from app.db.base import Base


class TriggerType(str, enum.Enum):
    """Disparadores con origen real.

    Auditoria 2026-11: la pantalla ofrecia 64 y la columna era un enum de
    Postgres con 14, asi que 52 no se podian guardar; y de los 14 ninguno se
    emitia. Ahora la columna es texto y aqui solo estan los que algo emite:
    los de cambio de un registro salen de `automation_events` (al guardar,
    venga de la via que venga) y los de fecha o umbral, del barrido periodico.
    """
    # Tareas
    task_created          = "task_created"
    task_status_changed   = "task_status_changed"
    task_assigned         = "task_assigned"
    task_completed        = "task_completed"
    task_blocked          = "task_blocked"
    task_overdue          = "task_overdue"            # barrido
    task_deadline_approaching = "task_deadline_approaching"  # barrido
    # Proyectos
    project_created       = "project_created"
    project_status_changed = "project_status_changed"
    budget_threshold      = "budget_threshold"        # barrido
    risk_score_high       = "risk_score_high"
    # Sprints
    sprint_started        = "sprint_started"
    sprint_ended          = "sprint_ended"
    # Tiempo y equipo
    timesheet_submitted   = "timesheet_submitted"
    timesheet_rejected    = "timesheet_rejected"
    timesheet_not_submitted = "timesheet_not_submitted"  # barrido
    absence_requested     = "absence_requested"
    absence_approved      = "absence_approved"
    absence_rejected      = "absence_rejected"
    # Service Desk
    ticket_created        = "ticket_created"
    ticket_resolved       = "ticket_resolved"
    ticket_reopened       = "ticket_reopened"
    ticket_escalated      = "ticket_escalated"
    ticket_sla_at_risk    = "ticket_sla_at_risk"
    ticket_sla_breached   = "ticket_sla_breached"
    # Finanzas y CRM
    expense_submitted     = "expense_submitted"
    expense_approved      = "expense_approved"
    expense_rejected      = "expense_rejected"
    opportunity_stage_changed = "opportunity_stage_changed"
    # Facturas (revisión 2026-11)
    invoice_sent          = "invoice_sent"
    invoice_paid          = "invoice_paid"
    invoice_overdue       = "invoice_overdue"         # barrido
    # Aprobaciones (revisión 2026-11)
    approval_requested    = "approval_requested"
    approval_approved     = "approval_approved"
    approval_rejected     = "approval_rejected"
    # Programada: según `schedule_cron`, sin esperar a un cambio (revisión 2026-11)
    scheduled             = "scheduled"


class ActionType(str, enum.Enum):
    """Acciones con ejecutor (`automations_service._ACCIONES`)."""
    create_alert          = "create_alert"
    send_alert            = "send_alert"           # alias historico de create_alert
    notify_user           = "notify_user"
    notify_role           = "notify_role"
    send_email            = "send_email"
    call_webhook          = "call_webhook"
    send_webhook          = "send_webhook"         # alias historico de call_webhook
    send_slack_message    = "send_slack_message"
    send_teams_message    = "send_teams_message"
    assign                = "assign"
    update_field          = "update_field"
    create_approval       = "create_approval"
    change_task_status    = "change_task_status"
    change_task_priority  = "change_task_priority"
    create_task           = "create_task"
    change_project_status = "change_project_status"
    escalate_ticket       = "escalate_ticket"
    change_ticket_status  = "change_ticket_status"
    conditional_branch    = "conditional_branch"


class AutomationRule(Base):
    """A single automation rule: one trigger → one or more actions."""
    __tablename__ = "automation_rules"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    name        = Column(String(255), nullable=False)
    description = Column(String(500), nullable=True)

    # Scope
    project_id  = Column(String(36), ForeignKey("projects.id"), nullable=True)  # None = global
    is_active   = Column(Boolean, default=True)
    is_global   = Column(Boolean, default=False)  # Applies to all projects

    # Trigger
    trigger_type       = Column(String(64), nullable=False, index=True)
    # JSON: una condición {"field", "operator", "value"} o un grupo
    # {"match": "all"|"any", "conditions": [...]} (anidable, revisión 2026-11).
    trigger_conditions = Column(Text, nullable=True)
    # Disparador «scheduled»: cron de cinco campos en la zona de la empresa.
    schedule_cron      = Column(String(100), nullable=True)
    next_run_at        = Column(DateTime(timezone=True), nullable=True, index=True)

    # Actions (JSON array)
    actions            = Column(Text, nullable=False)  # JSON: [{"type": "send_alert", "params": {...}}]

    # Stats
    run_count     = Column(Integer, default=0)
    last_run_at   = Column(DateTime(timezone=True), nullable=True)
    last_error    = Column(String(500), nullable=True)

    created_by    = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    updated_at    = Column(DateTime(timezone=True), onupdate=func.now())

    project    = relationship("Project")
    creator    = relationship("User", foreign_keys=[created_by])
    executions = relationship("AutomationExecution", back_populates="rule",
                              cascade="all, delete-orphan",
                              order_by="AutomationExecution.executed_at.desc()")

    def __repr__(self) -> str:
        return f"<AutomationRule id={self.id!r} name={self.name!r}>"


class AutomationExecution(Base):
    """Log of every automation rule execution."""
    __tablename__ = "automation_executions"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # audit #7
    rule_id     = Column(String(36), ForeignKey("automation_rules.id", ondelete="CASCADE"), nullable=False, index=True)
    trigger_context = Column(Text, nullable=True)   # JSON: what triggered it
    actions_taken   = Column(Text, nullable=True)   # JSON: what was done
    success     = Column(Boolean, default=True)
    error       = Column(String(500), nullable=True)
    # Los disparadores del barrido se repiten en cada pasada; esta clave
    # (p. ej. «task_overdue:<id>:<fecha>») hace que una regla actue una vez.
    dedupe_key  = Column(String(255), nullable=True, index=True)
    executed_at = Column(DateTime(timezone=True), server_default=func.now())

    rule = relationship("AutomationRule", back_populates="executions")

    def __repr__(self) -> str:
        return f"<AutomationExecution id={self.id!r} rule_id={self.rule_id!r}>"


class AutomationEvent(Base):
    """Bandeja de salida: un registro cambio y alguna regla puede querer saberlo.

    Lo anota `automation_events` en el flush de la misma transaccion que el
    cambio, y lo procesa el worker despues del commit: si el cambio se deshace,
    el evento tambien; y las acciones (correo, webhooks) no alargan la peticion.
    """
    __tablename__ = "automation_events"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    trigger_type    = Column(String(64), nullable=False)
    context         = Column(Text, nullable=True)       # JSON
    depth           = Column(Integer, nullable=False, default=0)
    status          = Column(String(20), nullable=False, default="pending", index=True)  # pending | done | failed | skipped (org desactivada)
    attempts        = Column(Integer, nullable=False, default=0)
    error           = Column(String(500), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    processed_at    = Column(DateTime(timezone=True), nullable=True)
