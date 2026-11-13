"""Service Desk — Analytics subdomain router (stats, ITIL metrics, agent performance)."""
from fastapi import APIRouter, Depends, Query, Body
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.core.deps import get_current_user, require_internal_user
from app.core.responses import APIListResponse, APIResponse
from app.models.user import User
from app.services.service_desk.analytics_service import get_itil_metrics_payload, get_agent_performance_payload
from app.services.service_desk.dashboard_layout_service import get_layout, save_layout
from app.services.service_desk.incident_intelligence_service import detect_recurring_incidents

router = APIRouter()


@router.get("/metrics/itil", summary="Métricas ITIL: MTTR, FCR, SLA compliance, volumen")
def get_itil_metrics(
    date_from: Optional[str] = Query(None), date_to: Optional[str] = Query(None),
    client_id: Optional[str] = Query(None),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data=get_itil_metrics_payload(db, date_from, date_to, client_id))


@router.get("/metrics/agent-performance", summary="Rendimiento por agente")
def get_agent_performance(
    date_from: Optional[str] = Query(None), date_to: Optional[str] = Query(None),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    return APIListResponse.ok(items=get_agent_performance_payload(db, date_from, date_to))


@router.get("/dashboard/layout", summary="Layout de dashboard Service Desk por rol")
def get_dashboard_layout(
    role: str = Query("operation", pattern="^(operation|manager|executive)$"),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return APIResponse.ok(data={"role": role, "layout": get_layout(db, org_id, role)})


@router.put("/dashboard/layout", summary="Guardar layout de dashboard Service Desk por rol")
def put_dashboard_layout(
    role: str = Query("operation", pattern="^(operation|manager|executive)$"),
    layout: dict = Body(...),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: dominio: operacion diaria del service desk
):
    org_id = getattr(current_user, "organization_id", None)
    return APIResponse.ok(data={"role": role, "layout": save_layout(db, org_id, role, layout)})


@router.get("/incidents/correlation", summary="Correlación de incidentes recurrentes para Problem Management")
def get_incident_correlation(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    return APIListResponse.ok(items=detect_recurring_incidents(db))
