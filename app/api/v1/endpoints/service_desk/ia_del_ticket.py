"""IA del ticket en pantalla (mejoras de mercado 16-11-2026).

Lo que faltaba para el panel de IA del ticket: los candidatos a duplicado
puntuados y explicados. El resto del panel usa rutas que ya existian
(`ai-analyze`, `ai-explain`, `routing-candidates`, `smart-assign`,
`/sd/predictive/tickets/{id}/sla-breach` y `/ai-planning/triage/{id}`).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import require_internal_user
from app.core.responses import APIResponse
from app.db.session import get_db
from app.models.user import User
from app.services.service_desk.duplicados import candidatos_a_duplicado

router = APIRouter(tags=["Service Desk - IA del ticket"])


@router.get("/tickets/{ticket_id}/duplicate-candidates",
            summary="Tickets parecidos de la empresa, puntuados y con el motivo")
def duplicate_candidates(ticket_id: str, db: Session = Depends(get_db),
                         current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data=candidatos_a_duplicado(db, current_user, ticket_id))


@router.get("/tickets/{ticket_id}/customer-context",
            summary="Contexto 360 del solicitante (tickets, cliente, contrato y equipos y licencias de ALM)")
def customer_context(ticket_id: str, db: Session = Depends(get_db),
                     current_user: User = Depends(require_internal_user)):
    from app.services.service_desk.customer_context_service import contexto_del_ticket
    return APIResponse.ok(data=contexto_del_ticket(db, current_user, ticket_id))
