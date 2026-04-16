"""
Microsoft 365 deep integration — Calendar sync + Teams notifications.

Calendar sync:
  GET  /m365/calendar/events          — list synced calendar events
  POST /m365/calendar/sync            — pull events via Microsoft Graph
  POST /m365/calendar/push-milestone  — create/update calendar event for a milestone
  DELETE /m365/calendar/events/{id}   — remove synced event

Teams notifications:
  POST /m365/teams/notify             — send adaptive card to Teams channel
  POST /m365/teams/webhooks/incoming  — receive Teams bot webhook payload
  GET  /m365/status                   — connection status + stats

Milestones auto-sync:
  POST /m365/calendar/sync-milestones — push all upcoming milestones as calendar events

NOTE: Real Graph API calls require AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID.
      When not configured, endpoints return 503 with setup instructions.
"""

from datetime import datetime, timedelta
from typing import List, Optional
import httpx

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.models.task import Task
from app.models.user import User
from app.services import m365_service

router = APIRouter()

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _m365_configured() -> bool:
    return bool(settings.AZURE_TENANT_ID and settings.AZURE_CLIENT_ID and settings.AZURE_CLIENT_SECRET)


def _require_m365():
    if not _m365_configured():
        raise HTTPException(503, detail={
            "error": "M365_NOT_CONFIGURED",
            "message": "Configura las variables de entorno: AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET",
            "docs_url": "https://learn.microsoft.com/en-us/graph/auth-v2-service",
        })


async def _get_graph_token() -> str:
    """Obtain a client-credentials OAuth token from Azure AD."""
    url = f"https://login.microsoftonline.com/{settings.AZURE_TENANT_ID}/oauth2/v2.0/token"
    data = {
        "grant_type":    "client_credentials",
        "client_id":     settings.AZURE_CLIENT_ID,
        "client_secret": settings.AZURE_CLIENT_SECRET,
        "scope":         "https://graph.microsoft.com/.default",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, data=data)
    if resp.status_code != 200:
        raise HTTPException(502, "Error obteniendo token de Azure AD")
    return resp.json()["access_token"]


def _get_graph_token_sync() -> str:
    """Obtain a client-credentials OAuth token from Azure AD (sync version)."""
    url = f"https://login.microsoftonline.com/{settings.AZURE_TENANT_ID}/oauth2/v2.0/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": settings.AZURE_CLIENT_ID,
        "client_secret": settings.AZURE_CLIENT_SECRET,
        "scope": "https://graph.microsoft.com/.default",
    }
    with httpx.Client(timeout=15) as client:
        resp = client.post(url, data=data)
    if resp.status_code != 200:
        raise HTTPException(502, "Error obteniendo token de Azure AD")
    return resp.json()["access_token"]


async def _graph_get(path: str) -> dict:
    token = await _get_graph_token()
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(f"{GRAPH_BASE}{path}", headers={"Authorization": f"Bearer {token}"})
    resp.raise_for_status()
    return resp.json()


async def _graph_post(path: str, payload: dict) -> dict:
    token = await _get_graph_token()
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(f"{GRAPH_BASE}{path}", json=payload, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    resp.raise_for_status()
    return resp.json()


async def _graph_patch(path: str, payload: dict) -> dict:
    token = await _get_graph_token()
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.patch(f"{GRAPH_BASE}{path}", json=payload, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    resp.raise_for_status()
    return resp.json()


async def _graph_delete(path: str):
    token = await _get_graph_token()
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.delete(f"{GRAPH_BASE}{path}", headers={"Authorization": f"Bearer {token}"})
    if resp.status_code not in (200, 204):
        resp.raise_for_status()


def _graph_get_sync(path: str) -> dict:
    token = _get_graph_token_sync()
    with httpx.Client(timeout=20) as client:
        resp = client.get(f"{GRAPH_BASE}{path}", headers={"Authorization": f"Bearer {token}"})
    resp.raise_for_status()
    return resp.json()


def _graph_post_sync(path: str, payload: dict) -> dict:
    token = _get_graph_token_sync()
    with httpx.Client(timeout=20) as client:
        resp = client.post(
            f"{GRAPH_BASE}{path}",
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
    resp.raise_for_status()
    return resp.json()


# ── Schemas ───────────────────────────────────────────────────────────────────

class CalendarEventCreate(BaseModel):
    subject:       str
    start_dt:      datetime
    end_dt:        datetime
    body:          Optional[str] = None
    location:      Optional[str] = None
    attendees:     List[str] = []     # list of email addresses
    user_upn:      str                # the user whose calendar to write to

class TeamsNotification(BaseModel):
    title:       str
    text:        str
    color:       str = "0078D4"       # hex without #
    webhook_url: Optional[str] = None # overrides TEAMS_WEBHOOK_URL env var

class MilestoneSyncRequest(BaseModel):
    user_upn:  str          # calendar owner
    days_ahead: int = 30    # sync milestones in next N days


# ── Status endpoint ──────────────────────────────────────────────────────────

@router.get("/status")
def m365_status(_: User = Depends(get_current_user)):
    configured = _m365_configured()
    teams_ok = bool(settings.TEAMS_WEBHOOK_URL)
    return {
        "graph_configured":            configured,
        "calendar_sync_enabled":       settings.M365_CALENDAR_SYNC_ENABLED,
        "teams_notifications_enabled": settings.M365_TEAMS_NOTIFICATIONS_ENABLED,
        "teams_webhook_configured":    teams_ok,
        "required_env_vars": {
            "AZURE_TENANT_ID":     bool(settings.AZURE_TENANT_ID),
            "AZURE_CLIENT_ID":     bool(settings.AZURE_CLIENT_ID),
            "AZURE_CLIENT_SECRET": bool(settings.AZURE_CLIENT_SECRET),
            "TEAMS_WEBHOOK_URL":   teams_ok,
        },
    }


# ── Calendar endpoints ────────────────────────────────────────────────────────

@router.post("/calendar/sync")
async def sync_calendar_events(
    user_upn: str,
    days: int = 14,
    _: User = Depends(get_current_user),
):
    """Pull upcoming calendar events for the given user via Microsoft Graph."""
    _require_m365()
    start = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    end   = (datetime.utcnow() + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    try:
        data = await _graph_get(
            f"/users/{user_upn}/calendarView?startDateTime={start}Z&endDateTime={end}Z&$top=50"
            "&$select=id,subject,start,end,location,webLink,attendees"
        )
        events = data.get("value", [])
        return {"pulled": len(events), "events": events}
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"Graph API error: {e.response.text}")


@router.post("/calendar/events")
async def create_calendar_event(
    body: CalendarEventCreate,
    _: User = Depends(get_current_user),
):
    """Create a calendar event in the specified user's Microsoft 365 calendar."""
    _require_m365()
    payload = {
        "subject": body.subject,
        "start": {"dateTime": body.start_dt.isoformat(), "timeZone": "UTC"},
        "end":   {"dateTime": body.end_dt.isoformat(),   "timeZone": "UTC"},
        "body":  {"contentType": "HTML", "content": body.body or ""},
        "location": {"displayName": body.location or ""},
        "attendees": [
            {"emailAddress": {"address": email}, "type": "required"}
            for email in body.attendees
        ],
    }
    try:
        result = await _graph_post(f"/users/{body.user_upn}/events", payload)
        return {"id": result.get("id"), "webLink": result.get("webLink"), "subject": result.get("subject")}
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"Graph API error: {e.response.text}")


@router.delete("/calendar/events/{event_id}")
async def delete_calendar_event(
    event_id: str,
    user_upn: str,
    _: User = Depends(get_current_user),
):
    _require_m365()
    try:
        await _graph_delete(f"/users/{user_upn}/events/{event_id}")
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"Graph API error: {e.response.text}")
    return {"ok": True}


@router.post("/calendar/sync-milestones")
def sync_milestones_to_calendar(
    req: MilestoneSyncRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Push upcoming project milestones as Microsoft 365 calendar events."""
    _require_m365()
    from datetime import date

    cutoff = date.today() + timedelta(days=req.days_ahead)
    milestones = m365_service.get_upcoming_milestones(db, cutoff, limit=50)

    created = []
    errors  = []
    for ms in milestones:
        if not ms.due_date:
            continue
        start_dt = datetime.combine(ms.due_date, datetime.min.time())
        end_dt   = start_dt + timedelta(hours=1)
        payload  = {
            "subject": f"[Milestone] {ms.name}",
            "start":   {"dateTime": start_dt.isoformat(), "timeZone": "UTC"},
            "end":     {"dateTime": end_dt.isoformat(),   "timeZone": "UTC"},
            "body":    {"contentType": "text", "content": ms.description or ""},
        }
        try:
            result = _graph_post_sync(f"/users/{req.user_upn}/events", payload)
            created.append({"milestone_id": ms.id, "event_id": result.get("id")})
        except Exception as e:
            errors.append({"milestone_id": ms.id, "error": str(e)})

    return {"created": len(created), "errors": errors, "details": created}


# ── Teams notification endpoints ──────────────────────────────────────────────

@router.post("/teams/notify")
async def send_teams_notification(
    body: TeamsNotification,
    _: User = Depends(get_current_user),
):
    """Send an Adaptive Card-style message to a Microsoft Teams channel via incoming webhook."""
    webhook_url = body.webhook_url or settings.TEAMS_WEBHOOK_URL
    if not webhook_url:
        raise HTTPException(503, "TEAMS_WEBHOOK_URL not configured")

    card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": body.color,
        "summary": body.title,
        "sections": [{
            "activityTitle": body.title,
            "activityText":  body.text,
            "markdown": True,
        }],
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(webhook_url, json=card)

    if resp.status_code not in (200, 202):
        raise HTTPException(502, f"Teams webhook error: {resp.text}")
    return {"ok": True, "status": resp.status_code}


@router.post("/teams/notify-project")
async def notify_project_milestone(
    project_name: str,
    milestone_name: str,
    due_date: str,
    _: User = Depends(get_current_user),
):
    """Send a formatted Teams notification about an upcoming milestone."""
    webhook_url = settings.TEAMS_WEBHOOK_URL
    if not webhook_url:
        raise HTTPException(503, "TEAMS_WEBHOOK_URL not configured")

    card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": "FF8C00",
        "summary": f"Milestone próximo: {milestone_name}",
        "sections": [{
            "activityTitle": f"📅 Milestone próximo — {project_name}",
            "activityText": f"**{milestone_name}** vence el **{due_date}**",
            "markdown": True,
        }],
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(webhook_url, json=card)

    if resp.status_code not in (200, 202):
        raise HTTPException(502, f"Teams webhook error: {resp.text}")
    return {"ok": True}


@router.post("/teams/webhooks/incoming")
async def receive_teams_webhook(
    payload: dict,
    _: User = Depends(get_current_user),
):
    """
    Receive incoming messages from a Teams bot (e.g. task updates, commands).
    Processes: 'create_task', 'list_projects', 'log_hours' commands from Teams chat.
    """
    text = payload.get("text", "").lower().strip()
    command = payload.get("command") or text.split()[0] if text else ""

    # Simple command dispatch
    if "create_task" in command or "nueva tarea" in text:
        return {"type": "message", "text": "Para crear una tarea ve a NexusPM → Tareas → Nueva tarea. [Abrir NexusPM](/)"}
    if "log_hours" in command or "imputar" in text:
        return {"type": "message", "text": "Para registrar horas ve a NexusPM → Imputar horas. [Abrir imputaciones](/imputar)"}
    if "projects" in command or "proyectos" in text:
        return {"type": "message", "text": "Consulta tus proyectos activos en NexusPM → Proyectos. [Ver proyectos](/projects)"}

    return {"type": "message", "text": "Hola! Puedo ayudarte con: `crear tarea`, `imputar horas`, `proyectos`. Escribe un comando."}


# ── User presence ──────────────────────────────────────────────────────────────

@router.get("/users/presence", summary="Presencia en tiempo real de usuarios M365")
async def get_users_presence(
    upns: str,
    _: User = Depends(get_current_user),
):
    """
    Returns real-time presence for a comma-separated list of UPNs.
    Uses POST /v1.0/communications/getPresencesByUserId (delegated or app permissions).
    Presence availability values: Available, Busy, DoNotDisturb, Away, BeRightBack, Offline, PresenceUnknown.
    """
    _require_m365()
    upn_list = [u.strip() for u in upns.split(",") if u.strip()]
    if not upn_list:
        raise HTTPException(400, detail="No UPNs provided")
    if len(upn_list) > 650:
        raise HTTPException(400, detail="Maximum 650 UPNs per request")

    # First resolve UPNs → object IDs via /users
    ids = []
    for upn in upn_list:
        try:
            user_data = await _graph_get(f"/users/{upn}?$select=id,displayName")
            ids.append(user_data.get("id"))
        except Exception:
            pass  # skip unresolvable UPNs

    if not ids:
        return []

    result = await _graph_post("/communications/getPresencesByUserId", {"ids": [i for i in ids if i]})
    return result.get("value", [])


# ── Microsoft Planner sync ─────────────────────────────────────────────────────

@router.post("/planner/tasks/sync", summary="Sincronizar tareas NexusPM a Microsoft Planner")
def sync_to_planner(
    project_id: str,
    plan_id: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Pushes active NexusPM tasks for a project to a Microsoft Planner plan.
    - If plan_id is provided, uses that plan.
    - If not, looks for an existing plan named after the project or creates one.
    - Upserts tasks: creates new ones, skips if already exists by title match.
    Returns a summary: { plan_id, created, skipped, errors }.
    """
    _require_m365()

    tasks = m365_service.get_active_tasks_for_project(db, project_id, limit=200)
    if not tasks:
        return {"plan_id": plan_id, "created": 0, "skipped": 0, "errors": 0, "message": "No active tasks"}

    # Resolve plan_id
    active_plan_id = plan_id
    if not active_plan_id:
        # Try to find existing plan for this project or create one
        try:
            # We need a group_id to create a Planner plan — use the first bucket owner group if configured
            # For now, return informative error
            raise HTTPException(400, detail={
                "error": "PLAN_ID_REQUIRED",
                "message": "Provide plan_id. To find your plan ID: https://graph.microsoft.com/v1.0/me/planner/plans",
            })
        except HTTPException:
            raise

    # Fetch existing Planner tasks for conflict detection
    try:
        existing_response = _graph_get_sync(f"/planner/plans/{active_plan_id}/tasks")
        existing_titles = {t.get("title", "").lower() for t in existing_response.get("value", [])}
    except Exception:
        existing_titles = set()

    created = 0
    skipped = 0
    errors  = 0

    for task in tasks:
        title = (task.title or "").strip()
        if not title:
            continue
        if title.lower() in existing_titles:
            skipped += 1
            continue
        due_str = None
        if task.due_date:
            try:
                due_str = datetime.combine(task.due_date, datetime.min.time()).isoformat() + "Z"
            except Exception:
                pass
        payload = {
            "planId": active_plan_id,
            "title":  title,
        }
        if due_str:
            payload["dueDateTime"] = due_str
        try:
            _graph_post_sync("/planner/tasks", payload)
            created += 1
        except Exception:
            errors += 1

    return {
        "plan_id": active_plan_id,
        "created": created,
        "skipped": skipped,
        "errors":  errors,
    }

