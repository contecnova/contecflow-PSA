"""Service Desk — Predictive Analytics REST API.

Severity prediction, resolution time estimation, and SLA breach probability.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.responses import APIListResponse, APIResponse
from app.core.tenancy import org_scoped_or_404
from app.db.session import get_db
from app.models.user import User
from app.services.service_desk.predictive_analytics_service import (
    estadisticas_predictivas,
    get_at_risk_tickets,
    predict_sla_breach,
    predict_ticket,
    run_predictive_scan,
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/predictive", tags=["Predictive Analytics ITSM"])


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/scan", summary="Ejecutar escaneo predictivo de todos los tickets abiertos")
def predictive_scan(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Re-score all open tickets with predictive models. Same logic as Celery task."""
    return APIResponse.ok(data=run_predictive_scan(db))


@router.get("/at-risk", summary="Tickets con mayor probabilidad de incumplir SLA")
def at_risk_tickets(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIListResponse.ok(items=get_at_risk_tickets(db, limit=limit))


@router.get("/tickets/{ticket_id}", summary="Predicción completa para un ticket específico")
def predict_one_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.service_desk import Ticket

    ticket = org_scoped_or_404(db, Ticket, ticket_id, current_user, detail="Ticket not found")

    prediction = predict_ticket(db, ticket)
    sla = predict_sla_breach(db, ticket)
    return APIResponse.ok(data={**prediction, "sla_breach": sla})


@router.get("/tickets/{ticket_id}/sla-breach", summary="Probabilidad de incumplimiento de SLA para un ticket")
def sla_breach_prediction(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.service_desk import Ticket

    ticket = org_scoped_or_404(db, Ticket, ticket_id, current_user, detail="Ticket not found")

    return APIResponse.ok(data=predict_sla_breach(db, ticket))


@router.get("/stats", summary="Estadísticas del modelo predictivo: distribución de riesgos")
def predictive_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aggregate stats on escalation risk and SLA breach across open tickets.

    Auditoria 2026-08 (hallazgo 22): esto cargaba **todos** los tickets
    abiertos, sin tope ni filtro explicito de organizacion, y gastaba **12
    consultas por ticket** —medido— entre los dos predictores. Con 500 tickets
    abiertos, 6.000 consultas en una peticion. El detalle esta en el comentario
    de `TOPE_DE_TICKETS_ANALIZADOS`.
    """
    return APIResponse.ok(
        data=estadisticas_predictivas(db, current_user))
