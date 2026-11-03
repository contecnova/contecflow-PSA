from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models.service_desk import Ticket
from app.models.user import User
from app.services.service_desk.status_compat import normalize_ticket_status
import logging

logger = logging.getLogger(__name__)


#: Filtro de lista → columna de igualdad. Auditoría 2026-09 (hallazgo 18): eran
#: seis `if` idénticos seguidos. Como tabla se ve de un vistazo qué se puede
#: filtrar, que es lo que hace falta para escribir el cliente.
#:
#: `status`, `sla_breached` y `search` no están aquí: el primero se normaliza
#: antes, y los otros dos no son igualdad.
_FILTROS_DE_IGUALDAD: tuple[tuple[str, str], ...] = (
    ("priority", "priority"),
    ("ticket_type", "ticket_type"),
    ("assigned_to", "assigned_to_user_id"),
    ("group_id", "assigned_group_id"),
    ("project_id", "project_id"),
    ("support_level", "support_level"),
)


def _acotar_a_lo_visible(q, db: Session, current_user: User):
    """Reduce la consulta a los tickets que este usuario puede ver.

    Auditoria 2026-11: era una segunda copia del acotado, distinta del de
    `scoping.scope_ticket_query` —aqui un empleado no veia ni los tickets que
    tenia asignados, y un administrador no veia los del portal o del correo
    sin agente—. El listado y el detalle tienen que decir lo mismo: una sola
    regla.
    """
    from app.services.service_desk.scoping import scope_ticket_query
    return scope_ticket_query(q, db, current_user)


def build_ticket_list_query(
    db: Session,
    current_user: User,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    ticket_type: Optional[str] = None,
    assigned_to: Optional[str] = None,
    group_id: Optional[str] = None,
    project_id: Optional[str] = None,
    support_level: Optional[str] = None,
    sla_breached: Optional[bool] = None,
    search: Optional[str] = None,
):
    """Consulta de tickets del service desk, acotada y con todos los filtros."""
    valores = locals()

    q = db.query(Ticket).options(
        joinedload(Ticket.requester_user),
        joinedload(Ticket.requester_client),
        joinedload(Ticket.assigned_to),
        joinedload(Ticket.assigned_group),
        joinedload(Ticket.project),
        joinedload(Ticket.ci),
        joinedload(Ticket.client),
    )
    q = _acotar_a_lo_visible(q, db, current_user)

    # Varios estados separados por comas (el Kanban pide solo los vivos).
    estados = [e for e in (normalize_ticket_status(x.strip()) for x in (status or "").split(",")) if e]
    if len(estados) == 1:
        q = q.filter(Ticket.status == estados[0])
    elif estados:
        q = q.filter(Ticket.status.in_(estados))

    for parametro, columna in _FILTROS_DE_IGUALDAD:
        if valores.get(parametro):
            q = q.filter(getattr(Ticket, columna) == valores[parametro])

    if sla_breached:
        # Un ticket cerrado no incumple: el SLA se mide mientras está vivo.
        ahora = datetime.now(timezone.utc)
        q = q.filter(
            Ticket.status.notin_(["resolved", "closed", "cancelled"]),
            or_(Ticket.sla_response_due < ahora, Ticket.sla_resolution_due < ahora),
        )

    if search:
        q = q.filter(or_(
            Ticket.number.ilike(f"%{search}%"),
            Ticket.title.ilike(f"%{search}%"),
        ))

    return q
