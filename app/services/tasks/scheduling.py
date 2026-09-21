"""
tasks/scheduling.py — Date/dependency cascade logic for tasks.

Exports:
    cascade_reschedule
"""
from __future__ import annotations

from collections import deque
from datetime import date, timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.bookings import TaskDependency, DependencyType
from app.models.task import Task


def _mover_sucesora(succ, current_task, dep) -> Optional[dict]:
    """Mueve una tarea sucesora detrás de su predecesora. `None` si no se puede.

    La sucesora empieza al día siguiente de que acabe la predecesora, más el
    desfase declarado en la dependencia.

    Dos casos:
      · Con fecha de inicio y de fin, **se conserva la duración**: la tarea se
        desplaza entera, no se estira.
      · Sólo con fecha de fin, se desplaza lo mismo que se habría desplazado el
        inicio.

    Una tarea sin ninguna fecha no se puede mover, y devuelve `None`.
    """
    nuevo_inicio = current_task.due_date + timedelta(days=1) + timedelta(days=dep.lag_days or 0)

    if succ.start_date and succ.due_date:
        duracion = succ.due_date - succ.start_date
        fin_anterior = succ.due_date
        succ.start_date = nuevo_inicio
        succ.due_date = nuevo_inicio + duracion
    elif succ.due_date:
        fin_anterior = succ.due_date
        succ.due_date = succ.due_date + (nuevo_inicio - (succ.start_date or succ.due_date))
    else:
        return None

    return {
        "task_id": succ.id,
        "title": succ.title,
        "old_due_date": str(fin_anterior),
        "new_due_date": str(succ.due_date),
        "shift_days": (succ.due_date - fin_anterior).days,
    }


def _propagar_a_sucesoras(db: Session, raiz_id: str) -> list[dict]:
    """Recorre las sucesoras fin-a-inicio en anchura y las mueve.

    El conjunto de visitadas no es una optimización: un grafo de dependencias
    puede tener ciclos, y sin él esto giraría para siempre. Una tarea se visita
    **una sola vez**, así que en un rombo manda el primer camino que llega.
    """
    movidas: list[dict] = []
    vistas = {raiz_id}
    cola: deque = deque([raiz_id])

    while cola:
        actual = db.query(Task).filter(Task.id == cola.popleft()).first()
        if not actual or not actual.due_date:
            continue

        dependencias = db.query(TaskDependency).filter(
            TaskDependency.predecessor_id == actual.id,
            TaskDependency.dependency_type == DependencyType.finish_to_start,
        ).all()

        for dep in dependencias:
            if dep.successor_id in vistas:
                continue
            vistas.add(dep.successor_id)
            sucesora = db.query(Task).filter(Task.id == dep.successor_id).first()
            if not sucesora:
                continue
            movida = _mover_sucesora(sucesora, actual, dep)
            if movida:
                movidas.append(movida)
                cola.append(dep.successor_id)
    return movidas


def cascade_reschedule(task_id: str, new_end_date: date, db: Session) -> dict:
    """Propaga un cambio de fecha de fin a todas las sucesoras fin-a-inicio.

    El recorrido es en anchura y lleva un conjunto de visitadas: un grafo de
    dependencias puede tener ciclos, y sin eso esto giraría para siempre.
    """
    raiz = db.query(Task).filter(Task.id == task_id).first()
    if not raiz:
        raise HTTPException(404, "Tarea no encontrada")

    fin_anterior = raiz.due_date
    if not fin_anterior:
        raise HTTPException(400, "La tarea raíz no tiene fecha de fin definida")

    desplazamiento = new_end_date - fin_anterior
    if desplazamiento.days == 0:
        return {
            "rescheduled": [],
            "total_shifted": 0,
            "message": "No hay cambio de fecha — nada que replanificar",
        }

    raiz.due_date = new_end_date
    if raiz.start_date:
        raiz.start_date = raiz.start_date + desplazamiento

    replanificadas = [{
        "task_id": raiz.id,
        "title": raiz.title,
        "old_due_date": str(fin_anterior),
        "new_due_date": str(new_end_date),
        "shift_days": desplazamiento.days,
    }]

    replanificadas += _propagar_a_sucesoras(db, task_id)
    db.commit()
    return {"rescheduled": replanificadas, "total_shifted": len(replanificadas)}
