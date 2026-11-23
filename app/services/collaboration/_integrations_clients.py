"""Wrappers de las APIs externas (Jira / GitHub / GitLab / Google / M365).

Expuestos via slash commands del bot Bridge.
Funciones devuelven dict con `ok` y resultado, o `error` si falla.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.services.collaboration._integrations import decrypt
from app.services.settings_service import outbound_http_timeout
from app.core.config import settings
from app.core.outbound_url import cliente_httpx_async

logger = logging.getLogger(__name__)

# §5 (auditoría 22-11-2026): `jira_create_issue`, `github_create_issue`,
# `gitlab_create_issue`, `google_calendar_create` y `m365_send_mail` no los
# llamaba nadie (ningún slash command): retirados. Quedan los listados de
# calendario, que sí usan `admin` y el panel.


def _token_for(integration) -> Optional[str]:
    if not integration:
        return None
    return decrypt(integration.access_token_enc)


# ── Jira ────────────────────────────────────────────────────────────────────
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
        # SSRF: host fijo de plataforma (www.googleapis.com)
        async with httpx.AsyncClient(timeout=outbound_http_timeout(default=15)) as c:
            r = await c.get(url, headers={"Authorization": f"Bearer {token}"},
                            params=params)
            return {"ok": r.status_code < 400, "status": r.status_code, "body": r.json()}
    except Exception as exc:
        logger.warning("google_calendar_list: excepcion ignorada", exc_info=True)
        return {"error": str(exc)}


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
            f"{settings.MICROSOFT_GRAPH_BASE}/v1.0/me/calendarView"
            f"?startDateTime={desde_iso}&endDateTime={hasta_iso}"
            f"&$top={top}&$orderby=start/dateTime"
        )
    else:
        url = f"{settings.MICROSOFT_GRAPH_BASE}/v1.0/me/events?$top={top}&$orderby=start/dateTime"
    try:
        # SSRF: host fijo de plataforma (settings.MICROSOFT_GRAPH_BASE)
        async with httpx.AsyncClient(timeout=outbound_http_timeout(default=15)) as c:
            r = await c.get(url, headers={"Authorization": f"Bearer {token}"})
            return {"ok": r.status_code < 400, "status": r.status_code, "body": r.json()}
    except Exception as exc:
        logger.warning("m365_calendar_list: excepcion ignorada", exc_info=True)
        return {"error": str(exc)}
