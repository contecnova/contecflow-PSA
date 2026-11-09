"""Escenarios de simulacion y su calculo.

Auditoria 2026-08 (hallazgo 22). Este codigo vivia en `mfa_service.py`, un
fichero de 1.435 lineas que contenia OCHO dominios sin relacion entre si —MFA,
organizaciones, Slack, presupuestos, planificacion asistida, escenarios, PDF y
tokens de BI— servidos ademas por un unico router llamado `mfa.py` con 38 rutas.

El reparto se pudo hacer mecanicamente porque los ocho dominios nunca estuvieron
acoplados, solo apilados: se comprobo por AST que no habia ni una llamada entre
grupos ni un solo ciclo. Los cuerpos se movieron verbatim.
"""

from app.core import timeutil
import json
from datetime import date, datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.core.config import settings
from app.services.settings_service import get_runtime_float, get_runtime_str
from app.models.user import User
from app.models.mfa import (
    ScenarioModel, ScenarioProject,
)
from sqlalchemy.orm import joinedload as jl


def compute_scenario(scenario_id: str, db: Session) -> dict:
    """Simulate capacity impact of scenario projects against current team capacity."""

    scenario = db.query(ScenarioModel).options(
        jl(ScenarioModel.projects)
    ).filter(ScenarioModel.id == scenario_id).first()
    if not scenario:
        raise ValueError("scenario_not_found")

    base_date = scenario.base_date or timeutil.today()
    horizon_end = base_date + timedelta(weeks=scenario.horizon_weeks)

    # Capacidad: solo los roles que trabajan en proyectos (ajuste
    # SCENARIO_CAPACITY_ROLES) y con las horas de cada persona. Antes contaba a
    # todos los activos —admin y RR. HH. incluidos— a la capacidad por defecto.
    org = scenario.organization_id
    roles = [r.strip() for r in (get_runtime_str(db, "SCENARIO_CAPACITY_ROLES", org) or "").split(",") if r.strip()]
    por_defecto = get_runtime_float(db, "DEFAULT_WEEKLY_CAPACITY_HOURS", org) or settings.DEFAULT_WEEKLY_CAPACITY_HOURS
    equipo = db.query(User).filter(User.is_active == True, User.role.in_(roles)).all() if roles else []
    active_users = len(equipo)
    weekly_capacity = round(sum((u.weekly_capacity_hours or por_defecto) for u in equipo), 1)

    total_demand_hours = 0
    weekly_demand = {}
    overloaded_weeks = []
    project_breakdown = []

    for sp in scenario.projects:
        if not sp.start_date or not sp.end_date:
            continue
        duration_weeks = max((sp.end_date - sp.start_date).days / 7, 1)
        hours_per_week = sp.total_hours / duration_weeks

        current = sp.start_date
        while current < sp.end_date and current < horizon_end:
            week_key = _semana_iso(current)
            weekly_demand[week_key] = weekly_demand.get(week_key, 0) + hours_per_week
            current += timedelta(weeks=1)
        # Revisión 2026-11: estas líneas estaban sangradas dentro del bucle de
        # reservas: sin reservas el reparto salía vacío y la demanda total a 0;
        # con reservas, repetía el último proyecto una vez por semana reservada.
        total_demand_hours += sp.total_hours
        project_breakdown.append({
            "name": sp.name,
            "total_hours": sp.total_hours,
            "hours_per_week": round(hours_per_week, 1),
            "start": str(sp.start_date),
            "end": str(sp.end_date),
            "is_existing": sp.is_existing,
        })

    # Lo que el equipo ya tiene reservado (reservas firmes) tambien ocupa
    # capacidad. Las de un proyecto que el escenario ya incluye no se suman dos veces.
    en_escenario = {sp.project_id for sp in scenario.projects if sp.project_id}
    comprometido = _horas_reservadas_por_semana(db, base_date, horizon_end, en_escenario)
    for week_key, horas in comprometido.items():
        weekly_demand[week_key] = weekly_demand.get(week_key, 0) + horas


    capacity_timeline = []
    for week_key, demand in sorted(weekly_demand.items()):
        utilization_pct = round(demand / max(weekly_capacity, 1) * 100, 1)
        is_overloaded = utilization_pct > 100
        if is_overloaded:
            overloaded_weeks.append(week_key)
        capacity_timeline.append({
            "week": week_key,
            "demand": round(demand, 1),
            "capacity": weekly_capacity,
            "utilization_pct": utilization_pct,
            "is_overloaded": is_overloaded,
        })

    avg_utilization = sum(c["utilization_pct"] for c in capacity_timeline) / max(len(capacity_timeline), 1)
    feasible = len(overloaded_weeks) == 0
    risk_level = "low" if feasible else ("medium" if len(overloaded_weeks) <= 3 else "high")

    results = {
        "feasible": feasible,
        "risk_level": risk_level,
        "avg_utilization_pct": round(avg_utilization, 1),
        "peak_utilization_pct": max((c["utilization_pct"] for c in capacity_timeline), default=0),
        "overloaded_weeks_count": len(overloaded_weeks),
        "overloaded_weeks": overloaded_weeks[:10],
        "total_demand_hours": round(total_demand_hours, 1),
        "team_size": active_users,
        "weekly_capacity": weekly_capacity,
        "committed_hours": round(sum(comprometido.values()), 1),
        "horizon_weeks": scenario.horizon_weeks,
        "project_breakdown": project_breakdown,
        "capacity_timeline": capacity_timeline[:24],
        "recommendation": (
            "El equipo tiene capacidad suficiente para asumir todos los proyectos del escenario." if feasible
            else f"Se detectan {len(overloaded_weeks)} semanas con sobrecarga. Considera retrasar proyectos o ampliar equipo."
        ),
    }

    scenario.results = json.dumps(results)
    scenario.status = "computed"
    scenario.computed_at = datetime.now(timezone.utc)
    db.commit()
    return results


def _semana_iso(dia: date) -> str:
    """Semana ISO 8601 (la del calendario laboral); `%W` iba una semana desfasada."""
    anyo, semana, _ = dia.isocalendar()
    return f"{anyo}-W{semana:02d}"


def _horas_reservadas_por_semana(db: Session, desde: date, hasta: date, excluir: set) -> dict:
    """Horas de reservas firmes y activas por semana ISO, en dias laborables."""
    from app.models.bookings import BookingType, ResourceBooking
    reservas = db.query(ResourceBooking).filter(
        ResourceBooking.is_active == True,
        ResourceBooking.booking_type == BookingType.hard,
        ResourceBooking.start_date < hasta,
        ResourceBooking.end_date >= desde,
    ).all()
    por_dia = settings.DEFAULT_WORKING_HOURS_PER_DAY
    semanas: dict = {}
    for r in reservas:
        if r.project_id and r.project_id in excluir:
            continue
        dia = max(r.start_date, desde)
        while dia <= r.end_date and dia < hasta:
            if dia.weekday() < 5:
                clave = _semana_iso(dia)
                semanas[clave] = semanas.get(clave, 0) + (r.hours_per_day or por_dia)
            dia += timedelta(days=1)
    return semanas


def list_scenarios(db: Session) -> list:
    scenarios = db.query(ScenarioModel).options(
        jl(ScenarioModel.projects),
        jl(ScenarioModel.creator),
    ).order_by(ScenarioModel.created_at.desc()).all()
    return [{
        "id": s.id, "name": s.name, "description": s.description,
        "status": s.status, "horizon_weeks": s.horizon_weeks,
        "project_count": len(s.projects),
        "creator": s.creator.full_name if s.creator else None,
        "created_at": str(s.created_at)[:10] if s.created_at else None,
        "computed_at": str(s.computed_at)[:16] if s.computed_at else None,
        "has_results": bool(s.results),
    } for s in scenarios]


def create_scenario(payload_dict: dict, created_by: str, db: Session) -> dict:
    base_date_val = payload_dict.get("base_date")
    if isinstance(base_date_val, str):
        base_date_val = date.fromisoformat(base_date_val)
    s = ScenarioModel(
        name=payload_dict["name"],
        description=payload_dict.get("description"),
        base_date=base_date_val or timeutil.today(),
        horizon_weeks=payload_dict.get("horizon_weeks", 12),
        created_by=created_by,
    )
    db.add(s); db.flush()
    for p in (payload_dict.get("projects") or []):
        db.add(ScenarioProject(
            scenario_id=s.id,
            name=p.get("name", "Proyecto hipotético"),
            project_id=p.get("project_id"),
            start_date=date.fromisoformat(p["start_date"]) if p.get("start_date") else None,
            end_date=date.fromisoformat(p["end_date"]) if p.get("end_date") else None,
            total_hours=p.get("total_hours", 0),
            skill_demand=json.dumps(p.get("skill_demand", {})),
            is_existing=bool(p.get("project_id")),
        ))
    db.commit()
    return {"ok": True, "id": s.id}


def get_scenario(scenario_id: str, db: Session) -> dict:
    s = db.query(ScenarioModel).options(jl(ScenarioModel.projects)).filter(
        ScenarioModel.id == scenario_id
    ).first()
    if not s:
        raise ValueError("not_found")
    return {
        "id": s.id, "name": s.name, "description": s.description,
        "status": s.status, "horizon_weeks": s.horizon_weeks,
        "base_date": str(s.base_date) if s.base_date else None,
        "computed_at": str(s.computed_at)[:16] if s.computed_at else None,
        "results": json.loads(s.results) if s.results else None,
        "projects": [{
            "id": p.id, "name": p.name,
            "start_date": str(p.start_date) if p.start_date else None,
            "end_date": str(p.end_date) if p.end_date else None,
            "total_hours": p.total_hours,
            "is_existing": p.is_existing,
        } for p in s.projects],
    }


def delete_scenario(scenario_id: str, db: Session) -> dict:
    s = db.query(ScenarioModel).filter(ScenarioModel.id == scenario_id).first()
    if not s:
        raise ValueError("not_found")
    db.delete(s); db.commit()
    return {"ok": True}
