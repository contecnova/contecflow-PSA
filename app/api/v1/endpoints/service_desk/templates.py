"""Service Desk — Templates subdomain router (ticket templates, canned responses, agent workspace, inbound email)."""
import logging
from fastapi import APIRouter, Depends, Query, Header, Body
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager, require_admin
from app.models.user import User
from app.services.service_desk.ticket_ops_service import commit_or_rollback as _commit_or_rollback
from app.schemas.service_desk import CannedResponseIn
from app.services.service_desk.ticket_template_service import (
    list_ticket_templates_payload, create_ticket_template_record,
    update_ticket_template_record, delete_ticket_template as delete_ticket_template_svc,
)
from app.services.service_desk.canned_response_service import (
    serialize_canned_response_compact, list_canned_responses_payload,
    create_canned_response_record, update_canned_response_record,
    delete_canned_response as delete_canned_response_svc,
)
from app.services.service_desk.customer_context_service import get_customer_context_payload
from app.services.service_desk.inbound_email_service import process_inbound_email

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/ticket-templates", summary="Plantillas de tickets por tipo/servicio")
def list_ticket_templates(ticket_type: Optional[str] = Query(None), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return list_ticket_templates_payload(db, ticket_type)


@router.post("/ticket-templates", summary="Crear plantilla de ticket")
def create_ticket_template(payload: dict = Body(...), db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    tmpl = create_ticket_template_record(db, payload)
    _commit_or_rollback(db); db.refresh(tmpl)
    return {"id": tmpl.id, "name": tmpl.name}


@router.patch("/ticket-templates/{template_id}", summary="Actualizar plantilla")
def update_ticket_template(template_id: str, payload: dict = Body(...), db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    update_ticket_template_record(db, template_id, payload)
    _commit_or_rollback(db)
    return {"ok": True}


@router.delete("/ticket-templates/{template_id}", summary="Eliminar plantilla")
def delete_ticket_template(template_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    delete_ticket_template_svc(db, template_id)
    _commit_or_rollback(db)
    return {"ok": True}


@router.get("/agent/customer-context/{requester_id}", summary="Contexto 360 del solicitante")
def get_customer_context(requester_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return get_customer_context_payload(db, requester_id)


@router.get("/canned-responses", summary="Listar respuestas rápidas")
def list_canned_responses(category: Optional[str] = None, search: Optional[str] = None, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    return list_canned_responses_payload(db, category, search)


@router.post("/canned-responses", summary="Crear respuesta rápida", status_code=201)
def create_canned_response(payload: CannedResponseIn, db: Session = Depends(get_db), cu: User = Depends(require_any_manager)):
    c = create_canned_response_record(db, payload, cu.id)
    _commit_or_rollback(db); db.refresh(c)
    return serialize_canned_response_compact(c)


@router.patch("/canned-responses/{canned_id}", summary="Editar respuesta rápida")
def update_canned_response(canned_id: str, payload: CannedResponseIn, db: Session = Depends(get_db), cu: User = Depends(require_any_manager)):
    c = update_canned_response_record(db, canned_id, payload)
    _commit_or_rollback(db); db.refresh(c)
    return serialize_canned_response_compact(c)


@router.delete("/canned-responses/{canned_id}", summary="Eliminar respuesta rápida")
def delete_canned_response(canned_id: str, db: Session = Depends(get_db), cu: User = Depends(require_any_manager)):
    delete_canned_response_svc(db, canned_id)
    _commit_or_rollback(db)
    return {"deleted": True}


@router.post("/inbound-email", summary="Email-to-ticket — webhook de email entrante", include_in_schema=True, status_code=201)
def inbound_email(
    payload: dict = Body(...),
    x_clarive_email_secret: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    ticket, req_email = process_inbound_email(db, payload, x_clarive_email_secret)
    _commit_or_rollback(db); db.refresh(ticket)
    logger.info("Email-to-ticket: %s from %r - %r", ticket.number, req_email, ticket.title)
    return {"ticket_id": ticket.id, "number": ticket.number, "status": "created"}
