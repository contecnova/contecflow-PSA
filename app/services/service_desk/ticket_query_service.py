from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models.service_desk._enums import ESTADOS_DE_TICKET_CERRADOS
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
        q = q.filter(Ticket.id.in_(_ids_con_sla_incumplido(q, db)))

    if search:
        # Auditoria 2026-11-22 (4.4): `%` y `_` del texto buscado son literales.
        patron = "%" + escapar_like(search) + "%"
        q = q.filter(or_(
            Ticket.number.ilike(patron, escape="\\"),
            Ticket.title.ilike(patron, escape="\\"),
        ))

    return q


def escapar_like(texto: str) -> str:
    """El texto con `\\`, `%` y `_` escapados para un LIKE con `escape='\\'`."""
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _ids_con_sla_incumplido(q, db: Session) -> list[str]:
    """Ids de los tickets de `q` con el SLA incumplido, descontando las pausas.

    Auditoria 2026-11-22 (servicios m-z, 4.3): el filtro comparaba los
    vencimientos con la hora a pelo, sin las pausas, y contaba como incumplida
    la respuesta de un ticket ya respondido a tiempo. La pausa solo aplaza el
    vencimiento, asi que «vencimiento < ahora» (o la marca ya guardada) es la
    criba en SQL y el veredicto lo da `_vencido`, el mismo de la resolucion:
    pausa acumulada en el calendario del SLA y, si esta en espera, el reloj
    parado desde `sla_paused_at`. Un ticket cerrado no incumple: el SLA se
    mide mientras esta vivo.
    """
    from app.services.service_desk.ticket_update_service import _aware, _vencido
    ahora = datetime.now(timezone.utc)
    candidatos = q.filter(
        Ticket.status.notin_(ESTADOS_DE_TICKET_CERRADOS),
        or_(Ticket.sla_response_breached.is_(True), Ticket.sla_resolution_breached.is_(True),
            Ticket.sla_response_due < ahora, Ticket.sla_resolution_due < ahora),
    ).all()
    ids = []
    for t in candidatos:
        reloj = _aware(t.sla_paused_at) if t.sla_paused_at else ahora
        respuesta = bool(t.sla_response_breached) if t.first_response_at else (
            t.sla_response_due is not None and _vencido(t.sla_response_due, t, reloj, db))
        resolucion = bool(t.sla_resolution_breached) or (
            t.sla_resolution_due is not None and _vencido(t.sla_resolution_due, t, reloj, db))
        if respuesta or resolucion:
            ids.append(t.id)
    return ids
