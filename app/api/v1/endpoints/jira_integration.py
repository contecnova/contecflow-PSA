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
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin_or_pm
from app.core.responses import APIListResponse
from app.db.session import get_db
from app.models.jira_integration import (
    JiraConfig,
    JiraFieldMap,
    JiraSyncDirection,
    JiraSyncLog,
    JiraSyncMap,
)
from app.models.service_desk import Ticket
from app.models.user import User
from app.core.abac_enforce import enforce_abac
from app.services.service_desk.jira_sync_service import (
    apply_jira_update_to_ticket,
    pull_jira_issue,
    push_ticket_to_jira,
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
    total = db.query(JiraConfig).count()
    configs = (
        db.query(JiraConfig)
        .order_by(JiraConfig.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [_serialize_config(c) for c in configs]
    return APIListResponse.ok(items=items, total=total, page=page, page_size=page_size)


@router.post("/configs", summary="Crear configuración Jira")
def create_jira_config(
    payload: JiraConfigIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_pm),
):
    config = JiraConfig(
        name=payload.name,
        jira_base_url=payload.jira_base_url,
        jira_email=payload.jira_email,
        jira_api_token_enc=payload.jira_api_token,  # encryption deferred to future key-mgmt layer
        jira_project_key=payload.jira_project_key,
        jira_issue_type_incident=payload.jira_issue_type_incident,
        jira_issue_type_service_request=payload.jira_issue_type_service_request,
        jira_issue_type_change=payload.jira_issue_type_change,
        jira_issue_type_problem=payload.jira_issue_type_problem,
        sync_direction=payload.sync_direction,
        sync_comments=payload.sync_comments,
        sync_status_changes=payload.sync_status_changes,
        sync_priority_changes=payload.sync_priority_changes,
        sync_assignments=payload.sync_assignments,
        sync_interval_minutes=payload.sync_interval_minutes,
        status_map_json=json.dumps(payload.status_map) if payload.status_map else None,
        priority_map_json=json.dumps(payload.priority_map) if payload.priority_map else None,
        created_by_user_id=current_user.id,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return _serialize_config(config)


@router.patch("/configs/{config_id}", summary="Actualizar configuración Jira")
def patch_jira_config(
    config_id: str,
    payload: JiraConfigPatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_pm),
):
    config: Optional[JiraConfig] = db.query(JiraConfig).filter(JiraConfig.id == config_id).first()
    if not config:
        raise HTTPException(404, "Jira config not found")

    updates = payload.model_dump(exclude_none=True)
    for k, v in updates.items():
        if k == "jira_api_token":
            config.jira_api_token_enc = v
        elif k == "status_map":
            config.status_map_json = json.dumps(v)
        elif k == "priority_map":
            config.priority_map_json = json.dumps(v)
        else:
            setattr(config, k, v)

    db.commit()
    db.refresh(config)
    return _serialize_config(config)


@router.delete("/configs/{config_id}", summary="Eliminar configuración Jira")
def delete_jira_config(
    config_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_pm),
):
    enforce_abac(db, current_user, "jira_config", config_id, action="delete")
    config = db.query(JiraConfig).filter(JiraConfig.id == config_id).first()
    if not config:
        raise HTTPException(404, "Jira config not found")
    db.delete(config)
    db.commit()
    return {"deleted": True}


@router.post("/configs/{config_id}/test", summary="Probar conexión Jira")
def test_jira_connection(
    config_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_pm),
):
    """Verify credentials by calling Jira's /myself endpoint."""
    import base64
    import httpx

    config = db.query(JiraConfig).filter(JiraConfig.id == config_id).first()
    if not config:
        raise HTTPException(404, "Jira config not found")

    creds = base64.b64encode(
        f"{config.jira_email}:{config.jira_api_token_enc}".encode()
    ).decode()

    try:
        resp = httpx.get(
            f"{config.jira_base_url.rstrip('/')}/rest/api/3/myself",
            headers={"Authorization": f"Basic {creds}", "Accept": "application/json"},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return {"ok": True, "jira_account_id": data.get("accountId"), "display_name": data.get("displayName")}
    except httpx.HTTPStatusError as exc:
        return {"ok": False, "error": f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"}
    except Exception as exc:
        logger.warning("Fallo verificando cuenta Jira: %s", exc)
        return {"ok": False, "error": str(exc)}


@router.get("/configs/{config_id}/sync-log", summary="Ver log de sincronización")
def get_sync_log(
    config_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_pm),
):
    q = (
        db.query(JiraSyncLog)
        .filter(JiraSyncLog.config_id == config_id)
        .order_by(JiraSyncLog.occurred_at.desc())
    )
    total = q.count()
    logs = q.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
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
        ],
    }


@router.post("/tickets/{ticket_id}/push", summary="Empujar ticket a Jira")
def push_ticket(
    ticket_id: str,
    config_id: str = Query(..., description="Jira config ID to use"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually push or re-push a Contecflow ticket to Jira."""
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Ticket not found")

    config = db.query(JiraConfig).filter(
        JiraConfig.id == config_id, JiraConfig.is_active == True
    ).first()
    if not config:
        raise HTTPException(404, "Active Jira config not found")

    try:
        sync_map = push_ticket_to_jira(db, config, ticket)
        db.commit()
        return {
            "ok": True,
            "jira_issue_key": sync_map.jira_issue_key,
            "sync_status": sync_map.sync_status,
        }
    except Exception as exc:
        db.rollback()
        raise HTTPException(502, f"Jira push failed: {exc}") from exc


@router.post("/webhook", summary="Recibir webhook de Jira Cloud")
async def receive_jira_webhook(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    """
    Receives Jira Cloud webhooks (issue_updated, comment_created, etc.)
    and applies changes to the linked Contecflow ticket.

    Jira sends: {"webhookEvent": "jira:issue_updated", "issue": {...}}
    """
    event = payload.get("webhookEvent", "")
    issue = payload.get("issue") or {}
    issue_key = issue.get("key") or payload.get("issueKey") or ""

    if not issue_key:
        return {"ok": True, "skipped": "no issue key"}

    # Find all sync maps matching this issue key
    maps: list[JiraSyncMap] = (
        db.query(JiraSyncMap)
        .filter(JiraSyncMap.jira_issue_key == issue_key)
        .all()
    )

    if not maps:
        return {"ok": True, "skipped": "no mapping found"}

    for sm in maps:
        config = db.query(JiraConfig).filter(
            JiraConfig.id == sm.config_id, JiraConfig.is_active == True
        ).first()
        if not config:
            continue
        if config.sync_direction not in (
            JiraSyncDirection.bidirectional,
            JiraSyncDirection.jira_to_contecflow,
        ):
            continue

        jira_fields = issue.get("fields", {})
        apply_jira_update_to_ticket(db, config, sm, jira_fields)

    db.commit()
    return {"ok": True, "processed": len(maps)}


@router.post("/sync/{config_id}", summary="Sincronización incremental manual")
def run_manual_sync(
    config_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_pm),
):
    """Trigger an incremental sync poll for all mapped tickets of a config."""
    background_tasks.add_task(run_incremental_sync, db, config_id)
    return {"ok": True, "message": "Incremental sync started in background"}
