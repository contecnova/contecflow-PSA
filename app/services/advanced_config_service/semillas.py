"""Valores por defecto y su siembra: alertas, tipos de tarea, numeracion y roles del sistema.

Parte de `app.services.advanced_config_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import json
from typing import Optional
from sqlalchemy.orm import Session
from app.models.advanced_config import AlertConfig
from app.models.advanced_config import TaskType
from app.models.advanced_config import NumberingSequence
from app.models.advanced_config import CustomRole


DEFAULT_ALERT_CONFIGS = [
    ("overload", "Sobrecarga de recursos", "Recurso supera el % de capacidad configurado", 100, "%", True, True, False, False, "critical"),
    ("burnout_risk", "Riesgo de burnout", "Recurso con alta carga durante N semanas consecutivas", 85, "%", True, True, True, False, "warning"),
    ("budget_exceeded", "Presupuesto superado", "Proyecto supera el % de presupuesto configurado", 90, "%", True, True, False, False, "warning"),
    ("budget_critical", "Presupuesto crítico", "Proyecto supera el 100% del presupuesto", 100, "%", True, True, False, False, "critical"),
    ("budget_forecast_overrun", "Previsión por encima del plan", "La previsión al cierre de un presupuesto aprobado pasa del % de su plan", 100, "%", True, True, False, False, "warning"),
    ("deadline_risk", "Riesgo de plazo", "Proyecto activo que vence en N días o menos", 7, "days", True, True, False, False, "warning"),
    ("no_imputation", "Sin imputaciones", "Recurso sin imputar durante N días laborables", 2, "days", False, False, True, True, "info"),
    ("task_blocked", "Tarea bloqueada", "Tarea bloqueada durante más de N días", 2, "days", False, True, False, False, "warning"),
    ("hours_deviation", "Desviación de horas", "Tarea supera el % de horas estimadas", 50, "%", False, True, False, False, "warning"),
]

DEFAULT_TASK_TYPES = [
    ("development", "Desarrollo", "💻", "#00d4ff", True),
    ("bug", "Bug / Incidencia", "🐛", "#ff4757", False),
    ("review", "Revisión / QA", "👁", "#ffb800", True),
    ("meeting", "Reunión", "🤝", "#7c3aed", False),
    ("documentation", "Documentación", "📄", "#7a8aaa", True),
    ("analysis", "Análisis", "🔍", "#00e5a0", True),
    ("training", "Formación", "📚", "#f97316", False),
    ("support", "Soporte", "🔧", "#06b6d4", True),
]

DEFAULT_NUMBERING = [
    ("project", "PRJ", "", "-", False, 4, False, "PRJ-0001"),
    ("task", "TSK", "", "-", False, 4, False, "TSK-0001"),
    ("contract", "CTR", "", "-", False, 4, False, "CTR-0001"),
    ("opportunity", "OPP", "", "-", False, 4, False, "OPP-0001"),
    ("change_request", "CR", "", "-", False, 3, False, "CR-001"),
    ("deliverable", "DEL", "", "-", False, 3, False, "DEL-001"),
    ("risk", "RSK", "", "-", False, 3, False, "RSK-001"),
]

DEFAULT_MODULES = [
    "dashboard", "projects", "tasks", "imputations", "timesheets", "resources",
    "capacity", "profitability", "pipeline", "contracts", "risks", "changes",
    "deliverables", "skills", "absences", "reports", "alerts", "exports", "settings",
]

# Los mismos modulos que aplica `app/core/modulos.py`.
DEFAULT_SYSTEM_ROLES = [
    ("admin",          "Dirección / Admin",         "#ff4757", True),
    ("pm",             "Project Manager",            "#00d4ff", True),
    ("hr",             "RRHH",                       "#00e5a0", True),
    ("team_lead",      "Team Lead",                  "#7c3aed", True),
    ("employee",       "Empleado",                   "#7a8aaa", True),
    ("subcontractor",  "Subcontratado",              "#f59e0b", True),
]


# ── Seeders ───────────────────────────────────────────────────────────────────

def seed_alert_configs(db: Session):
    if db.query(AlertConfig).count() > 0:
        return
    for at, label, desc, threshold, unit, notify_admin, notify_pm, notify_hr, notify_emp, severity in DEFAULT_ALERT_CONFIGS:
        db.add(AlertConfig(
            alert_type=at, label=label, description=desc,
            threshold_value=threshold, threshold_unit=unit,
            notify_admin=notify_admin, notify_pm=notify_pm,
            notify_hr=notify_hr, notify_employee=notify_emp,
            severity=severity,
        ))
    db.commit()


def seed_task_types(db: Session):
    if db.query(TaskType).count() > 0:
        return
    for i, (value, name, icon, color, billable) in enumerate(DEFAULT_TASK_TYPES):
        db.add(TaskType(
            value=value, name=name, icon=icon, color=color,
            is_billable_default=billable, sort_order=i,
        ))
    db.commit()


def seed_numbering(db: Session):
    if db.query(NumberingSequence).count() > 0:
        return
    for entity, prefix, suffix, sep, year, padding, reset, example in DEFAULT_NUMBERING:
        db.add(NumberingSequence(
            entity=entity, prefix=prefix, suffix=suffix, separator=sep,
            include_year=year, padding=padding, reset_yearly=reset, example=example,
        ))
    db.commit()


def seed_system_roles(db: Session, org_id: Optional[str] = None):
    """Una fila por rol base y organizacion (la de la sesion si no se da).

    Auditoria 2026-11: sembraba una sola vez en toda la instalacion, la fila
    quedaba sellada con la organizacion de quien abria la pantalla y la
    siguiente organizacion chocaba con el unico global del nombre.
    """
    org_id = org_id or db.info.get("organization_id")
    if not org_id:
        return
    from app.db.session import sin_filtro_de_tenant
    with sin_filtro_de_tenant(db):
        existentes = {n for (n,) in db.query(CustomRole.name).filter(CustomRole.organization_id == org_id)}
    all_modules = {m: True for m in DEFAULT_MODULES}
    nuevos = False
    for name, description, color, is_system in DEFAULT_SYSTEM_ROLES:
        if name not in existentes:
            db.add(CustomRole(
                name=name, description=description, color=color, organization_id=org_id,
                is_system=is_system, is_active=True,
                module_access=json.dumps(all_modules),
            ))
            nuevos = True
    if nuevos:
        db.commit()
