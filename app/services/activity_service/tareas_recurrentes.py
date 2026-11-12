"""Tareas recurrentes: definicion y materializacion de ocurrencias.

Parte de `app.services.activity_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.activity import RecurringTask, RecurringFreqType
from app.models.task import Task
from app.core import timeutil
from app.core.errores import ErrorDeDominio


TaskModel = Task


# ═══════════════════════════════════════════════════════════════════════════════
# RECURRING TASKS
# ═══════════════════════════════════════════════════════════════════════════════

def list_recurring_tasks_payload(
    db: Session,
    project_id: Optional[str],
    is_active: Optional[bool],
) -> list:
    q = db.query(RecurringTask)
    if project_id:
        q = q.filter(RecurringTask.project_id == project_id)
    if is_active is not None:
        q = q.filter(RecurringTask.is_active == is_active)
    rts = q.order_by(RecurringTask.start_date).all()
    return [{
        "id": r.id, "project_id": r.project_id, "title": r.title,
        "freq": r.freq, "interval_days": r.interval_days,
        "start_date": str(r.start_date), "end_date": str(r.end_date) if r.end_date else None,
        "last_generated": str(r.last_generated) if r.last_generated else None,
        "is_active": r.is_active, "priority": r.priority,
        "assignee_id": r.assignee_id, "due_offset_days": r.due_offset_days,
    } for r in rts]


def create_recurring_task_record(db: Session, payload, current_user: User) -> dict:
    try:
        RecurringFreqType(payload.freq)
    except ValueError:
        raise ErrorDeDominio(400, f"Invalid freq: {payload.freq}. Use: daily, weekly, monthly, custom")
    try:
        start = date.fromisoformat(payload.start_date)
    except ValueError:
        raise ErrorDeDominio(400, "start_date must be YYYY-MM-DD")
    end = date.fromisoformat(payload.end_date) if payload.end_date else None
    rt = RecurringTask(
        **{k: v for k, v in payload.model_dump().items() if k not in ("start_date", "end_date")},
        start_date=start,
        end_date=end,
        created_by=current_user.id,
    )
    db.add(rt)
    db.commit()
    db.refresh(rt)
    return {"id": rt.id, "title": rt.title}


def update_recurring_task_record(db: Session, rt_id: str, payload) -> dict:
    rt = db.query(RecurringTask).filter(RecurringTask.id == rt_id).first()
    if not rt:
        raise ErrorDeDominio(404)
    for k, v in payload.model_dump(exclude_unset=True).items():
        if k in ("start_date", "end_date"):
            v = date.fromisoformat(v) if v else None
        setattr(rt, k, v)
    db.commit()
    return {"ok": True}


def delete_recurring_task_record(db: Session, rt_id: str) -> dict:
    rt = db.query(RecurringTask).filter(RecurringTask.id == rt_id).first()
    if not rt:
        raise ErrorDeDominio(404)
    db.delete(rt)
    db.commit()
    return {"ok": True}


# ── Tareas recurrentes ───────────────────────────────────────────────────────
#
# Auditoría 2026-08 (hallazgo 18). `materialize_recurring_tasks_cmd` estaba en
# complejidad 16 y hacía cuatro cosas a la vez: numerar códigos, decidir qué
# días toca disparar, aplicar la máscara de días de la semana y crear filas.
# Separadas, la de decidir qué días toca es una **tabla de frecuencias** y las
# otras tres son de una línea cada una.

# Qué días dispara cada frecuencia, contando siempre desde `start_date`. Ojo a
# `monthly`: compara el número de día del mes, así que una recurrencia que
# empieza un día 31 **no dispara en febrero**. Es el comportamiento que había y
# no se cambia aquí —hacerlo es una decisión de producto (¿último día del mes?
# ¿el 28?)—, pero merece quedar escrito en vez de esconderse en un `elif`.
_DISPARA_EN = {
    RecurringFreqType.daily:   lambda rt, dia: True,
    RecurringFreqType.weekly:  lambda rt, dia: (dia - rt.start_date).days % 7 == 0,
    RecurringFreqType.monthly: lambda rt, dia: dia.day == rt.start_date.day,
    RecurringFreqType.custom:  lambda rt, dia: (
        (dia - rt.start_date).days % max(rt.interval_days, 1) == 0),
}


def _pasa_la_mascara_de_dias(rt, dia) -> bool:
    """La máscara de días de la semana, si la recurrencia tiene una.

    Es un mapa de bits con el lunes en el bit 0 (`date.weekday()`). Sin máscara
    —el caso normal— no filtra nada.
    """
    if not rt.weekday_mask:
        return True
    return bool(rt.weekday_mask & (1 << dia.weekday()))


def _ocurrencias_pendientes(rt, hoy) -> list:
    """Los días que esta recurrencia debería haber generado y no ha generado.

    Se recorre día a día desde el siguiente a `last_generated` —o al día
    anterior a `start_date` la primera vez— hasta hoy. Recorrer día a día en vez
    de saltar de ocurrencia en ocurrencia es deliberado: la máscara de días de
    la semana y el `monthly` por número de día no se expresan como un salto
    fijo, y el coste es proporcional a los días que el trabajo lleve sin correr.
    """
    ultima = rt.last_generated or (rt.start_date - timedelta(days=1))
    dia = ultima + timedelta(days=1)
    dispara = _DISPARA_EN.get(rt.freq)
    fechas = []
    while dia <= hoy:
        if dispara and dispara(rt, dia) and _pasa_la_mascara_de_dias(rt, dia):
            fechas.append(dia)
        dia += timedelta(days=1)
    return fechas


def _siguiente_codigo_de_tarea(session) -> str:
    """`TSK-00001`, `TSK-00002`… a partir del máximo que haya.

    Se conserva tal cual, con su carrera de condición incluida: dos procesos
    materializando a la vez pueden calcular el mismo número. La tabla tiene el
    código como único, así que el segundo falla en lugar de duplicar — que es
    exactamente lo que hace `create_task_record`, que captura el `IntegrityError`
    y devuelve 409. Aquí no hay quien lo reintente, y queda anotado.
    """
    import re as _re

    max_code = session.query(func.max(TaskModel.code)).scalar()
    if max_code:
        m = _re.search(r"(\d+)$", max_code)
        n = (int(m.group(1)) + 1) if m else 1
    else:
        n = 1
    return f"TSK-{n:05d}"


def _tarea_de_la_recurrencia(db: Session, rt, dia, current_user: User) -> None:
    """Crea la tarea de una ocurrencia y apunta la fecha en la recurrencia."""
    tarea = TaskModel(
        code=_siguiente_codigo_de_tarea(db),
        project_id=rt.project_id,
        title=f"{rt.title} [{dia.strftime('%d/%m/%Y')}]",
        description=rt.description,
        priority=rt.priority,
        assignee_id=rt.assignee_id,
        estimated_hours=rt.estimated_hours,
        story_points=rt.story_points,
        start_date=dia,
        due_date=dia + timedelta(days=rt.due_offset_days),
        created_by=current_user.id,
    )
    db.add(tarea)
    db.flush()
    rt.last_generated = dia


def materialize_recurring_tasks_cmd(db: Session, dry_run: bool, current_user: User) -> dict:
    hoy = timeutil.today()
    activas = db.query(RecurringTask).filter(
        RecurringTask.is_active == True,
        RecurringTask.start_date <= hoy,
    ).all()

    created = 0
    for rt in activas:
        # Una recurrencia caducada se desactiva aquí, y por eso el `dry_run` no
        # es del todo seco: esta escritura ocurre igual. Estaba así antes y se
        # conserva — el `commit` final sí que se salta, de modo que en `dry_run`
        # la desactivación se descarta con la sesión.
        if rt.end_date and rt.end_date < hoy:
            rt.is_active = False
            continue

        for dia in _ocurrencias_pendientes(rt, hoy):
            if not dry_run:
                _tarea_de_la_recurrencia(db, rt, dia, current_user)
            created += 1

    if not dry_run:
        db.commit()
    return {"ok": True, "dry_run": dry_run, "tasks_created": created}
