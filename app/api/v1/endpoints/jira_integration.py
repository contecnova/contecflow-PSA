"""
Jira Integration API endpoints.

Routes:
  GET    /integrations/jira/configs
  POST   /integrations/jira/configs
  PATCH  /integrations/jira/configs/{config_id}
  DELETE /integrations/jira/configs/{config_id}
  POST   /integrations/jira/configs/{config_id}/test
  GET    /integrations/jira/configs/{config_id}/sync-log
  POST   /integrations/jira/tickets/{ticket_id}/push
  POST   /integrations/jira/webhook          — receives Jira Cloud webhooks
  POST   /integrations/jira/sync/{config_id} — manual incremental poll

Auditoria 2026-08 (hallazgo 22). Las consultas de este fichero estan en
`services/service_desk/jira_sync_service.py`, y al moverlas aparecio la misma
asimetria de siempre dentro del propio fichero: cuatro endpoints usaban
`org_scoped_or_404` y otros tres buscaban por id a secas. El que mas importa es
`push_ticket`: una `JiraConfig` lleva las credenciales de Jira de un cliente, y
sin acotar se podia empujar un ticket con las de otro.

Auditoria 2026-11 (#34): `sd_jira_configs` es la unica configuracion de Jira.
La conexion de las tareas de proyecto (`/jira/*`) es la fila con
`usar_para_tareas`; la prueba de conexion es `jira_service.probar_conexion`.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin, require_admin_or_pm
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.jira_integration import (
    JiraConfig,
    JiraSyncDirection,
)
from app.models.user import User
from app.core.abac_enforce import enforce_abac
from app.services.service_desk.jira_sync_service import (
    aplicar_cambios_de_configuracion,
    borrar_configuracion,
    configuracion_activa_propia,
    configuracion_propia,
    crear_configuracion,
    listar_configuraciones,
    procesar_webhook,
    registro_de_sincronizacion,
    ticket_propio,
    empujar_ticket_confirmado,
    run_incremental_sync,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/integrations/jira", tags=["Jira Integration"])


# ── Schemas ────────────────────────────────────────────────────────────────────


class JiraConfigIn(BaseModel):
    name: str
    jira_base_url: str
    jira_email: str
    jira_api_token: str          # plain text; service layer encrypts on store
    jira_project_key: str
    jira_issue_type_incident: str = "Incident"
    jira_issue_type_service_request: str = "Service Request"
    jira_issue_type_change: str = "Change"
    jira_issue_type_problem: str = "Problem"
    sync_direction: JiraSyncDirection = JiraSyncDirection.bidirectional
    sync_comments: bool = True
    sync_status_changes: bool = True
    sync_priority_changes: bool = True
    sync_assignments: bool = False
    sync_interval_minutes: int = 5
    status_map: Optional[dict] = None
    priority_map: Optional[dict] = None
    usar_para_tareas: bool = False


class JiraConfigPatch(BaseModel):
    name: Optional[str] = None
    jira_api_token: Optional[str] = None
    sync_direction: Optional[JiraSyncDirection] = None
    sync_comments: Optional[bool] = None
    sync_status_changes: Optional[bool] = None
    sync_priority_changes: Optional[bool] = None
    sync_interval_minutes: Optional[int] = None
    is_active: Optional[bool] = None
    status_map: Optional[dict] = None
    priority_map: Optional[dict] = None
    usar_para_tareas: Optional[bool] = None


class JiraFieldMapIn(BaseModel):
    contecflow_field: str
    jira_field_id: str
    transform_fn: Optional[str] = None


# ── Helpers ────────────────────────────────────────────────────────────────────


def _serialize_config(c: JiraConfig) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "jira_base_url": c.jira_base_url,
        "jira_email": c.jira_email,
        "jira_project_key": c.jira_project_key,
        "jira_issue_type_incident": c.jira_issue_type_incident,
        "jira_issue_type_service_request": c.jira_issue_type_service_request,
        "jira_issue_type_change": c.jira_issue_type_change,
        "jira_issue_type_problem": c.jira_issue_type_problem,
        "sync_direction": c.sync_direction,
        "sync_comments": c.sync_comments,
        "sync_status_changes": c.sync_status_changes,
        "sync_priority_changes": c.sync_priority_changes,
        "sync_assignments": c.sync_assignments,
        "sync_interval_minutes": c.sync_interval_minutes,
        "is_active": c.is_active,
        "usar_para_tareas": bool(c.usar_para_tareas),
        "last_full_sync_at": c.last_full_sync_at,
        "created_at": c.created_at,
    }


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.get("/configs", response_model=APIListResponse[dict], summary="Listar configuraciones Jira")
def list_jira_configs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_pm),
):
    configs, total = listar_configuraciones(
        db, current_user, page=page, page_size=page_size)
    items = [_serialize_config(c) for c in configs]
    return APIListResponse.ok(items=items, total=total, page=page, page_size=page_size)


@router.post("/configs", summary="Crear configuración Jira")
def create_jira_config(
    payload: JiraConfigIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_pm),
):
    config = crear_configuracion(db, current_user, {
        "name": payload.name,
        "jira_base_url": payload.jira_base_url,
        "jira_email": payload.jira_email,
        # El cifrado queda para la capa de gestion de claves, como estaba.
        "jira_api_token_enc": payload.jira_api_token,
        "jira_project_key": payload.jira_project_key,
        "jira_issue_type_incident": payload.jira_issue_type_incident,
        "jira_issue_type_service_request": payload.jira_issue_type_service_request,
        "jira_issue_type_change": payload.jira_issue_type_change,
        "jira_issue_type_problem": payload.jira_issue_type_problem,
        "sync_direction": payload.sync_direction,
        "sync_comments": payload.sync_comments,
        "sync_status_changes": payload.sync_status_changes,
        "sync_priority_changes": payload.sync_priority_changes,
        "sync_assignments": payload.sync_assignments,
        "sync_interval_minutes": payload.sync_interval_minutes,
        "status_map_json": json.dumps(payload.status_map) if payload.status_map else None,
        "priority_map_json": json.dumps(payload.priority_map) if payload.priority_map else None,
        "usar_para_tareas": payload.usar_para_tareas,
    })
    return APIResponse.ok(data=_serialize_config(config))


@router.patch("/configs/{config_id}", summary="Actualizar configuración Jira")
def patch_jira_config(
    config_id: str,
    payload: JiraConfigPatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_pm),
):
    config: JiraConfig = configuracion_propia(db, current_user, config_id)
    config = aplicar_cambios_de_configuracion(
        db, config, payload.model_dump(exclude_none=True))
    return APIResponse.ok(data=_serialize_config(config))


@router.delete("/configs/{config_id}", summary="Eliminar configuración Jira")
def delete_jira_config(
    config_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_pm),
):
    enforce_abac(db, current_user, "jira_config", config_id, action="delete")
    borrar_configuracion(db, current_user, config_id)
    return APIResponse.ok(data={"deleted": True})


@router.post("/configs/{config_id}/test", summary="Probar conexión Jira")
def test_jira_connection(
    config_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_pm),
):
    """Verify credentials by calling Jira's /myself endpoint (`jira_service.probar_conexion`)."""
    from app.core.errores import ErrorDeDominio
    from app.services import jira_service

    config = configuracion_propia(db, current_user, config_id)
    try:
        r = jira_service.probar_conexion(jira_service.credenciales(config))
    except ErrorDeDominio as exc:
        # Contrato de esta ruta: 200 con ok=False (sin el cuerpo remoto, #25).
        return APIResponse.ok(data={"ok": False, "error": str(exc.detail)})
    return APIResponse.ok(data={"ok": True, "jira_account_id": r["account_id"], "display_name": r["display_name"]})


@router.get("/configs/{config_id}/sync-log", summary="Ver log de sincronización")
def get_sync_log(
    config_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_pm),
):
    # La configuracion se comprueba ANTES de exponer sus registros.
    config = configuracion_propia(db, current_user, config_id)
    logs, total = registro_de_sincronizacion(
        db, config, page=page, page_size=page_size)
    items = [
        {
            "id": lg.id,
            "ticket_id": lg.ticket_id,
            "jira_issue_key": lg.jira_issue_key,
            "event_type": lg.event_type,
            "direction": lg.direction,
            "success": lg.success,
            "error_message": lg.error_message,
            "occurred_at": lg.occurred_at,
        }
        for lg in logs
    ]
    return APIListResponse.ok(items=items, total=total, page=page, page_size=page_size)


@router.post("/tickets/{ticket_id}/push", summary="Empujar ticket a Jira")
def push_ticket(
    ticket_id: str,
    config_id: str = Query(..., description="Jira config ID to use"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sensible: credenciales de integracion
):
    """Manually push or re-push a Contecflow ticket to Jira."""
    # Las dos guardas son de la organizacion de quien llama. La de la
    # configuracion importa especialmente: lleva las credenciales de Jira de un
    # cliente, y empujar con las de otro es lo que esto impide.
    ticket = ticket_propio(db, current_user, ticket_id)
    config = configuracion_activa_propia(db, current_user, config_id)

    sync_map = empujar_ticket_confirmado(db, config, ticket)
    return APIResponse.ok(data={
        "ok": True,
        "jira_issue_key": sync_map.jira_issue_key,
        "sync_status": sync_map.sync_status,
    })


@router.post("/webhook", summary="Recibir webhook de Jira Cloud")
async def receive_jira_webhook(
    request: Request,
    x_atlassian_webhook_token: Optional[str] = Header(None),
    x_hub_signature_256: Optional[str] = Header(None),
    org: Optional[str] = Query(None, description="Organización (solo acota; autentica el secreto)"),
    db: Session = Depends(get_db),
):
    """
    Receives Jira Cloud webhooks (issue_updated, comment_created, etc.)
    and applies changes to the linked Contecflow ticket.

    Auditoria 2026-11 (#14): autentica el secreto de webhook de UNA
    organizacion (`POST /jira/webhook-secret`) y solo toca los enlaces de las
    configuraciones de esa organizacion. El `JIRA_WEBHOOK_SECRET` global ya no
    autentica: lo conocia cualquier cliente que configurase su Jira.

    Jira sends: {"webhookEvent": "jira:issue_updated", "issue": {...}}
    """
    from app.core.async_db import run_db
    from app.services.jira_service import organizacion_del_webhook

    body = await request.body()
    org_id = await run_db(organizacion_del_webhook, db, body,
                          x_atlassian_webhook_token, x_hub_signature_256, org)
    if not org_id:
        logger.warning("Jira webhook rejected: invalid/missing authentication token")
        raise HTTPException(403, "Invalid Jira webhook authentication")

    try:
        payload = json.loads(body or b"{}")
    except (ValueError, TypeError):
        raise HTTPException(400, "Invalid JSON payload")

    issue = payload.get("issue") or {}
    issue_key = issue.get("key") or payload.get("issueKey") or ""

    if not issue_key:
        return {"ok": True, "skipped": "no issue key"}

    # The handler is async (it awaits the raw body for auth), so the blocking
    # ORM work is offloaded to the threadpool to avoid stalling the event loop.
    return await run_db(procesar_webhook, db, issue, issue_key, org_id)


@router.post("/sync/{config_id}", summary="Sincronización incremental manual")
def run_manual_sync(
    config_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_pm),
):
    """Trigger an incremental sync poll for all mapped tickets of a config."""
    # La configuracion se comprueba antes de encolar: sin esto un administrador
    # disparaba la sincronizacion de la configuracion de otro cliente.
    config = configuracion_propia(db, current_user, config_id)
    # Segunda auditoria 2026-11 (n.º 31): antes `add_task(run_incremental_sync,
    # db, ...)` usaba la sesion de la peticion cuando la peticion ya habia
    # terminado (y cerrado esa sesion). Ahora viaja el id y el trabajo abre su
    # propia sesion, con el contexto de la empresa de la configuracion.
    from app.core.segundo_plano import encolar
    encolar(run_incremental_sync, config_id=config.id,
            _organizacion=config.organization_id)
    return APIResponse.ok(data={"ok": True, "message": "Incremental sync started in background"})
