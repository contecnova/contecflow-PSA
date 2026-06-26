"""Service Desk — Predictive Analytics REST API.

Severity prediction, resolution time estimation, and SLA breach probability.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.tenancy import org_scoped_or_404
from app.db.session import get_db
from app.models.user import User
from app.services.service_desk.predictive_analytics_service import (
    get_at_risk_tickets,
    predict_sla_breach,
    predict_ticket,
    run_predictive_scan,
)

router = APIRouter(prefix="/predictive", tags=["Predictive Analytics ITSM"])


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/scan", summary="Ejecutar escaneo predictivo de todos los tickets abiertos")
def predictive_scan(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Re-score all open tickets with predictive models. Same logic as Celery task."""
    return run_predictive_scan(db)


@router.get("/at-risk", summary="Tickets con mayor probabilidad de incumplir SLA")
def at_risk_tickets(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return {"tickets": get_at_risk_tickets(db, limit=limit)}


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
    return {**prediction, "sla_breach": sla}


@router.get("/tickets/{ticket_id}/sla-breach", summary="Probabilidad de incumplimiento de SLA para un ticket")
def sla_breach_prediction(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.service_desk import Ticket

    ticket = org_scoped_or_404(db, Ticket, ticket_id, current_user, detail="Ticket not found")

    return predict_sla_breach(db, ticket)


@router.get("/stats", summary="Estadísticas del modelo predictivo: distribución de riesgos")
def predictive_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aggregate stats on escalation risk and SLA breach across open tickets."""
    from app.models.service_desk import Ticket, TicketStatus
    from sqlalchemy import func

    open_tickets = (
        db.query(Ticket)
        .filter(Ticket.status.notin_(["resolved", "closed"]))
        .all()
    )

    risk_buckets = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    sla_at_risk = 0

    for ticket in open_tickets:
        try:
            pred = predict_ticket(db, ticket)
            severity = pred.get("predicted_severity", "low")
            risk_buckets[severity] = risk_buckets.get(severity, 0) + 1

            sla = predict_sla_breach(db, ticket)
            if sla.get("breach_probability", 0) >= 0.55:
                sla_at_risk += 1
        except Exception:
            pass

    return {
        "open_tickets": len(open_tickets),
        "severity_distribution": risk_buckets,
        "sla_at_risk_count": sla_at_risk,
        "sla_at_risk_pct": round(sla_at_risk / len(open_tickets) * 100, 1) if open_tickets else 0,
    }
