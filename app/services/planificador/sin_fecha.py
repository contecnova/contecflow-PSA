"""Auto-planificar tareas sin fecha (19-11-2026).

Antes esto lo hacía un modelo de IA: tardaba ~25 s, si el proveedor fallaba
devolvía un plan vacío sin avisar, suponía 40 h/semana para todos y no veía
dependencias, festivos, ausencias ni la carga que cada persona ya tenía. Ahora
es el motor de planificación, determinista y en milisegundos:

1. Tareas sin fecha de inicio ni de fin, no terminadas ni canceladas, de los
   proyectos que el usuario ve (uno o todos los de su empresa).
2. Orden: las predecesoras antes que sus sucesoras (dependencias de
   planificación), y entre las libres por prioridad (crítica → baja) y
   antigüedad.
3. Horas de cada tarea: `estimated_hours` (lo que quede según su avance); si no
   hay, `story_points` × jornada de la empresa; si tampoco, una jornada.
4. Cada tarea se coloca en el calendario de SU responsable (horario efectivo:
   turnos, jornada, festivos de su sede, ausencias aprobadas, contrato de un
   externo; `calendario.cargar_calendarios`) llenando las horas libres de cada
   día, descontada la carga que ya tiene (tareas con fechas y lo que este mismo
   plan le va asignando) y con el tope `LEVELING_OVERALLOCATION_PCT`. Sin
   responsable, el calendario de la empresa sin tope de carga.
5. Nunca empieza antes de hoy ni antes de que acaben sus predecesoras.

Cada propuesta lleva el motivo en datos (horas, persona, días, si esperó a una
predecesora) para que la pantalla lo pinte en el idioma del usuario.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core import timeutil
from app.models.project import Project
from app.models.task import Task, TaskPriority, TaskStatus
from app.services.planificador.calendario import Calendario, cargar_calendarios
from app.services.planificador.servicio import vinculos_de

_FUERA = (TaskStatus.done, TaskStatus.cancelled)
_PRIORIDAD = {TaskPriority.critical: 0, TaskPriority.high: 1, TaskPriority.medium: 2, TaskPriority.low: 3}
#: Como mucho tantos días buscando hueco para una tarea (evita bucles sin fin
#: con un calendario sin horas).
_MAX_DIAS_DE_BUSQUEDA = 3 * 366


def _pendiente(t: Task, jornada: float) -> tuple[float, str]:
    """Horas que quedan y de dónde salen (`estimacion`, `puntos`, `jornada`)."""
    avance = max(0.0, min(100.0, float(getattr(t, "progress_pct", 0) or 0)))
    if t.estimated_hours and t.estimated_hours > 0:
        return round(t.estimated_hours * (1 - avance / 100), 2) or 0.5, "estimacion"
    if t.story_points and t.story_points > 0:
        return round(t.story_points * jornada * (1 - avance / 100), 2) or 0.5, "puntos"
    return jornada, "jornada"


def _orden(tareas: list[Task], vinculos) -> list[Task]:
    """Topológico (predecesoras primero) y, entre libres, prioridad y antigüedad."""
    por_id = {t.id: t for t in tareas}
    preds: dict[str, set[str]] = defaultdict(set)
    sucs: dict[str, set[str]] = defaultdict(set)
    for v in vinculos:
        if v.predecessor_id in por_id and v.successor_id in por_id:
            preds[v.successor_id].add(v.predecessor_id)
            sucs[v.predecessor_id].add(v.successor_id)

    def clave(t: Task):
        return (_PRIORIDAD.get(t.priority, 2), t.created_at or timeutil.utcnow(), t.id)

    listas = sorted((t for t in tareas if not preds[t.id]), key=clave)
    hechas: list[Task] = []
    faltan = {k: set(v) for k, v in preds.items()}
    while listas:
        t = listas.pop(0)
        hechas.append(t)
        for s in sorted(sucs[t.id]):
            faltan[s].discard(t.id)
            if not faltan[s]:
                listas.append(por_id[s])
                listas.sort(key=clave)
    # Un ciclo de dependencias no bloquea: lo que quede va al final por prioridad.
    resto = sorted((t for t in tareas if t not in hechas), key=clave)
    return hechas + resto


def _carga_actual(db: Session, user_ids: set[str], cals: dict[str, Calendario], desde: date) -> dict[str, dict[date, float]]:
    """Horas por persona y día de sus tareas que ya tienen fechas (desde hoy)."""
    carga: dict[str, dict[date, float]] = defaultdict(lambda: defaultdict(float))
    if not user_ids:
        return carga
    q = (db.query(Task)
         .filter(Task.assignee_id.in_(user_ids), Task.is_active.is_(True), Task.status.notin_(_FUERA),
                 Task.start_date.isnot(None), Task.due_date.isnot(None), Task.due_date >= desde))
    for t in q.all():
        cal = cals.get(t.assignee_id)
        if cal is None or not t.estimated_hours:
            continue
        avance = max(0.0, min(100.0, float(getattr(t, "progress_pct", 0) or 0)))
        restante = t.estimated_hours * (1 - avance / 100)
        dias, d = [], max(t.start_date, desde)
        while d <= t.due_date:
            if cal.es_laborable(d):
                dias.append(d)
            d += timedelta(days=1)
        total = sum(cal.horas(d) for d in dias)
        for d in dias:
            carga[t.assignee_id][d] += restante * (cal.horas(d) / total if total > 0 else 1 / len(dias))
    return carga


def proponer(db: Session, user, *, project_id: Optional[str] = None, max_tareas: int = 20) -> dict:
    """El plan propuesto (no guarda nada). Lo aplica `bulk-dates` desde la pantalla."""
    from app.services.planificador.servicio import proyecto_visible
    from app.services.settings_service import get_runtime_float
    from app.services.settings_service.por_empresa import jornada_de_empresa

    org = (db.info or {}).get("organization_id") or getattr(user, "organization_id", None)
    if project_id:
        proyectos = [proyecto_visible(db, user, project_id)]
    else:
        q = db.query(Project).filter(Project.is_active.is_(True)) if hasattr(Project, "is_active") else db.query(Project)
        if org:
            q = q.filter(Project.organization_id == org)
        proyectos = []
        for p in q.all():
            try:
                proyectos.append(proyecto_visible(db, user, p.id))
            except Exception:  # noqa: BLE001 — sin acceso a ese proyecto: no se planifica
                continue
    ids_proyecto = [p.id for p in proyectos]
    if not ids_proyecto:
        return {"scheduled": [], "unscheduled_count": 0, "message_code": "sin_tareas"}

    base = (db.query(Task)
            .filter(Task.project_id.in_(ids_proyecto), Task.is_active.is_(True), Task.status.notin_(_FUERA),
                    Task.start_date.is_(None), Task.due_date.is_(None)))
    total_sin_fecha = base.count()
    if not total_sin_fecha:
        return {"scheduled": [], "unscheduled_count": 0, "message_code": "sin_tareas"}

    hoy = timeutil.today()
    jornada = float(jornada_de_empresa(db, org) or 8.0)
    tope = (get_runtime_float(db, "LEVELING_OVERALLOCATION_PCT", org) or 100.0) / 100.0
    vinculos_todos = vinculos_de(db, {t.id for t in base.all()})
    tareas = _orden(base.all(), vinculos_todos)[:max(1, int(max_tareas))]
    elegidas = {t.id for t in tareas}
    vinculos = [v for v in vinculos_todos if v.predecessor_id in elegidas and v.successor_id in elegidas]
    preds: dict[str, list] = defaultdict(list)
    for v in vinculos:
        preds[v.successor_id].append(v)

    personas = {t.assignee_id for t in tareas if t.assignee_id}
    empresa, cals = cargar_calendarios(db, org, personas, hoy)
    carga = _carga_actual(db, personas, cals, hoy)
    nombres = {}
    if personas:
        from app.models.user import User
        nombres = {u.id: u.full_name for u in db.query(User).filter(User.id.in_(personas)).all()}

    fin_de: dict[str, date] = {}
    propuestas = []
    for t in tareas:
        cal = cals.get(t.assignee_id) if t.assignee_id else None
        cal = cal or empresa
        horas, origen = _pendiente(t, jornada)
        # No antes de hoy ni antes de que acaben (más su desfase) sus predecesoras.
        desde, espera = hoy, False
        for v in preds[t.id]:
            fin_pred = fin_de.get(v.predecessor_id)
            if fin_pred:
                # Como fin-inicio: el laborable siguiente a su fin más el desfase
                # (en laborables). Entre tareas sin fecha no hay otro tipo útil.
                minimo = cal.adelante(fin_pred, 1 + max(0, int(v.lag_days or 0)))
                if minimo > desde:
                    desde, espera = minimo, True
        d = cal.siguiente(desde)
        inicio = fin = None
        quedan, dias_usados = horas, 0
        for _ in range(_MAX_DIAS_DE_BUSQUEDA):
            if quedan <= 1e-6:
                break
            if cal.es_laborable(d):
                capacidad = cal.horas(d) * (tope if t.assignee_id else 1.0)
                usado = carga[t.assignee_id][d] if t.assignee_id else 0.0
                libre = max(0.0, capacidad - usado)
                if libre > 1e-6:
                    toma = min(libre, quedan)
                    if t.assignee_id:
                        carga[t.assignee_id][d] += toma
                    quedan -= toma
                    inicio = inicio or d
                    fin = d
                    dias_usados += 1
            d += timedelta(days=1)
        if inicio is None:  # sin hueco en el horizonte: se señala, no se inventa
            propuestas.append({"task_id": t.id, "title": t.title, "project_id": t.project_id,
                               "suggested_start": None, "suggested_due": None,
                               "motivo": {"codigo": "sin_hueco", "horas": horas}})
            continue
        fin_de[t.id] = fin
        propuestas.append({
            "task_id": t.id, "title": t.title, "project_id": t.project_id,
            "suggested_start": inicio.isoformat(), "suggested_due": fin.isoformat(),
            "priority": getattr(t.priority, "value", t.priority),
            "assignee_id": t.assignee_id, "assignee_name": nombres.get(t.assignee_id),
            "motivo": {"codigo": "planificada", "horas": round(horas, 2), "origen_horas": origen,
                       "dias": dias_usados, "espera_predecesora": espera,
                       "persona": nombres.get(t.assignee_id), "sin_responsable": not t.assignee_id},
        })
    return {"scheduled": propuestas, "unscheduled_count": total_sin_fecha,
            "message_code": "planificadas" if propuestas else "sin_tareas"}
