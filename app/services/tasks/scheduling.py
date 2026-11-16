"""
tasks/scheduling.py — Replanificación en cascada al mover el fin de una tarea.

Exports:
    cascade_reschedule

Proyectos — planificador (16-11-2026). Antes solo seguía vínculos fin-inicio y
contaba días naturales. Ahora sigue los cuatro tipos (FS, SS, FF, SF) con su
desfase, en días laborables del calendario de cada tarea (el de la persona
asignada: festivos de la empresa y sus ausencias aprobadas), y usa las mismas
reglas que el camino crítico (`planificador/cpm.py`: `inicio_minimo`), así que
cascada y CPM no pueden discrepar.

Solo **empuja**: una sucesora se mueve si el vínculo ya no se cumple; si sigue
cumpliéndose, se queda donde la puso quien planifica. Al moverla se conserva su
duración en días laborables. Las terminadas no se mueven.
"""
from __future__ import annotations

from collections import deque
from datetime import date

from sqlalchemy.orm import Session

from app.core.errores import ErrorDeDominio
from app.models.bookings import TaskDependency
from app.models.project import Project
from app.models.task import Task, TaskStatus


def _fila(t: Task, inicio_ant, fin_ant) -> dict:
    return {
        "task_id": t.id,
        "title": t.title,
        "old_start_date": str(inicio_ant) if inicio_ant else None,
        "new_start_date": str(t.start_date) if t.start_date else None,
        "old_due_date": str(fin_ant) if fin_ant else None,
        "new_due_date": str(t.due_date) if t.due_date else None,
        "shift_days": (t.due_date - fin_ant).days if (t.due_date and fin_ant) else 0,
    }


def cascade_reschedule(task_id: str, new_end_date: date, db: Session) -> dict:
    """Mueve el fin de una tarea y propaga a sus sucesoras con los cuatro tipos de vínculo."""
    from app.services.planificador.calendario import cargar_calendarios
    from app.services.planificador.cpm import inicio_minimo
    from app.services.planificador.servicio import duracion_de, recalcular_si_procede, tareas_planificables

    raiz = db.query(Task).filter(Task.id == task_id).first()
    if not raiz:
        raise ErrorDeDominio(404, "Tarea no encontrada")
    if not raiz.due_date:
        raise ErrorDeDominio(400, "La tarea raíz no tiene fecha de fin definida")
    if new_end_date == raiz.due_date:
        return {"rescheduled": [], "total_shifted": 0,
                "message": "No hay cambio de fecha — nada que replanificar"}

    proyecto = db.query(Project).filter(Project.id == raiz.project_id).first()
    tareas = {t.id: t for t in tareas_planificables(db, raiz.project_id)}
    tareas.setdefault(raiz.id, raiz)
    cal_empresa, por_persona = cargar_calendarios(
        db, getattr(proyecto, "organization_id", None),
        {t.assignee_id for t in tareas.values() if t.assignee_id},
        min(raiz.due_date, new_end_date))

    def cal(t: Task):
        return por_persona.get(t.assignee_id, cal_empresa)

    duraciones = {tid: duracion_de(t, cal(t)) for tid, t in tareas.items()}

    deps = db.query(TaskDependency).filter(
        TaskDependency.predecessor_id.in_(list(tareas)), TaskDependency.successor_id.in_(list(tareas)),
        TaskDependency.is_active.is_(True), TaskDependency.link_type == "schedule",
    ).all()
    sucesoras: dict[str, list] = {}
    predecesoras: dict[str, list] = {}
    for d in deps:
        sucesoras.setdefault(d.predecessor_id, []).append(d)
        predecesoras.setdefault(d.successor_id, []).append(d)

    # 1. La raíz: nuevo fin, misma duración laborable.
    inicio_ant, fin_ant = raiz.start_date, raiz.due_date
    raiz.due_date = new_end_date
    if raiz.start_date:
        raiz.start_date = cal(raiz).inicio_desde(raiz.due_date, duraciones[raiz.id])
    movidas = [_fila(raiz, inicio_ant, fin_ant)]

    # 2. En anchura por las sucesoras. Una tarea puede revisitarse si otra de sus
    #    predecesoras la vuelve a empujar; el tope de visitas (aristas + 1 por
    #    tarea) impide girar sin fin si los datos traen un ciclo.
    originales: dict[str, tuple] = {}
    cola: deque = deque([raiz.id])
    visitas: dict[str, int] = {}
    tope = len(deps) + 1
    while cola:
        actual = cola.popleft()
        for d in sucesoras.get(actual, []):
            s = tareas.get(d.successor_id)
            if s is None or s.id == raiz.id or str(getattr(s.status, "value", s.status)) == TaskStatus.done.value:
                continue
            visitas[s.id] = visitas.get(s.id, 0) + 1
            if visitas[s.id] > tope:
                continue
            requerido = None
            for p_dep in predecesoras.get(s.id, []):
                p = tareas[p_dep.predecessor_id]
                if not p.due_date:
                    continue
                p_inicio = p.start_date or cal(p).inicio_desde(p.due_date, duraciones[p.id])
                minimo = inicio_minimo(
                    str(getattr(p_dep.dependency_type, "value", p_dep.dependency_type) or "FS"),
                    int(p_dep.lag_days or 0), p_inicio, p.due_date, cal_empresa, cal(s), duraciones[s.id])
                requerido = minimo if requerido is None else max(requerido, minimo)
            if requerido is None:
                continue
            inicio_actual = s.start_date or (cal(s).inicio_desde(s.due_date, duraciones[s.id]) if s.due_date else None)
            if inicio_actual is not None and inicio_actual >= requerido:
                continue
            ini_ant, fin_ant_s = originales.setdefault(s.id, (s.start_date, s.due_date))
            nuevo_fin = cal(s).fin_desde(requerido, duraciones[s.id])
            if s.start_date or not s.due_date:
                s.start_date = requerido
            s.due_date = nuevo_fin
            movidas = [m for m in movidas if m["task_id"] != s.id] + [_fila(s, ini_ant, fin_ant_s)]
            cola.append(s.id)

    db.commit()
    recalcular_si_procede(db, raiz.project_id)
    return {"rescheduled": movidas, "total_shifted": len(movidas)}
