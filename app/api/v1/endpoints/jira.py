"""
jira.py — Jira bidirectional integration.

Jira Cloud REST API v3 (email + API token → HTTP Basic auth).
Credentials stored in app_settings table (keys: jira_url, jira_email, jira_api_token, jira_project_key).

Endpoints:
  GET  /jira/config                          → get current Jira config (without token)
  POST /jira/config                          → save / update Jira config
  GET  /jira/test                            → test connectivity
  GET  /jira/issues?project_key=…&max=100    → list Jira issues (proxy)
  POST /jira/sync                            → pull Jira → NexusPM  (create/update Tasks)
  POST /jira/push?project_id=…              → push NexusPM tasks → Jira (create missing issues)
  POST /jira/webhook                         → receive Jira webhook events
  GET  /jira/sync-log?limit=50              → last N sync events from app_settings audit
"""
from __future__ import annotations

import base64
import hashlib
import datetime
import json
import logging
from typing import Optional, List

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Header
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin, require_any_manager
from app.models.user import User
from app.models.settings import AppSetting
from app.models.task import Task
from app.models.project import Project
from app.services.pagination_service import paginate_query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jira", tags=["Jira Integration"])

# ── helpers ────────────────────────────────────────────────────────────────────

def _get_setting(key: str, db: Session) -> Optional[str]:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else None

def _set_setting(key: str, value: str, db: Session):
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value, description=f"Jira integration: {key}"))
    db.flush()

def _jira_headers(email: str, token: str) -> dict:
    creds = base64.b64encode(f"{email}:{token}".encode()).decode()
    return {
        "Authorization": f"Basic {creds}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

def _get_jira_config(db: Session) -> dict:
    return {
        "jira_url":         _get_setting("jira_url", db),
        "jira_email":       _get_setting("jira_email", db),
        "jira_api_token":   _get_setting("jira_api_token", db),
        "jira_project_key": _get_setting("jira_project_key", db),
    }

# Jira issue status → NexusPM task status mapping
JIRA_STATUS_MAP = {
    "to do":        "todo",
    "open":         "todo",
    "backlog":      "backlog",
    "in progress":  "in_progress",
    "in review":    "in_review",
    "done":         "done",
    "closed":       "done",
    "resolved":     "done",
    "cancelled":    "cancelled",
    "won't fix":    "cancelled",
}

JIRA_PRIORITY_MAP = {
    "blocker":   "critical",
    "critical":  "critical",
    "highest":   "critical",
    "high":      "high",
    "medium":    "medium",
    "low":       "low",
    "lowest":    "low",
    "trivial":   "low",
}

# NexusPM → Jira status mapping
NM_TO_JIRA_STATUS = {
    "backlog":     "To Do",
    "todo":        "To Do",
    "in_progress": "In Progress",
    "in_review":   "In Review",
    "done":        "Done",
    "cancelled":   "Won't Fix",
}

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
    project_key:    Optional[str] = None   # override default project key
    project_id:     Optional[str] = None   # NexusPM project to link tasks to
    max_results:    int = 100
    since_days:     int = 30               # only sync issues updated in last N days
    dry_run:        bool = False


class JiraPushIn(BaseModel):
    project_id:     str                    # NexusPM project to push
    jira_project_key: Optional[str] = None
    statuses:       List[str] = ["todo", "backlog", "in_progress", "in_review"]
    dry_run:        bool = False


# ── endpoints ──────────────────────────────────────────────────────────────────

@router.get("/config", summary="Obtener configuración Jira")
def get_jira_config(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    cfg = _get_jira_config(db)
    safe = {k: v for k, v in cfg.items() if k != "jira_api_token"}
    safe["configured"] = bool(cfg.get("jira_url") and cfg.get("jira_api_token"))
    if cfg.get("jira_api_token"):
        # Return masked token (last 4 chars)
        safe["jira_api_token_hint"] = "••••" + cfg["jira_api_token"][-4:]
    return safe


@router.post("/config", summary="Guardar configuración Jira")
def save_jira_config(
    payload: JiraConfigIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    _set_setting("jira_url",         payload.jira_url,         db)
    _set_setting("jira_email",       payload.jira_email,       db)
    _set_setting("jira_api_token",   payload.jira_api_token,   db)
    _set_setting("jira_project_key", payload.jira_project_key, db)
    db.commit()
    return {"ok": True, "message": "Configuración Jira guardada"}


@router.get("/test", summary="Test de conexión Jira")
def test_jira_connection(
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    cfg = _get_jira_config(db)
    if not cfg["jira_url"] or not cfg["jira_api_token"]:
        raise HTTPException(400, "Jira no configurado. Ve a /jira/config primero.")
    try:
        resp = httpx.get(
            f"{cfg['jira_url']}/rest/api/3/myself",
            headers=_jira_headers(cfg["jira_email"], cfg["jira_api_token"]),
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "ok": True,
            "jira_url": cfg["jira_url"],
            "account_id": data.get("accountId"),
            "display_name": data.get("displayName"),
            "email": data.get("emailAddress"),
        }
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"Jira devolvió {e.response.status_code}: {e.response.text[:200]}")
    except Exception as e:
        raise HTTPException(502, f"No se pudo conectar con Jira: {str(e)[:200]}")


@router.get("/issues", summary="Listar issues Jira (proxy)")
def list_jira_issues(
    project_key: Optional[str] = Query(None),
    max_results: int = Query(50, le=200),
    jql: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    cfg = _get_jira_config(db)
    if not cfg["jira_url"] or not cfg["jira_api_token"]:
        raise HTTPException(400, "Jira no configurado.")
    key = project_key or cfg["jira_project_key"]
    if not key and not jql:
        raise HTTPException(400, "Proporciona project_key o un jql personalizado.")

    query = jql or f"project = {key} ORDER BY updated DESC"
    try:
        resp = httpx.post(
            f"{cfg['jira_url']}/rest/api/3/issue/search",
            headers=_jira_headers(cfg["jira_email"], cfg["jira_api_token"]),
            json={"jql": query, "maxResults": max_results,
                  "fields": ["summary", "status", "priority", "assignee", "description",
                              "created", "updated", "duedate", "issuetype", "labels", "subtasks"]},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
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
        return {"total": data.get("total", 0), "issues": issues}
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"Jira {e.response.status_code}: {e.response.text[:200]}")
    except Exception as e:
        raise HTTPException(502, f"Error Jira: {str(e)[:200]}")


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
    cfg = _get_jira_config(db)
    if not cfg["jira_url"] or not cfg["jira_api_token"]:
        raise HTTPException(400, "Jira no configurado.")

    key = payload.project_key or cfg["jira_project_key"]
    if not key:
        raise HTTPException(400, "Proporciona project_key.")

    cutoff = (datetime.datetime.utcnow() - datetime.timedelta(days=payload.since_days)).strftime("%Y-%m-%d")
    jql = f"project = {key} AND updated >= '{cutoff}' ORDER BY updated DESC"
    max_results = min(payload.max_results, 200)

    try:
        resp = httpx.post(
            f"{cfg['jira_url']}/rest/api/3/issue/search",
            headers=_jira_headers(cfg["jira_email"], cfg["jira_api_token"]),
            json={"jql": jql, "maxResults": max_results,
                  "fields": ["summary", "status", "priority", "description", "duedate",
                              "assignee", "issuetype", "labels", "subtasks"]},
            timeout=20,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"Jira {e.response.status_code}: {e.response.text[:200]}")
    except Exception as e:
        raise HTTPException(502, f"Error Jira: {str(e)[:200]}")

    issues = resp.json().get("issues", [])
    created = updated = skipped = 0

    for iss in issues:
        f = iss.get("fields", {})
        jira_key = iss["key"]
        jira_id  = iss["id"]
        title    = f.get("summary") or jira_key
        raw_status   = (f.get("status", {}).get("name") or "").lower()
        raw_priority = (f.get("priority", {}).get("name") or "").lower()
        nm_status    = JIRA_STATUS_MAP.get(raw_status, "todo")
        nm_priority  = JIRA_PRIORITY_MAP.get(raw_priority, "medium")
        due_date     = f.get("duedate")

        # Description: Jira uses Atlassian Document Format (ADF) — extract plain text
        desc_adf = f.get("description")
        desc_text = None
        if desc_adf and isinstance(desc_adf, dict):
            # Best-effort plain text extraction from ADF
            parts = []
            def _extract_text(node):
                if isinstance(node, dict):
                    if node.get("type") == "text":
                        parts.append(node.get("text", ""))
                    for child in node.get("content", []):
                        _extract_text(child)
            _extract_text(desc_adf)
            desc_text = " ".join(parts).strip() or None

        # Find existing task by jira_issue_key
        existing = db.query(Task).filter(Task.jira_issue_key == jira_key).first()

        if existing:
            if not payload.dry_run:
                existing.status         = nm_status
                existing.priority       = nm_priority
                existing.jira_issue_id  = jira_id
                existing.jira_synced_at = datetime.datetime.now(datetime.timezone.utc)
                if due_date:
                    existing.due_date = due_date
            updated += 1
        else:
            if not payload.dry_run:
                task = Task(
                    title=title,
                    description=desc_text,
                    status=nm_status,
                    priority=nm_priority,
                    due_date=due_date,
                    project_id=payload.project_id,
                    jira_issue_key=jira_key,
                    jira_issue_id=jira_id,
                    jira_synced_at=datetime.datetime.now(datetime.timezone.utc),
                    created_by_user_id=current_user.id,
                )
                db.add(task)
            created += 1

    if not payload.dry_run:
        db.commit()

    return {
        "ok": True,
        "dry_run": payload.dry_run,
        "issues_fetched": len(issues),
        "created": created,
        "updated": updated,
        "skipped": skipped,
    }


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
    cfg = _get_jira_config(db)
    if not cfg["jira_url"] or not cfg["jira_api_token"]:
        raise HTTPException(400, "Jira no configurado.")

    proj_key = payload.jira_project_key or cfg["jira_project_key"]
    if not proj_key:
        raise HTTPException(400, "Proporciona jira_project_key.")

    tasks = (
        db.query(Task)
        .filter(
            Task.project_id == payload.project_id,
            Task.status.in_(payload.statuses),
            Task.jira_issue_key == None,  # noqa: E711
        )
        .all()
    )

    NEXUS_PRIORITY_TO_JIRA = {"critical": "Highest", "high": "High", "medium": "Medium", "low": "Low", "none": "Medium"}
    created = skipped = errors = 0
    errs = []

    for task in tasks:
        jira_payload = {
            "fields": {
                "project": {"key": proj_key},
                "summary": task.title,
                "issuetype": {"name": "Task"},
                "priority": {"name": NEXUS_PRIORITY_TO_JIRA.get(task.priority or "medium", "Medium")},
            }
        }
        if task.description:
            jira_payload["fields"]["description"] = {
                "type": "doc", "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": task.description}]}]
            }
        if task.due_date:
            jira_payload["fields"]["duedate"] = str(task.due_date)

        if payload.dry_run:
            created += 1
            continue

        try:
            resp = httpx.post(
                f"{cfg['jira_url']}/rest/api/3/issue",
                headers=_jira_headers(cfg["jira_email"], cfg["jira_api_token"]),
                json=jira_payload,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            task.jira_issue_key = data["key"]
            task.jira_issue_id  = data["id"]
            task.jira_synced_at = datetime.datetime.now(datetime.timezone.utc)
            created += 1
        except Exception as e:
            errors += 1
            errs.append({"task_id": task.id, "error": str(e)[:100]})

    if not payload.dry_run:
        db.commit()

    return {
        "ok": True,
        "dry_run": payload.dry_run,
        "tasks_evaluated": len(tasks),
        "created": created,
        "skipped": skipped,
        "errors": errors,
        "error_details": errs[:10],
    }


@router.post("/webhook", summary="Recibir eventos Jira (issue:updated / issue:created)")
def jira_webhook(
    payload: dict,
    x_atlassian_token: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """
    Jira sends webhooks on issue events. This endpoint:
    - Updates NexusPM task status / priority when a Jira issue changes
    - Marks tasks as done when Jira issue is resolved/closed
    """
    event = payload.get("webhookEvent", "")
    issue = payload.get("issue", {})
    if not issue:
        return {"ok": True, "ignored": True}

    jira_key = issue.get("key")
    if not jira_key:
        return {"ok": True, "ignored": True}

    fields = issue.get("fields", {})
    raw_status   = (fields.get("status", {}).get("name") or "").lower()
    raw_priority = (fields.get("priority", {}).get("name") or "").lower()

    nm_status   = JIRA_STATUS_MAP.get(raw_status)
    nm_priority = JIRA_PRIORITY_MAP.get(raw_priority)

    task = db.query(Task).filter(Task.jira_issue_key == jira_key).first()
    if not task:
        return {"ok": True, "message": f"No task linked to {jira_key}"}

    changed = False
    if nm_status and task.status != nm_status:
        task.status = nm_status
        changed = True
    if nm_priority and task.priority != nm_priority:
        task.priority = nm_priority
        changed = True
    if event in ("jira:issue_deleted",):
        task.jira_issue_key = None
        task.jira_issue_id  = None
        changed = True
    if changed:
        task.jira_synced_at = datetime.datetime.now(datetime.timezone.utc)
        db.commit()

    return {"ok": True, "jira_key": jira_key, "updated": changed}


@router.get("/linked", summary="Tareas NexusPM vinculadas a Jira")
def get_linked_tasks(
    project_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(require_any_manager),
):
    q = db.query(Task).filter(Task.jira_issue_key != None)  # noqa: E711
    if project_id:
        q = q.filter(Task.project_id == project_id)
    tasks, _, _ = paginate_query(q.order_by(Task.updated_at.desc()), page, page_size)
    return [
        {
            "id": t.id, "title": t.title, "status": t.status,
            "jira_issue_key": t.jira_issue_key,
            "jira_issue_url": f"{_get_setting('jira_url', db)}/browse/{t.jira_issue_key}" if t.jira_issue_key else None,
            "jira_synced_at": t.jira_synced_at.isoformat() if t.jira_synced_at else None,
        }
        for t in tasks
    ]
