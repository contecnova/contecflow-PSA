"""
events.py — Standard system event bus for service orchestration.

All modules emit events via `emit_event()` after each relevant action.
Events dispatch to outbound webhooks and are ready for additional listeners
(message queues, audit enrichment, real-time push).

Event type catalog:  <domain>.<action>
Domains: portfolio, project, task, sprint, milestone, user, organization,
         ticket, invoice, expense, contract, risk, document, approval

Usage (always call AFTER db.commit() to ensure data consistency):
    from app.core.events import emit_event, EventType
    emit_event(db, EventType.PORTFOLIO_CREATED, {"name": p.name},
               actor=current_user, resource_id=p.id)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── Event type catalog ────────────────────────────────────────────────────────

class EventType:
    """Canonical event type strings. Format: <domain>.<action>."""

    # Portfolio
    PORTFOLIO_CREATED         = "portfolio.created"
    PORTFOLIO_UPDATED         = "portfolio.updated"
    PORTFOLIO_DELETED         = "portfolio.deleted"
    PORTFOLIO_PROJECT_ADDED   = "portfolio.project_added"
    PORTFOLIO_PROJECT_REMOVED = "portfolio.project_removed"

    # Project
    PROJECT_CREATED        = "project.created"
    PROJECT_UPDATED        = "project.updated"
    PROJECT_DELETED        = "project.deleted"
    PROJECT_STATUS_CHANGED = "project.status_changed"
    PROJECT_MEMBER_ADDED   = "project.member_added"
    PROJECT_MEMBER_REMOVED = "project.member_removed"
    PROJECT_COMPLETED      = "project.completed"

    # Task
    TASK_CREATED   = "task.created"
    TASK_UPDATED   = "task.updated"
    TASK_COMPLETED = "task.completed"
    TASK_ASSIGNED  = "task.assigned"
    TASK_DELETED   = "task.deleted"

    # Sprint
    SPRINT_CREATED   = "sprint.created"
    SPRINT_STARTED   = "sprint.started"
    SPRINT_COMPLETED = "sprint.completed"
    SPRINT_DELETED   = "sprint.deleted"

    # Milestone
    MILESTONE_CREATED   = "milestone.created"
    MILESTONE_UPDATED   = "milestone.updated"
    MILESTONE_COMPLETED = "milestone.completed"
    MILESTONE_APPROVED  = "milestone.approved"
    MILESTONE_INVOICED  = "milestone.invoiced"

    # User
    USER_CREATED      = "user.created"
    USER_UPDATED      = "user.updated"
    USER_ROLE_CHANGED = "user.role_changed"
    USER_DEACTIVATED  = "user.deactivated"
    USER_ACTIVATED    = "user.activated"

    # Organization
    ORG_CREATED      = "organization.created"
    ORG_UPDATED      = "organization.updated"
    ORG_USER_ADDED   = "organization.user_assigned"
    ORG_USER_REMOVED = "organization.user_removed"

    # Service Desk
    TICKET_CREATED   = "ticket.created"
    TICKET_UPDATED   = "ticket.updated"
    TICKET_ASSIGNED  = "ticket.assigned"
    TICKET_RESOLVED  = "ticket.resolved"
    TICKET_CLOSED    = "ticket.closed"
    TICKET_ESCALATED = "ticket.escalated"

    # Financial
    EXPENSE_SUBMITTED = "expense.submitted"
    EXPENSE_APPROVED  = "expense.approved"
    EXPENSE_REJECTED  = "expense.rejected"
    INVOICE_CREATED   = "invoice.created"
    INVOICE_PAID      = "invoice.paid"
    BUDGET_EXCEEDED   = "budget.exceeded"

    # Contract / Pipeline
    CONTRACT_CREATED = "contract.created"
    CONTRACT_SIGNED  = "contract.signed"
    CONTRACT_EXPIRED = "contract.expired"
    OPPORTUNITY_WON  = "opportunity.won"
    OPPORTUNITY_LOST = "opportunity.lost"

    # Document / Approval
    DOCUMENT_UPLOADED    = "document.uploaded"
    APPROVAL_REQUESTED   = "approval.requested"
    APPROVAL_APPROVED    = "approval.approved"
    APPROVAL_REJECTED    = "approval.rejected"

    # Risk
    RISK_CREATED   = "risk.created"
    RISK_UPDATED   = "risk.updated"
    RISK_MITIGATED = "risk.mitigated"
    RISK_CLOSED    = "risk.closed"


# ── Event envelope ────────────────────────────────────────────────────────────

@dataclass
class SystemEvent:
    """Standard event envelope. All fields except event_type and payload are optional."""
    event_type:    str
    payload:       dict
    actor_id:      Optional[str] = None
    actor_name:    Optional[str] = None
    org_id:        Optional[str] = None
    resource_type: Optional[str] = None
    resource_id:   Optional[str] = None
    project_id:    Optional[str] = None
    timestamp:     datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "event":         self.event_type,
            "timestamp":     self.timestamp.isoformat(),
            "actor_id":      self.actor_id,
            "actor_name":    self.actor_name,
            "org_id":        self.org_id,
            "resource_type": self.resource_type,
            "resource_id":   self.resource_id,
            "project_id":    self.project_id,
            "data":          self.payload,
        }


# ── Public API ────────────────────────────────────────────────────────────────

def emit_event(
    db: Any,
    event_type: str,
    payload: dict,
    *,
    actor: Any = None,
    org_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> None:
    """
    Emit a system event and dispatch it to all registered listeners.

    Call this AFTER db.commit() to guarantee data consistency.
    All errors are caught and logged — events never break the main flow.

    Args:
        db:            Active SQLAlchemy session (used for webhook dispatch).
        event_type:    Event type string (use EventType constants).
        payload:       Domain-specific event data.
        actor:         User that triggered the event (optional).
        org_id:        Override organization scope (defaults to actor.organization_id).
        resource_type: Type of the affected resource (e.g. "portfolio").
        resource_id:   ID of the affected resource.
        project_id:    Project scope for webhook filtering.
    """
    try:
        event = SystemEvent(
            event_type=event_type,
            payload=payload,
            actor_id=getattr(actor, "id", None),
            actor_name=getattr(actor, "full_name", None),
            org_id=org_id or getattr(actor, "organization_id", None),
            resource_type=resource_type,
            resource_id=resource_id,
            project_id=project_id,
        )
        _dispatch_webhooks(db, event)
    except Exception as exc:
        logger.debug("emit_event(%s) error: %s", event_type, exc)


# Legacy alias — used by older code that calls emit_system_event(event_type, payload, db=db)
def emit_system_event(
    event_type: str,
    payload: dict,
    db: Any = None,
    *,
    actor: Any = None,
    org_id: Optional[str] = None,
    resource_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> None:
    """Legacy wrapper. Prefer emit_event() for new code."""
    if db is None:
        logger.debug("emit_system_event(%s) skipped: no db session provided", event_type)
        return
    emit_event(
        db, event_type, payload,
        actor=actor, org_id=org_id,
        resource_id=resource_id, project_id=project_id,
    )


# ── Convenience helper ───────────────────────────────────────────────────────

def emit(
    db: Any,
    event_type: str,
    payload: dict,
    *,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    project_id: Optional[str] = None,
    actor: Any = None,
) -> None:
    """
    Short-form emit that reads the actor from db.info["current_user"] when not
    provided explicitly. Designed for service-layer use where current_user is
    available on the session but not passed as a function argument.
    """
    resolved_actor = actor or (db.info.get("current_user") if hasattr(db, "info") else None)
    emit_event(
        db, event_type, payload,
        actor=resolved_actor,
        resource_type=resource_type,
        resource_id=resource_id,
        project_id=project_id,
    )


# ── Internal dispatch ─────────────────────────────────────────────────────────

def _dispatch_webhooks(db: Any, event: SystemEvent) -> None:
    """Fire matching outbound webhooks. Errors are caught individually."""
    try:
        from app.services.webhooks import fire_webhook
        fire_webhook(db, event.event_type, event.to_dict(), project_id=event.project_id)
    except Exception as exc:
        logger.debug("Webhook dispatch for %s failed: %s", event.event_type, exc)
