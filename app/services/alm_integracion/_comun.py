"""Piezas comunes de la integración de ALM (fase 4): ajustes, tickets enlazados
y el acceso a las funciones del ciclo de ALM (fases 1 y 3).

Regla: la fase 4 NO escribe asignaciones, préstamos ni actas por su cuenta.
Todo pasa por `app.services.alm_asignaciones` (asignar, prestar, liberar,
devolver, liberar_licencias_de_usuario, equipos_de_usuario,
asignaciones_de_usuario) y `app.services.alm_actas`; aquí solo se agrupan los
usos para que el resto del paquete no repita importaciones ni detalles.
"""
from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from datetime import date
from typing import Iterator, Optional

from sqlalchemy.orm import Session

from app.core import timeutil
from app.core.errores import ErrorDeDominio

logger = logging.getLogger(__name__)

#: Políticas para el equipo sin devolver al dar de baja.
POLITICAS_DE_PENDIENTES = ("avisar", "confirmar", "bloquear")

#: Origen de los tickets que abre la integración (filtrable en el service desk).
ORIGEN_DE_TICKET = "alm"

#: Tipos de recurso con los que se enlaza un ticket (`Ticket.linked_resource_type`).
ENLACE_ACTIVO, ENLACE_LICENCIA = "asset", "license"


# ── Ajustes en caliente (grupo `licencias_integracion`) ───────────────────────

def ajuste_int(db: Session, clave: str, org_id: Optional[str]) -> int:
    from app.services import settings_service as ss
    return int(ss.get_runtime_int(db, clave, org_id) or 0)


def ajuste_str(db: Session, clave: str, org_id: Optional[str]) -> str:
    from app.services import settings_service as ss
    return (ss.get_runtime_str(db, clave, org_id) or "").strip()


def ajuste_bool(db: Session, clave: str, org_id: Optional[str]) -> bool:
    from app.services import settings_service as ss
    return bool(ss.get_runtime_bool(db, clave, org_id))


def politica_de_pendientes(db: Session, org_id: Optional[str]) -> str:
    valor = ajuste_str(db, "ALM_OFFBOARDING_PENDING_ASSETS", org_id).lower()
    return valor if valor in POLITICAS_DE_PENDIENTES else POLITICAS_DE_PENDIENTES[0]


def roles_de_respaldo(db: Session, org_id: Optional[str]) -> list[str]:
    return [r.strip() for r in ajuste_str(db, "ALM_KIT_FALLBACK_ROLES", org_id).split(",") if r.strip()]


# ── Contexto de organización ──────────────────────────────────────────────────

@contextmanager
def en_organizacion(db: Session, org_id: Optional[str]) -> Iterator[None]:
    """Trabaja como la organización de la persona (SCIM y trabajos de fondo
    llegan sin contexto publicado): las lecturas se acotan y las filas nuevas
    nacen en ella."""
    from app.services.service_desk.ticket_events import como_organizacion
    if not org_id or db.info.get("organization_id") == org_id:
        yield
        return
    with como_organizacion(db, org_id):
        yield


# ── Tickets enlazados a un activo o licencia ──────────────────────────────────

def abrir_ticket(db: Session, *, titulo: str, descripcion: str, solicitante_id: Optional[str],
                 tipo: str = "service_request", grupo_ajuste: Optional[str] = None,
                 org_id: Optional[str] = None, enlace: Optional[tuple[str, str]] = None,
                 service_item_id: Optional[str] = None, project_id: Optional[str] = None,
                 ci_id: Optional[str] = None, campos: Optional[dict] = None, urgencia: str = "medium"):
    """Ticket por el camino normal del service desk (numerador, SLA, enrutado,
    asignación, aprobación del catálogo y cumplimiento), enlazado al recurso.

    ``grupo_ajuste``: el ajuste que dice la cola (vacío: reglas de enrutado).
    ``enlace``: (``asset``|``license``, id) en `linked_resource_type/_id`.
    No confirma.
    """
    from app.schemas.service_desk import TicketCreateIn
    from app.services.service_desk.ticket_creation_service import build_internal_ticket

    grupo = ajuste_str(db, grupo_ajuste, org_id) if grupo_ajuste else ""
    if grupo:
        from app.models.service_desk import AgentGroup
        if db.get(AgentGroup, grupo) is None:
            logger.warning("ALM: la cola %s del ajuste %s no existe; se enruta por reglas", grupo, grupo_ajuste)
            grupo = ""
    payload = TicketCreateIn(
        title=titulo[:300], description=descripcion, ticket_type=tipo, urgency=urgencia,
        service_item_id=service_item_id, project_id=project_id, ci_id=ci_id,
        assigned_group_id=grupo or None, source=ORIGEN_DE_TICKET, dynamic_fields=campos or None,
    )
    ticket = build_internal_ticket(db, payload, solicitante_id)
    if org_id and not ticket.organization_id:
        ticket.organization_id = org_id
    if enlace:
        ticket.linked_resource_type, ticket.linked_resource_id = enlace
    db.flush()
    return ticket


def enlazar_ticket(db: Session, ticket_id: Optional[str], tipo: str, recurso_id: Optional[str]) -> None:
    """Deja el ticket apuntando al recurso (si no apuntaba ya a otro)."""
    if not ticket_id or not recurso_id:
        return
    from app.models.service_desk import Ticket
    t = db.get(Ticket, ticket_id)
    if t is not None and not t.linked_resource_id:
        t.linked_resource_type, t.linked_resource_id = tipo, recurso_id


def tickets_del_recurso(db: Session, tipo: str, recurso_id: str, solo_abiertos: bool = False) -> list[dict]:
    """El otro sentido del enlace: los tickets de un activo o licencia."""
    from app.models.service_desk import Ticket
    from app.models.service_desk._enums import ESTADOS_DE_TICKET_CERRADOS
    q = db.query(Ticket).filter(Ticket.linked_resource_type == tipo, Ticket.linked_resource_id == recurso_id)
    filas = q.order_by(Ticket.created_at.desc()).all()
    salida = []
    for t in filas:
        estado = getattr(t.status, "value", t.status)
        if solo_abiertos and estado in ESTADOS_DE_TICKET_CERRADOS:
            continue
        salida.append(serializar_ticket(t))
    return salida


def recurso_del_ticket(db: Session, ticket) -> Optional[dict]:
    """El sentido ticket → recurso: el activo o la licencia a la que apunta."""
    tipo, rid = ticket.linked_resource_type, ticket.linked_resource_id
    if tipo not in (ENLACE_ACTIVO, ENLACE_LICENCIA) or not rid:
        return None
    if tipo == ENLACE_ACTIVO:
        from app.models.alm import ALMAsset
        a = db.get(ALMAsset, rid)
        if a is None:
            return None
        from app.models.user import User
        titular = db.get(User, a.assigned_to_id) if a.assigned_to_id else None
        return {"tipo": tipo, "id": a.id, "name": a.name, "asset_tag": a.asset_tag,
                "serial_number": a.serial_number, "status": getattr(a.status, "value", a.status),
                "type": getattr(a.type, "value", a.type), "holder_name": titular.full_name if titular else None}
    from app.models.alm import ALMLicense
    lic = db.get(ALMLicense, rid)
    if lic is None:
        return None
    return {"tipo": tipo, "id": lic.id, "name": lic.name, "product_name": lic.product_name,
            "status": getattr(lic.status, "value", lic.status)}


def serializar_ticket(t) -> dict:
    return {
        "id": t.id, "number": t.number, "title": t.title,
        "status": getattr(t.status, "value", t.status),
        "ticket_type": getattr(t.ticket_type, "value", t.ticket_type),
        "approval_status": getattr(t, "approval_status", None),
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def ticket_cerrado(t) -> bool:
    from app.models.service_desk._enums import ESTADOS_DE_TICKET_CERRADOS
    return getattr(t.status, "value", t.status) in ESTADOS_DE_TICKET_CERRADOS


def resolver_ticket(db: Session, ticket_id: Optional[str], resolucion: str, actor_id: Optional[str]) -> None:
    """Resuelve el ticket por el camino normal (eventos, SLA, aviso al solicitante)."""
    if not ticket_id:
        return
    from app.models.service_desk import Ticket
    from app.schemas.service_desk import TicketUpdateIn
    from app.services.service_desk.ticket_update_service import apply_ticket_update
    t = db.get(Ticket, ticket_id)
    if t is None or ticket_cerrado(t):
        return
    t.resolution = resolucion
    apply_ticket_update(db, t, t.id, TicketUpdateIn(status="resolved"), current_user_id=actor_id,
                        old_assigned_to=t.assigned_to_user_id, old_support_level=t.support_level)


# ── Ciclo de ALM (fases 1 y 3) ────────────────────────────────────────────────

def asignaciones():
    """El servicio de asignación universal de las fases 1 y 3."""
    from app.services import alm_asignaciones
    return alm_asignaciones


def actas():
    """El servicio de actas de entrega y devolución (fase 1), o None si aún no está."""
    try:
        from app.services import alm_actas
    except ImportError:  # pragma: no cover - solo mientras la fase 1 no lo publique
        return None
    return alm_actas


def acta_de(db: Session, acta_id: Optional[str]):
    if not acta_id:
        return None
    from app.models.alm import ALMActa
    return db.get(ALMActa, acta_id)


def ultima_acta(db: Session, asignacion_id: str, tipo: str):
    """El acta (``delivery`` | ``return``) más reciente de una asignación."""
    from app.models.alm import ALMActa
    return (db.query(ALMActa).filter(ALMActa.assignment_id == asignacion_id, ALMActa.kind == tipo)
            .order_by(ALMActa.created_at.desc()).first())


def serializar_acta(a) -> Optional[dict]:
    if a is None:
        return None
    return {
        "id": a.id, "kind": a.kind, "status": a.status, "asset_id": a.asset_id,
        "asset_name": a.asset.name if a.asset is not None else None,
        "assignment_id": a.assignment_id, "condition": a.condition,
        "envelope_id": a.envelope_id, "document_id": a.document_id,
        "signed_at": a.signed_at.isoformat() if a.signed_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def hoy() -> date:
    return timeutil.today()


def json_o(valor, defecto):
    if not valor:
        return defecto
    try:
        return json.loads(valor)
    except ValueError:
        return defecto


def exigir(condicion: bool, codigo: str, estado: int = 422) -> None:
    """Errores con código `almint_*`: la interfaz los traduce (`almint.err_<código>`)."""
    if not condicion:
        raise ErrorDeDominio(estado, codigo)
