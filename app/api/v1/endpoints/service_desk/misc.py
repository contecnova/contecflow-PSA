"""Service Desk — Miscellaneous subdomain router (catalog, groups, problems, announcements, routing, changes, major incidents, assets, status page)."""
from fastapi import APIRouter, Depends, Query, Header, Body, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager, require_admin
from app.models.user import User
from app.services.service_desk.ticket_ops_service import commit_or_rollback as _commit_or_rollback
from app.schemas.service_desk import (
    ProblemIn, ProblemUpdateIn, ServiceCategoryIn, ServiceItemIn, ServiceItemUpdate,
    AgentGroupIn, AnnouncementIn, AssetIn, AssetUpdate,
    StatusComponentIn, StatusIncidentIn, StatusIncidentUpdateIn,
)
from app.services.service_desk.problem_service import (
    list_problems_payload, create_problem_record, get_scoped_problem_or_404,
    apply_problem_update, link_ticket_to_problem_record,
)
from app.services.service_desk.catalog_service import (
    list_catalog_payload, create_category_record, update_category_record, deactivate_category_record,
    create_service_record, update_service_record, deactivate_service_record,
)
from app.services.service_desk.agent_group_service import (
    list_groups_payload, create_group_record, update_group_record, deactivate_group_record,
    add_group_member_record, remove_group_member_record,
)
from app.services.service_desk.workload_service import get_group_workload_payload
from app.services.service_desk.announcement_service import (
    list_active_announcements, serialize_announcements, build_announcement, deactivate_announcement_record,
)
from app.services.service_desk.routing_rule_service import (
    list_routing_rules as _list_routing_rules, serialize_routing_rule,
    build_routing_rule, get_routing_rule_or_404, apply_routing_rule_update,
    delete_routing_rule as delete_routing_rule_svc,
)
from app.services.service_desk.change_service import (
    serialize_change, list_changes_payload, get_change_payload,
    create_change_record, update_change_record, approve_change_record,
)
from app.services.service_desk.major_incident_service import (
    list_major_incidents_payload, declare_major_incident_record,
    update_major_incident_record, serialize_major_incident,
)
from app.services.service_desk.asset_service import (
    asset_out as _asset_out, list_assets_payload, asset_stats_payload,
    get_asset_detail_payload, create_asset_record, update_asset_record,
    retire_asset_record, assign_asset_record,
)
from app.services.service_desk.status_page_service import (
    build_public_status_page_payload, build_status_page_embed_script,
    list_status_components_payload, create_status_component_record,
    update_status_component_record, delete_status_component as delete_status_component_svc,
    create_status_incident_record, add_status_incident_update_record,
)

router = APIRouter()

# ── Service Catalog ───────────────────────────────────────────────────────────

@router.get("/catalog", summary="Catálogo de servicios")
def get_catalog(public_only: bool = False, db: Session = Depends(get_db), authorization: Optional[str] = Header(None)):
    return list_catalog_payload(db, public_only)

@router.post("/catalog/categories", summary="Crear categoría")
def create_category(payload: ServiceCategoryIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    c = create_category_record(db, payload)
    _commit_or_rollback(db); db.refresh(c)
    return {"id": c.id, "name": c.name}

@router.patch("/catalog/categories/{cat_id}", summary="Actualizar categoría")
def update_category(cat_id: str, payload: ServiceCategoryIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    c = update_category_record(db, cat_id, payload)
    _commit_or_rollback(db)
    return {"id": c.id, "name": c.name}

@router.delete("/catalog/categories/{cat_id}", summary="Desactivar categoría")
def delete_category(cat_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    deactivate_category_record(db, cat_id)
    _commit_or_rollback(db)
    return {"ok": True}

@router.post("/catalog/services", summary="Crear servicio")
def create_service(payload: ServiceItemIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    s = create_service_record(db, payload)
    _commit_or_rollback(db); db.refresh(s)
    return {"id": s.id, "name": s.name}

@router.patch("/catalog/services/{service_id}", summary="Actualizar servicio")
def update_service(service_id: str, payload: ServiceItemUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    update_service_record(db, service_id, payload)
    _commit_or_rollback(db)
    return {"ok": True}

@router.delete("/catalog/services/{service_id}", summary="Desactivar servicio")
def delete_service(service_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    deactivate_service_record(db, service_id)
    _commit_or_rollback(db)
    return {"ok": True}

# ── Agent Groups ──────────────────────────────────────────────────────────────

@router.get("/groups", summary="Grupos de agentes")
def get_groups(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return list_groups_payload(db)

@router.post("/groups", summary="Crear grupo")
def create_group(payload: AgentGroupIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    g = create_group_record(db, payload)
    _commit_or_rollback(db); db.refresh(g)
    return {"id": g.id, "name": g.name}

@router.patch("/groups/{group_id}", summary="Actualizar grupo")
def update_group(group_id: str, payload: AgentGroupIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    g = update_group_record(db, group_id, payload)
    _commit_or_rollback(db)
    return {"id": g.id, "name": g.name}

@router.delete("/groups/{group_id}", summary="Eliminar grupo")
def delete_group(group_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    deactivate_group_record(db, group_id)
    _commit_or_rollback(db)
    return {"ok": True}

@router.post("/groups/{group_id}/members/{user_id}", summary="Añadir miembro a grupo")
def add_group_member(group_id: str, user_id: str, is_lead: bool = False, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    add_group_member_record(db, group_id, user_id, is_lead)
    _commit_or_rollback(db)
    return {"ok": True}

@router.delete("/groups/{group_id}/members/{user_id}", summary="Eliminar miembro de grupo")
def remove_group_member(group_id: str, user_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    remove_group_member_record(db, group_id, user_id)
    _commit_or_rollback(db)
    return {"ok": True}

@router.get("/groups/{group_id}/workload", summary="Distribución de carga de tickets por agente en el grupo")
def get_group_workload(group_id: str, db: Session = Depends(get_db), _: User = Depends(require_any_manager)):
    return get_group_workload_payload(db, group_id)

# ── Problems ──────────────────────────────────────────────────────────────────

@router.get("/problems", summary="Listar problemas")
def list_problems(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
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
    _commit_or_rollback(db)
    return {"ok": True}

@router.post("/problems/{problem_id}/link-ticket/{ticket_id}", summary="Vincular ticket a problema")
def link_ticket_to_problem(problem_id: str, ticket_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    link_ticket_to_problem_record(db, current_user, problem_id, ticket_id)
    _commit_or_rollback(db)
    return {"ok": True}

# ── Announcements ─────────────────────────────────────────────────────────────

@router.get("/announcements", summary="Anuncios activos")
def list_announcements(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), response: Response = None, db: Session = Depends(get_db)):
    return serialize_announcements(list_active_announcements(db, page, page_size, response))

@router.post("/announcements", summary="Crear anuncio")
def create_announcement(payload: AnnouncementIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    a = build_announcement(db, payload, current_user.id)
    _commit_or_rollback(db); db.refresh(a)
    return {"id": a.id}

@router.delete("/announcements/{ann_id}", summary="Desactivar anuncio")
def deactivate_announcement(ann_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    deactivate_announcement_record(db, ann_id)
    _commit_or_rollback(db)
    return {"ok": True}

# ── Routing Rules ─────────────────────────────────────────────────────────────

@router.get("/routing-rules", summary="Listar reglas de routing automático")
def list_routing_rules(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return [serialize_routing_rule(r) for r in _list_routing_rules(db)]

@router.post("/routing-rules", summary="Crear regla de routing")
def create_routing_rule(payload: dict = Body(...), db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    rule = build_routing_rule(db, payload)
    _commit_or_rollback(db); db.refresh(rule)
    return {"id": rule.id, "name": rule.name}

@router.patch("/routing-rules/{rule_id}", summary="Actualizar regla de routing")
def update_routing_rule(rule_id: str, payload: dict = Body(...), db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    rule = get_routing_rule_or_404(db, rule_id)
    apply_routing_rule_update(rule, payload)
    _commit_or_rollback(db)
    return {"ok": True}

@router.delete("/routing-rules/{rule_id}", summary="Eliminar regla de routing")
def delete_routing_rule(rule_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    delete_routing_rule_svc(db, rule_id)
    _commit_or_rollback(db)
    return {"ok": True}

# ── Change Management ─────────────────────────────────────────────────────────

@router.get("/changes", summary="Listar Change Requests ITSM")
def list_changes(
    status: Optional[str] = Query(None), change_type: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None), date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    return list_changes_payload(db, current_user, status, change_type, date_from, date_to, page, page_size)

@router.get("/changes/{change_id}", summary="Detalle de Change Request")
def get_change(change_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return get_change_payload(db, current_user, change_id, full=True)

@router.post("/changes", summary="Crear Change Request ITSM")
def create_change(payload: dict = Body(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    cr = create_change_record(db, current_user, payload)
    _commit_or_rollback(db); db.refresh(cr)
    return serialize_change(cr)

@router.patch("/changes/{change_id}", summary="Actualizar Change Request")
def update_change(change_id: str, payload: dict = Body(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    cr = update_change_record(db, current_user, change_id, payload)
    _commit_or_rollback(db)
    return serialize_change(cr)

@router.post("/changes/{change_id}/approve", summary="Aprobar Change Request (CAB)")
def approve_change(change_id: str, payload: dict = Body(default={}), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    cr = approve_change_record(db, current_user, change_id, payload)
    _commit_or_rollback(db)
    return {"ok": True, "status": cr.status.value}

# ── Major Incidents ───────────────────────────────────────────────────────────

@router.get("/major-incidents", summary="Listar incidentes mayores")
def list_major_incidents(status: Optional[str] = Query(None), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return list_major_incidents_payload(db, status)

@router.post("/major-incidents", summary="Declarar incidente mayor (P1/P2)")
def declare_major_incident(payload: dict = Body(...), db: Session = Depends(get_db), current_user: User = Depends(require_any_manager)):
    mi = declare_major_incident_record(db, payload, current_user.id)
    _commit_or_rollback(db); db.refresh(mi)
    return serialize_major_incident(mi)

@router.patch("/major-incidents/{mi_id}", summary="Actualizar incidente mayor")
def update_major_incident(mi_id: str, payload: dict = Body(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    mi = update_major_incident_record(db, mi_id, payload)
    _commit_or_rollback(db)
    return serialize_major_incident(mi)

# ── Assets ────────────────────────────────────────────────────────────────────

@router.get("/assets", summary="Listar activos IT (HAM/SAM)")
def list_assets(
    asset_type: Optional[str] = None, status: Optional[str] = None,
    assigned_user_id: Optional[str] = None, search: Optional[str] = None,
    page: int = Query(1, ge=1), page_size: int = Query(50, le=200),
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
):
    return list_assets_payload(db, asset_type, status, assigned_user_id, search, page, page_size)

@router.get("/assets/stats", summary="Estadísticas del inventario de activos")
def asset_stats(db: Session = Depends(get_db), _: User = Depends(require_any_manager)):
    return asset_stats_payload(db)

@router.get("/assets/{asset_id}", summary="Detalle de activo")
def get_asset(asset_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return get_asset_detail_payload(db, asset_id)

@router.post("/assets", summary="Crear activo IT", status_code=201)
def create_asset(payload: AssetIn, db: Session = Depends(get_db), current_user: User = Depends(require_any_manager)):
    asset = create_asset_record(db, payload)
    _commit_or_rollback(db); db.refresh(asset)
    return _asset_out(asset)

@router.patch("/assets/{asset_id}", summary="Actualizar activo")
def update_asset(asset_id: str, payload: AssetUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_any_manager)):
    a = update_asset_record(db, asset_id, payload, current_user.id)
    _commit_or_rollback(db); db.refresh(a)
    return _asset_out(a)

@router.delete("/assets/{asset_id}", summary="Dar de baja activo (retired)")
def retire_asset(asset_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_any_manager)):
    retire_asset_record(db, asset_id, current_user.id)
    _commit_or_rollback(db)
    return {"ok": True}

@router.post("/assets/{asset_id}/assign", summary="Asignar activo a usuario")
def assign_asset(asset_id: str, user_id: str = Body(..., embed=True), notes: Optional[str] = Body(None, embed=True), db: Session = Depends(get_db), current_user: User = Depends(require_any_manager)):
    user_name = assign_asset_record(db, asset_id, user_id, current_user.id, notes)
    _commit_or_rollback(db)
    return {"ok": True, "assigned_to": user_name}

# ── Status Page ───────────────────────────────────────────────────────────────

@router.get("/status-page", summary="Estado público del servicio (status page)")
def get_status_page(db: Session = Depends(get_db)):
    return build_public_status_page_payload(db)

@router.get("/status-page/embed.js", summary="Snippet JS embebible de status page", response_class=PlainTextResponse)
def status_page_embed_js():
    return build_status_page_embed_script()

@router.get("/status-page/components", summary="Listar componentes del status page (admin)")
def list_status_components(db: Session = Depends(get_db), _: User = Depends(require_any_manager)):
    return list_status_components_payload(db)

@router.post("/status-page/components", summary="Crear componente del status page", status_code=201)
def create_status_component(payload: StatusComponentIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    c = create_status_component_record(db, payload)
    _commit_or_rollback(db); db.refresh(c)
    return {"id": c.id, "name": c.name}

@router.patch("/status-page/components/{component_id}", summary="Actualizar estado de componente")
def update_status_component(component_id: str, payload: StatusComponentIn, db: Session = Depends(get_db), _: User = Depends(require_any_manager)):
    update_status_component_record(db, component_id, payload)
    _commit_or_rollback(db)
    return {"ok": True}

@router.delete("/status-page/components/{component_id}", summary="Eliminar componente")
def delete_status_component(component_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    delete_status_component_svc(db, component_id)
    _commit_or_rollback(db)
    return {"ok": True}

@router.post("/status-page/components/{component_id}/incidents", summary="Declarar incidente en status page", status_code=201)
def declare_status_incident(component_id: str, payload: StatusIncidentIn, db: Session = Depends(get_db), _: User = Depends(require_any_manager)):
    inc = create_status_incident_record(db, component_id, payload)
    _commit_or_rollback(db); db.refresh(inc)
    return {"id": inc.id}

@router.post("/status-page/incidents/{incident_id}/updates", summary="Añadir actualización a incidente de status page")
def add_status_incident_update(incident_id: str, payload: StatusIncidentUpdateIn, db: Session = Depends(get_db), _: User = Depends(require_any_manager)):
    updates_count = add_status_incident_update_record(db, incident_id, payload)
    _commit_or_rollback(db)
    return {"ok": True, "updates_count": updates_count}
