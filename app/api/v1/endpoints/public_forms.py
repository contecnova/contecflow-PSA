"""
Public intake forms — anonymous form submissions that auto-create tickets.
Endpoints:
  Authenticated (admin/pm):
    GET    /forms                  — list own forms
    POST   /forms                  — create form
    GET    /forms/{id}             — get form detail
    PATCH  /forms/{id}             — update form
    DELETE /forms/{id}             — delete form
    GET    /forms/{id}/submissions — list submissions for a form

  Public (no auth required):
    GET    /forms/public/{token}   — get form metadata for rendering
    POST   /forms/public/{token}/submit — submit form (creates ticket)
"""
import json
import logging
import secrets
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.ratelimit import limiter
from app.models.public_forms import PublicForm, PublicFormSubmission
from app.models.service_desk import Ticket, TicketStatus, TicketType, TicketPriority
from app.models.user import User, UserRole

router = APIRouter(prefix="/forms", tags=["Public Forms"])
log = logging.getLogger(__name__)


# ── Pydantic schemas ───────────────────────────────────────────────────────────

class FormCreateIn(BaseModel):
    name: str
    description: Optional[str] = None
    form_type: str = "ticket"          # ticket | task
    is_active: bool = True
    target_project_id: Optional[str] = None
    target_group_id: Optional[str] = None
    default_priority: str = "medium"
    default_category: Optional[str] = None
    success_message: Optional[str] = None
    notify_emails: list[str] = []


class FormUpdateIn(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    target_project_id: Optional[str] = None
    target_group_id: Optional[str] = None
    default_priority: Optional[str] = None
    default_category: Optional[str] = None
    success_message: Optional[str] = None
    notify_emails: Optional[list[str]] = None


class SubmitFormIn(BaseModel):
    submitter_name: Optional[str] = None
    submitter_email: Optional[EmailStr] = None
    subject: str
    description: Optional[str] = None
    priority: Optional[str] = None
    category: Optional[str] = None
    extra_fields: dict = {}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _form_out(form: PublicForm) -> dict:
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
        "notify_emails": json.loads(form.notify_emails or "[]"),
        "submission_count": form.submission_count,
        "created_by": form.created_by,
        "created_at": form.created_at.isoformat() if form.created_at else None,
        "public_url": f"/intake/{form.token}",
    }


# ── Authenticated endpoints ────────────────────────────────────────────────────

@router.get("", summary="Listar formularios públicos")
def list_forms(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    forms = db.query(PublicForm).filter(PublicForm.created_by == current_user.id).all()
    return [_form_out(f) for f in forms]


@router.post("", summary="Crear formulario público", status_code=201)
def create_form(
    payload: FormCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    form = PublicForm(
        id=str(uuid.uuid4()),
        name=payload.name,
        description=payload.description,
        form_type=payload.form_type,
        token=secrets.token_urlsafe(32),
        is_active=payload.is_active,
        target_project_id=payload.target_project_id,
        target_group_id=payload.target_group_id,
        default_priority=payload.default_priority,
        default_category=payload.default_category,
        success_message=payload.success_message,
        notify_emails=json.dumps(payload.notify_emails),
        created_by=current_user.id,
    )
    db.add(form)
    db.commit()
    db.refresh(form)
    return _form_out(form)


@router.get("/{form_id}", summary="Detalle de formulario")
def get_form(form_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    form = db.query(PublicForm).filter(PublicForm.id == form_id).first()
    if not form:
        raise HTTPException(404, "Formulario no encontrado")
    return _form_out(form)


@router.patch("/{form_id}", summary="Actualizar formulario")
def update_form(
    form_id: str,
    payload: FormUpdateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    form = db.query(PublicForm).filter(PublicForm.id == form_id).first()
    if not form:
        raise HTTPException(404, "Formulario no encontrado")
    if form.created_by != current_user.id and current_user.role != UserRole.admin:
        raise HTTPException(403, "Acceso denegado")
    for field, value in payload.model_dump(exclude_none=True).items():
        if field == "notify_emails":
            setattr(form, field, json.dumps(value))
        else:
            setattr(form, field, value)
    db.commit()
    db.refresh(form)
    return _form_out(form)


@router.delete("/{form_id}", summary="Eliminar formulario", status_code=204)
def delete_form(form_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    form = db.query(PublicForm).filter(PublicForm.id == form_id).first()
    if not form:
        raise HTTPException(404, "Formulario no encontrado")
    if form.created_by != current_user.id and current_user.role != UserRole.admin:
        raise HTTPException(403, "Acceso denegado")
    db.delete(form)
    db.commit()


@router.get("/{form_id}/submissions", summary="Envíos de un formulario")
def list_submissions(form_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    form = db.query(PublicForm).filter(PublicForm.id == form_id).first()
    if not form:
        raise HTTPException(404, "Formulario no encontrado")
    if form.created_by != current_user.id and current_user.role != UserRole.admin:
        raise HTTPException(403, "Acceso denegado")
    subs = db.query(PublicFormSubmission).filter(PublicFormSubmission.form_id == form_id).order_by(
        PublicFormSubmission.submitted_at.desc()
    ).all()
    return [
        {
            "id": s.id,
            "submitter_name": s.submitter_name,
            "submitter_email": s.submitter_email,
            "subject": s.subject,
            "description": s.description,
            "priority": s.priority,
            "category": s.category,
            "created_entity_id": s.created_entity_id,
            "created_entity_type": s.created_entity_type,
            "submitted_at": s.submitted_at.isoformat() if s.submitted_at else None,
        }
        for s in subs
    ]


# ── Public (unauthenticated) endpoints ────────────────────────────────────────

@router.get("/public/{token}", summary="Obtener metadatos de formulario público")
def get_public_form(token: str, db: Session = Depends(get_db)):
    form = db.query(PublicForm).filter(PublicForm.token == token, PublicForm.is_active == True).first()
    if not form:
        raise HTTPException(404, "Formulario no encontrado o inactivo")
    return {
        "id": form.id,
        "name": form.name,
        "description": form.description,
        "form_type": form.form_type,
        "default_priority": form.default_priority,
        "default_category": form.default_category,
        "success_message": form.success_message or "¡Gracias! Tu solicitud ha sido enviada.",
    }


@router.post("/public/{token}/submit", summary="Enviar formulario público", status_code=201)
@limiter.limit("10/minute")
def submit_public_form(
    token: str,
    payload: SubmitFormIn,
    request: Request,
    db: Session = Depends(get_db),
):
    form = db.query(PublicForm).filter(PublicForm.token == token, PublicForm.is_active == True).first()
    if not form:
        raise HTTPException(404, "Formulario no encontrado o inactivo")

    priority = payload.priority or form.default_priority
    category = payload.category or form.default_category
    ip = request.client.host if request.client else None

    # Create a ticket (service desk form_type)
    created_entity_id = None
    created_entity_type = None

    if form.form_type == "ticket":
        sp = db.begin_nested()  # savepoint — protects the outer transaction
        try:
            ticket = Ticket(
                number=_next_ticket_number("incident", db),
                ticket_type=TicketType.incident,
                title=payload.subject[:255],
                description=payload.description or "",
                priority=_map_priority(priority),
                support_level="l1",
                project_id=form.target_project_id,
                assigned_group_id=form.target_group_id,
                requester_name=payload.submitter_name,
                requester_email=payload.submitter_email,
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
            log.warning("Ticket creation failed during form submit (form=%s): %s", form.id, exc)

    # Record submission
    sub = PublicFormSubmission(
        id=str(uuid.uuid4()),
        form_id=form.id,
        submitter_name=payload.submitter_name,
        submitter_email=payload.submitter_email,
        subject=payload.subject,
        description=payload.description,
        priority=priority,
        category=category,
        extra_fields=json.dumps(payload.extra_fields),
        created_entity_id=created_entity_id,
        created_entity_type=created_entity_type,
        ip_address=ip,
    )
    db.add(sub)

    # Increment counter
    form.submission_count = (form.submission_count or 0) + 1

    db.commit()

    return {
        "ok": True,
        "message": form.success_message or "¡Gracias! Tu solicitud ha sido enviada.",
        "submission_id": sub.id,
        "ticket_id": created_entity_id,
    }


# ── Internal helpers ───────────────────────────────────────────────────────────

def _next_ticket_number(ticket_type: str, db: Session) -> str:
    from sqlalchemy import func, cast, Integer
    PREFIXES = {"incident": "INC", "service_request": "REQ", "change": "CHG", "problem": "PRB"}
    prefix = PREFIXES.get(ticket_type, "TKT")
    last_num = db.query(
        func.max(cast(func.substr(Ticket.number, len(prefix) + 2), Integer))
    ).filter(Ticket.ticket_type == ticket_type).scalar() or 0
    return f"{prefix}-{(last_num + 1):04d}"


def _map_priority(p: str) -> TicketPriority:
    mapping = {
        "critical": TicketPriority.p1_critical,
        "high": TicketPriority.p2_high,
        "medium": TicketPriority.p3_medium,
        "low": TicketPriority.p4_low,
    }
    return mapping.get(p, TicketPriority.p3_medium)
