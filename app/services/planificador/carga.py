"""Carga por persona y semana a partir de las tareas (rev. 173).

La vista «Carga por persona» de Tareas y la pantalla de disponibilidad la
leen de aquí, con el mismo reparto que la nivelación (`nivelacion._horas_por_dia`):
las horas que quedan de cada tarea pendiente se reparten por igual entre sus
días laborables en el calendario de su persona (festivos y ausencias), y la
capacidad de cada semana es la suma de las horas de su horario efectivo
(rev. 180: turnos, jornada, festivos de su sede, ausencias también por horas).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core import timeutil
from app.models.task import Task, TaskStatus
from app.services.planificador.calendario import cargar_calendarios
from app.services.planificador.nivelacion import _horas_por_dia


def _lunes(d: date) -> date:
    return d - timedelta(days=d.weekday())


def carga_por_semana(db: Session, user, project_id: Optional[str] = None,
                     desde: Optional[date] = None, semanas: Optional[int] = None) -> dict:
    """{personas: [{user_id, name, weeks: [{week, capacity, hours, pct}]}]}.

    Con `project_id`, las personas son las de ese proyecto pero su carga cuenta
    **todas** sus tareas (una persona sobrecargada lo está por la suma); el
    detalle `project_hours` dice cuánto es de este proyecto.
    """
    from app.models.user import User
    from app.services.politica_de_visibilidad import ids_de_personas_visibles
    from app.services.settings_service import get_runtime_float, get_runtime_int

    org = getattr(user, "organization_id", None)
    semanas = max(1, semanas or get_runtime_int(db, "RESOURCE_AVAILABILITY_WEEKS", org) or 1)
    inicio = _lunes(desde or timeutil.today())
    fin = inicio + timedelta(weeks=semanas) - timedelta(days=1)

    if project_id:
        from app.services.planificador.servicio import proyecto_visible
        proyecto_visible(db, user, project_id)
        personas = {u for (u,) in db.query(Task.assignee_id).filter(
            Task.project_id == project_id, Task.assignee_id.isnot(None), Task.is_active.is_(True)).distinct()}
    else:
        personas = {u for (u,) in db.query(User.id).filter(User.organization_id == org, User.is_active.is_(True))}
    visibles = ids_de_personas_visibles(db, user)
    if visibles is not None:
        personas &= set(visibles)
    if not personas:
        return {"from": inicio.isoformat(), "weeks": semanas, "people": []}

    cal_empresa, cals = cargar_calendarios(db, org, personas, inicio)
    nombres = dict(db.query(User.id, User.full_name).filter(User.id.in_(personas)).all())
    umbral = (get_runtime_float(db, "LEVELING_OVERALLOCATION_PCT", org) or 100.0)
    bajo = (get_runtime_float(db, "RESOURCE_UNDERUSE_PCT", org) or 0.0)

    horas: dict = defaultdict(lambda: defaultdict(float))
    del_proyecto: dict = defaultdict(lambda: defaultdict(float))
    tareas = db.query(Task).filter(
        Task.assignee_id.in_(personas), Task.is_active.is_(True),
        Task.status.notin_((TaskStatus.done, TaskStatus.cancelled)),
        Task.start_date.isnot(None), Task.due_date.isnot(None),
        Task.start_date <= fin, Task.due_date >= inicio,
    ).all()
    for t in tareas:
        for d, h in _horas_por_dia(t, cals.get(t.assignee_id, cal_empresa), t.start_date, t.due_date).items():
            if inicio <= d <= fin:
                horas[t.assignee_id][_lunes(d)] += h
                if project_id and t.project_id == project_id:
                    del_proyecto[t.assignee_id][_lunes(d)] += h

    salida = []
    for uid in sorted(personas, key=lambda u: (nombres.get(u) or "")):
        c = cals.get(uid, cal_empresa)
        filas = []
        for i in range(semanas):
            lunes = inicio + timedelta(weeks=i)
            capacidad = c.horas_en(lunes, lunes + timedelta(days=6))
            h = horas[uid][lunes]
            pct = round(h / capacidad * 100, 1) if capacidad else None
            filas.append({"week": lunes.isoformat(), "capacity": round(capacidad, 1), "hours": round(h, 1),
                          "project_hours": round(del_proyecto[uid][lunes], 1) if project_id else None,
                          "pct": pct,
                          "state": "over" if pct is not None and pct > umbral else
                                   "under" if pct is not None and pct < bajo else "ok"})
        salida.append({"user_id": uid, "name": nombres.get(uid), "weeks": filas})
    return {"from": inicio.isoformat(), "weeks": semanas, "people": salida}
