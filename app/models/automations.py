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
    task_status_changed   = "task_status_changed"
    task_overdue          = "task_overdue"
    budget_threshold      = "budget_threshold"
    sprint_started        = "sprint_started"
    sprint_ended          = "sprint_ended"
    timesheet_not_submitted = "timesheet_not_submitted"
    ticket_created        = "ticket_created"
    ticket_sla_at_risk    = "ticket_sla_at_risk"
    risk_score_high       = "risk_score_high"
    expense_submitted     = "expense_submitted"
    project_status_changed = "project_status_changed"
    date_reached          = "date_reached"
    custom_field_changed  = "custom_field_changed"   # v23.8: custom field value change trigger
    opportunity_stage_changed = "opportunity_stage_changed"  # v23.8: pipeline stage change


class ActionType(str, enum.Enum):
    send_alert            = "send_alert"
    create_alert          = "create_alert"
    change_task_status    = "change_task_status"
    assign_task           = "assign_task"
    create_task           = "create_task"
    escalate_ticket       = "escalate_ticket"
    change_ticket_status  = "change_ticket_status"
    notify_user           = "notify_user"
    notify_role           = "notify_role"
    # New action types (v24)
    send_email            = "send_email"
    call_webhook          = "call_webhook"
    send_slack_message    = "send_slack_message"
    send_teams_message    = "send_teams_message"
    # v23.8: third-party integrations
    create_jira_issue     = "create_jira_issue"
    update_jira_issue     = "update_jira_issue"
    create_hubspot_deal   = "create_hubspot_deal"
    update_hubspot_deal   = "update_hubspot_deal"
    # v24: workflow steps
    wait_step             = "wait_step"           # Delay execution — requires re-trigger via scheduler
    conditional_branch    = "conditional_branch"  # Evaluate condition → execute if_true or if_false actions


class AutomationRule(Base):
    """A single automation rule: one trigger → one or more actions."""
    __tablename__ = "automation_rules"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name        = Column(String(255), nullable=False)
    description = Column(String(500), nullable=True)

    # Scope
    project_id  = Column(String(36), ForeignKey("projects.id"), nullable=True)  # None = global
    is_active   = Column(Boolean, default=True)
    is_global   = Column(Boolean, default=False)  # Applies to all projects

    # Trigger
    trigger_type       = Column(Enum(TriggerType), nullable=False, index=True)
    trigger_conditions = Column(Text, nullable=True)   # JSON: {"field": "status", "operator": "equals", "value": "done"}

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


class AutomationExecution(Base):
    """Log of every automation rule execution."""
    __tablename__ = "automation_executions"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    rule_id     = Column(String(36), ForeignKey("automation_rules.id", ondelete="CASCADE"), nullable=False, index=True)
    trigger_context = Column(Text, nullable=True)   # JSON: what triggered it
    actions_taken   = Column(Text, nullable=True)   # JSON: what was done
    success     = Column(Boolean, default=True)
    error       = Column(String(500), nullable=True)
    executed_at = Column(DateTime(timezone=True), server_default=func.now())

    rule = relationship("AutomationRule", back_populates="executions")
