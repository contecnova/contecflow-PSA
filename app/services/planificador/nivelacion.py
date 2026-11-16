"""Nivelación de recursos: propone y aplica mover tareas dentro de su holgura.

Proyectos — planificador (16-11-2026). `/capacity/leveling` solo listaba planes
de capacidad y sugería «redistribuir» sin decir qué mover. Esto calcula la carga
diaria real de cada persona y propone retrasos concretos de tareas del proyecto:

  · **Carga**: cada tarea pendiente con persona, fechas y horas estimadas reparte
    sus horas por igual entre sus días laborables (calendario de la persona:
    festivos y ausencias aprobadas). Cuentan las tareas de **todos** los
    proyectos de la persona, no solo las de este: una persona sobrecargada lo
    está por la suma.
  · **Capacidad**: la jornada de la persona × `LEVELING_OVERALLOCATION_PCT`.
  · **Qué se mueve**: solo tareas de este proyecto, no terminadas, no críticas,
    y solo hacia delante. Cada retraso se comprueba contra **todas** sus
    sucesoras (los cuatro tipos con desfase, `cpm.inicio_minimo`) con las
    fechas que tengan en ese momento, contra su restricción (no terminar
    después de / debe terminar el) y contra su fin tardío del CPM. Mover una
    tarea más tarde nunca rompe a sus predecesoras.
  · **Heurística**: serie, las de más holgura primero; para cada una, el menor
    retraso que deja sus días sin sobrecarga, o si no existe, el que más horas
    de sobrecarga quita. Es la nivelación «dentro de la holgura» de MS Project:
    nunca alarga el proyecto.
  · Tareas sin horas estimadas no cargan (no se sabe cuánto pesan) y lo dice.

`proponer` no escribe nada; `aplicar` vuelve a calcular la propuesta en el
servidor y aplica las que se pidan (no se fía de fechas que mande el cliente).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.core import timeutil
from app.models.bookings import TaskDependency
from app.models.task import Task, TaskStatus
from app.services.planificador.calendario import Calendario, cargar_calendarios
from app.services.planificador.cpm import inicio_minimo

_ESTADOS_FUERA = (TaskStatus.done, TaskStatus.cancelled)


def _dias(cal: Calendario, inicio: date, fin: date) -> list[date]:
    out, d = [], inicio
    while d <= fin:
        if cal.es_laborable(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def _horas_por_dia(t: Task, cal: Calendario, inicio: date, fin: date) -> dict[date, float]:
    dias = _dias(cal, inicio, fin)
    if not dias or not t.estimated_hours:
        return {}
    restante = t.estimated_hours * (1 - (t.progress_pct or 0) / 100)
    reparto = max(restante, 0) / len(dias)
    return {d: reparto for d in dias}


def _sobrecarga(carga: dict, capacidad: float, dias: Iterable[date]) -> float:
    return sum(max(0.0, carga.get(d, 0.0) - capacidad) for d in dias)


def _umbral(db: Session, org_id: Optional[str]) -> tuple[float, int]:
    from app.services.settings_service import get_runtime_float, get_runtime_int
    pct = get_runtime_float(db, "LEVELING_OVERALLOCATION_PCT", org_id) or 100.0
    horizonte = get_runtime_int(db, "LEVELING_HORIZON_DAYS", org_id) or 0
    return pct / 100.0, max(1, horizonte)


def _calcular(db: Session, user, project_id: str) -> dict:
    from app.services.planificador.servicio import calcular_plan, proyecto_visible, tareas_planificables

    proyecto = proyecto_visible(db, user, project_id)
    plan = calcular_plan(db, user, project_id)          # guarda fin tardío y holguras al día
    tardios = {n["id"]: date.fromisoformat(n["late_finish"]) for n in plan["nodes"]}
    criticas = {n["id"] for n in plan["nodes"] if n["is_critical"]}
    org = proyecto.organization_id
    factor, horizonte = _umbral(db, org)
    hoy = timeutil.today()
    hasta = hoy + timedelta(days=horizonte)

    propias = tareas_planificables(db, project_id)
    personas = {t.assignee_id for t in propias if t.assignee_id}
    if not personas:
        return {"project_id": project_id, "moves": [], "overallocations_before": [],
                "overallocations_after": [], "skipped_without_estimate": 0}

    # Todas las tareas vivas de esas personas, en cualquier proyecto de la empresa.
    todas = (db.query(Task)
             .filter(Task.assignee_id.in_(personas), Task.is_active.is_(True),
                     Task.status.notin_(_ESTADOS_FUERA),
                     Task.start_date.isnot(None), Task.due_date.isnot(None),
                     Task.due_date >= hoy, Task.start_date <= hasta)
             .all())
    cal_empresa, por_persona = cargar_calendarios(db, org, personas, hoy)

    def cal(uid: Optional[str]) -> Calendario:
        return por_persona.get(uid, cal_empresa)

    carga: dict[str, dict[date, float]] = defaultdict(lambda: defaultdict(float))
    reparto: dict[str, dict[date, float]] = {}
    sin_estimar = 0
    for t in todas:
        r = _horas_por_dia(t, cal(t.assignee_id), t.start_date, t.due_date)
        if not r:
            sin_estimar += 1
            continue
        reparto[t.id] = r
        for d, h in r.items():
            carga[t.assignee_id][d] += h
    capacidad = {uid: cal(uid).horas_por_dia * factor for uid in personas}

    def sobrecargas() -> list[dict]:
        out = []
        for uid, dias in carga.items():
            for d, h in sorted(dias.items()):
                if hoy <= d <= hasta and h > capacidad[uid] + 1e-9:
                    out.append({"user_id": uid, "date": d.isoformat(), "hours": round(h, 2),
                                "capacity": round(capacidad[uid], 2)})
        return out

    antes = sobrecargas()

    por_id = {t.id: t for t in propias}
    deps = db.query(TaskDependency).filter(
        TaskDependency.predecessor_id.in_(list(por_id)), TaskDependency.is_active.is_(True),
        TaskDependency.link_type == "schedule").all()
    sucesoras: dict[str, list] = defaultdict(list)
    for d in deps:
        if d.successor_id in por_id:
            sucesoras[d.predecessor_id].append(d)

    def retraso_maximo(t: Task, c: Calendario, duracion: int) -> int:
        """Días laborables que la tarea puede retrasarse sin mover a nadie."""
        limite = tardios.get(t.id, t.due_date)
        if t.constraint_date and t.constraint_type in ("fnlt", "mfo"):
            limite = min(limite, t.constraint_date)
        if t.constraint_type == "mso":
            return 0
        maximo = max(0, c.distancia(t.due_date, c.anterior(limite)))
        for k in range(maximo, 0, -1):
            nuevo_ini = c.adelante(t.start_date, k)
            nuevo_fin = c.fin_desde(nuevo_ini, duracion)
            if all(_cumple(dep, nuevo_ini, nuevo_fin, c) for dep in sucesoras.get(t.id, [])):
                return k
        return 0

    def _cumple(dep, ini: date, fin: date, c: Calendario) -> bool:
        s = por_id[dep.successor_id]
        if not s.start_date or not s.due_date:
            return True
        cs = cal(s.assignee_id)
        dur_s = cs.duracion(s.start_date, s.due_date)
        minimo = inicio_minimo(str(getattr(dep.dependency_type, "value", dep.dependency_type) or "FS"),
                               int(dep.lag_days or 0), ini, fin, cal_empresa, cs, dur_s)
        return s.start_date >= minimo

    candidatas = [t for t in propias
                  if t.assignee_id and t.id in reparto and t.id not in criticas
                  and t.status not in _ESTADOS_FUERA and t.start_date and t.due_date]
    holgura = {n["id"]: n["total_float"] for n in plan["nodes"]}
    candidatas.sort(key=lambda t: (-(holgura.get(t.id) or 0), t.start_date))

    movimientos = []
    for t in candidatas:
        uid, c = t.assignee_id, cal(t.assignee_id)
        actuales = list(reparto[t.id])
        if _sobrecarga(carga[uid], capacidad[uid], actuales) <= 1e-9:
            continue
        duracion = c.duracion(t.start_date, t.due_date)
        maximo = retraso_maximo(t, c, duracion)
        if maximo <= 0:
            continue
        for d, h in reparto[t.id].items():          # se quita para medir sin ella
            carga[uid][d] -= h
        mejor_k, mejor_exceso = 0, _sobrecarga(
            {d: carga[uid].get(d, 0) + h for d, h in reparto[t.id].items()}, capacidad[uid], actuales)
        mejor_reparto = reparto[t.id]
        for k in range(1, maximo + 1):
            ini = c.adelante(t.start_date, k)
            fin = c.fin_desde(ini, duracion)
            r = _horas_por_dia(t, c, ini, fin)
            exceso = _sobrecarga({d: carga[uid].get(d, 0) + h for d, h in r.items()}, capacidad[uid], r)
            if exceso < mejor_exceso - 1e-9:
                mejor_k, mejor_exceso, mejor_reparto = k, exceso, r
            if exceso <= 1e-9:
                break
        for d, h in mejor_reparto.items():
            carga[uid][d] += h
        if mejor_k:
            ini = c.adelante(t.start_date, mejor_k)
            fin = c.fin_desde(ini, duracion)
            movimientos.append({
                "task_id": t.id, "code": t.code, "title": t.title, "assignee_id": uid,
                "old_start": t.start_date.isoformat(), "old_due": t.due_date.isoformat(),
                "new_start": ini.isoformat(), "new_due": fin.isoformat(),
                "delay_days": mejor_k, "max_delay_days": maximo,
            })
            reparto[t.id] = mejor_reparto
            t.start_date, t.due_date = ini, fin      # en memoria: las siguientes ven la nueva fecha

    despues = sobrecargas()
    return {
        "project_id": project_id,
        "moves": movimientos,
        "overallocations_before": antes,
        "overallocations_after": despues,
        "overallocated_hours_before": round(sum(o["hours"] - o["capacity"] for o in antes), 2),
        "overallocated_hours_after": round(sum(o["hours"] - o["capacity"] for o in despues), 2),
        "skipped_without_estimate": sin_estimar,
    }


def proponer(db: Session, user, project_id: str) -> dict:
    """La propuesta, sin escribir fechas (los cambios en memoria se descartan)."""
    try:
        return _calcular(db, user, project_id)
    finally:
        db.rollback()


def aplicar(db: Session, user, project_id: str, task_ids: Optional[list[str]] = None) -> dict:
    """Recalcula la propuesta y aplica los movimientos pedidos (todos si no se dice)."""
    from app.services.audit import audit_log
    from app.services.planificador.servicio import recalcular_si_procede

    propuesta = proponer(db, user, project_id)
    elegidos = [m for m in propuesta["moves"] if not task_ids or m["task_id"] in set(task_ids)]
    for m in elegidos:
        t = db.query(Task).filter(Task.id == m["task_id"], Task.project_id == project_id).first()
        if t is None:
            continue
        t.start_date = date.fromisoformat(m["new_start"])
        t.due_date = date.fromisoformat(m["new_due"])
    if elegidos:
        audit_log(db, user, "UPDATE", "resource_leveling", project_id, None,
                  new_values={"moved_tasks": [m["task_id"] for m in elegidos]})
    db.commit()
    recalcular_si_procede(db, project_id)
    return {**propuesta, "applied": elegidos, "total_applied": len(elegidos)}
