"""
Analytics engine – flexible data extraction for the reports builder.
Every query returns rows + metadata so the frontend can render any chart type.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from typing import Optional
import logging
from pydantic import BaseModel, Field

from app.db.session import get_db
from app.core.deps import require_admin, require_admin_or_pm, get_current_user, require_internal_user
from app.core.responses import APIListResponse, APIResponse
from app.models.user import User
# Legacy metrics fully migrated to MODULAR_METRICS_REGISTRY — see #109/#104.
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
        "y_label": "Coste (¤)",
        "default_chart": "bar",
    },
    "cost_by_person": {
        "label": "Coste por persona",
        "category": "Costes",
        "description": "Coste total por persona en el período",
        "x_label": "Persona",
        "y_label": "Coste (¤)",
        "default_chart": "bar",
    },
    "cost_by_month": {
        "label": "Coste mensual",
        "category": "Costes",
        "description": "Evolución mensual del coste interno",
        "x_label": "Mes",
        "y_label": "Coste (¤)",
        "default_chart": "line",
    },
    "cost_per_hour_by_person": {
        "label": "Coste/hora por persona",
        "category": "Costes",
        "description": "Coste/hora actual derivado del perfil de coste vigente (admin/hr)",
        "x_label": "Persona",
        "y_label": "Coste/h (¤)",
        "default_chart": "bar",
    },
    "cost_per_hour_by_department": {
        "label": "Coste/hora por departamento",
        "category": "Costes",
        "description": "Coste/hora medio por departamento",
        "x_label": "Departamento",
        "y_label": "Coste/h (¤)",
        "default_chart": "bar",
    },
    "cost_per_hour_by_country": {
        "label": "Coste/hora por país",
        "category": "Costes",
        "description": "Coste/hora medio por país (multi-país)",
        "x_label": "País",
        "y_label": "Coste/h (¤)",
        "default_chart": "bar",
    },
    "annual_cost_by_person": {
        "label": "Coste empresa anual por persona",
        "category": "Costes",
        "description": "Bruto + SS empresa + extras anuales por persona",
        "x_label": "Persona",
        "y_label": "¤/año",
        "default_chart": "bar",
    },
    "annual_cost_by_country": {
        "label": "Coste empresa anual por país",
        "category": "Costes",
        "description": "Coste empresa anual agregado por país",
        "x_label": "País",
        "y_label": "¤/año",
        "default_chart": "bar",
    },
    "cost_profile_coverage": {
        "label": "Cobertura de perfiles de coste",
        "category": "Costes",
        "description": "Personas con perfil de coste vs sólo tarifa interna vs sin datos",
        "x_label": "Estado",
        "y_label": "Personas",
        "default_chart": "pie",
    },
    "employer_cost_pct_by_country": {
        "label": "% Coste empresa por país",
        "category": "Costes",
        "description": "% de coste empresa (SS empresa + extras) configurado por país",
        "x_label": "País",
        "y_label": "%",
        "default_chart": "bar",
    },
    "cost_per_hour_drift": {
        "label": "Evolución coste/hora medio",
        "category": "Costes",
        "description": "Coste/hora medio de la org mes a mes (drift por subidas)",
        "x_label": "Mes",
        "y_label": "Coste/h (¤)",
        "default_chart": "line",
    },
    "margin_by_project": {
        "label": "Margen por proyecto",
        "category": "Rentabilidad",
        "description": "Ingresos, costes y margen bruto por proyecto",
        "x_label": "Proyecto",
        "y_label": "¤",
        "default_chart": "bar_grouped",
    },
    "margin_evolution": {
        "label": "Evolución del margen",
        "category": "Rentabilidad",
        "description": "Evolución mensual del margen",
        "x_label": "Mes",
        "y_label": "¤",
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
        "y_label": "¤ Ponderado",
        "default_chart": "bar",
    },
    "pipeline_evolution": {
        "label": "Evolución del pipeline",
        "category": "Negocio",
        "description": "Evolución mensual del valor del pipeline",
        "x_label": "Mes",
        "y_label": "¤",
        "default_chart": "line",
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
        "y_label": "¤",
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
    # ── Clientes / Negocio ───────────────────────────────────────────────────
    "revenue_by_client": {
        "label": "Ingresos por cliente",
        "category": "Negocio",
        "description": "Facturación total por cliente en el período",
        "x_label": "Cliente", "y_label": "¤", "default_chart": "bar",
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
        "x_label": "Estado", "y_label": "¤", "default_chart": "bar",
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
        "x_label": "Proveedor", "y_label": "¤/año", "default_chart": "bar",
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
        "x_label": "Origen", "y_label": "¤", "default_chart": "bar_stacked",
    },
    "burnout_index": {
        "label": "Índice de riesgo de burnout por persona",
        "category": "Bienestar",
        "description": "Score 0-100 por persona: utilización + trend + ausencias pendientes + tareas bloqueadas",
        "x_label": "Persona", "y_label": "Score", "default_chart": "bar",
    },
    # ── OKR & NPS ─────────────────────────────────────────────────────────────
    "okr_progress_by_objective": {
        "label": "Progreso OKR por objetivo",
        "category": "OKR",
        "description": "Porcentaje de progreso de cada objetivo OKR activo",
        "x_label": "Objetivo", "y_label": "Progreso (%)", "default_chart": "bar",
    },
    "okr_kr_completion_rate": {
        "label": "Tasa de consecución de Key Results",
        "category": "OKR",
        "description": "Tasa media de consecución de KRs agrupada por objetivo",
        "x_label": "Objetivo", "y_label": "Tasa KR (%)", "default_chart": "bar",
    },
    "nps_by_client": {
        "label": "NPS por cliente",
        "category": "NPS",
        "description": "Puntuación NPS media por cliente en el período",
        "x_label": "Cliente", "y_label": "NPS", "default_chart": "bar",
    },
    "nps_trend": {
        "label": "Evolución mensual del NPS",
        "category": "NPS",
        "description": "Tendencia mensual de la puntuación NPS media",
        "x_label": "Mes", "y_label": "NPS", "default_chart": "line",
    },
    "nps_distribution": {
        "label": "Distribución NPS (Promotores / Pasivos / Detractores)",
        "category": "NPS",
        "description": "Desglose de respuestas NPS en las tres categorías estándar",
        "x_label": "Categoría", "y_label": "Respuestas", "default_chart": "pie",
    },
    "client_health_score": {
        "label": "Health score por cliente",
        "category": "NPS",
        "description": "Último health score registrado por cliente (0-100)",
        "x_label": "Cliente", "y_label": "Score", "default_chart": "bar",
    },
    # ── Training & Git ─────────────────────────────────────────────────────────
    "training_completion_rate": {
        "label": "Tasa de finalización de cursos",
        "category": "Formación",
        "description": "Porcentaje de inscripciones completadas por curso",
        "x_label": "Curso", "y_label": "Completado (%)", "default_chart": "bar",
    },
    "certifications_by_user": {
        "label": "Certificaciones obtenidas por persona",
        "category": "Formación",
        "description": "Número de certificaciones obtenidas por persona en el período",
        "x_label": "Persona", "y_label": "Certificaciones", "default_chart": "bar",
    },
    "prs_by_author": {
        "label": "Pull Requests por autor",
        "category": "Git",
        "description": "Número de PRs abiertos por autor en el período",
        "x_label": "Autor", "y_label": "PRs", "default_chart": "bar",
    },
    "prs_by_project": {
        "label": "Pull Requests por proyecto",
        "category": "Git",
        "description": "Número de PRs por proyecto en el período",
        "x_label": "Proyecto", "y_label": "PRs", "default_chart": "bar",
    },
    "pr_cycle_time": {
        "label": "Tiempo de ciclo de PRs",
        "category": "Git",
        "description": "Horas medias desde apertura hasta merge por proyecto",
        "x_label": "Proyecto", "y_label": "Horas (media)", "default_chart": "bar",
    },
    "deployments_by_env": {
        "label": "Despliegues por entorno",
        "category": "Git",
        "description": "Número de despliegues realizados por entorno",
        "x_label": "Entorno", "y_label": "Despliegues", "default_chart": "bar",
    },
    "deployment_success_rate": {
        "label": "Tasa de éxito de despliegues",
        "category": "Git",
        "description": "Porcentaje de despliegues exitosos por entorno",
        "x_label": "Entorno", "y_label": "Éxito (%)", "default_chart": "bar",
    },
    # ── Revenue & Expenses ─────────────────────────────────────────────────────
    "revenue_recognized_by_month": {
        "label": "Ingresos reconocidos por mes",
        "category": "Ingresos",
        "description": "Evolución mensual de ingresos reconocidos (ASC-606 / rev_entries)",
        "x_label": "Mes", "y_label": "¤", "default_chart": "line",
    },
    "revenue_by_contract": {
        "label": "Ingresos reconocidos por contrato",
        "category": "Ingresos",
        "description": "Total de ingresos reconocidos acumulados por contrato",
        "x_label": "Contrato", "y_label": "¤", "default_chart": "bar",
    },
    "expenses_by_category": {
        "label": "Gastos por categoría",
        "category": "Gastos",
        "description": "Total de gastos agrupados por categoría",
        "x_label": "Categoría", "y_label": "¤", "default_chart": "pie",
    },
    "expenses_by_project": {
        "label": "Gastos por proyecto",
        "category": "Gastos",
        "description": "Total de gastos imputados por proyecto",
        "x_label": "Proyecto", "y_label": "¤", "default_chart": "bar",
    },
    "expenses_billable_vs_internal": {
        "label": "Gastos facturables vs internos",
        "category": "Gastos",
        "description": "Comparativa del importe de gastos facturables y gastos internos",
        "x_label": "Tipo", "y_label": "¤", "default_chart": "pie",
    },
    "expenses_trend": {
        "label": "Evolución mensual de gastos",
        "category": "Gastos",
        "description": "Tendencia mensual de gastos aprobados",
        "x_label": "Mes", "y_label": "¤", "default_chart": "line",
    },
    "expenses_pending_approval": {
        "label": "Gastos pendientes de aprobación",
        "category": "Gastos",
        "description": "Importe y número de gastos en estado 'submitted' por persona",
        "x_label": "Persona", "y_label": "¤ pendiente", "default_chart": "bar",
    },
    # ── Sprints & Tasks ────────────────────────────────────────────────────────
    "sprint_velocity_trend": {
        "label": "Evolución de velocidad por sprint",
        "category": "Sprints",
        "description": "Story points completados por sprint cerrado en el período",
        "x_label": "Sprint", "y_label": "Story Points", "default_chart": "line",
    },
    "sprint_completion_rate": {
        "label": "Tasa de completado por sprint",
        "category": "Sprints",
        "description": "Porcentaje de story points completados vs planificados por sprint",
        "x_label": "Sprint", "y_label": "Completado (%)", "default_chart": "bar",
    },
    "tasks_by_status": {
        "label": "Tareas por estado",
        "category": "Tareas",
        "description": "Distribución del total de tareas por estado",
        "x_label": "Estado", "y_label": "Tareas", "default_chart": "pie",
    },
    "tasks_by_priority": {
        "label": "Tareas por prioridad",
        "category": "Tareas",
        "description": "Distribución del total de tareas por prioridad",
        "x_label": "Prioridad", "y_label": "Tareas", "default_chart": "pie",
    },
    "tasks_overdue_by_assignee": {
        "label": "Tareas vencidas por responsable",
        "category": "Tareas",
        "description": "Número de tareas vencidas (due_date superada) por persona asignada",
        "x_label": "Persona", "y_label": "Tareas vencidas", "default_chart": "bar",
    },
    "task_completion_trend": {
        "label": "Evolución mensual de tareas completadas",
        "category": "Tareas",
        "description": "Número de tareas finalizadas cada mes",
        "x_label": "Mes", "y_label": "Tareas completadas", "default_chart": "line",
    },
    "tasks_by_assignee": {
        "label": "Carga de trabajo por persona",
        "category": "Tareas",
        "description": "Tareas abiertas actualmente por persona asignada",
        "x_label": "Persona", "y_label": "Tareas abiertas", "default_chart": "bar",
    },
    "epics_by_status": {
        "label": "Épicas por estado",
        "category": "Tareas",
        "description": "Distribución de épicas según su estado",
        "x_label": "Estado", "y_label": "Épicas", "default_chart": "pie",
    },
    "milestones_on_time_rate": {
        "label": "Hitos: a tiempo vs con retraso",
        "category": "Proyectos",
        "description": "Número de hitos completados a tiempo frente a los que se entregaron tarde",
        "x_label": "Resultado", "y_label": "Hitos", "default_chart": "pie",
    },
    # ── Portfolio & Performance ────────────────────────────────────────────────
    "portfolio_budget_usage": {
        "label": "Uso de presupuesto por portfolio",
        "category": "Portfolio",
        "description": "Presupuesto total vs gastado por cada portfolio activo",
        "x_label": "Portfolio", "y_label": "¤", "default_chart": "bar_stacked",
    },
    "performance_scores_by_person": {
        "label": "Score de evaluación por persona",
        "category": "RRHH",
        "description": "Puntuación global de la última evaluación de desempeño por persona",
        "x_label": "Persona", "y_label": "Score (0-10)", "default_chart": "bar",
    },
    "performance_cycle_completion_rate": {
        "label": "Tasa de completado de ciclos de evaluación",
        "category": "RRHH",
        "description": "Porcentaje de revisiones completadas por ciclo de evaluación",
        "x_label": "Ciclo", "y_label": "Completado (%)", "default_chart": "bar",
    },
    "timesheets_approval_rate": {
        "label": "Partes de horas por estado",
        "category": "Horas",
        "description": "Distribución de partes de horas semanales por estado de aprobación",
        "x_label": "Estado", "y_label": "Partes", "default_chart": "pie",
    },
    "timesheets_billable_hours_trend": {
        "label": "Tendencia mensual de horas facturables (partes)",
        "category": "Horas",
        "description": "Evolución mensual de horas facturables en partes aprobados",
        "x_label": "Mes", "y_label": "Horas facturables", "default_chart": "line",
    },
    "absences_by_type": {
        "label": "Ausencias por tipo",
        "category": "RRHH",
        "description": "Días laborables de ausencia agrupados por tipo (vacaciones, baja, etc.)",
        "x_label": "Tipo", "y_label": "Días", "default_chart": "pie",
    },
    "absences_by_person": {
        "label": "Ausencias por persona",
        "category": "RRHH",
        "description": "Total de días de ausencia aprobados por persona en el período",
        "x_label": "Persona", "y_label": "Días", "default_chart": "bar",
    },
    # ── Invoices & Alerts ──────────────────────────────────────────────────────
    "invoices_by_status": {
        "label": "Facturas por estado",
        "category": "Facturación",
        "description": "Número e importe de facturas agrupadas por estado",
        "x_label": "Estado", "y_label": "¤", "default_chart": "bar",
    },
    "invoice_amount_by_month": {
        "label": "Facturación mensual",
        "category": "Facturación",
        "description": "Importe total facturado por mes",
        "x_label": "Mes", "y_label": "¤", "default_chart": "line",
    },
    "invoice_amount_by_client": {
        "label": "Facturación por cliente",
        "category": "Facturación",
        "description": "Total facturado por cliente en el período",
        "x_label": "Cliente", "y_label": "¤", "default_chart": "bar",
    },
    "invoice_overdue_amount": {
        "label": "Facturas vencidas pendientes de cobro",
        "category": "Facturación",
        "description": "Facturas no pagadas con fecha de vencimiento superada por cliente",
        "x_label": "Cliente", "y_label": "¤ vencido", "default_chart": "bar",
    },
    "alerts_by_severity": {
        "label": "Alertas por severidad",
        "category": "Alertas",
        "description": "Distribución de alertas generadas por nivel de severidad",
        "x_label": "Severidad", "y_label": "Alertas", "default_chart": "pie",
    },
    "alerts_by_type": {
        "label": "Alertas por tipo",
        "category": "Alertas",
        "description": "Distribución de alertas por tipo",
        "x_label": "Tipo", "y_label": "Alertas", "default_chart": "bar",
    },
    "unresolved_alerts_by_project": {
        "label": "Alertas no resueltas por proyecto",
        "category": "Alertas",
        "description": "Número de alertas pendientes de resolución por proyecto",
        "x_label": "Proyecto", "y_label": "Alertas", "default_chart": "bar",
    },
    "sla_breach_trend": {
        "label": "Evolución mensual de incumplimientos SLA",
        "category": "Service Desk",
        "description": "Número de incumplimientos de SLA registrados por mes",
        "x_label": "Mes", "y_label": "Incumplimientos", "default_chart": "line",
    },
    "sla_breach_by_type": {
        "label": "Incumplimientos SLA por tipo",
        "category": "Service Desk",
        "description": "Distribución de incumplimientos SLA por tipo y tiempo medio de brecha",
        "x_label": "Tipo", "y_label": "Incumplimientos", "default_chart": "bar",
    },
    # ── Automations & CMDB ────────────────────────────────────────────────────
    "automation_success_rate": {
        "label": "Tasa de éxito de automatizaciones",
        "category": "Automatizaciones",
        "description": "Ejecuciones de automatización exitosas vs fallidas",
        "x_label": "Resultado", "y_label": "Ejecuciones", "default_chart": "pie",
    },
    "automation_run_stats": {
        "label": "Estadísticas de ejecución por regla",
        "category": "Automatizaciones",
        "description": "Total de ejecuciones, éxitos y errores por regla de automatización activa",
        "x_label": "Regla", "y_label": "Ejecuciones", "default_chart": "bar_stacked",
    },
    "cmdb_items_by_status": {
        "label": "Ítems CMDB por estado",
        "category": "CMDB",
        "description": "Distribución de elementos del inventario CMDB por estado",
        "x_label": "Estado", "y_label": "Ítems", "default_chart": "pie",
    },
    "cmdb_items_by_environment": {
        "label": "Ítems CMDB por entorno",
        "category": "CMDB",
        "description": "Número de elementos del CMDB por entorno (production, staging, dev...)",
        "x_label": "Entorno", "y_label": "Ítems", "default_chart": "bar",
    },
    "cmdb_items_by_type": {
        "label": "Ítems CMDB por tipo de CI",
        "category": "CMDB",
        "description": "Distribución de elementos del CMDB por tipo de activo",
        "x_label": "Tipo CI", "y_label": "Ítems", "default_chart": "pie",
    },
    "clients_by_industry": {
        "label": "Clientes por sector",
        "category": "Negocio",
        "description": "Distribución de clientes activos por sector industrial",
        "x_label": "Sector", "y_label": "Clientes", "default_chart": "pie",
    },
    "opportunity_by_owner": {
        "label": "Pipeline comercial por responsable",
        "category": "Negocio",
        "description": "Valor ponderado del pipeline abierto por propietario de la oportunidad",
        "x_label": "Responsable", "y_label": "Pipeline (¤)", "default_chart": "bar",
    },
}


def _simbolo(db, current_user) -> str:
    """Las etiquetas del catálogo llevan `¤`; se sirve el símbolo de la moneda de la organización."""
    from app.services.formato_regional import simbolo_de_moneda
    return simbolo_de_moneda(db, getattr(current_user, "organization_id", None))


@router.get("/catalogue", summary="Catálogo de métricas disponibles")
def get_catalogue(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.services.formato_regional import con_moneda
    result = {}
    for key, meta in CATALOGUE.items():
        cat = meta["category"]
        if cat not in result:
            result[cat] = []
        result[cat].append({"id": key, **meta})
    return APIResponse.ok(data=con_moneda(result, _simbolo(db, current_user)))


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


METRIC_REGISTRY = dict(MODULAR_METRICS_REGISTRY)


def _respuesta_de_metrica(metric_id: str, meta: dict, filtros: dict, rows: list) -> dict:
    """La forma de una respuesta analítica.

    Auditoría 2026-09 (hallazgo 18): este diccionario estaba escrito **tres
    veces, palabra por palabra** dentro de `run_query` —el caso vacío, el del
    registro de métricas y el final—, con los siete campos de `filters`
    repetidos en los tres. Tres copias de un contrato de API es una forma
    garantizada de que un día devuelvan cosas distintas.
    """
    return {
        "metric_id": metric_id,
        "meta": meta,
        "filters": filtros,
        "rows": rows,
        "total": len(rows),
        "summary": _compute_summary(rows, meta),
    }


def _ejecutar_metrica(metric_id: str, db, *, d_from, d_to, top_n, project_id,
                      department, project_ids, user_id, client_id, group_by,
                      organization_id, meta: dict):
    """Llama al manejador de la métrica. Devuelve `(filas, meta)`.

    Un manejador puede devolver sólo filas o una tupla `(filas, parche_de_meta)`
    —hay métricas que ajustan las columnas según los datos—, y aquí se
    normalizan las dos formas.

    Un fallo del manejador no tumba la respuesta (el catálogo se consulta desde
    paneles con varias métricas a la vez), pero ya no se disfraza de «sin
    datos»: va con `meta.error`, queda en el log y no se cachea (revisión 2026-11).
    """
    handler = METRIC_REGISTRY[metric_id]
    try:
        resultado = handler(
            db=db, d_from=d_from, d_to=d_to, top_n=top_n, project_id=project_id,
            department=department, project_ids=project_ids, user_id=user_id,
            client_id=client_id, group_by=group_by, organization_id=organization_id,
        )
    except Exception:
        logger.exception("La métrica %s falló", metric_id)
        db.rollback()
        return [], {**meta, "error": "No se pudo calcular esta métrica"}

    if isinstance(resultado, tuple):
        rows, parche = resultado
        return rows, ({**meta, **parche} if parche else meta)
    return resultado, meta


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
    group_by: Optional[str] = Query(None),  # agrupación secundaria
    top_n: int = Query(20, ge=1, le=100),
    no_cache: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if metric_id not in CATALOGUE:
        raise HTTPException(404, f"Métrica '{metric_id}' no encontrada")

    from app.services.formato_regional import con_moneda
    simbolo = _simbolo(db, current_user)
    meta = con_moneda(CATALOGUE[metric_id], simbolo)
    d_from, d_to = _date_range(date_from, date_to)
    project_ids = _filtered_project_ids(
        db, current_user,
        project_id=project_id, project_type=project_type, client_id=client_id,
    )

    # Pedir un proyecto concreto y quedarse sin ninguno visible es un intento de
    # acceso ajeno, no un resultado vacío.
    if project_id and project_ids == []:
        raise HTTPException(403, "No tienes acceso a este proyecto")

    filtros = {
        "date_from": str(d_from), "date_to": str(d_to),
        "project_id": project_id, "user_id": user_id, "department": department,
        "project_type": project_type, "client_id": client_id,
    }

    # Sin proyectos visibles bajo estos filtros no hay nada que calcular. **No
    # se cachea**: llenaría la caché de respuestas vacías para inquilinos raros.
    if project_ids == []:
        return APIResponse.ok(data=_respuesta_de_metrica(metric_id, meta, filtros, []))

    cache_key = _analytics_cache_key(
        "analytics.query", current_user,
        {**filtros, "metric_id": metric_id, "group_by": group_by, "top_n": top_n},
    )
    if not no_cache:
        cacheada = _cache_get(cache_key)
        if cacheada is not None:
            return APIResponse.ok(data=cacheada)

    rows: list = []
    if metric_id not in METRIC_REGISTRY:
        # En el catálogo sin cálculo: se dice, no se enseña vacío como si fuera un dato.
        meta = {**meta, "error": "Esta métrica no tiene cálculo"}
    else:
        rows, meta = _ejecutar_metrica(
            metric_id, db, d_from=d_from, d_to=d_to, top_n=top_n, project_id=project_id,
            department=department, project_ids=project_ids, user_id=user_id,
            client_id=client_id, group_by=group_by,
            organization_id=current_user.organization_id, meta=meta,
        )
        meta = con_moneda(meta, simbolo)  # el parche de la métrica también trae `¤`

    response = _respuesta_de_metrica(metric_id, meta, filtros, rows)
    if not no_cache and not meta.get("error"):
        _cache_set(cache_key, response, ttl_seconds=_get_metric_cache_ttl(metric_id))
    return APIResponse.ok(data=response)


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
            return APIResponse.ok(data=cached)
    response = _svc.get_filter_options_data(current_user, db)
    if not no_cache:
        _cache_set(cache_key, response, ttl_seconds=300)
    return APIResponse.ok(data=response)


@router.get("/hours_by_week", summary="Horas por semana")
def hours_by_week(
    weeks: int = Query(8, ge=1, le=52),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data=_svc.get_hours_by_week(weeks, current_user, db))


@router.get("/utilization/advanced", summary="Utilización avanzada (actual + bookings + proyección)")
def advanced_utilization(
    weeks_ahead: int = Query(4, ge=1, le=12),
    project_id: Optional[str] = Query(None),
    project_type: Optional[str] = Query(None),
    client_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data=_svc.get_advanced_utilization(weeks_ahead, project_id, project_type, client_id, current_user, db))


@router.get("/alerts/metric-breaches", summary="Alertas de métricas por umbral")
def metric_breaches(
    margin_threshold_pct: float = Query(10.0, ge=-100, le=100),
    top_n: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data=_svc.get_metric_breaches(margin_threshold_pct, top_n, current_user, db))


# ── BI Storytelling / Ask-the-Data / OLAP ───────────────────────────────────

class AskRequest(BaseModel):
    question: str


@router.get("/narrative", summary="Narrativa ejecutiva generada por IA")
def get_narrative(
    lang: Optional[str] = Query(None, description="Idioma: es | en | ca (por defecto, el del usuario / la organización)"),
    force_refresh: bool = Query(False, description="Ignorar caché y regenerar"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_pm),
):
    from app.services.bi_storytelling import generate_narrative
    org_id = getattr(current_user, "organization_id", None)
    return APIResponse.ok(data=generate_narrative(org_id=org_id, lang=lang, force_refresh=force_refresh,
                                                  user_id=current_user.id))


@router.post("/ask", summary="Pregunta en lenguaje natural sobre los datos OLAP")
def ask_the_data(
    payload: AskRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: dominio: consultas analiticas
):
    from app.services.ask_the_data import ask
    from app.services.bi_governance_service import registrar_acceso
    org_id = getattr(current_user, "organization_id", None)
    registrar_acceso(db, request, current_user, "ask", "olap", "view", {"question": payload.question[:500]})
    return APIResponse.ok(data=ask(
        question=payload.question,
        db=db,
        org_id=org_id,
        user_id=str(current_user.id),
        is_superadmin=bool(getattr(current_user, "is_superadmin", False)),
    ))


# ── Banco de preguntas validadas (revisión 2026-11) ──────────────────────────
class EjemploAskIn(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)
    sql: str = Field(..., min_length=10, max_length=5000)


@router.get("/ask/examples", summary="Preguntas validadas de Ask-the-Data de la empresa (admin o PM)")
def list_ask_examples(db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_pm)):
    from app.services import ask_banco
    return APIResponse.ok(data=ask_banco.lista(db, current_user.organization_id))


@router.post("/ask/examples", summary="Marcar una respuesta de Ask-the-Data como correcta (admin o PM)")
def save_ask_example(payload: EjemploAskIn, db: Session = Depends(get_db),
                     current_user: User = Depends(require_admin_or_pm)):
    from app.services import ask_banco
    from app.services.ask_the_data import SQLValidationError
    try:
        fila = ask_banco.guardar(db, current_user.organization_id, current_user.id, payload.question, payload.sql)
    except SQLValidationError as e:
        raise HTTPException(422, f"SQL no permitido: {e}")
    return APIResponse.ok(data={"id": fila.id, "question": fila.question})


@router.delete("/ask/examples/{example_id}", summary="Quitar una pregunta validada (admin o PM)")
def delete_ask_example(example_id: str, db: Session = Depends(get_db),
                       current_user: User = Depends(require_admin_or_pm)):
    from app.services import ask_banco
    if not ask_banco.borrar(db, current_user.organization_id, example_id):
        raise HTTPException(404, "No existe")
    return APIResponse.ok(data={"deleted": example_id})


# ── Estado y carga del almacén analítico (revisión 2026-11) ──────────────────
@router.get("/olap/status", summary="Última carga del almacén analítico y filas de la empresa")
def olap_status(current_user: User = Depends(require_internal_user)):
    from app.services.olap.etl import estado
    return APIResponse.ok(data=estado(current_user.organization_id,
                                      plataforma=bool(getattr(current_user, "is_superadmin", False))))


@router.post("/olap/refresh", summary="Recargar ya el almacén analítico desde la base (admin)")
def olap_refresh(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    from app.db.session import sin_filtro_de_tenant
    from app.services.olap.etl import resumen_de_carga, run_full_etl
    # La carga es de TODAS las empresas (el almacén es uno; cada consulta lleva
    # el filtro de su empresa), igual que el trabajo nocturno. Sus totales son
    # de toda la plataforma: solo un superadmin los ve (revisión 2026-11b).
    with sin_filtro_de_tenant(db):
        resultado = run_full_etl(db)
    return APIResponse.ok(data=resumen_de_carga(
        resultado, bool(getattr(current_user, "is_superadmin", False))))


@router.get("/olap/kpis", summary="KPIs del OLAP (DuckDB)")
def get_olap_kpis(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.services.olap.query_engine import get_kpi_summary
    org_id = getattr(current_user, "organization_id", None)
    return APIResponse.ok(data=get_kpi_summary(org_id))


@router.get("/olap/pipeline-funnel", summary="Funnel del pipeline (OLAP)")
def get_olap_pipeline_funnel(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.services.olap.query_engine import get_pipeline_funnel
    org_id = getattr(current_user, "organization_id", None)
    return APIListResponse.ok(items=get_pipeline_funnel(org_id))


@router.get("/olap/portfolio-health", summary="Salud del portfolio (OLAP)")
def get_olap_portfolio_health(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.services.olap.query_engine import get_portfolio_health
    org_id = getattr(current_user, "organization_id", None)
    return APIListResponse.ok(items=get_portfolio_health(org_id))


@router.get("/olap/margin-evolution", summary="Evolución del margen mensual (OLAP)")
def get_olap_margin_evolution(
    months: int = Query(12, ge=1, le=36),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.services.olap.query_engine import get_margin_evolution
    org_id = getattr(current_user, "organization_id", None)
    return APIListResponse.ok(items=get_margin_evolution(org_id, months))


@router.get("/olap/utilization", summary="Utilización por usuario (OLAP)")
def get_olap_utilization(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.services.olap.query_engine import get_utilization_by_user
    org_id = getattr(current_user, "organization_id", None)
    return APIListResponse.ok(items=get_utilization_by_user(org_id))
