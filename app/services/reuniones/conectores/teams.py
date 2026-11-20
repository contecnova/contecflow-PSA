"""Microsoft Teams vía Graph (credenciales de aplicación de la empresa).

Permisos de aplicación en Entra: `OnlineMeetings.Read.All`,
`OnlineMeetingTranscript.Read.All`, `Calendars.Read` y una *application access
policy* de Teams que permita a la aplicación leer las reuniones de esos
usuarios. Dos modos:
- sondeo: `calendarView` de las últimas horas de quien lo activó → reunión en
  línea por `JoinWebUrl` → `transcripts` → contenido VTT;
- suscripción: `communications/onlineMeetings/getAllTranscripts`; el aviso
  llega a `/webhooks/meetings/teams/{empresa}` con el `clientState` cifrado de
  la empresa y se procesa igual.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.core.codigos_de_error import ErrorConCodigo
from app.services.reuniones import config
from app.services.reuniones.conectores import Importable, exigir_activo, http
from app.services.reuniones.transcripcion import de_vtt

PLATAFORMA = "Microsoft Teams"


def _graph() -> str:
    from app.core.config import settings
    return f"{settings.MICROSOFT_GRAPH_BASE}/v1.0"


def token(db: Session, org: Optional[str]) -> str:
    from app.core.config import settings
    cfg = config.leer(db, org)
    exigir_activo(cfg, "teams", PLATAFORMA)
    t = cfg["teams"]
    secreto = config.secreto(db, org, "teams", "client_secret")
    if not (t.get("tenant_id") and t.get("client_id") and secreto):
        raise ErrorConCodigo("reuniones_conector_sin_credenciales", plataforma=PLATAFORMA)
    r = http("POST", f"{settings.MICROSOFT_OAUTH_BASE}/{t['tenant_id']}/oauth2/v2.0/token", plataforma=PLATAFORMA,
             data={"grant_type": "client_credentials", "client_id": t["client_id"], "client_secret": secreto,
                   "scope": f"{settings.MICROSOFT_GRAPH_BASE}/.default"})
    return r.json()["access_token"]


def _get(tk: str, ruta: str, **kw):
    return http("GET", ruta if ruta.startswith("http") else f"{_graph()}{ruta}", plataforma=PLATAFORMA,
                headers={"Authorization": f"Bearer {tk}"}, **kw)


def _reunion_por_url(tk: str, organizador: str, join_url: str) -> Optional[dict]:
    filtro = quote(f"JoinWebUrl eq '{join_url}'", safe="")
    datos = _get(tk, f"/users/{quote(organizador, safe='@')}/onlineMeetings?$filter={filtro}").json()
    valores = datos.get("value") or []
    return valores[0] if valores else None


def _importable(tk: str, organizador: str, reunion: dict, transcripcion_id: Optional[str] = None
                ) -> Optional[Importable]:
    base = f"/users/{quote(organizador, safe='@')}/onlineMeetings/{reunion['id']}"
    transcripciones = _get(tk, f"{base}/transcripts").json().get("value") or []
    if transcripcion_id:
        transcripciones = [t for t in transcripciones if t.get("id") == transcripcion_id] or \
            [{"id": transcripcion_id}]
    if not transcripciones:
        return None
    ultima = transcripciones[-1]
    vtt = _get(tk, f"{base}/transcripts/{ultima['id']}/content?$format=text/vtt").text
    participantes = []
    datos_p = reunion.get("participants") or {}
    org_ = (datos_p.get("organizer") or {}).get("upn")
    if org_:
        participantes.append({"name": ((datos_p.get("organizer") or {}).get("identity") or {}).get("user", {})
                              .get("displayName"), "email": org_, "role": "organizador"})
    for a in datos_p.get("attendees") or []:
        participantes.append({"name": ((a.get("identity") or {}).get("user") or {}).get("displayName"),
                              "email": a.get("upn"), "role": "asistente"})
    return Importable(origin="teams", external_id=f"{reunion['id']}:{ultima['id']}",
                      title=reunion.get("subject"), meeting_date=reunion.get("startDateTime"),
                      ends_at=reunion.get("endDateTime"), join_url=reunion.get("joinWebUrl"),
                      organizer_email=organizador, participants=participantes, segments=de_vtt(vtt))


def terminadas_de(db: Session, org: Optional[str], correo: str, horas: int = 24) -> list[Importable]:
    """Reuniones en línea terminadas en las últimas `horas` del calendario de `correo`, con transcripción."""
    tk = token(db, org)
    ahora = datetime.now(timezone.utc)
    desde = (ahora - timedelta(hours=horas)).strftime("%Y-%m-%dT%H:%M:%SZ")
    hasta = ahora.strftime("%Y-%m-%dT%H:%M:%SZ")
    eventos = _get(tk, f"/users/{quote(correo, safe='@')}/calendarView?startDateTime={desde}&endDateTime={hasta}"
                       "&$select=subject,start,end,isOnlineMeeting,onlineMeeting,organizer&$top=50").json()
    salida = []
    for ev in eventos.get("value") or []:
        url = ((ev.get("onlineMeeting") or {}).get("joinUrl"))
        if not ev.get("isOnlineMeeting") or not url:
            continue
        organizador = ((ev.get("organizer") or {}).get("emailAddress") or {}).get("address") or correo
        try:
            reunion = _reunion_por_url(tk, organizador, url)
            imp = _importable(tk, organizador, reunion) if reunion else None
        except ErrorConCodigo:
            continue   # sin permiso sobre ese organizador o sin transcripción: se sigue con las demás
        if imp is not None:
            salida.append(imp)
    return salida


def por_referencia(db: Session, org: Optional[str], correo: str, referencia: str) -> Importable:
    tk = token(db, org)
    reunion = _reunion_por_url(tk, correo, referencia.strip())
    imp = _importable(tk, correo, reunion) if reunion else None
    if imp is None:
        raise ErrorConCodigo("reuniones_plataforma_no_encontrada", plataforma=PLATAFORMA)
    return imp


_RECURSO = re.compile(r"users\('([^']+)'\)/onlineMeetings\('([^']+)'\)/transcripts\('([^']+)'\)", re.I)


def de_aviso(db: Session, org: Optional[str], aviso: dict) -> Optional[Importable]:
    """Un aviso de `getAllTranscripts` a reunión importable."""
    m = _RECURSO.search(aviso.get("resource") or "")
    if not m:
        return None
    usuario, reunion_id, transcripcion_id = m.groups()
    tk = token(db, org)
    reunion = _get(tk, f"/users/{quote(usuario, safe='@')}/onlineMeetings/{reunion_id}").json()
    return _importable(tk, usuario, reunion, transcripcion_id)


def suscribir(db: Session, org: Optional[str]) -> dict:
    """Crea o renueva la suscripción de Graph (máx. ~1 h para transcripciones sin datos cifrados)."""
    tk = token(db, org)
    cfg = config.leer(db, org)["teams"]
    estado = config.secreto(db, org, "teams", "client_state")
    caduca = (datetime.now(timezone.utc) + timedelta(minutes=55)).strftime("%Y-%m-%dT%H:%M:%S.0000000Z")
    if cfg.get("subscription_id"):
        try:
            r = http("PATCH", f"{_graph()}/subscriptions/{cfg['subscription_id']}", plataforma=PLATAFORMA,
                     headers={"Authorization": f"Bearer {tk}"}, json={"expirationDateTime": caduca})
            datos = r.json()
            config.guardar_campo_interno(db, org, "teams", {"subscription_expires_at": datos.get("expirationDateTime")})
            return {"id": cfg["subscription_id"], "expires_at": datos.get("expirationDateTime")}
        except ErrorConCodigo:
            pass   # caducada o borrada: se crea otra
    r = http("POST", f"{_graph()}/subscriptions", plataforma=PLATAFORMA, headers={"Authorization": f"Bearer {tk}"},
             json={"changeType": "created", "resource": "communications/onlineMeetings/getAllTranscripts",
                   "notificationUrl": config.url_de_webhook("teams", org), "clientState": estado,
                   "expirationDateTime": caduca})
    datos = r.json()
    config.guardar_campo_interno(db, org, "teams", {"subscription_id": datos.get("id"),
                                                     "subscription_expires_at": datos.get("expirationDateTime")})
    return {"id": datos.get("id"), "expires_at": datos.get("expirationDateTime")}


def probar(db: Session, org: Optional[str]) -> dict:
    token(db, org)
    return {"ok": True, "detail": "token de Graph obtenido"}
