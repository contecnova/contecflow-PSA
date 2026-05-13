from typing import Any, Callable, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.billing_reports import ReportDefinition
from app.models.user import User
import logging

logger = logging.getLogger(__name__)


SYSTEM_REPORTS = [
    {
        "id": "utilization_by_person",
        "name": "Utilización por persona",
        "description": "Horas facturables vs no facturables por empleado",
        "category": "utilization", "icon": "👥", "is_system": True,
        "data_source": "imputations",
        "chart_type": "bar_stacked",
    },
    {
        "id": "margin_by_project",
        "name": "Margen por proyecto",
        "description": "Ingresos, costes y margen para cada proyecto activo",
        "category": "financial", "icon": "💰", "is_system": True,
        "data_source": "projects",
        "chart_type": "bar_grouped",
    },
    {
        "id": "wip_report",
        "name": "Work In Progress (WIP)",
        "description": "Proyectos activos: % completado, horas consumidas vs planificadas, desviación",
        "category": "delivery", "icon": "⚙️", "is_system": True,
        "data_source": "projects",
        "chart_type": "table",
    },
    {
        "id": "capacity_forecast_12w",
        "name": "Previsión de capacidad 12 semanas",
        "description": "Horas disponibles vs demanda estimada por perfil para las próximas 12 semanas",
        "category": "utilization", "icon": "📅", "is_system": True,
        "data_source": "capacity",
        "chart_type": "area",
    },
    {
        "id": "sla_compliance",
        "name": "Cumplimiento de SLA",
        "description": "% SLA cumplido por categoría, prioridad y agente",
        "category": "itsm", "icon": "🎯", "is_system": True,
        "data_source": "tickets",
        "chart_type": "bar",
    },
    {
        "id": "timesheet_hours_trend",
        "name": "Tendencia de horas mensuales",
        "description": "Evolución de horas imputadas por mes y tipo",
        "category": "utilization", "icon": "📈", "is_system": True,
        "data_source": "imputations",
        "chart_type": "area",
    },
    {
        "id": "pipeline_health",
        "name": "Estado del pipeline comercial",
        "description": "Oportunidades por fase, importe potencial y probabilidad de cierre",
        "category": "financial", "icon": "🎪", "is_system": True,
        "data_source": "pipeline",
        "chart_type": "bar",
    },
    {
        "id": "expense_by_project",
        "name": "Gastos por proyecto y categoría",
        "description": "Desglose de gastos aprobados por proyecto, período y categoría",
        "category": "financial", "icon": "💸", "is_system": True,
        "data_source": "expenses",
        "chart_type": "bar_stacked",
    },
    {
        "id": "ticket_volume_trend",
        "name": "Volumen de tickets por semana",
        "description": "Evolución del número de tickets creados y resueltos",
        "category": "itsm", "icon": "🎫", "is_system": True,
        "data_source": "tickets",
        "chart_type": "line",
    },
    {
        "id": "project_health_dashboard",
        "name": "Dashboard de salud de proyectos",
        "description": "Semáforo de presupuesto, plazos y riesgos para toda la cartera",
        "category": "delivery", "icon": "🏥", "is_system": True,
        "data_source": "projects",
        "chart_type": "table",
    },
    {
        "id": "aged_wip",
        "name": "WIP Aging — tiempo sin facturar",
        "description": "Proyectos cerrados pendientes de factura y días transcurridos",
        "category": "financial", "icon": "⏳", "is_system": True,
        "data_source": "projects",
        "chart_type": "table",
    },
    {
        "id": "resource_skills_matrix",
        "name": "Matriz de skills del equipo",
        "description": "Qué skills tiene cada miembro y a qué nivel",
        "category": "utilization", "icon": "🧠", "is_system": True,
        "data_source": "skills",
        "chart_type": "table",
    },
]


DATA_SOURCES = {
    "imputations": {
        "label": "Imputaciones / Horas",
        "fields": [
            {"field": "user_name", "label": "Empleado", "type": "string"},
            {"field": "project_name", "label": "Proyecto", "type": "string"},
            {"field": "date", "label": "Fecha", "type": "date"},
            {"field": "hours", "label": "Horas", "type": "number", "aggregate": True},
            {"field": "is_billable", "label": "Facturable", "type": "boolean"},
            {"field": "work_type", "label": "Tipo trabajo", "type": "string"},
            {"field": "hourly_rate", "label": "Tarifa €/h", "type": "number"},
            {"field": "cost", "label": "Coste €", "type": "number", "aggregate": True},
        ]
    },
    "projects": {
        "label": "Proyectos",
        "fields": [
            {"field": "code", "label": "Código", "type": "string"},
            {"field": "name", "label": "Nombre", "type": "string"},
            {"field": "status", "label": "Estado", "type": "string"},
            {"field": "client_name", "label": "Cliente", "type": "string"},
            {"field": "budget_amount", "label": "Presupuesto €", "type": "number"},
            {"field": "budget_used_pct", "label": "% Presupuesto usado", "type": "number"},
            {"field": "hours_logged", "label": "Horas registradas", "type": "number"},
            {"field": "margin_pct", "label": "Margen %", "type": "number"},
            {"field": "start_date", "label": "Inicio", "type": "date"},
            {"field": "end_date_planned", "label": "Fin previsto", "type": "date"},
            {"field": "risk_level", "label": "Nivel riesgo", "type": "string"},
            {"field": "pm_name", "label": "Project Manager", "type": "string"},
        ]
    },
    "tickets": {
        "label": "Tickets Service Desk",
        "fields": [
            {"field": "number", "label": "Nº Ticket", "type": "string"},
            {"field": "title", "label": "Título", "type": "string"},
            {"field": "status", "label": "Estado", "type": "string"},
            {"field": "priority", "label": "Prioridad", "type": "string"},
            {"field": "ticket_type", "label": "Tipo", "type": "string"},
            {"field": "assigned_to", "label": "Agente", "type": "string"},
            {"field": "created_at", "label": "Creado", "type": "date"},
            {"field": "resolved_at", "label": "Resuelto", "type": "date"},
            {"field": "mttr_hours", "label": "MTTR (h)", "type": "number"},
            {"field": "sla_resolution_status", "label": "Estado SLA", "type": "string"},
            {"field": "csat_score", "label": "CSAT", "type": "number"},
        ]
    },
    "expenses": {
        "label": "Gastos",
        "fields": [
            {"field": "code", "label": "Código", "type": "string"},
            {"field": "user_name", "label": "Empleado", "type": "string"},
            {"field": "project_name", "label": "Proyecto", "type": "string"},
            {"field": "category", "label": "Categoría", "type": "string"},
            {"field": "amount", "label": "Importe €", "type": "number", "aggregate": True},
            {"field": "expense_date", "label": "Fecha", "type": "date"},
            {"field": "is_billable", "label": "Facturable", "type": "boolean"},
            {"field": "status", "label": "Estado", "type": "string"},
        ]
    },
    "pipeline": {
        "label": "Pipeline comercial",
        "fields": [
            {"field": "name", "label": "Oportunidad", "type": "string"},
            {"field": "client_name", "label": "Cliente", "type": "string"},
            {"field": "stage", "label": "Fase", "type": "string"},
            {"field": "amount", "label": "Importe €", "type": "number"},
            {"field": "probability_pct", "label": "Probabilidad %", "type": "number"},
            {"field": "weighted_amount", "label": "Importe ponderado €", "type": "number"},
            {"field": "expected_close", "label": "Cierre previsto", "type": "date"},
        ]
    },
    "capacity": {
        "label": "Capacidad y carga",
        "fields": [
            {"field": "user_name", "label": "Empleado", "type": "string"},
            {"field": "week", "label": "Semana", "type": "date"},
            {"field": "capacity_hours", "label": "Capacidad h", "type": "number"},
            {"field": "assigned_hours", "label": "Asignadas h", "type": "number"},
            {"field": "available_hours", "label": "Disponibles h", "type": "number"},
            {"field": "utilization_pct", "label": "Utilización %", "type": "number"},
        ]
    },
    "skills": {
        "label": "Skills del equipo",
        "fields": [
            {"field": "user_name", "label": "Empleado", "type": "string"},
            {"field": "skill_name", "label": "Skill", "type": "string"},
            {"field": "skill_category", "label": "Categoría", "type": "string"},
            {"field": "level", "label": "Nivel (1-5)", "type": "number"},
            {"field": "years_experience", "label": "Años exp.", "type": "number"},
        ]
    },
}


def build_report_catalog(db: Session, current_user: User) -> dict:
    saved = db.query(ReportDefinition).filter(
        or_(ReportDefinition.is_public == True,
            ReportDefinition.created_by == current_user.id)
    ).all()

    return {
        "system": SYSTEM_REPORTS,
        "custom": [{
            "id": r.id,
            "name": r.name,
            "description": r.description,
            "category": r.category,
            "icon": r.icon,
            "is_system": False,
            "is_public": r.is_public,
            "data_source": r.data_source,
            "chart_type": r.chart_type,
            "has_schedule": bool(r.schedule_cron),
            "created_by": r.created_by,
        } for r in saved],
    }


def get_data_sources() -> dict:
    return DATA_SOURCES


def dispatch_report(
    data_source: str,
    report_id: Optional[str],
    filters: dict,
    group_by: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
    project_id: Optional[str],
    org_id: Optional[str],
    runners: dict[str, Callable[..., Any]],
):
    if data_source == "projects":
        return runners["projects"](filters, group_by, date_from, date_to, org_id=org_id)
    if data_source == "imputations":
        return runners["imputations"](filters, group_by, date_from, date_to, project_id, org_id=org_id)
    if data_source == "tickets":
        return runners["tickets"](filters, group_by, date_from, date_to, org_id=org_id)
    if data_source == "expenses":
        return runners["expenses"](filters, group_by, date_from, date_to, project_id, org_id=org_id)
    if data_source == "capacity":
        return runners["capacity"](filters, date_from, date_to, org_id=org_id)
    if data_source == "skills":
        return runners["skills"](filters, org_id=org_id)
    if data_source == "pipeline":
        return runners["pipeline"](filters, org_id=org_id)
    return runners["system"](report_id, filters, date_from, date_to)
