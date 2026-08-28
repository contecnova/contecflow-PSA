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

    active_users = db.query(User).filter(User.is_active == True).count()
    hours_per_week_per_person = settings.DEFAULT_WEEKLY_CAPACITY_HOURS
    weekly_capacity = active_users * hours_per_week_per_person

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
            week_key = current.strftime("%Y-W%W")
            weekly_demand[week_key] = weekly_demand.get(week_key, 0) + hours_per_week
            current += timedelta(weeks=1)

        total_demand_hours += sp.total_hours
        project_breakdown.append({
            "name": sp.name,
            "total_hours": sp.total_hours,
            "hours_per_week": round(hours_per_week, 1),
            "start": str(sp.start_date),
            "end": str(sp.end_date),
            "is_existing": sp.is_existing,
        })

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
