"""Planificador de un proyecto: lee tareas, vínculos y calendarios, calcula y guarda.

Proyectos — planificador (16-11-2026). Es la única puerta al CPM:

  · `calcular_plan`   → calcula, guarda el resultado en las tareas (columnas de
                        `Task`: early_*, late_*, holguras, is_critical) y devuelve
                        el plan para la pantalla;
  · `recalcular_si_procede` → lo mismo, en silencio y solo si el ajuste
                        `PLANNING_AUTO_RECALCULATE` está activo; lo llaman las
                        escrituras que cambian el plan (fechas, vínculos,
                        estimaciones, asignación, restricciones);
  · `aplicar_plan`    → escribe las fechas tempranas en `start_date`/`due_date`
                        de las tareas no terminadas (el botón «Replanificar»).

`GET /activity/projects/{id}/critical-path` (el de antes) responde ahora con esto.
"""
from __future__ import annotations

import logging
import math
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core import timeutil
from app.core.errores import ErrorDeDominio
from app.models.bookings import TaskDependency
from app.models.project import Project
from app.models.task import Task, TaskStatus
from app.services.planificador.calendario import Calendario, cargar_calendarios
from app.services.planificador.cpm import RESTRICCIONES, ResultadoPlan, TareaPlan, Vinculo, calcular
from app.core.codigos_de_error import error

logger = logging.getLogger(__name__)


# ── Lectura ──────────────────────────────────────────────────────────────────

def proyecto_visible(db: Session, user, project_id: str) -> Project:
    """El proyecto, si es de la empresa del usuario y este lo ve. 404 si no."""
    from app.services.politica_de_visibilidad import exigir_proyecto_visible
    from app.services.tasks.queries import project_for_user

    proyecto = project_for_user(db, project_id, user) if user is not None else (
        db.query(Project).filter(Project.id == project_id).first())
    if not proyecto:
        raise error(404, "no_encontrado", detail="Proyecto no encontrado", que="proyecto")
    if user is not None:
        exigir_proyecto_visible(db, user, project_id)
    return proyecto


def tareas_planificables(db: Session, project_id: str) -> list[Task]:
    return (
        db.query(Task)
        .filter(Task.project_id == project_id, Task.is_active.is_(True),
                Task.status != TaskStatus.cancelled)
        .all()
    )


def vinculos_de(db: Session, ids: set[str]) -> list[TaskDependency]:
    """Dependencias que planifican (las informativas no mueven fechas)."""
    if not ids:
        return []
    return (
        db.query(TaskDependency)
        .filter(TaskDependency.predecessor_id.in_(ids), TaskDependency.successor_id.in_(ids),
                TaskDependency.is_active.is_(True), TaskDependency.link_type == "schedule")
        .all()
    )


def _estado(t: Task) -> str:
    return str(getattr(t.status, "value", t.status))


def _a_fecha(valor) -> Optional[date]:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    return valor


def duracion_de(t: Task, cal: Calendario) -> int:
    """Días laborables de una tarea en su calendario.

    Con inicio y fin, mandan las fechas: es lo que la persona ve y arrastra en
    el Gantt. Sin ellas, las horas estimadas entre la jornada de quien la hace.
    Sin nada, un día. Nunca menos de uno.
    """
    if t.start_date and t.due_date and t.due_date >= t.start_date:
        return cal.duracion(t.start_date, t.due_date)
    if t.estimated_hours:
        return max(1, math.ceil(t.estimated_hours / cal.horas_por_dia))
    return 1


def _tarea_plan(t: Task, cal: Calendario) -> TareaPlan:
    terminada = _estado(t) == TaskStatus.done.value
    fin_real = _a_fecha(t.completed_at) or t.due_date
    inicio_real = t.start_date or _a_fecha(t.started_at) or fin_real
    restriccion = t.constraint_type if t.constraint_type in RESTRICCIONES else None
    return TareaPlan(
        id=t.id,
        duracion=duracion_de(t, cal),
        calendario=cal,
        inicio_fijado=t.start_date,
        restriccion=restriccion,
        fecha_restriccion=t.constraint_date if restriccion else None,
        fijada=bool(terminada and inicio_real and fin_real),
        inicio_real=inicio_real,
        fin_real=max(fin_real, inicio_real) if (fin_real and inicio_real) else fin_real,
    )


def _umbrales(db: Session, org_id: Optional[str]) -> tuple[float, float]:
    from app.services.settings_service import get_runtime_float
    critico = get_runtime_float(db, "PLANNING_CRITICAL_FLOAT_DAYS", org_id) or 0.0
    casi = get_runtime_float(db, "PLANNING_NEAR_CRITICAL_FLOAT_DAYS", org_id) or 0.0
    return critico, max(casi, critico)


def preparar(db: Session, proyecto: Project, tareas: list[Task]):
    """Calendarios, tareas del CPM y vínculos de un proyecto. Lo comparten el
    cálculo, la cascada y la nivelación."""
    inicio_proyecto = (
        proyecto.start_date
        or min((t.start_date for t in tareas if t.start_date), default=None)
        or timeutil.today()
    )
    cal_empresa, por_persona = cargar_calendarios(
        db, proyecto.organization_id, {t.assignee_id for t in tareas if t.assignee_id}, inicio_proyecto)
    calendarios = {t.id: por_persona.get(t.assignee_id, cal_empresa) for t in tareas}
    plan = [_tarea_plan(t, calendarios[t.id]) for t in tareas]
    deps = vinculos_de(db, {t.id for t in tareas})
    vinculos = [Vinculo(d.predecessor_id, d.successor_id,
                        str(getattr(d.dependency_type, "value", d.dependency_type) or "FS"),
                        int(d.lag_days or 0)) for d in deps]
    return inicio_proyecto, cal_empresa, calendarios, plan, vinculos


# ── Cálculo ──────────────────────────────────────────────────────────────────

def _guardar(db: Session, tareas: list[Task], resultado: ResultadoPlan) -> None:
    """Escribe el resultado en las tareas sin tocar `updated_at` ni `version`:
    recalcular no es que alguien haya editado la tarea."""
    ahora = datetime.now(timezone.utc)
    for t in tareas:
        r = resultado.tareas.get(t.id)
        if r is None:
            continue
        db.query(Task).filter(Task.id == t.id).update({
            Task.early_start: r.inicio_temprano,
            Task.early_finish: r.fin_temprano,
            Task.late_start: r.inicio_tardio,
            Task.late_finish: r.fin_tardio,
            Task.total_float_days: r.holgura_total,
            Task.free_float_days: r.holgura_libre,
            Task.is_critical: bool(r.critica),
            Task.schedule_computed_at: ahora,
            Task.updated_at: Task.updated_at,
        }, synchronize_session=False)


def calcular_plan(db: Session, user, project_id: str, guardar: bool = True) -> dict:
    """Calcula el camino crítico del proyecto y, por defecto, lo guarda."""
    proyecto = proyecto_visible(db, user, project_id)
    tareas = tareas_planificables(db, project_id)
    if not tareas:
        return _plan_vacio(proyecto)
    inicio, cal_empresa, calendarios, plan, vinculos = preparar(db, proyecto, tareas)
    critico, casi = _umbrales(db, proyecto.organization_id)
    resultado = calcular(plan, vinculos, inicio, cal_empresa, critico)
    if guardar:
        _guardar(db, tareas, resultado)
        db.commit()
    return _payload(db, proyecto, tareas, plan, resultado, cal_empresa, vinculos, casi)


def recalcular_si_procede(db: Session, project_id: Optional[str]) -> None:
    """Recalcula tras una escritura que cambia el plan. Nunca rompe la escritura:
    si falla, queda en el log y el plan se recalcula en la siguiente."""
    if not project_id:
        return
    try:
        from app.services.settings_service import get_runtime_bool
        proyecto = db.query(Project).filter(Project.id == project_id).first()
        if not proyecto or not get_runtime_bool(db, "PLANNING_AUTO_RECALCULATE", proyecto.organization_id):
            return
        tareas = tareas_planificables(db, project_id)
        if not tareas:
            return
        inicio, cal_empresa, _cals, plan, vinculos = preparar(db, proyecto, tareas)
        critico, _casi = _umbrales(db, proyecto.organization_id)
        _guardar(db, tareas, calcular(plan, vinculos, inicio, cal_empresa, critico))
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("planificador: no se pudo recalcular el proyecto %s", project_id, exc_info=True)


def aplicar_plan(db: Session, user, project_id: str) -> dict:
    """Mueve las tareas no terminadas a sus fechas tempranas (replanificar)."""
    from app.services.audit import audit_log

    proyecto = proyecto_visible(db, user, project_id)
    tareas = tareas_planificables(db, project_id)
    if not tareas:
        return {"moved": [], "total_moved": 0}
    inicio, cal_empresa, _cals, plan, vinculos = preparar(db, proyecto, tareas)
    critico, _casi = _umbrales(db, proyecto.organization_id)
    resultado = calcular(plan, vinculos, inicio, cal_empresa, critico)
    movidas = []
    for t in tareas:
        r = resultado.tareas.get(t.id)
        if r is None or _estado(t) == TaskStatus.done.value:
            continue
        if t.start_date == r.inicio_temprano and t.due_date == r.fin_temprano:
            continue
        movidas.append({
            "task_id": t.id, "code": t.code, "title": t.title,
            "old_start": t.start_date.isoformat() if t.start_date else None,
            "old_due": t.due_date.isoformat() if t.due_date else None,
            "new_start": r.inicio_temprano.isoformat(), "new_due": r.fin_temprano.isoformat(),
        })
        t.start_date, t.due_date = r.inicio_temprano, r.fin_temprano
    _guardar(db, tareas, resultado)
    if movidas:
        audit_log(db, user, "UPDATE", "project_schedule", project_id, proyecto.name,
                  new_values={"moved_tasks": len(movidas)}, metadata={"action": "apply_schedule"})
    db.commit()
    return {"moved": movidas, "total_moved": len(movidas)}


# ── Respuesta ────────────────────────────────────────────────────────────────

def _plan_vacio(proyecto: Project) -> dict:
    return {
        "project_id": proyecto.id, "project_start": None, "project_finish": None,
        "deadline": proyecto.end_date_planned.isoformat() if proyecto.end_date_planned else None,
        "finish_vs_deadline_days": None, "project_duration_days": 0,
        "critical_path": [], "cycle": [], "nodes": [], "links": [], "calendar": None,
    }


def _payload(db: Session, proyecto: Project, tareas: list[Task], plan: list[TareaPlan],
             resultado: ResultadoPlan, cal_empresa: Calendario, vinculos: list[Vinculo],
             umbral_casi: float) -> dict:
    from app.services.baselines_service import fechas_de_linea_base_vigente

    por_id = {t.id: t for t in tareas}
    duraciones = {p.id: p.duracion for p in plan}
    base = fechas_de_linea_base_vigente(db, proyecto.id)
    nodos = []
    for tid in resultado.orden:
        t, r = por_id[tid], resultado.tareas[tid]
        b = base.get(tid)
        nodos.append({
            "id": t.id, "code": t.code, "title": t.title, "status": _estado(t),
            "assignee_id": t.assignee_id,
            "duration_days": duraciones[tid],
            "start_date": t.start_date.isoformat() if t.start_date else None,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "early_start": r.inicio_temprano.isoformat(), "early_finish": r.fin_temprano.isoformat(),
            "late_start": r.inicio_tardio.isoformat(), "late_finish": r.fin_tardio.isoformat(),
            "total_float": r.holgura_total, "free_float": r.holgura_libre,
            "is_critical": r.critica,
            "is_near_critical": (not r.critica) and r.holgura_total <= umbral_casi
                                and _estado(t) != TaskStatus.done.value,
            "constraint_type": t.constraint_type, "constraint_date":
                t.constraint_date.isoformat() if t.constraint_date else None,
            "baseline_start": b[0].isoformat() if b and b[0] else None,
            "baseline_end": b[1].isoformat() if b and b[1] else None,
            "in_cycle": tid in resultado.ciclo,
        })
    nodos.sort(key=lambda n: (n["early_start"], n["code"] or ""))
    plazo = proyecto.end_date_planned
    return {
        "project_id": proyecto.id,
        "project_start": resultado.inicio_proyecto.isoformat(),
        "project_finish": resultado.fin_proyecto.isoformat(),
        "deadline": plazo.isoformat() if plazo else None,
        "finish_vs_deadline_days": cal_empresa.distancia(plazo, resultado.fin_proyecto) if plazo else None,
        "project_duration_days": cal_empresa.laborables_en(resultado.inicio_proyecto, resultado.fin_proyecto),
        "critical_path": [por_id[tid].code for tid in resultado.camino_critico],
        "cycle": resultado.ciclo,
        "nodes": nodos,
        "links": [{"predecessor_id": v.predecesora, "successor_id": v.sucesora,
                   "dependency_type": v.tipo, "lag_days": v.desfase} for v in vinculos],
        "calendar": {
            "workdays": sorted(cal_empresa.dias_laborables),
            "hours_per_day": cal_empresa.horas_por_dia,
            "holidays": sorted(d.isoformat() for d in cal_empresa.no_laborables
                               if resultado.inicio_proyecto <= d <= resultado.fin_proyecto),
        },
    }
