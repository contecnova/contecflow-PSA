"""Líneas base del Gantt: congelar un cronograma y comparar contra él.

Auditoría 2026-08 (hallazgo 22). Estas operaciones vivían en
`endpoints/baselines.py` con **nueve consultas y escrituras directas**, y al
bajarlas apareció lo mismo que en el resto del hallazgo: los cuatro endpoints
anclan en `project_id` y **ninguno comprobaba de quién es el proyecto**.

Proyectos — planificador (16-11-2026, rev. 173):

  · la foto se guarda **por tarea** en `gantt_baseline_tasks` (antes, un JSON
    que nadie podía consultar). La migración 173 pasó los JSON viejos a filas;
  · cada proyecto tiene una línea base **vigente** (`is_current`): contra ella
    pinta el Gantt su barra de línea base, `/tasks` devuelve `baseline_start` y
    `baseline_end`, y el valor ganado saca su PV;
  · se puede comparar el plan de hoy contra cualquiera de ellas, y dos líneas
    base entre sí.

Un cronograma congelado lleva el presupuesto del proyecto en el momento de
congelarlo (`budget_at_freeze`) y el coste planificado de cada tarea: no es
metadato inocuo, y por eso cada lectura comprueba el proyecto.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.core import timeutil
from app.core.errores import ErrorDeDominio
from app.models.marketplace import GanttBaseline, GanttBaselineTask
from app.models.project import Project
from app.models.task import Task

logger = logging.getLogger(__name__)

#: Estados que cuentan como tarea terminada al congelar. Se comparan por su
#: valor de texto porque el modelo usa un `Enum` y el histórico trae cadenas.
ESTADOS_TERMINADOS = ("done", "closed", "completed")


def _org_de(user) -> Optional[str]:
    return getattr(user, "organization_id", None)


def _texto_de_estado(tarea: Task) -> str:
    return str(getattr(tarea.status, "value", tarea.status))


def proyecto_propio(db: Session, user, project_id: str) -> Project:
    """El proyecto, si es de la organización del usuario (y lo ve). 404 si no."""
    fila = (
        db.query(Project)
        .filter(Project.id == project_id, Project.organization_id == _org_de(user))
        .first()
    )
    if not fila:
        raise ErrorDeDominio(404, "Project not found")
    if hasattr(user, "role"):
        from app.services.politica_de_visibilidad import exigir_proyecto_visible
        exigir_proyecto_visible(db, user, project_id)
    return fila


def linea_base_propia(db: Session, user, project_id: str, baseline_id: str) -> GanttBaseline:
    """Una línea base de un proyecto ya comprobado."""
    proyecto_propio(db, user, project_id)
    fila = (
        db.query(GanttBaseline)
        .filter(GanttBaseline.id == baseline_id, GanttBaseline.project_id == project_id)
        .first()
    )
    if not fila:
        raise ErrorDeDominio(404, "Baseline not found")
    return fila


def list_baselines(db: Session, user, project_id: str) -> list[GanttBaseline]:
    proyecto_propio(db, user, project_id)
    return (
        db.query(GanttBaseline)
        .filter(GanttBaseline.project_id == project_id)
        .order_by(GanttBaseline.baseline_date.desc(), GanttBaseline.created_at.desc())
        .all()
    )


def serializar(b: GanttBaseline) -> dict:
    return {
        "id": b.id,
        "name": b.name,
        "description": b.description,
        "baseline_date": str(b.baseline_date),
        "total_tasks": b.total_tasks,
        "completed_tasks": b.completed_tasks,
        "total_hours": b.total_hours,
        "budget_at_freeze": b.budget_at_freeze,
        "is_initial": bool(b.is_initial),
        "is_current": bool(b.is_current),
        "created_at": str(b.created_at) if b.created_at else None,
    }


def _costes_por_hora(db: Session, user_ids: Iterable[str]) -> dict[str, float]:
    from app.services.cost_service import cost_per_hour_bulk
    try:
        return cost_per_hour_bulk(db, [u for u in set(user_ids) if u], timeutil.today())
    except Exception:  # sin perfiles de coste: el PV se queda en horas
        logger.warning("linea base: sin coste por hora; el PV se queda en horas", exc_info=True)
        return {}


def _hacer_vigente(db: Session, project_id: str, baseline: GanttBaseline) -> None:
    db.query(GanttBaseline).filter(
        GanttBaseline.project_id == project_id, GanttBaseline.id != baseline.id,
    ).update({GanttBaseline.is_current: False}, synchronize_session=False)
    baseline.is_current = True


def crear_linea_base(
    db: Session, user, project_id: str, *,
    name: str, description: Optional[str], is_initial: bool, make_current: Optional[bool] = None,
) -> GanttBaseline:
    """Congela el cronograma actual del proyecto como línea base.

    La primera de un proyecto es la vigente; las siguientes, solo si se pide.
    """
    from app.services.audit import audit_log

    proyecto = proyecto_propio(db, user, project_id)
    tareas = db.query(Task).filter(Task.project_id == project_id, Task.is_active.is_(True)).all()
    costes = _costes_por_hora(db, (t.assignee_id for t in tareas))

    horas = sum(t.estimated_hours or 0 for t in tareas)
    terminadas = sum(1 for t in tareas if _texto_de_estado(t) in ESTADOS_TERMINADOS)
    ya_hay = db.query(GanttBaseline.id).filter(GanttBaseline.project_id == project_id).first() is not None

    fila = GanttBaseline(
        organization_id=_org_de(user),
        project_id=project_id,
        name=name,
        description=description,
        baseline_date=timeutil.today(),
        total_tasks=len(tareas),
        completed_tasks=terminadas,
        total_hours=horas,
        budget_at_freeze=proyecto.budget_amount,
        is_initial=is_initial,
        created_by=user.id,
    )
    db.add(fila)
    db.flush()
    for t in tareas:
        coste = costes.get(t.assignee_id)
        db.add(GanttBaselineTask(
            organization_id=_org_de(user), baseline_id=fila.id, task_id=t.id, title=t.title,
            start_date=t.start_date, end_date=t.due_date, estimated_hours=t.estimated_hours,
            planned_cost=(t.estimated_hours * coste) if (t.estimated_hours and coste) else None,
            status=_texto_de_estado(t), assignee_id=t.assignee_id, progress_pct=t.progress_pct,
        ))
    if make_current or (make_current is None and not ya_hay):
        _hacer_vigente(db, project_id, fila)
    audit_log(db, user, "CREATE", "gantt_baseline", fila.id, name,
              new_values={"project_id": project_id, "tasks": len(tareas), "is_current": bool(fila.is_current)})
    db.commit()
    db.refresh(fila)
    return fila


def marcar_vigente(db: Session, user, project_id: str, baseline_id: str) -> GanttBaseline:
    from app.services.audit import audit_log
    fila = linea_base_propia(db, user, project_id, baseline_id)
    _hacer_vigente(db, project_id, fila)
    audit_log(db, user, "UPDATE", "gantt_baseline", fila.id, fila.name, new_values={"is_current": True})
    db.commit()
    db.refresh(fila)
    return fila


def tareas_de_linea_base(db: Session, baseline: GanttBaseline) -> dict[str, dict]:
    """La foto por tarea. Filas si las hay; si no, el JSON histórico."""
    filas = db.query(GanttBaselineTask).filter(GanttBaselineTask.baseline_id == baseline.id).all()
    if filas:
        return {f.task_id: {
            "title": f.title,
            "start": f.start_date.isoformat() if f.start_date else None,
            "end": f.end_date.isoformat() if f.end_date else None,
            "status": f.status, "estimated_hours": f.estimated_hours, "planned_cost": f.planned_cost,
        } for f in filas}
    try:
        congelado = json.loads(baseline.schedule_snapshot or "{}")
    except ValueError:
        return {}
    return {t["task_id"]: t for t in congelado.get("tasks", []) if t.get("task_id")}


def _dias_de_desvio(fin_actual: Optional[str], fin_congelado: Optional[str]) -> Optional[int]:
    """Días entre el fin actual y el congelado, o `None` si falta alguno.

    Una fecha ilegible da `None` y no rompe la comparación entera: la línea base
    es un histórico y puede traer datos de versiones anteriores.
    """
    if not (fin_actual and fin_congelado):
        return None
    try:
        return (date.fromisoformat(fin_actual) - date.fromisoformat(fin_congelado)).days
    except ValueError:
        return None


def _comparar(actual: dict[str, dict], congelado: dict[str, dict]) -> tuple[list, dict]:
    deltas = []
    for tid, a in actual.items():
        anterior = congelado.get(tid)
        if not anterior:
            deltas.append({"task_id": tid, "title": a.get("title"), "delta": "new_task",
                           "current_start": a.get("start"), "current_end": a.get("end")})
            continue
        deltas.append({
            "task_id": tid,
            "title": a.get("title"),
            "baseline_start": anterior.get("start"),
            "baseline_end": anterior.get("end"),
            "current_start": a.get("start"),
            "current_end": a.get("end"),
            "start_slip_days": _dias_de_desvio(a.get("start"), anterior.get("start")),
            "slip_days": _dias_de_desvio(a.get("end"), anterior.get("end")),
            "baseline_status": anterior.get("status"),
            "current_status": a.get("status"),
            "baseline_hours": anterior.get("estimated_hours"),
            "current_hours": a.get("estimated_hours"),
        })
    borradas = [{"task_id": tid, "title": c.get("title"), "delta": "removed",
                 "baseline_start": c.get("start"), "baseline_end": c.get("end")}
                for tid, c in congelado.items() if tid not in actual]
    comparadas = [d for d in deltas if d.get("delta") != "new_task"]
    desvios = [d.get("slip_days") or 0 for d in comparadas]
    resumen = {
        "tasks_compared": len(comparadas),
        "tasks_slipped": sum(1 for s in desvios if s > 0),
        "tasks_ahead": sum(1 for s in desvios if s < 0),
        "avg_slip_days": round(sum(desvios) / max(len(desvios), 1), 1),
        "max_slip_days": max(desvios, default=0),
        "tasks_removed": len(borradas),
        "tasks_added": sum(1 for d in deltas if d.get("delta") == "new_task"),
        "baseline_hours": round(sum((c.get("estimated_hours") or 0) for c in congelado.values()), 1),
        "current_hours": round(sum((a.get("estimated_hours") or 0) for a in actual.values()), 1),
    }
    return deltas + borradas, resumen


def comparar_con_linea_base(db: Session, user, project_id: str, baseline_id: str,
                            against_id: Optional[str] = None) -> dict:
    """Compara el cronograma de hoy (o otra línea base, `against_id`) contra una congelada."""
    linea = linea_base_propia(db, user, project_id, baseline_id)
    congelado = tareas_de_linea_base(db, linea)
    if against_id:
        otra = linea_base_propia(db, user, project_id, against_id)
        actual = tareas_de_linea_base(db, otra)
        contra = {"id": otra.id, "name": otra.name, "baseline_date": str(otra.baseline_date)}
    else:
        actual = {t.id: {
            "title": t.title,
            "start": t.start_date.isoformat() if t.start_date else None,
            "end": t.due_date.isoformat() if t.due_date else None,
            "status": _texto_de_estado(t), "estimated_hours": t.estimated_hours,
        } for t in db.query(Task).filter(Task.project_id == project_id, Task.is_active.is_(True)).all()}
        contra = None
    deltas, resumen = _comparar(actual, congelado)
    return {
        "baseline_id": baseline_id,
        "baseline_name": linea.name,
        "baseline_date": str(linea.baseline_date),
        "against": contra,
        "summary": resumen,
        "task_deltas": deltas,
    }


def borrar_linea_base(db: Session, user, project_id: str, baseline_id: str) -> None:
    from app.services.audit import audit_log
    fila = linea_base_propia(db, user, project_id, baseline_id)
    audit_log(db, user, "DELETE", "gantt_baseline", fila.id, fila.name)
    db.delete(fila)
    db.commit()


# ── Para el Gantt, /tasks y el valor ganado ─────────────────────────────────

def linea_base_vigente(db: Session, project_id: str) -> Optional[GanttBaseline]:
    return (db.query(GanttBaseline)
            .filter(GanttBaseline.project_id == project_id, GanttBaseline.is_current.is_(True))
            .first())


def fechas_de_linea_base_vigente(db: Session, project_id: str) -> dict[str, tuple]:
    """{task_id: (inicio, fin)} de la línea base vigente del proyecto."""
    base = linea_base_vigente(db, project_id)
    if base is None:
        return {}
    return {tid: (s, e) for tid, s, e in db.query(
        GanttBaselineTask.task_id, GanttBaselineTask.start_date, GanttBaselineTask.end_date,
    ).filter(GanttBaselineTask.baseline_id == base.id).all()}


def anotar_linea_base(db: Session, tareas: list) -> list:
    """Pone `baseline_start`/`baseline_end` a una página de tareas (dos consultas
    para toda la página, sea de uno o de varios proyectos)."""
    proyectos = {t.project_id for t in tareas if getattr(t, "project_id", None)}
    if not proyectos:
        return tareas
    vigentes = dict(db.query(GanttBaseline.project_id, GanttBaseline.id).filter(
        GanttBaseline.project_id.in_(proyectos), GanttBaseline.is_current.is_(True)).all())
    if not vigentes:
        return tareas
    fechas = {(b, tid): (s, e) for b, tid, s, e in db.query(
        GanttBaselineTask.baseline_id, GanttBaselineTask.task_id,
        GanttBaselineTask.start_date, GanttBaselineTask.end_date,
    ).filter(GanttBaselineTask.baseline_id.in_(list(vigentes.values())),
             GanttBaselineTask.task_id.in_([t.id for t in tareas])).all()}
    for t in tareas:
        par = fechas.get((vigentes.get(t.project_id), t.id))
        if par:
            t.baseline_start, t.baseline_end = par
    return tareas
