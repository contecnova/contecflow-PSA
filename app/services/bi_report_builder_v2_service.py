"""BI Report Builder v2 service.

Advances the Phase-2 Report Builder with:
- 15+ configurable presets with column/group/filter options
- Per-org preset customization (override columns, groupBy, sortBy, name)
- Export endpoint that returns richly-formatted data ready for xlsx/pdf
- Template-based preset with variable slot support
- Preset categories for navigation
"""
from __future__ import annotations
import logging

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.settings import AppSetting
from app.services.report_builder_service import execute_report

CUSTOM_PRESETS_KEY = "bi.report_builder_v2.custom_presets"
EXECUTIONS_KEY = "bi.report_builder_v2.executions"

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
        logging.getLogger(__name__).debug("_get_json: excepcion ignorada", exc_info=True)
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
    executed = execute_preset_with_controls(
        db,
        organization_id=organization_id,
        preset_id=preset_id,
        limit=limit,
        timeout_seconds=6,
    )
    return executed["result"]


def _get_executions(db: Session, organization_id: Optional[str]) -> dict[str, Any]:
    data = _get_json(db, EXECUTIONS_KEY, organization_id, default={})
    return data if isinstance(data, dict) else {}


def _save_executions(db: Session, organization_id: Optional[str], executions: dict[str, Any]) -> None:
    # Keep only newest 200 executions per org.
    values = sorted(executions.values(), key=lambda x: x.get("updated_at", ""), reverse=True)[:200]
    compact = {row["id"]: row for row in values if row.get("id")}
    _set_json(
        db,
        EXECUTIONS_KEY,
        organization_id,
        compact,
        description="BI controlled execution status and progress",
    )


def get_execution_status(db: Session, *, organization_id: Optional[str], execution_id: str) -> dict[str, Any]:
    executions = _get_executions(db, organization_id)
    row = executions.get(execution_id)
    if not row:
        raise ValueError("execution_not_found")
    return row


def execute_preset_with_controls(
    db: Session,
    *,
    organization_id: Optional[str],
    preset_id: str,
    limit: int,
    timeout_seconds: int = 8,
) -> dict[str, Any]:
    """Run a BI preset with progress checkpoints and graceful degradation.

    Uses staged limits to avoid expensive single-pass requests and to preserve
    partial data if execution crosses timeout budget.
    """
    preset = get_preset(db, organization_id=organization_id, preset_id=preset_id)
    execution_id = str(uuid.uuid4())
    started_at = _iso_now()

    executions = _get_executions(db, organization_id)
    executions[execution_id] = {
        "id": execution_id,
        "preset_id": preset_id,
        "status": "running",
        "progress": 0,
        "degraded": False,
        "started_at": started_at,
        "updated_at": started_at,
    }
    _save_executions(db, organization_id, executions)

    start_ts = time.monotonic()
    staged_limits = []
    for candidate in (min(limit, 500), min(limit, 1500), limit):
        if candidate > 0 and candidate not in staged_limits:
            staged_limits.append(candidate)

    rows: list[dict[str, Any]] = []
    error = None
    completed_stage = 0

    for idx, staged_limit in enumerate(staged_limits, start=1):
        elapsed = time.monotonic() - start_ts
        if elapsed > timeout_seconds:
            break
        try:
            result = execute_report(
                db=db,
                report_type=preset_id,
                sort_column=preset.get("sort_by"),
                sort_direction=preset.get("sort_direction", "desc"),
                filters=preset.get("filters") or {},
                limit=staged_limit,
            )
            rows = result if isinstance(result, list) else (result.get("rows") if isinstance(result, dict) else [])
            completed_stage = idx
            executions = _get_executions(db, organization_id)
            row = executions.get(execution_id, {})
            row.update(
                {
                    "status": "running",
                    "progress": int((idx / len(staged_limits)) * 100),
                    "rows_preview": len(rows),
                    "updated_at": _iso_now(),
                }
            )
            executions[execution_id] = row
            _save_executions(db, organization_id, executions)
        except Exception as exc:
            logging.getLogger(__name__).warning("execute_preset_with_controls: excepcion ignorada", exc_info=True)
            error = str(exc)
            break

    elapsed_ms = int((time.monotonic() - start_ts) * 1000)
    degraded = bool(error) or (completed_stage < len(staged_limits))
    out = {
        "preset_id": preset_id,
        "preset_name": preset.get("name"),
        "category": preset.get("category"),
        "columns": preset.get("columns"),
        "rows": rows,
        "count": len(rows),
        "generated_at": _iso_now(),
        "degraded": degraded,
        "execution_ms": elapsed_ms,
        "timeout_seconds": timeout_seconds,
        "completed_stages": completed_stage,
        "total_stages": len(staged_limits),
    }

    executions = _get_executions(db, organization_id)
    current = executions.get(execution_id, {})
    current.update(
        {
            "status": "failed" if error and not rows else "completed",
            "progress": 100 if not error else current.get("progress", 0),
            "degraded": degraded,
            "rows": len(rows),
            "error": error,
            "updated_at": _iso_now(),
            "finished_at": _iso_now(),
            "execution_ms": elapsed_ms,
        }
    )
    executions[execution_id] = current
    _save_executions(db, organization_id, executions)

    return {
        "execution_id": execution_id,
        "result": out,
        "status": current,
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


# ── BI Phase 2: Dashboard Templates ───────────────────────────────────────────

TEMPLATES_KEY = "bi.report_builder_v2.templates"
DASHBOARD_LAYOUTS_KEY = "bi.report_builder_v2.layouts"

# ── Component library (static registry) ───────────────────────────────────────

COMPONENT_TYPES: list[dict[str, Any]] = [
    {
        "type": "chart_bar",
        "label": "Gráfico de barras",
        "category": "visualization",
        "default_config": {"orientation": "vertical", "stacked": False, "show_legend": True},
        "accepts_columns": True,
        "min_w": 4, "min_h": 3,
    },
    {
        "type": "chart_line",
        "label": "Gráfico de líneas",
        "category": "visualization",
        "default_config": {"smooth": True, "show_area": False, "show_legend": True},
        "accepts_columns": True,
        "min_w": 4, "min_h": 3,
    },
    {
        "type": "chart_pie",
        "label": "Gráfico de tarta / donut",
        "category": "visualization",
        "default_config": {"donut": False, "show_labels": True},
        "accepts_columns": True,
        "min_w": 3, "min_h": 3,
    },
    {
        "type": "chart_scatter",
        "label": "Gráfico de dispersión",
        "category": "visualization",
        "default_config": {"x_col": None, "y_col": None, "size_col": None},
        "accepts_columns": True,
        "min_w": 4, "min_h": 3,
    },
    {
        "type": "chart_heatmap",
        "label": "Mapa de calor",
        "category": "visualization",
        "default_config": {"color_scale": "viridis"},
        "accepts_columns": True,
        "min_w": 5, "min_h": 4,
    },
    {
        "type": "kpi_card",
        "label": "Tarjeta KPI",
        "category": "metric",
        "default_config": {"metric_col": None, "comparison_col": None, "format": "number", "prefix": "", "suffix": ""},
        "accepts_columns": True,
        "min_w": 2, "min_h": 2,
    },
    {
        "type": "table",
        "label": "Tabla de datos",
        "category": "data",
        "default_config": {"paginate": True, "page_size": 25, "sortable": True, "searchable": True},
        "accepts_columns": True,
        "min_w": 6, "min_h": 4,
    },
    {
        "type": "text",
        "label": "Bloque de texto / Markdown",
        "category": "content",
        "default_config": {"content": "", "format": "markdown"},
        "accepts_columns": False,
        "min_w": 2, "min_h": 1,
    },
    {
        "type": "image",
        "label": "Imagen / Logo",
        "category": "content",
        "default_config": {"src": "", "alt": "", "fit": "contain"},
        "accepts_columns": False,
        "min_w": 2, "min_h": 2,
    },
    {
        "type": "divider",
        "label": "Separador",
        "category": "layout",
        "default_config": {"orientation": "horizontal"},
        "accepts_columns": False,
        "min_w": 12, "min_h": 1,
    },
]


def list_component_types() -> list[dict[str, Any]]:
    """Return the static component type registry."""
    return COMPONENT_TYPES


# ── Template CRUD ──────────────────────────────────────────────────────────────

def list_templates(db: Session, *, organization_id: Optional[str]) -> list[dict[str, Any]]:
    templates_map = _get_json(db, TEMPLATES_KEY, organization_id, default={})
    return sorted(templates_map.values(), key=lambda t: t.get("created_at", ""), reverse=True)


def get_template(db: Session, *, organization_id: Optional[str], template_id: str) -> dict[str, Any]:
    templates_map = _get_json(db, TEMPLATES_KEY, organization_id, default={})
    tpl = templates_map.get(template_id)
    if not tpl:
        raise ValueError("template_not_found")
    return tpl


def create_template(
    db: Session,
    *,
    organization_id: Optional[str],
    name: str,
    description: str = "",
    layout: list[dict[str, Any]] | None = None,
    preset_id: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    import uuid
    templates_map = _get_json(db, TEMPLATES_KEY, organization_id, default={})
    template_id = str(uuid.uuid4())
    template = {
        "id": template_id,
        "name": name,
        "description": description,
        "layout": layout or [],
        "preset_id": preset_id,
        "tags": tags or [],
        "created_at": _iso_now(),
        "updated_at": _iso_now(),
    }
    templates_map[template_id] = template
    _set_json(db, TEMPLATES_KEY, organization_id, templates_map,
              description="BI Report Builder v2 dashboard templates (JSON)")
    return template


def update_template(
    db: Session,
    *,
    organization_id: Optional[str],
    template_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    templates_map = _get_json(db, TEMPLATES_KEY, organization_id, default={})
    tpl = templates_map.get(template_id)
    if not tpl:
        raise ValueError("template_not_found")
    allowed = {"name", "description", "layout", "preset_id", "tags"}
    for field in allowed:
        if field in payload:
            tpl[field] = payload[field]
    tpl["updated_at"] = _iso_now()
    templates_map[template_id] = tpl
    _set_json(db, TEMPLATES_KEY, organization_id, templates_map,
              description="BI Report Builder v2 dashboard templates (JSON)")
    return tpl


def delete_template(db: Session, *, organization_id: Optional[str], template_id: str) -> bool:
    templates_map = _get_json(db, TEMPLATES_KEY, organization_id, default={})
    if template_id not in templates_map:
        raise ValueError("template_not_found")
    del templates_map[template_id]
    _set_json(db, TEMPLATES_KEY, organization_id, templates_map,
              description="BI Report Builder v2 dashboard templates (JSON)")
    return True


# ── Dashboard layout persistence (drag-and-drop grid) ─────────────────────────

def get_dashboard_layout(
    db: Session,
    *,
    organization_id: Optional[str],
    dashboard_key: str,
) -> dict[str, Any]:
    layouts = _get_json(db, DASHBOARD_LAYOUTS_KEY, organization_id, default={})
    return layouts.get(dashboard_key, {"dashboard_key": dashboard_key, "components": [], "grid_cols": 12})


def save_dashboard_layout(
    db: Session,
    *,
    organization_id: Optional[str],
    dashboard_key: str,
    components: list[dict[str, Any]],
    grid_cols: int = 12,
) -> dict[str, Any]:
    """Persist drag-and-drop grid layout for a named dashboard.

    Each component item is: ``{id, type, preset_id?, x, y, w, h, config}``.
    """
    layouts = _get_json(db, DASHBOARD_LAYOUTS_KEY, organization_id, default={})
    layout = {
        "dashboard_key": dashboard_key,
        "components": components,
        "grid_cols": grid_cols,
        "saved_at": _iso_now(),
    }
    layouts[dashboard_key] = layout
    _set_json(db, DASHBOARD_LAYOUTS_KEY, organization_id, layouts,
              description="BI Report Builder v2 dashboard drag-and-drop layouts (JSON)")
    return layout


def list_dashboard_layouts(db: Session, *, organization_id: Optional[str]) -> list[dict[str, Any]]:
    layouts = _get_json(db, DASHBOARD_LAYOUTS_KEY, organization_id, default={})
    return list(layouts.values())
