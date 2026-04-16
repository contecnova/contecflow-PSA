"""
Service Desk ITSM/ITIL API – full ITIL-aligned endpoints.
Works standalone OR integrated with Clarive projects/contracts.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Header, Body, BackgroundTasks, Cookie, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session, joinedload
from typing import Optional
from datetime import datetime, timedelta, date, timezone
import logging

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager, require_admin
from app.models.user import User, UserRole
from app.models.service_desk import (
    ConfigurationItem,
    Ticket, TicketStatus, TicketPriority,
    TicketComment,
    KBArticle, Announcement,
    # v3 — market-leader extensions
)
from app.models.clients import Client
from app.models.pipeline import Contract

router = APIRouter()
logger = logging.getLogger(__name__)


from app.services.service_desk.ticket_ops_service import commit_or_rollback as _commit_or_rollback

# ── Service layer & schemas ───────────────────────────────────────────────────
from app.services.sla_service import (  # noqa: E402
    next_problem_number as _next_problem_number,
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
    scope_ci_query as _scope_ci_query,
)
from app.services.service_desk.ticket_read_service import (  # noqa: E402
    list_tickets_payload,
    my_queue_payload,
    client_my_tickets_payload,
    client_ticket_detail_payload,
    ticket_detail_payload,
)
from app.services.service_desk.ticket_update_service import (  # noqa: E402
    get_scoped_ticket_or_404,
    apply_ticket_update,
)
from app.services.service_desk.ticket_creation_service import (  # noqa: E402
    build_internal_ticket,
    build_client_portal_ticket,
)
from app.services.service_desk.comment_service import (  # noqa: E402
    get_scoped_ticket_or_404 as get_scoped_ticket_for_comment_or_404,
    add_internal_comment,
    get_ticket_or_404 as get_ticket_for_client_comment_or_404,
    add_client_comment,
)
from app.services.service_desk.csat_service import (  # noqa: E402
    submit_ticket_csat,
)
from app.services.service_desk.ticket_ops_service import (  # noqa: E402
    get_scoped_ticket_or_404 as get_scoped_ticket_for_ops_or_404,
    add_ticket_time,
    escalate_ticket_level,
)
from app.services.service_desk.problem_service import (  # noqa: E402
    list_problems_payload,
    create_problem_record,
    get_scoped_problem_or_404,
    apply_problem_update,
    link_ticket_to_problem_record,
)
from app.services.service_desk.kb_service import (  # noqa: E402
    list_kb_articles_scoped,
    serialize_kb_articles,
    get_kb_article_and_increment_view,
    serialize_kb_article_detail,
    build_kb_article,
    get_scoped_kb_article_or_404,
    apply_kb_article_update,
    update_kb_helpful_vote,
    create_kb_from_ticket,
    delete_kb_article,
)
from app.services.service_desk.announcement_service import (  # noqa: E402
    list_active_announcements,
    serialize_announcements,
    build_announcement,
    deactivate_announcement_record,
)
from app.services.service_desk.cmdb_service import (  # noqa: E402
    list_cmdb_items,
    serialize_cmdb_items,
    enforce_ci_org_constraints,
    build_ci,
    get_scoped_ci_or_404,
    apply_ci_update,
)
from app.services.service_desk.change_service import (  # noqa: E402
    serialize_change,
    list_changes_payload,
    get_change_payload,
    create_change_record,
    update_change_record,
    approve_change_record,
)
from app.services.service_desk.major_incident_service import (  # noqa: E402
    list_major_incidents_payload,
    declare_major_incident_record,
    update_major_incident_record,
    serialize_major_incident,
)
from app.services.service_desk.ticket_template_service import (  # noqa: E402
    list_ticket_templates_payload,
    create_ticket_template_record,
    update_ticket_template_record,
    delete_ticket_template,
)
from app.services.service_desk.canned_response_service import (  # noqa: E402
    serialize_canned_response_compact,
    list_canned_responses_payload,
    create_canned_response_record,
    update_canned_response_record,
    delete_canned_response,
)
from app.services.service_desk.known_error_service import (  # noqa: E402
    get_known_errors,
    serialize_known_error,
)
from app.services.service_desk.oncall_service import (  # noqa: E402
    list_oncall_schedules_payload,
    create_oncall_schedule_record,
    update_oncall_schedule_record,
    delete_oncall_schedule,
    create_oncall_entry_record,
    delete_oncall_entry,
    list_current_oncall_payload,
)
from app.services.service_desk.watcher_service import (  # noqa: E402
    list_ticket_watchers,
    serialize_ticket_watcher,
    watch_ticket_command,
    unwatch_ticket_command,
)
from app.services.service_desk.merge_split_service import (  # noqa: E402
    merge_ticket_command,
    split_ticket_command,
    list_ticket_merges_payload,
)
from app.services.service_desk.escalation_service import (  # noqa: E402
    list_escalation_rules_payload,
    create_escalation_rule_record,
    update_escalation_rule_record,
    delete_escalation_rule,
    run_escalation_rules_job,
    list_escalation_logs_payload,
)
from app.services.service_desk.sla_assignment_service import (  # noqa: E402
    assign_sla_policy_target,
    sla_policy_id_from_payload,
)
from app.services.service_desk.sla_policy_service import (  # noqa: E402
    list_sla_policies_payload,
    create_sla_policy_record,
    update_sla_policy_record,
    deactivate_sla_policy_record,
)
from app.services.service_desk.agent_group_service import (  # noqa: E402
    list_groups_payload,
    create_group_record,
    update_group_record,
    deactivate_group_record,
    add_group_member_record,
    remove_group_member_record,
)
from app.services.service_desk.holiday_service import (  # noqa: E402
    list_holidays_payload,
    create_holiday_record,
    delete_holiday,
)
from app.services.service_desk.workload_service import (  # noqa: E402
    get_group_workload_payload,
    auto_assign_ticket_command,
)
from app.services.service_desk.asset_service import (  # noqa: E402
    asset_out as _asset_out,
    list_assets_payload,
    asset_stats_payload,
    get_asset_detail_payload,
    create_asset_record,
    update_asset_record,
    retire_asset_record,
    assign_asset_record,
)
from app.services.service_desk.status_page_service import (  # noqa: E402
    build_public_status_page_payload,
    build_status_page_embed_script,
    list_status_components_payload,
    create_status_component_record,
    update_status_component_record,
    delete_status_component,
    create_status_incident_record,
    add_status_incident_update_record,
)
from app.services.service_desk.ai_suggest_service import (  # noqa: E402
    build_ai_ticket_suggestion,
)
from app.services.service_desk.inbound_email_service import (  # noqa: E402
    process_inbound_email,
)
from app.services.service_desk.link_service import (  # noqa: E402
    list_ticket_links_payload,
    create_ticket_link_record,
    delete_ticket_link,
)
from app.services.service_desk.routing_rule_service import (  # noqa: E402
    list_routing_rules as _list_routing_rules,
    serialize_routing_rule,
    build_routing_rule,
    get_routing_rule_or_404,
    apply_routing_rule_update,
    delete_routing_rule,
)
from app.services.service_desk.metrics_service import (  # noqa: E402
    priority_matrix_payload,
)
from app.services.service_desk.sla_event_service import (  # noqa: E402
    pause_ticket_sla_from_payload,
    resume_ticket_sla,
    list_sla_events,
)
from app.services.service_desk.analytics_service import (  # noqa: E402
    get_itil_metrics_payload,
    get_agent_performance_payload,
)
from app.services.service_desk.customer_context_service import (  # noqa: E402
    get_customer_context_payload,
)
from app.services.service_desk.semantic_feedback_service import (  # noqa: E402
    enqueue_profile_refresh,
    enqueue_reassign_feedback,
)
from app.services.service_desk.stats_service import (  # noqa: E402
    get_service_desk_stats,
)
from app.services.service_desk.cmdb_relation_service import (  # noqa: E402
    get_ci_relations_payload,
    build_ci_relation,
    get_ci_impact_payload,
)
from app.services.service_desk.catalog_service import (  # noqa: E402
    list_catalog_payload,
    create_category_record,
    update_category_record,
    deactivate_category_record,
    create_service_record,
    update_service_record,
    deactivate_service_record,
)
from app.services.service_desk.portal_auth_service import (  # noqa: E402
    require_portal_client,
)

# ── Service Catalog ───────────────────────────────────────────────────────────

@router.get("/catalog", summary="Catálogo de servicios")
def get_catalog(
    public_only: bool = False,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
):
    return list_catalog_payload(db, public_only)

@router.post("/catalog/categories", summary="Crear categoría")
def create_category(payload: ServiceCategoryIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    c = create_category_record(db, payload)
    _commit_or_rollback(db); db.refresh(c)
    return {"id": c.id, "name": c.name}

@router.patch("/catalog/categories/{cat_id}", summary="Actualizar categoría")
def update_category(cat_id: str, payload: ServiceCategoryIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    c = update_category_record(db, cat_id, payload)
    _commit_or_rollback(db); return {"id": c.id, "name": c.name}

@router.delete("/catalog/categories/{cat_id}", summary="Desactivar categoría")
def delete_category(cat_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    deactivate_category_record(db, cat_id)
    _commit_or_rollback(db); return {"ok": True}

@router.post("/catalog/services", summary="Crear servicio")
def create_service(payload: ServiceItemIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    s = create_service_record(db, payload)
    _commit_or_rollback(db); db.refresh(s)
    return {"id": s.id, "name": s.name}

@router.patch("/catalog/services/{service_id}", summary="Actualizar servicio")
def update_service(service_id: str, payload: ServiceItemUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    update_service_record(db, service_id, payload)
    _commit_or_rollback(db); return {"ok": True}

@router.delete("/catalog/services/{service_id}", summary="Desactivar servicio")
def delete_service(service_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    deactivate_service_record(db, service_id)
    _commit_or_rollback(db); return {"ok": True}


# ── SLA Policies ──────────────────────────────────────────────────────────────

@router.get("/sla-policies", summary="Políticas de SLA")
def get_sla_policies(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return list_sla_policies_payload(db)

@router.post("/sla-policies", summary="Crear política SLA")
def create_sla_policy(payload: SLAPolicyIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    p = create_sla_policy_record(db, payload)
    _commit_or_rollback(db); db.refresh(p)
    return {"id": p.id, "name": p.name}


# ── Agent Groups ──────────────────────────────────────────────────────────────

@router.get("/groups", summary="Grupos de agentes")
def get_groups(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return list_groups_payload(db)

@router.patch("/sla-policies/{policy_id}", summary="Actualizar política SLA")
def update_sla_policy(policy_id: str, payload: SLAPolicyIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    p = update_sla_policy_record(db, policy_id, payload)
    _commit_or_rollback(db); return {"id": p.id, "name": p.name}

@router.delete("/sla-policies/{policy_id}", summary="Eliminar política SLA")
def delete_sla_policy(policy_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    deactivate_sla_policy_record(db, policy_id)
    _commit_or_rollback(db); return {"ok": True}

@router.post("/groups", summary="Crear grupo")
def create_group(payload: AgentGroupIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    g = create_group_record(db, payload)
    _commit_or_rollback(db); db.refresh(g)
    return {"id": g.id, "name": g.name}

@router.patch("/groups/{group_id}", summary="Actualizar grupo")
def update_group(group_id: str, payload: AgentGroupIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    g = update_group_record(db, group_id, payload)
    _commit_or_rollback(db); return {"id": g.id, "name": g.name}

@router.delete("/groups/{group_id}", summary="Eliminar grupo")
def delete_group(group_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    deactivate_group_record(db, group_id)
    _commit_or_rollback(db); return {"ok": True}

@router.post("/groups/{group_id}/members/{user_id}", summary="Añadir miembro a grupo")
def add_group_member(group_id: str, user_id: str, is_lead: bool = False, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    add_group_member_record(db, group_id, user_id, is_lead)
    _commit_or_rollback(db)
    return {"ok": True}

@router.delete("/groups/{group_id}/members/{user_id}", summary="Eliminar miembro de grupo")
def remove_group_member(group_id: str, user_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    remove_group_member_record(db, group_id, user_id)
    _commit_or_rollback(db); return {"ok": True}


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
    return list_tickets_payload(
        db=db,
        current_user=current_user,
        ticket_out=_ticket_out,
        status=status,
        priority=priority,
        ticket_type=ticket_type,
        assigned_to=assigned_to,
        group_id=group_id,
        project_id=project_id,
        support_level=support_level,
        sla_breached=sla_breached,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.get("/tickets/my-queue", summary="Mi cola de trabajo")
def my_queue(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return my_queue_payload(db, current_user, _ticket_out)



@router.get("/tickets/client/my", summary="Mis tickets (cliente)")
def client_my_tickets(
    status: Optional[str] = None,
    authorization: Optional[str] = Header(None),
    portal_access_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
):
    client = require_portal_client(authorization, portal_access_token, db, detail="No autorizado")
    return client_my_tickets_payload(db, client.id, _ticket_out, status)


# ── Problem Management ────────────────────────────────────────────────────────


@router.get("/tickets/client/{ticket_id}", summary="Detalle de ticket (cliente portal)")
def get_ticket_client(
    ticket_id: str,
    authorization: Optional[str] = Header(None),
    portal_access_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
):
    """Endpoint para que el cliente del portal vea el detalle de uno de sus tickets."""
    client = require_portal_client(authorization, portal_access_token, db, detail="Autenticación requerida")
    return client_ticket_detail_payload(db, client.id, ticket_id, _ticket_out)



@router.get("/tickets/{ticket_id}", summary="Detalle de ticket")
def get_ticket(ticket_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return ticket_detail_payload(db, current_user, ticket_id, _ticket_out)


@router.post("/tickets", summary="Crear ticket (agente interno)")
def create_ticket(
    payload: TicketCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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
    ticket_id: str,
    payload: TicketUpdateIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = get_scoped_ticket_or_404(db, current_user, ticket_id)

    old_support_level = ticket.support_level  # Capturar ANTES del loop
    old_assigned_to   = ticket.assigned_to_user_id
    effects = apply_ticket_update(
        db=db,
        ticket=ticket,
        ticket_id=ticket_id,
        payload=payload,
        current_user_id=current_user.id,
        old_assigned_to=old_assigned_to,
        old_support_level=old_support_level,
    )

    _commit_or_rollback(db); db.refresh(ticket)

    # Background: refresh semantic profile when ticket is resolved
    if effects["refresh_profile"]:
        enqueue_profile_refresh(background_tasks, ticket.assigned_to_user_id)

    # Background: implicit feedback when ticket is reassigned
    if effects["reassigned"]:
        enqueue_reassign_feedback(background_tasks, ticket_id, "ticket")

    return _ticket_out(ticket)


@router.post("/tickets/{ticket_id}/comments", summary="Añadir comentario")
def add_comment(
    ticket_id: str,
    payload: CommentIn,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
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
    ticket_id: str,
    payload: CommentIn,
    authorization: Optional[str] = Header(None),
    portal_access_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
):
    client = require_portal_client(authorization, portal_access_token, db, detail="No autorizado")
    ticket = get_ticket_for_client_comment_or_404(db, ticket_id)
    comment = add_client_comment(db, ticket, ticket_id, payload.body, client.id)
    _commit_or_rollback(db)
    return {"id": comment.id, "created_at": str(comment.created_at)[:16]}


@router.post("/tickets/{ticket_id}/time-log", summary="Registrar tiempo")
def log_time(
    ticket_id: str,
    payload: TimeLogIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = get_scoped_ticket_for_ops_or_404(db, current_user, ticket_id)
    result = add_ticket_time(db, ticket, ticket_id, current_user.id, payload.minutes, payload.note)
    _commit_or_rollback(db)
    return result


@router.post("/tickets/{ticket_id}/escalate", summary="Escalar ticket")
def escalate_ticket(
    ticket_id: str,
    to_level: str = Query(...),
    reason: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = get_scoped_ticket_for_ops_or_404(db, current_user, ticket_id)
    result = escalate_ticket_level(db, ticket, ticket_id, to_level, reason, current_user.id)
    _commit_or_rollback(db)
    return result


@router.post("/tickets/{ticket_id}/csat", summary="Valoración de satisfacción")
def submit_csat(
    ticket_id: str,
    payload: CSATIn,
    authorization: Optional[str] = Header(None),
    portal_access_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
):
    client = require_portal_client(authorization, portal_access_token, db, detail="Autenticación requerida")
    result = submit_ticket_csat(db, ticket_id, payload.score, payload.comment)
    _commit_or_rollback(db)
    return result


# ── Client ticket views ───────────────────────────────────────────────────────

@router.get("/problems", summary="Listar problemas")
def list_problems(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return list_problems_payload(db, current_user, page, page_size)

@router.post("/problems", summary="Crear problema")
def create_problem(payload: ProblemIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    p = create_problem_record(db, current_user, payload)
    _commit_or_rollback(db); db.refresh(p)
    return {"id": p.id, "number": p.number}

@router.patch("/problems/{problem_id}", summary="Actualizar problema")
def update_problem(problem_id: str, payload: ProblemUpdateIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    p = get_scoped_problem_or_404(db, current_user, problem_id)
    apply_problem_update(db, current_user, p, payload)
    _commit_or_rollback(db); return {"ok": True}

@router.post("/problems/{problem_id}/link-ticket/{ticket_id}", summary="Vincular ticket a problema")
def link_ticket_to_problem(problem_id: str, ticket_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    link_ticket_to_problem_record(db, current_user, problem_id, ticket_id)
    _commit_or_rollback(db); return {"ok": True}


# ── Knowledge Base ────────────────────────────────────────────────────────────

@router.get("/kb", summary="Artículos de base de conocimiento")
def list_kb_articles(
    search: Optional[str] = None,
    category_id: Optional[str] = None,
    public_only: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    response: Response = None,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
):
    articles = list_kb_articles_scoped(
        db=db,
        search=search,
        category_id=category_id,
        public_only=public_only,
        page=page,
        page_size=page_size,
        response=response,
        authorization=authorization,
    )
    return serialize_kb_articles(articles, public_only)

@router.get("/kb/{article_id}", summary="Detalle de artículo KB")
def get_kb_article(article_id: str, db: Session = Depends(get_db)):
    a = get_kb_article_and_increment_view(db, article_id)
    _commit_or_rollback(db)
    return serialize_kb_article_detail(a)

@router.post("/kb", summary="Crear artículo KB")
def create_kb_article(payload: KBArticleIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    a = build_kb_article(db, payload, current_user.id)
    _commit_or_rollback(db); db.refresh(a)
    return {"id": a.id, "number": a.number}

@router.patch("/kb/{article_id}", summary="Actualizar artículo KB")
def update_kb_article(article_id: str, payload: KBArticleUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    a = get_scoped_kb_article_or_404(db, current_user, article_id)
    apply_kb_article_update(a, payload)
    _commit_or_rollback(db); return {"ok": True}

@router.delete("/kb/{article_id}", summary="Eliminar artículo KB")
def delete_kb_article(
    article_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    delete_kb_article(db, current_user, article_id)
    _commit_or_rollback(db)
    return {"ok": True}


@router.post("/kb/{article_id}/helpful", summary="Marcar artículo como útil")
def mark_helpful(article_id: str, helpful: bool = True, db: Session = Depends(get_db)):
    update_kb_helpful_vote(db, article_id, helpful)
    _commit_or_rollback(db); return {"ok": True}

@router.post("/tickets/{ticket_id}/to-kb", summary="Convertir resolución de ticket en artículo KB")
def ticket_to_kb(ticket_id: str, title: str = Query(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    a = create_kb_from_ticket(db, ticket_id, title, current_user.id)
    _commit_or_rollback(db)
    db.refresh(a)
    return {"id": a.id, "number": a.number}


# ── CMDB ──────────────────────────────────────────────────────────────────────

@router.get("/cmdb", summary="Inventario CMDB")
def list_cmdb(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = list_cmdb_items(db, current_user, page, page_size)
    return serialize_cmdb_items(items)

@router.post("/cmdb", summary="Crear CI")
def create_ci(payload: CIIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    enforce_ci_org_constraints(db, current_user, payload, is_update=False)
    ci = build_ci(db, payload)
    _commit_or_rollback(db); db.refresh(ci)
    return {"id": ci.id, "code": ci.code}

@router.patch("/cmdb/{ci_id}", summary="Actualizar CI")
def update_ci(ci_id: str, payload: CIIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    ci = get_scoped_ci_or_404(db, current_user, ci_id)
    enforce_ci_org_constraints(db, current_user, payload, is_update=True)
    apply_ci_update(ci, payload)
    _commit_or_rollback(db); return {"ok": True}


# ── Announcements ─────────────────────────────────────────────────────────────

@router.get("/announcements", summary="Anuncios activos")
def list_announcements(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    response: Response = None,
    db: Session = Depends(get_db),
):
    announcements = list_active_announcements(db, page, page_size, response)
    return serialize_announcements(announcements)

@router.post("/announcements", summary="Crear anuncio")
def create_announcement(payload: AnnouncementIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    a = build_announcement(db, payload, current_user.id)
    _commit_or_rollback(db); db.refresh(a)
    return {"id": a.id}

@router.delete("/announcements/{ann_id}", summary="Desactivar anuncio")
def deactivate_announcement(ann_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    deactivate_announcement_record(db, ann_id)
    _commit_or_rollback(db); return {"ok": True}


# ── Analytics / Dashboard ─────────────────────────────────────────────────────

@router.get("/stats", summary="Estadísticas del service desk")
def get_stats(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_service_desk_stats(db, current_user, days)

# ════════════════════════════════════════════════════════════════════════════
# AMPLIACIÓN ITIL/ITSM v2
# ════════════════════════════════════════════════════════════════════════════
from app.models.service_desk import (
    TicketLink,
)


# ── Routing Rules CRUD ────────────────────────────────────────────────────────

@router.get("/routing-rules", summary="Listar reglas de routing automático")
def list_routing_rules(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rules = _list_routing_rules(db)
    return [serialize_routing_rule(r) for r in rules]


@router.post("/routing-rules", summary="Crear regla de routing")
def create_routing_rule(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    rule = build_routing_rule(db, payload)
    _commit_or_rollback(db); db.refresh(rule)
    return {"id": rule.id, "name": rule.name}


@router.patch("/routing-rules/{rule_id}", summary="Actualizar regla de routing")
def update_routing_rule(
    rule_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    rule = get_routing_rule_or_404(db, rule_id)
    apply_routing_rule_update(rule, payload)
    _commit_or_rollback(db)
    return {"ok": True}


@router.delete("/routing-rules/{rule_id}", summary="Eliminar regla de routing")
def delete_routing_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    delete_routing_rule(db, rule_id)
    _commit_or_rollback(db)
    return {"ok": True}


# ── Priority Matrix ───────────────────────────────────────────────────────────

@router.post("/priority-matrix", summary="Calcular prioridad ITIL por urgencia × impacto")
def calculate_priority(
    payload: dict = Body(...),
    current_user: User = Depends(get_current_user),
):
    return priority_matrix_payload(payload)


# ── Linked Tickets ────────────────────────────────────────────────────────────

@router.get("/tickets/{ticket_id}/links", summary="Ver tickets vinculados")
def get_ticket_links(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return list_ticket_links_payload(db, ticket_id)


@router.post("/tickets/{ticket_id}/links", summary="Vincular tickets")
def link_tickets(
    ticket_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lk = create_ticket_link_record(db, ticket_id, payload, current_user.id)
    _commit_or_rollback(db)
    return {"ok": True, "link_id": lk.id}


@router.delete("/tickets/{ticket_id}/links/{link_id}", summary="Eliminar vínculo")
def delete_ticket_link(
    ticket_id: str, link_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    delete_ticket_link(db, link_id)
    _commit_or_rollback(db)
    return {"ok": True}


# ── SLA — Pause / Resume / Events ────────────────────────────────────────────

@router.post("/tickets/{ticket_id}/sla/pause", summary="Pausar SLA (esperando cliente/OOH)")
def pause_sla(
    ticket_id: str,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = pause_ticket_sla_from_payload(db, ticket_id, current_user.id, payload)
    _commit_or_rollback(db)
    return result


@router.post("/tickets/{ticket_id}/sla/resume", summary="Reanudar SLA")
def resume_sla(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = resume_ticket_sla(db, ticket_id, current_user.id)
    _commit_or_rollback(db)
    return result


@router.get("/tickets/{ticket_id}/sla/events", summary="Historial de eventos SLA")
def get_sla_events(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return list_sla_events(db, ticket_id)


# ── ITIL Metrics ─────────────────────────────────────────────────────────────

@router.get("/metrics/itil", summary="Métricas ITIL: MTTR, FCR, SLA compliance, volumen")
def get_itil_metrics(
    date_from: Optional[str] = Query(None),
    date_to:   Optional[str] = Query(None),
    client_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_itil_metrics_payload(db, date_from, date_to, client_id)


@router.get("/metrics/agent-performance", summary="Rendimiento por agente")
def get_agent_performance(
    date_from: Optional[str] = Query(None),
    date_to:   Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_agent_performance_payload(db, date_from, date_to)


# ── CMDB — Relaciones entre CIs ───────────────────────────────────────────────

@router.get("/cmdb/{ci_id}/relations", summary="Relaciones del CI (impacto)")
def get_ci_relations(
    ci_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_ci_relations_payload(db, current_user, ci_id)


@router.post("/cmdb/relations", summary="Crear relación entre CIs")
def create_ci_relation(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    rel = build_ci_relation(db, current_user, payload)
    _commit_or_rollback(db)
    return {"id": rel.id, "ok": True}


@router.get("/cmdb/{ci_id}/impact", summary="Análisis de impacto — CIs afectados si este falla")
def get_ci_impact(
    ci_id: str,
    max_depth: int = Query(5, ge=1, le=10, description="Maximum BFS hops from the root CI"),
    limit: int = Query(500, ge=1, le=2000, description="Maximum number of impacted CIs to return"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_ci_impact_payload(db, current_user, ci_id, max_depth=max_depth, limit=limit)


# ── Change Management ITSM ────────────────────────────────────────────────────

@router.get("/changes", summary="Listar Change Requests ITSM")
def list_changes(
    status:     Optional[str] = Query(None),
    change_type: Optional[str] = Query(None),
    date_from:  Optional[str] = Query(None),
    date_to:    Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return list_changes_payload(db, current_user, status, change_type, date_from, date_to, page, page_size)


@router.get("/changes/{change_id}", summary="Detalle de Change Request")
def get_change(
    change_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_change_payload(db, current_user, change_id, full=True)


@router.post("/changes", summary="Crear Change Request ITSM")
def create_change(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cr = create_change_record(db, current_user, payload)
    _commit_or_rollback(db); db.refresh(cr)
    return serialize_change(cr)


@router.patch("/changes/{change_id}", summary="Actualizar Change Request")
def update_change(
    change_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cr = update_change_record(db, current_user, change_id, payload)

    _commit_or_rollback(db)
    return serialize_change(cr)


@router.post("/changes/{change_id}/approve", summary="Aprobar Change Request (CAB)")
def approve_change(
    change_id: str,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cr = approve_change_record(db, current_user, change_id, payload)

    _commit_or_rollback(db)
    return {"ok": True, "status": cr.status.value}


# ── Major Incidents ───────────────────────────────────────────────────────────

@router.get("/major-incidents", summary="Listar incidentes mayores")
def list_major_incidents(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return list_major_incidents_payload(db, status)


@router.post("/major-incidents", summary="Declarar incidente mayor (P1/P2)")
def declare_major_incident(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    mi = declare_major_incident_record(db, payload, current_user.id)
    _commit_or_rollback(db)
    db.refresh(mi)
    return serialize_major_incident(mi)


@router.patch("/major-incidents/{mi_id}", summary="Actualizar incidente mayor")
def update_major_incident(
    mi_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    mi = update_major_incident_record(db, mi_id, payload)

    _commit_or_rollback(db)
    return serialize_major_incident(mi)


# ── Ticket Templates ──────────────────────────────────────────────────────────

@router.get("/ticket-templates", summary="Plantillas de tickets por tipo/servicio")
def list_ticket_templates(
    ticket_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return list_ticket_templates_payload(db, ticket_type)


@router.post("/ticket-templates", summary="Crear plantilla de ticket")
def create_ticket_template(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    tmpl = create_ticket_template_record(db, payload)
    _commit_or_rollback(db); db.refresh(tmpl)
    return {"id": tmpl.id, "name": tmpl.name}


@router.patch("/ticket-templates/{template_id}", summary="Actualizar plantilla")
def update_ticket_template(
    template_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    update_ticket_template_record(db, template_id, payload)
    _commit_or_rollback(db)
    return {"ok": True}


# ── Known Errors (KEDB) ───────────────────────────────────────────────────────

@router.get("/known-errors", summary="Base de errores conocidos (KEDB)")
def list_known_errors(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Problemas en estado known_error con workaround documentado."""
    problems = get_known_errors(db)
    return [serialize_known_error(p) for p in problems]


# ── Agent Workspace — vista 360 del solicitante ───────────────────────────────

@router.delete("/ticket-templates/{template_id}", summary="Eliminar plantilla")
def delete_ticket_template(template_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    delete_ticket_template(db, template_id)
    _commit_or_rollback(db); return {"ok": True}

@router.get("/agent/customer-context/{requester_id}", summary="Contexto 360 del solicitante")
def get_customer_context(
    requester_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Vista unificada del historial del cliente para el agente."""
    return get_customer_context_payload(db, requester_id)

# ── Canned Responses (respuestas rápidas) ─────────────────────────────────────


@router.get("/canned-responses", summary="Listar respuestas rápidas")
def list_canned_responses(
    category: Optional[str] = None,
    search:   Optional[str] = None,
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    return list_canned_responses_payload(db, category, search)


@router.post("/canned-responses", summary="Crear respuesta rápida", status_code=201)
def create_canned_response(
    payload: CannedResponseIn,
    db: Session = Depends(get_db),
    cu: User = Depends(require_any_manager),
):
    c = create_canned_response_record(db, payload, cu.id)
    _commit_or_rollback(db); db.refresh(c)
    return serialize_canned_response_compact(c)


@router.patch("/canned-responses/{canned_id}", summary="Editar respuesta rápida")
def update_canned_response(
    canned_id: str,
    payload: CannedResponseIn,
    db: Session = Depends(get_db),
    cu: User = Depends(require_any_manager),
):
    c = update_canned_response_record(db, canned_id, payload)
    _commit_or_rollback(db); db.refresh(c)
    return serialize_canned_response_compact(c)


@router.delete("/canned-responses/{canned_id}", summary="Eliminar respuesta rápida")
def delete_canned_response(
    canned_id: str,
    db: Session = Depends(get_db),
    cu: User = Depends(require_any_manager),
):
    delete_canned_response(db, canned_id)
    _commit_or_rollback(db)
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
    ticket, req_email = process_inbound_email(db, payload, x_clarive_email_secret)
    _commit_or_rollback(db)
    db.refresh(ticket)

    logger.info("Email-to-ticket: %s from %r - %r", ticket.number, req_email, ticket.title)

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
    return list_oncall_schedules_payload(db, group_id)


@router.post("/oncall/schedules", summary="Crear schedule de guardia", status_code=201)
def create_oncall_schedule(
    payload: OnCallScheduleIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    s = create_oncall_schedule_record(db, payload)
    _commit_or_rollback(db); db.refresh(s)
    return {"id": s.id, "name": s.name}


@router.patch("/oncall/schedules/{schedule_id}", summary="Actualizar schedule")
def update_oncall_schedule(
    schedule_id: str,
    payload: OnCallScheduleIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    update_oncall_schedule_record(db, schedule_id, payload)
    _commit_or_rollback(db)
    return {"ok": True}


@router.delete("/oncall/schedules/{schedule_id}", summary="Eliminar schedule")
def delete_oncall_schedule(
    schedule_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    delete_oncall_schedule(db, schedule_id)
    _commit_or_rollback(db)
    return {"ok": True}


@router.post("/oncall/schedules/{schedule_id}/entries", summary="Añadir turno de guardia", status_code=201)
def add_oncall_entry(
    schedule_id: str,
    payload: OnCallEntryIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    entry = create_oncall_entry_record(db, schedule_id, payload)
    _commit_or_rollback(db)
    return {"id": entry.id}


@router.delete("/oncall/entries/{entry_id}", summary="Eliminar turno de guardia")
def delete_oncall_entry(
    entry_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    delete_oncall_entry(db, entry_id)
    _commit_or_rollback(db)
    return {"ok": True}


@router.get("/oncall/current", summary="¿Quién está de guardia ahora?")
def get_current_oncall(
    group_id: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Devuelve el agente de guardia en este momento para cada schedule activo."""
    return list_current_oncall_payload(db, group_id)


# ═══════════════════════════════════════════════════════════════════════════════
# TICKET WATCHERS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/tickets/{ticket_id}/watchers", summary="Ver seguidores del ticket")
def get_watchers(
    ticket_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    watchers = list_ticket_watchers(db, ticket_id)
    return [serialize_ticket_watcher(w) for w in watchers]


@router.post("/tickets/{ticket_id}/watch", summary="Seguir ticket (watch)", status_code=201)
def watch_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = watch_ticket_command(db, ticket_id, current_user.id)
    _commit_or_rollback(db)
    return result


@router.delete("/tickets/{ticket_id}/watch", summary="Dejar de seguir ticket (unwatch)")
def unwatch_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = unwatch_ticket_command(db, ticket_id, current_user.id)
    _commit_or_rollback(db)
    return result


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
    result = merge_ticket_command(
        db, ticket_id, payload.merged_ticket_id, payload.reason, current_user.id
    )
    _commit_or_rollback(db)
    return result


@router.post("/tickets/{ticket_id}/split", summary="Dividir ticket en ticket hijo")
def split_ticket(
    ticket_id: str,
    payload: SplitTicketIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    result = split_ticket_command(
        db=db,
        ticket_id=ticket_id,
        payload=payload,
        current_user_id=current_user.id,
    )
    _commit_or_rollback(db)
    db.refresh(result["child"])
    return {"ok": True, "parent": result["parent"].number, "child": result["child"].number, "child_id": result["child"].id}


@router.post("/tickets/{ticket_id}/ai-suggest", summary="Sugerir respuesta IA para ticket")
def suggest_ticket_response_ai(
    ticket_id: str,
    payload: Optional[dict] = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return build_ai_ticket_suggestion(db, ticket_id, payload, current_user)


@router.patch("/sla-policies/assign/client/{client_id}", summary="Asignar política SLA a cliente")
def assign_sla_to_client(
    client_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    sla_policy_id = sla_policy_id_from_payload(payload)
    result = assign_sla_policy_target(db, "client", client_id, sla_policy_id)
    _commit_or_rollback(db)
    return result


@router.patch("/sla-policies/assign/contract/{contract_id}", summary="Asignar política SLA a contrato")
def assign_sla_to_contract(
    contract_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    sla_policy_id = sla_policy_id_from_payload(payload)
    result = assign_sla_policy_target(db, "contract", contract_id, sla_policy_id)
    _commit_or_rollback(db)
    return result


@router.get("/tickets/{ticket_id}/merges", summary="Ver merges de un ticket")
def get_merges(
    ticket_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return list_ticket_merges_payload(db, ticket_id)


# ═══════════════════════════════════════════════════════════════════════════════
# AUTO-ESCALATION RULES
# ═══════════════════════════════════════════════════════════════════════════════




@router.get("/escalation-rules", summary="Listar reglas de escalada automática")
def list_escalation_rules(
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    return list_escalation_rules_payload(db)


@router.post("/escalation-rules", summary="Crear regla de escalada", status_code=201)
def create_escalation_rule(
    payload: EscalationRuleIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    rule = create_escalation_rule_record(db, payload)
    _commit_or_rollback(db); db.refresh(rule)
    return {"ok": True, "id": rule.id}


@router.patch("/escalation-rules/{rule_id}", summary="Actualizar regla de escalada")
def update_escalation_rule(
    rule_id: str,
    payload: EscalationRuleIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    update_escalation_rule_record(db, rule_id, payload)
    _commit_or_rollback(db)
    return {"ok": True}


@router.delete("/escalation-rules/{rule_id}", summary="Eliminar regla de escalada")
def delete_escalation_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    delete_escalation_rule(db, rule_id)
    _commit_or_rollback(db)
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
    result = run_escalation_rules_job(db)
    _commit_or_rollback(db)
    return result


@router.get("/escalation-rules/logs", summary="Historial de escaladas disparadas")
def get_escalation_logs(
    ticket_id: Optional[str] = None,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    return list_escalation_logs_payload(db, ticket_id, limit)


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
    return list_holidays_payload(db, year, country)


@router.post("/sla-holidays", summary="Añadir festivo al calendario SLA", status_code=201)
def create_holiday(
    payload: HolidayIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    h = create_holiday_record(db, payload)
    _commit_or_rollback(db)
    return {"id": h.id}


@router.delete("/sla-holidays/{holiday_id}", summary="Eliminar festivo")
def delete_holiday(
    holiday_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    delete_holiday(db, holiday_id)
    _commit_or_rollback(db)
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
    return get_group_workload_payload(db, group_id)


@router.post("/tickets/{ticket_id}/auto-assign", summary="Auto-asignar ticket al agente con menos carga del grupo")
def auto_assign_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    result = auto_assign_ticket_command(db, ticket_id, current_user.id)
    _commit_or_rollback(db)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# ASSET MANAGEMENT (HAM / SAM)
# ═══════════════════════════════════════════════════════════════════════════════



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
    return list_assets_payload(db, asset_type, status, assigned_user_id, search, page, page_size)


@router.get("/assets/stats", summary="Estadísticas del inventario de activos")
def asset_stats(
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    return asset_stats_payload(db)


@router.get("/assets/{asset_id}", summary="Detalle de activo")
def get_asset(
    asset_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return get_asset_detail_payload(db, asset_id)


@router.post("/assets", summary="Crear activo IT", status_code=201)
def create_asset(
    payload: AssetIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    asset = create_asset_record(db, payload)
    _commit_or_rollback(db); db.refresh(asset)
    return _asset_out(asset)


@router.patch("/assets/{asset_id}", summary="Actualizar activo")
def update_asset(
    asset_id: str,
    payload: AssetUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    a = update_asset_record(db, asset_id, payload, current_user.id)

    _commit_or_rollback(db); db.refresh(a)
    return _asset_out(a)


@router.delete("/assets/{asset_id}", summary="Dar de baja activo (retired)")
def retire_asset(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    retire_asset_record(db, asset_id, current_user.id)
    _commit_or_rollback(db)
    return {"ok": True}


@router.post("/assets/{asset_id}/assign", summary="Asignar activo a usuario")
def assign_asset(
    asset_id: str,
    user_id: str = Body(..., embed=True),
    notes: Optional[str] = Body(None, embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    user_name = assign_asset_record(db, asset_id, user_id, current_user.id, notes)
    _commit_or_rollback(db)
    return {"ok": True, "assigned_to": user_name}


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE STATUS PAGE
# ═══════════════════════════════════════════════════════════════════════════════




@router.get("/status-page", summary="Estado público del servicio (status page)")
def get_status_page(
    db: Session = Depends(get_db),
):
    """Endpoint público — no requiere autenticación."""
    return build_public_status_page_payload(db)

@router.get("/status-page/embed.js", summary="Snippet JS embebible de status page", response_class=PlainTextResponse)
def status_page_embed_js():
    """Returns a lightweight embeddable script for third-party websites."""
    return build_status_page_embed_script()


@router.get("/status-page/components", summary="Listar componentes del status page (admin)")
def list_status_components(
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    return list_status_components_payload(db)


@router.post("/status-page/components", summary="Crear componente del status page", status_code=201)
def create_status_component(
    payload: StatusComponentIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    c = create_status_component_record(db, payload)
    _commit_or_rollback(db); db.refresh(c)
    return {"id": c.id, "name": c.name}


@router.patch("/status-page/components/{component_id}", summary="Actualizar estado de componente")
def update_status_component(
    component_id: str,
    payload: StatusComponentIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    update_status_component_record(db, component_id, payload)
    _commit_or_rollback(db)
    return {"ok": True}


@router.delete("/status-page/components/{component_id}", summary="Eliminar componente")
def delete_status_component(
    component_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    delete_status_component(db, component_id)
    _commit_or_rollback(db)
    return {"ok": True}


@router.post("/status-page/components/{component_id}/incidents", summary="Declarar incidente en status page", status_code=201)
def declare_status_incident(
    component_id: str,
    payload: StatusIncidentIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    inc = create_status_incident_record(db, component_id, payload)
    _commit_or_rollback(db); db.refresh(inc)
    return {"id": inc.id}


@router.post("/status-page/incidents/{incident_id}/updates", summary="Añadir actualización a incidente de status page")
def add_status_incident_update(
    incident_id: str,
    payload: StatusIncidentUpdateIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    updates_count = add_status_incident_update_record(db, incident_id, payload)

    _commit_or_rollback(db)
    return {"ok": True, "updates_count": updates_count}


