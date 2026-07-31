"""
integrations_hub.py — Endpoints para Slack, Teams y Jira.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Body, Query, Request
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
import os
from pydantic import BaseModel

from app.core.config import settings
from app.core.responses import APIResponse
from app.core.secret_utils import decrypt_config_secrets
from app.db.session import get_db
from app.core.deps import require_any_manager
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["integrations-hub"])


# ── Schemas ────────────────────────────────────────────────────────────────────
class SlackTestIn(BaseModel):
    webhook_url: str
    message:     str = "✅ Contecflow conectado correctamente con Slack"

class TeamsTestIn(BaseModel):
    webhook_url: str
    message:     str = "✅ Contecflow conectado correctamente con Teams"

class JiraTestIn(BaseModel):
    base_url:  str
    email:     str
    api_token: str

class JiraIssueIn(BaseModel):
    integration_id: str
    project_key:    str
    summary:        str
    description:    str = ""
    issue_type:     str = "Task"
    priority:       str = "Medium"
    labels:         Optional[list] = None
    nexus_task_id:  Optional[str] = None  # vincular con tarea Contecflow


# ── Slack endpoints ────────────────────────────────────────────────────────────
@router.post("/slack/test", summary="Probar conexión Slack")
def test_slack(
    payload: SlackTestIn,
    current_user: User = Depends(require_any_manager),
):
    from app.services.integrations import send_slack_message, build_slack_blocks
    blocks = build_slack_blocks(
        "🔗 Contecflow — Conexión verificada",
        [("Usuario", current_user.full_name), ("Hora", datetime.now().strftime("%H:%M"))],
    )
    result = send_slack_message(payload.webhook_url, payload.message, blocks=blocks)
    if not result["ok"]:
        raise HTTPException(400, f"Error Slack: {result.get('error')}")
    return APIResponse.ok(data={"ok": True, "message": "Mensaje enviado a Slack correctamente"})


@router.post("/slack/notify", summary="Enviar notificación manual a Slack")
def notify_slack(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.services.integrations import send_slack_message, get_active_integration
    import json
    cfg = get_active_integration(db, payload.get("integration_id"))
    if not cfg: raise HTTPException(404, "Integración no encontrada")
    cfg_dict     = decrypt_config_secrets(json.loads(cfg.config or "{}"))
    webhook_url  = cfg_dict.get("webhook_url", "")
    if not webhook_url: raise HTTPException(400, "Webhook URL no configurada")

    result = send_slack_message(webhook_url, payload.get("text", "Notificación de Contecflow"))
    if not result["ok"]: raise HTTPException(400, result.get("error"))
    return APIResponse.ok(data={"ok": True})


# ── Teams endpoints ────────────────────────────────────────────────────────────
@router.post("/teams/test", summary="Probar conexión Microsoft Teams")
def test_teams(
    payload: TeamsTestIn,
    current_user: User = Depends(require_any_manager),
):
    from app.services.integrations import send_teams_message
    result = send_teams_message(
        payload.webhook_url,
        title="🔗 Contecflow — Conexión verificada",
        text=payload.message,
        facts=[("Usuario", current_user.full_name), ("Hora", datetime.now().strftime("%H:%M"))],
    )
    if not result["ok"]:
        raise HTTPException(400, f"Error Teams: {result.get('error')}")
    return APIResponse.ok(data={"ok": True, "message": "Mensaje enviado a Teams correctamente"})


# ── Jira endpoints ─────────────────────────────────────────────────────────────
@router.post("/jira/test", summary="Verificar conexión con Jira")
def test_jira(
    payload: JiraTestIn,
    current_user: User = Depends(require_any_manager),
):
    from app.services.integrations import get_jira_projects
    cfg = {"base_url": payload.base_url, "email": payload.email, "api_token": payload.api_token}
    result = get_jira_projects(cfg)
    if not result["ok"]:
        raise HTTPException(400, f"Error Jira: {result.get('error')}")
    projects = result["data"].get("values", [])
    return APIResponse.ok(data={
        "ok": True,
        "projects": [{"key": p["key"], "name": p["name"]} for p in projects[:20]],
        "total": len(projects),
    })


@router.post("/jira/issues", summary="Crear issue en Jira desde Contecflow")
def create_jira_issue(
    payload: JiraIssueIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.services.integrations import create_jira_issue as _create_issue, get_active_integration, link_jira_to_task
    import json

    cfg = get_active_integration(db, payload.integration_id)
    if not cfg: raise HTTPException(404, "Integración Jira no encontrada")

    cfg_dict = decrypt_config_secrets(json.loads(cfg.config or "{}"))
    result = _create_issue(
        cfg_dict,
        project_key=payload.project_key,
        summary=payload.summary,
        description=payload.description,
        issue_type=payload.issue_type,
        priority=payload.priority,
        labels=payload.labels or [],
    )
    if not result["ok"]:
        raise HTTPException(400, f"Error Jira: {result.get('error')}")

    if payload.nexus_task_id and result.get("key"):
        link_jira_to_task(db, payload.nexus_task_id, result["key"])

    return APIResponse.ok(data=result)


@router.get("/jira/search", summary="Buscar issues en Jira via JQL")
def search_jira(
    integration_id: str = Query(...),
    jql:            str = Query("project = NEXUS ORDER BY created DESC"),
    max_results:    int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.services.integrations import search_jira_issues, get_active_integration
    import json

    cfg = get_active_integration(db, integration_id)
    if not cfg: raise HTTPException(404)
    cfg_dict = decrypt_config_secrets(json.loads(cfg.config or "{}"))
    result = search_jira_issues(cfg_dict, jql, max_results)
    if not result["ok"]: raise HTTPException(400, result.get("error"))
    issues = result["data"].get("issues", [])
    return APIResponse.ok(data={
        "total": result["data"].get("total", 0),
        "issues": [{
            "key":      i["key"],
            "summary":  i["fields"]["summary"],
            "status":   i["fields"]["status"]["name"],
            "priority": i["fields"].get("priority", {}).get("name", "—"),
            "assignee": (i["fields"].get("assignee") or {}).get("displayName", "—"),
        } for i in issues],
    })


@router.post("/jira/transition", summary="Cambiar estado de issue Jira")
def transition_jira(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.services.integrations import transition_jira_issue, get_active_integration
    import json

    cfg = get_active_integration(db, payload.get("integration_id"))
    if not cfg: raise HTTPException(404)
    cfg_dict = decrypt_config_secrets(json.loads(cfg.config or "{}"))
    result = transition_jira_issue(cfg_dict, payload.get("issue_key"), payload.get("transition"))
    if not result["ok"]: raise HTTPException(400, result.get("error"))
    return APIResponse.ok(data={"ok": True})


# ── Evento manual ──────────────────────────────────────────────────────────────
@router.post("/notify-event", summary="Disparar notificación de evento a Slack/Teams")
def manual_event_notify(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.services.integrations import notify_event
    results = notify_event(
        event_type=payload.get("event_type", ""),
        entity=payload.get("entity", {}),
        db=db,
    )
    return APIResponse.ok(data={"ok": True, "dispatched": len(results), "results": results})


# ── Inbound bot — Slack slash commands ────────────────────────────────────────
@router.post("/slack/commands", summary="Receptor de slash commands desde Slack", include_in_schema=False)
async def slack_inbound_command(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Receives Slack slash command payloads (application/x-www-form-urlencoded).
    Supported commands:
      /contecflow tarea <título> [#proyecto]  → crear tarea
      /contecflow tiempo <horas> [#proyecto]  → registrar imputación del día de hoy
      /contecflow ticket <asunto>             → crear ticket en Service Desk
      /contecflow estado <code>               → consultar estado de tarea/proyecto
      /contecflow ayuda                       → lista de comandos
    Security: validates X-Slack-Signature (HMAC-SHA256) when SLACK_SIGNING_SECRET is set.
    """
    import hashlib
    import hmac

    # ── Signature verification ────────────────────────────────────────────────
    signing_secret = settings.SLACK_SIGNING_SECRET
    body_bytes = await request.body()
    if not signing_secret:
        if os.getenv("TESTING") != "1":
            raise HTTPException(503, "Slack inbound commands are not configured")
    if signing_secret:
        ts  = request.headers.get("X-Slack-Request-Timestamp", "")
        sig = request.headers.get("X-Slack-Signature", "")
        # Replay attack prevention: reject requests older than 5 minutes
        try:
            import time as _time
            if abs(_time.time() - float(ts)) > 300:
                raise HTTPException(403, "Request timestamp too old")
        except (ValueError, TypeError):
            raise HTTPException(403, "Missing or invalid X-Slack-Request-Timestamp")
        base = f"v0:{ts}:{body_bytes.decode()}"
        expected = "v0=" + hmac.new(signing_secret.encode(), base.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            raise HTTPException(403, "Invalid Slack signature")

    from urllib.parse import parse_qs
    params = {k: v[0] for k, v in parse_qs(body_bytes.decode()).items()}

    command_text = params.get("text", "").strip()
    user_name    = params.get("user_name", "")
    params.get("response_url", "")

    # Parse command verb
    parts = command_text.split(None, 1)
    verb  = (parts[0] if parts else "").lower()
    rest  = parts[1] if len(parts) > 1 else ""

    # Audit #C7: async webhook (await request.body() for HMAC). DB work via
    # threadpool — the slack_* helpers below are sync internally.
    from app.core.async_db import run_db
    from app.services.integrations import find_user_by_slack_name
    contecflow_user = await run_db(find_user_by_slack_name, db, user_name)

    try:
        if verb in ("tarea", "task"):
            return await _slack_create_task(rest, contecflow_user, db)
        elif verb in ("tiempo", "time", "horas"):
            return await _slack_log_time(rest, contecflow_user, db)
        elif verb in ("ticket",):
            return await _slack_create_ticket(rest, contecflow_user, db)
        elif verb in ("estado", "status"):
            return await _slack_get_status(rest, db)
        else:
            return _slack_help()
    except Exception as exc:
        logger.warning("Fallo procesando comando entrante de Slack: %s", exc, exc_info=True)
        return {"response_type": "ephemeral", "text": f"❌ Error: {exc}"}


async def _slack_create_task(text: str, user, db):
    """Parse: tarea <título> [#proyecto-code]"""
    from app.core.async_db import run_db
    from app.services.integrations import slack_create_task_from_text
    return await run_db(slack_create_task_from_text, db, text, user)


async def _slack_log_time(text: str, user, db):
    """Parse: tiempo <horas> [#proyecto-code] [descripción]"""
    from app.core.async_db import run_db
    from app.services.integrations import slack_log_time_from_text
    return await run_db(slack_log_time_from_text, db, text, user)


async def _slack_create_ticket(text: str, user, db):
    """Creates a Service Desk incident ticket from Slack."""
    from app.core.async_db import run_db
    from app.services.integrations import slack_create_ticket_from_text
    return await run_db(slack_create_ticket_from_text, db, text, user)


async def _slack_get_status(code: str, db):
    from app.core.async_db import run_db
    from app.services.integrations import slack_get_status_by_code
    return await run_db(slack_get_status_by_code, db, code)


from app.services.integrations import slack_help_response as _slack_help


# ── Inbound bot — MS Teams adaptive card actions ──────────────────────────────
@router.post("/teams/commands", summary="Receptor de acciones de MS Teams", include_in_schema=False)
async def teams_inbound_command(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Receives Teams Bot Framework activity payloads (JSON).
    Supports conversational commands identical to the Slack bot.
    Validates Bearer token audience against TEAMS_BOT_APP_ID env var.
    """
    import json as _json

    # ── Bearer token validation ───────────────────────────────────────────────
    bot_app_id = settings.TEAMS_BOT_APP_ID
    if not bot_app_id:
        if os.getenv("TESTING") != "1":
            raise HTTPException(503, "Teams inbound commands are not configured")
    if bot_app_id:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(401, "Missing Teams bearer token")
        import base64 as _b64
        raw_token = auth_header.removeprefix("Bearer ").strip()
        try:
            parts = raw_token.split(".")
            padded = parts[1] + "=" * (4 - len(parts[1]) % 4)
            claims = _json.loads(_b64.urlsafe_b64decode(padded))
            if claims.get("aud") != bot_app_id and claims.get("appid") != bot_app_id:
                raise HTTPException(403, "Teams token audience mismatch")
        # intentional: chained re-raise preserves context
        except HTTPException:
            raise
        except Exception:
            logger.warning("Token bearer de Teams inválido o malformado")
            raise HTTPException(403, "Invalid Teams bearer token")

    body = await request.json()
    text = (body.get("text") or "").strip().lower()
    # Extract user info from Teams payload
    from_obj   = body.get("from", {})
    teams_name = from_obj.get("name", "").strip()

    # Audit #C7: DB lookup offloaded to threadpool.
    from app.core.async_db import run_db
    from app.services.integrations import find_user_by_teams_name
    contecflow_user = (await run_db(find_user_by_teams_name, db, teams_name)) if teams_name else None

    parts = text.split(None, 1)
    verb  = (parts[0] if parts else "").lower()
    rest  = parts[1] if len(parts) > 1 else ""

    try:
        if verb in ("tarea", "task"):
            result = await _slack_create_task(rest, contecflow_user, db)
        elif verb in ("tiempo", "time"):
            result = await _slack_log_time(rest, contecflow_user, db)
        elif verb in ("ticket",):
            result = await _slack_create_ticket(rest, contecflow_user, db)
        elif verb in ("estado", "status"):
            result = await _slack_get_status(rest, db)
        else:
            result = _slack_help()
        reply_text = result.get("text", "✅")
    except Exception as exc:
        logger.warning("Fallo procesando comando entrante de Teams: %s", exc, exc_info=True)
        reply_text = f"❌ Error: {exc}"

    # Return Teams Activity reply format
    return {
        "type": "message",
        "text": reply_text,
    }
