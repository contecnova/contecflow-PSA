"""
Report Builder Service — business logic extracted from report_builder.py router.
Handles: entity schema, query execution, CSV export, template CRUD (stored in AppSetting).
"""
from __future__ import annotations

import csv
import io
import importlib
import json
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from app.models.user import User
from app.models.imputation import Imputation
from app.models.project import Project
from app.models.project import Project as _Proj
from app.models.settings import AppSetting
from app.models.task import Task
from app.core import timeutil
from app.services.pagination_service import paginate_query

# ── Entity catalog (static config) ───────────────────────────────────────────

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

# ── Template persistence helpers (AppSetting table) ───────────────────────────

_TEMPLATE_KEY_PREFIX = "report_templates:"


def load_user_templates(user_id: str, db: Session) -> List[dict]:
    row = db.query(AppSetting).filter(
        AppSetting.key == f"{_TEMPLATE_KEY_PREFIX}{user_id}"
    ).first()
    if not row or not row.value:
        return []
    try:
        return json.loads(row.value)
    except (json.JSONDecodeError, TypeError):
        return []


def save_user_templates(user_id: str, templates: List[dict], db: Session) -> None:
    key = f"{_TEMPLATE_KEY_PREFIX}{user_id}"
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    serialized = json.dumps(templates)
    if row:
        row.value = serialized
    else:
        db.add(AppSetting(key=key, value=serialized,
                          description="Report Builder templates"))
    db.commit()


# ── Model resolution ──────────────────────────────────────────────────────────

def get_model_class(entity: str):

    mapping: Dict[str, Any] = {
        "projects":    Project,
        "tasks":       Task,
        "users":       User,
        "imputations": Imputation,
    }

    _optional = [
        ("app.models.expenses",  "Expense",                   "expenses"),
        ("app.models.sprints",   "Sprint",                    "sprints"),
        ("app.models.financial", "Timesheet",                 "timesheets"),
        ("app.models.financial", "ProjectMilestone",          "milestones"),
        ("app.models.pipeline",  "Opportunity",               "opportunities"),
        ("app.models.pipeline",  "Contract",                  "contracts"),
        ("app.models.clients",   "Client",                    "clients"),
        # `Risk` vive en `pipeline`, no en `resources`. Estaba mal escrito y el
        # `getattr(..., None)` de abajo se lo tragaba: `get_model_class("risks")`
        # devolvia None y TODO informe sobre riesgos respondia 400 «entidad no
        # soportada en este entorno», mientras el catalogo ofrecia sus 16
        # columnas en la interfaz. Auditoria 2026-08, hallazgo 18.
        ("app.models.pipeline",  "Risk",                      "risks"),
        ("app.models.resources", "Absence",                   "absences"),
        ("app.models.resources", "Deliverable",               "deliverables"),
        ("app.models.service_desk", "Ticket",                 "tickets"),
        ("app.models.service_desk", "Problem",                "problems"),
        ("app.models.service_desk", "KBArticle",              "kb_articles"),
        ("app.models.enterprise", "Subcontractor",            "subcontractors"),
        ("app.models.enterprise", "SubcontractorWorker",      "subcontractor_workers"),
        ("app.models.enterprise", "SubcontractorAssignment",  "subcontractor_assignments"),
    ]

    for module_path, class_name, key in _optional:
        try:
            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name, None)
            if cls is not None and key is not None:
                mapping[key] = cls
        except (ImportError, AttributeError):
            pass

    return mapping.get(entity)


# ── Filter application ────────────────────────────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 18). `apply_filter` era complejidad 15: doce
# `elif` sobre el mismo `operator` en treinta lineas, la tabla de despacho mas
# limpia que quedaba en el repo. Y traia defecto.
#
# EL DEFECTO. `operator: "in"` con un valor que NO era una lista caia en
#
#     elif operator == "in":
#         if isinstance(value, list):
#             query = query.filter(col.in_(value))
#
# sin rama alternativa, asi que la funcion DEVOLVIA LA CONSULTA SIN FILTRAR —
# todas las filas. Y pasaba las dos validaciones del llamador, que si existen y
# si devuelven 400 (`op in OPERATORS` y `col_name in allowed_cols`), porque lo
# que fallaba era el TIPO del valor, y `value` esta declarado `Any` sin
# validacion de esquema. Quien pedia «estado esta en [...]» no recibia un error:
# recibia el informe completo, con cifras plausibles.
#
# LA INVARIANTE que fija el arreglo: **ningun operador de la tabla puede dejar
# la consulta sin filtrar**. Cada entrada devuelve una clausula, siempre. Un
# valor del tipo equivocado se interpreta de la forma que mas se acerca a lo
# pedido —un escalar en un `in` es una lista de uno— pero nunca se convierte en
# «no filtres nada».
#
# La otra puerta al mismo fallo era `if not hasattr(model, column): return
# query`, con una columna que el catalogo declara y el modelo no tiene. Hoy es
# inalcanzable —las 243 columnas de `ENTITIES` existen todas en su modelo, y hay
# un test estructural que lo mantiene asi— pero devolver sin filtrar no es la
# reaccion correcta a una incoherencia de catalogo. Ahora es un 500: el error es
# del servidor, no de quien pide el informe, y un 500 se ve en los logs mientras
# que un informe completo de mas no se ve en ningun sitio.


def _lista(value: Any) -> list:
    """El valor de un `in`, siempre como lista.

    Un escalar se interpreta como lista de un elemento, que es lo que la persona
    quería decir. Lo que NO puede pasar es que un valor mal tipado deje la
    consulta sin filtrar: `col.in_([])` y `col.in_([None])` no devuelven filas,
    y eso es correcto para «está en el conjunto vacío» — devolverlo todo no lo
    es para nada.
    """
    if isinstance(value, (list, tuple, set, frozenset)):
        return list(value)
    return [value]


# Los doce operadores del constructor de informes. `OPERATORS` lleva sus
# etiquetas para la interfaz; esta tabla, su traducción a SQL. Las dos tienen que
# cubrir exactamente las mismas claves, y hay un test que lo cruza: si divergen,
# un operador que la validación acepta y esta tabla no implementa volvería a
# devolver todo sin filtrar, que es el mismo fallo por otra puerta.
_CLAUSULAS: Dict[str, Any] = {
    "eq":           lambda col, v: col == v,
    "neq":          lambda col, v: col != v,
    "gt":           lambda col, v: col > v,
    "lt":           lambda col, v: col < v,
    "gte":          lambda col, v: col >= v,
    "lte":          lambda col, v: col <= v,
    "contains":     lambda col, v: col.ilike(f"%{v}%"),
    "not_contains": lambda col, v: col.notilike(f"%{v}%"),
    "starts_with":  lambda col, v: col.ilike(f"{v}%"),
    "in":           lambda col, v: col.in_(_lista(v)),
    # Los dos de nulidad ignoran el valor a propósito: «está vacío» no lleva
    # operando, y la interfaz no manda ninguno.
    "is_null":      lambda col, v: col.is_(None),
    "is_not_null":  lambda col, v: col.isnot(None),
}

#: Los operadores que esta capa sabe traducir a SQL. Público para que el test
#: estructural los cruce con `OPERATORS` sin tocar el diccionario privado.
OPERADORES_SOPORTADOS = frozenset(_CLAUSULAS)


def apply_filter(query, model, column: str, operator: str, value: Any):
    """Añade a `query` la cláusula de un filtro del constructor de informes.

    El llamador valida antes que `column` esté en el catálogo de la entidad y
    que `operator` esté en `OPERATORS`, y devuelve 400 si no. Lo que esta
    función garantiza es lo que aquello no cubría: **que nunca devuelva la
    consulta sin filtrar**. Una columna que el modelo no tenga o un operador sin
    traducción son incoherencias del servidor, y se lanzan como tales.
    """
    if not hasattr(model, column):
        raise HTTPException(
            500,
            f"Catálogo de informes incoherente: la columna '{column}' no existe "
            f"en {model.__name__}",
        )
    clausula = _CLAUSULAS.get(operator)
    if clausula is None:
        raise HTTPException(
            500,
            f"Catálogo de informes incoherente: el operador '{operator}' no "
            f"tiene traducción a SQL",
        )
    return query.filter(clausula(getattr(model, column), value))


def _serialize_value(v: Any) -> Any:
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


# ── Core report execution ─────────────────────────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 18). `execute_report` y `execute_report_paginated`
# eran LA MISMA FUNCION. Medido con `difflib` sobre sus cuerpos, ignorando
# sangria: 41 de 50 lineas identicas, el 82 %. Lo unico que cambiaba era la
# firma y el bloque final —una devolvia una lista con `limit`, la otra un
# diccionario con `paginate_query`—; el acotado por tenant, la validacion de
# columnas, el bucle de filtros y el orden eran copia exacta.
#
# El coste no era el numero de lineas: era que **una podia arreglar un fallo y
# la otra no**. En este mismo repo eso ya paso dos veces —PUT y PATCH de SCIM
# cubriendo campos distintos, y las dos copias del sondeo SNMP divergiendo— asi
# que no es un riesgo hipotetico. Ahora las dos llaman a `_preparar_consulta`.


def _valor_del_filtro(f, clave: str, defecto=None):
    """Un campo de un filtro, venga como objeto o como diccionario.

    Los dos llamadores pasan lo que les llega del endpoint, que puede ser un
    modelo de Pydantic o un `dict` crudo segun la ruta.
    """
    return getattr(f, clave) if hasattr(f, clave) else f.get(clave, defecto)


def _acotar_por_tenant(db_query, model, current_user, db):
    """Limita la consulta a la organización de quien pide el informe.

    Un superadministrador de plataforma ve todo a propósito. Para el resto se
    filtra por `organization_id` si el modelo la tiene, y si no por los
    proyectos de su organización.

    **La rama sin acotar** —un usuario que no es superadministrador y no tiene
    organización— no es alcanzable, y conviene saber por qué: `organization_id`
    es `nullable=False` en `app/models/user.py`, así que un usuario autenticado
    siempre trae organización. Es una dependencia de OTRO fichero, de modo que
    si alguien relaja esa restricción esta rama se abre; por debajo queda el
    listener `do_orm_execute` de `app/db/session.py`, que es la segunda barrera.
    Las 20 entidades del catálogo de informes tienen `organization_id`, y hay un
    test que lo comprueba.
    """
    if current_user.is_superadmin or not current_user.organization_id:
        return db_query

    org_id = current_user.organization_id
    if hasattr(model, "organization_id"):
        return db_query.filter(model.organization_id == org_id)
    if hasattr(model, "project_id"):
        proj_ids = db.query(_Proj.id).filter(
            _Proj.organization_id == org_id
        ).scalar_subquery()
        return db_query.filter(model.project_id.in_(proj_ids))
    return db_query


def _preparar_consulta(
    entity: str, columns: List[str], filters: list, sort_column: Optional[str],
    sort_direction: str, current_user: User, db: Session,
):
    """La consulta de un informe, montada y sin ejecutar.

    Devuelve `(model, db_query)`. Todo lo que comparten la vista sin paginar y
    la paginada está aquí: resolución de la entidad, validación de columnas
    contra el catálogo, acotado por tenant, filtros y orden. Lo único que cambia
    entre las dos es cómo se materializa el resultado.
    """
    model = get_model_class(entity)
    if model is None:
        raise HTTPException(400, f"Entidad '{entity}' no soportada en este entorno")

    entity_def = ENTITIES.get(entity, {})
    allowed_cols = set(entity_def.get("columns", {}).keys())

    for c in columns:
        if c not in allowed_cols:
            raise HTTPException(400, f"Columna '{c}' no permitida para la entidad '{entity}'")

    db_query = _acotar_por_tenant(db.query(model), model, current_user, db)

    for f in filters:
        col_name = _valor_del_filtro(f, "column", "")
        op = _valor_del_filtro(f, "operator", "")
        val = _valor_del_filtro(f, "value")
        if col_name not in allowed_cols:
            raise HTTPException(400, f"Columna de filtro '{col_name}' no permitida")
        if op not in OPERATORS:
            raise HTTPException(400, f"Operador '{op}' no soportado")
        db_query = apply_filter(db_query, model, col_name, op, val)

    # Un `sort_column` que no esté en el catálogo se ignora en silencio, y es lo
    # correcto: el orden es una preferencia de presentación, no parte de lo que
    # se pide. Un filtro inválido sí es un 400, porque cambia QUÉ filas salen.
    if sort_column and sort_column in allowed_cols and hasattr(model, sort_column):
        col = getattr(model, sort_column)
        db_query = db_query.order_by(
            col.desc() if sort_direction == "desc" else col.asc()
        )

    return model, db_query


def _serializar(filas, columns: List[str]) -> List[Dict]:
    """Las filas como diccionarios, sólo con las columnas pedidas.

    El `getattr(..., None)` cubre una columna del catálogo que el modelo no
    tenga. Es la misma incoherencia que `apply_filter` convierte en 500, pero
    aquí se deja pasar como nulo a propósito: en un filtro cambia QUÉ filas
    salen, y en la presentación sólo deja una celda vacía.
    """
    return [
        {c: _serialize_value(getattr(row, c, None)) for c in columns}
        for row in filas
    ]


#: Tope duro de filas de una vista sin paginar, por encima de lo que pida quien
#: llama: una entidad grande sin límite devuelve megabytes que nadie lee.
_MAX_FILAS_SIN_PAGINAR = 2000


def execute_report(
    entity: str, columns: List[str], filters: list, sort_column: Optional[str],
    sort_direction: str, limit: int, current_user: User, db: Session,
) -> List[Dict]:
    """El informe sin paginar, para la vista previa. Usa `limit`."""
    _, db_query = _preparar_consulta(
        entity, columns, filters, sort_column, sort_direction, current_user, db
    )
    filas = db_query.limit(min(limit, _MAX_FILAS_SIN_PAGINAR)).all()
    return _serializar(filas, columns)


def execute_report_paginated(
    entity: str, columns: List[str], filters: list, sort_column: Optional[str],
    sort_direction: str, page: int, page_size: int, current_user: User, db: Session,
) -> dict:
    """El informe paginado de verdad, con el total y el número de páginas."""
    _, db_query = _preparar_consulta(
        entity, columns, filters, sort_column, sort_direction, current_user, db
    )
    items, total, pages = paginate_query(db_query, page, page_size)
    return {
        "items": _serializar(items, columns),
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
    }


def build_csv_response(columns: List[str], rows: List[Dict], entity: str, pagination: dict = None) -> StreamingResponse:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
    buf.seek(0)
    filename = f"report_{entity}_{timeutil.today().isoformat()}.csv"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    if pagination:
        headers["X-Total-Count"] = str(pagination.get("total", 0))
        headers["X-Page"] = str(pagination.get("page", 1))
        headers["X-Page-Size"] = str(pagination.get("page_size", len(rows)))
        headers["X-Total-Pages"] = str(pagination.get("pages", 1))
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers=headers,
    )
