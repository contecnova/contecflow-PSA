"""
tasks/scheduling.py — Date/dependency cascade logic for tasks.

Exports:
    cascade_reschedule
"""
from __future__ import annotations

from collections import deque
from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.bookings import TaskDependency, DependencyType
from app.models.task import Task


def cascade_reschedule(task_id: str, new_end_date: date, db: Session) -> dict:
    """
    Propagate a due-date shift to all FS successor tasks via BFS.
    Returns rescheduled task list + total count.
    """
    root_task = db.query(Task).filter(Task.id == task_id).first()
    if not root_task:
        raise HTTPException(404, "Tarea no encontrada")

    old_end = root_task.due_date
    if not old_end:
        raise HTTPException(400, "La tarea raíz no tiene fecha de fin definida")

    delta = new_end_date - old_end
    if delta.days == 0:
        return {
            "rescheduled": [],
            "total_shifted": 0,
            "message": "No hay cambio de fecha — nada que replanificar",
        }

    root_task.due_date = new_end_date
    if root_task.start_date:
        root_task.start_date = root_task.start_date + delta
    rescheduled = [{
        "task_id": root_task.id,
        "title": root_task.title,
        "old_due_date": str(old_end),
        "new_due_date": str(new_end_date),
        "shift_days": delta.days,
    }]

    visited = {task_id}
    queue: deque = deque([task_id])

    while queue:
        current_id = queue.popleft()
        current_task = db.query(Task).filter(Task.id == current_id).first()
        if not current_task or not current_task.due_date:
            continue

        deps = db.query(TaskDependency).filter(
            TaskDependency.predecessor_id == current_id,
            TaskDependency.dependency_type == DependencyType.finish_to_start,
        ).all()

        for dep in deps:
            succ_id = dep.successor_id
            if succ_id in visited:
                continue
            visited.add(succ_id)
            succ = db.query(Task).filter(Task.id == succ_id).first()
            if not succ:
                continue

            lag = timedelta(days=dep.lag_days or 0)
            new_start = current_task.due_date + timedelta(days=1) + lag
            if succ.start_date and succ.due_date:
                duration = succ.due_date - succ.start_date
                old_due = succ.due_date
                succ.start_date = new_start
                succ.due_date = new_start + duration
            elif succ.due_date:
                old_due = succ.due_date
                shift_here = new_start - (succ.start_date or succ.due_date)
                succ.due_date = succ.due_date + shift_here
            else:
                continue

            rescheduled.append({
                "task_id": succ.id,
                "title": succ.title,
                "old_due_date": str(old_due),
                "new_due_date": str(succ.due_date),
                "shift_days": (succ.due_date - old_due).days,
            })
            queue.append(succ_id)

    db.commit()
    return {"rescheduled": rescheduled, "total_shifted": len(rescheduled)}
