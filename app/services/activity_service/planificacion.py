"""Planificacion: camino critico, demanda de recursos y simulacion de proyecto.

Parte de `app.services.activity_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from datetime import date, timedelta
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.activity import ResourceDemandForecast
from app.models.bookings import TaskDependency
from app.models.pipeline import Opportunity, OpportunityStage
from app.models.project import Project
from app.models.task import Task, TaskStatus
from app.core import timeutil
from app.core.errores import ErrorDeDominio


# ═══════════════════════════════════════════════════════════════════════════════
# CRITICAL PATH (CPM)
# ═══════════════════════════════════════════════════════════════════════════════

# ── Camino crítico (CPM), fase a fase ────────────────────────────────────────
#
# Auditoría 2026-09. `critical_path_payload` llevaba las cinco fases del método
# en un solo cuerpo y llegaba a complejidad 16. No se ha partido por el número:
# las fases del CPM **tienen nombre de libro** —construir el grafo, ordenar
# topológicamente, pasada adelante, pasada atrás—, y con cada una en su función
# el cuerpo principal se lee como el algoritmo que es.


def _duracion_en_dias(t: Task) -> float:
    """Los días que dura una tarea, con la cascada de fuentes que ya tenía.

    Las horas estimadas mandan —a ocho por día—; si no hay, la ventana entre
    fechas; y si tampoco, un día. Nunca menos de uno: una tarea de duración
    cero no existe en un camino crítico, colapsaría a sus vecinas.
    """
    if t.estimated_hours:
        return max(1, t.estimated_hours / 8)
    if t.start_date and t.due_date:
        return max(1, (t.due_date - t.start_date).days + 1)
    return 1.0


def _grafo_de_dependencias(task_map: dict, deps: list) -> tuple[dict, dict]:
    """Sucesores y predecesores de cada tarea, con su desfase."""
    sucesores: dict = {tid: [] for tid in task_map}
    predecesores: dict = {tid: [] for tid in task_map}
    for d in deps:
        sucesores[d.predecessor_id].append((d.successor_id, d.lag_days or 0))
        predecesores[d.successor_id].append((d.predecessor_id, d.lag_days or 0))
    return sucesores, predecesores


def _orden_topologico(task_map: dict, sucesores: dict, predecesores: dict) -> list:
    """Las tareas en orden de dependencia (Kahn).

    Las que quedan fuera del recorrido —porque forman un ciclo— **se añaden al
    final en vez de descartarse**. Un ciclo de dependencias es un dato malo, no
    una excepción: descartar esas tareas dejaría un diagrama al que le faltan
    filas sin decir por qué. Puestas al final, el cálculo sigue y se ven.
    """
    grado = {tid: len(predecesores[tid]) for tid in task_map}
    cola = [tid for tid, g in grado.items() if g == 0]
    orden = []
    while cola:
        n = cola.pop(0)
        orden.append(n)
        for (suc, _) in sucesores[n]:
            grado[suc] -= 1
            if grado[suc] == 0:
                cola.append(suc)

    for tid in task_map:
        if tid not in orden:
            orden.append(tid)
    return orden


def _pasada_adelante(task_map: dict, orden: list, predecesores: dict) -> tuple[dict, dict]:
    """Inicio y fin más tempranos de cada tarea."""
    ES: dict = {tid: 0.0 for tid in task_map}
    EF: dict = {}
    for tid in orden:
        if predecesores[tid]:
            ES[tid] = max(EF[pid] + desfase
                          for pid, desfase in predecesores[tid] if pid in EF)
        EF[tid] = ES[tid] + _duracion_en_dias(task_map[tid])
    return ES, EF


def _pasada_atras(task_map: dict, orden: list, sucesores: dict,
                  duracion_proyecto: float) -> tuple[dict, dict]:
    """Inicio y fin más tardíos, recorriendo el orden al revés."""
    LF: dict = {tid: duracion_proyecto for tid in task_map}
    LS: dict = {}
    for tid in reversed(orden):
        if sucesores[tid]:
            LF[tid] = min(LS[sid] - desfase
                          for sid, desfase in sucesores[tid] if sid in LS)
        LS[tid] = LF[tid] - _duracion_en_dias(task_map[tid])
    return LS, LF


def critical_path_payload(db: Session, project_id: str) -> dict:

    tasks = db.query(Task).filter(
        Task.project_id == project_id,
        Task.status != TaskStatus.cancelled,
    ).all()
    if not tasks:
        raise ErrorDeDominio(404, "No tasks found for this project")

    task_map = {t.id: t for t in tasks}
    deps = db.query(TaskDependency).filter(
        TaskDependency.predecessor_id.in_(task_map.keys()),
        TaskDependency.successor_id.in_(task_map.keys()),
    ).all()

    successors, predecessors = _grafo_de_dependencias(task_map, deps)
    dur = _duracion_en_dias
    topo_order = _orden_topologico(task_map, successors, predecessors)
    ES, EF = _pasada_adelante(task_map, topo_order, predecessors)
    project_duration = max(EF.values()) if EF else 0
    LS, LF = _pasada_atras(task_map, topo_order, successors, project_duration)

    nodes = []
    for tid in topo_order:
        t = task_map[tid]
        float_val = round(LS[tid] - ES[tid], 2)
        nodes.append({
            "id": t.id,
            "code": t.code,
            "title": t.title,
            "duration_days": round(dur(t), 1),
            "early_start": round(ES[tid], 2),
            "early_finish": round(EF[tid], 2),
            "late_start": round(LS[tid], 2),
            "late_finish": round(LF[tid], 2),
            "total_float": float_val,
            "is_critical": float_val <= 0,
            "status": t.status.value,
            "assignee_id": t.assignee_id,
        })

    critical_path = [n["code"] for n in nodes if n["is_critical"]]
    nodes.sort(key=lambda x: x["early_start"])

    return {
        "project_id": project_id,
        "project_duration_days": round(project_duration, 1),
        "critical_path": critical_path,
        "nodes": nodes,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# RESOURCE DEMAND
# ═══════════════════════════════════════════════════════════════════════════════

def resource_demand_payload(db: Session, horizon_months: int, min_probability: float) -> dict:

    today = timeutil.today()
    date(
        today.year + (today.month + horizon_months - 1) // 12,
        (today.month + horizon_months - 1) % 12 + 1,
        1,
    )

    active_opps = db.query(Opportunity).filter(
        Opportunity.stage.not_in([OpportunityStage.won, OpportunityStage.lost, OpportunityStage.cancelled]),
        Opportunity.probability >= min_probability,
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
        "horizon_months": horizon_months,
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

    if payload.add_resources:
        extra_hours_week = sum(r.get("hours_per_week", 40) for r in payload.add_resources)
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
            r.get("hours_per_week", 40) * r.get("rate_per_hour", avg_rate)
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
