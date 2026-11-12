"""Service Desk — Miscellaneous subdomain router (catalog, groups, problems, announcements, routing, changes, major incidents, assets, status page)."""
from fastapi import APIRouter, Depends, Query, Body, Response, HTTPException, Request
from app.services.service_desk.portal_auth_service import Lector, get_portal_client_or_user
from sqlalchemy.orm import Session
from typing import Optional
import json
import logging

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin, require_any_manager
from app.core.abac_enforce import enforce_abac
from app.core.responses import APIListResponse, APIResponse
from app.core.ratelimit import limiter
from app.models.user import User
from app.services.service_desk.ticket_ops_service import commit_or_rollback as _commit_or_rollback
from app.schemas.service_desk import (
    ProblemUpdateIn, ServiceCategoryIn, ServiceItemIn, ServiceItemUpdate, AgentGroupIn,
    AnnouncementIn, StatusComponentIn, StatusIncidentIn,
    StatusIncidentUpdateIn,
)
from app.services.service_desk.problem_service import (
    get_scoped_problem_or_404, apply_problem_update, link_ticket_to_problem_record,
    cerrar_problema,
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
    create_change_record, update_change_record, approve_change_record, get_change_by_id,
    cancelar_cambio,
)
from app.services.service_desk.change_management_service import (
    assess_change_risk_ai,
    create_rollout_plan,
    check_change_suitability_for_automation,
    generate_rollback_automation_script,
    ChangeType as ChangeAutomationType,
    RiskLevel,
)
from app.services.service_desk.major_incident_service import (
    list_major_incidents_payload, declare_major_incident_record,
    update_major_incident_record, serialize_major_incident,
)
from app.services.service_desk.status_page_service import (
    build_public_status_page_payload,
    list_status_components_payload, create_status_component_record,
    update_status_component_record, delete_status_component as delete_status_component_svc,
    create_status_incident_record, add_status_incident_update_record,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _json_default_serializer(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)

# ── Service Catalog ───────────────────────────────────────────────────────────

@router.get("/catalog", summary="Catálogo de servicios")
def get_catalog(public_only: bool = False, db: Session = Depends(get_db),
                lector=Depends(get_portal_client_or_user)):
    """Catalogo para un agente (todo) o para un cliente del portal (lo visible de su organizacion)."""
    return APIListResponse.ok(items=list_catalog_payload(db, public_only or lector.solo_publico))

@router.post("/catalog/categories", summary="Crear categoría")
def create_category(payload: ServiceCategoryIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    c = create_category_record(db, payload)
    _commit_or_rollback(db); db.refresh(c)
    return APIResponse.ok(data={"id": c.id, "name": c.name})

@router.patch("/catalog/categories/{cat_id}", summary="Actualizar categoría")
def update_category(cat_id: str, payload: ServiceCategoryIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    c = update_category_record(db, cat_id, payload)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"id": c.id, "name": c.name})

@router.delete("/catalog/categories/{cat_id}", summary="Desactivar categoría")
def delete_category(cat_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    enforce_abac(db, current_user, "sd_catalog_category", cat_id, action="delete")
    deactivate_category_record(db, cat_id)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True})

@router.post("/catalog/services", summary="Crear servicio")
def create_service(payload: ServiceItemIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    s = create_service_record(db, payload)
    _commit_or_rollback(db); db.refresh(s)
    return APIResponse.ok(data={"id": s.id, "name": s.name})

@router.patch("/catalog/services/{service_id}", summary="Actualizar servicio")
def update_service(service_id: str, payload: ServiceItemUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    update_service_record(db, service_id, payload)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True})

@router.delete("/catalog/services/{service_id}", summary="Desactivar servicio")
def delete_service(service_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    enforce_abac(db, current_user, "sd_catalog_service", service_id, action="delete")
    deactivate_service_record(db, service_id)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True})

# ── Agent Groups ──────────────────────────────────────────────────────────────

@router.get("/groups", summary="Grupos de agentes")
def get_groups(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return APIListResponse.ok(items=list_groups_payload(db))

@router.post("/groups", summary="Crear grupo")
def create_group(payload: AgentGroupIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    g = create_group_record(db, payload)
    _commit_or_rollback(db); db.refresh(g)
    return APIResponse.ok(data={"id": g.id, "name": g.name})

@router.patch("/groups/{group_id}", summary="Actualizar grupo")
def update_group(group_id: str, payload: AgentGroupIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    g = update_group_record(db, group_id, payload)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"id": g.id, "name": g.name})

@router.delete("/groups/{group_id}", summary="Eliminar grupo")
def delete_group(group_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    enforce_abac(db, current_user, "sd_agent_group", group_id, action="delete")
    deactivate_group_record(db, group_id)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True})

@router.post("/groups/{group_id}/members/{user_id}", summary="Añadir miembro a grupo")
def add_group_member(group_id: str, user_id: str, is_lead: bool = False, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    add_group_member_record(db, group_id, user_id, is_lead)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True})

@router.delete("/groups/{group_id}/members/{user_id}", summary="Eliminar miembro de grupo")
def remove_group_member(group_id: str, user_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    enforce_abac(db, current_user, "sd_agent_group", group_id, action="delete")
    remove_group_member_record(db, group_id, user_id)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True})

@router.get("/groups/{group_id}/workload", summary="Distribución de carga de tickets por agente en el grupo")
def get_group_workload(group_id: str, db: Session = Depends(get_db), _: User = Depends(require_any_manager)):
    return APIResponse.ok(data=get_group_workload_payload(db, group_id))

# ── Problems ──────────────────────────────────────────────────────────────────

# NOTE: GET /problems and POST /problems are canonically served by
# problem_management.py (ITSM-P08). Removed here to avoid duplicate routes.
# PATCH /problems/{id} and the link-ticket route below remain unique to this module.

@router.patch("/problems/{problem_id}", summary="Actualizar problema")
@limiter.limit("30/minute")
def update_problem(request: Request, problem_id: str, payload: ProblemUpdateIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    p = get_scoped_problem_or_404(db, current_user, problem_id)
    apply_problem_update(db, current_user, p, payload)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True})

@router.delete("/problems/{problem_id}", summary="Cerrar problema")
@limiter.limit("30/minute")
def close_problem(request: Request, problem_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    """Auditoria 2026-08 (hallazgo 37): esta ruta **no existia**.

    El boton de borrar de `ITSMKnowledgeTab` **no hacia nada** — uno de los dos
    borrados silenciosos que la auditoria dejo anotados. Cierra el problema en
    vez de borrar la fila; el porque esta en el docstring de `cerrar_problema`.
    """
    enforce_abac(db, current_user, "sd_problem", problem_id, action="delete")
    datos = cerrar_problema(db, current_user, problem_id)
    _commit_or_rollback(db)
    return APIResponse.ok(data=datos)

@router.post("/problems/{problem_id}/link-ticket/{ticket_id}", summary="Vincular ticket a problema")
@limiter.limit("30/minute")
def link_ticket_to_problem(request: Request, problem_id: str, ticket_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    link_ticket_to_problem_record(db, current_user, problem_id, ticket_id)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True})

# ── Announcements ─────────────────────────────────────────────────────────────

@router.get("/announcements", summary="Anuncios activos")
def list_announcements(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), response: Response = None,
                       db: Session = Depends(get_db), lector: Lector = Depends(get_portal_client_or_user)):
    # Auditoria 2026-11: se servian sin login, sin organizacion y sin mirar
    # `show_to_clients` (un anonimo leia los internos de todas).
    return APIListResponse.ok(items=serialize_announcements(list_active_announcements(
        db, page, page_size, response, solo_clientes=lector.solo_publico)), page=page, page_size=page_size)

@router.post("/announcements", summary="Crear anuncio")
def create_announcement(payload: AnnouncementIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    a = build_announcement(db, payload, current_user.id)
    _commit_or_rollback(db); db.refresh(a)
    return APIResponse.ok(data={"id": a.id})

@router.delete("/announcements/{ann_id}", summary="Desactivar anuncio")
def deactivate_announcement(ann_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    enforce_abac(db, current_user, "sd_announcement", ann_id, action="delete")
    deactivate_announcement_record(db, ann_id)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True})

# ── Routing Rules ─────────────────────────────────────────────────────────────

@router.get("/routing-rules", summary="Listar reglas de routing automático")
def list_routing_rules(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return APIListResponse.ok(items=[serialize_routing_rule(r) for r in _list_routing_rules(db)])

@router.post("/routing-rules", summary="Crear regla de routing")
def create_routing_rule(payload: dict = Body(...), db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    rule = build_routing_rule(db, payload)
    _commit_or_rollback(db); db.refresh(rule)
    return APIResponse.ok(data={"id": rule.id, "name": rule.name})

@router.patch("/routing-rules/{rule_id}", summary="Actualizar regla de routing")
def update_routing_rule(rule_id: str, payload: dict = Body(...), db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    rule = get_routing_rule_or_404(db, rule_id)
    apply_routing_rule_update(rule, payload)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True})

@router.delete("/routing-rules/{rule_id}", summary="Eliminar regla de routing")
def delete_routing_rule(rule_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    enforce_abac(db, current_user, "sd_routing_rule", rule_id, action="delete")
    delete_routing_rule_svc(db, rule_id)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True})


@router.get("/routing/stats", summary="Estadísticas del modelo ML de routing (ITSM-P07)")
def routing_ml_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """Return aggregate ML routing statistics: coverage, avg resolution time, top agents."""
    from app.services.service_desk.ml_routing_service import get_routing_stats

    return APIResponse.ok(data=get_routing_stats(db))


@router.post("/routing/run-outcome-scan", summary="Backfill de outcomes de routing (admin)")
def run_routing_outcome_scan(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Manually trigger the routing outcome backfill job."""
    from app.services.service_desk.ml_routing_service import run_outcome_scan

    result = run_outcome_scan(db)
    return APIResponse.ok(data={"ok": True, **result})

# ── Change Management ─────────────────────────────────────────────────────────

@router.get("/changes", summary="Listar Change Requests ITSM")
def list_changes(
    status: Optional[str] = Query(None), change_type: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None), date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    return APIListResponse.ok(items=list_changes_payload(db, current_user, status, change_type, date_from, date_to, page, page_size), page=page, page_size=page_size)

@router.get("/changes/{change_id}", summary="Detalle de Change Request")
def get_change(change_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return APIResponse.ok(data=get_change_payload(db, current_user, change_id, full=True))

@router.post("/changes", summary="Crear Change Request ITSM")
def create_change(payload: dict = Body(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    cr = create_change_record(db, current_user, payload)
    _commit_or_rollback(db); db.refresh(cr)
    return APIResponse.ok(data=serialize_change(cr))

@router.patch("/changes/{change_id}", summary="Actualizar Change Request")
def update_change(change_id: str, payload: dict = Body(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    cr = update_change_record(db, current_user, change_id, payload)
    _commit_or_rollback(db)
    return APIResponse.ok(data=serialize_change(cr))

@router.delete("/changes/{change_id}", summary="Cancelar Change Request")
def cancel_change(
    change_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    # Auditoria 2026-09: el unico control era `enforce_abac`, que sin
    # politicas activas no comprueba nada. El resto del ciclo de vida del
    # cambio —`rollout/start`, `rollback`, `cab/fast-track`— ya exige
    # gestor; cancelarlo no puede ser mas facil que ejecutarlo.
    _: User = Depends(require_any_manager),
):
    """Auditoria 2026-08 (hallazgo 37): esta ruta **no existia**.

    El boton de borrar de un cambio **no hacia nada** — el otro borrado
    silencioso. Cancela en vez de borrar; el porque, y por que un cambio ya
    implementado responde 409, estan en el docstring de `cancelar_cambio`.
    """
    enforce_abac(db, current_user, "sd_change", change_id, action="delete")
    datos = cancelar_cambio(db, current_user, change_id)
    _commit_or_rollback(db)
    return APIResponse.ok(data=datos)

@router.post("/changes/{change_id}/approve", summary="Aprobar Change Request (CAB)")
def approve_change(change_id: str, payload: dict = Body(default={}), db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    cr = approve_change_record(db, current_user, change_id, payload)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True, "status": cr.status.value})


@router.post("/changes/{change_id}/assess-risk", summary="Evaluar riesgo de cambio con IA")
def assess_change_risk(change_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    cr = get_change_by_id(db, current_user, change_id)
    if not cr:
        raise HTTPException(404, "Change request no encontrado")

    try:
        impacted = json.loads(cr.affected_cis) if cr.affected_cis else []
        if not isinstance(impacted, list):
            impacted = []
    except Exception:
        logger.debug("assess_change_risk: excepcion ignorada", exc_info=True)
        impacted = []

    assessment = assess_change_risk_ai(
        db,
        title=cr.title,
        description=cr.description,
        impact_areas=[cr.impact_description or "unspecified"],
        affected_cis=[str(v) for v in impacted],
        rollback_plan=cr.rollback_plan or "",
    )

    cr.auto_risk_score = float(assessment.get("risk_score", 0) or 0)
    cr.impact_analysis_json = json.dumps(assessment)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"change_id": cr.id, "assessment": assessment})


@router.post("/changes/{change_id}/plan-rollout", summary="Planificación de rollout automatizado")
def plan_change_rollout(
    change_id: str,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    cr = get_change_by_id(db, current_user, change_id)
    if not cr:
        raise HTTPException(404, "Change request no encontrado")

    try:
        impacted = json.loads(cr.affected_cis) if cr.affected_cis else []
        if not isinstance(impacted, list):
            impacted = []
    except Exception:
        logger.debug("plan_change_rollout: excepcion ignorada", exc_info=True)
        impacted = []

    estimated_duration = int(payload.get("estimated_duration_minutes", 120))
    rollout_plan = create_rollout_plan(
        db,
        change_id=cr.id,
        affected_cis=[str(v) for v in impacted],
        rollback_plan=cr.rollback_plan or "",
        estimated_duration_minutes=estimated_duration,
    )
    cr.suggested_window_json = json.dumps(rollout_plan, default=_json_default_serializer)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"change_id": cr.id, "rollout_plan": rollout_plan})


@router.get("/changes/{change_id}/automation-check", summary="Comprobar nivel de automatización de cambio")
def automation_check(change_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    cr = get_change_by_id(db, current_user, change_id)
    if not cr:
        raise HTTPException(404, "Change request no encontrado")

    risk_str = (cr.risk.value if cr.risk else "medium").lower()
    type_str = (cr.change_type.value if cr.change_type else "normal").lower()
    risk = RiskLevel[risk_str] if risk_str in RiskLevel.__members__ else RiskLevel.medium
    ctype = (
        ChangeAutomationType[type_str]
        if type_str in ChangeAutomationType.__members__
        else ChangeAutomationType.normal
    )

    result = check_change_suitability_for_automation(
        db,
        change_id=cr.id,
        risk_level=risk,
        change_type=ctype,
    )
    return APIResponse.ok(data={"change_id": cr.id, **result})


@router.post("/changes/{change_id}/rollback-script", summary="Generar script de rollback")
def rollback_script(change_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    cr = get_change_by_id(db, current_user, change_id)
    if not cr:
        raise HTTPException(404, "Change request no encontrado")

    try:
        impacted = json.loads(cr.affected_cis) if cr.affected_cis else []
        if not isinstance(impacted, list):
            impacted = []
    except Exception:
        logger.debug("rollback_script: excepcion ignorada", exc_info=True)
        impacted = []

    script = generate_rollback_automation_script(
        change_id=cr.number or cr.id,
        rollback_plan=cr.rollback_plan or "echo 'No rollback plan defined'",
        affected_cis=[str(v) for v in impacted],
    )
    return APIResponse.ok(data={"change_id": cr.id, "script": script})

# ── Major Incidents ───────────────────────────────────────────────────────────

@router.get("/major-incidents", summary="Listar incidentes mayores")
def list_major_incidents(status: Optional[str] = Query(None), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return APIListResponse.ok(items=list_major_incidents_payload(db, status))

@router.post("/major-incidents", summary="Declarar incidente mayor (P1/P2)")
def declare_major_incident(payload: dict = Body(...), db: Session = Depends(get_db), current_user: User = Depends(require_any_manager)):
    mi = declare_major_incident_record(db, payload, current_user.id)
    _commit_or_rollback(db); db.refresh(mi)
    return APIResponse.ok(data=serialize_major_incident(mi))

@router.patch("/major-incidents/{mi_id}", summary="Actualizar incidente mayor")
def update_major_incident(mi_id: str, payload: dict = Body(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    mi = update_major_incident_record(db, mi_id, payload)
    _commit_or_rollback(db)
    return APIResponse.ok(data=serialize_major_incident(mi))

# ── Assets ────────────────────────────────────────────────────────────────────
# Viven en ALM (`/alm/assets`). Auditoria 2026-11: aqui habia un segundo
# inventario (`sd_assets`); la migracion 111 lo fundio con ALM.

# ── Status Page ───────────────────────────────────────────────────────────────

@router.get("/status-page", summary="Estado público del servicio de una organización (?org=<slug>)")
def get_status_page(response: Response, org: Optional[str] = Query(None, max_length=100), db: Session = Depends(get_db)):
    from app.services.service_desk.status_page_service import organizacion_de_la_pagina
    # Pública y sin credenciales: la lee el widget desde la web del cliente.
    response.headers["Access-Control-Allow-Origin"] = "*"
    return APIResponse.ok(data=build_public_status_page_payload(db, organizacion_de_la_pagina(db, org)))

@router.get("/status-page/link", summary="Dirección pública de la página de estado de la organización")
def status_page_link(db: Session = Depends(get_db), current_user: User = Depends(require_any_manager)):
    from app.services.service_desk.status_page_service import enlace_publico
    return APIResponse.ok(data=enlace_publico(db, current_user.organization_id))


@router.get("/status-page/components", summary="Listar componentes del status page (admin)")
def list_status_components(db: Session = Depends(get_db), _: User = Depends(require_any_manager)):
    return APIListResponse.ok(items=list_status_components_payload(db))

@router.post("/status-page/components", summary="Crear componente del status page", status_code=201)
def create_status_component(payload: StatusComponentIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    c = create_status_component_record(db, payload)
    _commit_or_rollback(db); db.refresh(c)
    return APIResponse.ok(data={"id": c.id, "name": c.name})

@router.patch("/status-page/components/{component_id}", summary="Actualizar estado de componente")
def update_status_component(component_id: str, payload: StatusComponentIn, db: Session = Depends(get_db), _: User = Depends(require_any_manager)):
    update_status_component_record(db, component_id, payload)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True})

@router.delete("/status-page/components/{component_id}", summary="Eliminar componente")
def delete_status_component(component_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    enforce_abac(db, current_user, "sd_status_component", component_id, action="delete")
    delete_status_component_svc(db, component_id)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True})

@router.post("/status-page/components/{component_id}/incidents", summary="Declarar incidente en status page", status_code=201)
def declare_status_incident(component_id: str, payload: StatusIncidentIn, db: Session = Depends(get_db), _: User = Depends(require_any_manager)):
    inc = create_status_incident_record(db, component_id, payload)
    _commit_or_rollback(db); db.refresh(inc)
    return APIResponse.ok(data={"id": inc.id})

@router.post("/status-page/incidents/{incident_id}/updates", summary="Añadir actualización a incidente de status page")
def add_status_incident_update(incident_id: str, payload: StatusIncidentUpdateIn, db: Session = Depends(get_db), _: User = Depends(require_any_manager)):
    updates_count = add_status_incident_update_record(db, incident_id, payload)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True, "updates_count": updates_count})


# ── Problem → Change (RFC) flow ───────────────────────────────────────────────

from pydantic import BaseModel as _BaseModel, Field as _Field


class ProblemToChangeIn(_BaseModel):
    change_type: str = _Field("normal", pattern="^(standard|normal|emergency)$")
    planned_start: Optional[str] = None
    planned_end: Optional[str] = None
    custom_title: Optional[str] = _Field(None, max_length=500)
    custom_description: Optional[str] = None


# NOTE: POST /problems/{problem_id}/create-change is canonically served by
# problem_management.py. Removed here to avoid duplicate routes.


# ── Alert Correlation ML ──────────────────────────────────────────────────────

@router.get("/alerts/correlate", summary="Clusterizar alertas abiertas por CI + ventana temporal")
def correlate_alerts(
    window_hours: int = Query(4, ge=1, le=48),
    min_cluster_size: int = Query(2, ge=2, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.services.service_desk.alert_correlation_service import cluster_open_alerts
    org_id = getattr(current_user, "organization_id", None)
    clusters = cluster_open_alerts(db, organization_id=org_id, window_hours=window_hours, min_cluster_size=min_cluster_size)
    return APIResponse.ok(data={
        "clusters": [
            {
                "cluster_id": c.cluster_id,
                "size": c.size,
                "ci_id": c.ci_id,
                "category": c.category,
                "priority": c.priority,
                "correlation_score": c.correlation_score,
                "suggested_action": c.suggested_action,
                "ticket_numbers": c.ticket_numbers,
                "ticket_ids": c.ticket_ids,
                "earliest_at": c.earliest_at.isoformat() if c.earliest_at else None,
                "latest_at": c.latest_at.isoformat() if c.latest_at else None,
                "root_ci_ids": c.root_ci_ids,
            }
            for c in clusters
        ],
        "count": len(clusters),
        "window_hours": window_hours,
    })


@router.get("/alerts/correlate/stats", summary="Estadísticas de correlación de alertas")
def correlation_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.services.service_desk.alert_correlation_service import get_correlation_stats
    org_id = getattr(current_user, "organization_id", None)
    return APIResponse.ok(data=get_correlation_stats(db, organization_id=org_id))


class MergeClusterIn(_BaseModel):
    ticket_ids: list[str] = _Field(..., min_length=2)
    auto_rca: bool = True


@router.post("/alerts/correlate/merge-to-problem", summary="Convertir cluster de alertas en Problema", status_code=201)
def merge_cluster_to_problem(
    payload: MergeClusterIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.services.service_desk.alert_correlation_service import merge_cluster_to_problem as _svc
    try:
        result = _svc(db, ticket_ids=payload.ticket_ids, current_user=current_user, auto_rca=payload.auto_rca)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True, **result})


# ── CAB Rollout Execution ─────────────────────────────────────────────────────

class RolloutStartIn(_BaseModel):
    rollout_plan: dict


class PhaseAdvanceIn(_BaseModel):
    status: str = _Field(..., pattern="^(in_progress|completed|failed|skipped)$")
    notes: str = _Field("", max_length=2000)


class RollbackIn(_BaseModel):
    reason: str = _Field(..., min_length=5, max_length=1000)


class EmergencyCABIn(_BaseModel):
    approver_ids: list[str] = _Field(..., min_length=1)
    justification: str = _Field(..., min_length=10, max_length=2000)


@router.post("/changes/{change_id}/rollout/start", summary="Iniciar ejecución de rollout de cambio", status_code=201)
def start_rollout(
    change_id: str,
    payload: RolloutStartIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.services.service_desk.change_management_service import start_rollout_execution
    state = start_rollout_execution(db, change_id=change_id, rollout_plan=payload.rollout_plan, current_user=current_user)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True, "state": state})


@router.get("/changes/{change_id}/rollout", summary="Estado de ejecución de rollout")
def get_rollout_state(
    change_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.services.service_desk.change_management_service import get_rollout_execution_state
    state = get_rollout_execution_state(db, change_id)
    if not state:
        raise HTTPException(404, "No hay ejecución de rollout para este cambio")
    return APIResponse.ok(data=state)


@router.post("/changes/{change_id}/rollout/phases/{phase_number}/advance", summary="Avanzar fase de rollout")
def advance_phase(
    change_id: str,
    phase_number: int,
    payload: PhaseAdvanceIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.services.service_desk.change_management_service import advance_rollout_phase
    try:
        state = advance_rollout_phase(db, change_id=change_id, phase_number=phase_number, phase_status=payload.status, notes=payload.notes, current_user=current_user)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True, "state": state})


@router.post("/changes/{change_id}/rollback", summary="Triggear rollback manual de cambio")
def trigger_rollback(
    change_id: str,
    payload: RollbackIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.services.service_desk.change_management_service import trigger_change_rollback
    result = trigger_change_rollback(db, change_id=change_id, reason=payload.reason, current_user=current_user)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True, **result})


@router.post("/changes/{change_id}/cab/fast-track", summary="Fast-track de emergencia en CAB")
def emergency_cab_fast_track(
    change_id: str,
    payload: EmergencyCABIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.services.service_desk.change_management_service import fast_track_emergency_cab
    try:
        result = fast_track_emergency_cab(db, change_id=change_id, approver_ids=payload.approver_ids, justification=payload.justification, current_user=current_user)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True, **result})

