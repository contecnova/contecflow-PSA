"""
Enterprise endpoint — delegates all business logic to enterprise_service.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, datetime, timezone
from app.schemas.enterprise import (
    PermissionCreate, PermissionUpdate, WebhookCreate, WebhookUpdate, SSOCreate, SSOUpdate,
    SubCreate, SubUpdate, RateCreate, AssignmentCreate, WorkerCreate, WorkerUpdate, WorkerSkillCreate, ForecastUpdate
)

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager, require_admin
from app.core.abac_enforce import enforce_abac
from app.core.responses import APIListResponse, APIResponse
from app.models.user import User
from app.models.enterprise import WebhookEvent
import app.services.enterprise_service as _svc
from app.core.constantes import MAX_TAMANO_DE_PAGINA

router = APIRouter()



# ── Audit Log ─────────────────────────────────────────────────────────────────

@router.get("/audit-log", summary="Registro de auditoría global")
def get_audit_log(
    resource: Optional[str] = None, resource_id: Optional[str] = None,
    user_id: Optional[str] = None, action: Optional[str] = None,
    date_from: Optional[date] = None, date_to: Optional[date] = None,
    page: int = Query(1, ge=1), page_size: int = Query(50, le=MAX_TAMANO_DE_PAGINA),
    db: Session = Depends(get_db), current_user: User = Depends(require_admin),
):
    return APIResponse.ok(data=_svc.get_audit_log(db, resource, resource_id, user_id, action, date_from, date_to, page, page_size))


# ── Cadena a prueba de manipulación (revisión 2026-11) ──────────────────────
@router.get("/audit-log/chain/verify", summary="Verifica la cadena del registro de auditoría de la empresa (admin)")
def verify_audit_chain(
    expected_seq: Optional[int] = Query(None, ge=1), expected_hash: Optional[str] = Query(None, max_length=64),
    db: Session = Depends(get_db), current_user: User = Depends(require_admin),
):
    from app.db import cadena_auditoria
    esperada = {"seq": expected_seq, "entry_hash": expected_hash} if expected_seq and expected_hash else None
    return APIResponse.ok(data=cadena_auditoria.verificar(db, current_user.organization_id, esperada))


@router.get("/audit-log/chain/export", summary="Exportación firmada (Ed25519) del registro de auditoría (admin)")
def export_audit_chain(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    import json as _json
    from fastapi.responses import Response
    doc = _svc.exportar_cadena_de_auditoria(db, current_user)
    nombre = f"audit-chain-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.json"
    return Response(_json.dumps(doc, ensure_ascii=False, indent=1), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.get("/audit-log/chain/public-key", summary="Clave pública (PEM) que firma las exportaciones del registro")
def audit_chain_public_key(current_user: User = Depends(require_admin)):
    from app.db import cadena_auditoria
    return APIResponse.ok(data={"public_key_pem": cadena_auditoria.clave_publica_pem(), "alg": "Ed25519"})


@router.get("/audit-log/stats", summary="Estadísticas del audit log")
def audit_stats(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db), current_user: User = Depends(require_admin),
):
    return APIResponse.ok(data=_svc.compute_audit_stats(db, days))


# ── Project Permissions ───────────────────────────────────────────────────────



@router.get("/project-permissions/{project_id}", summary="Permisos de un proyecto")
def get_project_permissions(
    project_id: str, db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIListResponse.ok(items=_svc.get_project_permissions(project_id, db))


@router.post("/project-permissions/{project_id}", summary="Conceder acceso a proyecto")
def grant_project_permission(
    project_id: str, payload: PermissionCreate,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    try:
        return APIResponse.ok(data=_svc.grant_project_permission(project_id, payload, current_user, db))
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.patch("/project-permissions/{project_id}/{permission_id}", summary="Actualizar permiso")
def update_project_permission(
    project_id: str, permission_id: str, payload: PermissionUpdate,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    try:
        return APIResponse.ok(data=_svc.update_project_permission(project_id, permission_id, payload, db))
    except ValueError:
        raise HTTPException(404)


@router.delete("/project-permissions/{project_id}/{permission_id}", summary="Revocar acceso")
def revoke_project_permission(
    project_id: str, permission_id: str,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "project_permission", permission_id, action="delete")
    try:
        return APIResponse.ok(data=_svc.revoke_project_permission(project_id, permission_id, current_user, db))
    except ValueError:
        raise HTTPException(404)


# ── Webhooks ──────────────────────────────────────────────────────────────────



@router.get("/webhooks", summary="Listar webhooks")
def list_webhooks(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    return APIListResponse.ok(items=_svc.list_webhooks(db))


@router.get("/webhooks/events", summary="Lista de eventos disponibles")
def list_webhook_events(current_user: User = Depends(get_current_user)):
    return APIListResponse.ok(items=[{"value": e.value, "label": e.value.replace(".", " › ").replace("_", " ").title()} for e in WebhookEvent])


@router.post("/webhooks", summary="Crear webhook")
def create_webhook(
    payload: WebhookCreate, db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        return APIResponse.ok(data=_svc.create_webhook(payload, current_user, db))
    except ValueError as e:
        # SSRF guard / validation failure → 400 (bad destination URL).
        raise HTTPException(400, str(e))


@router.patch("/webhooks/{hook_id}", summary="Actualizar webhook")
def update_webhook(
    hook_id: str, payload: WebhookUpdate,
    db: Session = Depends(get_db), current_user: User = Depends(require_admin),
):
    try:
        return APIResponse.ok(data=_svc.update_webhook(hook_id, payload, current_user, db))
    except ValueError as e:
        if str(e) == "not_found":
            raise HTTPException(404)
        # SSRF guard / validation failure → 400.
        raise HTTPException(400, str(e))


@router.delete("/webhooks/{hook_id}", summary="Eliminar webhook")
def delete_webhook(
    hook_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin),
):
    enforce_abac(db, current_user, "webhook", hook_id, action="delete")
    try:
        return APIResponse.ok(data=_svc.delete_webhook(hook_id, current_user, db))
    except ValueError:
        raise HTTPException(404)


@router.post("/webhooks/{hook_id}/test", summary="Enviar payload de prueba")
def test_webhook(
    hook_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin),
):
    hook = _svc.get_webhook_for_test(hook_id, db)
    if not hook: raise HTTPException(404)
    return APIResponse.ok(data=_svc.test_webhook_delivery(hook, current_user))


@router.get("/webhooks/{hook_id}/deliveries", summary="Historial de entregas")
def get_deliveries(
    hook_id: str, limit: int = Query(20, le=100),
    db: Session = Depends(get_db), current_user: User = Depends(require_admin),
):
    return APIListResponse.ok(items=_svc.get_webhook_deliveries(hook_id, limit, db))


# ── SSO ───────────────────────────────────────────────────────────────────────



@router.get("/sso", summary="Configuraciones SSO")
def list_sso(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    return APIListResponse.ok(items=_svc.list_sso_configs(db))


@router.post("/sso", summary="Crear configuración SSO")
def create_sso(
    payload: SSOCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin),
):
    return APIResponse.ok(data=_svc.create_sso_config(payload, current_user, db))


@router.patch("/sso/{config_id}", summary="Actualizar SSO")
def update_sso(
    config_id: str, payload: SSOUpdate,
    db: Session = Depends(get_db), current_user: User = Depends(require_admin),
):
    try:
        return APIResponse.ok(data=_svc.update_sso_config(config_id, payload, current_user, db))
    except ValueError as e:
        msg = str(e)
        raise HTTPException(403 if "org_mismatch" in msg else 404, msg)


@router.delete("/sso/{config_id}", summary="Eliminar SSO")
def delete_sso(
    config_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin),
):
    enforce_abac(db, current_user, "sso_config", config_id, action="delete")
    try:
        return APIResponse.ok(data=_svc.delete_sso_config(config_id, db, current_user))
    except ValueError:
        raise HTTPException(404)


@router.post("/sso/{config_id}/test", summary="Validar configuración SSO")
def test_sso(
    config_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin),
):
    config = _svc.get_sso_config_for_test(config_id, db)
    if not config: raise HTTPException(404)
    return APIResponse.ok(data=_svc.validate_sso_config(config))


# ── Notifications ─────────────────────────────────────────────────────────────

@router.get("/notifications", summary="Mis notificaciones")
def my_notifications(
    unread_only: bool = False, page: int = Query(1, ge=1), page_size: int = Query(20, le=100),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data=_svc.get_my_notifications(current_user, unread_only, page, page_size, db))


@router.post("/notifications/read-all", summary="Marcar todas como leídas")
def mark_all_read(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return APIResponse.ok(data=_svc.mark_all_notifications_read(current_user, db))


@router.post("/notifications/{notif_id}/read", summary="Marcar como leída")
def mark_read(
    notif_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    try:
        return APIResponse.ok(data=_svc.mark_notification_read(notif_id, current_user, db))
    except ValueError:
        raise HTTPException(404)


@router.delete("/notifications/clear-old", summary="Limpiar notificaciones antiguas")
def clear_old_notifications(
    days: int = Query(90, ge=30),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    enforce_abac(db, current_user, "notification", current_user.id, action="delete")
    return APIResponse.ok(data=_svc.clear_old_notifications(current_user, days, db))


# ── Subcontractors ────────────────────────────────────────────────────────────



@router.get("/subcontractors", summary="Listar subcontratistas")
def list_subcontractors(
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    return APIListResponse.ok(items=_svc.list_subcontractors(is_active, db))


@router.post("/subcontractors", summary="Crear subcontratista")
def create_subcontractor(
    payload: SubCreate, db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=_svc.create_subcontractor(payload, current_user, db))


@router.patch("/subcontractors/{sub_id}", summary="Actualizar subcontratista")
def update_subcontractor(
    sub_id: str, payload: SubUpdate,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    try:
        return APIResponse.ok(data=_svc.update_subcontractor(sub_id, payload, db))
    except ValueError:
        raise HTTPException(404)


@router.delete("/subcontractors/{sub_id}", summary="Eliminar subcontratista (soft delete)")
def delete_subcontractor(
    sub_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "subcontractor", sub_id, action="delete")
    try:
        return APIResponse.ok(data=_svc.delete_subcontractor(sub_id, db))
    except ValueError as e:
        msg = str(e)
        if "has_dependencies" in msg:
            detail = msg.split("has_dependencies:", 1)[1] if ":" in msg else "Tiene dependencias"
            raise HTTPException(400, f"No se puede eliminar: {detail}")
        raise HTTPException(404, "Subcontratista no encontrado")


@router.post("/subcontractors/{sub_id}/rates", summary="Añadir tarifa")
def add_rate(
    sub_id: str, payload: RateCreate,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    try:
        return APIResponse.ok(data=_svc.add_subcontractor_rate(sub_id, payload, db))
    except ValueError:
        raise HTTPException(404)


@router.delete("/subcontractors/{sub_id}/rates/{rate_id}", summary="Eliminar tarifa")
def delete_rate(
    sub_id: str, rate_id: str,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "subcontractor_rate", rate_id, action="delete")
    try:
        return APIResponse.ok(data=_svc.delete_subcontractor_rate(sub_id, rate_id, db))
    except ValueError as e:
        msg = str(e)
        raise HTTPException(400 if "dependencies" in msg else 404, msg)


@router.get("/subcontractors/{sub_id}/assignments", summary="Asignaciones del subcontratista")
def get_assignments(
    sub_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    return APIListResponse.ok(items=_svc.get_subcontractor_assignments(sub_id, db))


@router.post("/subcontractors/{sub_id}/assignments", summary="Asignar a proyecto")
def create_assignment(
    sub_id: str, payload: AssignmentCreate,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    try:
        return APIResponse.ok(data=_svc.create_subcontractor_assignment(sub_id, payload, current_user, db))
    except ValueError:
        raise HTTPException(404)


@router.get("/subcontractors/workers", summary="Buscar trabajadores de subcontratistas")
def list_all_workers(
    skill_id: Optional[str] = None, is_active: Optional[bool] = None,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    return APIListResponse.ok(items=_svc.list_all_workers(skill_id, is_active, db))


@router.get("/subcontractors/{sub_id}/workers", summary="Trabajadores del subcontratista")
def get_workers(
    sub_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    try:
        return APIListResponse.ok(items=_svc.get_workers_for_subcontractor(sub_id, db))
    except ValueError:
        raise HTTPException(404)


@router.post("/subcontractors/{sub_id}/workers", summary="Añadir trabajador al subcontratista", status_code=201)
def create_worker(
    sub_id: str, payload: WorkerCreate,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    sub = _svc.get_subcontractor(db, sub_id)
    if not sub: raise HTTPException(404)
    return APIResponse.ok(data=_svc.create_worker_with_user(sub, payload, current_user, db))


@router.patch("/subcontractors/workers/{worker_id}", summary="Actualizar trabajador")
def update_worker(
    worker_id: str, payload: WorkerUpdate,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    try:
        return APIResponse.ok(data=_svc.update_worker(worker_id, payload, db))
    except ValueError:
        raise HTTPException(404)


@router.delete("/subcontractors/workers/{worker_id}", summary="Desactivar trabajador (soft delete)")
def delete_worker(
    worker_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "subcontractor_worker", worker_id, action="delete")
    try:
        return APIResponse.ok(data=_svc.delete_worker(worker_id, db))
    except ValueError as e:
        msg = str(e)
        raise HTTPException(400 if "dependencies" in msg else 404, msg)


@router.post("/subcontractors/workers/{worker_id}/skills", summary="Asignar skill al trabajador", status_code=201)
def add_worker_skill(
    worker_id: str, payload: WorkerSkillCreate,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    try:
        return APIResponse.ok(data=_svc.add_worker_skill(worker_id, payload, db))
    except ValueError:
        raise HTTPException(404)


@router.delete("/subcontractors/workers/{worker_id}/skills/{skill_id}", summary="Eliminar skill del trabajador")
def remove_worker_skill(
    worker_id: str, skill_id: str,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "subcontractor_worker_skill", skill_id, action="delete")
    try:
        return APIResponse.ok(data=_svc.remove_worker_skill(worker_id, skill_id, db))
    except ValueError:
        raise HTTPException(404)


@router.get("/subcontractors/{sub_id}/timelogs", summary="Registros de horas del subcontratista")
def get_timelogs(
    sub_id: str, project_id: Optional[str] = None,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    return APIListResponse.ok(items=_svc.get_timelogs(sub_id, project_id, db))


@router.post("/subcontractors/{sub_id}/timelogs", summary="Registrar horas de subcontratista")
def create_timelog(
    sub_id: str, payload: dict = Body(...),
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    try:
        return APIResponse.ok(data=_svc.create_timelog(sub_id, payload, db))
    except ValueError:
        raise HTTPException(404)


@router.delete("/subcontractors/{sub_id}/timelogs/{log_id}", summary="Eliminar registro de horas")
def delete_timelog(
    sub_id: str, log_id: str,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "subcontractor_timelog", log_id, action="delete")
    try:
        return APIResponse.ok(data=_svc.delete_timelog(sub_id, log_id, db))
    except ValueError as e:
        msg = str(e)
        raise HTTPException(400 if "invoiced" in msg else 404, msg)


@router.get("/subcontractors/{sub_id}/invoices", summary="Facturas recibidas del subcontratista")
def get_sub_invoices(
    sub_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    return APIListResponse.ok(items=_svc.get_sub_invoices(sub_id, db))


@router.post("/subcontractors/{sub_id}/invoices", summary="Registrar factura recibida")
def create_sub_invoice(
    sub_id: str, payload: dict = Body(...),
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    try:
        return APIResponse.ok(data=_svc.create_sub_invoice(sub_id, payload, current_user, db))
    except ValueError:
        raise HTTPException(404)


@router.patch("/subcontractors/{sub_id}/invoices/{inv_id}", summary="Actualizar estado de factura")
def update_sub_invoice(
    sub_id: str, inv_id: str, payload: dict = Body(...),
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    try:
        return APIResponse.ok(data=_svc.update_sub_invoice(sub_id, inv_id, payload, db))
    except ValueError:
        raise HTTPException(404)


@router.get("/subcontractors-dashboard", summary="Dashboard global de subcontratistas")
def subcontractors_dashboard(
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=_svc.get_subcontractors_dashboard(db))


# ── Revenue Forecast ──────────────────────────────────────────────────────────



@router.get("/revenue-forecast/portfolio", summary="Previsión de ingresos de toda la cartera")
def portfolio_forecast(
    year: int = Query(None),
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=_svc.get_portfolio_forecast(db, year or datetime.now(timezone.utc).year))


@router.get("/revenue-forecast/{project_id}", summary="Previsión de un proyecto")
def project_forecast(
    project_id: str, year: int = Query(None),
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=_svc.get_project_forecast(project_id, year or datetime.now(timezone.utc).year, db))


@router.post("/revenue-forecast/{project_id}/{year}/{month}", summary="Crear/actualizar previsión mensual")
def upsert_forecast(
    project_id: str, year: int, month: int, payload: ForecastUpdate,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    if not 1 <= month <= 12: raise HTTPException(400, "Mes inválido (1-12)")
    return APIResponse.ok(data=_svc.upsert_forecast(project_id, year, month, payload, db))
