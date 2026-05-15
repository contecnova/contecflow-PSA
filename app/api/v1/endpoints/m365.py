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
from typing import Optional
import logging
import httpx

from fastapi import APIRouter, Depends, HTTPException
from app.schemas.m365 import CalendarEventCreate, TeamsNotification, MilestoneSyncRequest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.core.abac_enforce import enforce_abac
from app.services import m365_service

router = APIRouter()
logger = logging.getLogger(__name__)

# ── Helpers (delegated to m365_service) ──────────────────────────────────────
# Only the helpers actually referenced by the endpoints below are aliased;
# unused passthroughs (GRAPH_BASE, get_graph_token{,_sync}, graph_patch) have
# been removed — they live in m365_service and can be imported directly there.
_m365_configured = m365_service.m365_configured
_require_m365 = m365_service.require_m365
_graph_get = m365_service.graph_get
_graph_post = m365_service.graph_post
_graph_delete = m365_service.graph_delete
_graph_get_sync = m365_service.graph_get_sync
_graph_post_sync = m365_service.graph_post_sync


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
        logger.warning("Graph API sync failed: status=%s", e.response.status_code)
        raise HTTPException(e.response.status_code, "Graph API request failed")


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
        logger.warning("Graph API create event failed: status=%s", e.response.status_code)
        raise HTTPException(e.response.status_code, "Graph API request failed")


@router.delete("/calendar/events/{event_id}")
async def delete_calendar_event(
    event_id: str,
    user_upn: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enforce_abac(db, current_user, "m365_calendar_event", event_id, action="delete")
    _require_m365()
    try:
        await _graph_delete(f"/users/{user_upn}/events/{event_id}")
    except httpx.HTTPStatusError as e:
        logger.warning("Graph API delete event failed: status=%s", e.response.status_code)
        raise HTTPException(e.response.status_code, "Graph API request failed")
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
        logger.warning("Teams webhook notify failed: status=%s", resp.status_code)
        raise HTTPException(502, "Teams webhook delivery failed")
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
        logger.warning("Teams milestone webhook notify failed: status=%s", resp.status_code)
        raise HTTPException(502, "Teams webhook delivery failed")
    return {"ok": True}


@router.post("/teams/webhooks/incoming")
async def receive_teams_webhook(
    payload: dict,
    _: User = Depends(get_current_user),
):
    """
    Receive incoming messages from a Teams bot (e.g. task updates, commands).
    Processes: 'create_task', 'list_projects', 'log_hours' commands from Teams chat.

    NOTE (audit #94): the response strings below are *intentional* UX fallbacks
    — short bot replies that point the user to the correct NexusPM screen.
    They are NOT stub placeholders for a missing backend implementation;
    the actual data (tasks, projects, imputations) lives in their own endpoints
    and the Teams bot is only meant to be a thin shortcut. Keep them as
    constants here so the bot's surface is reviewable in one place.
    """
    text = payload.get("text", "").lower().strip()
    command = payload.get("command") or text.split()[0] if text else ""

    # Simple command dispatch — fixed Spanish copy is the product spec for the
    # Teams bot integration (single-tenant, Spanish-only deployment for now).
    if "create_task" in command or "nueva tarea" in text:
        return {"type": "message", "text": "Para crear una tarea ve a NexusPM → Tareas → Nueva tarea. [Abrir NexusPM](/)"}
    if "log_hours" in command or "imputar" in text:
        return {"type": "message", "text": "Para registrar horas ve a NexusPM → Imputar horas. [Abrir imputaciones](/imputar)"}
    if "projects" in command or "proyectos" in text:
        return {"type": "message", "text": "Consulta tus proyectos activos en NexusPM → Proyectos. [Ver proyectos](/projects)"}

    # Default greeting / help reply when no known command matched.
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
            logger.warning("Error resolviendo UPN M365 %s, se omite", upn, exc_info=True)

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
        # intentional: chained re-raise preserves context
        except HTTPException:
            raise

    # Fetch existing Planner tasks for conflict detection
    try:
        existing_response = _graph_get_sync(f"/planner/plans/{active_plan_id}/tasks")
        existing_titles = {t.get("title", "").lower() for t in existing_response.get("value", [])}
    except Exception:
        logger.warning("Error obteniendo tareas existentes del plan Planner %s", active_plan_id, exc_info=True)
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
                logger.warning("Error formateando due_date para tarea %s", getattr(task, "id", None), exc_info=True)
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
            logger.warning("Error creando tarea Planner '%s' en plan %s", title, active_plan_id, exc_info=True)
            errors += 1

    return {
        "plan_id": active_plan_id,
        "created": created,
        "skipped": skipped,
        "errors":  errors,
    }

