from datetime import datetime, timezone as tz
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.services.numbering import next_numbered_code

from app.models.service_desk import ChangeStatus, ITSMChangeRequest, Problem, Ticket
from app.models.user import User
from app.services.service_desk.scoping import (
    _org_user_ids_subquery,
    scope_problem_query as _scope_problem_query,
    scope_ticket_query as _scope_ticket_query,
)


def scope_change_query(q, db: Session, current_user: User):
    if current_user.is_superadmin:
        return q
    org_user_ids = _org_user_ids_subquery(db, current_user)
    if org_user_ids is None:
        return q.filter(False)
    return q.filter(
        or_(
            ITSMChangeRequest.requester_id.in_(org_user_ids),
            ITSMChangeRequest.owner_id.in_(org_user_ids),
        )
    )


def build_change_list_query(
    db: Session,
    current_user: User,
    status: Optional[str],
    change_type: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
):
    q = db.query(ITSMChangeRequest).options(
        joinedload(ITSMChangeRequest.requester),
        joinedload(ITSMChangeRequest.owner),
    )
    q = scope_change_query(q, db, current_user)
    if status:
        q = q.filter(ITSMChangeRequest.status == status)
    if change_type:
        q = q.filter(ITSMChangeRequest.change_type == change_type)
    if date_from:
        q = q.filter(ITSMChangeRequest.created_at >= datetime.fromisoformat(date_from).replace(tzinfo=tz.utc))
    if date_to:
        q = q.filter(ITSMChangeRequest.created_at <= datetime.fromisoformat(date_to).replace(tzinfo=tz.utc))
    return q


def list_changes_payload(
    db: Session,
    current_user: User,
    status: Optional[str],
    change_type: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
    page: int,
    page_size: int,
) -> list[dict]:
    q = build_change_list_query(db, current_user, status, change_type, date_from, date_to)
    changes = (
        q.order_by(ITSMChangeRequest.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return [serialize_change(c) for c in changes]


def get_change_by_id(db: Session, current_user: User, change_id: str):
    return scope_change_query(db.query(ITSMChangeRequest), db, current_user).filter(
        ITSMChangeRequest.id == change_id
    ).first()


def get_change_payload(db: Session, current_user: User, change_id: str, full: bool = False) -> dict:
    change = get_change_by_id(db, current_user, change_id)
    if not change:
        raise HTTPException(404, "Change request no encontrado")
    return serialize_change(change, full=full)


def serialize_change(change: ITSMChangeRequest, full: bool = False) -> dict:
    base = {
        "id": change.id,
        "number": change.number,
        "title": change.title,
        "change_type": change.change_type.value if change.change_type else None,
        "status": change.status.value if change.status else None,
        "risk": change.risk.value if change.risk else None,
        "priority": change.priority.value if change.priority else None,
        "planned_start": str(change.planned_start) if change.planned_start else None,
        "planned_end": str(change.planned_end) if change.planned_end else None,
        "actual_start": str(change.actual_start) if change.actual_start else None,
        "actual_end": str(change.actual_end) if change.actual_end else None,
        "requester_id": change.requester_id,
        "requester": change.requester.full_name if change.requester else None,
        "owner_id": change.owner_id,
        "owner": change.owner.full_name if change.owner else None,
        "approved_by": change.approved_by,
        "approved_at": str(change.approved_at) if change.approved_at else None,
        "pir_success": change.pir_success,
        "pir_date": str(change.pir_date) if change.pir_date else None,
        "downtime_minutes": change.downtime_minutes,
        "created_at": str(change.created_at),
    }
    if full:
        base.update(
            {
                "description": change.description,
                "business_justification": change.business_justification,
                "implementation_plan": change.implementation_plan,
                "rollback_plan": change.rollback_plan,
                "test_plan": change.test_plan,
                "impact_description": change.impact_description,
                "pir_notes": change.pir_notes,
            }
        )
    return base


def next_change_number(db: Session) -> str:
    return next_numbered_code(db, "itsm_change", prefix="CHG", padding=5, separator="")


def build_change_request(payload: dict, requester_id: str, number: str) -> ITSMChangeRequest:
    if not payload.get("title") or not payload.get("description"):
        raise HTTPException(422, "title y description son obligatorios")

    change = ITSMChangeRequest(
        number=number,
        title=payload["title"],
        description=payload["description"],
        change_type=payload.get("change_type", "normal"),
        risk=payload.get("risk", "medium"),
        priority=payload.get("priority", "p3_medium"),
        implementation_plan=payload.get("implementation_plan"),
        rollback_plan=payload.get("rollback_plan"),
        test_plan=payload.get("test_plan"),
        business_justification=payload.get("business_justification"),
        impact_description=payload.get("impact_description"),
        downtime_minutes=payload.get("downtime_minutes", 0),
        requester_id=requester_id,
        owner_id=payload.get("owner_id"),
        related_ticket_id=payload.get("related_ticket_id"),
        related_problem_id=payload.get("related_problem_id"),
    )
    if payload.get("planned_start"):
        change.planned_start = datetime.fromisoformat(payload["planned_start"]).replace(tzinfo=tz.utc)
    if payload.get("planned_end"):
        change.planned_end = datetime.fromisoformat(payload["planned_end"]).replace(tzinfo=tz.utc)
    return change


def apply_change_update(change: ITSMChangeRequest, payload: dict, current_user_id: str) -> None:
    for field in (
        "title",
        "description",
        "change_type",
        "risk",
        "priority",
        "status",
        "implementation_plan",
        "rollback_plan",
        "test_plan",
        "business_justification",
        "impact_description",
        "downtime_minutes",
        "pir_notes",
        "pir_success",
        "owner_id",
    ):
        if field in payload:
            setattr(change, field, payload[field])

    for dt_field in ("planned_start", "planned_end", "actual_start", "actual_end", "pir_date"):
        if dt_field in payload and payload[dt_field]:
            setattr(change, dt_field, datetime.fromisoformat(payload[dt_field]).replace(tzinfo=tz.utc))

    if payload.get("status") == "approved":
        change.approved_at = datetime.now(tz.utc)
        change.approved_by = current_user_id


def approve_change_request(change: ITSMChangeRequest, approved: bool, approver_id: str, reason: Optional[str]) -> None:
    change.status = ChangeStatus.approved if approved else ChangeStatus.cancelled
    change.approved_at = datetime.now(tz.utc)
    change.approved_by = approver_id
    if not approved:
        change.rejected_reason = reason or "Rechazado por CAB"


def create_change_record(db: Session, current_user: User, payload: dict) -> ITSMChangeRequest:
    number = next_change_number(db)
    change = build_change_request(payload, current_user.id, number)
    enforce_change_org_constraints(db, current_user, change)
    db.add(change)
    return change


def update_change_record(db: Session, current_user: User, change_id: str, payload: dict) -> ITSMChangeRequest:
    change = get_change_by_id(db, current_user, change_id)
    if not change:
        raise HTTPException(404)

    apply_change_update(change, payload, current_user.id)
    enforce_change_org_constraints(db, current_user, change)
    return change


def approve_change_record(db: Session, current_user: User, change_id: str, payload: dict) -> ITSMChangeRequest:
    change = get_change_by_id(db, current_user, change_id)
    if not change:
        raise HTTPException(404)

    approve_change_request(
        change,
        approved=payload.get("approved", True),
        approver_id=current_user.id,
        reason=payload.get("reason"),
    )
    return change


def enforce_change_org_constraints(db: Session, current_user: User, change: ITSMChangeRequest) -> None:
    if current_user.is_superadmin or not current_user.organization_id:
        return

    if change.owner_id:
        owner = db.query(User).filter(User.id == change.owner_id).first()
        if not owner or owner.organization_id != current_user.organization_id:
            raise HTTPException(403, "No puedes asignar owner fuera de tu organización")

    if change.related_ticket_id:
        ticket = _scope_ticket_query(db.query(Ticket), db, current_user).filter(Ticket.id == change.related_ticket_id).first()
        if not ticket:
            raise HTTPException(403, "Ticket relacionado fuera de tu organización")

    if change.related_problem_id:
        problem = _scope_problem_query(db.query(Problem), db, current_user).filter(Problem.id == change.related_problem_id).first()
        if not problem:
            raise HTTPException(403, "Problema relacionado fuera de tu organización")
