"""Service Desk — Analytics subdomain router (stats, ITIL metrics, agent performance)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.services.service_desk.stats_service import get_service_desk_stats
from app.services.service_desk.analytics_service import get_itil_metrics_payload, get_agent_performance_payload

router = APIRouter()


@router.get("/stats", summary="Estadísticas del service desk")
def get_stats(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return get_service_desk_stats(db, current_user, days)


@router.get("/metrics/itil", summary="Métricas ITIL: MTTR, FCR, SLA compliance, volumen")
def get_itil_metrics(
    date_from: Optional[str] = Query(None), date_to: Optional[str] = Query(None),
    client_id: Optional[str] = Query(None),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    return get_itil_metrics_payload(db, date_from, date_to, client_id)


@router.get("/metrics/agent-performance", summary="Rendimiento por agente")
def get_agent_performance(
    date_from: Optional[str] = Query(None), date_to: Optional[str] = Query(None),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    return get_agent_performance_payload(db, date_from, date_to)
