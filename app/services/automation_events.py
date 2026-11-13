"""Bandeja de eventos de las automatizaciones (`automation_events`).

Auditoria 2026-11. `fire_trigger()` no lo llamaba ningun servicio: una regla
solo corria al pulsar «Probar». Igual que `service_desk/ticket_events.py`, el
evento se anota en el `before_flush` de la sesion y no en cada endpoint: una
tarea cambia de estado desde su ficha, el tablero, Jira, la IA, una regla o la
API, y cada via que se olvidara de avisar seria una regla que no salta. Aqui
no se olvida ninguna, porque todas acaban guardando el registro.

- El evento entra en la misma transaccion que el cambio: si se deshace, el
  evento tambien.
- Solo se anota si la organizacion tiene alguna regla activa con ese
  disparador (una consulta por flush con cambios vigilados).
- Lo procesa el worker despues del commit (`procesar_pendientes`); la tarea
  periodica del beat es la red cuando el broker no esta.
- Lo que hace una regla puede disparar otra; la profundidad viaja con el
  evento y `AUTOMATIONS_MAX_CHAIN_DEPTH` corta la cadena.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import event, inspect, select

from app.db.session import TenantSession
# Registra sus escuchadores ya: si entrara por primera vez desde `_tras_confirmar`
# (antes importaba `app.worker`; ahora encola por nombre), lo haria en mitad del commit y SQLAlchemy
# revienta con «deque mutated during iteration». Medido en Postgres con un
# script que no cargaba `app.main`.
import app.services.service_desk.ticket_events  # noqa: F401,E402

logger = logging.getLogger(__name__)

_PENDIENTES = "automatizaciones_pendientes"
#: Profundidad de la cadena mientras se ejecutan las acciones de una regla.
PROFUNDIDAD = "automatizacion_profundidad"


def _v(x: Any) -> Any:
    return getattr(x, "value", x)


def _cambio(obj, campo: str) -> Optional[tuple]:
    """(antes, despues) si `campo` cambio en este flush; None si no."""
    hist = inspect(obj).attrs[campo].history
    if not hist.has_changes():
        return None
    antes = _v(hist.deleted[0]) if hist.deleted else None
    despues = _v(hist.added[0]) if hist.added else None
    return None if antes == despues else (antes, despues)


# ── Que evento produce cada registro ────────────────────────────────────────
# Cada funcion devuelve [(disparador, contexto)]. `nuevo` dice si es un alta.

def _tarea(obj, nuevo: bool) -> list:
    ctx = {"task_id": obj.id, "project_id": obj.project_id, "code": obj.code, "title": obj.title,
           "status": _v(obj.status), "priority": _v(obj.priority),
           "assignee_id": obj.assignee_id, "user_id": obj.assignee_id,
           "due_date": str(obj.due_date) if obj.due_date else None}
    if nuevo:
        return [("task_created", ctx)]
    salida = []
    estado = _cambio(obj, "status")
    if estado:
        c = {**ctx, "old_status": estado[0]}
        salida.append(("task_status_changed", c))
        if estado[1] == "done":
            salida.append(("task_completed", c))
        elif estado[1] == "blocked":
            salida.append(("task_blocked", c))
    asignado = _cambio(obj, "assignee_id")
    if asignado and asignado[1]:
        salida.append(("task_assigned", {**ctx, "old_assignee_id": asignado[0]}))
    return salida


def _proyecto(obj, nuevo: bool) -> list:
    ctx = {"project_id": obj.id, "code": obj.code, "name": obj.name, "status": _v(obj.status)}
    if nuevo:
        return [("project_created", ctx)]
    estado = _cambio(obj, "status")
    return [("project_status_changed", {**ctx, "old_status": estado[0]})] if estado else []


def _contexto_ticket(t) -> dict:
    return {"ticket_id": t.id, "number": t.number, "title": t.title, "status": _v(t.status),
            "priority": _v(t.priority), "ticket_type": _v(t.ticket_type),
            "support_level": _v(t.support_level), "project_id": t.project_id,
            "assignee_id": t.assigned_to_user_id, "user_id": t.assigned_to_user_id}


_CERRADOS = {"resolved", "closed", "cancelled"}


def _ticket(obj, nuevo: bool) -> list:
    ctx = _contexto_ticket(obj)
    if nuevo:
        return [("ticket_created", ctx)]
    estado = _cambio(obj, "status")
    if not estado:
        return []
    c = {**ctx, "old_status": estado[0]}
    if estado[1] == "resolved":
        return [("ticket_resolved", c)]
    if estado[0] in _CERRADOS and estado[1] not in _CERRADOS:
        return [("ticket_reopened", c)]
    return []


_EVENTO_DE_TICKET = {"sla_warning": "ticket_sla_at_risk", "sla_breached": "ticket_sla_breached",
                     "escalated": "ticket_escalated"}


def _evento_de_ticket(session, obj, nuevo: bool) -> list:
    """SLA en riesgo, incumplido y escalado ya los anota la bandeja de tickets."""
    disparador = _EVENTO_DE_TICKET.get(obj.kind)
    if not nuevo or not disparador:
        return []
    from app.models.service_desk import Ticket
    with session.no_autoflush:
        ticket = obj.ticket if getattr(obj, "ticket", None) is not None else session.get(Ticket, obj.ticket_id)
    if ticket is None:
        return []
    datos = json.loads(obj.data or "{}") if isinstance(obj.data, str) else (obj.data or {})
    return [(disparador, {**_contexto_ticket(ticket), "event": obj.kind,
                          **{k: v for k, v in datos.items() if k in ("sla", "due", "to_level")}})]


def _gasto(obj, nuevo: bool) -> list:
    estado = (None, _v(obj.status)) if nuevo else _cambio(obj, "status")
    disparador = {"submitted": "expense_submitted", "approved": "expense_approved",
                  "rejected": "expense_rejected"}.get(estado[1]) if estado else None
    if not disparador:
        return []
    return [(disparador, {"expense_id": obj.id, "code": getattr(obj, "code", None),
                          "project_id": obj.project_id, "user_id": obj.user_id,
                          "amount": float(obj.amount or 0), "status": estado[1]})]


def _parte(obj, nuevo: bool) -> list:
    estado = (None, _v(obj.status)) if nuevo else _cambio(obj, "status")
    disparador = {"submitted": "timesheet_submitted", "rejected": "timesheet_rejected"}.get(
        estado[1]) if estado else None
    if not disparador:
        return []
    return [(disparador, {"timesheet_id": obj.id, "user_id": obj.user_id,
                          "week_start": str(obj.week_start), "status": estado[1]})]


def _ausencia(obj, nuevo: bool) -> list:
    estado = (None, _v(obj.status)) if nuevo else _cambio(obj, "status")
    disparador = {"pending": "absence_requested", "approved": "absence_approved",
                  "rejected": "absence_rejected"}.get(estado[1]) if estado else None
    if not disparador or (disparador == "absence_requested" and not nuevo):
        return []
    return [(disparador, {"absence_id": obj.id, "user_id": obj.user_id, "status": estado[1],
                          "start_date": str(obj.start_date), "end_date": str(getattr(obj, "end_date", "") or "")})]


def _sprint(obj, nuevo: bool) -> list:
    estado = (None, _v(obj.status)) if nuevo else _cambio(obj, "status")
    disparador = {"active": "sprint_started", "completed": "sprint_ended"}.get(estado[1]) if estado else None
    if not disparador:
        return []
    return [(disparador, {"sprint_id": obj.id, "project_id": obj.project_id, "name": obj.name,
                          "status": estado[1]})]


def _oportunidad(obj, nuevo: bool) -> list:
    if nuevo:
        return []
    etapa = _cambio(obj, "stage")
    if not etapa:
        return []
    return [("opportunity_stage_changed", {"opportunity_id": obj.id, "name": obj.name,
                                           "client_name": obj.client_name, "stage": etapa[1],
                                           "old_stage": etapa[0], "user_id": obj.owner_id})]


def _riesgo(obj, nuevo: bool) -> list:
    if not nuevo and not _cambio(obj, "risk_score"):
        return []
    if obj.risk_score is None:
        return []
    return [("risk_score_high", {"risk_id": obj.id, "project_id": obj.project_id,
                                 "risk_score": float(obj.risk_score), "status": _v(obj.status)})]


def _factura(obj, nuevo: bool) -> list:
    """Revisión 2026-11: enviada y cobrada (la vencida sale del barrido)."""
    estado = (None, _v(obj.status)) if nuevo else _cambio(obj, "status")
    disparador = {"sent": "invoice_sent", "paid": "invoice_paid"}.get(estado[1]) if estado else None
    if not disparador:
        return []
    from app.services.automations_service import contexto_de_factura
    return [(disparador, contexto_de_factura(obj))]


def _aprobacion(obj, nuevo: bool) -> list:
    """Revisión 2026-11: pedida, aprobada o rechazada (venga del motor, del correo o de una regla)."""
    estado = (None, obj.status) if nuevo else _cambio(obj, "status")
    disparador = {"pending": "approval_requested", "approved": "approval_approved",
                  "rejected": "approval_rejected"}.get(estado[1]) if estado else None
    if not disparador or (disparador == "approval_requested" and not nuevo):
        return []
    return [(disparador, {"approval_id": obj.id, "entity_type": obj.entity_type, "entity_id": obj.entity_id,
                          "workflow_id": obj.workflow_id, "user_id": obj.requested_by, "status": estado[1],
                          "title": obj.entity_summary})]


def _vigilados() -> dict:
    from app.models.billing_reports import ApprovalRequest, Invoice
    from app.models.expenses import Expense
    from app.models.financial import Timesheet
    from app.models.pipeline import Opportunity, Risk
    from app.models.project import Project
    from app.models.resources import Absence
    from app.models.service_desk import Ticket, TicketEvent
    from app.models.sprints import Sprint
    from app.models.task import Task
    return {Task: _tarea, Project: _proyecto, Ticket: _ticket, TicketEvent: None, Expense: _gasto,
            Timesheet: _parte, Absence: _ausencia, Sprint: _sprint, Opportunity: _oportunidad,
            Risk: _riesgo, Invoice: _factura, ApprovalRequest: _aprobacion}


_VIGILADOS: Optional[dict] = None


def _dar_id(obj) -> None:
    """Revisión 2026-11: en un alta el `id` aún es None en `before_flush` (el valor
    por defecto se aplica al insertar), así que el evento salía sin `task_id` y
    toda acción sobre «la tarea del evento» fallaba. Se asigna aquí, con el
    mismo valor por defecto de la columna."""
    columna = type(obj).__table__.c.get("id")
    if getattr(obj, "id", None) is not None or columna is None or columna.default is None:
        return
    if getattr(columna.default, "is_callable", False):
        obj.id = columna.default.arg(None)


def eventos_del_flush(session) -> list[tuple[Optional[str], str, dict]]:
    """[(organizacion, disparador, contexto)] de los cambios de este flush."""
    global _VIGILADOS
    if _VIGILADOS is None:
        _VIGILADOS = _vigilados()
    salida = []
    for coleccion, nuevo in ((session.new, True), (session.dirty, False)):
        for obj in list(coleccion):
            cls = type(obj)
            if cls not in _VIGILADOS:
                continue
            if not nuevo and not session.is_modified(obj, include_collections=False):
                continue
            fn = _VIGILADOS[cls]
            if nuevo:
                _dar_id(obj)
            try:
                pares = _evento_de_ticket(session, obj, nuevo) if fn is None else fn(obj, nuevo)
            except Exception:
                logger.exception("automatizaciones: no se pudo leer el evento de %s", cls.__name__)
                continue
            org = getattr(obj, "organization_id", None) or session.info.get("organization_id")
            for disparador, ctx in pares:
                salida.append((org, disparador, ctx))
    return salida


def _antes_de_guardar(session, flush_context, instances) -> None:
    eventos = [e for e in eventos_del_flush(session) if e[0]]
    if not eventos:
        return
    from app.models.automations import AutomationEvent, AutomationRule
    orgs = {e[0] for e in eventos}
    with session.no_autoflush:
        filas = session.execute(
            select(AutomationRule.organization_id, AutomationRule.trigger_type).where(
                AutomationRule.is_active.is_(True), AutomationRule.organization_id.in_(orgs),
            ).distinct()
        ).all()
    con_regla = {(o, t) for o, t in filas}
    profundidad = session.info.get(PROFUNDIDAD, 0)
    anotados = 0
    for org, disparador, ctx in eventos:
        if (org, disparador) not in con_regla:
            continue
        session.add(AutomationEvent(
            organization_id=org, trigger_type=disparador, depth=profundidad,
            context=json.dumps({**ctx, "event_type": disparador}, default=str),
        ))
        anotados += 1
    if anotados:
        session.info[_PENDIENTES] = True


def _tras_confirmar(session) -> None:
    if not session.info.pop(_PENDIENTES, False):
        return
    try:
        from app.core.segundo_plano import enviar_tarea
        enviar_tarea("app.worker.automations_procesar_eventos", retry=False)
    except Exception as exc:
        logger.debug("automatizaciones: sin broker, la recoge la tarea periodica (%s)", exc)


def _tras_deshacer(session) -> None:
    session.info.pop(_PENDIENTES, None)


# ── Proceso ─────────────────────────────────────────────────────────────────

def procesar_evento(db, ev) -> dict:
    """Ejecuta las reglas del evento y lo marca como hecho (o fallido)."""
    from app.services import automations_service
    from app.services.service_desk.ticket_events import como_organizacion

    ev.attempts = (ev.attempts or 0) + 1
    with como_organizacion(db, ev.organization_id):
        try:
            # Lo que escriben las acciones va en un savepoint: si una revienta,
            # se deshace lo suyo y el evento queda anotado como fallido.
            with db.begin_nested():
                resultado = automations_service.disparar(
                    db, ev.trigger_type, json.loads(ev.context or "{}"), ev.organization_id,
                    profundidad=ev.depth or 0)
            ev.status = "done"
            ev.error = None
        except Exception as exc:
            logger.exception("automatizaciones: el evento %s fallo", ev.id)
            from app.services.settings_service import get_runtime_int
            maximo = get_runtime_int(db, "AUTOMATIONS_EVENT_MAX_ATTEMPTS", ev.organization_id) or 3
            ev.status = "failed" if ev.attempts >= maximo else "pending"
            ev.error = str(exc)[:500]
            resultado = {"error": str(exc)}
        ev.processed_at = datetime.now(timezone.utc)
        db.commit()
    return resultado


def procesar_pendientes(db, limite: Optional[int] = None) -> dict:
    """Procesa la bandeja, del mas antiguo al mas nuevo."""
    from app.models.automations import AutomationEvent
    from app.services.settings_service import get_runtime_int

    limite = limite or get_runtime_int(db, "AUTOMATIONS_EVENT_BATCH_SIZE") or 200
    pendientes = db.query(AutomationEvent).filter(AutomationEvent.status == "pending").order_by(
        AutomationEvent.created_at).limit(limite).all()
    reglas = 0
    for ev in pendientes:
        r = procesar_evento(db, ev)
        reglas += len(r.get("rules", [])) if isinstance(r, dict) else 0
    return {"events": len(pendientes), "rules_run": reglas}


event.listen(TenantSession, "before_flush", _antes_de_guardar)
event.listen(TenantSession, "after_commit", _tras_confirmar)
event.listen(TenantSession, "after_soft_rollback", lambda session, previous: _tras_deshacer(session))
