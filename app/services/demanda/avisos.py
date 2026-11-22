"""Flujos de información del expediente: quién se entera de qué.

Cada flujo declara avisos (`notify`) a nivel de flujo y por fase:
`{"event": <evento>, "to": {"type": <destinatario>, "value": …}}`. Eventos:
`submitted`, `enter`, `decision`, `info_requested`, `sla_warning`,
`sla_breach`, `closed`. Destinatarios: el solicitante (cliente del portal o
usuario interno), los responsables de los pasos de la fase, un rol, un grupo,
una persona o un responsable dinámico (PM del proyecto, gestor del cliente,
responsable de quien pide, jefe de departamento, proveedor).

Aunque el flujo no lo diga, «pedir información» y el cierre siempre avisan al
solicitante: sin ese aviso el expediente se queda parado sin que nadie lo sepa.

Usuarios internos: fila en `notifications` (y la app la empuja). Cliente del
portal: mensaje por WebSocket. Un fallo aquí nunca tumba la transición.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.services.demanda import definicion as D

logger = logging.getLogger(__name__)

_SIEMPRE_AL_SOLICITANTE = ("info_requested", "closed")

_TITULOS = {
    "submitted": "Solicitud {code} registrada",
    "enter": "{code}: pasa a «{fase}»",
    "decision": "{code}: nueva decisión en «{fase}»",
    "info_requested": "{code}: se necesita más información",
    "sla_warning": "{code}: el plazo de «{fase}» está a punto de vencer",
    "sla_breach": "{code}: plazo vencido en «{fase}»",
    "closed": "{code}: {estado}",
}


def _destinatarios(db: Session, req, f: Optional[dict], destino: dict) -> tuple[set, bool]:
    """(ids de usuarios internos, ¿avisar al cliente del portal?)."""
    from app.services.demanda.acceso import DINAMICOS, usuarios_dinamicos, usuarios_responsables
    tipo = destino.get("type")
    if tipo == "requester":
        return ({req.requester_user_id} if req.requester_user_id else set()), bool(req.client_user_id)
    if tipo == "assignees":
        ids: set = set()
        for p in D.pasos(f or {}):
            ids.update(usuarios_responsables(db, req.organization_id, p, req))
        return ids, False
    if tipo in DINAMICOS:
        return set(usuarios_dinamicos(db, req, destino)), False
    return set(usuarios_responsables(db, req.organization_id, {"assignee": destino}, req)), False


def emitir(db: Session, req, evento: str, f: Optional[dict], extra: Optional[dict] = None) -> int:
    """Envía los avisos de `evento`. Devuelve cuántos usuarios internos se avisaron."""
    try:
        return _emitir(db, req, evento, f, extra or {})
    except Exception:
        logger.warning("demanda: no se pudo avisar de %s en %s", evento, getattr(req, "id", None), exc_info=True)
        return 0


def _emitir(db: Session, req, evento: str, f: Optional[dict], extra: dict) -> int:
    from app.models.enterprise import Notification, NotificationType
    defn = D.cargar(req.flow_snapshot)
    reglas = [n for n in (defn.get("notify") or []) + ((f or {}).get("notify") or []) if n.get("event") == evento]
    usuarios: set = set()
    al_cliente = False
    for r in reglas:
        ids, cliente = _destinatarios(db, req, f, r.get("to") or {})
        usuarios |= ids
        al_cliente = al_cliente or cliente
    if evento in _SIEMPRE_AL_SOLICITANTE:
        if req.requester_user_id:
            usuarios.add(req.requester_user_id)
        al_cliente = al_cliente or bool(req.client_user_id)
    usuarios.discard(None)
    titulo = _TITULOS.get(evento, "{code}").format(code=req.code, fase=D.nombre((f or {}).get("name")),
                                                   estado=req.status)
    cuerpo = (extra.get("mensaje") or req.title or "")[:1000]
    for uid in usuarios:
        db.add(Notification(id=str(uuid.uuid4()), organization_id=req.organization_id, user_id=uid,
                            type=NotificationType.system, title=titulo[:255], body=cuerpo,
                            resource="demand_request", resource_id=req.id, action_url=f"/demand?id={req.id}"))
    if al_cliente and req.client_user_id:
        try:
            from app.core.background import spawn
            from app.services.notifications import publish_user_notification
            spawn(publish_user_notification(str(req.client_user_id), {
                "type": "demand_event", "event": evento, "request_id": req.id, "code": req.code,
                "status": req.status, "phase": req.current_phase_key, "title": req.title,
                "ts": datetime.now(timezone.utc).isoformat()}), name="demanda-portal")
        except Exception:
            logger.debug("demanda: sin WebSocket para el cliente", exc_info=True)
    return len(usuarios)
