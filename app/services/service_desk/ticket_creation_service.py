from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.client_portal import ClientUser
from app.models.service_desk import ServiceItem, Ticket
from app.schemas.service_desk import TicketCreateIn
from app.services.service_desk.routing_rule_service import apply_routing_rules
from app.services.service_desk.scoping import resolve_sla_policy_for_ticket as _resolve_sla_policy_for_ticket
from app.services.service_desk.dynamic_ticket_fields_service import save_ticket_dynamic_fields
from app.services.sla_service import (
    PRIORITY_MATRIX,
    calculate_sla_due as _calculate_sla_due,
    next_ticket_number as _next_ticket_number,
    norm_enum as _norm_enum,
)
import logging

logger = logging.getLogger(__name__)


def _emit_ticket_created_metric(ticket: Ticket) -> None:
    """Best-effort Prometheus counter increment; never raises into business flow."""
    try:
        from app.core.metrics import tickets_created_total

        def _v(field):
            value = getattr(ticket, field, None)
            return getattr(value, "value", value) if value is not None else "unknown"

        tickets_created_total.labels(
            tenant_id=str(getattr(ticket, "organization_id", None) or "unknown"),
            ticket_type=str(_v("ticket_type")),
            priority=str(_v("priority")),
            source=str(_v("source")),
        ).inc()
    except Exception:  # noqa: S110
        pass


def _semantic_assignee_if_enabled(db: Session, ticket: Ticket, candidate_user_ids: list[str]) -> str | None:
    """Return semantic suggestion when enabled by SemConfig; else None.

    This preserves semantic engine value without replacing the ML routing fallback.
    """
    try:
        from app.models.semantic_engine import SemConfig  # noqa: PLC0415
        from app.services.semantic_classifier import SemanticAssigner  # noqa: PLC0415

        cfg = db.query(SemConfig).first()
        if not cfg or not bool(getattr(cfg, "auto_assign_tickets", False)):
            return None

        priority = str(ticket.priority.value) if hasattr(ticket.priority, "value") else str(ticket.priority or "medium")
        suggestion = SemanticAssigner(db).suggest_for_ticket(
            ticket.title or "",
            ticket.description or "",
            candidate_user_ids,
            priority=priority,
        )
        suggested = suggestion.get("suggested_user_id")
        if suggested and suggested in set(candidate_user_ids):
            return suggested
    except Exception:
        return None
    return None


def _auto_assign_ticket_on_create(db: Session, ticket: Ticket) -> None:
    """Ensure every newly created ticket gets an assignee using ML routing.

    If a manual assignee already exists, preserve it and just normalize status/event.
    """
    from app.models.service_desk import AgentGroupMember, TicketStatus  # noqa: PLC0415
    from app.services.service_desk.ml_routing_service import (  # noqa: PLC0415
        predict_best_agent,
        record_routing_event,
    )

    def _status_value(v):
        if hasattr(v, "value"):
            return str(v.value)
        s = str(v)
        if s.startswith("TicketStatus."):
            return s.split(".", 1)[1]
        return s

    if ticket.assigned_to_user_id:
        status_now = _status_value(ticket.status)
        if not ticket.status or status_now in {TicketStatus.new.value, TicketStatus.assigned.value, "None"}:
            ticket.status = TicketStatus.assigned
        if not ticket.id:
            db.flush()
        record_routing_event(db, ticket)
        return

    # Service Catalog can define a default target group.
    if not ticket.assigned_group_id and ticket.service_item and ticket.service_item.auto_assign_group:
        ticket.assigned_group_id = ticket.service_item.auto_assign_group

    if ticket.assigned_group_id:
        members = (
            db.query(AgentGroupMember)
            .filter(AgentGroupMember.group_id == ticket.assigned_group_id)
            .all()
        )
    else:
        # Global fallback: all SD agents (deduplicated by user)
        all_members = db.query(AgentGroupMember).all()
        seen: set[str] = set()
        members = []
        for m in all_members:
            if m.user_id in seen:
                continue
            seen.add(m.user_id)
            members.append(m)

    if not members:
        return

    candidate_user_ids = [m.user_id for m in members if getattr(m, "user_id", None)]
    best_agent_id = _semantic_assignee_if_enabled(db, ticket, candidate_user_ids)
    if not best_agent_id:
        best_agent_id = predict_best_agent(db, ticket, members)
    if not best_agent_id:
        return

    ticket.assigned_to_user_id = best_agent_id
    if not ticket.assigned_group_id:
        chosen = next((m for m in members if m.user_id == best_agent_id), None)
        if chosen:
            ticket.assigned_group_id = chosen.group_id

    status_now = _status_value(ticket.status)
    if not ticket.status or status_now in {TicketStatus.new.value, TicketStatus.assigned.value, "None"}:
        ticket.status = TicketStatus.assigned

    if not ticket.id:
        db.flush()
    record_routing_event(db, ticket)


def build_internal_ticket(db: Session, payload: TicketCreateIn, requester_user_id: str) -> Ticket:
    priority = payload.priority
    if not priority:
        priority = PRIORITY_MATRIX.get(
            (_norm_enum(payload.urgency), _norm_enum(payload.impact)),
            "p3_medium",
        )

    sla_policy = _resolve_sla_policy_for_ticket(
        db,
        contract_id=payload.contract_id,
        client_id=payload.client_id,
    )
    resp_due, res_due = _calculate_sla_due(priority, sla_policy, db=db)

    service_item = None
    if payload.service_item_id:
        service_item = db.query(ServiceItem).filter(ServiceItem.id == payload.service_item_id).first()
        if service_item:
            if not payload.priority:
                priority = (
                    service_item.default_priority.value
                    if hasattr(service_item.default_priority, "value")
                    else service_item.default_priority
                )
            resp_due = datetime.now(timezone.utc) + timedelta(hours=service_item.sla_response_hours)
            res_due = datetime.now(timezone.utc) + timedelta(hours=service_item.sla_resolution_hours)

    ticket = Ticket(
        number=_next_ticket_number(payload.ticket_type, db),
        ticket_type=payload.ticket_type,
        title=payload.title,
        description=payload.description,
        urgency=payload.urgency,
        impact=payload.impact,
        priority=priority,
        support_level=(
            service_item.default_support_level.value
            if service_item and hasattr(service_item.default_support_level, "value")
            else "l1"
        ),
        project_id=payload.project_id,
        client_id=payload.client_id,
        contract_id=payload.contract_id,
        ci_id=payload.ci_id,
        service_item_id=payload.service_item_id,
        assigned_to_user_id=payload.assigned_to_user_id,
        assigned_group_id=payload.assigned_group_id,
        requester_user_id=requester_user_id,
        requester_name=payload.requester_name,
        requester_email=payload.requester_email,
        tags=payload.tags,
        source=payload.source,
        sla_policy_id=sla_policy.id if sla_policy else None,
        sla_response_due=resp_due,
        sla_resolution_due=res_due,
        created_by_user_id=requester_user_id,
    )

    db.add(ticket)
    apply_routing_rules(ticket, db)
    _auto_assign_ticket_on_create(db, ticket)
    db.flush()
    save_ticket_dynamic_fields(db, ticket.id, payload.dynamic_fields)
    _emit_ticket_created_metric(ticket)
    return ticket


def build_client_portal_ticket(db: Session, payload: TicketCreateIn, client: ClientUser) -> Ticket:
    priority = payload.priority
    if not priority:
        priority = PRIORITY_MATRIX.get(
            (_norm_enum(payload.urgency), _norm_enum(payload.impact)),
            "p3_medium",
        )

    sla_policy = _resolve_sla_policy_for_ticket(
        db,
        contract_id=payload.contract_id,
        client_id=client.client_org_id,
    )
    resp_due, res_due = _calculate_sla_due(priority, sla_policy, db=db)

    if payload.service_item_id:
        service_item = db.query(ServiceItem).filter(ServiceItem.id == payload.service_item_id).first()
        if service_item:
            resp_due = datetime.now(timezone.utc) + timedelta(hours=service_item.sla_response_hours)
            res_due = datetime.now(timezone.utc) + timedelta(hours=service_item.sla_resolution_hours)

    if payload.project_id and payload.project_id != client.project_id:
        raise HTTPException(403, "No puedes crear tickets para proyectos a los que no perteneces")

    ticket = Ticket(
        number=_next_ticket_number(payload.ticket_type, db),
        ticket_type=payload.ticket_type,
        title=payload.title,
        description=payload.description,
        urgency=payload.urgency,
        impact=payload.impact,
        priority=priority,
        project_id=client.project_id,
        client_id=client.client_org_id,
        contract_id=payload.contract_id,
        ci_id=payload.ci_id,
        service_item_id=payload.service_item_id,
        tags=payload.tags,
        requester_client_id=client.id,
        source="portal",
        sla_policy_id=sla_policy.id if sla_policy else None,
        sla_response_due=resp_due,
        sla_resolution_due=res_due,
    )
    db.add(ticket)
    apply_routing_rules(ticket, db)
    _auto_assign_ticket_on_create(db, ticket)
    db.flush()
    save_ticket_dynamic_fields(db, ticket.id, payload.dynamic_fields)
    _emit_ticket_created_metric(ticket)
    return ticket
