"""Estados y ciclos de vida configurables por tipo de ticket
(mejoras de mercado 16-11-2026, migracion 174).

El estado del ticket era un enum fijo (`TicketStatus`). Ahora cada empresa
puede declarar, por tipo de ticket, sus propios estados («Esperando pieza»,
«En revisión de seguridad»…) y, si quiere, que transiciones se permiten.

Compatibilidad: cada estado propio cae en un **estado base** de `TicketStatus`
y el ticket sigue guardando ese estado base en `status`. Por eso el SLA (y sus
pausas en `pending_client`/`pending_third`), el OLA, el UC, los avisos, los
flujos, los informes, el portal y las integraciones siguen igual: leen
`status`. El estado propio va en `sd_tickets.lifecycle_state`.

Sin ciclo de vida para un tipo, todo es como antes: los estados son los base.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.core.errores import ErrorDeDominio
from app.models.service_desk import (
    TicketLifecycle, TicketLifecycleState, TicketLifecycleTransition, TicketStatus,
)

ESTADOS_BASE = tuple(s.value for s in TicketStatus)
TIPOS = ("incident", "service_request", "change", "problem", "question")


def _v(x):
    return getattr(x, "value", x)


def ciclo_del_tipo(db: Session, org_id, ticket_type) -> Optional[TicketLifecycle]:
    q = db.query(TicketLifecycle).filter(TicketLifecycle.ticket_type == _v(ticket_type),
                                         TicketLifecycle.is_active.is_(True))
    q = q.filter(TicketLifecycle.organization_id == org_id)
    return q.first()


def _estados(db: Session, ciclo: TicketLifecycle) -> list[TicketLifecycleState]:
    return (db.query(TicketLifecycleState).filter(TicketLifecycleState.lifecycle_id == ciclo.id)
            .order_by(TicketLifecycleState.sort_order).all())


def _permitida(db: Session, ciclo: TicketLifecycle, desde: Optional[str], hasta: str) -> bool:
    if not ciclo.restrict_transitions or not desde or desde == hasta:
        return True
    return db.query(TicketLifecycleTransition.id).filter(
        TicketLifecycleTransition.lifecycle_id == ciclo.id,
        TicketLifecycleTransition.from_key == desde, TicketLifecycleTransition.to_key == hasta,
    ).first() is not None


def resolver_estado(db: Session, ticket, estado_propio: Optional[str],
                    estado_base: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """(estado propio, estado base) que deja un cambio de estado del ticket.

    - Con `estado_propio`: tiene que existir en el ciclo del tipo del ticket y
      la transicion estar permitida; su base pasa a ser el estado del ticket.
    - Solo con `estado_base` (la API de siempre, el portal, el correo…): el
      primer estado propio con esa base, o ninguno.
    """
    ciclo = ciclo_del_tipo(db, ticket.organization_id, ticket.ticket_type)
    if ciclo is None:
        if estado_propio:
            raise ErrorDeDominio(422, "Este tipo de ticket no tiene ciclo de vida propio")
        return None, estado_base
    estados = _estados(db, ciclo)
    if estado_propio:
        destino = next((e for e in estados if e.key == estado_propio), None)
        if destino is None:
            raise ErrorDeDominio(422, f"Estado desconocido: {estado_propio}")
        if not _permitida(db, ciclo, ticket.lifecycle_state, destino.key):
            raise ErrorDeDominio(409, "El ciclo de vida no permite ese paso")
        return destino.key, destino.base_status
    if estado_base:
        destino = next((e for e in estados if e.base_status == estado_base), None)
        return (destino.key if destino else None), estado_base
    return ticket.lifecycle_state, None


def estado_inicial(db: Session, ticket) -> Optional[str]:
    ciclo = ciclo_del_tipo(db, ticket.organization_id, ticket.ticket_type)
    if ciclo is None:
        return None
    estados = _estados(db, ciclo)
    inicial = next((e for e in estados if e.is_initial), None) or \
        next((e for e in estados if e.base_status == _v(ticket.status)), None)
    return inicial.key if inicial else None


# ── Lectura y mantenimiento ───────────────────────────────────────────────────

def serializar(db: Session, ciclo: TicketLifecycle) -> dict:
    return {
        "id": ciclo.id, "ticket_type": ciclo.ticket_type, "name": ciclo.name, "is_active": ciclo.is_active,
        "restrict_transitions": ciclo.restrict_transitions,
        "states": [{"key": e.key, "label": e.label, "base_status": e.base_status, "is_initial": e.is_initial,
                    "color": e.color, "sort_order": e.sort_order} for e in _estados(db, ciclo)],
        "transitions": [{"from_key": t.from_key, "to_key": t.to_key} for t in db.query(TicketLifecycleTransition)
                        .filter(TicketLifecycleTransition.lifecycle_id == ciclo.id).all()],
    }


def listar(db: Session, org_id) -> list[dict]:
    return [serializar(db, c) for c in db.query(TicketLifecycle).filter(TicketLifecycle.organization_id == org_id)
            .order_by(TicketLifecycle.ticket_type).all()]


def opciones_del_ticket(db: Session, ticket) -> dict:
    """Los estados a los que puede pasar el ticket (para la pantalla)."""
    ciclo = ciclo_del_tipo(db, ticket.organization_id, ticket.ticket_type)
    if ciclo is None:
        return {"lifecycle": None, "current": None, "states": []}
    estados = _estados(db, ciclo)
    actual = ticket.lifecycle_state
    return {
        "lifecycle": ciclo.name, "current": actual,
        "states": [{"key": e.key, "label": e.label, "base_status": e.base_status, "color": e.color,
                    "allowed": _permitida(db, ciclo, actual, e.key)} for e in estados],
    }


def guardar(db: Session, org_id, datos: dict) -> dict:
    """Crea o sustituye el ciclo de vida de un tipo de ticket (estados y transiciones)."""
    tipo = datos.get("ticket_type")
    if tipo not in TIPOS:
        raise ErrorDeDominio(422, "Tipo de ticket no válido")
    estados = datos.get("states") or []
    if not estados:
        raise ErrorDeDominio(422, "Un ciclo de vida necesita al menos un estado")
    claves = [str(e.get("key") or "").strip() for e in estados]
    if any(not k for k in claves) or len(set(claves)) != len(claves):
        raise ErrorDeDominio(422, "Cada estado necesita una clave única")
    for e in estados:
        if e.get("base_status") not in ESTADOS_BASE:
            raise ErrorDeDominio(422, f"Estado base no válido: {e.get('base_status')}")
        if not str(e.get("label") or "").strip():
            raise ErrorDeDominio(422, "Cada estado necesita un nombre")
    # Que ningun estado base quede sin estado propio en el que caer seria un
    # ciclo incompleto: el portal, el correo o un flujo pueden poner cualquiera.
    transiciones = datos.get("transitions") or []
    for t in transiciones:
        if t.get("from_key") not in claves or t.get("to_key") not in claves:
            raise ErrorDeDominio(422, "Una transición usa un estado que no existe")

    ciclo = db.query(TicketLifecycle).filter(TicketLifecycle.organization_id == org_id,
                                             TicketLifecycle.ticket_type == tipo).first()
    if ciclo is None:
        ciclo = TicketLifecycle(organization_id=org_id, ticket_type=tipo, name=str(datos.get("name") or tipo)[:150])
        db.add(ciclo)
        db.flush()
    else:
        ciclo.name = str(datos.get("name") or ciclo.name)[:150]
        db.query(TicketLifecycleState).filter(TicketLifecycleState.lifecycle_id == ciclo.id).delete()
        db.query(TicketLifecycleTransition).filter(TicketLifecycleTransition.lifecycle_id == ciclo.id).delete()
    ciclo.is_active = bool(datos.get("is_active", True))
    ciclo.restrict_transitions = bool(datos.get("restrict_transitions", False))
    hay_inicial = any(e.get("is_initial") for e in estados)
    for i, e in enumerate(estados):
        db.add(TicketLifecycleState(
            organization_id=org_id, lifecycle_id=ciclo.id, key=claves[i][:50], label=str(e["label"]).strip()[:100],
            base_status=e["base_status"], is_initial=bool(e.get("is_initial")) or (not hay_inicial and i == 0),
            color=(e.get("color") or None), sort_order=i))
    for t in transiciones:
        db.add(TicketLifecycleTransition(organization_id=org_id, lifecycle_id=ciclo.id,
                                         from_key=t["from_key"], to_key=t["to_key"]))
    db.commit()
    return serializar(db, ciclo)


def borrar(db: Session, org_id, ciclo_id: str) -> None:
    ciclo = db.query(TicketLifecycle).filter(TicketLifecycle.id == ciclo_id,
                                             TicketLifecycle.organization_id == org_id).first()
    if ciclo is None:
        raise ErrorDeDominio(404, "Ciclo de vida no encontrado")
    db.delete(ciclo)
    db.commit()
