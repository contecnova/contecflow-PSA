"""Vigilancia periodica del SLA: guarda el estado, avisa y escala.

Auditoria 2026-11. El bucle de control del SLA estaba muerto: `sla_*_status`
no se escribia nunca (solo se calculaba al leer), `sla_breach_scan` solo dejaba
una linea en el log, ningun `SLAEvent` de riesgo o incumplimiento se creaba, y
las reglas de escalado —que preguntan precisamente por ese estado guardado—
solo corrian si alguien llamaba al endpoint a mano. Ahora, cada pasada:

1. calcula el estado de respuesta y de resolucion de cada ticket abierto en el
   calendario de su politica, y lo guarda;
2. en cada transicion a «en riesgo» o «incumplido» escribe el `SLAEvent` y un
   evento de ticket, que avisa al agente y a los responsables de la cola;
3. ejecuta las reglas de escalado sobre el estado recien guardado.

Tambien vigila el OLA de cada cola (`AgentGroup.ola_hours`): el tiempo que
tiene la cola desde que le llega el ticket hasta que lo resuelve o lo pasa,
en el calendario del ticket y sin contar la pausa. Al incumplirse avisa una
vez al agente y a los responsables de esa cola.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.service_desk import (
    AgentGroup,
    SLAEvent,
    SLAEventType,
    SLAPolicy,
    SLAStatus,
    Ticket,
    TicketStatus,
)
from app.services import settings_service as _ss
from app.services.service_desk.ticket_events import registrar
from app.services.sla_service import aware, calendario_sla, estado_sla, sumar_horas_sla, vencimiento_efectivo

logger = logging.getLogger(__name__)

ESTADOS_ABIERTOS = (
    TicketStatus.new, TicketStatus.assigned, TicketStatus.in_progress,
    TicketStatus.pending_client, TicketStatus.pending_third,
)
_GRAVEDAD = {"ok": 0, "paused": 0, "at_risk": 1, "breached": 2}


def _v(x):
    return getattr(x, "value", x)


class _Calendarios:
    """Un calendario por (politica, organizacion): los festivos salen de la base."""

    def __init__(self, db: Session):
        self.db = db
        self._cache: dict = {}

    def de(self, ticket: Ticket):
        clave = (ticket.sla_policy_id, ticket.organization_id)
        if clave not in self._cache:
            politica = None
            if ticket.sla_policy_id:
                politica = self.db.get(SLAPolicy, ticket.sla_policy_id)
            self._cache[clave] = calendario_sla(self.db, politica, ticket.organization_id)
        return self._cache[clave]


def _transicion(db: Session, ticket: Ticket, tipo_sla: str, antes: str, ahora_estado: str, due) -> None:
    """Anota el paso a «en riesgo» o «incumplido». Volver a «ok» no avisa."""
    if _GRAVEDAD[ahora_estado] <= _GRAVEDAD.get(antes, 0):
        return
    if ahora_estado == "at_risk":
        tipo_evento, kind = SLAEventType.breach_warn, "sla_warning"
    else:
        tipo_evento, kind = SLAEventType.breached, "sla_breached"
        if tipo_sla == "response":
            ticket.sla_response_breached = True
        else:
            ticket.sla_resolution_breached = True
    db.add(SLAEvent(
        organization_id=ticket.organization_id, ticket_id=ticket.id,
        event_type=tipo_evento, sla_type=tipo_sla,
    ))
    registrar(db, ticket, kind, {"sla": tipo_sla, "due": due.isoformat()}, actor_user_id=None)


def evaluar_ticket(db: Session, ticket: Ticket, cal, aviso_pct: float, ahora: datetime) -> int:
    """Actualiza los dos estados de SLA de un ticket. Devuelve cuantos cambiaron."""
    cambios = 0
    pausado = ticket.sla_paused_at is not None
    pares = (
        ("response", "sla_response_status", ticket.sla_response_due,
         ticket.first_response_at is None),
        ("resolution", "sla_resolution_status", ticket.sla_resolution_due, True),
    )
    for tipo_sla, campo, due, vigente in pares:
        if due is None or not vigente:
            continue
        antes = _v(getattr(ticket, campo)) or "ok"
        if pausado:
            nuevo = "paused"
        else:
            nuevo = estado_sla(ticket.created_at, due, ticket.sla_pause_minutes, cal, aviso_pct, ahora)
        if nuevo == antes:
            continue
        setattr(ticket, campo, SLAStatus(nuevo))
        cambios += 1
        if not pausado:
            _transicion(db, ticket, tipo_sla, antes, nuevo, vencimiento_efectivo(due, ticket.sla_pause_minutes))
    return cambios


def evaluar_ola(db: Session, ticket: Ticket, grupo: AgentGroup, cal, ahora: datetime) -> bool:
    """Pone el vencimiento del OLA y anota el incumplimiento. True si incumple ahora."""
    due = sumar_horas_sla(ticket.group_assigned_at, grupo.ola_hours, cal)
    if ticket.ola_due is None or aware(ticket.ola_due) != due:
        ticket.ola_due = due
    if ticket.sla_paused_at is not None:
        return False
    pausa_en_cola = max(0, (ticket.sla_pause_minutes or 0) - (ticket.ola_pause_base or 0))
    efectivo = vencimiento_efectivo(due, pausa_en_cola)
    if ahora <= efectivo:
        return False
    ticket.ola_breached = True
    db.add(SLAEvent(
        organization_id=ticket.organization_id, ticket_id=ticket.id,
        event_type=SLAEventType.breached, sla_type="ola",
    ))
    registrar(db, ticket, "ola_breached",
              {"group_id": grupo.id, "group": grupo.name, "due": efectivo.isoformat()}, actor_user_id=None)
    return True


def _escanear_olas(db: Session, calendarios: "_Calendarios", ahora: datetime) -> tuple[int, int]:
    filas = (
        db.query(Ticket, AgentGroup)
        .join(AgentGroup, AgentGroup.id == Ticket.assigned_group_id)
        .filter(
            Ticket.status.in_(ESTADOS_ABIERTOS),
            Ticket.group_assigned_at.isnot(None),
            Ticket.ola_breached == False,  # noqa: E712
            AgentGroup.ola_hours.isnot(None),
            AgentGroup.ola_hours > 0,
        )
        .all()
    )
    incumplidos = errores = 0
    for ticket, grupo in filas:
        try:
            incumplidos += evaluar_ola(db, ticket, grupo, calendarios.de(ticket), ahora)
        except ValueError:
            logger.exception("OLA de %s no evaluado: calendario invalido", ticket.number)
            errores += 1
    return incumplidos, errores


def escanear(db: Session, ahora: Optional[datetime] = None) -> dict:
    """Una pasada sobre los tickets abiertos con vencimiento. Confirma al final."""
    from app.services.service_desk.escalation_service import run_escalation_rules_engine

    ahora = ahora or datetime.now(timezone.utc)
    calendarios = _Calendarios(db)
    avisos: dict = {}
    tickets = (
        db.query(Ticket)
        .filter(
            Ticket.status.in_(ESTADOS_ABIERTOS),
            or_(Ticket.sla_response_due.isnot(None), Ticket.sla_resolution_due.isnot(None)),
        )
        .all()
    )
    revisados = cambiados = errores = 0
    for ticket in tickets:
        org = ticket.organization_id
        if org not in avisos:
            avisos[org] = _ss.get_runtime_float(db, "SLA_PREDICTION_WARNING_PCT", org)
        try:
            cambiados += evaluar_ticket(db, ticket, calendarios.de(ticket), avisos[org], ahora)
        except ValueError:
            # Un calendario mal configurado (zona o dias invalidos) no puede
            # parar la vigilancia del resto de tickets.
            logger.exception("SLA de %s no evaluado: calendario invalido", ticket.number)
            errores += 1
        revisados += 1
    olas, errores_ola = _escanear_olas(db, calendarios, ahora)
    db.flush()
    escalado = run_escalation_rules_engine(db, ahora=ahora)
    db.commit()
    return {"revisados": revisados, "cambiados": cambiados, "errores": errores + errores_ola,
            "ola_incumplidos": olas,
            "escalados": escalado["escalations_fired"]}
