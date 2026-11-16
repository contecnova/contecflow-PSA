from datetime import timezone

from sqlalchemy.orm import Session

from app.models.service_desk._enums import ESTADOS_DE_TICKET_CERRADOS
from app.models.service_desk import Ticket
import logging

logger = logging.getLogger(__name__)


def get_customer_context_payload(db: Session, requester_id: str) -> dict:
    recent_tickets = db.query(Ticket).filter(
        Ticket.requester_user_id == requester_id
    ).order_by(Ticket.created_at.desc()).limit(10).all()

    open_tickets = [
        t for t in recent_tickets if t.status.value not in ESTADOS_DE_TICKET_CERRADOS
    ]
    resolved = [t for t in recent_tickets if t.resolved_at]

    csat_scores = [t.csat_score for t in recent_tickets if t.csat_score]
    avg_csat = round(sum(csat_scores) / len(csat_scores), 2) if csat_scores else None

    mttr = 0
    if resolved:
        def _norm(dt):
            return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)

        mttr = round(
            sum((_norm(t.resolved_at) - _norm(t.created_at)).total_seconds() / 60 for t in resolved)
            / len(resolved),
            0,
        )

    return {
        "requester_id": requester_id,
        "open_tickets": len(open_tickets),
        "total_tickets_30d": len(recent_tickets),
        "avg_csat": avg_csat,
        "mttr_minutes": mttr,
        "recent_tickets": [
            {
                "id": t.id,
                "number": t.number,
                "title": t.title,
                "status": t.status.value,
                "priority": t.priority.value,
                "created_at": str(t.created_at),
            }
            for t in recent_tickets[:5]
        ],
    }


# ── Contexto del cliente desde el ticket (mejoras de mercado 16-11-2026) ──────

#: Cuantos tickets recientes y recursos se ensenan como mucho en el panel.
TOPE_DEL_PANEL = 10


def contexto_del_ticket(db: Session, current_user, ticket_id: str) -> dict:
    """El contexto 360 del solicitante para el panel del agente.

    Sale del ticket (que el agente tiene que poder ver): quien pide (persona
    o contacto del portal), su cliente y contrato, sus tickets (los abiertos
    contados de verdad, no entre los diez ultimos), su satisfaccion y, si la
    empresa usa Licencias y activos (ALM), los equipos y licencias que tiene
    asignados el solicitante o su cliente ahora mismo.

    Minimo privilegio: sin correo ni telefono de la persona salvo para quien
    puede ver contactos ajenos (`politica_de_visibilidad.ve_contacto_ajeno`).
    """
    from sqlalchemy import func, or_
    from app.services.politica_de_visibilidad import ve_contacto_ajeno
    from app.services.service_desk.scoping import get_scoped_ticket_or_404

    ticket = get_scoped_ticket_or_404(db, current_user, ticket_id)
    filtro = None
    if ticket.requester_user_id:
        filtro = Ticket.requester_user_id == ticket.requester_user_id
    elif ticket.requester_client_id:
        filtro = Ticket.requester_client_id == ticket.requester_client_id
    elif ticket.requester_email:
        filtro = Ticket.requester_email == ticket.requester_email
    base = db.query(Ticket).filter(filtro, Ticket.organization_id == ticket.organization_id) if filtro is not None else None

    abiertos = base.filter(Ticket.status.notin_(ESTADOS_DE_TICKET_CERRADOS)).count() if base is not None else 0
    total = base.count() if base is not None else 0
    csat = base.with_entities(func.avg(Ticket.csat_score)).filter(Ticket.csat_score.isnot(None)).scalar() if base is not None else None
    recientes = base.filter(Ticket.id != ticket.id).order_by(Ticket.created_at.desc()).limit(TOPE_DEL_PANEL).all() if base is not None else []

    persona = {"name": ticket.requester_name, "email": None, "phone": None, "kind": "external"}
    if ticket.requester_user is not None:
        persona.update(name=ticket.requester_user.full_name, kind="user",
                       department=getattr(ticket.requester_user, "department", None))
    elif ticket.requester_client is not None:
        persona.update(name=ticket.requester_client.full_name, kind="portal")
    if ve_contacto_ajeno(current_user):
        persona.update(email=ticket.requester_email, phone=getattr(ticket, "requester_phone", None))

    cliente = None
    if ticket.client_id:
        from app.models.clients import Client
        c = db.get(Client, ticket.client_id)
        if c is not None:
            cliente = {"id": c.id, "name": getattr(c, "name", None)}
    contrato = None
    if ticket.contract_id:
        from app.models.pipeline import Contract
        k = db.get(Contract, ticket.contract_id)
        if k is not None:
            contrato = {"id": k.id, "name": getattr(k, "title", None) or getattr(k, "name", None),
                        "status": getattr(getattr(k, "status", None), "value", getattr(k, "status", None))}

    return {
        "ticket_id": ticket.id, "requester": persona, "client": cliente, "contract": contrato,
        "sla_policy_id": ticket.sla_policy_id,
        "open_tickets": abiertos, "total_tickets": total,
        "avg_csat": round(float(csat), 2) if csat is not None else None,
        "recent_tickets": [{
            "id": t.id, "number": t.number, "title": t.title,
            "status": getattr(t.status, "value", t.status), "priority": getattr(t.priority, "value", t.priority),
            "created_at": t.created_at.isoformat() if t.created_at else None,
        } for t in recientes],
        "alm": _recursos_alm(db, ticket, or_),
    }


def _recursos_alm(db: Session, ticket, or_) -> dict:
    """Equipos y licencias vigentes del solicitante o de su cliente (si hay ALM)."""
    try:
        from app.models.alm import ALMAsignacion, ALMAsset, ALMLicense
    except ImportError:
        return {"available": False, "assets": [], "licenses": []}
    condiciones = []
    if ticket.requester_user_id:
        condiciones.append(ALMAsignacion.holder_user_id == ticket.requester_user_id)
    if ticket.client_id:
        condiciones.append(ALMAsignacion.holder_client_id == ticket.client_id)
    if not condiciones:
        return {"available": True, "assets": [], "licenses": []}
    filas = (db.query(ALMAsignacion)
             .filter(or_(*condiciones), ALMAsignacion.status == "active",
                     ALMAsignacion.organization_id == ticket.organization_id)
             .order_by(ALMAsignacion.assigned_at.desc()).limit(TOPE_DEL_PANEL * 2).all())
    activos, licencias = [], []
    for a in filas:
        if a.resource_type == "asset" and a.asset_id:
            x = db.get(ALMAsset, a.asset_id)
            if x is not None:
                activos.append({"id": x.id, "name": x.name, "asset_tag": x.asset_tag, "serial_number": x.serial_number,
                                "type": getattr(x.type, "value", x.type), "mode": a.mode,
                                "since": a.valid_from.isoformat() if a.valid_from else None})
        elif a.resource_type == "license" and a.license_id:
            x = db.get(ALMLicense, a.license_id)
            if x is not None:
                licencias.append({"id": x.id, "name": x.name, "product_name": x.product_name, "quantity": a.quantity,
                                  "since": a.valid_from.isoformat() if a.valid_from else None,
                                  "until": a.valid_to.isoformat() if a.valid_to else None})
    return {"available": True, "assets": activos[:TOPE_DEL_PANEL], "licenses": licencias[:TOPE_DEL_PANEL]}
