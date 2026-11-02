"""Tareas de cumplimiento de las peticiones del catalogo.

Auditoria 2026-11: el cumplimiento era manual (pasos que un administrador
lanzaba a mano). Ahora un servicio declara sus tareas; al pedirse —o al
aprobarse, si pide aprobacion— cada una nace como ticket hijo en su cola, y
cuando todas estan hechas la peticion se resuelve sola.

Los hijos llevan `source = "fulfillment"`: los que salen de dividir un ticket
a mano tambien tienen padre, y esos no deben cerrar a nadie.
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.service_desk import AgentGroup, ServiceItem, Ticket

ORIGEN = "fulfillment"
_HECHOS = {"resolved", "closed", "cancelled"}


def validar_tareas(db: Session, tareas: Optional[list]) -> Optional[str]:
    """Las tareas como JSON para guardar, o None. 422 si alguna no se puede crear."""
    if not tareas:
        return None
    limpias = []
    for t in tareas:
        titulo = str((t or {}).get("title") or "").strip()
        grupo = (t or {}).get("group_id")
        if not titulo or not grupo:
            raise HTTPException(422, "Cada tarea necesita título y cola")
        if db.get(AgentGroup, grupo) is None:
            raise HTTPException(422, f"La cola de la tarea «{titulo}» no existe")
        limpias.append({"title": titulo[:300], "group_id": grupo})
    return json.dumps(limpias)


def tareas_de(item: Optional[ServiceItem]) -> list[dict]:
    if item is None or not item.fulfillment_tasks:
        return []
    try:
        valor = json.loads(item.fulfillment_tasks)
    except ValueError:
        return []
    return valor if isinstance(valor, list) else []


def crear_tareas(db: Session, peticion: Ticket, item: Optional[ServiceItem]) -> list[Ticket]:
    """Un ticket hijo por tarea, en su cola. No hace nada si ya se crearon."""
    from app.services.service_desk.ticket_creation_service import build_fulfillment_task

    tareas = tareas_de(item)
    if not tareas or db.query(Ticket.id).filter(Ticket.parent_ticket_id == peticion.id,
                                                Ticket.source == ORIGEN).first():
        return []
    return [build_fulfillment_task(db, peticion, t["title"], t["group_id"]) for t in tareas]


def al_terminar_una_tarea(db: Session, tarea: Ticket) -> bool:
    """Si era la ultima pendiente, resuelve la peticion. Devuelve si la resolvio."""
    from app.schemas.service_desk import TicketUpdateIn
    from app.services.service_desk.ticket_update_service import apply_ticket_update

    if tarea.source != ORIGEN or not tarea.parent_ticket_id:
        return False
    peticion = db.get(Ticket, tarea.parent_ticket_id)
    if peticion is None or getattr(peticion.status, "value", peticion.status) in _HECHOS:
        return False
    hermanas = db.query(Ticket).filter(Ticket.parent_ticket_id == peticion.id, Ticket.source == ORIGEN).all()
    if any(getattr(h.status, "value", h.status) not in _HECHOS for h in hermanas):
        return False
    peticion.resolution = "Petición completada: " + ", ".join(h.title for h in hermanas)
    apply_ticket_update(db, peticion, peticion.id, TicketUpdateIn(status="resolved"), current_user_id=None,
                        old_assigned_to=peticion.assigned_to_user_id, old_support_level=peticion.support_level)
    return True
