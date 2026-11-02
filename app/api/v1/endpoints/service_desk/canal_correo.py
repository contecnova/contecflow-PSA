"""Service Desk — estado del correo entrante: ultimos mensajes, prueba y lectura."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import require_admin
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.service_desk import InboundMessage, Ticket
from app.models.user import User
from app.services.service_desk import buzones

router = APIRouter(prefix="/inbound", tags=["Service Desk - Correo entrante"])


@router.get("/messages", summary="Últimos correos recibidos y qué se hizo con cada uno")
def ultimos(limit: int = Query(30, ge=1, le=200), db: Session = Depends(get_db),
            _: User = Depends(require_admin)):
    filas = (db.query(InboundMessage, Ticket.number)
             .outerjoin(Ticket, Ticket.id == InboundMessage.ticket_id)
             .order_by(InboundMessage.received_at.desc()).limit(limit).all())
    return APIListResponse.ok(items=[{
        "id": m.id, "received_at": m.received_at.isoformat() if m.received_at else None,
        "sender": m.sender, "outcome": m.outcome, "reason": m.reason,
        "ticket_id": m.ticket_id, "ticket_number": numero, "channel": m.channel,
    } for m, numero in filas])


@router.post("/test", summary="Probar la conexión con el buzón (no procesa nada)")
def probar(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    return APIResponse.ok(data=buzones.probar_buzon(db, user.organization_id))


@router.post("/run", summary="Leer ahora el buzón de la organización")
def leer_ahora(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    return APIResponse.ok(data=buzones.leer_buzon(db, user.organization_id))
