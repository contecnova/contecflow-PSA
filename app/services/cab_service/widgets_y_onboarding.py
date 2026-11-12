"""Widgets del panel del usuario y pasos de bienvenida.

Parte de `app.services.cab_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.cab import DashboardWidget
from app.models.cab import OnboardingState


# ─── Dashboard widget helpers ─────────────────────────────────────────────────

AVAILABLE_WIDGETS = [
    {"type": "kpi_hours_week",    "label": "Horas esta semana",          "category": "time",      "default_w": 1, "default_h": 1},
    {"type": "kpi_projects_active","label": "Proyectos activos",          "category": "projects",  "default_w": 1, "default_h": 1},
    {"type": "kpi_tickets_open",  "label": "Tickets abiertos",           "category": "itsm",      "default_w": 1, "default_h": 1},
    {"type": "kpi_budget_health", "label": "Salud presupuesto",          "category": "finance",   "default_w": 1, "default_h": 1},
    {"type": "chart_hours_trend", "label": "Tendencia horas (14d)",      "category": "time",      "default_w": 2, "default_h": 2},
    {"type": "chart_pipeline",    "label": "Pipeline por fase",          "category": "sales",     "default_w": 2, "default_h": 2},
    {"type": "chart_sla",         "label": "SLA compliance (30d)",       "category": "itsm",      "default_w": 2, "default_h": 1},
    {"type": "list_my_tasks",     "label": "Mis tareas pendientes",      "category": "tasks",     "default_w": 2, "default_h": 2},
    {"type": "list_alerts",       "label": "Alertas recientes",          "category": "alerts",    "default_w": 2, "default_h": 1},
    {"type": "list_my_timesheets","label": "Mis imputaciones recientes", "category": "time",      "default_w": 2, "default_h": 1},
    {"type": "calendar_week",     "label": "Calendario semanal",         "category": "calendar",  "default_w": 4, "default_h": 2},
    {"type": "chart_budget_gauge","label": "Gauge presupuesto",          "category": "finance",   "default_w": 1, "default_h": 1},
]


def default_widget_layout(role: str) -> list:
    if role in ["admin", "pm"]:
        return [
            {"widget_type": "kpi_projects_active", "position_x": 0, "position_y": 0, "width": 1, "height": 1},
            {"widget_type": "kpi_hours_week",       "position_x": 1, "position_y": 0, "width": 1, "height": 1},
            {"widget_type": "kpi_tickets_open",     "position_x": 2, "position_y": 0, "width": 1, "height": 1},
            {"widget_type": "kpi_budget_health",    "position_x": 3, "position_y": 0, "width": 1, "height": 1},
            {"widget_type": "list_my_tasks",        "position_x": 0, "position_y": 1, "width": 2, "height": 2},
            {"widget_type": "chart_hours_trend",    "position_x": 2, "position_y": 1, "width": 2, "height": 2},
        ]
    else:
        return [
            {"widget_type": "kpi_hours_week",       "position_x": 0, "position_y": 0, "width": 1, "height": 1},
            {"widget_type": "list_my_tasks",        "position_x": 0, "position_y": 1, "width": 2, "height": 2},
        ]


# ─── Dashboard Widgets ────────────────────────────────────────────────────────

def get_user_widgets(current_user, db: Session) -> list:
    widgets = db.query(DashboardWidget).filter(
        DashboardWidget.user_id == current_user.id,
        DashboardWidget.is_visible == True,
    ).order_by(DashboardWidget.position_y, DashboardWidget.position_x).all()

    if not widgets:
        return default_widget_layout(current_user.role)

    return [{
        "id": w.id, "widget_type": w.widget_type,
        "title": w.title,
        "position_x": w.position_x, "position_y": w.position_y,
        "width": w.width, "height": w.height,
        "config": json.loads(w.config) if w.config else {},
    } for w in widgets]


def save_widget_layout(payload: list, current_user_id: str, db: Session) -> dict:
    db.query(DashboardWidget).filter(DashboardWidget.user_id == current_user_id).delete()
    db.flush()
    for item in payload:
        widget_type = item.get("widget_type")
        if not widget_type:
            continue
        w = DashboardWidget(
            user_id=current_user_id,
            widget_type=widget_type,
            title=item.get("title"),
            position_x=item.get("position_x", 0),
            position_y=item.get("position_y", 0),
            width=item.get("width", 1),
            height=item.get("height", 1),
            config=json.dumps(item.get("config", {})),
        )
        db.add(w)
    db.commit()
    return {"ok": True, "count": len(payload)}


def reset_widgets(current_user_id: str, db: Session) -> dict:
    db.query(DashboardWidget).filter(DashboardWidget.user_id == current_user_id).delete()
    db.commit()
    return {"ok": True}


# ─── Onboarding ───────────────────────────────────────────────────────────────

ONBOARDING_STEPS = [
    {"id": "create_project",  "title": "Crea tu primer proyecto",      "description": "Configura el nombre, cliente y fechas de tu primer proyecto.",      "action": "/projects", "icon": "⬡"},
    {"id": "invite_team",     "title": "Invita a tu equipo",           "description": "Añade los miembros del equipo que van a trabajar en el proyecto.",   "action": "/settings", "icon": "👥"},
    {"id": "configure_sla",   "title": "Configura el SLA",             "description": "Define el horario laboral y los festivos para el cálculo de SLAs.",  "action": "/settings", "icon": "🎯"},
    {"id": "create_sprint",   "title": "Lanza tu primer sprint",       "description": "Crea un sprint con tareas y fija las fechas de inicio y fin.",       "action": "/sprints",  "icon": "⚡"},
    {"id": "first_timesheet", "title": "Imputa tus primeras horas",    "description": "Registra las horas trabajadas hoy en el proyecto que acabas de crear.", "action": "/imputar", "icon": "⏱"},
]


def get_onboarding(current_user, db: Session) -> dict:
    state = db.query(OnboardingState).filter(
        OnboardingState.user_id == current_user.id
    ).first()
    if not state:
        state = OnboardingState(user_id=current_user.id, completed_steps="[]")
        db.add(state); db.commit(); db.refresh(state)

    completed = json.loads(state.completed_steps or "[]")
    return {
        "is_complete": state.is_complete,
        "is_dismissed": state.dismissed_at is not None,
        "current_step": state.current_step,
        "completed_steps": completed,
        "progress_pct": round(len(completed) / len(ONBOARDING_STEPS) * 100),
        "steps": [{**step, "completed": step["id"] in completed} for step in ONBOARDING_STEPS],
    }


def complete_onboarding_step(step_id: str, current_user, db: Session) -> dict:
    if step_id not in [s["id"] for s in ONBOARDING_STEPS]:
        raise ValueError(f"Step '{step_id}' no existe")
    state = db.query(OnboardingState).filter(
        OnboardingState.user_id == current_user.id
    ).first()
    if not state:
        state = OnboardingState(user_id=current_user.id, completed_steps="[]")
        db.add(state); db.flush()

    completed = json.loads(state.completed_steps or "[]")
    if step_id not in completed:
        completed.append(step_id)
    state.completed_steps = json.dumps(completed)
    state.current_step = len(completed)
    if len(completed) >= len(ONBOARDING_STEPS):
        state.is_complete = True
        state.completed_at = datetime.now(timezone.utc)
    db.commit()
    return {
        "ok": True, "completed_steps": completed,
        "is_complete": state.is_complete,
        "progress_pct": round(len(completed) / len(ONBOARDING_STEPS) * 100),
    }


def dismiss_onboarding(current_user, db: Session) -> dict:
    state = db.query(OnboardingState).filter(
        OnboardingState.user_id == current_user.id
    ).first()
    if not state:
        state = OnboardingState(user_id=current_user.id, completed_steps="[]")
        db.add(state); db.flush()
    state.dismissed_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}
