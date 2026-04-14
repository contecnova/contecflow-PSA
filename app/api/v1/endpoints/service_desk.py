"""
Service Desk ITSM/ITIL API – full ITIL-aligned endpoints.
Works standalone OR integrated with Clarive projects/contracts.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Header, Body, BackgroundTasks, Cookie
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_, or_, cast, Integer
from typing import Optional
from datetime import datetime, timedelta, date, timezone, time as dt_time
import json
import math
import logging

from app.db.session import get_db
from app.core.config import settings
from app.core.deps import get_current_user, require_any_manager, require_admin
from app.models.user import User, UserRole
from app.models.service_desk import (
    ServiceCategory, ServiceItem, SLAPolicy,
    ConfigurationItem, AgentGroup, AgentGroupMember,
    Ticket, TicketStatus, TicketPriority,
    TicketComment, TicketHistory, TicketTimeLog,
    Problem, KBArticle, KBStatus, Announcement,
    CannedResponse,
    # v3 — market-leader extensions
    OnCallSchedule, OnCallEntry,
    TicketWatcher, TicketMerge,
    EscalationRule, EscalationLog, EscalationTrigger, EscalationAction,
    SDSLAHoliday,
    Asset, AssetHistory, AssetType, AssetStatus,
    StatusPageComponent, StatusPageIncident, StatusPageComponentStatus,
)
from app.models.client_portal import ClientUser
from app.models.clients import Client
from app.models.pipeline import Contract
from app.models.project import Project

router = APIRouter()
logger = logging.getLogger(__name__)


def _commit_or_rollback(db: Session, detail: str = "Error de transacción") -> None:
    try:
        Session.commit(db)
    except Exception:
        db.rollback()
        logger.exception("Database transaction failed in service_desk")
        raise HTTPException(500, detail)

# ── Service layer & schemas ───────────────────────────────────────────────────
from app.services.sla_service import (  # noqa: E402
    PRIORITY_MATRIX, TICKET_PREFIXES, PRIORITY_LABELS, STATUS_LABELS,
    TYPE_LABELS, SLA_HOURS,
    norm_enum as _norm_enum, aware as _aware,
    advisory_lock_key as _advisory_lock_key,
    add_working_hours as _add_working_hours,
    compute_sla_status as _compute_sla_status,
    calculate_sla_due as _calculate_sla_due,
    next_ticket_number as _next_ticket_number,
    next_problem_number as _next_problem_number,
    next_kb_number as _next_kb_number,
    next_ci_number as _next_ci_number,
    log_history as _log_history,
    get_client_from_token as _get_client_from_token,
    ticket_out as _ticket_out,
)
from app.schemas.service_desk import (  # noqa: E402
    TicketCreateIn, TicketUpdateIn, CommentIn, TimeLogIn, CSATIn, MergeIn,
    SplitTicketIn,
    ProblemIn, ProblemUpdateIn,
    KBArticleIn, KBArticleUpdate,
    ServiceCategoryIn, ServiceItemIn, ServiceItemUpdate,
    SLAPolicyIn, HolidayIn,
    CIIn, AgentGroupIn, AnnouncementIn,
    EscalationRuleIn, AssetIn, AssetUpdate,
    StatusComponentIn, StatusIncidentIn, StatusIncidentUpdateIn,
    CannedResponseIn, OnCallScheduleIn, OnCallEntryIn,
)
from app.services.service_desk.scoping import (  # noqa: E402
    resolve_sla_policy_for_ticket as _resolve_sla_policy_for_ticket,
    scope_ticket_query as _scope_ticket_query,
    scope_problem_query as _scope_problem_query,
    scope_ci_query as _scope_ci_query,
    scope_kb_query as _scope_kb_query,
    _org_user_ids_subquery,
)


def _portal_client_from_auth(
    authorization: Optional[str],
    portal_access_token: Optional[str],
    db: Session,
) -> Optional[ClientUser]:
    token_value = authorization
    if not token_value and portal_access_token:
        token_value = f"Bearer {portal_access_token}"
    return _get_client_from_token(token_value, db)


def _scope_change_query(q, db: Session, current_user: User):
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

# ── Service Catalog ───────────────────────────────────────────────────────────

@router.get("/catalog", summary="Catálogo de servicios")
def get_catalog(
    public_only: bool = False,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
):
    q = db.query(ServiceCategory).options(
        joinedload(ServiceCategory.services)
    ).filter(ServiceCategory.is_active == True)
    cats = q.order_by(ServiceCategory.sort_order).all()
    result = []
    for cat in cats:
        services = [s for s in cat.services if s.is_active and (not public_only or s.is_visible_to_clients)]
        if services:
            result.append({
                "id": cat.id, "name": cat.name, "description": cat.description,
                "icon": cat.icon, "color": cat.color,
                "services": [{
                    "id": s.id, "name": s.name, "description": s.description,
                    "ticket_type": s.ticket_type, "default_priority": s.default_priority,
                    "sla_response_hours": s.sla_response_hours,
                    "sla_resolution_hours": s.sla_resolution_hours,
                    "requires_approval": s.requires_approval,
                } for s in sorted(services, key=lambda x: x.sort_order)],
            })
    return result

@router.post("/catalog/categories", summary="Crear categoría")
def create_category(payload: ServiceCategoryIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    c = ServiceCategory(**payload.model_dump()); db.add(c); _commit_or_rollback(db); db.refresh(c)
    return {"id": c.id, "name": c.name}

@router.patch("/catalog/categories/{cat_id}", summary="Actualizar categoría")
def update_category(cat_id: str, payload: ServiceCategoryIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    c = db.query(ServiceCategory).filter(ServiceCategory.id == cat_id).first()
    if not c: raise HTTPException(404, "Categoría no encontrada")
    for k, v in payload.model_dump(exclude_unset=True).items(): setattr(c, k, v)
    _commit_or_rollback(db); return {"id": c.id, "name": c.name}

@router.delete("/catalog/categories/{cat_id}", summary="Desactivar categoría")
def delete_category(cat_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    c = db.query(ServiceCategory).filter(ServiceCategory.id == cat_id).first()
    if not c: raise HTTPException(404, "Categoría no encontrada")
    c.is_active = False; _commit_or_rollback(db); return {"ok": True}

@router.post("/catalog/services", summary="Crear servicio")
def create_service(payload: ServiceItemIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    s = ServiceItem(**payload.model_dump()); db.add(s); _commit_or_rollback(db); db.refresh(s)
    return {"id": s.id, "name": s.name}

@router.patch("/catalog/services/{service_id}", summary="Actualizar servicio")
def update_service(service_id: str, payload: ServiceItemUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    s = db.query(ServiceItem).filter(ServiceItem.id == service_id).first()
    if not s: raise HTTPException(404, "No encontrado")
    for k, v in payload.model_dump(exclude_unset=True).items(): setattr(s, k, v)
    _commit_or_rollback(db); return {"ok": True}

@router.delete("/catalog/services/{service_id}", summary="Desactivar servicio")
def delete_service(service_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    s = db.query(ServiceItem).filter(ServiceItem.id == service_id).first()
    if not s: raise HTTPException(404)
    s.is_active = False; _commit_or_rollback(db); return {"ok": True}


# ── SLA Policies ──────────────────────────────────────────────────────────────

@router.get("/sla-policies", summary="Políticas de SLA")
def get_sla_policies(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    policies = db.query(SLAPolicy).filter(SLAPolicy.is_active == True).all()
    return [{
        "id": p.id, "name": p.name, "description": p.description,
        "is_default": p.is_default,
        "p1_response_hours": p.p1_response_hours, "p1_resolution_hours": p.p1_resolution_hours,
        "p2_response_hours": p.p2_response_hours, "p2_resolution_hours": p.p2_resolution_hours,
        "p3_response_hours": p.p3_response_hours, "p3_resolution_hours": p.p3_resolution_hours,
        "p4_response_hours": p.p4_response_hours, "p4_resolution_hours": p.p4_resolution_hours,
        "business_hours_only": p.business_hours_only,
    } for p in policies]

@router.post("/sla-policies", summary="Crear política SLA")
def create_sla_policy(payload: SLAPolicyIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if payload.is_default:
        db.query(SLAPolicy).update({"is_default": False})
    p = SLAPolicy(**payload.model_dump()); db.add(p); _commit_or_rollback(db); db.refresh(p)
    return {"id": p.id, "name": p.name}


# ── Agent Groups ──────────────────────────────────────────────────────────────

@router.get("/groups", summary="Grupos de agentes")
def get_groups(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    groups = db.query(AgentGroup).options(
        joinedload(AgentGroup.members).joinedload(AgentGroupMember.user)
    ).filter(AgentGroup.is_active == True).all()
    return [{
        "id": g.id, "name": g.name, "description": g.description,
        "support_level": g.support_level,
        "members": [{"id": m.user_id, "full_name": m.user.full_name, "is_lead": m.is_lead} for m in g.members if m.user],
    } for g in groups]

@router.patch("/sla-policies/{policy_id}", summary="Actualizar política SLA")
def update_sla_policy(policy_id: str, payload: SLAPolicyIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    p = db.query(SLAPolicy).filter(SLAPolicy.id == policy_id).first()
    if not p: raise HTTPException(404, "Política SLA no encontrada")
    if payload.is_default:
        db.query(SLAPolicy).filter(SLAPolicy.id != policy_id).update({"is_default": False})
    for k, v in payload.model_dump(exclude_unset=True).items(): setattr(p, k, v)
    _commit_or_rollback(db); return {"id": p.id, "name": p.name}

@router.delete("/sla-policies/{policy_id}", summary="Eliminar política SLA")
def delete_sla_policy(policy_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    p = db.query(SLAPolicy).filter(SLAPolicy.id == policy_id).first()
    if not p: raise HTTPException(404, "Política SLA no encontrada")
    p.is_active = False; _commit_or_rollback(db); return {"ok": True}

@router.post("/groups", summary="Crear grupo")
def create_group(payload: AgentGroupIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    g = AgentGroup(**payload.model_dump()); db.add(g); _commit_or_rollback(db); db.refresh(g)
    return {"id": g.id, "name": g.name}

@router.patch("/groups/{group_id}", summary="Actualizar grupo")
def update_group(group_id: str, payload: AgentGroupIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    g = db.query(AgentGroup).filter(AgentGroup.id == group_id).first()
    if not g: raise HTTPException(404, "Grupo no encontrado")
    for k, v in payload.model_dump(exclude_unset=True).items(): setattr(g, k, v)
    _commit_or_rollback(db); return {"id": g.id, "name": g.name}

@router.delete("/groups/{group_id}", summary="Eliminar grupo")
def delete_group(group_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    g = db.query(AgentGroup).filter(AgentGroup.id == group_id).first()
    if not g: raise HTTPException(404, "Grupo no encontrado")
    g.is_active = False; _commit_or_rollback(db); return {"ok": True}

@router.post("/groups/{group_id}/members/{user_id}", summary="Añadir miembro a grupo")
def add_group_member(group_id: str, user_id: str, is_lead: bool = False, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if not db.query(AgentGroup).filter(AgentGroup.id == group_id).first():
        raise HTTPException(404, "Grupo no encontrado")
    if not db.query(User).filter(User.id == user_id).first():
        raise HTTPException(404, "Usuario no encontrado")
    if db.query(AgentGroupMember).filter(AgentGroupMember.group_id == group_id, AgentGroupMember.user_id == user_id).first():
        raise HTTPException(400, "Ya es miembro")
    db.add(AgentGroupMember(group_id=group_id, user_id=user_id, is_lead=is_lead)); _commit_or_rollback(db)
    return {"ok": True}

@router.delete("/groups/{group_id}/members/{user_id}", summary="Eliminar miembro de grupo")
def remove_group_member(group_id: str, user_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    m = db.query(AgentGroupMember).filter(AgentGroupMember.group_id == group_id, AgentGroupMember.user_id == user_id).first()
    if not m: raise HTTPException(404)
    db.delete(m); _commit_or_rollback(db); return {"ok": True}


# ── Tickets ───────────────────────────────────────────────────────────────────

@router.get("/tickets", summary="Listar tickets con filtros")
def list_tickets(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    ticket_type: Optional[str] = None,
    assigned_to: Optional[str] = None,
    group_id: Optional[str] = None,
    project_id: Optional[str] = None,
    support_level: Optional[str] = None,
    sla_breached: Optional[bool] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Ticket).options(
        joinedload(Ticket.requester_user),
        joinedload(Ticket.requester_client),
        joinedload(Ticket.assigned_to),
        joinedload(Ticket.assigned_group),
        joinedload(Ticket.project),
        joinedload(Ticket.ci),
        joinedload(Ticket.client),
    )
    # Scope to current user's organisation (superadmins see everything)
    if not current_user.is_superadmin:
        if current_user.role in (UserRole.employee, UserRole.subcontractor):
            # Employees only see their own tickets
            q = q.filter(Ticket.requester_user_id == current_user.id)
        elif current_user.organization_id:
            # Managers/admins see tickets belonging to users in their org
            org_user_ids = db.query(User.id).filter(
                User.organization_id == current_user.organization_id
            ).scalar_subquery()
            q = q.filter(
                or_(
                    Ticket.requester_user_id.in_(org_user_ids),
                    Ticket.assigned_to_user_id.in_(org_user_ids),
                )
            )
    if status: q = q.filter(Ticket.status == status)
    if priority: q = q.filter(Ticket.priority == priority)
    if ticket_type: q = q.filter(Ticket.ticket_type == ticket_type)
    if assigned_to: q = q.filter(Ticket.assigned_to_user_id == assigned_to)
    if group_id: q = q.filter(Ticket.assigned_group_id == group_id)
    if project_id: q = q.filter(Ticket.project_id == project_id)
    if support_level: q = q.filter(Ticket.support_level == support_level)
    if sla_breached:
        now = datetime.now(timezone.utc)
        q = q.filter(
            Ticket.status.notin_(["resolved", "closed", "cancelled"]),
            or_(Ticket.sla_response_due < now, Ticket.sla_resolution_due < now)
        )
    if search:
        q = q.filter(or_(Ticket.number.ilike(f"%{search}%"), Ticket.title.ilike(f"%{search}%")))

    total = q.count()
    tickets = q.order_by(Ticket.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"tickets": [_ticket_out(t) for t in tickets], "total": total, "page": page, "pages": math.ceil(total / page_size)}


@router.get("/tickets/my-queue", summary="Mi cola de trabajo")
def my_queue(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tickets = db.query(Ticket).options(
        joinedload(Ticket.requester_user),
        joinedload(Ticket.requester_client),
        joinedload(Ticket.project),
    ).filter(
        Ticket.assigned_to_user_id == current_user.id,
        Ticket.status.notin_(["resolved", "closed", "cancelled"])
    ).order_by(Ticket.priority, Ticket.created_at).all()
    return [_ticket_out(t) for t in tickets]



@router.get("/tickets/client/my", summary="Mis tickets (cliente)")
def client_my_tickets(
    status: Optional[str] = None,
    authorization: Optional[str] = Header(None),
    portal_access_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
):
    client = _portal_client_from_auth(authorization, portal_access_token, db)
    if not client: raise HTTPException(401)
    q = db.query(Ticket).options(
        joinedload(Ticket.assigned_to), joinedload(Ticket.assigned_group),
        joinedload(Ticket.project),
    ).filter(Ticket.requester_client_id == client.id)
    if status: q = q.filter(Ticket.status == status)
    return [_ticket_out(t) for t in q.order_by(Ticket.created_at.desc()).all()]


# ── Problem Management ────────────────────────────────────────────────────────


@router.get("/tickets/client/{ticket_id}", summary="Detalle de ticket (cliente portal)")
def get_ticket_client(
    ticket_id: str,
    authorization: Optional[str] = Header(None),
    portal_access_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
):
    """Endpoint para que el cliente del portal vea el detalle de uno de sus tickets."""
    client = _portal_client_from_auth(authorization, portal_access_token, db)
    if not client:
        raise HTTPException(401, "Autenticación requerida")

    t = db.query(Ticket).options(
        joinedload(Ticket.requester_user), joinedload(Ticket.requester_client),
        joinedload(Ticket.assigned_to), joinedload(Ticket.assigned_group),
        joinedload(Ticket.project),
        joinedload(Ticket.comments).joinedload(TicketComment.author_user),
        joinedload(Ticket.comments).joinedload(TicketComment.author_client),
    ).filter(
        Ticket.id == ticket_id,
        Ticket.requester_client_id == client.id,  # Solo sus propios tickets
    ).first()

    if not t:
        raise HTTPException(404, "Ticket no encontrado")

    return _ticket_out(t, include_comments=True)



@router.get("/tickets/{ticket_id}", summary="Detalle de ticket")
def get_ticket(ticket_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = db.query(Ticket).options(
        joinedload(Ticket.requester_user), joinedload(Ticket.requester_client),
        joinedload(Ticket.assigned_to), joinedload(Ticket.assigned_group),
        joinedload(Ticket.project), joinedload(Ticket.ci),
        joinedload(Ticket.comments).joinedload(TicketComment.author_user),
        joinedload(Ticket.comments).joinedload(TicketComment.author_client),
        joinedload(Ticket.history).joinedload(TicketHistory.changed_by),
        joinedload(Ticket.time_logs),
    )
    t = _scope_ticket_query(q, db, current_user).filter(Ticket.id == ticket_id).first()
    if not t: raise HTTPException(404, "Ticket no encontrado")
    return _ticket_out(t, include_comments=True)


@router.post("/tickets", summary="Crear ticket (agente interno)")
def create_ticket(
    payload: TicketCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Auto-calculate priority from urgency × impact if not provided
    priority = payload.priority
    if not priority:
        priority = PRIORITY_MATRIX.get((_norm_enum(payload.urgency), _norm_enum(payload.impact)), "p3_medium")

    # Get SLA policy (contract/client override default)
    sla_policy = _resolve_sla_policy_for_ticket(
        db,
        contract_id=payload.contract_id,
        client_id=payload.client_id,
    )
    resp_due, res_due = _calculate_sla_due(priority, sla_policy, db=db)

    # If service item provided, override defaults
    service_item = None
    if payload.service_item_id:
        service_item = db.query(ServiceItem).filter(ServiceItem.id == payload.service_item_id).first()
        if service_item:
            if not payload.priority:
                priority = service_item.default_priority.value if hasattr(service_item.default_priority, 'value') else service_item.default_priority
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
        support_level=service_item.default_support_level.value if service_item and hasattr(service_item.default_support_level, 'value') else "l1",
        project_id=payload.project_id,
        client_id=payload.client_id,
        contract_id=payload.contract_id,
        ci_id=payload.ci_id,
        service_item_id=payload.service_item_id,
        assigned_to_user_id=payload.assigned_to_user_id,
        assigned_group_id=payload.assigned_group_id,
        requester_user_id=current_user.id,
        requester_name=payload.requester_name,
        requester_email=payload.requester_email,
        tags=payload.tags,
        source=payload.source,
        sla_policy_id=sla_policy.id if sla_policy else None,
        sla_response_due=resp_due,
        sla_resolution_due=res_due,
        created_by_user_id=current_user.id,
    )
    db.add(ticket)
    _apply_routing_rules(ticket, db)
    if payload.assigned_to_user_id:
        ticket.status = TicketStatus.assigned
    _commit_or_rollback(db); db.refresh(ticket)
    return _ticket_out(ticket)


@router.post("/tickets/client", summary="Crear ticket desde portal cliente")
def create_ticket_client(
    payload: TicketCreateIn,
    authorization: Optional[str] = Header(None),
    portal_access_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
):
    client = _portal_client_from_auth(authorization, portal_access_token, db)
    if not client: raise HTTPException(401, "Autenticación requerida")

    priority = payload.priority
    if not priority:
        priority = PRIORITY_MATRIX.get((_norm_enum(payload.urgency), _norm_enum(payload.impact)), "p3_medium")

    sla_policy = _resolve_sla_policy_for_ticket(
        db,
        contract_id=payload.contract_id,
        client_id=client.client_org_id,
    )
    resp_due, res_due = _calculate_sla_due(priority, sla_policy, db=db)

    service_item = None
    if payload.service_item_id:
        service_item = db.query(ServiceItem).filter(ServiceItem.id == payload.service_item_id).first()
        if service_item:
            resp_due = datetime.now(timezone.utc) + timedelta(hours=service_item.sla_response_hours)
            res_due = datetime.now(timezone.utc) + timedelta(hours=service_item.sla_resolution_hours)

    # Always use client's own project_id — prevents portal users from creating
    # tickets on behalf of projects they don't belong to.
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
    db.add(ticket); _commit_or_rollback(db); db.refresh(ticket)
    return _ticket_out(ticket)


@router.patch("/tickets/{ticket_id}", summary="Actualizar ticket")
def update_ticket(
    ticket_id: str,
    payload: TicketUpdateIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = _scope_ticket_query(db.query(Ticket), db, current_user).filter(Ticket.id == ticket_id).first()
    if not ticket: raise HTTPException(404, "Ticket no encontrado")

    old_support_level = ticket.support_level  # Capturar ANTES del loop
    old_assigned_to   = ticket.assigned_to_user_id

    changes = payload.model_dump(exclude_unset=True)
    for field, new_val in changes.items():
        old_val = getattr(ticket, field, None)
        _log_history(db, ticket_id, field, old_val, new_val, current_user.id)
        setattr(ticket, field, new_val)

    now = datetime.now(timezone.utc)

    # Handle status transitions
    if payload.status:
        if payload.status == "in_progress":
            if not ticket.first_response_at:
                ticket.first_response_at = now
            # Resume SLA if coming back from pending_client
            if ticket.sla_paused_at:
                paused_at = ticket.sla_paused_at
                if paused_at.tzinfo is None:
                    paused_at = paused_at.replace(tzinfo=timezone.utc)
                paused_mins = int((now - paused_at).total_seconds() / 60)
                ticket.sla_pause_minutes = (ticket.sla_pause_minutes or 0) + paused_mins
                ticket.sla_paused_at = None
        elif payload.status == "resolved":
            ticket.resolved_at = now
            if not ticket.first_response_at:
                ticket.first_response_at = now
        elif payload.status == "closed":
            ticket.closed_at = now
            if not ticket.csat_requested_at:
                ticket.csat_requested_at = now  # Trigger CSAT
        elif payload.status == "pending_client":
            ticket.sla_paused_at = now  # Pause SLA
        else:
            # Resume SLA if coming back from pending
            if ticket.sla_paused_at:
                paused_at = ticket.sla_paused_at
                if paused_at.tzinfo is None:
                    paused_at = paused_at.replace(tzinfo=timezone.utc)
                paused_mins = int((now - paused_at).total_seconds() / 60)
                ticket.sla_pause_minutes = (ticket.sla_pause_minutes or 0) + paused_mins
                ticket.sla_paused_at = None

    # Recalculate priority if urgency/impact changed
    if payload.urgency or payload.impact:
        new_priority = PRIORITY_MATRIX.get((_norm_enum(ticket.urgency), _norm_enum(ticket.impact)), "p3_medium")
        if not payload.priority:
            old_priority = ticket.priority
            ticket.priority = new_priority
            # Recalculate SLA due dates when priority changes and ticket is still open
            if new_priority != old_priority and ticket.status not in ("resolved", "closed", "cancelled"):
                sla_policy = db.query(SLAPolicy).filter(SLAPolicy.id == ticket.sla_policy_id).first() if ticket.sla_policy_id else None
                resp_due, res_due = _calculate_sla_due(new_priority, sla_policy, db=db)
                ticket.sla_response_due = resp_due
                ticket.sla_resolution_due = res_due

    if payload.tags is not None:
        ticket.tags = payload.tags

    # Auto-escalate support level
    if payload.support_level:
        _log_history(db, ticket_id, "escalation", old_support_level, payload.support_level, current_user.id)

    _commit_or_rollback(db); db.refresh(ticket)

    # Background: refresh semantic profile when ticket is resolved
    if payload.status in ("resolved", "closed") and ticket.assigned_to_user_id:
        _sd_refresh_profile_bg(background_tasks, ticket.assigned_to_user_id)

    # Background: implicit feedback when ticket is reassigned
    if (payload.assigned_to_user_id and old_assigned_to
            and payload.assigned_to_user_id != old_assigned_to):
        _sd_reassign_feedback_bg(background_tasks, ticket_id, "ticket")

    return _ticket_out(ticket)


def _sd_refresh_profile_bg(background_tasks: BackgroundTasks, user_id: str):
    from app.services.semantic_classifier import SemanticAssigner
    from app.db.session import SessionLocal

    def _run():
        _db = SessionLocal()
        try:
            SemanticAssigner(_db).refresh_user_profile(user_id)
        except Exception:
            pass
        finally:
            _db.close()

    background_tasks.add_task(_run)


def _sd_reassign_feedback_bg(background_tasks: BackgroundTasks, item_id: str, item_type: str):
    from app.db.session import SessionLocal

    def _run():
        _db = SessionLocal()
        try:
            from app.models.semantic_engine import SemAssignment
            assignment = _db.query(SemAssignment).filter(
                SemAssignment.item_id == item_id,
                SemAssignment.item_type == item_type,
            ).order_by(SemAssignment.created_at.desc()).first()
            if assignment and assignment.was_accepted is None:
                assignment.was_accepted = False
                _commit_or_rollback(_db)
        except Exception:
            pass
        finally:
            _db.close()

    background_tasks.add_task(_run)


@router.post("/tickets/{ticket_id}/comments", summary="Añadir comentario")
def add_comment(
    ticket_id: str,
    payload: CommentIn,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    ticket = _scope_ticket_query(db.query(Ticket), db, current_user).filter(Ticket.id == ticket_id).first()
    if not ticket: raise HTTPException(404)

    comment = TicketComment(
        ticket_id=ticket_id,
        body=payload.body,
        is_public=payload.is_public,
        author_user_id=current_user.id if current_user else None,
    )
    db.add(comment)

    # First response
    if not ticket.first_response_at and current_user and payload.is_public:
        ticket.first_response_at = datetime.now(timezone.utc)
        if ticket.status == TicketStatus.new:
            ticket.status = TicketStatus.in_progress

    _commit_or_rollback(db); db.refresh(comment)
    return {
        "id": comment.id, "body": comment.body, "is_public": comment.is_public,
        "author_name": current_user.full_name if current_user else "Cliente",
        "created_at": str(comment.created_at)[:16],
    }


@router.post("/tickets/{ticket_id}/comments/client", summary="Comentario del cliente")
def add_client_comment(
    ticket_id: str,
    payload: CommentIn,
    authorization: Optional[str] = Header(None),
    portal_access_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
):
    client = _portal_client_from_auth(authorization, portal_access_token, db)
    if not client: raise HTTPException(401, "No autorizado")
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket: raise HTTPException(404)

    comment = TicketComment(
        ticket_id=ticket_id, body=payload.body, is_public=True,
        author_client_id=client.id,
    )
    db.add(comment)
    if ticket.status == TicketStatus.pending_client:
        ticket.status = TicketStatus.in_progress
        if ticket.sla_paused_at:
            paused_at2 = ticket.sla_paused_at
            if paused_at2.tzinfo is None:
                paused_at2 = paused_at2.replace(tzinfo=timezone.utc)
            paused = int((datetime.now(timezone.utc) - paused_at2).total_seconds() / 60)
            ticket.sla_pause_minutes = (ticket.sla_pause_minutes or 0) + paused
            ticket.sla_paused_at = None
    _commit_or_rollback(db)
    return {"id": comment.id, "created_at": str(comment.created_at)[:16]}


@router.post("/tickets/{ticket_id}/time-log", summary="Registrar tiempo")
def log_time(
    ticket_id: str,
    payload: TimeLogIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = _scope_ticket_query(db.query(Ticket), db, current_user).filter(Ticket.id == ticket_id).first()
    if not ticket: raise HTTPException(404)
    log = TicketTimeLog(ticket_id=ticket_id, user_id=current_user.id, **payload.model_dump())
    db.add(log)
    ticket.time_spent_minutes = (ticket.time_spent_minutes or 0) + payload.minutes
    _commit_or_rollback(db)
    return {"ok": True, "total_minutes": ticket.time_spent_minutes}


@router.post("/tickets/{ticket_id}/escalate", summary="Escalar ticket")
def escalate_ticket(
    ticket_id: str,
    to_level: str = Query(...),
    reason: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = _scope_ticket_query(db.query(Ticket), db, current_user).filter(Ticket.id == ticket_id).first()
    if not ticket: raise HTTPException(404)
    old_level = ticket.support_level
    ticket.support_level = to_level
    _log_history(db, ticket_id, "support_level", old_level, to_level, current_user.id)
    if reason:
        db.add(TicketComment(ticket_id=ticket_id, body=f"🔺 Escalado a {to_level}: {reason}", is_public=False, author_user_id=current_user.id))
    _commit_or_rollback(db)
    return {"ok": True, "from": old_level, "to": to_level}


@router.post("/tickets/{ticket_id}/csat", summary="Valoración de satisfacción")
def submit_csat(
    ticket_id: str,
    payload: CSATIn,
    authorization: Optional[str] = Header(None),
    portal_access_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
):
    client = _portal_client_from_auth(authorization, portal_access_token, db)
    if not client:
        raise HTTPException(401, "Autenticación requerida")
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket: raise HTTPException(404)
    if ticket.status not in ["resolved", "closed"]: raise HTTPException(400, "Solo tickets resueltos")
    ticket.csat_score = payload.score
    ticket.csat_comment = payload.comment
    if ticket.status == "resolved":
        ticket.status = TicketStatus.closed
        ticket.closed_at = datetime.now(timezone.utc)
    _commit_or_rollback(db)
    return {"ok": True}


# ── Client ticket views ───────────────────────────────────────────────────────

@router.get("/problems", summary="Listar problemas")
def list_problems(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Problem).options(
        joinedload(Problem.ci), joinedload(Problem.owner),
        joinedload(Problem.related_tickets),
    )
    q = _scope_problem_query(q, db, current_user)
    probs = (
        q.order_by(Problem.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return [{
        "id": p.id, "number": p.number, "title": p.title, "description": p.description,
        "status": p.status, "priority": p.priority,
        "root_cause": p.root_cause, "workaround": p.workaround,
        "ci_name": p.ci.name if p.ci else None,
        "owner_name": p.owner.full_name if p.owner else None,
        "related_ticket_count": len(p.related_tickets),
        "created_at": str(p.created_at)[:10],
        "resolved_at": str(p.resolved_at)[:10] if p.resolved_at else None,
    } for p in probs]

@router.post("/problems", summary="Crear problema")
def create_problem(payload: ProblemIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user.is_superadmin and current_user.organization_id:
        if payload.project_id:
            project = db.query(Project).filter(
                Project.id == payload.project_id,
                Project.organization_id == current_user.organization_id,
            ).first()
            if not project:
                raise HTTPException(403, "No puedes crear problemas para proyectos fuera de tu organización")
        if payload.owner_user_id:
            owner = db.query(User).filter(User.id == payload.owner_user_id).first()
            if not owner or owner.organization_id != current_user.organization_id:
                raise HTTPException(403, "No puedes asignar un owner fuera de tu organización")
    p = Problem(number=_next_problem_number(db), **payload.model_dump())
    db.add(p); _commit_or_rollback(db); db.refresh(p)
    return {"id": p.id, "number": p.number}

@router.patch("/problems/{problem_id}", summary="Actualizar problema")
def update_problem(problem_id: str, payload: ProblemUpdateIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    p = _scope_problem_query(db.query(Problem), db, current_user).filter(Problem.id == problem_id).first()
    if not p: raise HTTPException(404)
    if not current_user.is_superadmin and current_user.organization_id:
        if payload.project_id:
            project = db.query(Project).filter(
                Project.id == payload.project_id,
                Project.organization_id == current_user.organization_id,
            ).first()
            if not project:
                raise HTTPException(403, "No puedes mover problemas fuera de tu organización")
        if payload.owner_user_id:
            owner = db.query(User).filter(User.id == payload.owner_user_id).first()
            if not owner or owner.organization_id != current_user.organization_id:
                raise HTTPException(403, "No puedes asignar un owner fuera de tu organización")
    for k, v in payload.model_dump(exclude_unset=True).items(): setattr(p, k, v)
    if payload.status in ["resolved", "closed"]: p.resolved_at = datetime.now(timezone.utc)
    _commit_or_rollback(db); return {"ok": True}

@router.post("/problems/{problem_id}/link-ticket/{ticket_id}", summary="Vincular ticket a problema")
def link_ticket_to_problem(problem_id: str, ticket_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    problem = _scope_problem_query(db.query(Problem), db, current_user).filter(Problem.id == problem_id).first()
    if not problem: raise HTTPException(404)
    ticket = _scope_ticket_query(db.query(Ticket), db, current_user).filter(Ticket.id == ticket_id).first()
    if not ticket: raise HTTPException(404)
    ticket.problem_id = problem.id
    _commit_or_rollback(db); return {"ok": True}


# ── Knowledge Base ────────────────────────────────────────────────────────────

@router.get("/kb", summary="Artículos de base de conocimiento")
def list_kb_articles(
    search: Optional[str] = None,
    category_id: Optional[str] = None,
    public_only: bool = False,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
):
    q = db.query(KBArticle).options(joinedload(KBArticle.author)).filter(KBArticle.status == KBStatus.published)
    if public_only: q = q.filter(KBArticle.is_public == True)
    if category_id: q = q.filter(KBArticle.category_id == category_id)
    if search: q = q.filter(or_(KBArticle.title.ilike(f"%{search}%"), KBArticle.body.ilike(f"%{search}%"), KBArticle.tags.ilike(f"%{search}%")))

    # Scope to current user's organisation for authenticated internal users
    if not public_only and authorization and authorization.startswith("Bearer "):
        bearer = authorization.removeprefix("Bearer ").strip()
        from app.core.security import decode_token
        _payload = decode_token(bearer)
        if _payload and _payload.get("type") == "access":
            _uid = _payload.get("sub")
            _user = db.query(User).filter(User.id == _uid, User.is_active == True).first()
            if _user:
                q = _scope_kb_query(q, db, _user)

    articles = q.order_by(KBArticle.helpful_count.desc()).limit(200).all()
    return [{
        "id": a.id, "number": a.number, "title": a.title, "summary": a.summary,
        "body": a.body if not public_only else None,
        "tags": a.tags, "is_public": a.is_public,
        "view_count": a.view_count, "helpful_count": a.helpful_count,
        "author_name": a.author.full_name if a.author else None,
        "published_at": str(a.published_at)[:10] if a.published_at else None,
    } for a in articles]

@router.get("/kb/{article_id}", summary="Detalle de artículo KB")
def get_kb_article(article_id: str, db: Session = Depends(get_db)):
    a = db.query(KBArticle).filter(KBArticle.id == article_id).first()
    if not a: raise HTTPException(404)
    a.view_count = (a.view_count or 0) + 1; _commit_or_rollback(db)
    return {"id": a.id, "number": a.number, "title": a.title, "body": a.body, "summary": a.summary, "tags": a.tags, "view_count": a.view_count, "helpful_count": a.helpful_count}

@router.post("/kb", summary="Crear artículo KB")
def create_kb_article(payload: KBArticleIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    a = KBArticle(number=_next_kb_number(db), author_id=current_user.id, **payload.model_dump())
    if payload.status == "published": a.published_at = datetime.now(timezone.utc)
    db.add(a); _commit_or_rollback(db); db.refresh(a)
    return {"id": a.id, "number": a.number}

@router.patch("/kb/{article_id}", summary="Actualizar artículo KB")
def update_kb_article(article_id: str, payload: KBArticleUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    a = _scope_kb_query(db.query(KBArticle), db, current_user).filter(KBArticle.id == article_id).first()
    if not a: raise HTTPException(404)
    for k, v in payload.model_dump(exclude_unset=True, exclude_none=True).items(): setattr(a, k, v)
    if payload.status == "published" and not a.published_at: a.published_at = datetime.now(timezone.utc)
    _commit_or_rollback(db); return {"ok": True}

@router.delete("/kb/{article_id}", summary="Eliminar artículo KB")
def delete_kb_article(
    article_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    a = _scope_kb_query(db.query(KBArticle), db, current_user).filter(KBArticle.id == article_id).first()
    if not a: raise HTTPException(404, "Artículo no encontrado")
    db.delete(a)
    _commit_or_rollback(db)
    return {"ok": True}


@router.post("/kb/{article_id}/helpful", summary="Marcar artículo como útil")
def mark_helpful(article_id: str, helpful: bool = True, db: Session = Depends(get_db)):
    a = db.query(KBArticle).filter(KBArticle.id == article_id).first()
    if not a: raise HTTPException(404)
    if helpful: a.helpful_count = (a.helpful_count or 0) + 1
    else: a.not_helpful_count = (a.not_helpful_count or 0) + 1
    _commit_or_rollback(db); return {"ok": True}

@router.post("/tickets/{ticket_id}/to-kb", summary="Convertir resolución de ticket en artículo KB")
def ticket_to_kb(ticket_id: str, title: str = Query(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket: raise HTTPException(404)
    if not ticket.resolution: raise HTTPException(400, "El ticket no tiene resolución")
    a = KBArticle(number=_next_kb_number(db), title=title, body=f"**Síntoma**\n{ticket.description}\n\n**Solución**\n{ticket.resolution}", summary=ticket.title[:200], author_id=current_user.id, created_from_ticket_id=ticket_id, status=KBStatus.draft)
    db.add(a)
    db.flush()
    ticket.kb_article_id = a.id
    _commit_or_rollback(db)
    db.refresh(a)
    return {"id": a.id, "number": a.number}


# ── CMDB ──────────────────────────────────────────────────────────────────────

@router.get("/cmdb", summary="Inventario CMDB")
def list_cmdb(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(ConfigurationItem).options(joinedload(ConfigurationItem.project), joinedload(ConfigurationItem.owner))
    q = _scope_ci_query(q, db, current_user)
    items = (
        q.order_by(ConfigurationItem.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return [{
        "id": ci.id, "code": ci.code, "name": ci.name, "ci_type": ci.ci_type,
        "status": ci.status, "criticality": ci.criticality,
        "environment": ci.environment, "version": ci.version,
        "project_id": ci.project_id, "project_name": ci.project.name if ci.project else None,
        "owner_name": ci.owner.full_name if ci.owner else None,
        "open_tickets": len([]),  # Calculated below
    } for ci in items]

@router.post("/cmdb", summary="Crear CI")
def create_ci(payload: CIIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    if not current_user.is_superadmin and current_user.organization_id:
        if payload.project_id:
            project = db.query(Project).filter(
                Project.id == payload.project_id,
                Project.organization_id == current_user.organization_id,
            ).first()
            if not project:
                raise HTTPException(403, "No puedes crear CIs para proyectos fuera de tu organización")
        if payload.owner_user_id:
            owner = db.query(User).filter(User.id == payload.owner_user_id).first()
            if not owner or owner.organization_id != current_user.organization_id:
                raise HTTPException(403, "No puedes asignar owner fuera de tu organización")
    ci = ConfigurationItem(code=_next_ci_number(db), **payload.model_dump())
    db.add(ci); _commit_or_rollback(db); db.refresh(ci)
    return {"id": ci.id, "code": ci.code}

@router.patch("/cmdb/{ci_id}", summary="Actualizar CI")
def update_ci(ci_id: str, payload: CIIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    ci = _scope_ci_query(db.query(ConfigurationItem), db, current_user).filter(ConfigurationItem.id == ci_id).first()
    if not ci: raise HTTPException(404)
    if not current_user.is_superadmin and current_user.organization_id:
        if payload.project_id:
            project = db.query(Project).filter(
                Project.id == payload.project_id,
                Project.organization_id == current_user.organization_id,
            ).first()
            if not project:
                raise HTTPException(403, "No puedes mover CIs fuera de tu organización")
        if payload.owner_user_id:
            owner = db.query(User).filter(User.id == payload.owner_user_id).first()
            if not owner or owner.organization_id != current_user.organization_id:
                raise HTTPException(403, "No puedes asignar owner fuera de tu organización")
    for k, v in payload.model_dump().items(): setattr(ci, k, v)
    _commit_or_rollback(db); return {"ok": True}


# ── Announcements ─────────────────────────────────────────────────────────────

@router.get("/announcements", summary="Anuncios activos")
def list_announcements(db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    ann = db.query(Announcement).filter(
        Announcement.is_active == True,
        or_(Announcement.ends_at == None, Announcement.ends_at > now),
    ).order_by(Announcement.created_at.desc()).limit(50).all()
    return [{"id": a.id, "title": a.title, "body": a.body, "type": a.type, "show_to_clients": a.show_to_clients, "ci_name": a.ci.name if a.ci else None, "starts_at": str(a.starts_at)[:16] if a.starts_at else None, "ends_at": str(a.ends_at)[:16] if a.ends_at else None} for a in ann]

@router.post("/announcements", summary="Crear anuncio")
def create_announcement(payload: AnnouncementIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    a = Announcement(created_by=current_user.id, **payload.model_dump())
    db.add(a); _commit_or_rollback(db); db.refresh(a)
    return {"id": a.id}

@router.delete("/announcements/{ann_id}", summary="Desactivar anuncio")
def deactivate_announcement(ann_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    a = db.query(Announcement).filter(Announcement.id == ann_id).first()
    if not a: raise HTTPException(404)
    a.is_active = False; _commit_or_rollback(db); return {"ok": True}


# ── Analytics / Dashboard ─────────────────────────────────────────────────────

@router.get("/stats", summary="Estadísticas del service desk")
def get_stats(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    now = datetime.now(timezone.utc)

    scoped_tickets = _scope_ticket_query(db.query(Ticket), db, current_user)

    total = scoped_tickets.filter(Ticket.created_at >= since).count()
    open_count = scoped_tickets.filter(Ticket.status.notin_(["resolved", "closed", "cancelled"])).count()
    resolved = scoped_tickets.filter(Ticket.created_at >= since, Ticket.status.in_(["resolved", "closed"])).count()

    # SLA compliance
    sla_breached = scoped_tickets.filter(
        Ticket.created_at >= since,
        Ticket.status.notin_(["cancelled"]),
        or_(
            and_(Ticket.sla_resolution_due < now, Ticket.status.notin_(["resolved", "closed"])),
            and_(Ticket.resolved_at != None, Ticket.sla_resolution_due != None, Ticket.resolved_at > Ticket.sla_resolution_due)
        )
    ).count()
    sla_compliance = round((1 - sla_breached / max(total, 1)) * 100, 1)

    # MTTR (mean time to resolution)
    resolved_tickets = scoped_tickets.filter(Ticket.created_at >= since, Ticket.resolved_at != None).all()
    mttr = 0
    if resolved_tickets:
        hours_list = []
        for t in resolved_tickets:
            if t.resolved_at and t.created_at:
                try:
                    h = (_aware(t.resolved_at) - _aware(t.created_at)).total_seconds() / 3600
                    hours_list.append(h)
                except Exception as e:
                    logging.getLogger(__name__).warning(f"Skipping ticket {t.id} MTTR calc due invalid timestamp: {e}")
        total_hours = sum(hours_list)
        mttr = round(total_hours / max(len(hours_list), 1), 1)

    # CSAT
    csat_tickets = scoped_tickets.filter(Ticket.created_at >= since, Ticket.csat_score != None).all()
    avg_csat = round(sum(t.csat_score for t in csat_tickets) / max(len(csat_tickets), 1), 1) if csat_tickets else None

    # FCR (first contact resolution – resolved without escalation)
    fcr_count = scoped_tickets.filter(
        Ticket.created_at >= since,
        Ticket.status.in_(["resolved", "closed"]),
        Ticket.support_level == "l1",
    ).count()
    fcr_rate = round(fcr_count / max(resolved, 1) * 100, 1)

    # By priority
    by_priority = {}
    for pri in ["p1_critical", "p2_high", "p3_medium", "p4_low"]:
        count = scoped_tickets.filter(Ticket.created_at >= since, Ticket.priority == pri).count()
        by_priority[pri] = {"count": count, "label": PRIORITY_LABELS[pri]["label"], "color": PRIORITY_LABELS[pri]["color"]}

    # By type
    by_type = {}
    for ttype in ["incident", "service_request", "change", "question"]:
        count = scoped_tickets.filter(Ticket.created_at >= since, Ticket.ticket_type == ttype).count()
        by_type[ttype] = {"count": count, "label": TYPE_LABELS[ttype]["label"], "icon": TYPE_LABELS[ttype]["icon"]}

    # By status
    by_status = {}
    for st in ["new", "assigned", "in_progress", "pending_client", "resolved", "closed"]:
        count = scoped_tickets.filter(Ticket.status == st).count()
        by_status[st] = {"count": count, "label": STATUS_LABELS[st]["label"], "color": STATUS_LABELS[st]["color"]}

    # Backlog by agent
    agents = db.query(User.id, User.full_name, func.count(Ticket.id).label("count")).join(
        Ticket, Ticket.assigned_to_user_id == User.id
    )
    if not current_user.is_superadmin and current_user.organization_id:
        agents = agents.filter(User.organization_id == current_user.organization_id)
    agents = agents.filter(Ticket.status.notin_(["resolved", "closed", "cancelled"])).group_by(User.id, User.full_name).all()

    # Volume trend (last N days)
    trend = []
    for i in range(min(days, 30), 0, -1):
        d = date.today() - timedelta(days=i)
        count = scoped_tickets.filter(func.date(Ticket.created_at) == d).count()
        trend.append({"date": str(d)[5:], "count": count})

    # SLA breached right now
    sla_at_risk = scoped_tickets.filter(
        Ticket.status.notin_(["resolved", "closed", "cancelled"]),
        Ticket.sla_resolution_due < now + timedelta(hours=2),
        Ticket.sla_resolution_due > now,
    ).count()
    sla_breached_now = scoped_tickets.filter(
        Ticket.status.notin_(["resolved", "closed", "cancelled"]),
        Ticket.sla_resolution_due < now,
    ).count()

    return {
        "period_days": days,
        "summary": {
            "total": total,
            "open": open_count,
            "resolved": resolved,
            "sla_compliance_pct": sla_compliance,
            "sla_at_risk": sla_at_risk,
            "sla_breached_now": sla_breached_now,
            "mttr_hours": mttr,
            "avg_csat": avg_csat,
            "fcr_rate_pct": fcr_rate,
        },
        "by_priority": by_priority,
        "by_type": by_type,
        "by_status": by_status,
        "backlog_by_agent": [{"user_id": a.id, "user_name": a.full_name, "count": a.count} for a in agents],
        "trend": trend,
    }

# ════════════════════════════════════════════════════════════════════════════
# AMPLIACIÓN ITIL/ITSM v2
# ════════════════════════════════════════════════════════════════════════════
from app.models.service_desk import (
    TicketLink, RoutingRule, SLAEvent, SLAEventType,
    CIRelation, ITSMChangeRequest, ChangeStatus,
    MajorIncident, TicketTemplate,
)


# ── Helpers ITIL ─────────────────────────────────────────────────────────────

def _priority_matrix(urgency: str, impact: str) -> str:
    """Calcula la prioridad ITIL según urgencia × impacto."""
    matrix = {
        ("critical", "enterprise"): "p1_critical",
        ("critical", "department"): "p1_critical",
        ("critical", "user"):       "p2_high",
        ("high",     "enterprise"): "p1_critical",
        ("high",     "department"): "p2_high",
        ("high",     "user"):       "p2_high",
        ("medium",   "enterprise"): "p2_high",
        ("medium",   "department"): "p3_medium",
        ("medium",   "user"):       "p3_medium",
        ("low",      "enterprise"): "p3_medium",
        ("low",      "department"): "p4_low",
        ("low",      "user"):       "p4_low",
    }
    return matrix.get((urgency, impact), "p3_medium")


def _apply_routing_rules(ticket: Ticket, db: Session) -> bool:
    """Aplica reglas de routing automático. Devuelve True si se asignó."""
    rules = db.query(RoutingRule).filter(
        RoutingRule.is_active == True
    ).order_by(RoutingRule.priority).all()

    for rule in rules:
        conditions = json.loads(rule.conditions or "{}")
        match = True

        ticket_type = _norm_enum(ticket.ticket_type)
        ticket_priority = _norm_enum(ticket.priority)

        if "ticket_type" in conditions:
            if ticket_type != conditions["ticket_type"]:
                match = False
        if "priority" in conditions:
            prios = conditions["priority"] if isinstance(conditions["priority"], list) else [conditions["priority"]]
            if ticket_priority not in prios:
                match = False
        if "category_id" in conditions and ticket.service_item:
            if ticket.service_item.category_id != conditions["category_id"]:
                match = False
        if "requester_domain" in conditions:
            domain_cond = conditions["requester_domain"]
            allowed = domain_cond if isinstance(domain_cond, list) else [domain_cond]
            requester_email = ticket.requester_email or (ticket.requester_user.email if ticket.requester_user else None)
            domain = (requester_email.split("@", 1)[1].lower() if requester_email and "@" in requester_email else "")
            allowed_norm = [str(d).lower().strip() for d in allowed]
            if domain not in allowed_norm:
                match = False
        if "keyword_in_title" in conditions:
            kws = conditions["keyword_in_title"]
            kws = kws if isinstance(kws, list) else [kws]
            title_l = (ticket.title or "").lower()
            if not any(str(k).lower().strip() in title_l for k in kws if str(k).strip()):
                match = False
        if "time_of_day" in conditions:
            tod = conditions["time_of_day"]
            t_created = (ticket.created_at or datetime.now(timezone.utc)).time()
            if isinstance(tod, str) and "-" in tod:
                start_s, end_s = [p.strip() for p in tod.split("-", 1)]
                start_t = dt_time.fromisoformat(start_s)
                end_t = dt_time.fromisoformat(end_s)
                if not (start_t <= t_created <= end_t):
                    match = False
            elif isinstance(tod, dict):
                start_s = tod.get("start")
                end_s = tod.get("end")
                if start_s and end_s:
                    start_t = dt_time.fromisoformat(start_s)
                    end_t = dt_time.fromisoformat(end_s)
                    if not (start_t <= t_created <= end_t):
                        match = False
        if "day_of_week" in conditions:
            dow = conditions["day_of_week"]
            allowed = dow if isinstance(dow, list) else [dow]
            w = (ticket.created_at or datetime.now(timezone.utc)).weekday()  # Monday=0
            day_labels = {
                "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                "friday": 4, "saturday": 5, "sunday": 6,
            }
            allowed_idx = []
            for d in allowed:
                if isinstance(d, int):
                    allowed_idx.append(d)
                else:
                    d_l = str(d).lower().strip()
                    if d_l.isdigit():
                        allowed_idx.append(int(d_l))
                    elif d_l in day_labels:
                        allowed_idx.append(day_labels[d_l])
            if w not in allowed_idx:
                match = False
        if "client_org_id" in conditions:
            cid = conditions["client_org_id"]
            allowed = cid if isinstance(cid, list) else [cid]
            ticket_client_id = ticket.client_id or (ticket.requester_client.client_org_id if ticket.requester_client else None)
            if ticket_client_id not in allowed:
                match = False
        if "sla_policy_id" in conditions:
            sp = conditions["sla_policy_id"]
            allowed = sp if isinstance(sp, list) else [sp]
            if ticket.sla_policy_id not in allowed:
                match = False
        if "tag_contains" in conditions:
            tg = conditions["tag_contains"]
            tg = tg if isinstance(tg, list) else [tg]
            tag_text = (ticket.tags or "").lower()
            if not any(str(t).lower().strip() in tag_text for t in tg if str(t).strip()):
                match = False

        if match:
            actions = json.loads(rule.actions or "{}")
            if "assign_group" in actions:
                ticket.assigned_group_id = actions["assign_group"]
            if "assign_user" in actions:
                ticket.assigned_to_user_id = actions["assign_user"]
            if "set_priority" in actions:
                ticket.priority = actions["set_priority"]
            if "set_support_level" in actions:
                ticket.support_level = actions["set_support_level"]
            return True
    return False


def _compute_itil_metrics(tickets, now=None):
    """Calcula MTTR, MTBF, FCR para un conjunto de tickets."""
    from datetime import timezone as tz
    if now is None:
        from datetime import datetime
        now = datetime.now(tz.utc)

    def _safe_dt(dt):
        """Normaliza datetime naive→aware(UTC) para aritmética segura."""
        if dt is None: return None
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=tz.utc)

    resolved = [t for t in tickets if t.resolved_at and t.created_at]
    mttr_minutes = 0
    if resolved:
        total = sum((_safe_dt(t.resolved_at) - _safe_dt(t.created_at)).total_seconds() / 60 for t in resolved)
        mttr_minutes = round(total / len(resolved), 1)

    # FCR: resueltos en primer contacto (sin re-asignaciones, 1 comentario del agente)
    fcr_count = sum(
        1 for t in resolved
        if len([c for c in (t.comments or []) if not getattr(c, 'is_client', False)]) <= 2
    )
    fcr_pct = round(fcr_count / len(resolved) * 100, 1) if resolved else 0

    return {
        "mttr_minutes": mttr_minutes,
        "mttr_hours":   round(mttr_minutes / 60, 1),
        "fcr_percent":  fcr_pct,
        "total_resolved": len(resolved),
    }


# ── Routing Rules CRUD ────────────────────────────────────────────────────────

@router.get("/routing-rules", summary="Listar reglas de routing automático")
def list_routing_rules(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rules = db.query(RoutingRule).order_by(RoutingRule.priority).all()
    return [{"id": r.id, "name": r.name, "is_active": r.is_active,
             "priority": r.priority, "conditions": r.conditions,
             "actions": r.actions} for r in rules]


@router.post("/routing-rules", summary="Crear regla de routing")
def create_routing_rule(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if not payload.get("name"):
        raise HTTPException(422, "name es obligatorio")
    rule = RoutingRule(
        name=payload["name"],
        is_active=payload.get("is_active", True),
        priority=payload.get("priority", 100),
        conditions=json.dumps(payload.get("conditions", {})),
        actions=json.dumps(payload.get("actions", {})),
    )
    db.add(rule); _commit_or_rollback(db); db.refresh(rule)
    return {"id": rule.id, "name": rule.name}


@router.patch("/routing-rules/{rule_id}", summary="Actualizar regla de routing")
def update_routing_rule(
    rule_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    rule = db.query(RoutingRule).filter(RoutingRule.id == rule_id).first()
    if not rule: raise HTTPException(404)
    for k in ("name", "is_active", "priority"):
        if k in payload: setattr(rule, k, payload[k])
    if "conditions" in payload:
        rule.conditions = json.dumps(payload["conditions"])
    if "actions" in payload:
        rule.actions = json.dumps(payload["actions"])
    _commit_or_rollback(db)
    return {"ok": True}


@router.delete("/routing-rules/{rule_id}", summary="Eliminar regla de routing")
def delete_routing_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    rule = db.query(RoutingRule).filter(RoutingRule.id == rule_id).first()
    if not rule: raise HTTPException(404)
    db.delete(rule); _commit_or_rollback(db)
    return {"ok": True}


# ── Priority Matrix ───────────────────────────────────────────────────────────

@router.post("/priority-matrix", summary="Calcular prioridad ITIL por urgencia × impacto")
def calculate_priority(
    payload: dict = Body(...),
    current_user: User = Depends(get_current_user),
):
    urgency = payload.get("urgency", "medium")
    impact  = payload.get("impact", "user")
    priority = _priority_matrix(urgency, impact)
    return {"urgency": urgency, "impact": impact, "recommended_priority": priority}


# ── Linked Tickets ────────────────────────────────────────────────────────────

@router.get("/tickets/{ticket_id}/links", summary="Ver tickets vinculados")
def get_ticket_links(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy.orm import joinedload
    links = db.query(TicketLink).options(
        joinedload(TicketLink.target),
        joinedload(TicketLink.source),
    ).filter(
        (TicketLink.source_id == ticket_id) | (TicketLink.target_id == ticket_id)
    ).all()

    result = []
    for lk in links:
        other = lk.target if lk.source_id == ticket_id else lk.source
        result.append({
            "link_id":    lk.id,
            "link_type":  lk.link_type.value,
            "direction":  "outbound" if lk.source_id == ticket_id else "inbound",
            "ticket_id":  other.id,
            "ticket_number": other.number,
            "ticket_title":  other.title,
            "ticket_status": other.status.value,
            "ticket_priority": other.priority.value,
        })
    return result


@router.post("/tickets/{ticket_id}/links", summary="Vincular tickets")
def link_tickets(
    ticket_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_id = payload.get("target_id")
    link_type = payload.get("link_type", "relates_to")

    if not db.query(Ticket).filter(Ticket.id == ticket_id).first():
        raise HTTPException(404, "Ticket origen no encontrado")
    if not db.query(Ticket).filter(Ticket.id == target_id).first():
        raise HTTPException(404, "Ticket destino no encontrado")
    if ticket_id == target_id:
        raise HTTPException(400, "No se puede vincular un ticket consigo mismo")

    # Evitar duplicados
    existing = db.query(TicketLink).filter(
        ((TicketLink.source_id == ticket_id) & (TicketLink.target_id == target_id)) |
        ((TicketLink.source_id == target_id) & (TicketLink.target_id == ticket_id))
    ).first()
    if existing:
        raise HTTPException(409, "Ya existe un vínculo entre estos tickets")

    lk = TicketLink(
        source_id=ticket_id, target_id=target_id,
        link_type=link_type, created_by=current_user.id,
    )
    db.add(lk); _commit_or_rollback(db)
    return {"ok": True, "link_id": lk.id}


@router.delete("/tickets/{ticket_id}/links/{link_id}", summary="Eliminar vínculo")
def delete_ticket_link(
    ticket_id: str, link_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lk = db.query(TicketLink).filter(TicketLink.id == link_id).first()
    if not lk: raise HTTPException(404)
    db.delete(lk); _commit_or_rollback(db)
    return {"ok": True}


# ── SLA — Pause / Resume / Events ────────────────────────────────────────────

@router.post("/tickets/{ticket_id}/sla/pause", summary="Pausar SLA (esperando cliente/OOH)")
def pause_sla(
    ticket_id: str,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from datetime import datetime, timezone as tz
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket: raise HTTPException(404)
    if ticket.sla_paused_at:
        raise HTTPException(400, "SLA ya está pausado")

    ticket.sla_paused_at = datetime.now(tz.utc)
    # Actualizar status a waiting_client si corresponde
    if ticket.status.value not in ("resolved", "closed"):
        ticket.status = "pending_client"

    event = SLAEvent(
        ticket_id=ticket_id, event_type=SLAEventType.paused,
        note=payload.get("note", "SLA pausado"), created_by=current_user.id,
    )
    db.add(event); _commit_or_rollback(db)
    return {"ok": True, "paused_at": str(ticket.sla_paused_at)}


@router.post("/tickets/{ticket_id}/sla/resume", summary="Reanudar SLA")
def resume_sla(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from datetime import datetime, timezone as tz
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket: raise HTTPException(404)
    if not ticket.sla_paused_at:
        raise HTTPException(400, "SLA no está pausado")

    now = datetime.now(tz.utc)
    paused_at_tz = ticket.sla_paused_at
    if paused_at_tz.tzinfo is None:
        paused_at_tz = paused_at_tz.replace(tzinfo=timezone.utc)
    pause_duration = int((now - paused_at_tz).total_seconds() / 60)
    ticket.sla_pause_minutes = (ticket.sla_pause_minutes or 0) + pause_duration
    ticket.sla_paused_at = None

    # Extender los plazos del SLA por el tiempo pausado
    from datetime import timedelta
    if ticket.sla_response_due:
        ticket.sla_response_due += timedelta(minutes=pause_duration)
    if ticket.sla_resolution_due:
        ticket.sla_resolution_due += timedelta(minutes=pause_duration)

    event = SLAEvent(
        ticket_id=ticket_id, event_type=SLAEventType.resumed,
        note=f"SLA reanudado — {pause_duration} min pausado", created_by=current_user.id,
    )
    db.add(event); _commit_or_rollback(db)
    return {"ok": True, "paused_minutes": pause_duration}


@router.get("/tickets/{ticket_id}/sla/events", summary="Historial de eventos SLA")
def get_sla_events(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    events = db.query(SLAEvent).filter(
        SLAEvent.ticket_id == ticket_id
    ).order_by(SLAEvent.created_at).all()
    return [{"id": e.id, "event_type": e.event_type.value,
             "sla_type": e.sla_type, "note": e.note,
             "created_at": str(e.created_at)} for e in events]


# ── ITIL Metrics ─────────────────────────────────────────────────────────────

@router.get("/metrics/itil", summary="Métricas ITIL: MTTR, FCR, SLA compliance, volumen")
def get_itil_metrics(
    date_from: Optional[str] = Query(None),
    date_to:   Optional[str] = Query(None),
    client_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from datetime import datetime, timezone as tz, timedelta
    from sqlalchemy.orm import joinedload

    d_from = datetime.fromisoformat(date_from).replace(tzinfo=tz.utc) if date_from else \
             datetime.now(tz.utc) - timedelta(days=30)
    d_to   = datetime.fromisoformat(date_to).replace(tzinfo=tz.utc) if date_to else \
             datetime.now(tz.utc)

    q = db.query(Ticket).options(
        joinedload(Ticket.comments)
    ).filter(Ticket.created_at.between(d_from, d_to))
    if client_id:
        q = q.filter(Ticket.client_id == client_id)
    tickets = q.all()

    total    = len(tickets)
    resolved = [t for t in tickets if t.resolved_at]
    open_t   = [t for t in tickets if t.status.value not in ("resolved", "closed", "cancelled")]
    breached = [t for t in tickets if t.sla_resolution_status and t.sla_resolution_status.value == "breached"]

    # MTTR
    metrics = _compute_itil_metrics(tickets)

    # SLA Compliance
    sla_compliant = [t for t in resolved if t.sla_resolution_status and t.sla_resolution_status.value == "ok"]
    sla_pct = round(len(sla_compliant) / len(resolved) * 100, 1) if resolved else 100.0

    # Por tipo
    by_type = {}
    for t in tickets:
        k = t.ticket_type.value
        by_type[k] = by_type.get(k, 0) + 1

    # Por prioridad
    by_priority = {}
    for t in tickets:
        k = t.priority.value
        by_priority[k] = by_priority.get(k, 0) + 1

    # CSAT
    csat_scores = [t.csat_score for t in tickets if t.csat_score]
    avg_csat = round(sum(csat_scores) / len(csat_scores), 2) if csat_scores else None

    # Breach por prioridad
    breach_by_priority = {}
    for t in breached:
        k = t.priority.value
        breach_by_priority[k] = breach_by_priority.get(k, 0) + 1

    return {
        "period": {"from": str(d_from.date()), "to": str(d_to.date())},
        "volume": {
            "total": total, "open": len(open_t), "resolved": len(resolved),
            "breached_sla": len(breached),
        },
        "sla_compliance_pct": sla_pct,
        "mttr_minutes":       metrics["mttr_minutes"],
        "mttr_hours":         metrics["mttr_hours"],
        "fcr_percent":        metrics["fcr_percent"],
        "avg_csat":           avg_csat,
        "by_type":            by_type,
        "by_priority":        by_priority,
        "breach_by_priority": breach_by_priority,
    }


@router.get("/metrics/agent-performance", summary="Rendimiento por agente")
def get_agent_performance(
    date_from: Optional[str] = Query(None),
    date_to:   Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from datetime import datetime, timezone as tz, timedelta
    d_from = datetime.fromisoformat(date_from).replace(tzinfo=tz.utc) if date_from else \
             datetime.now(tz.utc) - timedelta(days=30)
    d_to   = datetime.fromisoformat(date_to).replace(tzinfo=tz.utc) if date_to else \
             datetime.now(tz.utc)

    agents = db.query(User).filter(User.is_active == True).all()
    result = []
    for agent in agents:
        agent_tickets = db.query(Ticket).filter(
            Ticket.assigned_to_user_id == agent.id,
            Ticket.created_at.between(d_from, d_to),
        ).all()
        if not agent_tickets: continue

        resolved = [t for t in agent_tickets if t.resolved_at and t.created_at]
        mttr = 0
        if resolved:
            def _sdt(dt):
                return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
            mttr = round(sum((_sdt(t.resolved_at) - _sdt(t.created_at)).total_seconds() / 60
                             for t in resolved) / len(resolved), 0)
        csat_scores = [t.csat_score for t in agent_tickets if t.csat_score]
        breached = sum(1 for t in agent_tickets
                       if t.sla_resolution_status and t.sla_resolution_status.value == "breached")

        result.append({
            "agent_id":    agent.id,
            "agent_name":  agent.full_name,
            "total":       len(agent_tickets),
            "resolved":    len(resolved),
            "open":        len(agent_tickets) - len(resolved),
            "mttr_minutes": mttr,
            "avg_csat":    round(sum(csat_scores)/len(csat_scores), 2) if csat_scores else None,
            "sla_breaches": breached,
        })

    result.sort(key=lambda x: -x["resolved"])
    return result


# ── CMDB — Relaciones entre CIs ───────────────────────────────────────────────

@router.get("/cmdb/{ci_id}/relations", summary="Relaciones del CI (impacto)")
def get_ci_relations(
    ci_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy.orm import joinedload
    base_ci = _scope_ci_query(db.query(ConfigurationItem), db, current_user).filter(ConfigurationItem.id == ci_id).first()
    if not base_ci:
        raise HTTPException(404, "CI no encontrado")
    visible_ci_ids = _scope_ci_query(db.query(ConfigurationItem.id), db, current_user).scalar_subquery()
    rels = db.query(CIRelation).options(
        joinedload(CIRelation.source_ci), joinedload(CIRelation.target_ci)
    ).filter(
        (CIRelation.source_ci_id == ci_id) | (CIRelation.target_ci_id == ci_id),
        CIRelation.source_ci_id.in_(visible_ci_ids),
        CIRelation.target_ci_id.in_(visible_ci_ids),
    ).all()
    return [{
        "id": r.id, "relation_type": r.relation_type.value,
        "source": {"id": r.source_ci.id, "name": r.source_ci.name, "type": r.source_ci.ci_type.value},
        "target": {"id": r.target_ci.id, "name": r.target_ci.name, "type": r.target_ci.ci_type.value},
        "notes": r.notes,
    } for r in rels]


@router.post("/cmdb/relations", summary="Crear relación entre CIs")
def create_ci_relation(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    src_id = payload.get("source_ci_id")
    tgt_id = payload.get("target_ci_id")
    if not src_id or not tgt_id:
        raise HTTPException(422, "source_ci_id y target_ci_id son obligatorios")
    if not _scope_ci_query(db.query(ConfigurationItem), db, current_user).filter(ConfigurationItem.id == src_id).first():
        raise HTTPException(404, "CI origen no encontrado")
    if not _scope_ci_query(db.query(ConfigurationItem), db, current_user).filter(ConfigurationItem.id == tgt_id).first():
        raise HTTPException(404, "CI destino no encontrado")
    rel = CIRelation(
        source_ci_id=src_id,
        target_ci_id=tgt_id,
        relation_type=payload.get("relation_type", "depends_on"),
        notes=payload.get("notes"),
    )
    db.add(rel); _commit_or_rollback(db)
    return {"id": rel.id, "ok": True}


@router.get("/cmdb/{ci_id}/impact", summary="Análisis de impacto — CIs afectados si este falla")
def get_ci_impact(
    ci_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """BFS para encontrar todos los CIs que dependen de este CI."""
    from collections import deque

    base_ci = _scope_ci_query(db.query(ConfigurationItem), db, current_user).filter(ConfigurationItem.id == ci_id).first()
    if not base_ci:
        raise HTTPException(404, "CI no encontrado")
    visible_ci_ids = _scope_ci_query(db.query(ConfigurationItem.id), db, current_user).scalar_subquery()

    visited = set()
    queue   = deque([ci_id])
    impacted = []

    while queue:
        current = queue.popleft()
        if current in visited: continue
        visited.add(current)

        # CIs que dependen de current (current es el target, ellos son source)
        dependents = db.query(CIRelation).filter(
            CIRelation.target_ci_id == current,
            CIRelation.relation_type.in_(["depends_on", "hosts", "part_of"]),
            CIRelation.source_ci_id.in_(visible_ci_ids),
            CIRelation.target_ci_id.in_(visible_ci_ids),
        ).all()

        for dep in dependents:
            if dep.source_ci_id not in visited:
                ci = db.query(ConfigurationItem).filter(
                    ConfigurationItem.id == dep.source_ci_id
                )
                ci = _scope_ci_query(ci, db, current_user).first()
                if ci:
                    impacted.append({
                        "ci_id": ci.id, "ci_name": ci.name,
                        "ci_type": ci.ci_type.value, "criticality": ci.criticality,
                        "relation": dep.relation_type.value,
                    })
                queue.append(dep.source_ci_id)

    return {"ci_id": ci_id, "impacted_count": len(impacted), "impacted": impacted}


# ── Change Management ITSM ────────────────────────────────────────────────────

@router.get("/changes", summary="Listar Change Requests ITSM")
def list_changes(
    status:     Optional[str] = Query(None),
    change_type: Optional[str] = Query(None),
    date_from:  Optional[str] = Query(None),
    date_to:    Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy.orm import joinedload
    from datetime import datetime, timezone as tz
    q = db.query(ITSMChangeRequest).options(
        joinedload(ITSMChangeRequest.requester),
        joinedload(ITSMChangeRequest.owner),
    )
    q = _scope_change_query(q, db, current_user)
    if status:      q = q.filter(ITSMChangeRequest.status == status)
    if change_type: q = q.filter(ITSMChangeRequest.change_type == change_type)
    if date_from:   q = q.filter(ITSMChangeRequest.created_at >= datetime.fromisoformat(date_from).replace(tzinfo=tz.utc))
    if date_to:     q = q.filter(ITSMChangeRequest.created_at <= datetime.fromisoformat(date_to).replace(tzinfo=tz.utc))
    changes = (
        q.order_by(ITSMChangeRequest.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return [_change_out(c) for c in changes]


def _change_out(c: ITSMChangeRequest, full: bool = False) -> dict:
    base = {
        "id": c.id, "number": c.number, "title": c.title,
        "change_type": c.change_type.value if c.change_type else None,
        "status": c.status.value if c.status else None,
        "risk": c.risk.value if c.risk else None,
        "priority": c.priority.value if c.priority else None,
        "planned_start": str(c.planned_start) if c.planned_start else None,
        "planned_end":   str(c.planned_end)   if c.planned_end   else None,
        "actual_start":  str(c.actual_start)  if c.actual_start  else None,
        "actual_end":    str(c.actual_end)    if c.actual_end    else None,
        "requester_id":  c.requester_id,
        "requester":     c.requester.full_name if c.requester else None,
        "owner_id":      c.owner_id,
        "owner":         c.owner.full_name     if c.owner     else None,
        "approved_by":   c.approved_by,
        "approved_at":   str(c.approved_at)   if c.approved_at   else None,
        "pir_success":   c.pir_success,
        "pir_date":      str(c.pir_date)      if c.pir_date      else None,
        "downtime_minutes": c.downtime_minutes,
        "created_at":    str(c.created_at),
    }
    if full:
        base.update({
            "description":           c.description,
            "business_justification": c.business_justification,
            "implementation_plan":   c.implementation_plan,
            "rollback_plan":         c.rollback_plan,
            "test_plan":             c.test_plan,
            "impact_description":    c.impact_description,
            "pir_notes":             c.pir_notes,
        })
    return base


@router.get("/changes/{change_id}", summary="Detalle de Change Request")
def get_change(
    change_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cr = _scope_change_query(db.query(ITSMChangeRequest), db, current_user).filter(ITSMChangeRequest.id == change_id).first()
    if not cr: raise HTTPException(404, "Change request no encontrado")
    return _change_out(cr, full=True)


@router.post("/changes", summary="Crear Change Request ITSM")
def create_change(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Generar número
    import re as _re
    if not payload.get("title") or not payload.get("description"):
        raise HTTPException(422, "title y description son obligatorios")
    max_chg = db.query(func.max(ITSMChangeRequest.number)).scalar()
    if max_chg:
        _m = _re.search(r"(\d+)$", max_chg)
        n = (int(_m.group(1)) + 1) if _m else 1
    else:
        n = 1
    number = f"CHG{n:05d}"

    cr = ITSMChangeRequest(
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
        requester_id=current_user.id,
        owner_id=payload.get("owner_id"),
        related_ticket_id=payload.get("related_ticket_id"),
        related_problem_id=payload.get("related_problem_id"),
    )
    if payload.get("planned_start"):
        from datetime import datetime, timezone as tz
        cr.planned_start = datetime.fromisoformat(payload["planned_start"]).replace(tzinfo=tz.utc)
    if payload.get("planned_end"):
        from datetime import datetime, timezone as tz
        cr.planned_end = datetime.fromisoformat(payload["planned_end"]).replace(tzinfo=tz.utc)

    if not current_user.is_superadmin and current_user.organization_id:
        if cr.owner_id:
            owner = db.query(User).filter(User.id == cr.owner_id).first()
            if not owner or owner.organization_id != current_user.organization_id:
                raise HTTPException(403, "No puedes asignar owner fuera de tu organización")
        if cr.related_ticket_id:
            t = _scope_ticket_query(db.query(Ticket), db, current_user).filter(Ticket.id == cr.related_ticket_id).first()
            if not t:
                raise HTTPException(403, "Ticket relacionado fuera de tu organización")
        if cr.related_problem_id:
            p = _scope_problem_query(db.query(Problem), db, current_user).filter(Problem.id == cr.related_problem_id).first()
            if not p:
                raise HTTPException(403, "Problema relacionado fuera de tu organización")

    db.add(cr); _commit_or_rollback(db); db.refresh(cr)
    return _change_out(cr)


@router.patch("/changes/{change_id}", summary="Actualizar Change Request")
def update_change(
    change_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from datetime import datetime, timezone as tz
    cr = _scope_change_query(db.query(ITSMChangeRequest), db, current_user).filter(ITSMChangeRequest.id == change_id).first()
    if not cr: raise HTTPException(404)

    for field in ("title", "description", "change_type", "risk", "priority", "status",
                  "implementation_plan", "rollback_plan", "test_plan",
                  "business_justification", "impact_description", "downtime_minutes",
                  "pir_notes", "pir_success", "owner_id"):
        if field in payload:
            setattr(cr, field, payload[field])

    for dt_field in ("planned_start", "planned_end", "actual_start", "actual_end", "pir_date"):
        if dt_field in payload and payload[dt_field]:
            setattr(cr, dt_field, datetime.fromisoformat(payload[dt_field]).replace(tzinfo=tz.utc))

    # Transiciones automáticas
    if payload.get("status") == "approved":
        cr.approved_at = datetime.now(tz.utc)
        cr.approved_by = current_user.id

    if not current_user.is_superadmin and current_user.organization_id:
        if cr.owner_id:
            owner = db.query(User).filter(User.id == cr.owner_id).first()
            if not owner or owner.organization_id != current_user.organization_id:
                raise HTTPException(403, "No puedes asignar owner fuera de tu organización")
        if cr.related_ticket_id:
            t = _scope_ticket_query(db.query(Ticket), db, current_user).filter(Ticket.id == cr.related_ticket_id).first()
            if not t:
                raise HTTPException(403, "Ticket relacionado fuera de tu organización")
        if cr.related_problem_id:
            p = _scope_problem_query(db.query(Problem), db, current_user).filter(Problem.id == cr.related_problem_id).first()
            if not p:
                raise HTTPException(403, "Problema relacionado fuera de tu organización")

    _commit_or_rollback(db)
    return _change_out(cr)


@router.post("/changes/{change_id}/approve", summary="Aprobar Change Request (CAB)")
def approve_change(
    change_id: str,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from datetime import datetime, timezone as tz
    cr = _scope_change_query(db.query(ITSMChangeRequest), db, current_user).filter(ITSMChangeRequest.id == change_id).first()
    if not cr: raise HTTPException(404)

    approved = payload.get("approved", True)
    cr.status = ChangeStatus.approved if approved else ChangeStatus.cancelled
    cr.approved_at = datetime.now(tz.utc)
    cr.approved_by = current_user.id
    if not approved:
        cr.rejected_reason = payload.get("reason", "Rechazado por CAB")

    _commit_or_rollback(db)
    return {"ok": True, "status": cr.status.value}


# ── Major Incidents ───────────────────────────────────────────────────────────

@router.get("/major-incidents", summary="Listar incidentes mayores")
def list_major_incidents(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy.orm import joinedload
    q = db.query(MajorIncident).options(
        joinedload(MajorIncident.commander)
    )
    if status: q = q.filter(MajorIncident.status == status)
    mis = q.order_by(MajorIncident.declared_at.desc()).all()
    return [_mi_out(m) for m in mis]


def _mi_out(m: MajorIncident) -> dict:
    return {
        "id": m.id, "number": m.number, "title": m.title,
        "status": m.status.value, "severity": m.severity,
        "declared_at": str(m.declared_at),
        "resolved_at": str(m.resolved_at) if m.resolved_at else None,
        "commander": m.commander.full_name if m.commander else None,
        "impact_statement": m.impact_statement,
        "notifications_sent": m.notifications_sent,
    }


@router.post("/major-incidents", summary="Declarar incidente mayor (P1/P2)")
def declare_major_incident(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    import re as _re2
    if not payload.get("title"):
        raise HTTPException(422, "title es obligatorio")
    max_mi = db.query(func.max(MajorIncident.number)).scalar()
    if max_mi:
        _m2 = _re2.search(r"(\d+)$", max_mi)
        n = (int(_m2.group(1)) + 1) if _m2 else 1
    else:
        n = 1

    mi = MajorIncident(
        number=f"MI{n:04d}",
        title=payload["title"],
        severity=payload.get("severity", "P1"),
        impact_statement=payload.get("impact_statement"),
        incident_commander_id=payload.get("commander_id", current_user.id),
        communication_lead_id=payload.get("comm_lead_id"),
    )
    db.add(mi); _commit_or_rollback(db); db.refresh(mi)

    # Escalar tickets vinculados si se proporcionan
    for tid in payload.get("ticket_ids", []):
        t = db.query(Ticket).filter(Ticket.id == tid).first()
        if t:
            t.priority = "p1_critical"
            t.support_level = "l3"

    _commit_or_rollback(db)
    return _mi_out(mi)


@router.patch("/major-incidents/{mi_id}", summary="Actualizar incidente mayor")
def update_major_incident(
    mi_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from datetime import datetime, timezone as tz
    mi = db.query(MajorIncident).filter(MajorIncident.id == mi_id).first()
    if not mi: raise HTTPException(404)

    for field in ("title", "status", "impact_statement", "resolution_summary",
                  "timeline", "notifications_sent"):
        if field in payload: setattr(mi, field, payload[field])

    if payload.get("status") == "resolved":
        mi.resolved_at = datetime.now(tz.utc)

    _commit_or_rollback(db)
    return _mi_out(mi)


# ── Ticket Templates ──────────────────────────────────────────────────────────

@router.get("/ticket-templates", summary="Plantillas de tickets por tipo/servicio")
def list_ticket_templates(
    ticket_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(TicketTemplate).filter(TicketTemplate.is_active == True)
    if ticket_type: q = q.filter(TicketTemplate.ticket_type == ticket_type)
    templates = q.all()
    return [{
        "id": t.id, "name": t.name,
        "ticket_type": t.ticket_type.value,
        "custom_fields": t.custom_fields,
        "default_priority": t.default_priority.value if t.default_priority else None,
        "description_template": t.description_template,
    } for t in templates]


@router.post("/ticket-templates", summary="Crear plantilla de ticket")
def create_ticket_template(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if not payload.get("name") or not payload.get("ticket_type"):
        raise HTTPException(422, "name y ticket_type son obligatorios")
    tmpl = TicketTemplate(
        name=payload["name"],
        ticket_type=payload["ticket_type"],
        category_id=payload.get("category_id"),
        custom_fields=json.dumps(payload.get("custom_fields", [])),
        default_priority=payload.get("default_priority", "p3_medium"),
        default_group_id=payload.get("default_group_id"),
        description_template=payload.get("description_template"),
        auto_assign_to_id=payload.get("auto_assign_to_id"),
    )
    db.add(tmpl); _commit_or_rollback(db); db.refresh(tmpl)
    return {"id": tmpl.id, "name": tmpl.name}


@router.patch("/ticket-templates/{template_id}", summary="Actualizar plantilla")
def update_ticket_template(
    template_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    tmpl = db.query(TicketTemplate).filter(TicketTemplate.id == template_id).first()
    if not tmpl: raise HTTPException(404)
    for field in ("name", "is_active", "default_priority", "description_template"):
        if field in payload: setattr(tmpl, field, payload[field])
    if "custom_fields" in payload:
        tmpl.custom_fields = json.dumps(payload["custom_fields"])
    _commit_or_rollback(db)
    return {"ok": True}


# ── Known Errors (KEDB) ───────────────────────────────────────────────────────

@router.get("/known-errors", summary="Base de errores conocidos (KEDB)")
def list_known_errors(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Problemas en estado known_error con workaround documentado."""
    from sqlalchemy.orm import joinedload
    problems = db.query(Problem).options(
        joinedload(Problem.ci),
        joinedload(Problem.related_tickets),
    ).filter(
        Problem.status == "known_error",
        Problem.workaround.isnot(None),
    ).all()
    return [{
        "id": p.id, "number": p.number, "title": p.title,
        "workaround": p.workaround, "root_cause": p.root_cause,
        "ci": p.ci.name if p.ci else None,
        "affected_tickets": len(p.related_tickets),
    } for p in problems]


# ── Agent Workspace — vista 360 del solicitante ───────────────────────────────

@router.delete("/ticket-templates/{template_id}", summary="Eliminar plantilla")
def delete_ticket_template(template_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    t = db.query(TicketTemplate).filter(TicketTemplate.id == template_id).first()
    if not t: raise HTTPException(404, "Plantilla no encontrada")
    db.delete(t); _commit_or_rollback(db); return {"ok": True}

@router.get("/agent/customer-context/{requester_id}", summary="Contexto 360 del solicitante")
def get_customer_context(
    requester_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Vista unificada del historial del cliente para el agente."""

    recent_tickets = db.query(Ticket).filter(
        Ticket.requester_user_id == requester_id
    ).order_by(Ticket.created_at.desc()).limit(10).all()

    open_tickets = [t for t in recent_tickets if t.status.value not in ("resolved", "closed", "cancelled")]
    resolved = [t for t in recent_tickets if t.resolved_at]

    # CSAT histórico
    csat_scores = [t.csat_score for t in recent_tickets if t.csat_score]
    avg_csat = round(sum(csat_scores) / len(csat_scores), 2) if csat_scores else None

    # MTTR personal
    mttr = 0
    if resolved:
        def _norm(dt):
            return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
        mttr = round(sum((_norm(t.resolved_at) - _norm(t.created_at)).total_seconds() / 60
                         for t in resolved) / len(resolved), 0)

    return {
        "requester_id": requester_id,
        "open_tickets": len(open_tickets),
        "total_tickets_30d": len(recent_tickets),
        "avg_csat": avg_csat,
        "mttr_minutes": mttr,
        "recent_tickets": [{
            "id": t.id, "number": t.number, "title": t.title,
            "status": t.status.value, "priority": t.priority.value,
            "created_at": str(t.created_at),
        } for t in recent_tickets[:5]],
    }

# ── Canned Responses (respuestas rápidas) ─────────────────────────────────────


@router.get("/canned-responses", summary="Listar respuestas rápidas")
def list_canned_responses(
    category: Optional[str] = None,
    search:   Optional[str] = None,
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    q = db.query(CannedResponse).filter(CannedResponse.is_active == True)
    if category: q = q.filter(CannedResponse.category == category)
    if search:
        q = q.filter(
            (CannedResponse.title.ilike(f"%{search}%")) |
            (CannedResponse.body.ilike(f"%{search}%")) |
            (CannedResponse.shortcut.ilike(f"%{search}%"))
        )
    items = q.order_by(CannedResponse.category, CannedResponse.title).all()
    return [
        {
            "id": c.id, "title": c.title, "body": c.body,
            "category": c.category, "shortcut": c.shortcut,
            "is_active": c.is_active,
            "created_by": c.creator.full_name if c.creator else None,
        }
        for c in items
    ]


@router.post("/canned-responses", summary="Crear respuesta rápida", status_code=201)
def create_canned_response(
    payload: CannedResponseIn,
    db: Session = Depends(get_db),
    cu: User = Depends(require_any_manager),
):
    import uuid as _uuid
    c = CannedResponse(id=str(_uuid.uuid4()), created_by=cu.id, **payload.model_dump())
    db.add(c); _commit_or_rollback(db); db.refresh(c)
    return {"id": c.id, "title": c.title, "body": c.body,
            "category": c.category, "shortcut": c.shortcut}


@router.patch("/canned-responses/{canned_id}", summary="Editar respuesta rápida")
def update_canned_response(
    canned_id: str,
    payload: CannedResponseIn,
    db: Session = Depends(get_db),
    cu: User = Depends(require_any_manager),
):
    c = db.query(CannedResponse).filter(CannedResponse.id == canned_id).first()
    if not c: raise HTTPException(404, "Respuesta rápida no encontrada")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    _commit_or_rollback(db); db.refresh(c)
    return {"id": c.id, "title": c.title, "body": c.body}


@router.delete("/canned-responses/{canned_id}", summary="Eliminar respuesta rápida")
def delete_canned_response(
    canned_id: str,
    db: Session = Depends(get_db),
    cu: User = Depends(require_any_manager),
):
    c = db.query(CannedResponse).filter(CannedResponse.id == canned_id).first()
    if not c: raise HTTPException(404, "Respuesta rápida no encontrada")
    db.delete(c); _commit_or_rollback(db)
    return {"deleted": True}


# ── Email-to-ticket inbound webhook ──────────────────────────────────────────
# Compatible with Mailgun, SendGrid, Postmark and any relay that POSTs JSON.
# Protect with INBOUND_EMAIL_SECRET in settings; relay must send it as
# X-Clarive-Email-Secret header.
#
# Expected JSON body (superset of Mailgun/SendGrid inbound parse):
# {
#   "from": "Ada Lovelace <ada@example.com>",
#   "subject": "Printer won't print",
#   "body-plain": "Full text...",       # Mailgun key
#   "text": "Full text...",             # SendGrid / Postmark key
#   "stripped-text": "...",             # Mailgun stripped
#   "sender": "ada@example.com",        # some relays use this
#   "attachments": [...],               # ignored for now
# }



def _parse_email_address(raw: Optional[str]) -> tuple[str, str]:
    """Extract (name, email) from 'Name <email>' or just 'email'."""
    if not raw:
        return "", ""
    raw = raw.strip()
    if "<" in raw and ">" in raw:
        name  = raw[:raw.index("<")].strip().strip('"')
        email = raw[raw.index("<") + 1 : raw.index(">")].strip()
    else:
        name, email = "", raw
    return name, email


@router.post("/inbound-email",
             summary="Email-to-ticket — webhook de email entrante",
             include_in_schema=True,
             status_code=201)
def inbound_email(
    payload: dict = Body(...),
    x_clarive_email_secret: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """
    Receives an inbound email webhook (Mailgun, SendGrid, Postmark, or any relay)
    and creates a Service Desk ticket automatically.

    Security: set INBOUND_EMAIL_SECRET env var; the relay must send it as
    the X-Clarive-Email-Secret HTTP header. If the env var is empty, the
    endpoint is disabled (returns 403) to avoid accidental open relay.
    """
    import uuid as _uuid
    import hmac

    secret = settings.INBOUND_EMAIL_SECRET if hasattr(settings, "INBOUND_EMAIL_SECRET") else ""
    if not secret:
        raise HTTPException(403, "Email inbound deshabilitado: configura INBOUND_EMAIL_SECRET")

    # Constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(x_clarive_email_secret or "", secret):
        raise HTTPException(403, "Firma inválida")

    # ── Parse sender ─────────────────────────────────────────────────────────
    raw_from = (payload.get("from") or payload.get("From") or
                payload.get("sender") or "")
    req_name, req_email = _parse_email_address(raw_from)

    # ── Parse body ───────────────────────────────────────────────────────────
    description = (
        payload.get("stripped-text") or
        payload.get("body-plain") or
        payload.get("text") or
        payload.get("html") or
        "(Sin cuerpo)"
    )[:4000]  # guard against huge emails

    subject = (payload.get("subject") or "(Sin asunto)").strip()[:255]

    # ── Auto-assign to first available agent (round-robin fallback) ──────────
    from app.models.user import UserRole as UR
    agents = db.query(User).filter(
        User.role.in_([UR.admin, UR.pm]),
        User.is_active.is_(True),
    ).order_by(User.created_at).all()
    assigned_to = agents[0].id if agents else None

    # ── Determine SLA policy — use the first active one ───────────────────────
    from app.models.service_desk import SLAPolicy, TicketType, TicketPriority, TicketUrgency, TicketImpact, SupportLevel
    sla = db.query(SLAPolicy).filter(SLAPolicy.is_active.is_(True)).order_by(SLAPolicy.response_hours).first()

    from datetime import timezone as tz
    now = datetime.now(tz.utc)

    ticket = Ticket(
        id               = str(_uuid.uuid4()),
        number           = f"EML-{_uuid.uuid4().hex[:8].upper()}",
        ticket_type      = TicketType.service_request,
        title            = subject,
        description      = description,
        status           = TicketStatus.open,
        priority         = TicketPriority.p3_medium,
        urgency          = TicketUrgency.medium,
        impact           = TicketImpact.user,
        support_level    = SupportLevel.l1,
        source           = "email",
        requester_name   = req_name or req_email or "Email",
        requester_email  = req_email or None,
        assigned_to_user_id = assigned_to,
        sla_policy_id    = sla.id if sla else None,
        sla_response_due = now + timedelta(hours=sla.response_hours) if sla else None,
        sla_resolution_due = now + timedelta(hours=sla.resolution_hours) if sla else None,
        created_at       = now,
    )
    db.add(ticket)
    _commit_or_rollback(db)
    db.refresh(ticket)

    log = logging.getLogger(__name__)
    log.info(f"Email-to-ticket: {ticket.number} from {req_email!r} — '{subject}'")

    return {"ticket_id": ticket.id, "number": ticket.number, "status": "created"}


# ═══════════════════════════════════════════════════════════════════════════════
# ON-CALL SCHEDULES (PagerDuty-style)
# ═══════════════════════════════════════════════════════════════════════════════



@router.get("/oncall/schedules", summary="Listar schedules de guardia")
def list_oncall_schedules(
    group_id: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(OnCallSchedule).options(
        joinedload(OnCallSchedule.group),
        joinedload(OnCallSchedule.entries).joinedload(OnCallEntry.user),
    )
    if group_id:
        q = q.filter(OnCallSchedule.group_id == group_id)
    schedules = q.order_by(OnCallSchedule.name).all()
    return [{
        "id": s.id, "name": s.name, "group_id": s.group_id,
        "group_name": s.group.name if s.group else None,
        "rotation": s.rotation, "timezone": s.timezone,
        "is_active": s.is_active, "description": s.description,
        "entries": [{
            "id": e.id, "user_id": e.user_id,
            "user_name": e.user.full_name if e.user else None,
            "start_dt": e.start_dt.isoformat(), "end_dt": e.end_dt.isoformat(),
            "notes": e.notes,
        } for e in (s.entries or [])],
    } for s in schedules]


@router.post("/oncall/schedules", summary="Crear schedule de guardia", status_code=201)
def create_oncall_schedule(
    payload: OnCallScheduleIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    s = OnCallSchedule(**payload.model_dump())
    db.add(s); _commit_or_rollback(db); db.refresh(s)
    return {"id": s.id, "name": s.name}


@router.patch("/oncall/schedules/{schedule_id}", summary="Actualizar schedule")
def update_oncall_schedule(
    schedule_id: str,
    payload: OnCallScheduleIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    s = db.query(OnCallSchedule).filter(OnCallSchedule.id == schedule_id).first()
    if not s: raise HTTPException(404)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    _commit_or_rollback(db)
    return {"ok": True}


@router.delete("/oncall/schedules/{schedule_id}", summary="Eliminar schedule")
def delete_oncall_schedule(
    schedule_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    s = db.query(OnCallSchedule).filter(OnCallSchedule.id == schedule_id).first()
    if not s: raise HTTPException(404)
    db.delete(s); _commit_or_rollback(db)
    return {"ok": True}


@router.post("/oncall/schedules/{schedule_id}/entries", summary="Añadir turno de guardia", status_code=201)
def add_oncall_entry(
    schedule_id: str,
    payload: OnCallEntryIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    s = db.query(OnCallSchedule).filter(OnCallSchedule.id == schedule_id).first()
    if not s: raise HTTPException(404)
    if payload.start_dt >= payload.end_dt:
        raise HTTPException(400, "start_dt must be before end_dt")
    entry = OnCallEntry(schedule_id=schedule_id, **payload.model_dump())
    db.add(entry); _commit_or_rollback(db)
    return {"id": entry.id}


@router.delete("/oncall/entries/{entry_id}", summary="Eliminar turno de guardia")
def delete_oncall_entry(
    entry_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    entry = db.query(OnCallEntry).filter(OnCallEntry.id == entry_id).first()
    if not entry: raise HTTPException(404)
    db.delete(entry); _commit_or_rollback(db)
    return {"ok": True}


@router.get("/oncall/current", summary="¿Quién está de guardia ahora?")
def get_current_oncall(
    group_id: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Devuelve el agente de guardia en este momento para cada schedule activo."""
    now = datetime.now(timezone.utc)
    q = db.query(OnCallEntry).options(
        joinedload(OnCallEntry.user),
        joinedload(OnCallEntry.schedule).joinedload(OnCallSchedule.group),
    ).filter(
        OnCallEntry.start_dt <= now,
        OnCallEntry.end_dt > now,
    )
    if group_id:
        q = q.join(OnCallSchedule).filter(OnCallSchedule.group_id == group_id)
    entries = q.all()
    return [{
        "schedule_id": e.schedule_id,
        "schedule_name": e.schedule.name if e.schedule else None,
        "group_name": e.schedule.group.name if e.schedule and e.schedule.group else None,
        "user_id": e.user_id,
        "user_name": e.user.full_name if e.user else None,
        "user_email": e.user.email if e.user else None,
        "until": e.end_dt.isoformat(),
    } for e in entries]


# ═══════════════════════════════════════════════════════════════════════════════
# TICKET WATCHERS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/tickets/{ticket_id}/watchers", summary="Ver seguidores del ticket")
def get_watchers(
    ticket_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    watchers = db.query(TicketWatcher).options(
        joinedload(TicketWatcher.user)
    ).filter(TicketWatcher.ticket_id == ticket_id).all()
    return [{
        "id": w.id, "user_id": w.user_id,
        "user_name": w.user.full_name if w.user else None,
        "user_email": w.user.email if w.user else None,
        "since": w.created_at.isoformat() if w.created_at else None,
    } for w in watchers]


@router.post("/tickets/{ticket_id}/watch", summary="Seguir ticket (watch)", status_code=201)
def watch_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket: raise HTTPException(404)
    existing = db.query(TicketWatcher).filter(
        TicketWatcher.ticket_id == ticket_id,
        TicketWatcher.user_id == current_user.id,
    ).first()
    if existing:
        return {"ok": True, "already_watching": True}
    w = TicketWatcher(ticket_id=ticket_id, user_id=current_user.id)
    db.add(w); _commit_or_rollback(db)
    return {"ok": True, "id": w.id}


@router.delete("/tickets/{ticket_id}/watch", summary="Dejar de seguir ticket (unwatch)")
def unwatch_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    w = db.query(TicketWatcher).filter(
        TicketWatcher.ticket_id == ticket_id,
        TicketWatcher.user_id == current_user.id,
    ).first()
    if w:
        db.delete(w); _commit_or_rollback(db)
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# TICKET MERGE (duplicate management)
# ═══════════════════════════════════════════════════════════════════════════════



@router.post("/tickets/{ticket_id}/merge", summary="Fusionar ticket duplicado en éste")
def merge_ticket(
    ticket_id: str,
    payload: MergeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """
    Marca merged_ticket_id como duplicado y lo cierra, transfiriendo su historial
    al ticket primario.
    """
    primary = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not primary: raise HTTPException(404, "Ticket primario no encontrado")
    dup = db.query(Ticket).filter(Ticket.id == payload.merged_ticket_id).first()
    if not dup: raise HTTPException(404, "Ticket a fusionar no encontrado")
    if primary.id == dup.id: raise HTTPException(400, "No se puede fusionar un ticket consigo mismo")

    # Close the duplicate
    dup.status = TicketStatus.closed
    dup.resolution = f"Ticket duplicado. Fusionado en {primary.number}."
    dup.closed_at = datetime.now(timezone.utc)

    # Transfer comments to primary
    db.query(TicketComment).filter(TicketComment.ticket_id == dup.id).update(
        {"ticket_id": primary.id}, synchronize_session=False
    )

    # Log the merge
    merge_log = TicketMerge(
        primary_id=primary.id,
        merged_id=dup.id,
        reason=payload.reason,
        merged_by_user=current_user.id,
    )
    db.add(merge_log)

    # Add history note on primary
    _log_history(db, primary.id, "merged_ticket", None, dup.number, current_user.id)

    _commit_or_rollback(db)
    return {"ok": True, "primary": primary.number, "merged": dup.number}


@router.post("/tickets/{ticket_id}/split", summary="Dividir ticket en ticket hijo")
def split_ticket(
    ticket_id: str,
    payload: SplitTicketIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    parent = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not parent:
        raise HTTPException(404, "Ticket origen no encontrado")

    child_title = payload.title or f"{parent.title} (split)"
    child_description = payload.description or parent.description
    child_priority = payload.priority or (parent.priority.value if hasattr(parent.priority, "value") else parent.priority)
    child_type = payload.ticket_type or (parent.ticket_type.value if hasattr(parent.ticket_type, "value") else parent.ticket_type)

    child = Ticket(
        number=_next_ticket_number(child_type, db),
        ticket_type=child_type,
        title=child_title,
        description=child_description,
        priority=child_priority,
        urgency=payload.urgency or parent.urgency,
        impact=payload.impact or parent.impact,
        support_level=payload.support_level or parent.support_level,
        status=TicketStatus.new,
        requester_user_id=parent.requester_user_id,
        requester_client_id=parent.requester_client_id,
        requester_name=parent.requester_name,
        requester_email=parent.requester_email,
        project_id=parent.project_id,
        client_id=parent.client_id,
        contract_id=parent.contract_id,
        ci_id=parent.ci_id,
        service_item_id=parent.service_item_id,
        sla_policy_id=parent.sla_policy_id,
        tags=payload.tags if payload.tags is not None else parent.tags,
        source=parent.source,
        parent_ticket_id=parent.id,
        created_by_user_id=current_user.id,
    )
    db.add(child)
    db.flush()

    link = TicketLink(
        source_id=parent.id,
        target_id=child.id,
        link_type="child_of",
        created_by=current_user.id,
    )
    db.add(link)

    if payload.copy_latest_comments > 0:
        comments = db.query(TicketComment).filter(
            TicketComment.ticket_id == parent.id
        ).order_by(TicketComment.created_at.desc()).limit(payload.copy_latest_comments).all()
        for c in reversed(comments):
            db.add(TicketComment(
                ticket_id=child.id,
                body=c.body,
                is_public=c.is_public,
                is_solution=False,
                author_user_id=c.author_user_id,
                author_client_id=c.author_client_id,
                author_name=c.author_name,
            ))

    _log_history(db, parent.id, "split_ticket", None, child.number, current_user.id)
    _log_history(db, child.id, "created_from_split", None, parent.number, current_user.id)

    _commit_or_rollback(db)
    db.refresh(child)
    return {"ok": True, "parent": parent.number, "child": child.number, "child_id": child.id}


@router.post("/tickets/{ticket_id}/ai-suggest", summary="Sugerir respuesta IA para ticket")
def suggest_ticket_response_ai(
    ticket_id: str,
    payload: Optional[dict] = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Ticket no encontrado")

    req = payload or {}
    user_content = (req.get("content") or "").strip()
    query_text = user_content or f"{ticket.title}\n{ticket.description}"

    kb_matches = []
    try:
        from app.services.semantic_classifier import _get_model, _cosine

        model, _ = _get_model()
        q_emb = model.encode([query_text], show_progress_bar=False)[0]
        if hasattr(q_emb, "tolist"):
            q_emb = q_emb.tolist()

        arts = db.query(KBArticle).filter(KBArticle.status == KBStatus.published).all()
        scored = []
        for a in arts:
            text = f"{a.title or ''}\n{a.summary or ''}\n{a.body or ''}".strip()
            if not text:
                continue
            a_emb = model.encode([text], show_progress_bar=False)[0]
            if hasattr(a_emb, "tolist"):
                a_emb = a_emb.tolist()
            sim = _cosine(q_emb, a_emb)
            scored.append((sim, a))
        scored.sort(key=lambda x: x[0], reverse=True)
        kb_matches = [{
            "id": a.id,
            "number": a.number,
            "title": a.title,
            "summary": a.summary,
            "score": round(float(s), 4),
        } for s, a in scored[:5] if s > 0]
    except Exception:
        like = db.query(KBArticle).filter(
            KBArticle.status == KBStatus.published,
            or_(
                KBArticle.title.ilike(f"%{query_text[:80]}%"),
                KBArticle.body.ilike(f"%{query_text[:80]}%"),
            )
        ).limit(5).all()
        kb_matches = [{
            "id": a.id,
            "number": a.number,
            "title": a.title,
            "summary": a.summary,
            "score": None,
        } for a in like]

    canned = db.query(CannedResponse).filter(CannedResponse.is_active == True).all()
    q_words = {w for w in query_text.lower().split() if len(w) >= 4}
    canned_scored = []
    for c in canned:
        text = f"{c.title or ''} {c.body or ''} {c.shortcut or ''}".lower()
        overlap = sum(1 for w in q_words if w in text)
        if overlap > 0:
            canned_scored.append((overlap, c))
    canned_scored.sort(key=lambda x: x[0], reverse=True)
    canned_matches = [{
        "id": c.id,
        "title": c.title,
        "body": c.body,
        "shortcut": c.shortcut,
        "score": s,
    } for s, c in canned_scored[:5]]

    kb_context = "\n\n".join(
        [f"[{k['number']}] {k['title']}\n{k.get('summary') or ''}" for k in kb_matches]
    ) or "(sin artículos KB relevantes)"
    canned_context = "\n\n".join(
        [f"[{c['title']}] {c['body']}" for c in canned_matches]
    ) or "(sin respuestas rápidas relevantes)"

    system = (
        "Eres un agente senior de Service Desk ITIL. "
        "Redacta una respuesta al cliente en español, profesional, breve y accionable. "
        "No inventes hechos. Si faltan datos, pide información concreta."
    )
    messages = [{
        "role": "user",
        "content": (
            f"Ticket: {ticket.number}\\n"
            f"Título: {ticket.title}\\n"
            f"Descripción: {ticket.description}\\n\\n"
            f"Contenido adicional del agente: {user_content or '(ninguno)'}\\n\\n"
            f"Artículos KB similares:\\n{kb_context}\\n\\n"
            f"Canned responses sugeridas:\\n{canned_context}\\n\\n"
            "Devuélveme SOLO un borrador de respuesta listo para enviar al cliente."
        ),
    }]

    try:
        from app.api.v1.endpoints.ai_providers import call_ai
        draft = call_ai(
            db,
            messages=messages,
            system=system,
            module="service_desk",
            user_id=current_user.id,
            max_tokens=500,
        )
    except Exception as exc:
        _log = logging.getLogger(__name__)
        _log.warning("AI suggest fallback for ticket %s: %s", ticket_id, exc)
        kb_hint = kb_matches[0]["title"] if kb_matches else "la base de conocimiento"
        draft = (
            "Gracias por contactar con soporte. Estamos revisando tu incidencia y ya hemos iniciado diagnóstico. "
            f"Como primer paso, vamos a contrastarlo con {kb_hint}. "
            "¿Podrías confirmarnos los pasos exactos para reproducirlo y, si es posible, adjuntar captura del error y hora aproximada?"
        )

    return {
        "ticket_id": ticket.id,
        "ticket_number": ticket.number,
        "draft": draft,
        "kb_matches": kb_matches,
        "canned_matches": canned_matches,
    }


@router.patch("/sla-policies/assign/client/{client_id}", summary="Asignar política SLA a cliente")
def assign_sla_to_client(
    client_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    sla_policy_id = payload.get("sla_policy_id")
    cli = db.query(Client).filter(Client.id == client_id).first()
    if not cli:
        raise HTTPException(404, "Cliente no encontrado")
    if sla_policy_id:
        p = db.query(SLAPolicy).filter(SLAPolicy.id == sla_policy_id, SLAPolicy.is_active == True).first()
        if not p:
            raise HTTPException(404, "Política SLA no encontrada")
    cli.sla_policy_id = sla_policy_id
    _commit_or_rollback(db)
    return {"ok": True, "client_id": client_id, "sla_policy_id": sla_policy_id}


@router.patch("/sla-policies/assign/contract/{contract_id}", summary="Asignar política SLA a contrato")
def assign_sla_to_contract(
    contract_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    sla_policy_id = payload.get("sla_policy_id")
    ctr = db.query(Contract).filter(Contract.id == contract_id).first()
    if not ctr:
        raise HTTPException(404, "Contrato no encontrado")
    if sla_policy_id:
        p = db.query(SLAPolicy).filter(SLAPolicy.id == sla_policy_id, SLAPolicy.is_active == True).first()
        if not p:
            raise HTTPException(404, "Política SLA no encontrada")
    ctr.sla_policy_id = sla_policy_id
    _commit_or_rollback(db)
    return {"ok": True, "contract_id": contract_id, "sla_policy_id": sla_policy_id}


@router.get("/tickets/{ticket_id}/merges", summary="Ver merges de un ticket")
def get_merges(
    ticket_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    merges = db.query(TicketMerge).options(
        joinedload(TicketMerge.merged_ticket),
        joinedload(TicketMerge.merged_by),
    ).filter(TicketMerge.primary_id == ticket_id).all()
    return [{
        "id": m.id,
        "merged_ticket_number": m.merged_ticket.number if m.merged_ticket else None,
        "reason": m.reason,
        "merged_by": m.merged_by.full_name if m.merged_by else None,
        "merged_at": m.merged_at.isoformat() if m.merged_at else None,
    } for m in merges]


# ═══════════════════════════════════════════════════════════════════════════════
# AUTO-ESCALATION RULES
# ═══════════════════════════════════════════════════════════════════════════════




@router.get("/escalation-rules", summary="Listar reglas de escalada automática")
def list_escalation_rules(
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    rules = db.query(EscalationRule).order_by(EscalationRule.sort_order).all()
    return [{
        "id": r.id, "name": r.name, "is_active": r.is_active,
        "sort_order": r.sort_order, "trigger": r.trigger, "action": r.action,
        "applies_to_priority": r.applies_to_priority,
        "idle_hours_threshold": r.idle_hours_threshold,
        "group_id": r.group_id, "target_group_id": r.target_group_id,
        "notify_user_ids": r.notify_user_ids, "target_priority": r.target_priority,
    } for r in rules]


@router.post("/escalation-rules", summary="Crear regla de escalada", status_code=201)
def create_escalation_rule(
    payload: EscalationRuleIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    # Validate enums
    try:
        EscalationTrigger(payload.trigger)
        EscalationAction(payload.action)
    except ValueError as e:
        raise HTTPException(400, str(e))
    rule = EscalationRule(**payload.model_dump())
    db.add(rule); _commit_or_rollback(db); db.refresh(rule)
    return {"ok": True, "id": rule.id}


@router.patch("/escalation-rules/{rule_id}", summary="Actualizar regla de escalada")
def update_escalation_rule(
    rule_id: str,
    payload: EscalationRuleIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    rule = db.query(EscalationRule).filter(EscalationRule.id == rule_id).first()
    if not rule: raise HTTPException(404)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(rule, k, v)
    _commit_or_rollback(db)
    return {"ok": True}


@router.delete("/escalation-rules/{rule_id}", summary="Eliminar regla de escalada")
def delete_escalation_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    rule = db.query(EscalationRule).filter(EscalationRule.id == rule_id).first()
    if not rule: raise HTTPException(404)
    db.delete(rule); _commit_or_rollback(db)
    return {"ok": True}


@router.post("/escalation-rules/run", summary="Ejecutar reglas de escalada (job manual/cron)")
def run_escalation_rules(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Evalúa todas las reglas activas contra tickets abiertos.
    En producción esto lo ejecutaría el scheduler periódicamente.
    """
    now = datetime.now(timezone.utc)
    rules = db.query(EscalationRule).filter(EscalationRule.is_active == True).order_by(EscalationRule.sort_order).all()
    open_tickets = db.query(Ticket).filter(
        Ticket.status.not_in([TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled])
    ).all()

    fired = 0
    for rule in rules:
        priority_filter = None
        if rule.applies_to_priority:
            import json as _json
            try:
                priority_filter = _json.loads(rule.applies_to_priority)
            except Exception:
                priority_filter = [rule.applies_to_priority]

        for ticket in open_tickets:
            if priority_filter and ticket.priority.value not in priority_filter:
                continue
            if rule.group_id and ticket.assigned_group_id != rule.group_id:
                continue

            should_fire = False
            if rule.trigger == EscalationTrigger.sla_at_risk and ticket.sla_resolution_status == "at_risk":
                should_fire = True
            elif rule.trigger == EscalationTrigger.sla_breached and ticket.sla_resolution_status == "breached":
                should_fire = True
            elif rule.trigger == EscalationTrigger.idle_hours and rule.idle_hours_threshold:
                last_activity = ticket.updated_at or ticket.created_at
                if last_activity:
                    idle = (now - last_activity).total_seconds() / 3600
                    should_fire = idle >= rule.idle_hours_threshold
            elif rule.trigger == EscalationTrigger.priority and not ticket.assigned_to_user_id:
                should_fire = True

            if not should_fire:
                continue

            # Prevent double-firing: check if already logged recently (last hour)
            recent = db.query(EscalationLog).filter(
                EscalationLog.rule_id == rule.id,
                EscalationLog.ticket_id == ticket.id,
                EscalationLog.triggered_at >= now - timedelta(hours=1),
            ).first()
            if recent:
                continue

            # Apply action
            action_desc = f"Rule '{rule.name}' fired: {rule.action}"
            if rule.action == EscalationAction.reassign_group and rule.target_group_id:
                ticket.assigned_group_id = rule.target_group_id
                action_desc += f" → group {rule.target_group_id}"
            elif rule.action == EscalationAction.elevate_priority and rule.target_priority:
                old_p = ticket.priority.value
                ticket.priority = TicketPriority(rule.target_priority)
                action_desc += f" {old_p} → {rule.target_priority}"

            log = EscalationLog(rule_id=rule.id, ticket_id=ticket.id, action_taken=action_desc)
            db.add(log)
            fired += 1

    _commit_or_rollback(db)
    return {"ok": True, "rules_evaluated": len(rules), "tickets_evaluated": len(open_tickets), "escalations_fired": fired}


@router.get("/escalation-rules/logs", summary="Historial de escaladas disparadas")
def get_escalation_logs(
    ticket_id: Optional[str] = None,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    q = db.query(EscalationLog).options(
        joinedload(EscalationLog.rule),
        joinedload(EscalationLog.ticket),
    )
    if ticket_id:
        q = q.filter(EscalationLog.ticket_id == ticket_id)
    logs = q.order_by(EscalationLog.triggered_at.desc()).limit(limit).all()
    return [{
        "id": l.id,
        "rule_name": l.rule.name if l.rule else None,
        "ticket_number": l.ticket.number if l.ticket else None,
        "action_taken": l.action_taken,
        "triggered_at": l.triggered_at.isoformat() if l.triggered_at else None,
    } for l in logs]


# ═══════════════════════════════════════════════════════════════════════════════
# SLA HOLIDAY CALENDAR
# ═══════════════════════════════════════════════════════════════════════════════




@router.get("/sla-holidays", summary="Festivos del calendario SLA")
def list_holidays(
    year: Optional[int] = None,
    country: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(SDSLAHoliday)
    if year:
        q = q.filter(SDSLAHoliday.holiday_date.like(f"{year}-%"))
    if country:
        q = q.filter((SDSLAHoliday.country == country) | (SDSLAHoliday.country == None))
    holidays = q.order_by(SDSLAHoliday.holiday_date).all()
    return [{
        "id": h.id, "name": h.name, "holiday_date": h.holiday_date,
        "country": h.country, "sla_policy_id": h.sla_policy_id,
    } for h in holidays]


@router.post("/sla-holidays", summary="Añadir festivo al calendario SLA", status_code=201)
def create_holiday(
    payload: HolidayIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    h = SDSLAHoliday(**payload.model_dump())
    db.add(h); _commit_or_rollback(db)
    return {"id": h.id}


@router.delete("/sla-holidays/{holiday_id}", summary="Eliminar festivo")
def delete_holiday(
    holiday_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    h = db.query(SDSLAHoliday).filter(SDSLAHoliday.id == holiday_id).first()
    if not h: raise HTTPException(404)
    db.delete(h); _commit_or_rollback(db)
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# WORKLOAD-BALANCED ASSIGNMENT (round-robin por carga de tickets abiertos)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/groups/{group_id}/workload", summary="Distribución de carga de tickets por agente en el grupo")
def get_group_workload(
    group_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    group = db.query(AgentGroup).options(
        joinedload(AgentGroup.members).joinedload(AgentGroupMember.user)
    ).filter(AgentGroup.id == group_id).first()
    if not group: raise HTTPException(404)

    result = []
    for member in group.members:
        open_count = db.query(func.count(Ticket.id)).filter(
            Ticket.assigned_to_user_id == member.user_id,
            Ticket.status.not_in([TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled]),
        ).scalar() or 0
        p1_count = db.query(func.count(Ticket.id)).filter(
            Ticket.assigned_to_user_id == member.user_id,
            Ticket.priority == TicketPriority.p1_critical,
            Ticket.status.not_in([TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled]),
        ).scalar() or 0
        result.append({
            "user_id": member.user_id,
            "user_name": member.user.full_name if member.user else None,
            "is_lead": member.is_lead,
            "open_tickets": open_count,
            "p1_tickets": p1_count,
        })

    result.sort(key=lambda x: x["open_tickets"])
    return {
        "group_id": group_id,
        "group_name": group.name,
        "agents": result,
        "recommended_assignee": result[0] if result else None,
    }


@router.post("/tickets/{ticket_id}/auto-assign", summary="Auto-asignar ticket al agente con menos carga del grupo")
def auto_assign_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket: raise HTTPException(404)
    if not ticket.assigned_group_id:
        raise HTTPException(400, "El ticket no tiene grupo asignado. Asigna un grupo primero.")

    members = db.query(AgentGroupMember).filter(
        AgentGroupMember.group_id == ticket.assigned_group_id
    ).all()
    if not members:
        raise HTTPException(400, "El grupo no tiene agentes")

    # Find the agent with fewest open tickets (round-robin by load)
    best_agent_id = None
    best_count = float("inf")
    for member in members:
        count = db.query(func.count(Ticket.id)).filter(
            Ticket.assigned_to_user_id == member.user_id,
            Ticket.status.not_in([TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled]),
        ).scalar() or 0
        if count < best_count:
            best_count = count
            best_agent_id = member.user_id

    old_assignee = ticket.assigned_to_user_id
    ticket.assigned_to_user_id = best_agent_id
    if ticket.status == TicketStatus.new:
        ticket.status = TicketStatus.assigned
    _log_history(db, ticket.id, "assigned_to_user_id", old_assignee, best_agent_id, current_user.id)
    _commit_or_rollback(db)

    agent = db.query(User).filter(User.id == best_agent_id).first()
    return {"ok": True, "assigned_to": best_agent_id, "agent_name": agent.full_name if agent else None}


# ═══════════════════════════════════════════════════════════════════════════════
# ASSET MANAGEMENT (HAM / SAM)
# ═══════════════════════════════════════════════════════════════════════════════



def _next_asset_code(db: Session) -> str:
    import re
    max_code = db.query(func.max(Asset.code)).scalar()
    if max_code:
        m = re.search(r"(\d+)$", max_code)
        n = (int(m.group(1)) + 1) if m else 1
    else:
        n = 1
    return f"ASSET-{n:04d}"


def _asset_out(a: Asset) -> dict:
    return {
        "id": a.id, "code": a.code, "name": a.name,
        "asset_type": a.asset_type, "status": a.status,
        "serial_number": a.serial_number, "model": a.model,
        "manufacturer": a.manufacturer, "part_number": a.part_number,
        "license_key": a.license_key, "license_seats": a.license_seats,
        "license_used": a.license_used,
        "purchase_date": a.purchase_date, "warranty_expiry": a.warranty_expiry,
        "eol_date": a.eol_date, "lease_expiry": a.lease_expiry,
        "purchase_price": a.purchase_price, "current_value": a.current_value,
        "currency": a.currency, "po_number": a.po_number,
        "vendor": a.vendor, "vendor_contract": a.vendor_contract,
        "location": a.location,
        "assigned_user_id": a.assigned_user_id,
        "assigned_user_name": a.assigned_user.full_name if a.assigned_user else None,
        "department": a.department, "ci_id": a.ci_id,
        "tags": a.tags, "notes": a.notes,
        "managed_by_user_id": a.managed_by_user_id,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@router.get("/assets", summary="Listar activos IT (HAM/SAM)")
def list_assets(
    asset_type: Optional[str] = None,
    status: Optional[str] = None,
    assigned_user_id: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(Asset).options(joinedload(Asset.assigned_user))
    if asset_type:
        q = q.filter(Asset.asset_type == asset_type)
    if status:
        q = q.filter(Asset.status == status)
    if assigned_user_id:
        q = q.filter(Asset.assigned_user_id == assigned_user_id)
    if search:
        q = q.filter(
            (Asset.name.ilike(f"%{search}%")) |
            (Asset.serial_number.ilike(f"%{search}%")) |
            (Asset.code.ilike(f"%{search}%")) |
            (Asset.model.ilike(f"%{search}%"))
        )
    total = q.count()
    assets = q.order_by(Asset.code).offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "page": page, "assets": [_asset_out(a) for a in assets]}


@router.get("/assets/stats", summary="Estadísticas del inventario de activos")
def asset_stats(
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    total = db.query(func.count(Asset.id)).scalar() or 0
    by_type = db.query(Asset.asset_type, func.count(Asset.id)).group_by(Asset.asset_type).all()
    by_status = db.query(Asset.status, func.count(Asset.id)).group_by(Asset.status).all()
    expiring_warranty = db.query(func.count(Asset.id)).filter(
        Asset.warranty_expiry.isnot(None),
        Asset.warranty_expiry <= (date.today() + timedelta(days=90)).isoformat(),
        Asset.warranty_expiry >= date.today().isoformat(),
    ).scalar() or 0
    eol_soon = db.query(func.count(Asset.id)).filter(
        Asset.eol_date.isnot(None),
        Asset.eol_date <= (date.today() + timedelta(days=180)).isoformat(),
        Asset.eol_date >= date.today().isoformat(),
    ).scalar() or 0
    return {
        "total_assets": total,
        "by_type": {t: c for t, c in by_type},
        "by_status": {s: c for s, c in by_status},
        "expiring_warranty_90d": expiring_warranty,
        "eol_within_180d": eol_soon,
    }


@router.get("/assets/{asset_id}", summary="Detalle de activo")
def get_asset(
    asset_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    a = db.query(Asset).options(
        joinedload(Asset.assigned_user),
        joinedload(Asset.managed_by),
        joinedload(Asset.history),
    ).filter(Asset.id == asset_id).first()
    if not a: raise HTTPException(404)
    out = _asset_out(a)
    out["history"] = [{
        "field": h.field_name, "old": h.old_value, "new": h.new_value,
        "note": h.note, "changed_at": h.changed_at.isoformat() if h.changed_at else None,
    } for h in (a.history or [])]
    return out


@router.post("/assets", summary="Crear activo IT", status_code=201)
def create_asset(
    payload: AssetIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    try:
        AssetType(payload.asset_type)
    except ValueError:
        raise HTTPException(400, f"Invalid asset_type: {payload.asset_type}")
    asset = Asset(code=_next_asset_code(db), **payload.model_dump())
    db.add(asset); _commit_or_rollback(db); db.refresh(asset)
    return _asset_out(asset)


@router.patch("/assets/{asset_id}", summary="Actualizar activo")
def update_asset(
    asset_id: str,
    payload: AssetUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    a = db.query(Asset).options(joinedload(Asset.assigned_user)).filter(Asset.id == asset_id).first()
    if not a: raise HTTPException(404)

    update_data = payload.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        old_val = str(getattr(a, k, None))
        setattr(a, k, v)
        if old_val != str(v):
            hist = AssetHistory(asset_id=a.id, field_name=k, old_value=old_val, new_value=str(v), changed_by=current_user.id)
            db.add(hist)

    _commit_or_rollback(db); db.refresh(a)
    return _asset_out(a)


@router.delete("/assets/{asset_id}", summary="Dar de baja activo (retired)")
def retire_asset(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    a = db.query(Asset).filter(Asset.id == asset_id).first()
    if not a: raise HTTPException(404)
    old = a.status
    a.status = AssetStatus.retired
    hist = AssetHistory(asset_id=a.id, field_name="status", old_value=str(old), new_value="retired", changed_by=current_user.id)
    db.add(hist); _commit_or_rollback(db)
    return {"ok": True}


@router.post("/assets/{asset_id}/assign", summary="Asignar activo a usuario")
def assign_asset(
    asset_id: str,
    user_id: str = Body(..., embed=True),
    notes: Optional[str] = Body(None, embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    a = db.query(Asset).filter(Asset.id == asset_id).first()
    if not a: raise HTTPException(404)
    user = db.query(User).filter(User.id == user_id).first()
    if not user: raise HTTPException(404, "User not found")

    old_user = a.assigned_user_id
    a.assigned_user_id = user_id
    a.status = AssetStatus.deployed
    hist = AssetHistory(
        asset_id=a.id, field_name="assigned_user_id",
        old_value=old_user, new_value=user_id,
        changed_by=current_user.id, note=notes,
    )
    db.add(hist); _commit_or_rollback(db)
    return {"ok": True, "assigned_to": user.full_name}


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE STATUS PAGE
# ═══════════════════════════════════════════════════════════════════════════════




@router.get("/status-page", summary="Estado público del servicio (status page)")
def get_status_page(
    db: Session = Depends(get_db),
):
    """Endpoint público — no requiere autenticación."""
    components = db.query(StatusPageComponent).filter(
        StatusPageComponent.is_public == True
    ).order_by(StatusPageComponent.sort_order, StatusPageComponent.name).all()

    # Global status: worst component status
    status_severity = {
        "operational": 0, "degraded_performance": 1,
        "partial_outage": 2, "major_outage": 3, "maintenance": 4,
    }
    worst = "operational"
    for c in components:
        if status_severity.get(c.status, 0) > status_severity.get(worst, 0):
            worst = c.status

    groups: dict = {}
    for c in components:
        g = c.group_name or "General"
        if g not in groups:
            groups[g] = []

        # Active incidents for this component
        active_incidents = db.query(StatusPageIncident).filter(
            StatusPageIncident.component_id == c.id,
            StatusPageIncident.resolved_at == None,
        ).all()

        groups[g].append({
            "id": c.id, "name": c.name, "description": c.description,
            "status": c.status, "uptime_30d_pct": c.uptime_30d_pct,
            "active_incidents": [{
                "id": i.id, "title": i.title, "status": i.status,
                "impact": i.impact, "started_at": i.started_at.isoformat() if i.started_at else None,
            } for i in active_incidents],
        })

    return {
        "overall_status": worst,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "groups": groups,
    }

@router.get("/status-page/embed.js", summary="Snippet JS embebible de status page", response_class=PlainTextResponse)
def status_page_embed_js():
    """Returns a lightweight embeddable script for third-party websites."""
    script = """
(function(){
    var scriptTag = document.currentScript;
    var api = (scriptTag && scriptTag.getAttribute('data-api')) || window.location.origin;
    var targetId = (scriptTag && scriptTag.getAttribute('data-target')) || 'clarive-status-page';
    var mount = document.getElementById(targetId);
    if(!mount){
        mount = document.createElement('div');
        mount.id = targetId;
        document.body.appendChild(mount);
    }
    fetch(api + '/api/v1/sd/status-page')
        .then(function(r){ return r.json(); })
        .then(function(data){
            var html = '<div style="font-family:system-ui,sans-serif;border:1px solid #d0d7de;border-radius:8px;padding:12px;max-width:760px">'
                + '<div style="font-weight:700;margin-bottom:8px">Service Status: ' + (data.overall_status || 'operational') + '</div>';
            Object.keys(data.groups || {}).forEach(function(g){
                html += '<div style="margin-top:8px"><div style="font-weight:600">' + g + '</div>';
                (data.groups[g] || []).forEach(function(c){
                    html += '<div style="display:flex;justify-content:space-between;font-size:13px;padding:4px 0">'
                        + '<span>' + c.name + '</span><span>' + c.status + '</span></div>';
                });
                html += '</div>';
            });
            html += '</div>';
            mount.innerHTML = html;
        })
        .catch(function(){ mount.innerHTML = '<div>Unable to load status page</div>'; });
})();
""".strip()
    return script


@router.get("/status-page/components", summary="Listar componentes del status page (admin)")
def list_status_components(
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    components = db.query(StatusPageComponent).order_by(
        StatusPageComponent.sort_order, StatusPageComponent.name
    ).all()
    return [{
        "id": c.id, "name": c.name, "description": c.description,
        "group_name": c.group_name, "sort_order": c.sort_order,
        "status": c.status, "is_public": c.is_public, "ci_id": c.ci_id,
        "uptime_30d_pct": c.uptime_30d_pct,
    } for c in components]


@router.post("/status-page/components", summary="Crear componente del status page", status_code=201)
def create_status_component(
    payload: StatusComponentIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    try:
        StatusPageComponentStatus(payload.status)
    except ValueError:
        raise HTTPException(400, f"Invalid status: {payload.status}")
    c = StatusPageComponent(**payload.model_dump())
    db.add(c); _commit_or_rollback(db); db.refresh(c)
    return {"id": c.id, "name": c.name}


@router.patch("/status-page/components/{component_id}", summary="Actualizar estado de componente")
def update_status_component(
    component_id: str,
    payload: StatusComponentIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    c = db.query(StatusPageComponent).filter(StatusPageComponent.id == component_id).first()
    if not c: raise HTTPException(404)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    _commit_or_rollback(db)
    return {"ok": True}


@router.delete("/status-page/components/{component_id}", summary="Eliminar componente")
def delete_status_component(
    component_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    c = db.query(StatusPageComponent).filter(StatusPageComponent.id == component_id).first()
    if not c: raise HTTPException(404)
    db.delete(c); _commit_or_rollback(db)
    return {"ok": True}


@router.post("/status-page/components/{component_id}/incidents", summary="Declarar incidente en status page", status_code=201)
def declare_status_incident(
    component_id: str,
    payload: StatusIncidentIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    c = db.query(StatusPageComponent).filter(StatusPageComponent.id == component_id).first()
    if not c: raise HTTPException(404)

    import json as _json
    now = datetime.now(timezone.utc)
    initial_update = [{"time": now.isoformat(), "status": payload.status, "message": payload.update_message or "Investigating"}]
    inc = StatusPageIncident(
        component_id=component_id,
        title=payload.title,
        status=payload.status,
        impact=payload.impact,
        ticket_id=payload.ticket_id,
        updates=_json.dumps(initial_update),
    )
    # Update component status to reflect incident
    c.status = payload.impact
    db.add(inc); _commit_or_rollback(db); db.refresh(inc)
    return {"id": inc.id}


@router.post("/status-page/incidents/{incident_id}/updates", summary="Añadir actualización a incidente de status page")
def add_status_incident_update(
    incident_id: str,
    payload: StatusIncidentUpdateIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    import json as _json
    inc = db.query(StatusPageIncident).filter(StatusPageIncident.id == incident_id).first()
    if not inc: raise HTTPException(404)

    updates = _json.loads(inc.updates or "[]")
    updates.append({
        "time": datetime.now(timezone.utc).isoformat(),
        "status": payload.status,
        "message": payload.message,
    })
    inc.updates = _json.dumps(updates)
    inc.status = payload.status

    if payload.status == "resolved":
        inc.resolved_at = datetime.now(timezone.utc)
        # Restore component to operational
        component = db.query(StatusPageComponent).filter(
            StatusPageComponent.id == inc.component_id
        ).first()
        if component:
            component.status = "operational"

    _commit_or_rollback(db)
    return {"ok": True, "updates_count": len(updates)}


