"""
Analytics engine – flexible data extraction for the reports builder.
Every query returns rows + metadata so the frontend can render any chart type.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from typing import Optional
from datetime import date, timedelta
import json
import time
import logging
from threading import Lock

from app.db.session import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.project import Project
from app.models.task import Task
from app.models.imputation import Imputation
from app.models.resources import Absence, ChangeRequest, Deliverable
from app.models.bookings import ResourceBooking, BookingType
from app.core.config import settings
from app.api.v1.endpoints.analytics_legacy_metrics import LEGACY_METRIC_IDS, run_legacy_metric
# New modular metrics system
from app.services.metrics import METRICS_REGISTRY as MODULAR_METRICS_REGISTRY
from app.services import analytics_service as _svc

router = APIRouter()

logger = logging.getLogger(__name__)

# Cache/helpers delegated to analytics_service
_get_metric_cache_ttl = _svc.get_metric_cache_ttl
_cache_get   = _svc.cache_get
_cache_set   = _svc.cache_set
_analytics_cache_key = _svc.build_cache_key


def _get_redis_cache_client():
    return _svc._get_redis_client()


def _cache_get(key: str) -> Optional[dict]:
    return _svc.cache_get(key)


def _cache_set(key: str, value: dict, ttl_seconds: int = None) -> None:
    _svc.cache_set(key, value, ttl_seconds)


def _analytics_cache_key(namespace: str, current_user: User, payload: dict) -> str:
    return _svc.build_cache_key(namespace, current_user, payload)


# ── Available dimensions & metrics catalogue ──────────────────────────────────

CATALOGUE = {
    "hours_by_person": {
        "label": "Horas por persona",
        "category": "Horas",
        "description": "Total de horas imputadas agrupadas por persona",
        "x_label": "Persona",
        "y_label": "Horas",
        "default_chart": "bar",
    },
    "hours_by_project": {
        "label": "Horas por proyecto",
        "category": "Horas",
        "description": "Total de horas por proyecto",
        "x_label": "Proyecto",
        "y_label": "Horas",
        "default_chart": "bar",
    },
    "hours_by_week": {
        "label": "Horas por semana",
        "category": "Horas",
        "description": "Evolución semanal de horas imputadas",
        "x_label": "Semana",
        "y_label": "Horas",
        "default_chart": "line",
    },
    "hours_by_month": {
        "label": "Horas por mes",
        "category": "Horas",
        "description": "Evolución mensual de horas imputadas",
        "x_label": "Mes",
        "y_label": "Horas",
        "default_chart": "line",
    },
    "hours_by_department": {
        "label": "Horas por departamento",
        "category": "Horas",
        "description": "Horas totales agrupadas por departamento",
        "x_label": "Departamento",
        "y_label": "Horas",
        "default_chart": "pie",
    },
    "hours_billable_vs_internal": {
        "label": "Facturables vs Internas",
        "category": "Horas",
        "description": "Comparativa de horas facturables contra internas por persona o proyecto",
        "x_label": "Persona / Proyecto",
        "y_label": "Horas",
        "default_chart": "bar_stacked",
    },
    "cost_by_project": {
        "label": "Coste por proyecto",
        "category": "Costes",
        "description": "Coste interno acumulado por proyecto",
        "x_label": "Proyecto",
        "y_label": "Coste (€)",
        "default_chart": "bar",
    },
    "cost_by_person": {
        "label": "Coste por persona",
        "category": "Costes",
        "description": "Coste total por persona en el período",
        "x_label": "Persona",
        "y_label": "Coste (€)",
        "default_chart": "bar",
    },
    "cost_by_month": {
        "label": "Coste mensual",
        "category": "Costes",
        "description": "Evolución mensual del coste interno",
        "x_label": "Mes",
        "y_label": "Coste (€)",
        "default_chart": "line",
    },
    "margin_by_project": {
        "label": "Margen por proyecto",
        "category": "Rentabilidad",
        "description": "Ingresos, costes y margen bruto por proyecto",
        "x_label": "Proyecto",
        "y_label": "€",
        "default_chart": "bar_grouped",
    },
    "margin_evolution": {
        "label": "Evolución del margen",
        "category": "Rentabilidad",
        "description": "Evolución mensual del margen",
        "x_label": "Mes",
        "y_label": "€",
        "default_chart": "line",
    },
    "budget_consumption": {
        "label": "Consumo de presupuesto",
        "category": "Rentabilidad",
        "description": "% de presupuesto consumido por proyecto",
        "x_label": "Proyecto",
        "y_label": "% Consumido",
        "default_chart": "bar",
    },
    "load_by_person": {
        "label": "Carga por persona",
        "category": "Capacidad",
        "description": "% de carga semanal por persona",
        "x_label": "Semana",
        "y_label": "% Carga",
        "default_chart": "line",
    },
    "load_by_week": {
        "label": "Carga media del equipo por semana",
        "category": "Capacidad",
        "description": "Carga media del equipo semana a semana",
        "x_label": "Semana",
        "y_label": "% Carga",
        "default_chart": "line",
    },
    "tasks_by_status": {
        "label": "Tareas por estado",
        "category": "Proyectos",
        "description": "Distribución de tareas por estado",
        "x_label": "Estado",
        "y_label": "Tareas",
        "default_chart": "pie",
    },
    "tasks_by_project": {
        "label": "Tareas por proyecto",
        "category": "Proyectos",
        "description": "Número de tareas por proyecto",
        "x_label": "Proyecto",
        "y_label": "Tareas",
        "default_chart": "bar",
    },
    "projects_by_status": {
        "label": "Proyectos por estado",
        "category": "Proyectos",
        "description": "Distribución de proyectos por estado",
        "x_label": "Estado",
        "y_label": "Proyectos",
        "default_chart": "pie",
    },
    "projects_by_type": {
        "label": "Proyectos por tipo",
        "category": "Proyectos",
        "description": "Distribución de proyectos por tipo (consulting, development, maintenance, etc)",
        "x_label": "Tipo",
        "y_label": "Proyectos",
        "default_chart": "pie",
    },
    "deliverables_status": {
        "label": "Estado de entregables",
        "category": "Proyectos",
        "description": "Entregables por estado en todos los proyectos",
        "x_label": "Estado",
        "y_label": "Entregables",
        "default_chart": "pie",
    },
    "risks_by_level": {
        "label": "Riesgos por nivel",
        "category": "Proyectos",
        "description": "Distribución de riesgos abiertos por nivel",
        "x_label": "Nivel",
        "y_label": "Riesgos",
        "default_chart": "pie",
    },
    "pipeline_by_stage": {
        "label": "Pipeline por etapa",
        "category": "Negocio",
        "description": "Valor y número de oportunidades por etapa",
        "x_label": "Etapa",
        "y_label": "€ Ponderado",
        "default_chart": "bar",
    },
    "pipeline_evolution": {
        "label": "Evolución del pipeline",
        "category": "Negocio",
        "description": "Evolución mensual del valor del pipeline",
        "x_label": "Mes",
        "y_label": "€",
        "default_chart": "line",
    },
    "absences_by_type": {
        "label": "Ausencias por tipo",
        "category": "RRHH",
        "description": "Días de ausencia por tipo en el período",
        "x_label": "Tipo",
        "y_label": "Días",
        "default_chart": "pie",
    },
    "absences_by_person": {
        "label": "Ausencias por persona",
        "category": "RRHH",
        "description": "Días de ausencia por empleado",
        "x_label": "Persona",
        "y_label": "Días",
        "default_chart": "bar",
    },
    "absences_by_month": {
        "label": "Ausencias por mes",
        "category": "RRHH",
        "description": "Días de ausencia acumulados por mes",
        "x_label": "Mes",
        "y_label": "Días",
        "default_chart": "line",
    },
    "productivity_by_person": {
        "label": "Productividad por persona",
        "category": "RRHH",
        "description": "Horas reales vs capacidad teórica por persona",
        "x_label": "Persona",
        "y_label": "Horas",
        "default_chart": "bar_grouped",
    },
    "change_requests_status": {
        "label": "Control de cambios",
        "category": "Proyectos",
        "description": "CRs por estado e impacto acumulado",
        "x_label": "Estado",
        "y_label": "CRs",
        "default_chart": "bar",
    },
    "hours_heatmap": {
        "label": "Heatmap de horas (persona × semana)",
        "category": "Horas",
        "description": "Mapa de calor de horas imputadas por persona y semana",
        "x_label": "Semana",
        "y_label": "Persona",
        "default_chart": "heatmap",
    },
    "cost_vs_budget": {
        "label": "Coste real vs Presupuesto",
        "category": "Rentabilidad",
        "description": "Comparativa coste acumulado vs presupuesto por proyecto",
        "x_label": "Proyecto",
        "y_label": "€",
        "default_chart": "bar_grouped",
    },
    # ── Service Desk ─────────────────────────────────────────────────────────
    "tickets_by_status": {
        "label": "Tickets por estado",
        "category": "Service Desk",
        "description": "Distribución de tickets por estado actual",
        "x_label": "Estado", "y_label": "Tickets", "default_chart": "pie",
    },
    "tickets_by_type": {
        "label": "Tickets por tipo",
        "category": "Service Desk",
        "description": "Incidencias, solicitudes, consultas y cambios",
        "x_label": "Tipo", "y_label": "Tickets", "default_chart": "bar",
    },
    "tickets_by_agent": {
        "label": "Tickets por agente",
        "category": "Service Desk",
        "description": "Carga de tickets abiertos y resueltos por agente",
        "x_label": "Agente", "y_label": "Tickets", "default_chart": "bar_grouped",
    },
    "tickets_by_priority": {
        "label": "Tickets por prioridad",
        "category": "Service Desk",
        "description": "Distribución de tickets por nivel de prioridad",
        "x_label": "Prioridad", "y_label": "Tickets", "default_chart": "bar",
    },
    "ticket_resolution_time": {
        "label": "Tiempo medio de resolución",
        "category": "Service Desk",
        "description": "Tiempo medio de resolución de tickets en horas, por tipo o agente",
        "x_label": "Tipo", "y_label": "Horas", "default_chart": "bar",
    },
    "ticket_sla_compliance": {
        "label": "Cumplimiento de SLA",
        "category": "Service Desk",
        "description": "% de tickets que cumplen SLA de respuesta y resolución por mes",
        "x_label": "Mes", "y_label": "% Cumplimiento", "default_chart": "line",
    },
    "ticket_volume_trend": {
        "label": "Tendencia de volumen de tickets",
        "category": "Service Desk",
        "description": "Tickets abiertos vs cerrados mes a mes",
        "x_label": "Mes", "y_label": "Tickets", "default_chart": "line",
    },
    "ticket_csat": {
        "label": "Satisfacción del cliente (CSAT)",
        "category": "Service Desk",
        "description": "Puntuación media de satisfacción por agente o mes",
        "x_label": "Agente", "y_label": "CSAT (1-5)", "default_chart": "bar",
    },
    # ── Sprints / Agilidad ───────────────────────────────────────────────────
    "sprint_velocity": {
        "label": "Velocidad de sprint",
        "category": "Agilidad",
        "description": "Story points completados por sprint",
        "x_label": "Sprint", "y_label": "Story Points", "default_chart": "bar",
    },
    "sprint_completion_rate": {
        "label": "Tasa de completitud de sprint",
        "category": "Agilidad",
        "description": "% de story points completados respecto al planificado",
        "x_label": "Sprint", "y_label": "% Completado", "default_chart": "line",
    },
    "tasks_lead_time": {
        "label": "Lead time de tareas",
        "category": "Agilidad",
        "description": "Tiempo medio desde creación hasta completado por proyecto",
        "x_label": "Proyecto", "y_label": "Días", "default_chart": "bar",
    },
    "tasks_blocked_by_project": {
        "label": "Tareas bloqueadas",
        "category": "Agilidad",
        "description": "Número de tareas bloqueadas por proyecto",
        "x_label": "Proyecto", "y_label": "Tareas bloqueadas", "default_chart": "bar",
    },
    "tasks_overdue": {
        "label": "Tareas con retraso",
        "category": "Agilidad",
        "description": "Tareas que han superado su fecha límite sin completarse",
        "x_label": "Proyecto", "y_label": "Tareas retrasadas", "default_chart": "bar",
    },
    "tasks_by_assignee": {
        "label": "Tareas por persona",
        "category": "Agilidad",
        "description": "Distribución de tareas activas por miembro del equipo",
        "x_label": "Persona", "y_label": "Tareas", "default_chart": "bar_grouped",
    },
    # ── Clientes / Negocio ───────────────────────────────────────────────────
    "revenue_by_client": {
        "label": "Ingresos por cliente",
        "category": "Negocio",
        "description": "Facturación total por cliente en el período",
        "x_label": "Cliente", "y_label": "€", "default_chart": "bar",
    },
    "projects_by_client": {
        "label": "Proyectos por cliente",
        "category": "Negocio",
        "description": "Número de proyectos activos y completados por cliente",
        "x_label": "Cliente", "y_label": "Proyectos", "default_chart": "bar_grouped",
    },
    "contracts_by_status": {
        "label": "Contratos por estado",
        "category": "Negocio",
        "description": "Distribución de contratos por estado y valor acumulado",
        "x_label": "Estado", "y_label": "€", "default_chart": "bar",
    },
    "win_rate_evolution": {
        "label": "Tasa de éxito comercial",
        "category": "Negocio",
        "description": "% de oportunidades ganadas vs cerradas por mes",
        "x_label": "Mes", "y_label": "% Win rate", "default_chart": "line",
    },
    # ── ALM ──────────────────────────────────────────────────────────────────
    "license_cost_by_vendor": {
        "label": "Coste de licencias por proveedor",
        "category": "ALM",
        "description": "Gasto anual en licencias agrupado por proveedor",
        "x_label": "Proveedor", "y_label": "€/año", "default_chart": "bar",
    },
    "license_expiry_timeline": {
        "label": "Línea de tiempo de vencimientos",
        "category": "ALM",
        "description": "Licencias y contratos que vencen en los próximos 12 meses",
        "x_label": "Mes", "y_label": "Vencimientos", "default_chart": "bar",
    },
    "assets_by_type": {
        "label": "Activos por tipo",
        "category": "ALM",
        "description": "Inventario de activos por categoría (hardware, software, etc.)",
        "x_label": "Tipo", "y_label": "Activos", "default_chart": "pie",
    },
    "license_utilization": {
        "label": "Utilización de licencias",
        "category": "ALM",
        "description": "% de seats usados respecto al total por licencia",
        "x_label": "Licencia", "y_label": "% Uso", "default_chart": "bar",
    },
    # ── Semantic Engine ──────────────────────────────────────────────────────
    "semantic_accuracy_trend": {
        "label": "Precisión del motor de asignación",
        "category": "IA",
        "description": "% de asignaciones aceptadas vs rechazadas por mes",
        "x_label": "Mes", "y_label": "% Aceptadas", "default_chart": "line",
    },
    "semantic_assignments_by_mode": {
        "label": "Asignaciones por modo de motor",
        "category": "IA",
        "description": "Desglose de asignaciones por motor (semántico, LLM, cache experto)",
        "x_label": "Modo", "y_label": "Asignaciones", "default_chart": "pie",
    },
    # ── Advanced Metrics (Forecasting & People Analytics) ─────────────────────
    "forecast_revenue": {
        "label": "Proyección de ingresos (90 días)",
        "category": "Estrategia",
        "description": "Ingresos pronosticados: combinan pipeline + proyectos activos + contratos vigentes",
        "x_label": "Origen", "y_label": "€", "default_chart": "bar_stacked",
    },
    "burnout_index": {
        "label": "Índice de riesgo de burnout por persona",
        "category": "Bienestar",
        "description": "Score 0-100 por persona: utilización + trend + ausencias pendientes + tareas bloqueadas",
        "x_label": "Persona", "y_label": "Score", "default_chart": "bar",
    },
}


@router.get("/catalogue", summary="Catálogo de métricas disponibles")
def get_catalogue(current_user: User = Depends(get_current_user)):
    result = {}
    for key, meta in CATALOGUE.items():
        cat = meta["category"]
        if cat not in result:
            result[cat] = []
        result[cat].append({"id": key, **meta})
    return result


def _date_range(date_from: Optional[str], date_to: Optional[str]):
    return _svc.parse_date_range(date_from, date_to)


def _month_label(d) -> str:
    return _svc.month_label(d)


def _week_label(d) -> str:
    return _svc.week_label(d)


def _filtered_project_ids(db, current_user, *, project_id, project_type, client_id):
    return _svc.get_filtered_project_ids(db, current_user,
                                          project_id=project_id, project_type=project_type, client_id=client_id)


_month_label = _svc.month_label
_week_label  = _svc.week_label


def _filtered_project_ids(db, current_user, *, project_id, project_type, client_id):
    return _svc.get_filtered_project_ids(db, current_user,
                                          project_id=project_id, project_type=project_type, client_id=client_id)


# Build METRIC_REGISTRY: combine modular metrics + legacy metrics (for transition period)
METRIC_REGISTRY = dict(MODULAR_METRICS_REGISTRY)

# Add legacy metrics that haven't been migrated yet
def _build_legacy_metric_handler(metric_id: str):
    def _handler(**kwargs):
        rows, meta_patch = run_legacy_metric(metric_id, **kwargs)
        return rows, meta_patch
    return _handler

for _legacy_metric_id in LEGACY_METRIC_IDS:
    if _legacy_metric_id not in METRIC_REGISTRY:
        METRIC_REGISTRY[_legacy_metric_id] = _build_legacy_metric_handler(_legacy_metric_id)


@router.get("/query/{metric_id}", summary="Ejecutar consulta analítica")
def run_query(
    metric_id: str,
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    project_type: Optional[str] = Query(None),
    client_id: Optional[str] = Query(None),
    group_by: Optional[str] = Query(None),  # secondary grouping
    top_n: int = Query(20, ge=1, le=100),
    no_cache: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if metric_id not in CATALOGUE:
        raise HTTPException(404, f"Métrica '{metric_id}' no encontrada")

    meta = CATALOGUE[metric_id]
    d_from, d_to = _date_range(date_from, date_to)
    rows = []
    project_ids = _filtered_project_ids(
        db,
        current_user,
        project_id=project_id,
        project_type=project_type,
        client_id=client_id,
    )

    # Explicit forbidden access attempt to foreign project.
    if project_id and project_ids == []:
        raise HTTPException(403, "No tienes acceso a este proyecto")

    cache_key = _analytics_cache_key(
        "analytics.query",
        current_user,
        {
            "metric_id": metric_id,
            "date_from": str(d_from),
            "date_to": str(d_to),
            "project_id": project_id,
            "user_id": user_id,
            "department": department,
            "project_type": project_type,
            "client_id": client_id,
            "group_by": group_by,
            "top_n": top_n,
        },
    )

    # Tenant has no visible projects under current filters => empty result set.
    if project_ids == []:
        response = {
            "metric_id": metric_id,
            "meta": meta,
            "filters": {
                "date_from": str(d_from), "date_to": str(d_to),
                "project_id": project_id, "user_id": user_id, "department": department,
                "project_type": project_type, "client_id": client_id,
            },
            "rows": [],
            "total": 0,
            "summary": {},
        }
        # No cache for empty result: avoids polluting cache with empty responses for rare tenants
        return response
    if not no_cache:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

    if metric_id in METRIC_REGISTRY:
        handler = METRIC_REGISTRY[metric_id]
        handler_result = handler(
            db=db,
            d_from=d_from,
            d_to=d_to,
            top_n=top_n,
            project_id=project_id,
            department=department,
            project_ids=project_ids,
            user_id=user_id,
            client_id=client_id,
            group_by=group_by,
            organization_id=current_user.organization_id,
        )
        if isinstance(handler_result, tuple):
            rows, meta_patch = handler_result
            if meta_patch:
                meta = {**meta, **meta_patch}
        else:
            rows = handler_result
        response = {
            "metric_id": metric_id,
            "meta": meta,
            "filters": {
                "date_from": str(d_from), "date_to": str(d_to),
                "project_id": project_id, "user_id": user_id, "department": department,
                "project_type": project_type, "client_id": client_id,
            },
            "rows": rows,
            "total": len(rows),
            "summary": _compute_summary(rows, meta),
        }
        if not no_cache:
            ttl = _get_metric_cache_ttl(metric_id)
            _cache_set(cache_key, response, ttl_seconds=ttl)
        return response

    rows = []

    if not rows:
        rows = []

    response = {
        "metric_id": metric_id,
        "meta": meta,
        "filters": {
            "date_from": str(d_from), "date_to": str(d_to),
            "project_id": project_id, "user_id": user_id, "department": department,
            "project_type": project_type, "client_id": client_id,
        },
        "rows": rows,
        "total": len(rows),
        "summary": _compute_summary(rows, meta),
    }
    if not no_cache:
        ttl = _get_metric_cache_ttl(metric_id)
        _cache_set(cache_key, response, ttl_seconds=ttl)
    return response


def _compute_summary(rows, meta=None):
    return _svc.compute_summary(rows)


@router.get("/filters/options", summary="Opciones para los filtros")
def get_filter_options(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    no_cache: bool = Query(False),
):
    cache_key = _analytics_cache_key("analytics.filters.options", current_user, {})
    if not no_cache:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached
    response = _svc.get_filter_options_data(current_user, db)
    if not no_cache:
        _cache_set(cache_key, response, ttl_seconds=300)
    return response


@router.get("/hours_by_week", summary="Horas por semana")
def hours_by_week(
    weeks: int = Query(8, ge=1, le=52),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _svc.get_hours_by_week(weeks, current_user, db)


@router.get("/utilization/advanced", summary="Utilización avanzada (actual + bookings + proyección)")
def advanced_utilization(
    weeks_ahead: int = Query(4, ge=1, le=12),
    project_id: Optional[str] = Query(None),
    project_type: Optional[str] = Query(None),
    client_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _svc.get_advanced_utilization(weeks_ahead, project_id, project_type, client_id, current_user, db)


@router.get("/alerts/metric-breaches", summary="Alertas de métricas por umbral")
def metric_breaches(
    margin_threshold_pct: float = Query(10.0, ge=-100, le=100),
    top_n: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _svc.get_metric_breaches(margin_threshold_pct, top_n, current_user, db)
