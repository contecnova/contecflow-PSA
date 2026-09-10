"""Líneas base del Gantt: congelar un cronograma y comparar contra él.

Auditoría 2026-08 (hallazgo 22). Estas operaciones vivían en
`endpoints/baselines.py` con **nueve consultas y escrituras directas**, y al
bajarlas apareció lo mismo que en el resto del hallazgo: los cuatro endpoints
anclan en `project_id` y **ninguno comprobaba de quién es el proyecto**.

Todo lo demás cuelga de ahí —las líneas base se buscan por `project_id`, las
tareas también—, así que el proyecto es el único punto donde la tenencia se
puede verificar, y era el que faltaba. Lo único que lo impedía era el filtro
implícito de `TenantSession`, que es una red de seguridad y no una guarda.

Un cronograma congelado lleva el presupuesto del proyecto en el momento de
congelarlo (`budget_at_freeze`) y las horas estimadas de cada tarea: no es
metadato inocuo.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core import timeutil
from app.models.marketplace import GanttBaseline
from app.models.project import Project
from app.models.task import Task

#: Estados que cuentan como tarea terminada al congelar. Se comparan por su
#: valor de texto porque el modelo usa un `Enum` y el histórico trae cadenas.
ESTADOS_TERMINADOS = ("done", "closed", "completed")


def _org_de(user) -> Optional[str]:
    return getattr(user, "organization_id", None)


def _texto_de_estado(tarea: Task) -> str:
    return str(getattr(tarea.status, "value", tarea.status))


def proyecto_propio(db: Session, user, project_id: str) -> Project:
    """El proyecto, si es de la organización del usuario. 404 si no.

    Es la guarda que faltaba, y la única posible: las líneas base y las tareas
    se buscan por `project_id`, así que si el proyecto no se comprueba no se
    comprueba nada.
    """
    fila = (
        db.query(Project)
        .filter(Project.id == project_id, Project.organization_id == _org_de(user))
        .first()
    )
    if not fila:
        raise HTTPException(404, "Project not found")
    return fila


def linea_base_propia(db: Session, user, project_id: str, baseline_id: str) -> GanttBaseline:
    """Una línea base de un proyecto ya comprobado.

    El proyecto se verifica primero; después el filtro por `project_id` basta,
    porque el ámbito llega por la clave padre.
    """
    proyecto_propio(db, user, project_id)
    fila = (
        db.query(GanttBaseline)
        .filter(
            GanttBaseline.id == baseline_id,
            GanttBaseline.project_id == project_id,
        )
        .first()
    )
    if not fila:
        raise HTTPException(404, "Baseline not found")
    return fila


def list_baselines(db: Session, user, project_id: str) -> list[GanttBaseline]:
    proyecto_propio(db, user, project_id)
    return (
        db.query(GanttBaseline)
        .filter(GanttBaseline.project_id == project_id)
        .order_by(GanttBaseline.baseline_date.desc())
        .all()
    )


def _fotografia_del_cronograma(tareas: list[Task]) -> dict:
    """La foto que se congela: una entrada por tarea con sus fechas y horas."""
    return {
        "frozen_at": str(timeutil.today()),
        "tasks": [
            {
                "task_id": t.id,
                "title": t.title,
                "start": str(t.start_date) if getattr(t, "start_date", None) else None,
                "end": str(t.due_date) if t.due_date else None,
                "progress": getattr(t, "progress", 0),
                "status": _texto_de_estado(t),
                "estimated_hours": getattr(t, "estimated_hours", None),
                "assignee_id": getattr(t, "assignee_id", None),
            }
            for t in tareas
        ],
    }


def crear_linea_base(
    db: Session, user, project_id: str, *,
    name: str, description: Optional[str], is_initial: bool,
) -> GanttBaseline:
    """Congela el cronograma actual del proyecto como línea base."""
    proyecto = proyecto_propio(db, user, project_id)
    tareas = db.query(Task).filter(Task.project_id == project_id).all()

    horas = sum(t.estimated_hours or 0 for t in tareas
                if getattr(t, "estimated_hours", None))
    terminadas = sum(1 for t in tareas if _texto_de_estado(t) in ESTADOS_TERMINADOS)

    fila = GanttBaseline(
        organization_id=_org_de(user),
        project_id=project_id,
        name=name,
        description=description,
        baseline_date=timeutil.today(),
        schedule_snapshot=json.dumps(_fotografia_del_cronograma(tareas)),
        total_tasks=len(tareas),
        completed_tasks=terminadas,
        total_hours=horas,
        # `Project` NO tiene columna `budget`: la de dinero es `budget_amount`.
        # El endpoint leia `proj.budget if hasattr(proj, "budget") else None`, y
        # ese `hasattr` tapaba el nombre equivocado, asi que `budget_at_freeze`
        # ha sido **siempre None** y la comparacion contra la linea base nunca
        # pudo mostrar desvio de presupuesto. Auditoria 2026-08.
        budget_at_freeze=proyecto.budget_amount,
        is_initial=is_initial,
        created_by=user.id,
    )
    db.add(fila)
    db.commit()
    db.refresh(fila)
    return fila


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


def comparar_con_linea_base(db: Session, user, project_id: str, baseline_id: str) -> dict:
    """Compara el cronograma de hoy contra el congelado."""
    linea = linea_base_propia(db, user, project_id, baseline_id)

    congelado = json.loads(linea.schedule_snapshot)
    tareas_congeladas = {t["task_id"]: t for t in congelado.get("tasks", [])}
    tareas_actuales = db.query(Task).filter(Task.project_id == project_id).all()

    deltas = []
    for t in tareas_actuales:
        anterior = tareas_congeladas.get(t.id)
        if not anterior:
            deltas.append({"task_id": t.id, "title": t.title, "delta": "new_task"})
            continue
        fin_actual = str(t.due_date) if t.due_date else None
        deltas.append({
            "task_id": t.id,
            "title": t.title,
            "baseline_end": anterior.get("end"),
            "current_end": fin_actual,
            "slip_days": _dias_de_desvio(fin_actual, anterior.get("end")),
            "baseline_status": anterior.get("status"),
            "current_status": _texto_de_estado(t),
            "baseline_hours": anterior.get("estimated_hours"),
            "current_hours": getattr(t, "estimated_hours", None),
        })

    ids_actuales = {t.id for t in tareas_actuales}
    borradas = [
        {"task_id": tid, "delta": "removed"}
        for tid in tareas_congeladas if tid not in ids_actuales
    ]

    desviadas = sum(1 for d in deltas if (d.get("slip_days") or 0) > 0)
    desvio_medio = sum(d.get("slip_days") or 0 for d in deltas) / max(len(deltas), 1)

    return {
        "baseline_id": baseline_id,
        "baseline_name": linea.name,
        "baseline_date": str(linea.baseline_date),
        "summary": {
            "tasks_compared": len(deltas),
            "tasks_slipped": desviadas,
            "avg_slip_days": round(desvio_medio, 1),
            "tasks_removed": len(borradas),
            "tasks_added": sum(1 for d in deltas if d.get("delta") == "new_task"),
        },
        "task_deltas": deltas + borradas,
    }


def borrar_linea_base(db: Session, user, project_id: str, baseline_id: str) -> None:
    fila = linea_base_propia(db, user, project_id, baseline_id)
    db.delete(fila)
    db.commit()
