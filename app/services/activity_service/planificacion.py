"""Planificacion: camino critico, demanda de recursos y simulacion de proyecto.

Parte de `app.services.activity_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from datetime import date, timedelta
from sqlalchemy.orm import Session
from app.core.config import settings
from app.services.settings_service.por_empresa import capacidad_semanal_de_empresa
from app.models.activity import ResourceDemandForecast
from app.models.pipeline import Opportunity, OpportunityStage
from app.models.project import Project
from app.models.task import Task, TaskStatus
from app.core import timeutil
from app.core.errores import ErrorDeDominio


# ═══════════════════════════════════════════════════════════════════════════════
# CRITICAL PATH (CPM)
# ═══════════════════════════════════════════════════════════════════════════════
#
# Proyectos — planificador (16-11-2026). Aquí había un segundo CPM que trataba
# todo vínculo como fin-inicio, contaba días naturales y dividía horas entre 8.
# Se retiró: el camino crítico es uno, `app/services/planificador`, con los
# cuatro tipos de vínculo, desfases, calendarios laborales y restricciones.

def critical_path_payload(db: Session, project_id: str, user=None) -> dict:
    """El plan del proyecto (planificador/servicio.py). Se mantiene el nombre
    porque es la ruta histórica `/activity/projects/{id}/critical-path`."""
    from app.services.planificador.servicio import calcular_plan
    return calcular_plan(db, user, project_id)


# ═══════════════════════════════════════════════════════════════════════════════
# RESOURCE DEMAND
# ═══════════════════════════════════════════════════════════════════════════════

def resource_demand_payload(db: Session, horizon_months: int, min_probability: float, p=None) -> dict:
    """Demanda de recursos del pipeline dentro del horizonte.

    Periodo libre (16-11-2026): el horizonte se calculaba y se descartaba (la
    fecha no se asignaba a nada), así que entraban todas las oportunidades
    abiertas fuera cual fuera su inicio. Ahora cuenta: entran las que empiezan
    antes del fin del horizonte (``p.fecha_hasta`` o el día 1 del mes siguiente
    a ``horizon_months``) y las que aún no tienen fecha de inicio.
    """
    if p is not None:
        fin = p.fecha_hasta
        horizonte = {"desde": str(p.fecha_desde), "hasta": str(fin)}
    else:
        today = timeutil.today()
        limite = date(
            today.year + (today.month + horizon_months - 1) // 12,
            (today.month + horizon_months - 1) % 12 + 1,
            1,
        )
        fin = limite - timedelta(days=1)
        horizonte = {"desde": str(today), "hasta": str(fin)}

    active_opps = db.query(Opportunity).filter(
        Opportunity.stage.not_in([OpportunityStage.won, OpportunityStage.lost, OpportunityStage.cancelled]),
        Opportunity.probability >= min_probability,
        (Opportunity.expected_start_date.is_(None)) | (Opportunity.expected_start_date <= fin),
    ).all()

    opp_ids = [o.id for o in active_opps]
    lines = db.query(ResourceDemandForecast).filter(
        ResourceDemandForecast.opportunity_id.in_(opp_ids)
    ).all() if opp_ids else []

    prob_map = {o.id: o.probability / 100 for o in active_opps}

    by_role: dict = {}
    for line in lines:
        prob = prob_map.get(line.opportunity_id, 1.0)
        weighted = round(line.hours_required * prob, 1)
        role = line.role_or_skill
        if role not in by_role:
            by_role[role] = {"total_hours": 0, "weighted_hours": 0, "opportunities": 0}
        by_role[role]["total_hours"] += line.hours_required
        by_role[role]["weighted_hours"] += weighted
        by_role[role]["opportunities"] += 1

    opp_detail = [{
        "id": o.id, "name": o.name, "probability": o.probability,
        "expected_start": str(o.expected_start_date) if o.expected_start_date else None,
        "expected_hours": o.expected_hours,
        "expected_revenue": o.expected_revenue,
        "demand_lines": [{
            "role": l.role_or_skill, "hours": l.hours_required,
            "weighted_hours": round(l.hours_required * prob_map.get(o.id, 1.0), 1),
        } for l in lines if l.opportunity_id == o.id],
    } for o in active_opps if any(l.opportunity_id == o.id for l in lines)]

    return {
        "horizon_months": horizon_months if p is None else None,
        "periodo": p.a_dict() if p is not None else None,
        "horizonte": horizonte,
        "min_probability": min_probability,
        "opportunities_in_scope": len(active_opps),
        "demand_by_role": [
            {"role": role, **data}
            for role, data in sorted(by_role.items(), key=lambda x: -x[1]["weighted_hours"])
        ],
        "opportunity_breakdown": opp_detail,
    }


def create_demand_line_record(db: Session, payload) -> dict:
    opp = db.query(Opportunity).filter(Opportunity.id == payload.opportunity_id).first()
    if not opp:
        raise ErrorDeDominio(404, "Opportunity not found")
    d = payload.model_dump()
    if d.get("start_date"):
        d["start_date"] = date.fromisoformat(d["start_date"])
    if d.get("end_date"):
        d["end_date"] = date.fromisoformat(d["end_date"])
    d["weighted_hours"] = round(d["hours_required"] * opp.probability / 100, 1)
    line = ResourceDemandForecast(**d)
    db.add(line)
    db.commit()
    return {"id": line.id}


def delete_demand_line_record(db: Session, line_id: str) -> dict:
    line = db.query(ResourceDemandForecast).filter(ResourceDemandForecast.id == line_id).first()
    if not line:
        raise ErrorDeDominio(404)
    db.delete(line)
    db.commit()
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# WHAT-IF SIMULATION
# ═══════════════════════════════════════════════════════════════════════════════

def _resolve_simulation_rate(db: Session, project, tasks) -> float:
    """Tarifa €/hora con la que valorar una simulación de proyecto.

    Auditoría 2026-08 (P2-20). Sustituye a un literal de 80.0 que se aplicaba a
    todos los clientes por igual. Se usa el dato real cuando existe y sólo se
    recurre al valor configurable cuando no hay ninguno.
    """
    # 1. Tarifa de facturación del proyecto: es la que el cliente tiene pactada.
    if project is not None and getattr(project, "billing_rate", None):
        return float(project.billing_rate)

    # 2. Media de las tarifas de los usuarios asignados a las tareas del
    #    proyecto. Refleja la composición real del equipo.
    assignee_ids = {
        getattr(t, "assignee_id", None) for t in (tasks or [])
        if getattr(t, "assignee_id", None)
    }
    if assignee_ids:
        from app.models.user import User

        tarifas = [
            float(r[0])
            for r in db.query(User.hourly_rate)
            .filter(User.id.in_(assignee_ids), User.hourly_rate.isnot(None))
            .all()
            if r[0]
        ]
        if tarifas:
            return sum(tarifas) / len(tarifas)

    # 3. Último recurso: valor por defecto de la instalación.
    return float(settings.DEFAULT_SIMULATION_HOURLY_RATE)


def simulate_project_payload(db: Session, project_id: str, payload) -> dict:

    tasks = db.query(Task).filter(
        Task.project_id == project_id,
        Task.status.not_in([TaskStatus.done, TaskStatus.cancelled]),
    ).all()
    if not tasks:
        raise ErrorDeDominio(404, "No open tasks found")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ErrorDeDominio(404)

    defer_ids = set(payload.defer_task_ids or [])
    cut_ids = set(payload.cut_task_ids or [])

    remaining_tasks = [t for t in tasks if t.id not in cut_ids and t.id not in defer_ids]
    total_hours = sum((t.estimated_hours or 0) for t in remaining_tasks)
    overdue = [t for t in remaining_tasks if t.due_date and t.due_date < timeutil.today()]

    due_dates = [t.due_date for t in remaining_tasks if t.due_date]
    base_end = max(due_dates) if due_dates else timeutil.today()

    sim_end = base_end
    notes = []

    if payload.delay_days:
        sim_end = sim_end + timedelta(days=payload.delay_days)
        notes.append(f"All remaining tasks delayed by {payload.delay_days} days")

    effective_compression = 1.0
    if payload.compress_pct and payload.compress_pct > 0:
        effective_compression = 1 - (payload.compress_pct / 100)
        remaining_days = (sim_end - timeutil.today()).days
        new_days = int(remaining_days * effective_compression)
        sim_end = timeutil.today() + timedelta(days=new_days)
        notes.append(
            f"Team expansion at {payload.compress_pct}% → duration compressed "
            f"from {remaining_days}d to {new_days}d"
        )

    # 18-11-2026: un recurso añadido sin horas trabaja la semana de la empresa (antes 40 fijas).
    semana = capacidad_semanal_de_empresa(db, registro=project)
    if payload.add_resources:
        extra_hours_week = sum(r.get("hours_per_week") or semana for r in payload.add_resources)
        remaining_hours = total_hours * effective_compression
        saved_weeks = (remaining_hours * 0.7) / max(extra_hours_week, 1)
        saved_days = int(saved_weeks * 5)
        sim_end = sim_end - timedelta(days=saved_days)
        notes.append(f"{len(payload.add_resources)} extra resource(s) added → ~{saved_days} days saved")

    deferred_detail = [{
        "id": t.id, "code": t.code, "title": t.title,
        "estimated_hours": t.estimated_hours,
    } for t in tasks if t.id in defer_ids]

    cut_detail = [{
        "id": t.id, "code": t.code, "title": t.title,
        "estimated_hours": t.estimated_hours,
    } for t in tasks if t.id in cut_ids]

    # Tarifa para valorar la simulación (auditoría 2026-08, P2-20). Antes era un
    # literal `avg_rate = 80.0`: cualquier cliente cuyas tarifas no fueran 80 €/h
    # recibía cifras económicas equivocadas, y nada en la interfaz avisaba de que
    # el número era una constante y no su dato.
    #
    # Orden de preferencia, del dato más específico al más genérico:
    #   1. la tarifa de facturación del propio proyecto
    #   2. la media de las tarifas de los usuarios asignados a sus tareas
    #   3. el valor por defecto configurable de la organización
    avg_rate = _resolve_simulation_rate(db, project, tasks)
    cost_delta = -sum((t.estimated_hours or 0) * avg_rate for t in tasks if t.id in cut_ids)
    if payload.add_resources:
        cost_delta += sum(
            (r.get("hours_per_week") or semana) * r.get("rate_per_hour", avg_rate)
            for r in payload.add_resources
        ) * ((sim_end - timeutil.today()).days / 5)

    at_risk = [{
        "id": t.id, "code": t.code, "title": t.title,
        "due_date": str(t.due_date),
    } for t in overdue if t.id not in cut_ids and t.id not in defer_ids]

    return {
        "project_id": project_id,
        "project_name": project.name,
        "simulation": {
            "base_end_date": str(base_end),
            "simulated_end_date": str(sim_end),
            "days_delta": (sim_end - base_end).days,
            "total_remaining_hours": round(total_hours, 1),
            "effective_remaining_hours": round(total_hours * effective_compression, 1),
            "cost_delta_eur": round(cost_delta, 2),
            "deferred_tasks": len(deferred_detail),
            "cut_tasks": len(cut_detail),
            "at_risk_tasks": len(at_risk),
        },
        "notes": notes,
        "deferred": deferred_detail,
        "cut": cut_detail,
        "at_risk": at_risk,
    }
