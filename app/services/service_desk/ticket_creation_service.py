from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.client_portal import ClientUser
from app.models.service_desk import ServiceItem, Ticket, TicketStatus
from app.schemas.service_desk import TicketCreateIn
from app.services.service_desk.routing_rule_service import apply_routing_rules
from app.services.service_desk.scoping import resolve_sla_policy_for_ticket as _resolve_sla_policy_for_ticket
from app.services.sla_service import (
    PRIORITY_MATRIX,
    calculate_sla_due as _calculate_sla_due,
    next_ticket_number as _next_ticket_number,
    norm_enum as _norm_enum,
)


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
    if payload.assigned_to_user_id:
        ticket.status = TicketStatus.assigned
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
    return ticket
