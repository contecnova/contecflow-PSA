"""Tareas de cumplimiento de las peticiones del catalogo.

Auditoria 2026-11: el cumplimiento era manual (pasos que un administrador
lanzaba a mano). Ahora un servicio declara sus tareas; al pedirse —o al
aprobarse, si pide aprobacion— cada una nace como ticket hijo en su cola, y
cuando todas estan hechas la peticion se resuelve sola.

Mejoras de mercado (16-11-2026, migracion 174): las tareas son filas de
`sd_service_item_tasks` (antes un JSON en `sd_service_items.fulfillment_tasks`)
con cola, persona, SLA propio y etapa. Las de la misma etapa nacen a la vez;
la siguiente etapa nace cuando terminan todas las de la anterior; al acabar la
ultima, la peticion se resuelve. El ticket hijo guarda su tarea
(`fulfillment_task_id`).

Los hijos llevan `source = "fulfillment"`: los que salen de dividir un ticket
a mano tambien tienen padre, y esos no deben cerrar a nadie.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session, object_session

from app.models.service_desk._enums import ESTADOS_DE_TICKET_CERRADOS
from app.models.service_desk import AgentGroup, ServiceItem, ServiceItemTask, Ticket, TicketStatus
from app.models.user import User
from app.core.codigos_de_error import error

logger = logging.getLogger(__name__)

ORIGEN = "fulfillment"
_HECHOS = ESTADOS_DE_TICKET_CERRADOS
#: Horas de SLA de una tarea: como mucho un año (evita errores de tecleo).
MAX_HORAS_DE_TAREA = 24 * 365


def validar_tareas(db: Session, tareas: Optional[list]) -> Optional[list[dict]]:
    """Las tareas limpias para guardar, o None. 422 si alguna no se puede crear.

    Cada tarea: `title` y `group_id` obligatorios; `description`,
    `assignee_user_id` (de la empresa y activo), `sla_hours` y `stage` (1, 2…)
    opcionales.
    """
    if not tareas:
        return None
    limpias = []
    for i, t in enumerate(tareas):
        t = t or {}
        titulo = str(t.get("title") or "").strip()
        grupo = t.get("group_id")
        if not titulo or not grupo:
            raise error(422, "tarea_sin_titulo_o_cola")
        if db.get(AgentGroup, grupo) is None:
            raise error(422, "tarea_cola_no_existe", tarea=titulo)
        persona = t.get("assignee_user_id") or None
        if persona and db.query(User.id).filter(User.id == persona, User.is_active == True).first() is None:  # noqa: E712
            raise error(422, "tarea_persona_no_valida", tarea=titulo)
        horas = t.get("sla_hours")
        if horas not in (None, ""):
            horas = float(horas)
            if not 0 < horas <= MAX_HORAS_DE_TAREA:
                raise error(422, "tarea_horas_no_validas", tarea=titulo)
        else:
            horas = None
        etapa = int(t.get("stage") or 1)
        if etapa < 1:
            raise error(422, "etapa_empieza_en_1")
        limpias.append({"title": titulo[:300], "group_id": grupo, "assignee_user_id": persona,
                        "description": (str(t.get("description") or "").strip() or None),
                        "sla_hours": horas, "stage": etapa, "sort_order": i})
    return limpias


def guardar_tareas(db: Session, item: ServiceItem, tareas: Optional[list[dict]]) -> None:
    """Sustituye las tareas del servicio por estas (ya validadas)."""
    db.query(ServiceItemTask).filter(ServiceItemTask.service_item_id == item.id).delete(synchronize_session=False)
    for t in tareas or []:
        db.add(ServiceItemTask(organization_id=item.organization_id, service_item_id=item.id, **t))
    item.fulfillment_tasks = None


def _filas(db: Session, item: ServiceItem) -> list[ServiceItemTask]:
    return (db.query(ServiceItemTask).filter(ServiceItemTask.service_item_id == item.id)
            .order_by(ServiceItemTask.stage, ServiceItemTask.sort_order).all())


def tareas_de(item: Optional[ServiceItem]) -> list[dict]:
    """Las tareas del servicio, en orden de etapa."""
    if item is None or item.id is None:
        return []
    db = object_session(item)
    if db is None:
        return []
    return [{"id": f.id, "title": f.title, "description": f.description, "group_id": f.group_id,
             "assignee_user_id": f.assignee_user_id, "sla_hours": f.sla_hours, "stage": f.stage}
            for f in _filas(db, item)]


def _hijos(db: Session, peticion: Ticket) -> list[Ticket]:
    return db.query(Ticket).filter(Ticket.parent_ticket_id == peticion.id, Ticket.source == ORIGEN).all()


def _crear_etapa(db: Session, peticion: Ticket, filas: list[ServiceItemTask]) -> list[Ticket]:
    from app.services.service_desk.ticket_creation_service import build_fulfillment_task
    return [build_fulfillment_task(db, peticion, f.title, f.group_id, tarea=f) for f in filas]


def crear_tareas(db: Session, peticion: Ticket, item: Optional[ServiceItem]) -> list[Ticket]:
    """Crea los tickets de la primera etapa. No hace nada si ya se crearon."""
    if item is None:
        return []
    # Licencias y hardware, fase 4: un ítem de ALM («Pedir licencia», «Pedir
    # equipo») ya aprobado se da de alta solo en ALM (o se pide su compra).
    from app.services.alm_integracion.catalogo import al_cumplir_peticion
    al_cumplir_peticion(db, peticion, item)
    filas = _filas(db, item)
    if not filas or db.query(Ticket.id).filter(Ticket.parent_ticket_id == peticion.id,
                                                Ticket.source == ORIGEN).first():
        return []
    primera = filas[0].stage
    return _crear_etapa(db, peticion, [f for f in filas if f.stage == primera])


def al_terminar_una_tarea(db: Session, tarea: Ticket) -> bool:
    """Al cerrarse una tarea: abre la siguiente etapa si toca o, si era la
    ultima pendiente, resuelve la peticion. Devuelve si la resolvio."""
    from app.schemas.service_desk import TicketUpdateIn
    from app.services.service_desk.ticket_update_service import apply_ticket_update

    if tarea.source != ORIGEN or not tarea.parent_ticket_id:
        return False
    peticion = db.get(Ticket, tarea.parent_ticket_id)
    if peticion is None or getattr(peticion.status, "value", peticion.status) in _HECHOS:
        return False
    hermanas = _hijos(db, peticion)
    if any(getattr(h.status, "value", h.status) not in _HECHOS for h in hermanas):
        return False
    # Auditoria 2026-11-22 (servicios m-z, 4.3): una tarea cancelada no esta
    # hecha. Antes contaba como tal y la peticion se resolvia «completada» (o
    # abria la etapa siguiente) sin haberse hecho el trabajo; ahora la
    # peticion queda abierta y decide el agente.
    if any(getattr(h.status, "value", h.status) == TicketStatus.cancelled.value for h in hermanas):
        logger.info("peticion %s: tareas canceladas; no se resuelve sola", peticion.id)
        return False
    item = db.get(ServiceItem, peticion.service_item_id) if peticion.service_item_id else None
    if item is not None:
        hechas = {h.fulfillment_task_id for h in hermanas if h.fulfillment_task_id}
        pendientes = [f for f in _filas(db, item) if f.id not in hechas]
        if hechas and pendientes:
            # Hay etapas por abrir: la siguiente es la menor que falta.
            siguiente = pendientes[0].stage
            _crear_etapa(db, peticion, [f for f in pendientes if f.stage == siguiente])
            return False
    peticion.resolution = "Petición completada: " + ", ".join(h.title for h in hermanas)
    apply_ticket_update(db, peticion, peticion.id, TicketUpdateIn(status="resolved"), current_user_id=None,
                        old_assigned_to=peticion.assigned_to_user_id, old_support_level=peticion.support_level)
    return True


def estado_de_las_tareas(db: Session, peticion: Ticket) -> list[dict]:
    """Las tareas de una peticion con su estado (las que aun no han nacido, `planned`)."""
    hijos = {h.fulfillment_task_id: h for h in _hijos(db, peticion) if h.fulfillment_task_id}
    item = db.get(ServiceItem, peticion.service_item_id) if peticion.service_item_id else None
    salida = []
    for f in (_filas(db, item) if item is not None else []):
        h = hijos.get(f.id)
        salida.append({
            "task_id": f.id, "title": f.title, "stage": f.stage, "group_id": f.group_id,
            "assignee_user_id": h.assigned_to_user_id if h else f.assignee_user_id,
            "ticket_id": h.id if h else None, "ticket_number": h.number if h else None,
            "status": getattr(h.status, "value", h.status) if h else "planned",
            "sla_resolution_due": h.sla_resolution_due.isoformat() if h and h.sla_resolution_due else None,
            "sla_breached": bool(h.sla_resolution_breached) if h else False,
        })
    return salida
