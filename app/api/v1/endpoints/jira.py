"""
jira.py — Jira bidirectional integration.

Jira Cloud REST API v3 (email + API token → HTTP Basic auth).

Auditoria 2026-11 (#34): rutas finas sobre `services/jira_service.py`, la unica
capa de Jira. La configuracion es la conexion `usar_para_tareas` de la
organizacion en `sd_jira_configs` (antes, cuatro `app_settings`).

Endpoints:
  GET  /jira/config                          → get current Jira config (without token)
  POST /jira/config                          → save / update Jira config
  GET  /jira/test                            → test connectivity
  GET  /jira/issues?project_key=…&max=100    → list Jira issues (proxy)
  POST /jira/sync                            → pull Jira → NexusPM  (create/update Tasks)
  POST /jira/push?project_id=…              → push NexusPM tasks → Jira (create missing issues)
  POST /jira/webhook                         → receive Jira webhook events
  POST /jira/webhook-secret                  → generar/rotar el secreto del webhook
  GET  /jira/linked                          → tareas enlazadas
"""
from __future__ import annotations

import datetime
import json
from app.core.timeutil import utcnow
import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Header, Request
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.deps import require_admin, require_any_manager
from app.core.responses import APIListResponse, APIResponse
from app.models.user import User
from app.services.pagination_service import paginate_query
from app.services import jira_service
from app.services.jira_service import JIRA_STATUS_MAP, JIRA_PRIORITY_MAP

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Jira Integration"])

# ── schemas ────────────────────────────────────────────────────────────────────

class JiraConfigIn(BaseModel):
    jira_url:         str
    jira_email:       str
    jira_api_token:   str
    jira_project_key: str

    @field_validator("jira_url")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")


class JiraSyncIn(BaseModel):
    project_key:    Optional[str] = None
    project_id:     Optional[str] = None
    max_results:    int = 100
    since_days:     int = 30
    dry_run:        bool = False


class JiraPushIn(BaseModel):
    project_id:       str
    jira_project_key: Optional[str] = None
    statuses:         List[str] = ["todo", "backlog", "in_progress", "in_review"]
    dry_run:          bool = False


# ── endpoints ──────────────────────────────────────────────────────────────────

@router.get("/config", summary="Obtener configuración Jira")
def get_jira_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    cfg = jira_service.get_jira_config(db, current_user.organization_id)
    safe = {k: v for k, v in cfg.items() if k != "jira_api_token"}
    safe["configured"] = bool(cfg.get("jira_url") and cfg.get("jira_api_token"))
    if cfg.get("jira_api_token"):
        safe["jira_api_token_hint"] = "••••" + cfg["jira_api_token"][-4:]
    return APIResponse.ok(data=safe)


@router.post("/config", summary="Guardar configuración Jira")
def save_jira_config(
    payload: JiraConfigIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    jira_service.save_jira_config(
        db,
        org_id=current_user.organization_id,
        jira_url=payload.jira_url,
        jira_email=payload.jira_email,
        jira_api_token=payload.jira_api_token,
        jira_project_key=payload.jira_project_key,
    )
    return APIResponse.ok(data={"ok": True, "message": "Configuración Jira guardada"})


@router.get("/test", summary="Test de conexión Jira")
def test_jira_connection(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    cfg = jira_service.get_jira_config(db, current_user.organization_id)
    # Auditoria 2026-11 (#34): la misma prueba que `/integrations/jira/configs/{id}/test`.
    return APIResponse.ok(data={"jira_url": cfg["jira_url"], **jira_service.probar_conexion(cfg)})


@router.get("/issues", summary="Listar issues Jira (proxy)")
def list_jira_issues(
    project_key: Optional[str] = Query(None),
    max_results: int = Query(50, le=200),
    jql: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    cfg = jira_service.get_jira_config(db, current_user.organization_id)
    if not cfg["jira_url"] or not cfg["jira_api_token"]:
        raise HTTPException(400, "Jira no configurado.")
    key = project_key or cfg["jira_project_key"]
    if not key and not jql:
        raise HTTPException(400, "Proporciona project_key o un jql personalizado.")

    query = jql or f"project = {key} ORDER BY updated DESC"
    data = jira_service.llamar_a_jira(cfg, "POST", "/rest/api/3/issue/search", timeout=15, json={
        "jql": query, "maxResults": max_results,
        "fields": ["summary", "status", "priority", "assignee", "description",
                   "created", "updated", "duedate", "issuetype", "labels", "subtasks"]})
    issues = []
    for iss in data.get("issues", []):
        f = iss.get("fields", {})
        issues.append({
            "key": iss["key"],
            "id": iss["id"],
            "summary": f.get("summary"),
            "status": f.get("status", {}).get("name"),
            "priority": f.get("priority", {}).get("name"),
            "assignee": f.get("assignee", {}).get("displayName") if f.get("assignee") else None,
            "due_date": f.get("duedate"),
            "issue_type": f.get("issuetype", {}).get("name"),
            "labels": f.get("labels", []),
            "updated": f.get("updated"),
        })
    return APIResponse.ok(data={"total": data.get("total", 0), "issues": issues})


@router.post("/sync", summary="Jira → NexusPM: importar / actualizar tareas")
def sync_jira_to_nexus(
    payload: JiraSyncIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """
    Pulls issues from Jira and creates or updates corresponding NexusPM Tasks.
    Matching is done by jira_issue_key on the Task model.
    """
    cfg = jira_service.get_jira_config(db, current_user.organization_id)
    if not cfg["jira_url"] or not cfg["jira_api_token"]:
        raise HTTPException(400, "Jira no configurado.")

    key = payload.project_key or cfg["jira_project_key"]
    if not key:
        raise HTTPException(400, "Proporciona project_key.")

    cutoff = (utcnow() - datetime.timedelta(days=payload.since_days)).strftime("%Y-%m-%d")
    jql = f"project = {key} AND updated >= '{cutoff}' ORDER BY updated DESC"
    max_results = min(payload.max_results, 200)

    data = jira_service.llamar_a_jira(cfg, "POST", "/rest/api/3/issue/search", timeout=20, json={
        "jql": jql, "maxResults": max_results,
        "fields": ["summary", "status", "priority", "description", "duedate",
                   "assignee", "issuetype", "labels", "subtasks"]})

    issues = data.get("issues", [])
    stats = jira_service.sync_jira_issues(
        db,
        issues=issues,
        project_id=payload.project_id,
        current_user_id=current_user.id,
        dry_run=payload.dry_run,
        org_id=current_user.organization_id,
    )

    return APIResponse.ok(data={
        "ok": True,
        "dry_run": payload.dry_run,
        "issues_fetched": len(issues),
        **stats,
    })


@router.post("/push", summary="NexusPM → Jira: crear issues para tareas no vinculadas")
def push_nexus_to_jira(
    payload: JiraPushIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """
    For each NexusPM task in the project that has no jira_issue_key,
    creates a new Jira issue and stores the returned key back on the task.
    """
    cfg = jira_service.get_jira_config(db, current_user.organization_id)
    if not cfg["jira_url"] or not cfg["jira_api_token"]:
        raise HTTPException(400, "Jira no configurado.")

    proj_key = payload.jira_project_key or cfg["jira_project_key"]
    if not proj_key:
        raise HTTPException(400, "Proporciona jira_project_key.")

    # Segunda auditoria 2026-11 (n.º 20): una llamada a Jira (15 s) por tarea
    # iba dentro de la peticion. Ahora va al worker; con cola: 202
    # `{status: "queued"}`. `dry_run` no llama a Jira y sigue siendo sincrono
    # (es la vista previa). Sin cola, como siempre.
    from app.core.segundo_plano import EN_COLA, encolar, respuesta_en_cola
    argumentos = dict(project_id=payload.project_id, statuses=list(payload.statuses),
                      jira_project_key=proj_key, org_id=current_user.organization_id)
    if payload.dry_run:
        return APIResponse.ok(data=jira_service.empujar_tareas_a_jira(db, dry_run=True, **argumentos))
    resultado = encolar(jira_service.empujar_tareas_a_jira, **argumentos, _sesion=db)
    if resultado is EN_COLA:
        return respuesta_en_cola(dry_run=False)
    return APIResponse.ok(data=resultado)


@router.post("/webhook-secret", summary="Generar (o rotar) el secreto del webhook Jira de la organización")
def rotate_jira_webhook_secret(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """El secreto se muestra UNA vez. Jira debe enviarlo en `X-Atlassian-Webhook-Token`
    (o firmar el cuerpo con él en `X-Hub-Signature-256`)."""
    secreto = jira_service.generar_secreto_de_webhook(db, current_user.organization_id)
    # Revisión GRC 2026-11b: rotar el secreto invalida el webhook en curso y no
    # dejaba rastro. El valor nunca se registra.
    from app.services.audit import auditar_y_confirmar
    auditar_y_confirmar(db, current_user, "SECRET_ROTATED", "jira_webhook_secret", current_user.organization_id)
    return APIResponse.ok(data={
        "secret": secreto,
        "header": "X-Atlassian-Webhook-Token",
        "webhook_paths": [f"/api/v1/jira/webhook?org={current_user.organization_id}",
                          f"/api/v1/integrations/jira/webhook?org={current_user.organization_id}"],
    })


@router.post("/webhook", summary="Recibir eventos Jira (issue:updated / issue:created)")
async def jira_webhook(
    request: Request,
    x_atlassian_webhook_token: Optional[str] = Header(None),
    x_hub_signature_256: Optional[str] = Header(None),
    org: Optional[str] = Query(None, description="Organización (solo acota; autentica el secreto)"),
    db: Session = Depends(get_db),
):
    """
    Jira sends webhooks on issue events. This endpoint:
    - Updates NexusPM task status / priority when a Jira issue changes
    - Marks tasks as done when Jira issue is resolved/closed

    Auditoria 2026-11 (#14): autentica el secreto de webhook DE UNA
    organizacion (`POST /jira/webhook-secret`), y solo toca tareas de esa
    organizacion. El `JIRA_WEBHOOK_SECRET` global ya no autentica.
    """
    from app.core.async_db import run_db

    body = await request.body()
    org_id = await run_db(jira_service.organizacion_del_webhook, db, body,
                          x_atlassian_webhook_token, x_hub_signature_256, org)
    if not org_id:
        logger.warning("Jira webhook rejected: invalid/missing authentication token")
        raise HTTPException(403, "Invalid Jira webhook authentication")

    try:
        payload = json.loads(body or b"{}")
    except (ValueError, TypeError):
        raise HTTPException(400, "Invalid JSON payload")

    event = payload.get("webhookEvent", "")
    issue = payload.get("issue", {})
    if not issue:
        return {"ok": True, "ignored": True}

    jira_key = issue.get("key")
    if not jira_key:
        return {"ok": True, "ignored": True}

    # Async handler (awaits raw body for auth) → offload blocking ORM to threadpool.
    return await run_db(_process_legacy_jira_webhook_sync, db, issue, jira_key, event, org_id)


def _process_legacy_jira_webhook_sync(db: Session, issue: dict, jira_key: str, event: str,
                                      org_id: Optional[str] = None) -> dict:
    fields       = issue.get("fields", {})
    raw_status   = (fields.get("status", {}).get("name") or "").lower()
    raw_priority = (fields.get("priority", {}).get("name") or "").lower()
    nm_status    = JIRA_STATUS_MAP.get(raw_status)
    nm_priority  = JIRA_PRIORITY_MAP.get(raw_priority)

    task = jira_service.get_task_by_jira_key(db, jira_key, org_id)
    if not task:
        return {"ok": True, "message": f"No task linked to {jira_key}"}

    changed = jira_service.update_task_from_webhook(db, task, nm_status, nm_priority, event)
    return {"ok": True, "jira_key": jira_key, "updated": changed}


@router.get("/linked", summary="Tareas NexusPM vinculadas a Jira")
def get_linked_tasks(
    project_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    q = jira_service.get_linked_tasks_query(db, project_id, org_id=current_user.organization_id)
    from app.models.task import Task as TaskModel
    tasks, _, _ = paginate_query(q.order_by(TaskModel.updated_at.desc()), page, page_size)
    jira_url = jira_service.get_jira_config(db, current_user.organization_id)["jira_url"]
    items = [
        {
            "id": t.id, "title": t.title, "status": t.status,
            "jira_issue_key": t.jira_issue_key,
            "jira_issue_url": f"{jira_url}/browse/{t.jira_issue_key}" if t.jira_issue_key else None,
            "jira_synced_at": t.jira_synced_at.isoformat() if t.jira_synced_at else None,
        }
        for t in tasks
    ]
    return APIListResponse.ok(items=items, page=page, page_size=page_size)
