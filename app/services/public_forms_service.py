"""Service layer for public intake forms."""
import json
import logging
import secrets
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.models.public_forms import PublicForm, PublicFormSubmission
from app.models.service_desk import Ticket, TicketStatus, TicketType, TicketPriority

log = logging.getLogger(__name__)

# ── Priority mapping ───────────────────────────────────────────────────────────

_PRIORITY_MAP = {
    "critical": TicketPriority.p1_critical,
    "high": TicketPriority.p2_high,
    "medium": TicketPriority.p3_medium,
    "low": TicketPriority.p4_low,
}

def map_priority(p: str) -> TicketPriority:
    return _PRIORITY_MAP.get(p, TicketPriority.p3_medium)


# ── Form CRUD ──────────────────────────────────────────────────────────────────

def list_forms(db: Session, user_id: str) -> list[PublicForm]:
    return db.query(PublicForm).filter(
        PublicForm.created_by == user_id,
        PublicForm.is_active == True,
    ).all()


def create_form(
    db: Session,
    *,
    name: str,
    description: Optional[str],
    form_type: str,
    is_active: bool,
    target_project_id: Optional[str],
    target_group_id: Optional[str],
    default_priority: str,
    default_category: Optional[str],
    success_message: Optional[str],
    notify_emails: list[str],
    created_by: str,
) -> PublicForm:
    form = PublicForm(
        id=str(uuid.uuid4()),
        name=name,
        description=description,
        form_type=form_type,
        token=secrets.token_urlsafe(32),
        is_active=is_active,
        target_project_id=target_project_id,
        target_group_id=target_group_id,
        default_priority=default_priority,
        default_category=default_category,
        success_message=success_message,
        notify_emails=json.dumps(notify_emails),
        created_by=created_by,
    )
    db.add(form)
    db.commit()
    db.refresh(form)
    return form


def get_form_by_id(db: Session, form_id: str) -> Optional[PublicForm]:
    return db.query(PublicForm).filter(
        PublicForm.id == form_id,
        PublicForm.is_active == True,
    ).first()


def update_form(db: Session, form: PublicForm, updates: dict) -> PublicForm:
    for field, value in updates.items():
        if field == "notify_emails":
            setattr(form, field, json.dumps(value))
        else:
            setattr(form, field, value)
    db.commit()
    db.refresh(form)
    return form


def delete_form(db: Session, form: PublicForm) -> None:
    form.is_active = False
    db.commit()


def list_submissions(db: Session, form_id: str) -> list[PublicFormSubmission]:
    return (
        db.query(PublicFormSubmission)
        .filter(PublicFormSubmission.form_id == form_id)
        .order_by(PublicFormSubmission.submitted_at.desc())
        .all()
    )


# ── Public (unauthenticated) ───────────────────────────────────────────────────

def get_active_form_by_token(db: Session, token: str) -> Optional[PublicForm]:
    return (
        db.query(PublicForm)
        .filter(PublicForm.token == token, PublicForm.is_active == True)
        .first()
    )


def _next_ticket_number(ticket_type: str, db: Session, org_id: Optional[str] = None) -> str:
    """El numerador comun: antes esta copia no bloqueaba ni miraba la organizacion."""
    from app.services.sla_service import next_ticket_number
    return next_ticket_number(ticket_type, db, org_id)


def submit_form(
    db: Session,
    *,
    form: PublicForm,
    submitter_name: Optional[str],
    submitter_email: Optional[str],
    subject: str,
    description: Optional[str],
    priority: str,
    category: Optional[str],
    extra_fields: dict,
    ip_address: Optional[str],
) -> tuple[PublicFormSubmission, Optional[str]]:
    """
    Creates a submission record and (if form_type=='ticket') a Ticket.
    Returns (submission, created_entity_id).
    """
    created_entity_id = None
    created_entity_type = None

    if form.form_type == "ticket":
        sp = db.begin_nested()
        try:
            ticket = Ticket(
                number=_next_ticket_number("incident", db, form.organization_id),
                ticket_type=TicketType.incident,
                title=subject[:255],
                description=description or "",
                priority=map_priority(priority),
                support_level="l1",
                project_id=form.target_project_id,
                assigned_group_id=form.target_group_id,
                requester_name=submitter_name,
                requester_email=submitter_email,
                source="public_form",
                status=TicketStatus.new,
            )
            db.add(ticket)
            db.flush()
            sp.commit()
            created_entity_id = ticket.id
            created_entity_type = "ticket"
        except Exception as exc:
            sp.rollback()
            log.warning(
                "Ticket creation failed during form submit (form=%s): %s",
                form.id,
                exc,
            )

    sub = PublicFormSubmission(
        id=str(uuid.uuid4()),
        form_id=form.id,
        submitter_name=submitter_name,
        submitter_email=submitter_email,
        subject=subject,
        description=description,
        priority=priority,
        category=category,
        extra_fields=json.dumps(extra_fields),
        created_entity_id=created_entity_id,
        created_entity_type=created_entity_type,
        ip_address=ip_address,
    )
    db.add(sub)
    form.submission_count = (form.submission_count or 0) + 1
    db.commit()

    return sub, created_entity_id


# ── Serialization helper ───────────────────────────────────────────────────

def serialize_form(form) -> dict:
    import json as _json
    return {
        "id": form.id,
        "name": form.name,
        "description": form.description,
        "form_type": form.form_type,
        "token": form.token,
        "is_active": form.is_active,
        "target_project_id": form.target_project_id,
        "target_group_id": form.target_group_id,
        "default_priority": form.default_priority,
        "default_category": form.default_category,
        "success_message": form.success_message,
        "notify_emails": _json.loads(form.notify_emails or "[]"),
        "submission_count": form.submission_count,
        "created_by": form.created_by,
        "created_at": form.created_at.isoformat() if form.created_at else None,
        "public_url": f"/intake/{form.token}",
    }
