"""Bot de Microsoft Teams: contestar con la base de conocimiento, y contestar de verdad (revisión 2026-11).

Lo que contecmind tenía. Dos piezas:

1. **Responder con la base de conocimiento.** Un mensaje que no es un comando
   (`tarea`, `ticket`…) se contesta con los artículos de la base del Service
   Desk de la empresa de quien escribe, igual que el asistente interno
   (`kb_calidad.contexto`: correcciones de experto y artículos con su número),
   citando las fuentes. Sin nada en la base, lo dice y la pregunta queda como
   «pregunta sin respuesta» (origen `teams`).

2. **Enviar la respuesta.** Bot Framework no lee el cuerpo de la respuesta HTTP
   de una actividad `message`: la respuesta se envía aparte, con `POST` a
   `{serviceUrl}/v3/conversations/{id}/activities/{actividad}`, autenticada con
   un token de la aplicación del bot (`TEAMS_BOT_APP_ID` +
   `TEAMS_BOT_APP_PASSWORD`). El `serviceUrl` lo trae la petición: sólo se usa
   si coincide con el del token firmado (`serviceurl`) y con un dominio de
   `TEAMS_BOT_ALLOWED_SERVICE_HOSTS`.

**No verificado contra Azure/Teams reales**: no hay un registro de bot con el
que probarlo. Las pruebas comprueban la forma exacta de las llamadas (token y
actividad) con dobles, según la documentación de Bot Framework.
"""
from __future__ import annotations

import fnmatch
import logging
import time
from typing import Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

_SISTEMA = ("Eres el asistente de la empresa en Microsoft Teams. Contesta en el idioma de la pregunta, en pocas "
            "líneas, usando SOLO la información de la base de conocimiento que sigue. Si no basta, dilo.")
_token: dict = {"valor": None, "caduca": 0.0}


# ── 1. Respuesta con la base de conocimiento ──────────────────────────────────

def respuesta_de_la_base(db, usuario, pregunta: str) -> str:
    from app.services.ai_provider_service import call_ai, es_aviso_de_ia
    from app.services.service_desk.kb_calidad import contexto
    ctx = contexto(db, pregunta, solo_publico=False, origen="teams")
    if not ctx["prompt"]:
        db.commit()   # el hueco queda apuntado
        return ("No encuentro nada sobre eso en la base de conocimiento. He apuntado la pregunta para que "
                "alguien la responda.")
    texto = call_ai(db, [{"role": "user", "content": pregunta}], system=_SISTEMA + ctx["prompt"],
                    module="knowledge_base", user_id=usuario.id, organization_id=usuario.organization_id,
                    is_superadmin=False, max_tokens=600)
    db.commit()
    if es_aviso_de_ia(texto):
        return "Ahora mismo no puedo consultar la IA. Prueba más tarde."
    fuentes = "\n".join(f"- [{s['number']}] {s['title']}" for s in ctx["sources"])
    return texto.strip() + (f"\n\nFuentes:\n{fuentes}" if fuentes else "")


# ── 2. Enviar la respuesta a Teams ────────────────────────────────────────────

def _host_permitido(url: str) -> bool:
    from app.core.config import settings
    partes = urlparse(url)
    if partes.scheme != "https" or not partes.hostname:
        return False
    patrones = [p.strip().lower() for p in settings.TEAMS_BOT_ALLOWED_SERVICE_HOSTS.split(",") if p.strip()]
    return any(fnmatch.fnmatch(partes.hostname.lower(), p) for p in patrones)


def service_url_valido(actividad: dict, claims: Optional[dict]) -> Optional[str]:
    """El `serviceUrl` de la actividad, sólo si coincide con el del token y su dominio está permitido."""
    url = (actividad.get("serviceUrl") or "").strip()
    del_token = ((claims or {}).get("serviceurl") or "").strip()
    if not url or url.rstrip("/").lower() != del_token.rstrip("/").lower():
        return None
    return url if _host_permitido(url) else None


def _token_de_la_aplicacion() -> str:
    from app.core.config import settings
    if _token["valor"] and _token["caduca"] > time.time() + 60:
        return _token["valor"]
    r = httpx.post(settings.TEAMS_BOT_TOKEN_URL, data={
        "grant_type": "client_credentials", "client_id": settings.TEAMS_BOT_APP_ID,
        "client_secret": settings.TEAMS_BOT_APP_PASSWORD, "scope": settings.TEAMS_BOT_TOKEN_SCOPE}, timeout=10)
    r.raise_for_status()
    datos = r.json()
    _token.update(valor=datos["access_token"], caduca=time.time() + int(datos.get("expires_in", 3600)))
    return _token["valor"]


def actividad_de_respuesta(actividad: dict, texto: str) -> dict:
    return {"type": "message", "text": texto, "textFormat": "markdown",
            "replyToId": actividad.get("id"), "conversation": actividad.get("conversation"),
            "from": actividad.get("recipient"), "recipient": actividad.get("from")}


def enviar(actividad: dict, texto: str, service_url: str) -> bool:
    """POST de la respuesta al Bot Connector. Devuelve si Teams la aceptó."""
    from app.core.config import settings
    if not (settings.TEAMS_BOT_APP_ID and settings.TEAMS_BOT_APP_PASSWORD):
        logger.warning("teams: sin TEAMS_BOT_APP_PASSWORD no se puede contestar en Teams")
        return False
    conversacion = (actividad.get("conversation") or {}).get("id")
    if not conversacion:
        return False
    url = f"{service_url.rstrip('/')}/v3/conversations/{conversacion}/activities"
    if actividad.get("id"):
        url += f"/{actividad['id']}"
    try:
        r = httpx.post(url, json=actividad_de_respuesta(actividad, texto),
                       headers={"Authorization": f"Bearer {_token_de_la_aplicacion()}"}, timeout=10)
        r.raise_for_status()
        return True
    except Exception:
        logger.warning("teams: no se pudo enviar la respuesta", exc_info=True)
        return False
