"""Entrada de alertas de monitorizacion: de una alerta a una incidencia.

Auditoria 2026-11: no habia entrada de alertas. La «correlacion de alertas»
agrupaba tickets ya abiertos; nada convertia una alerta de Prometheus, Zabbix
o Datadog en incidencia. Ahora:

- una alerta nueva abre una incidencia (prioridad segun su gravedad,
  `SD_EVENT_SEVERITY_MAP`; enlazada al CI si su codigo o nombre casa);
- la misma alerta mientras sigue abierta solo suma repeticiones;
- al recuperarse se anota en la incidencia y, si nadie la ha tocado y
  `SD_EVENT_AUTO_RESOLVE` lo permite, se resuelve sola.

Formatos: el de Alertmanager (`{"alerts": [...]}`) y uno generico
(`{"key", "status", "severity", "title", "description", "ci"}`, o una lista).
La organizacion sale del token (`X-Contecflow-Event-Token`), que se guarda en
Credenciales > «Monitoring alerts».
"""
from __future__ import annotations

import hmac
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.service_desk import ConfigurationItem, MonitoringAlert, Ticket, TicketComment
from app.services import settings_service as _ss
from app.services.service_desk.ticket_events import como_organizacion

logger = logging.getLogger(__name__)

_ABIERTOS = ("new", "assigned", "in_progress", "pending_client", "pending_third")


@dataclass
class Alerta:
    clave: str
    estado: str                  # firing | resolved
    gravedad: Optional[str]
    titulo: str
    descripcion: Optional[str]
    ci: Optional[str]


# ── Organizacion por token ───────────────────────────────────────────────────

def organizacion_del_token(db: Session, token: Optional[str]) -> Optional[str]:
    """La organizacion cuyo token de monitorizacion es este. 403 si ninguna."""
    from app.db.session import sin_filtro_de_tenant
    from app.models.settings import IntegrationCredential
    from app.services.integration_credentials_service import _resolve_value, _field_spec

    if not token:
        raise HTTPException(403, "Falta X-Contecflow-Event-Token")
    campo = _field_spec("monitoring", "ingest_token")
    with sin_filtro_de_tenant(db):
        filas = db.query(IntegrationCredential).filter(
            IntegrationCredential.provider == "monitoring", IntegrationCredential.key == "ingest_token").all()
    for fila in filas:
        valor = _resolve_value(fila, campo)
        if valor and hmac.compare_digest(str(valor), token):
            return fila.organization_id
    raise HTTPException(403, "Token de monitorización inválido")


# ── Formatos ─────────────────────────────────────────────────────────────────

def leer(payload) -> list[Alerta]:
    """Alertmanager o el formato generico (un objeto o una lista)."""
    if isinstance(payload, dict) and isinstance(payload.get("alerts"), list):
        salida = []
        for a in payload["alerts"]:
            etiquetas, notas = a.get("labels") or {}, a.get("annotations") or {}
            clave = a.get("fingerprint") or json.dumps(etiquetas, sort_keys=True)
            salida.append(Alerta(
                clave=f"alertmanager:{clave}"[:255],
                estado="resolved" if a.get("status") == "resolved" else "firing",
                gravedad=etiquetas.get("severity"),
                titulo=(notas.get("summary") or etiquetas.get("alertname") or "Alerta")[:500],
                descripcion=notas.get("description"),
                ci=etiquetas.get("instance") or etiquetas.get("host") or etiquetas.get("service"),
            ))
        return salida
    elementos = payload if isinstance(payload, list) else [payload]
    salida = []
    for e in elementos:
        if not isinstance(e, dict) or not (e.get("key") and e.get("title")):
            raise HTTPException(422, "Cada alerta necesita key y title")
        salida.append(Alerta(
            clave=str(e["key"])[:255], estado="resolved" if e.get("status") == "resolved" else "firing",
            gravedad=e.get("severity"), titulo=str(e["title"])[:500], descripcion=e.get("description"),
            ci=e.get("ci"),
        ))
    return salida


# ── Proceso ──────────────────────────────────────────────────────────────────

def _prioridad(db: Session, gravedad: Optional[str], org_id: Optional[str]) -> str:
    try:
        mapa = json.loads(_ss.get_runtime_str(db, "SD_EVENT_SEVERITY_MAP", org_id) or "{}")
    except ValueError:
        logger.warning("SD_EVENT_SEVERITY_MAP no es JSON válido")
        mapa = {}
    return mapa.get((gravedad or "").lower(), "p3_medium")


def _ci(db: Session, referencia: Optional[str]) -> Optional[str]:
    if not referencia:
        return None
    ref = referencia.split(":")[0].strip().lower()
    ci = db.query(ConfigurationItem.id).filter(or_(
        func.lower(ConfigurationItem.code) == ref, func.lower(ConfigurationItem.name) == ref)).first()
    return ci[0] if ci else None


def _abierta(db: Session, alerta: Alerta, source: str) -> Optional[MonitoringAlert]:
    return db.query(MonitoringAlert).filter(
        MonitoringAlert.source == source, MonitoringAlert.dedupe_key == alerta.clave,
        MonitoringAlert.status == "firing",
    ).first()


def _tocada_por_alguien(db: Session, ticket: Ticket) -> bool:
    """Si un agente ha comentado: entonces la resolucion la decide una persona."""
    return db.query(TicketComment.id).filter(TicketComment.ticket_id == ticket.id,
                                             TicketComment.author_user_id.isnot(None)).first() is not None


def _al_recuperarse(db: Session, fila: MonitoringAlert, org_id: Optional[str]) -> None:
    from app.schemas.service_desk import TicketUpdateIn
    from app.services.service_desk.ticket_update_service import apply_ticket_update

    ahora = datetime.now(timezone.utc)
    fila.status, fila.resolved_at, fila.last_seen_at = "resolved", ahora, ahora
    ticket = db.get(Ticket, fila.ticket_id) if fila.ticket_id else None
    if ticket is None or getattr(ticket.status, "value", ticket.status) not in _ABIERTOS:
        return
    db.add(TicketComment(ticket_id=ticket.id, organization_id=ticket.organization_id, is_public=False,
                         author_name="Monitorización", body=f"La alerta se ha recuperado ({fila.source})."))
    if _ss.get_runtime_bool(db, "SD_EVENT_AUTO_RESOLVE", org_id) and not _tocada_por_alguien(db, ticket) \
            and ticket.approval_status != "pending":
        ticket.resolution = "Recuperado automáticamente: la alerta de monitorización volvió a la normalidad."
        apply_ticket_update(db, ticket, ticket.id, TicketUpdateIn(status="resolved"), current_user_id=None,
                            old_assigned_to=ticket.assigned_to_user_id, old_support_level=ticket.support_level)


def procesar(db: Session, org_id: Optional[str], source: str, alertas: list[Alerta]) -> dict:
    """Aplica las alertas. No confirma la transaccion."""
    from app.services.service_desk.ticket_creation_service import build_channel_ticket

    cuenta = {"created": 0, "repeated": 0, "resolved": 0, "ignored": 0}
    with como_organizacion(db, org_id):
        for a in alertas:
            fila = _abierta(db, a, source)
            if a.estado == "resolved":
                if fila is None:
                    cuenta["ignored"] += 1
                else:
                    _al_recuperarse(db, fila, org_id)
                    cuenta["resolved"] += 1
                continue
            if fila is not None:
                fila.occurrences += 1
                fila.last_seen_at = datetime.now(timezone.utc)
                cuenta["repeated"] += 1
                continue
            ci_id = _ci(db, a.ci)
            ticket = build_channel_ticket(
                db, org_id=org_id, titulo=a.titulo, descripcion=a.descripcion or a.titulo,
                source="monitoring", requester_name=f"Monitorización ({source})",
                priority=_prioridad(db, a.gravedad, org_id), ticket_type="incident", ci_id=ci_id,
            )
            db.add(MonitoringAlert(organization_id=org_id, source=source, dedupe_key=a.clave,
                                   severity=a.gravedad, title=a.titulo, description=a.descripcion,
                                   ci_id=ci_id, ticket_id=ticket.id))
            db.flush()
            cuenta["created"] += 1
    return cuenta


def ultimas(db: Session, limite: int) -> list[dict]:
    filas = (db.query(MonitoringAlert, Ticket.number).outerjoin(Ticket, Ticket.id == MonitoringAlert.ticket_id)
             .order_by(MonitoringAlert.last_seen_at.desc()).limit(limite).all())
    return [{"id": m.id, "source": m.source, "status": m.status, "severity": m.severity, "title": m.title,
             "occurrences": m.occurrences, "ticket_id": m.ticket_id, "ticket_number": numero,
             "first_seen_at": m.first_seen_at.isoformat() if m.first_seen_at else None,
             "last_seen_at": m.last_seen_at.isoformat() if m.last_seen_at else None} for m, numero in filas]
