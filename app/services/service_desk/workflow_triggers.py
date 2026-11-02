"""Arranque automatico de flujos del diseñador con los eventos de ticket.

Auditoria 2026-11. Los flujos solo arrancaban a mano, desde la API: un flujo
«cuando entre un P1, avisa al responsable y espera su aprobacion» no se podia
construir. Ahora el nodo de inicio declara su disparador en su configuracion:

    {"trigger": "created", "condition": "priority == p1_critical"}

`trigger` es un tipo de evento de `sd_ticket_events` y `condition` una
expresion del mini-DSL del motor (`evaluate_expression`, sin `eval`) sobre el
ticket y el evento.

Un flujo que cambia el ticket genera eventos; esos eventos no disparan flujos
(van marcados con su origen), o un flujo que cambia el estado al dispararse por
un cambio de estado se llamaria a si mismo sin fin.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.service_desk import Ticket, TicketEvent
from app.models.workflow_designer import (
    WorkflowBlueprint,
    WorkflowBlueprintStatus,
    WorkflowRun,
    WorkflowRunStatus,
)

logger = logging.getLogger(__name__)

#: Eventos que un nodo de inicio puede declarar como disparador.
DISPARADORES = (
    "created", "assigned", "group_assigned", "status_changed",
    "priority_changed", "commented", "sla_warning", "sla_breached", "ola_breached", "escalated",
)

ORIGEN_FLUJO = "workflow"


def contexto_de_ticket(ticket: Ticket, ev: Optional[TicketEvent] = None, data: Optional[dict] = None) -> dict:
    """Lo que ve una condicion: los campos del ticket y, si lo hay, el evento."""
    v = lambda x: getattr(x, "value", x)  # noqa: E731
    ctx = {
        "id": ticket.id,
        "number": ticket.number,
        "title": ticket.title,
        "ticket_type": v(ticket.ticket_type),
        "status": v(ticket.status),
        "priority": v(ticket.priority),
        "urgency": v(ticket.urgency),
        "impact": v(ticket.impact),
        "support_level": v(ticket.support_level),
        "source": ticket.source,
        "assigned_to_user_id": ticket.assigned_to_user_id,
        "assigned_group_id": ticket.assigned_group_id,
        "client_id": ticket.client_id,
        "service_item_id": ticket.service_item_id,
        "ci_id": ticket.ci_id,
        "tags": ticket.tags or "",
    }
    if ev is not None:
        ctx["event"] = {"kind": ev.kind, **(data or {})}
    return ctx


def _disparador(grafo: dict) -> tuple[Optional[str], str]:
    for nodo in grafo.get("nodes", []):
        if (nodo.get("type") or (nodo.get("data") or {}).get("type")) == "start":
            cfg = nodo.get("config") or (nodo.get("data") or {}).get("config") or {}
            return cfg.get("trigger") or None, cfg.get("condition") or ""
    return None, ""


def lanzar_flujos_del_evento(db: Session, ev: TicketEvent, ticket: Ticket, data: dict) -> int:
    """Arranca los flujos publicados cuyo disparador encaja con el evento."""
    from app.services.service_desk.workflow_engine import (
        _get_published_version,
        evaluate_expression,
        start_run,
    )

    if data.get("origin") == ORIGEN_FLUJO or ev.kind not in DISPARADORES:
        return 0
    q = db.query(WorkflowBlueprint).filter(
        WorkflowBlueprint.is_active == True,  # noqa: E712
        WorkflowBlueprint.status == WorkflowBlueprintStatus.published,
        WorkflowBlueprint.process_type == "ticket",
    )
    if ev.organization_id:
        q = q.filter(WorkflowBlueprint.organization_id == ev.organization_id)
    lanzados = 0
    for bp in q.all():
        version = _get_published_version(db, bp.id)
        if version is None:
            continue
        disparador, condicion = _disparador(json.loads(version.graph_json or "{}"))
        if disparador != ev.kind:
            continue
        ctx = contexto_de_ticket(ticket, ev, data)
        if not evaluate_expression(condicion, ctx):
            continue
        # Un flujo vivo sobre este ticket no se duplica: el segundo evento
        # (otro comentario, otro cambio) no lo vuelve a arrancar.
        vivo = db.query(WorkflowRun.id).filter(
            WorkflowRun.blueprint_id == bp.id,
            WorkflowRun.target_entity_type == "ticket",
            WorkflowRun.target_entity_id == ticket.id,
            WorkflowRun.status.in_([WorkflowRunStatus.running, WorkflowRunStatus.waiting]),
        ).first()
        if vivo:
            continue
        previo = db.info.get("sd_origen")
        db.info["sd_origen"] = ORIGEN_FLUJO
        try:
            start_run(
                db, blueprint_id=bp.id, target_entity_type="ticket",
                target_entity_id=ticket.id, context=ctx,
                organization_id=ticket.organization_id,
            )
            # Los eventos se anotan al volcar: hay que volcar con la marca
            # puesta, o los cambios del flujo saldrian sin origen.
            db.flush()
            lanzados += 1
        finally:
            if previo is None:
                db.info.pop("sd_origen", None)
            else:
                db.info["sd_origen"] = previo
    return lanzados
