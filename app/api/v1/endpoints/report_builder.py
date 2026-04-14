"""
Report Builder — no-code parametric report system.

Supports: projects | tasks | imputations | users | expenses | sprints |
          tickets | opportunities | contracts | risks | absences |
          timesheets | milestones | deliverables | clients |
          subcontractors | subcontractor_workers | subcontractor_assignments |
          kb_articles | problems
Operators: eq | neq | gt | lt | gte | lte | contains | in | is_null | is_not_null
Output: JSON (preview) | CSV export
"""

import csv
import io
import json
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.user import User

router = APIRouter()

# ── Allowed entities & their exposed columns ──────────────────────────────

ENTITIES: Dict[str, Dict] = {
    "projects": {
        "label": "Proyectos",
        "group": "proyectos_recursos",
        "columns": {
            "code":             {"label": "Código",           "type": "str"},
            "name":             {"label": "Nombre",           "type": "str"},
            "description":      {"label": "Descripción",      "type": "str"},
            "project_type":     {"label": "Tipo",             "type": "str"},
            "status":           {"label": "Estado",           "type": "str"},
            "risk_level":       {"label": "Nivel de riesgo",  "type": "str"},
            "client_name":      {"label": "Cliente",          "type": "str"},
            "department":       {"label": "Departamento",     "type": "str"},
            "is_billable":      {"label": "Facturable",       "type": "bool"},
            "billing_rate":     {"label": "Tarifa fact. (€/h)","type": "float"},
            "contract_amount":  {"label": "Importe contrato", "type": "float"},
            "billing_type":     {"label": "Tipo facturación", "type": "str"},
            "budget_hours":     {"label": "Horas presupuesto","type": "float"},
            "budget_amount":    {"label": "Presupuesto (€)",  "type": "float"},
            "currency":         {"label": "Moneda",           "type": "str"},
            "start_date":       {"label": "Fecha inicio",     "type": "date"},
            "end_date_planned": {"label": "Fin planificado",  "type": "date"},
            "end_date_real":    {"label": "Fin real",         "type": "date"},
            "tags":             {"label": "Etiquetas",        "type": "str"},
            "created_at":       {"label": "Creado",           "type": "date"},
        },
    },
    "tasks": {
        "label": "Tareas",
        "group": "proyectos_recursos",
        "columns": {
            "code":             {"label": "Código",           "type": "str"},
            "title":            {"label": "Título",           "type": "str"},
            "status":           {"label": "Estado",           "type": "str"},
            "priority":         {"label": "Prioridad",        "type": "str"},
            "issue_type":       {"label": "Tipo de tarea",    "type": "str"},
            "estimated_hours":  {"label": "Horas estimadas",  "type": "float"},
            "story_points":     {"label": "Story points",     "type": "float"},
            "start_date":       {"label": "Inicio",           "type": "date"},
            "due_date":         {"label": "Vencimiento",      "type": "date"},
            "completed_at":     {"label": "Completada",       "type": "date"},
            "created_at":       {"label": "Creada",           "type": "date"},
            "tags":             {"label": "Etiquetas",        "type": "str"},
            "blocked_reason":   {"label": "Motivo bloqueo",   "type": "str"},
        },
    },
    "imputations": {
        "label": "Imputaciones de tiempo",
        "group": "tiempo_costes",
        "columns": {
            "date":                  {"label": "Fecha",              "type": "date"},
            "hours":                 {"label": "Horas",              "type": "float"},
            "cost_amount":           {"label": "Coste (€)",          "type": "float"},
            "hourly_rate_snapshot":  {"label": "Tarifa horaria",     "type": "float"},
            "description":           {"label": "Descripción",        "type": "str"},
            "is_approved":           {"label": "Aprobada",           "type": "bool"},
            "is_billable":           {"label": "Facturable",         "type": "bool"},
            "approved_at":           {"label": "Fecha aprobación",   "type": "date"},
            "created_at":            {"label": "Registrada",         "type": "date"},
        },
    },
    "users": {
        "label": "Usuarios / Equipo",
        "group": "personas",
        "columns": {
            "full_name":              {"label": "Nombre completo",    "type": "str"},
            "email":                  {"label": "Email",              "type": "str"},
            "role":                   {"label": "Rol sistema",        "type": "str"},
            "department":             {"label": "Departamento",       "type": "str"},
            "job_title":              {"label": "Cargo",              "type": "str"},
            "phone":                  {"label": "Teléfono",           "type": "str"},
            "weekly_capacity_hours":  {"label": "Capacidad semana (h)","type": "float"},
            "hourly_rate":            {"label": "Tarifa horaria",     "type": "float"},
            "currency":               {"label": "Moneda",             "type": "str"},
            "is_active":              {"label": "Activo",             "type": "bool"},
            "last_login":             {"label": "Último acceso",      "type": "date"},
            "created_at":             {"label": "Alta en sistema",    "type": "date"},
        },
    },
    "expenses": {
        "label": "Gastos",
        "group": "tiempo_costes",
        "columns": {
            "code":             {"label": "Código",           "type": "str"},
            "category":         {"label": "Categoría",        "type": "str"},
            "description":      {"label": "Descripción",      "type": "str"},
            "amount":           {"label": "Importe",          "type": "float"},
            "currency":         {"label": "Moneda",           "type": "str"},
            "expense_date":     {"label": "Fecha gasto",      "type": "date"},
            "is_billable":      {"label": "Facturable",       "type": "bool"},
            "status":           {"label": "Estado",           "type": "str"},
            "submitted_at":     {"label": "Enviado",          "type": "date"},
            "reviewed_at":      {"label": "Revisado",         "type": "date"},
            "reimbursed_at":    {"label": "Reembolsado",      "type": "date"},
            "notes":            {"label": "Notas",            "type": "str"},
            "created_at":       {"label": "Creado",           "type": "date"},
        },
    },
    "sprints": {
        "label": "Sprints",
        "group": "proyectos_recursos",
        "columns": {
            "number":           {"label": "Nº Sprint",         "type": "int"},
            "name":             {"label": "Nombre",            "type": "str"},
            "goal":             {"label": "Objetivo",          "type": "str"},
            "status":           {"label": "Estado",            "type": "str"},
            "start_date":       {"label": "Inicio",            "type": "date"},
            "end_date":         {"label": "Fin",               "type": "date"},
            "closed_at":        {"label": "Cerrado",           "type": "date"},
            "planned_points":   {"label": "Puntos planif.",    "type": "float"},
            "completed_points": {"label": "Puntos completados","type": "float"},
            "velocity":         {"label": "Velocidad",         "type": "float"},
            "went_well":        {"label": "¿Qué fue bien?",    "type": "str"},
            "to_improve":       {"label": "A mejorar",         "type": "str"},
        },
    },
    "tickets": {
        "label": "Tickets Service Desk",
        "group": "service_desk",
        "columns": {
            "number":               {"label": "Número",             "type": "str"},
            "title":                {"label": "Título",             "type": "str"},
            "ticket_type":          {"label": "Tipo",               "type": "str"},
            "status":               {"label": "Estado",             "type": "str"},
            "priority":             {"label": "Prioridad",          "type": "str"},
            "urgency":              {"label": "Urgencia",           "type": "str"},
            "impact":               {"label": "Impacto",            "type": "str"},
            "support_level":        {"label": "Nivel soporte",      "type": "str"},
            "requester_name":       {"label": "Solicitante",        "type": "str"},
            "requester_email":      {"label": "Email solicitante",  "type": "str"},
            "sla_response_status":  {"label": "Estado SLA resp.",   "type": "str"},
            "sla_resolution_status":{"label": "Estado SLA resol.",  "type": "str"},
            "sla_response_due":     {"label": "SLA respuesta hasta","type": "date"},
            "sla_resolution_due":   {"label": "SLA resol. hasta",   "type": "date"},
            "csat_score":           {"label": "CSAT (1-5)",         "type": "float"},
            "time_spent_minutes":   {"label": "Tiempo invertido (min)","type": "float"},
            "source":               {"label": "Canal origen",       "type": "str"},
            "resolution_code":      {"label": "Código resolución",  "type": "str"},
            "first_response_at":    {"label": "1ª respuesta",       "type": "date"},
            "resolved_at":          {"label": "Resuelto",           "type": "date"},
            "closed_at":            {"label": "Cerrado",            "type": "date"},
            "created_at":           {"label": "Creado",             "type": "date"},
        },
    },
    "opportunities": {
        "label": "Oportunidades (Pipeline)",
        "group": "pipeline_contratos",
        "columns": {
            "code":                 {"label": "Código",             "type": "str"},
            "name":                 {"label": "Nombre",             "type": "str"},
            "client_name":          {"label": "Cliente",            "type": "str"},
            "contact_name":         {"label": "Contacto",           "type": "str"},
            "contact_email":        {"label": "Email contacto",     "type": "str"},
            "stage":                {"label": "Etapa",              "type": "str"},
            "probability":          {"label": "Probabilidad (%)",   "type": "float"},
            "expected_revenue":     {"label": "Ingresos esperados", "type": "float"},
            "expected_margin_pct":  {"label": "Margen esperado (%)", "type": "float"},
            "expected_hours":       {"label": "Horas estimadas",    "type": "float"},
            "expected_close_date":  {"label": "Cierre esperado",    "type": "date"},
            "expected_start_date":  {"label": "Inicio esperado",    "type": "date"},
            "expected_duration_weeks": {"label": "Duración (sem.)", "type": "float"},
            "lost_reason":          {"label": "Motivo pérdida",     "type": "str"},
            "notes":                {"label": "Notas",              "type": "str"},
            "created_at":           {"label": "Creada",             "type": "date"},
            "updated_at":           {"label": "Actualizada",        "type": "date"},
        },
    },
    "contracts": {
        "label": "Contratos",
        "group": "pipeline_contratos",
        "columns": {
            "code":             {"label": "Código",           "type": "str"},
            "name":             {"label": "Nombre",           "type": "str"},
            "client_name":      {"label": "Cliente",          "type": "str"},
            "client_contact":   {"label": "Contacto",         "type": "str"},
            "contract_type":    {"label": "Tipo contrato",    "type": "str"},
            "status":           {"label": "Estado",           "type": "str"},
            "total_amount":     {"label": "Importe total",    "type": "float"},
            "hourly_rate":      {"label": "Tarifa horaria",   "type": "float"},
            "hours_bag":        {"label": "Bolsa de horas",   "type": "float"},
            "hours_used":       {"label": "Horas usadas",     "type": "float"},
            "monthly_retainer": {"label": "Retainer mensual", "type": "float"},
            "start_date":       {"label": "Inicio",           "type": "date"},
            "end_date":         {"label": "Vencimiento",      "type": "date"},
            "signed_date":      {"label": "Fecha firma",      "type": "date"},
            "payment_terms":    {"label": "Condiciones pago", "type": "str"},
            "notes":            {"label": "Notas",            "type": "str"},
            "created_at":       {"label": "Creado",           "type": "date"},
        },
    },
    "risks": {
        "label": "Riesgos",
        "group": "proyectos_recursos",
        "columns": {
            "code":               {"label": "Código",             "type": "str"},
            "title":              {"label": "Título",             "type": "str"},
            "category":           {"label": "Categoría",          "type": "str"},
            "probability":        {"label": "Probabilidad",       "type": "str"},
            "impact":             {"label": "Impacto",            "type": "str"},
            "risk_score":         {"label": "Puntuación riesgo",  "type": "float"},
            "status":             {"label": "Estado",             "type": "str"},
            "response_type":      {"label": "Respuesta",          "type": "str"},
            "mitigation_plan":    {"label": "Plan mitigación",    "type": "str"},
            "cost_impact_min":    {"label": "Coste mín. (€)",     "type": "float"},
            "cost_impact_max":    {"label": "Coste máx. (€)",     "type": "float"},
            "schedule_impact_days":{"label": "Impacto plazo (días)","type": "float"},
            "identified_date":    {"label": "Identificado",       "type": "date"},
            "review_date":        {"label": "Revisión",           "type": "date"},
            "closed_date":        {"label": "Cerrado",            "type": "date"},
            "created_at":         {"label": "Creado",             "type": "date"},
        },
    },
    "absences": {
        "label": "Ausencias / Vacaciones",
        "group": "personas",
        "columns": {
            "type":             {"label": "Tipo ausencia",    "type": "str"},
            "status":           {"label": "Estado",           "type": "str"},
            "start_date":       {"label": "Inicio",           "type": "date"},
            "end_date":         {"label": "Fin",              "type": "date"},
            "working_days":     {"label": "Días laborables",  "type": "float"},
            "reason":           {"label": "Motivo",           "type": "str"},
            "rejection_reason": {"label": "Motivo rechazo",   "type": "str"},
            "approved_at":      {"label": "Aprobado",         "type": "date"},
            "created_at":       {"label": "Solicitada",       "type": "date"},
        },
    },
    "timesheets": {
        "label": "Partes de horas (Timesheets)",
        "group": "tiempo_costes",
        "columns": {
            "week_start":       {"label": "Semana inicio",    "type": "date"},
            "week_end":         {"label": "Semana fin",       "type": "date"},
            "status":           {"label": "Estado",           "type": "str"},
            "total_hours":      {"label": "Total horas",      "type": "float"},
            "billable_hours":   {"label": "Horas facturables","type": "float"},
            "total_cost":       {"label": "Coste total (€)",  "type": "float"},
            "submitted_at":     {"label": "Enviado",          "type": "date"},
            "reviewed_at":      {"label": "Revisado",         "type": "date"},
            "review_notes":     {"label": "Notas revisión",   "type": "str"},
            "created_at":       {"label": "Creado",           "type": "date"},
        },
    },
    "milestones": {
        "label": "Hitos de proyecto",
        "group": "proyectos_recursos",
        "columns": {
            "name":                 {"label": "Nombre",             "type": "str"},
            "description":          {"label": "Descripción",        "type": "str"},
            "due_date":             {"label": "Fecha objetivo",     "type": "date"},
            "is_completed":         {"label": "Completado",         "type": "bool"},
            "completed_date":       {"label": "Fecha completado",   "type": "date"},
            "billing_status":       {"label": "Estado facturación", "type": "str"},
            "billing_amount":       {"label": "Importe factura (€)","type": "float"},
            "billing_pct":          {"label": "Porcentaje factura", "type": "float"},
            "is_billed":            {"label": "Facturado",          "type": "bool"},
            "billed_at":            {"label": "Fecha factura",      "type": "date"},
            "created_at":           {"label": "Creado",             "type": "date"},
        },
    },
    "deliverables": {
        "label": "Entregables",
        "group": "proyectos_recursos",
        "columns": {
            "code":             {"label": "Código",           "type": "str"},
            "name":             {"label": "Nombre",           "type": "str"},
            "description":      {"label": "Descripción",      "type": "str"},
            "format":           {"label": "Formato",          "type": "str"},
            "status":           {"label": "Estado",           "type": "str"},
            "planned_date":     {"label": "Fecha planif.",    "type": "date"},
            "delivered_date":   {"label": "Entregado",        "type": "date"},
            "accepted_date":    {"label": "Aceptado",         "type": "date"},
            "client_contact":   {"label": "Contacto cliente", "type": "str"},
            "rejection_reason": {"label": "Motivo rechazo",   "type": "str"},
            "created_at":       {"label": "Creado",           "type": "date"},
        },
    },
    "clients": {
        "label": "Clientes",
        "group": "pipeline_contratos",
        "columns": {
            "name":             {"label": "Nombre",           "type": "str"},
            "short_name":       {"label": "Nombre corto",     "type": "str"},
            "tax_id":           {"label": "NIF / Tax ID",     "type": "str"},
            "industry":         {"label": "Sector",           "type": "str"},
            "status":           {"label": "Estado",           "type": "str"},
            "contact_name":     {"label": "Contacto nombre",  "type": "str"},
            "contact_email":    {"label": "Contacto email",   "type": "str"},
            "contact_phone":    {"label": "Teléfono",         "type": "str"},
            "contact_role":     {"label": "Cargo contacto",   "type": "str"},
            "website":          {"label": "Web",              "type": "str"},
            "city":             {"label": "Ciudad",           "type": "str"},
            "country":          {"label": "País",             "type": "str"},
            "payment_terms":    {"label": "Condiciones pago", "type": "str"},
            "credit_limit":     {"label": "Límite crédito",   "type": "float"},
            "currency":         {"label": "Moneda",           "type": "str"},
            "is_active":        {"label": "Activo",           "type": "bool"},
            "created_at":       {"label": "Alta",             "type": "date"},
        },
    },
    "subcontractors": {
        "label": "Subcontratistas (empresas)",
        "group": "subcontratistas",
        "columns": {
            "code":         {"label": "Código",       "type": "str"},
            "name":         {"label": "Nombre",       "type": "str"},
            "company":      {"label": "Empresa",      "type": "str"},
            "email":        {"label": "Email",        "type": "str"},
            "phone":        {"label": "Teléfono",     "type": "str"},
            "country":      {"label": "País",         "type": "str"},
            "vat_number":   {"label": "NIF / VAT",    "type": "str"},
            "currency":     {"label": "Moneda",       "type": "str"},
            "is_active":    {"label": "Activo",       "type": "bool"},
            "notes":        {"label": "Notas",        "type": "str"},
            "created_at":   {"label": "Alta",         "type": "date"},
        },
    },
    "subcontractor_workers": {
        "label": "Subcontratistas (personas)",
        "group": "subcontratistas",
        "columns": {
            "name":             {"label": "Nombre",           "type": "str"},
            "role":             {"label": "Rol / Perfil",     "type": "str"},
            "email":            {"label": "Email",            "type": "str"},
            "phone":            {"label": "Teléfono",         "type": "str"},
            "cost_rate":        {"label": "Tarifa coste (€/h)","type": "float"},
            "sell_rate":        {"label": "Tarifa venta (€/h)","type": "float"},
            "currency":         {"label": "Moneda",           "type": "str"},
            "available_from":   {"label": "Disponible desde", "type": "date"},
            "available_until":  {"label": "Disponible hasta", "type": "date"},
            "is_active":        {"label": "Activo",           "type": "bool"},
            "created_at":       {"label": "Alta",             "type": "date"},
        },
    },
    "subcontractor_assignments": {
        "label": "Asignaciones subcontratistas",
        "group": "subcontratistas",
        "columns": {
            "po_number":         {"label": "Nº Pedido (PO)",     "type": "str"},
            "po_amount":         {"label": "Techo PO (€)",       "type": "float"},
            "hours_contracted":  {"label": "Horas contratadas",  "type": "float"},
            "hours_logged":      {"label": "Horas registradas",  "type": "float"},
            "start_date":        {"label": "Inicio",             "type": "date"},
            "end_date":          {"label": "Fin",                "type": "date"},
            "notes":             {"label": "Notas",              "type": "str"},
            "created_at":        {"label": "Creada",             "type": "date"},
        },
    },
    "problems": {
        "label": "Problemas (ITSM)",
        "group": "service_desk",
        "columns": {
            "number":           {"label": "Número",           "type": "str"},
            "title":            {"label": "Título",           "type": "str"},
            "status":           {"label": "Estado",           "type": "str"},
            "priority":         {"label": "Prioridad",        "type": "str"},
            "root_cause":       {"label": "Causa raíz",       "type": "str"},
            "workaround":       {"label": "Solución temporal","type": "str"},
            "fix_description":  {"label": "Solución definitiva","type": "str"},
            "resolved_at":      {"label": "Resuelto",         "type": "date"},
            "created_at":       {"label": "Creado",           "type": "date"},
        },
    },
    "kb_articles": {
        "label": "Artículos base de conocimiento",
        "group": "service_desk",
        "columns": {
            "number":           {"label": "Número",           "type": "str"},
            "title":            {"label": "Título",           "type": "str"},
            "summary":          {"label": "Resumen",          "type": "str"},
            "status":           {"label": "Estado",           "type": "str"},
            "tags":             {"label": "Etiquetas",        "type": "str"},
            "is_public":        {"label": "Público",          "type": "bool"},
            "view_count":       {"label": "Visualizaciones",  "type": "int"},
            "helpful_count":    {"label": "Útil (votos)",     "type": "int"},
            "not_helpful_count":{"label": "No útil (votos)",  "type": "int"},
            "published_at":     {"label": "Publicado",        "type": "date"},
            "created_at":       {"label": "Creado",           "type": "date"},
        },
    },
}

GROUPS: Dict[str, str] = {
    "proyectos_recursos":  "Proyectos y Recursos",
    "tiempo_costes":       "Tiempo y Costes",
    "personas":            "Personas y Equipo",
    "pipeline_contratos":  "Pipeline y Contratos",
    "subcontratistas":     "Subcontratistas",
    "service_desk":        "Service Desk / ITSM",
}

OPERATORS = {
    "eq":          {"label": "igual a"},
    "neq":         {"label": "distinto de"},
    "gt":          {"label": "mayor que"},
    "lt":          {"label": "menor que"},
    "gte":         {"label": "mayor o igual"},
    "lte":         {"label": "menor o igual"},
    "contains":    {"label": "contiene"},
    "not_contains":{"label": "no contiene"},
    "in":          {"label": "está en (lista)"},
    "is_null":     {"label": "está vacío"},
    "is_not_null": {"label": "no está vacío"},
    "starts_with": {"label": "empieza por"},
}

# ── Pydantic schemas ───────────────────────────────────────────────────────

class FilterCondition(BaseModel):
    column:   str
    operator: str
    value:    Any

class SortSpec(BaseModel):
    column: str
    direction: str = "asc"  # asc | desc

class ReportQuery(BaseModel):
    entity:  str
    columns: List[str]
    filters: List[FilterCondition] = []
    sort:    Optional[SortSpec] = None
    limit:   int = 500

class ReportTemplate(BaseModel):
    name:   str
    query:  ReportQuery

# ── Template persistence helpers (AppSetting table) ───────────────────────

_TEMPLATE_KEY_PREFIX = "report_templates:"


def _load_user_templates(user_id: str, db: Session) -> List[dict]:
    from app.models.settings import AppSetting
    row = db.query(AppSetting).filter(
        AppSetting.key == f"{_TEMPLATE_KEY_PREFIX}{user_id}"
    ).first()
    if not row or not row.value:
        return []
    try:
        return json.loads(row.value)
    except (json.JSONDecodeError, TypeError):
        return []


def _save_user_templates(user_id: str, templates: List[dict], db: Session) -> None:
    from app.models.settings import AppSetting
    key = f"{_TEMPLATE_KEY_PREFIX}{user_id}"
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    serialized = json.dumps(templates)
    if row:
        row.value = serialized
    else:
        db.add(AppSetting(key=key, value=serialized, description="Report Builder templates"))
    db.commit()

# ── Helpers ───────────────────────────────────────────────────────────────

def _get_model_class(entity: str):
    """Resolve entity name to SQLAlchemy model."""
    from app.models.project import Project
    from app.models.task import Task
    from app.models.user import User
    from app.models.imputation import Imputation

    mapping: Dict[str, Any] = {
        "projects":    Project,
        "tasks":       Task,
        "users":       User,
        "imputations": Imputation,
    }

    _optional = [
        ("app.models.expenses",  "Expense",                   "expenses"),
        ("app.models.sprints",   "Sprint",                    "sprints"),
        # Financial / delivery
        ("app.models.financial", "Timesheet",                 "timesheets"),
        ("app.models.financial", "ProjectMilestone",          "milestones"),
        # Pipeline / contracts / clients
        ("app.models.pipeline",  "Opportunity",               "opportunities"),
        ("app.models.pipeline",  "Contract",                  "contracts"),
        ("app.models.pipeline",  "WorkOrder",                 None),  # fallback key below
        ("app.models.clients",   "Client",                    "clients"),
        # Projects extras
        ("app.models.resources", "Risk",                      "risks"),
        ("app.models.resources", "Absence",                   "absences"),
        ("app.models.resources", "Deliverable",               "deliverables"),
        # Service desk
        ("app.models.service_desk", "Ticket",                 "tickets"),
        ("app.models.service_desk", "Problem",                "problems"),
        ("app.models.service_desk", "KBArticle",              "kb_articles"),
        # Subcontractors
        ("app.models.enterprise", "Subcontractor",            "subcontractors"),
        ("app.models.enterprise", "SubcontractorWorker",      "subcontractor_workers"),
        ("app.models.enterprise", "SubcontractorAssignment",  "subcontractor_assignments"),
    ]

    for module_path, class_name, key in _optional:
        try:
            import importlib
            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name, None)
            if cls is not None and key is not None:
                mapping[key] = cls
        except (ImportError, AttributeError):
            pass

    return mapping.get(entity)


def _apply_filter(query, model, condition: FilterCondition):
    """Apply a single filter condition to a SQLAlchemy query."""
    if not hasattr(model, condition.column):
        return query  # skip unknown columns silently

    col = getattr(model, condition.column)
    op  = condition.operator
    v   = condition.value

    if op == "eq":
        query = query.filter(col == v)
    elif op == "neq":
        query = query.filter(col != v)
    elif op == "gt":
        query = query.filter(col > v)
    elif op == "lt":
        query = query.filter(col < v)
    elif op == "gte":
        query = query.filter(col >= v)
    elif op == "lte":
        query = query.filter(col <= v)
    elif op == "contains":
        query = query.filter(col.ilike(f"%{v}%"))
    elif op == "not_contains":
        query = query.filter(col.notilike(f"%{v}%"))
    elif op == "starts_with":
        query = query.filter(col.ilike(f"{v}%"))
    elif op == "in":
        if isinstance(v, list):
            query = query.filter(col.in_(v))
    elif op == "is_null":
        query = query.filter(col.is_(None))
    elif op == "is_not_null":
        query = query.filter(col.isnot(None))
    return query


def _serialize_value(v):
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def _execute_report(q: ReportQuery, db: Session, current_user: User) -> List[Dict]:
    model = _get_model_class(q.entity)
    if model is None:
        raise HTTPException(400, f"Entidad '{q.entity}' no soportada en este entorno")

    entity_def = ENTITIES.get(q.entity, {})
    allowed_cols = set(entity_def.get("columns", {}).keys())

    # Validate requested columns
    for c in q.columns:
        if c not in allowed_cols:
            raise HTTPException(400, f"Columna '{c}' no permitida para la entidad '{q.entity}'")

    db_query = db.query(model)

    # ── Tenant isolation ──────────────────────────────────────────────────────
    # Superadmins see all data; all other users are scoped to their organisation.
    if not current_user.is_superadmin and current_user.organization_id:
        org_id = current_user.organization_id
        if hasattr(model, "organization_id"):
            db_query = db_query.filter(model.organization_id == org_id)
        elif hasattr(model, "project_id"):
            # Scope through projects owned by the user's organisation
            from app.models.project import Project as _Proj
            proj_ids = db.query(_Proj.id).filter(
                _Proj.organization_id == org_id
            ).scalar_subquery()
            db_query = db_query.filter(model.project_id.in_(proj_ids))
        elif q.entity == "users":
            db_query = db_query.filter(model.organization_id == org_id)

    # Apply filters
    for f in q.filters:
        if f.column not in allowed_cols:
            raise HTTPException(400, f"Columna de filtro '{f.column}' no permitida")
        if f.operator not in OPERATORS:
            raise HTTPException(400, f"Operador '{f.operator}' no soportado")
        db_query = _apply_filter(db_query, model, f)

    # Sort
    if q.sort and q.sort.column in allowed_cols and hasattr(model, q.sort.column):
        col = getattr(model, q.sort.column)
        db_query = db_query.order_by(col.desc() if q.sort.direction == "desc" else col.asc())

    rows = db_query.limit(min(q.limit, 2000)).all()

    result = []
    for row in rows:
        record = {}
        for c in q.columns:
            if hasattr(row, c):
                record[c] = _serialize_value(getattr(row, c))
            else:
                record[c] = None
        result.append(record)

    return result


# ── Routes ────────────────────────────────────────────────────────────────

@router.get("/schema")
def get_schema(_: User = Depends(get_current_user)):
    """Return available entities, columns, and operators for the UI builder."""
    return {
        "entities":  ENTITIES,
        "operators": OPERATORS,
        "groups":    GROUPS,
    }


@router.post("/preview")
def preview_report(
    q: ReportQuery,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Execute a report query and return rows (max 500 preview limit)."""
    if q.entity not in ENTITIES:
        raise HTTPException(400, f"Entidad '{q.entity}' desconocida")
    q.limit = min(q.limit, 500)
    rows = _execute_report(q, db, current_user)
    return {"rows": rows, "count": len(rows), "truncated": len(rows) == q.limit}


@router.post("/export")
def export_report(
    q: ReportQuery,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Execute a report query and return CSV file."""
    if q.entity not in ENTITIES:
        raise HTTPException(400, f"Entidad '{q.entity}' desconocida")
    q.limit = 2000
    rows = _execute_report(q, db, current_user)

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=q.columns)
    writer.writeheader()
    writer.writerows(rows)
    buf.seek(0)

    filename = f"report_{q.entity}_{date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/templates")
def list_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _load_user_templates(str(current_user.id), db)


@router.post("/templates")
def save_template(
    tpl: ReportTemplate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if tpl.query.entity not in ENTITIES:
        raise HTTPException(400, f"Entidad '{tpl.query.entity}' desconocida")
    templates = _load_user_templates(str(current_user.id), db)
    next_id = max((t["id"] for t in templates), default=0) + 1
    record = {"id": next_id, "name": tpl.name, "query": tpl.query.model_dump()}
    templates.append(record)
    _save_user_templates(str(current_user.id), templates, db)
    return record


@router.delete("/templates/{template_id}")
def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    templates = _load_user_templates(str(current_user.id), db)
    updated = [t for t in templates if t["id"] != template_id]
    if len(updated) == len(templates):
        raise HTTPException(404, "Plantilla no encontrada")
    _save_user_templates(str(current_user.id), updated, db)
    return {"ok": True}
