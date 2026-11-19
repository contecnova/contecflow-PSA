"""Service Desk — Analytics subdomain router (stats, ITIL metrics, agent performance)."""
from fastapi import APIRouter, Depends, Query, Body
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.core.deps import get_current_user, require_internal_user
from app.core.periodo import CON_HORA, Periodo, periodo
from app.core.responses import APIListResponse, APIResponse
from app.models.user import User
from app.services.service_desk.analytics_service import get_itil_metrics_payload, get_agent_performance_payload
from app.core.errores import ErrorDeDominio
from app.services.service_desk.dashboard_layout_service import WIDGETS, get_layout, reset_layout, save_layout
from app.services.service_desk.incident_intelligence_service import detect_recurring_incidents
from app.core.codigos_de_error import error

router = APIRouter()

# Periodo libre (16-11-2026): tickets con instante (created_at) -> admite hora.
# No son series: solo filtran. `date_from`/`date_to` (fecha final incluida)
# siguen valiendo como alias; `days` también.
_PERIODO_SD = periodo(dias_por_defecto=30, granularidades=CON_HORA, serie=False,
                      alias_dias=("days",), alias_desde=("date_from",), alias_hasta=("date_to",))


@router.get("/metrics/itil", summary="Métricas ITIL: MTTR, FCR, SLA compliance, volumen")
def get_itil_metrics(
    client_id: Optional[str] = Query(None),
    p: Periodo = Depends(_PERIODO_SD),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data=get_itil_metrics_payload(db, p, client_id))


@router.get("/metrics/agent-performance", summary="Rendimiento por agente")
def get_agent_performance(
    p: Periodo = Depends(_PERIODO_SD),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    return APIListResponse.ok(items=get_agent_performance_payload(db, p))


@router.get("/dashboard/layout", summary="Panel del service desk de quien mira (suyo, de la empresa o de serie)")
def get_dashboard_layout(
    role: str = Query("operation", pattern="^(operation|manager|executive)$"),
    db: Session = Depends(get_db), current_user: User = Depends(require_internal_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return APIResponse.ok(data={"role": role, "layout": get_layout(db, org_id, role, current_user.id),
                                "widgets": list(WIDGETS)})


@router.put("/dashboard/layout", summary="Guardar el panel propio o (admin, scope=org) el de la empresa")
def put_dashboard_layout(
    role: str = Query("operation", pattern="^(operation|manager|executive)$"),
    scope: str = Query("user", pattern="^(user|org)$"),
    layout: dict = Body(...),
    db: Session = Depends(get_db), current_user: User = Depends(require_internal_user),
):
    # Mejoras de mercado 16-11-2026: antes cualquier agente cambiaba el panel de
    # toda la empresa. El de la empresa es de administrador; el resto, el suyo.
    org_id = getattr(current_user, "organization_id", None)
    if scope == "org" and getattr(current_user.role, "value", current_user.role) != "admin":
        raise error(403, "solo_admin", detail="Solo un administrador cambia el panel de la empresa")
    return APIResponse.ok(data={"role": role, "layout": save_layout(
        db, org_id, role, layout, None if scope == "org" else current_user.id)})


@router.delete("/dashboard/layout", summary="Volver al panel de la empresa (borra el propio)")
def reset_dashboard_layout(
    role: str = Query("operation", pattern="^(operation|manager|executive)$"),
    db: Session = Depends(get_db), current_user: User = Depends(require_internal_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return APIResponse.ok(data={"role": role, "layout": reset_layout(db, org_id, role, current_user.id)})


@router.get("/incidents/correlation", summary="Correlación de incidentes recurrentes para Problem Management")
def get_incident_correlation(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    return APIListResponse.ok(items=detect_recurring_incidents(db))
