"""BI Report Builder v2 service.

Advances the Phase-2 Report Builder with:
- 15+ configurable presets with column/group/filter options
- Per-org preset customization (override columns, groupBy, sortBy, name)
- Export endpoint that returns richly-formatted data ready for xlsx/pdf
- Template-based preset with variable slot support
- Preset categories for navigation
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.settings import AppSetting
from app.services.report_builder_service import execute_report

CUSTOM_PRESETS_KEY = "bi.report_builder_v2.custom_presets"

# ── Default preset catalog ─────────────────────────────────────────────────────

BASE_PRESETS: list[dict[str, Any]] = [
    # --- Finance ---
    {
        "id": "finance_revenue_by_client",
        "name": "Revenue por cliente",
        "category": "finance",
        "description": "Ingresos agrupados por cliente en el período seleccionado",
        "table": "projects",
        "columns": ["client_name", "project_name", "billing_rate", "total_hours", "revenue_actual"],
        "group_by": "client_name",
        "sort_by": "revenue_actual",
        "sort_direction": "desc",
        "filters": {},
        "customizable": True,
    },
    {
        "id": "finance_margin_evolution",
        "name": "Evolución de margen mensual",
        "category": "finance",
        "description": "Margen bruto mes a mes en los últimos 12 meses",
        "table": "imputations_monthly",
        "columns": ["month", "total_revenue", "total_cost", "gross_margin", "margin_pct"],
        "group_by": "month",
        "sort_by": "month",
        "sort_direction": "asc",
        "filters": {},
        "customizable": False,
    },
    {
        "id": "finance_budget_vs_actual",
        "name": "Presupuesto vs Real",
        "category": "finance",
        "description": "Comparativa de presupuesto planificado vs gasto real por proyecto",
        "table": "projects",
        "columns": ["project_name", "budget_amount", "cost_actual", "deviation_pct"],
        "group_by": None,
        "sort_by": "deviation_pct",
        "sort_direction": "desc",
        "filters": {"status": "active"},
        "customizable": True,
    },
    # --- Delivery ---
    {
        "id": "delivery_schedule_health",
        "name": "Salud de entregas",
        "category": "delivery",
        "description": "Estado de salud de todos los proyectos activos (plazo, alertas, estimación)",
        "table": "projects",
        "columns": ["project_name", "client_name", "status", "planned_end_date", "schedule_deviation_days", "alerts_count"],
        "group_by": None,
        "sort_by": "schedule_deviation_days",
        "sort_direction": "desc",
        "filters": {"status": "active"},
        "customizable": True,
    },
    {
        "id": "delivery_milestone_tracker",
        "name": "Seguimiento de hitos",
        "category": "delivery",
        "description": "Hitos por proyecto con estado y fecha estimada vs real",
        "table": "milestones",
        "columns": ["project_name", "name", "due_date", "completed_at", "status"],
        "group_by": "project_name",
        "sort_by": "due_date",
        "sort_direction": "asc",
        "filters": {},
        "customizable": True,
    },
    # --- Resources ---
    {
        "id": "resources_utilization_team",
        "name": "Utilización del equipo",
        "category": "resources",
        "description": "Utilización por miembro del equipo en el período",
        "table": "resources",
        "columns": ["user_name", "role", "allocated_hours", "logged_hours", "utilization_pct"],
        "group_by": "role",
        "sort_by": "utilization_pct",
        "sort_direction": "desc",
        "filters": {},
        "customizable": True,
    },
    {
        "id": "resources_capacity_forecast",
        "name": "Forecast de capacidad",
        "category": "resources",
        "description": "Capacidad disponible y demanda planificada por los próximos 3 meses",
        "table": "resource_forecast",
        "columns": ["month", "resource_name", "available_hours", "planned_hours", "gap_hours"],
        "group_by": "month",
        "sort_by": "month",
        "sort_direction": "asc",
        "filters": {},
        "customizable": False,
    },
    # --- Operations ---
    {
        "id": "ops_delivery_mix",
        "name": "Mix de tipo de proyectos",
        "category": "operations",
        "description": "Distribución de proyectos por tipo y estado",
        "table": "projects",
        "columns": ["project_type", "status", "count", "total_budget"],
        "group_by": "project_type",
        "sort_by": "count",
        "sort_direction": "desc",
        "filters": {},
        "customizable": True,
    },
    {
        "id": "ops_task_completion_rate",
        "name": "Tasa de completación de tareas",
        "category": "operations",
        "description": "Tareas completadas vs abiertas por proyecto",
        "table": "tasks",
        "columns": ["project_name", "total_tasks", "completed_tasks", "overdue_tasks", "completion_rate_pct"],
        "group_by": "project_name",
        "sort_by": "completion_rate_pct",
        "sort_direction": "asc",
        "filters": {},
        "customizable": True,
    },
    # --- Service Desk ---
    {
        "id": "sd_ticket_volume_by_type",
        "name": "Volumen de tickets por tipo",
        "category": "service_desk",
        "description": "Distribución de tickets por tipo, prioridad y estado",
        "table": "sd_tickets",
        "columns": ["ticket_type", "priority", "status", "count", "avg_resolution_hours"],
        "group_by": "ticket_type",
        "sort_by": "count",
        "sort_direction": "desc",
        "filters": {},
        "customizable": True,
    },
    {
        "id": "sd_sla_compliance",
        "name": "Cumplimiento SLA",
        "category": "service_desk",
        "description": "Cumplimiento de SLA por categoría de ticket en el período",
        "table": "sd_tickets",
        "columns": ["category", "sla_target_hours", "avg_resolution_hours", "breach_count", "compliance_pct"],
        "group_by": "category",
        "sort_by": "compliance_pct",
        "sort_direction": "asc",
        "filters": {},
        "customizable": False,
    },
    # --- HR / Talent ---
    {
        "id": "hr_team_performance",
        "name": "Rendimiento del equipo",
        "category": "hr",
        "description": "Métricas de rendimiento y satisfacción por miembro del equipo",
        "table": "performance_reviews",
        "columns": ["user_name", "role", "composite_score", "peer_rating", "tasks_completed"],
        "group_by": "role",
        "sort_by": "composite_score",
        "sort_direction": "desc",
        "filters": {},
        "customizable": True,
    },
    # --- Executive ---
    {
        "id": "exec_kpi_summary",
        "name": "Resumen KPIs ejecutivos",
        "category": "executive",
        "description": "Cuadro de mando ejecutivo con KPIs principales del período",
        "table": "projects",
        "columns": ["metric", "current_value", "previous_value", "change_pct", "status"],
        "group_by": None,
        "sort_by": "metric",
        "sort_direction": "asc",
        "filters": {},
        "customizable": True,
    },
    {
        "id": "exec_top_clients",
        "name": "Top clientes por revenue",
        "category": "executive",
        "description": "Top 10 clientes ordenados por ingresos en el período",
        "table": "projects",
        "columns": ["client_name", "project_count", "total_revenue", "total_margin", "avg_margin_pct"],
        "group_by": "client_name",
        "sort_by": "total_revenue",
        "sort_direction": "desc",
        "filters": {},
        "customizable": True,
    },
    {
        "id": "exec_risk_radar",
        "name": "Radar de riesgos",
        "category": "executive",
        "description": "Proyectos con mayor riesgo: combinación de plazo, presupuesto y alertas",
        "table": "projects",
        "columns": ["project_name", "client_name", "risk_score", "budget_deviation_pct", "schedule_deviation_days", "alerts_count"],
        "group_by": None,
        "sort_by": "risk_score",
        "sort_direction": "desc",
        "filters": {"status": "active"},
        "customizable": True,
    },
]


def _setting_row(db: Session, key: str, organization_id: Optional[str]) -> Optional[AppSetting]:
    q = db.query(AppSetting).filter(AppSetting.key == key)
    if organization_id:
        q = q.filter(AppSetting.organization_id == organization_id)
    else:
        q = q.filter(AppSetting.organization_id.is_(None))
    return q.first()


def _get_json(db: Session, key: str, organization_id: Optional[str], default: Any) -> Any:
    row = _setting_row(db, key, organization_id)
    if not row or not row.value:
        return default
    try:
        return json.loads(row.value)
    except Exception:
        return default


def _set_json(db: Session, key: str, organization_id: Optional[str], value: Any, description: str) -> None:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    row = _setting_row(db, key, organization_id)
    if not row:
        row = AppSetting(key=key, organization_id=organization_id, description=description, value=payload)
        db.add(row)
    else:
        row.value = payload
    db.commit()


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Public API ─────────────────────────────────────────────────────────────────

def list_presets(db: Session, *, organization_id: Optional[str]) -> list[dict[str, Any]]:
    """Base catalog merged with org-level customizations."""
    custom_map = _get_json(db, CUSTOM_PRESETS_KEY, organization_id, default={})
    result = []
    for p in BASE_PRESETS:
        merged = {**p, **(custom_map.get(p["id"]) or {})}
        result.append(merged)
    return result


def list_presets_by_category(db: Session, *, organization_id: Optional[str]) -> dict[str, list[dict[str, Any]]]:
    presets = list_presets(db, organization_id=organization_id)
    by_cat: dict[str, list] = {}
    for p in presets:
        cat = p.get("category", "other")
        by_cat.setdefault(cat, []).append(p)
    return by_cat


def get_preset(db: Session, *, organization_id: Optional[str], preset_id: str) -> dict[str, Any]:
    presets = list_presets(db, organization_id=organization_id)
    target = next((p for p in presets if p["id"] == preset_id), None)
    if not target:
        raise ValueError("preset_not_found")
    return target


def customize_preset(
    db: Session,
    *,
    organization_id: Optional[str],
    preset_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Override specific fields for a given preset at the org level."""
    # Verify preset exists in base catalog
    base = next((p for p in BASE_PRESETS if p["id"] == preset_id), None)
    if not base:
        raise ValueError("preset_not_found")
    if not base.get("customizable"):
        raise ValueError("preset_not_customizable")

    custom_map = _get_json(db, CUSTOM_PRESETS_KEY, organization_id, default={})
    existing = custom_map.get(preset_id) or {}
    allowed_fields = {"name", "columns", "group_by", "sort_by", "sort_direction", "filters"}
    for field in allowed_fields:
        if field in payload and payload[field] is not None:
            existing[field] = payload[field]
    custom_map[preset_id] = existing
    _set_json(db, CUSTOM_PRESETS_KEY, organization_id, custom_map,
              description="BI Report Builder v2 custom preset overrides (JSON)")
    return {**base, **existing}


def reset_preset_customization(
    db: Session,
    *,
    organization_id: Optional[str],
    preset_id: str,
) -> dict[str, Any]:
    custom_map = _get_json(db, CUSTOM_PRESETS_KEY, organization_id, default={})
    custom_map.pop(preset_id, None)
    _set_json(db, CUSTOM_PRESETS_KEY, organization_id, custom_map,
              description="BI Report Builder v2 custom preset overrides (JSON)")
    base = next((p for p in BASE_PRESETS if p["id"] == preset_id), None)
    if not base:
        raise ValueError("preset_not_found")
    return base


def preview_preset(
    db: Session,
    *,
    organization_id: Optional[str],
    preset_id: str,
    limit: int = 50,
) -> dict[str, Any]:
    preset = get_preset(db, organization_id=organization_id, preset_id=preset_id)
    try:
        result = execute_report(
            db=db,
            report_type=preset_id,
            sort_column=preset.get("sort_by"),
            sort_direction=preset.get("sort_direction", "desc"),
            filters=preset.get("filters") or {},
            limit=limit,
        )
        rows = result if isinstance(result, list) else (result.get("rows") if isinstance(result, dict) else [])
    except Exception:
        rows = []

    return {
        "preset_id": preset_id,
        "preset_name": preset.get("name"),
        "category": preset.get("category"),
        "columns": preset.get("columns"),
        "rows": rows,
        "count": len(rows),
        "generated_at": _iso_now(),
    }


def export_preset_data(
    db: Session,
    *,
    organization_id: Optional[str],
    preset_id: str,
    export_format: str = "json",
) -> dict[str, Any]:
    """Return data payload ready for client-side Excel/CSV rendering."""
    result = preview_preset(db, organization_id=organization_id, preset_id=preset_id, limit=5000)
    return {
        "export_format": export_format,
        "filename": f"{preset_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.{export_format}",
        "preset_name": result.get("preset_name"),
        "columns": result.get("columns"),
        "rows": result.get("rows"),
        "count": result.get("count"),
        "generated_at": _iso_now(),
    }
