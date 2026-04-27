"""Service Desk — Tickets subdomain router."""
from fastapi import APIRouter, Depends, Query, Header, Body, BackgroundTasks, Cookie, Response
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager
from app.models.user import User
from app.models.service_desk import Ticket, AgentGroupMember
from app.services.service_desk.ticket_ops_service import commit_or_rollback as _commit_or_rollback
from app.services.sla_service import ticket_out as _ticket_out
from app.schemas.service_desk import (
    TicketCreateIn, TicketUpdateIn, CommentIn, TimeLogIn, CSATIn, MergeIn, SplitTicketIn,
)
from app.services.service_desk.ticket_read_service import (
    list_tickets_payload, my_queue_payload, my_queue_prioritized_payload, client_my_tickets_payload,
    client_ticket_detail_payload, ticket_detail_payload,
)
from app.services.service_desk.ticket_update_service import get_scoped_ticket_or_404, apply_ticket_update
from app.services.service_desk.ticket_creation_service import build_internal_ticket, build_client_portal_ticket
from app.services.service_desk.comment_service import (
    get_scoped_ticket_or_404 as get_scoped_ticket_for_comment_or_404,
    add_internal_comment,
    get_ticket_or_404 as get_ticket_for_client_comment_or_404,
    add_client_comment as add_client_comment_svc,
)
from app.services.service_desk.csat_service import submit_ticket_csat
from app.services.service_desk.ticket_ops_service import (
    get_scoped_ticket_or_404 as get_scoped_ticket_for_ops_or_404,
    add_ticket_time, escalate_ticket_level,
)
from app.services.service_desk.link_service import (
    list_ticket_links_payload, create_ticket_link_record,
    delete_ticket_link as delete_ticket_link_svc,
)
from app.services.service_desk.sla_event_service import (
    pause_ticket_sla_from_payload, resume_ticket_sla, list_sla_events,
)
from app.services.service_desk.watcher_service import (
    list_ticket_watchers, serialize_ticket_watcher, watch_ticket_command, unwatch_ticket_command,
)
from app.services.service_desk.merge_split_service import (
    merge_ticket_command, split_ticket_command, list_ticket_merges_payload,
)
from app.services.service_desk.ai_suggest_service import build_ai_ticket_suggestion
from app.services.service_desk.workload_service import auto_assign_ticket_command, score_agent_for_ticket
from app.services.service_desk.incident_intelligence_service import score_auto_resolution
from app.services.service_desk.kb_service import create_kb_from_ticket
from app.services.service_desk.portal_auth_service import require_portal_client
from app.services.service_desk.semantic_feedback_service import (
    enqueue_profile_refresh, enqueue_reassign_feedback,
)

router = APIRouter()


@router.get("/tickets", summary="Listar tickets con filtros")
def list_tickets(
    status: Optional[str] = None, priority: Optional[str] = None,
    ticket_type: Optional[str] = None, assigned_to: Optional[str] = None,
    group_id: Optional[str] = None, project_id: Optional[str] = None,
    support_level: Optional[str] = None, sla_breached: Optional[bool] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    return list_tickets_payload(
        db=db, current_user=current_user, ticket_out=_ticket_out,
        status=status, priority=priority, ticket_type=ticket_type,
        assigned_to=assigned_to, group_id=group_id, project_id=project_id,
        support_level=support_level, sla_breached=sla_breached,
        search=search, page=page, page_size=page_size,
    )


@router.get("/tickets/my-queue", summary="Mi cola de trabajo")
def my_queue(
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200),
    response: Response = None,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    tickets = my_queue_payload(db, current_user, _ticket_out)
    total = len(tickets)
    start = (page - 1) * page_size
    items = tickets[start:start + page_size]
    if response is not None:
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
    return items


@router.get("/tickets/my-queue/prioritized", summary="Mi cola priorizada por riesgo SLA y valor de negocio")
def my_queue_prioritized(
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200),
    response: Response = None,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    tickets = my_queue_prioritized_payload(db, current_user, _ticket_out)
    total = len(tickets)
    start = (page - 1) * page_size
    items = tickets[start:start + page_size]
    if response is not None:
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
    return items


@router.get("/tickets/client/my", summary="Mis tickets (cliente)")
def client_my_tickets(
    status: Optional[str] = None,
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200),
    response: Response = None,
    authorization: Optional[str] = Header(None),
    portal_access_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
):
    client = require_portal_client(authorization, portal_access_token, db, detail="No autorizado")
    items = client_my_tickets_payload(db, client.id, _ticket_out, status)
    total = len(items)
    items = items[(page - 1) * page_size:(page - 1) * page_size + page_size]
    if response is not None:
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
    return items


@router.get("/tickets/client/{ticket_id}", summary="Detalle de ticket (cliente portal)")
def get_ticket_client(
    ticket_id: str,
    authorization: Optional[str] = Header(None),
    portal_access_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
):
    client = require_portal_client(authorization, portal_access_token, db, detail="Autenticación requerida")
    return client_ticket_detail_payload(db, client.id, ticket_id, _ticket_out)


@router.get("/tickets/{ticket_id}", summary="Detalle de ticket")
def get_ticket(ticket_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return ticket_detail_payload(db, current_user, ticket_id, _ticket_out)


@router.post("/tickets", summary="Crear ticket (agente interno)")
def create_ticket(payload: TicketCreateIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    ticket = build_internal_ticket(db, payload, current_user.id)
    _commit_or_rollback(db); db.refresh(ticket)
    return _ticket_out(ticket)


@router.post("/tickets/client", summary="Crear ticket desde portal cliente")
def create_ticket_client(
    payload: TicketCreateIn,
    authorization: Optional[str] = Header(None),
    portal_access_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
):
    client = require_portal_client(authorization, portal_access_token, db, detail="Autenticación requerida")
    ticket = build_client_portal_ticket(db, payload, client)
    _commit_or_rollback(db); db.refresh(ticket)
    return _ticket_out(ticket)


@router.patch("/tickets/{ticket_id}", summary="Actualizar ticket")
def update_ticket(
    ticket_id: str, payload: TicketUpdateIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    ticket = get_scoped_ticket_or_404(db, current_user, ticket_id)
    old_assigned_to = ticket.assigned_to_user_id
    old_support_level = ticket.support_level
    effects = apply_ticket_update(
        db=db, ticket=ticket, ticket_id=ticket_id, payload=payload,
        current_user_id=current_user.id,
        old_assigned_to=old_assigned_to, old_support_level=old_support_level,
    )
    _commit_or_rollback(db); db.refresh(ticket)
    if effects["refresh_profile"]:
        enqueue_profile_refresh(background_tasks, ticket.assigned_to_user_id)
    if effects["reassigned"]:
        enqueue_reassign_feedback(background_tasks, ticket_id, "ticket")
    return _ticket_out(ticket)


@router.post("/tickets/{ticket_id}/comments", summary="Añadir comentario")
def add_comment(
    ticket_id: str, payload: CommentIn,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db), current_user: Optional[User] = Depends(get_current_user),
):
    ticket = get_scoped_ticket_for_comment_or_404(db, current_user, ticket_id)
    comment = add_internal_comment(db, ticket, ticket_id, payload.body, payload.is_public, current_user)
    _commit_or_rollback(db); db.refresh(comment)
    return {
        "id": comment.id, "body": comment.body, "is_public": comment.is_public,
        "author_name": current_user.full_name if current_user else "Cliente",
        "created_at": str(comment.created_at)[:16],
    }


@router.post("/tickets/{ticket_id}/comments/client", summary="Comentario del cliente")
def add_client_comment(
    ticket_id: str, payload: CommentIn,
    authorization: Optional[str] = Header(None),
    portal_access_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
):
    client = require_portal_client(authorization, portal_access_token, db, detail="No autorizado")
    ticket = get_ticket_for_client_comment_or_404(db, ticket_id)
    comment = add_client_comment_svc(db, ticket, ticket_id, payload.body, client.id)
    _commit_or_rollback(db)
    return {"id": comment.id, "created_at": str(comment.created_at)[:16]}


@router.post("/tickets/{ticket_id}/time-log", summary="Registrar tiempo")
def log_time(ticket_id: str, payload: TimeLogIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    ticket = get_scoped_ticket_for_ops_or_404(db, current_user, ticket_id)
    result = add_ticket_time(db, ticket, ticket_id, current_user.id, payload.minutes, payload.description)
    _commit_or_rollback(db)
    return result


@router.post("/tickets/{ticket_id}/escalate", summary="Escalar ticket")
def escalate_ticket(
    ticket_id: str, to_level: str = Query(...), reason: Optional[str] = Query(None),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    ticket = get_scoped_ticket_for_ops_or_404(db, current_user, ticket_id)
    result = escalate_ticket_level(db, ticket, ticket_id, to_level, reason, current_user.id)
    _commit_or_rollback(db)
    return result


@router.post("/tickets/{ticket_id}/csat", summary="Valoración de satisfacción")
def submit_csat(
    ticket_id: str, payload: CSATIn,
    authorization: Optional[str] = Header(None),
    portal_access_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
):
    require_portal_client(authorization, portal_access_token, db, detail="Autenticación requerida")
    result = submit_ticket_csat(db, ticket_id, payload.score, payload.comment)
    _commit_or_rollback(db)
    return result


@router.get("/tickets/{ticket_id}/links", summary="Ver tickets vinculados")
def get_ticket_links(ticket_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return list_ticket_links_payload(db, ticket_id)


@router.post("/tickets/{ticket_id}/links", summary="Vincular tickets")
def link_tickets(ticket_id: str, payload: dict = Body(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    lk = create_ticket_link_record(db, ticket_id, payload, current_user.id)
    _commit_or_rollback(db)
    return {"ok": True, "link_id": lk.id}


@router.delete("/tickets/{ticket_id}/links/{link_id}", summary="Eliminar vínculo")
def delete_ticket_link(ticket_id: str, link_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    delete_ticket_link_svc(db, link_id)
    _commit_or_rollback(db)
    return {"ok": True}


@router.post("/tickets/{ticket_id}/sla/pause", summary="Pausar SLA")
def pause_sla(ticket_id: str, payload: dict = Body(default={}), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = pause_ticket_sla_from_payload(db, ticket_id, current_user.id, payload)
    _commit_or_rollback(db)
    return result


@router.post("/tickets/{ticket_id}/sla/resume", summary="Reanudar SLA")
def resume_sla(ticket_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = resume_ticket_sla(db, ticket_id, current_user.id)
    _commit_or_rollback(db)
    return result


@router.get("/tickets/{ticket_id}/sla/events", summary="Historial de eventos SLA")
def get_sla_events(ticket_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return list_sla_events(db, ticket_id)


@router.get("/tickets/{ticket_id}/watchers", summary="Ver seguidores del ticket")
def get_watchers(ticket_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return [serialize_ticket_watcher(w) for w in list_ticket_watchers(db, ticket_id)]


@router.post("/tickets/{ticket_id}/watch", summary="Seguir ticket", status_code=201)
def watch_ticket(ticket_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = watch_ticket_command(db, ticket_id, current_user.id)
    _commit_or_rollback(db)
    return result


@router.delete("/tickets/{ticket_id}/watch", summary="Dejar de seguir ticket")
def unwatch_ticket(ticket_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = unwatch_ticket_command(db, ticket_id, current_user.id)
    _commit_or_rollback(db)
    return result


@router.post("/tickets/{ticket_id}/merge", summary="Fusionar ticket duplicado en éste")
def merge_ticket(ticket_id: str, payload: MergeIn, db: Session = Depends(get_db), current_user: User = Depends(require_any_manager)):
    result = merge_ticket_command(db, ticket_id, payload.merged_ticket_id, payload.reason, current_user.id)
    _commit_or_rollback(db)
    return result


@router.post("/tickets/{ticket_id}/split", summary="Dividir ticket en ticket hijo")
def split_ticket(ticket_id: str, payload: SplitTicketIn, db: Session = Depends(get_db), current_user: User = Depends(require_any_manager)):
    result = split_ticket_command(db=db, ticket_id=ticket_id, payload=payload, current_user_id=current_user.id)
    _commit_or_rollback(db); db.refresh(result["child"])
    return {"ok": True, "parent": result["parent"].number, "child": result["child"].number, "child_id": result["child"].id}


@router.post("/tickets/{ticket_id}/ai-suggest", summary="Sugerir respuesta IA para ticket")
def suggest_ticket_response_ai(ticket_id: str, payload: Optional[dict] = Body(default=None), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return build_ai_ticket_suggestion(db, ticket_id, payload, current_user)


@router.post("/tickets/{ticket_id}/auto-assign", summary="Auto-asignar ticket al agente con menos carga del grupo")
def auto_assign_ticket(ticket_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_any_manager)):
    result = auto_assign_ticket_command(db, ticket_id, current_user.id)
    _commit_or_rollback(db)
    return result


@router.get("/tickets/{ticket_id}/ai-explain", summary="Explicación de confianza IA para asignación y auto-resolución")
def explain_ai_decision(ticket_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        return {"ok": False, "error": "Ticket no encontrado"}

    auto_resolution = score_auto_resolution(db, ticket)
    candidates = []
    if ticket.assigned_group_id:
        members = db.query(AgentGroupMember).filter(AgentGroupMember.group_id == ticket.assigned_group_id).all()
        for member in members:
            candidates.append(
                {
                    "user_id": member.user_id,
                    "assignment_score": score_agent_for_ticket(db, member.user_id, ticket),
                }
            )
        candidates.sort(key=lambda c: c["assignment_score"], reverse=True)

    return {
        "ticket_id": ticket.id,
        "ticket_number": ticket.number,
        "auto_resolution": auto_resolution,
        "assignment_candidates": candidates[:5],
        "confidence_trace": {
            "auto_resolution_threshold": 85,
            "routing_method": "ml_score_v1",
        },
    }


@router.get("/tickets/{ticket_id}/merges", summary="Ver merges de un ticket")
def get_merges(ticket_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return list_ticket_merges_payload(db, ticket_id)


@router.post("/tickets/{ticket_id}/to-kb", summary="Convertir resolución de ticket en artículo KB")
def ticket_to_kb(ticket_id: str, title: str = Query(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    a = create_kb_from_ticket(db, ticket_id, title, current_user.id)
    _commit_or_rollback(db); db.refresh(a)
    return {"id": a.id, "number": a.number}
