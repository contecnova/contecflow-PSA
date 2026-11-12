"""Wrappers de las APIs externas (Jira / GitHub / GitLab / Google / M365).

Expuestos via slash commands del bot Bridge.
Funciones devuelven dict con `ok` y resultado, o `error` si falla.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.services.collaboration._integrations import decrypt

logger = logging.getLogger(__name__)


def _token_for(integration) -> Optional[str]:
    if not integration:
        return None
    return decrypt(integration.access_token_enc)


# ── Jira ────────────────────────────────────────────────────────────────────
async def jira_create_issue(integration, project_key: str, summary: str, description: str) -> dict:
    token = _token_for(integration)
    if not token:
        return {"error": "Jira no autenticado"}
    cloud_id = (integration.config or {}).get("cloud_id")
    if not cloud_id:
        return {"error": "cloud_id Jira no configurado"}
    url = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/issue"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = {
        "fields": {
            "project": {"key": project_key},
            "summary": summary,
            "description": {
                "type": "doc", "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}],
            },
            "issuetype": {"name": "Task"},
        }
    }
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(url, headers=headers, json=body)
            return {"ok": r.status_code < 400, "status": r.status_code, "body": r.json()}
    except Exception as exc:
        logger.warning("jira_create_issue: excepcion ignorada", exc_info=True)
        return {"error": str(exc)}


# ── GitHub ──────────────────────────────────────────────────────────────────
async def github_create_issue(integration, owner: str, repo: str, title: str, body: str) -> dict:
    token = _token_for(integration)
    if not token:
        return {"error": "GitHub no autenticado"}
    url = f"https://api.github.com/repos/{owner}/{repo}/issues"
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(url, headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            }, json={"title": title, "body": body})
            return {"ok": r.status_code < 400, "status": r.status_code, "body": r.json()}
    except Exception as exc:
        logger.warning("github_create_issue: excepcion ignorada", exc_info=True)
        return {"error": str(exc)}


# ── GitLab ──────────────────────────────────────────────────────────────────
async def gitlab_create_issue(integration, project_id: str, title: str, description: str) -> dict:
    token = _token_for(integration)
    if not token:
        return {"error": "GitLab no autenticado"}
    url = f"https://gitlab.com/api/v4/projects/{project_id}/issues"
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(url, headers={"Authorization": f"Bearer {token}"},
                             json={"title": title, "description": description})
            return {"ok": r.status_code < 400, "status": r.status_code, "body": r.json()}
    except Exception as exc:
        logger.warning("gitlab_create_issue: excepcion ignorada", exc_info=True)
        return {"error": str(exc)}


# ── Google Calendar ─────────────────────────────────────────────────────────
async def google_calendar_list(
    integration,
    max_results: int = 10,
    *,
    desde_iso: Optional[str] = None,
    hasta_iso: Optional[str] = None,
) -> dict:
    """Eventos del calendario primario, opcionalmente acotados a una ventana.

    Auditoría 2026-08. `orderBy=startTime` ordena ascendente desde el principio
    del calendario, así que sin `timeMin` esto devolvía los eventos MÁS
    ANTIGUOS —los de hace años— presentándolos como «próximos». La ventana no es
    un extra: es lo que hace que el orden ascendente signifique lo que dice.
    """
    token = _token_for(integration)
    if not token:
        return {"error": "Google no autenticado"}
    url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
    params: dict = {
        "maxResults": max_results,
        "orderBy": "startTime",
        "singleEvents": True,
    }
    if desde_iso:
        params["timeMin"] = desde_iso
    if hasta_iso:
        params["timeMax"] = hasta_iso
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(url, headers={"Authorization": f"Bearer {token}"},
                            params=params)
            return {"ok": r.status_code < 400, "status": r.status_code, "body": r.json()}
    except Exception as exc:
        logger.warning("google_calendar_list: excepcion ignorada", exc_info=True)
        return {"error": str(exc)}


async def google_calendar_create(integration, summary: str, start_iso: str, end_iso: str) -> dict:
    token = _token_for(integration)
    if not token:
        return {"error": "Google no autenticado"}
    url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(url, headers={"Authorization": f"Bearer {token}"}, json={
                "summary": summary,
                "start": {"dateTime": start_iso},
                "end": {"dateTime": end_iso},
            })
            return {"ok": r.status_code < 400, "status": r.status_code, "body": r.json()}
    except Exception as exc:
        logger.warning("google_calendar_create: excepcion ignorada", exc_info=True)
        return {"error": str(exc)}


# ── Microsoft 365 ───────────────────────────────────────────────────────────
async def m365_calendar_list(
    integration,
    top: int = 10,
    *,
    desde_iso: Optional[str] = None,
    hasta_iso: Optional[str] = None,
) -> dict:
    """Eventos del calendario del usuario, opcionalmente acotados a una ventana.

    Auditoría 2026-08: mismo defecto que en Google. `$orderby=start/dateTime`
    con `$top` y sin filtro devuelve los eventos más antiguos de la cuenta.

    Se usa `calendarView`, que es el recurso que Graph destina a una ventana
    temporal, y no `events` con `$filter`: `calendarView` expande las series
    periódicas en sus apariciones concretas, mientras que `events` devuelve la
    serie maestra con su fecha de inicio original —una reunión semanal creada en
    2024 aparecería como un evento de 2024 y no en la semana que viene—.
    """
    token = _token_for(integration)
    if not token:
        return {"error": "M365 no autenticado"}
    if desde_iso and hasta_iso:
        url = (
            "https://graph.microsoft.com/v1.0/me/calendarView"
            f"?startDateTime={desde_iso}&endDateTime={hasta_iso}"
            f"&$top={top}&$orderby=start/dateTime"
        )
    else:
        url = f"https://graph.microsoft.com/v1.0/me/events?$top={top}&$orderby=start/dateTime"
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(url, headers={"Authorization": f"Bearer {token}"})
            return {"ok": r.status_code < 400, "status": r.status_code, "body": r.json()}
    except Exception as exc:
        logger.warning("m365_calendar_list: excepcion ignorada", exc_info=True)
        return {"error": str(exc)}


async def m365_send_mail(integration, to: str, subject: str, body: str) -> dict:
    token = _token_for(integration)
    if not token:
        return {"error": "M365 no autenticado"}
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": to}}],
        },
        "saveToSentItems": True,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post("https://graph.microsoft.com/v1.0/me/sendMail",
                             headers={"Authorization": f"Bearer {token}"}, json=payload)
            return {"ok": r.status_code < 400, "status": r.status_code}
    except Exception as exc:
        logger.warning("m365_send_mail: excepcion ignorada", exc_info=True)
        return {"error": str(exc)}
