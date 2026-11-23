"""Valor ganado (EVM): un solo cálculo, sobre la línea base y el avance real.

Proyectos — planificador (16-11-2026). Había tres implementaciones
(`project_service.evm`, `portfolio_service.get_evm_quick` y
`profitability_service._indicadores_evm`) con dos defectos comunes:

  · el **PV** era lineal entre el inicio y el fin del proyecto: un proyecto que
    concentra el trabajo al final salía «retrasado» desde el primer día;
  · el **EV** solo contaba tareas terminadas: una tarea al 90 % valía cero.

Ahora:

  · **BAC**: el coste planificado de la línea base vigente (horas × coste/hora
    de la persona al congelar); si la línea base no tiene costes, el
    presupuesto del proyecto; si tampoco, horas estimadas × tarifa media
    imputada (el respaldo de antes).
  · **Presupuesto de cada tarea**: su parte del BAC, por su coste planificado
    o, sin él, por sus horas estimadas.
  · **PV a una fecha**: cada tarea reparte su presupuesto por igual entre los
    días laborables de su ventana **en la línea base** (calendario de la
    empresa). Sin línea base, con las fechas del plan de hoy (y se dice en
    `pv_source`).
  · **EV**: presupuesto de cada tarea × su avance real (`progress_pct`;
    terminada = 100 %).
  · **AC**: coste real del cálculo único (`margen_de_proyectos`, el de
    rentabilidad): imputaciones activas convertidas + gastos + subcontrata + ALM.

`indicadores()` son las fórmulas (CPI, SPI, CV, SV, EAC, ETC, VAC, TCPI) y es lo
único que usan las otras dos pantallas. La curva S histórica sale de
`evm_snapshots`, que el worker rellena cada día.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core import timeutil
from app.models.marketplace import GanttBaseline, GanttBaselineTask
from app.models.project import Project, ProjectStatus
from app.models.task import Task, TaskStatus


@dataclass(slots=True)
class Indicadores:
    bac: float
    pv: Optional[float]
    ev: float
    ac: float
    cpi: Optional[float]
    spi: Optional[float]
    cv: float
    sv: Optional[float]
    eac: float
    etc: float
    vac: float
    tcpi: Optional[float]


def indicadores(bac: float, pv: Optional[float], ev: float, ac: float,
                pct_complete: Optional[float] = None) -> Indicadores:
    """Las fórmulas estándar del PMBOK. Sin CPI (AC = 0) la EAC es el BAC, salvo
    que haya avance: entonces se extrapola el coste por el avance."""
    cpi = round(ev / ac, 4) if ac > 0 else None
    spi = round(ev / pv, 4) if (pv is not None and pv > 0) else None
    if cpi and cpi > 0:
        eac = round(ac + (bac - ev) / cpi, 2)
    elif pct_complete and pct_complete >= 1 and ac > 0:
        eac = round(ac / (pct_complete / 100), 2)
    else:
        eac = round(bac, 2)
    resto = bac - ac
    tcpi = round((bac - ev) / resto, 4) if resto != 0 else None
    return Indicadores(
        bac=round(bac, 2), pv=round(pv, 2) if pv is not None else None, ev=round(ev, 2), ac=round(ac, 2),
        cpi=cpi, spi=spi, cv=round(ev - ac, 2), sv=round(ev - pv, 2) if pv is not None else None,
        eac=eac, etc=round(max(eac - ac, 0), 2), vac=round(bac - eac, 2), tcpi=tcpi,
    )


# ── Datos de un proyecto ─────────────────────────────────────────────────────

@dataclass
class _Partida:
    task_id: str
    presupuesto: float
    inicio: Optional[date]
    fin: Optional[date]
    avance: float          # 0-1


def coste_real(db: Session, project_id: str, proyecto: Optional[Project] = None) -> float:
    """AC: personal + gastos + subcontrata + licencias y equipos (ALM), en la moneda de la empresa.

    Auditoría 22-11-2026 (M6, §7.2): el cálculo único (`margen_de_proyectos`):
    solo imputaciones activas, cada una convertida a la moneda de la empresa
    con el tipo de su fecha (y horas × tarifa congelada si no tiene coste).
    Antes sumaba borradas y monedas mezcladas, y no coincidía con rentabilidad.
    """
    from app.services.margen_de_proyectos import margen_en_bloque
    proyecto = proyecto or db.get(Project, project_id)
    if proyecto is None:
        return 0.0
    return float(margen_en_bloque(db, [proyecto])[proyecto.id]["total_cost"])


#: Avance que se supone a una tarea **sin** `progress_pct` declarado, por su
#: estado. Una tarea en revisión está más cerca de acabada que una en curso.
#: Es la única tabla de pesos (antes vivía en rentabilidad, que ahora la importa).
PESO_DE_PROGRESO_POR_ESTADO = {
    TaskStatus.done: 1.0,
    TaskStatus.in_review: 0.8,
    TaskStatus.in_progress: 0.5,
    TaskStatus.todo: 0.0,
    TaskStatus.backlog: 0.0,
    TaskStatus.blocked: 0.0,
    TaskStatus.cancelled: 0.0,
}


def _avance(t: Task) -> float:
    """Avance real de 0 a 1: terminada = 1; si no, el % declarado; si no hay,
    el peso de su estado."""
    if str(getattr(t.status, "value", t.status)) == TaskStatus.done.value:
        return 1.0
    if t.progress_pct is not None:
        return max(0.0, min(100.0, t.progress_pct)) / 100.0
    return PESO_DE_PROGRESO_POR_ESTADO.get(t.status, 0.0)


def _partidas(db: Session, proyecto: Project) -> tuple[list[_Partida], float, str, Optional[str]]:
    """Presupuesto por tarea, BAC, de dónde sale el PV y la línea base usada."""
    tareas = {t.id: t for t in db.query(Task).filter(
        Task.project_id == proyecto.id, Task.is_active.is_(True), Task.status != TaskStatus.cancelled).all()}
    base = (db.query(GanttBaseline)
            .filter(GanttBaseline.project_id == proyecto.id, GanttBaseline.is_current.is_(True)).first())
    filas = (db.query(GanttBaselineTask).filter(GanttBaselineTask.baseline_id == base.id).all()
             if base else [])

    if filas:
        coste_base = sum(f.planned_cost or 0 for f in filas)
        horas_base = sum(f.estimated_hours or 0 for f in filas)
        bac = coste_base or proyecto.budget_amount or _bac_de_respaldo(db, proyecto, horas_base)
        partidas = []
        for f in filas:
            peso = ((f.planned_cost or 0) / coste_base) if coste_base else (
                ((f.estimated_hours or 0) / horas_base) if horas_base else 1 / len(filas))
            t = tareas.get(f.task_id)
            partidas.append(_Partida(f.task_id, bac * peso, f.start_date, f.end_date, _avance(t) if t else 0.0))
        return _con_ventana_del_proyecto(partidas, proyecto), bac, "baseline", base.id

    horas = sum(t.estimated_hours or 0 for t in tareas.values())
    bac = proyecto.budget_amount or _bac_de_respaldo(db, proyecto, horas)
    n = len(tareas) or 1
    partidas = [_Partida(t.id, bac * (((t.estimated_hours or 0) / horas) if horas else 1 / n),
                         t.start_date, t.due_date, _avance(t)) for t in tareas.values()]
    return _con_ventana_del_proyecto(partidas, proyecto), bac, "current_plan", None


def _con_ventana_del_proyecto(partidas: list[_Partida], proyecto: Project) -> list[_Partida]:
    """Una tarea sin fechas se planifica repartida por toda la ventana del
    proyecto (inicio → fin previsto): es lo que el PV lineal de antes suponía
    para todo el proyecto, y ahora solo para lo que no tiene fechas."""
    if proyecto.start_date and proyecto.end_date_planned and proyecto.end_date_planned >= proyecto.start_date:
        for p in partidas:
            if not (p.inicio and p.fin):
                p.inicio, p.fin = proyecto.start_date, proyecto.end_date_planned
    return partidas


def _bac_de_respaldo(db: Session, proyecto: Project, horas: float) -> float:
    """Sin presupuesto: horas estimadas × tarifa media imputada (lo de siempre)."""
    from app.models.imputation import Imputation
    tarifa = db.query(func.avg(Imputation.hourly_rate_snapshot)).filter(
        Imputation.project_id == proyecto.id, Imputation.hourly_rate_snapshot.isnot(None)).scalar() or 0.0
    return (horas or 0) * tarifa


def _pv_a(partidas: list[_Partida], dia: date, cal) -> Optional[float]:
    """Valor planificado a fecha `dia`. None si ninguna partida tiene fechas."""
    con_fechas = [p for p in partidas if p.inicio and p.fin]
    if not con_fechas:
        return None
    pv = 0.0
    for p in con_fechas:
        if dia >= p.fin:
            pv += p.presupuesto
        elif dia >= p.inicio:
            total = cal.laborables_en(p.inicio, p.fin) or 1
            pv += p.presupuesto * cal.laborables_en(p.inicio, dia) / total
    return pv


def evm_de_proyecto(db: Session, proyecto: Project, *, dia: Optional[date] = None,
                    ac: Optional[float] = None) -> dict:
    """El valor ganado de un proyecto a una fecha (hoy por defecto).

    `ac` permite a rentabilidad pasar el coste de su rango de fechas.
    """
    from app.services.planificador.calendario import calendario_de_empresa

    dia = dia or timeutil.today()
    partidas, bac, fuente, base_id = _partidas(db, proyecto)
    cal = calendario_de_empresa(db, proyecto.organization_id)
    pv = _pv_a(partidas, dia, cal)
    ev = sum(p.presupuesto * p.avance for p in partidas)
    ac = coste_real(db, proyecto.id, proyecto) if ac is None else ac
    pct_complete = (ev / bac * 100) if bac else (
        sum(p.avance for p in partidas) / len(partidas) * 100 if partidas else 0.0)
    pct_planned = (pv / bac * 100) if (bac and pv is not None) else None
    ind = indicadores(bac, pv, ev, ac, pct_complete)
    return {
        "bac": ind.bac, "pv": ind.pv, "ev": ind.ev, "ac": ind.ac,
        "cpi": ind.cpi, "spi": ind.spi, "cv": ind.cv, "sv": ind.sv,
        "eac": ind.eac, "etc": ind.etc, "vac": ind.vac, "tcpi": ind.tcpi,
        "pct_complete": round(pct_complete, 1),
        "pct_planned": round(pct_planned, 1) if pct_planned is not None else None,
        "pv_source": fuente,
        "baseline_id": base_id,
        "has_schedule": pv is not None,
        "_partidas": partidas,
    }


# ── Curva S ──────────────────────────────────────────────────────────────────

def guardar_punto(db: Session, proyecto: Project, dia: Optional[date] = None) -> None:
    """Un punto de la curva S (uno por proyecto y día: si ya existe, se pisa)."""
    from app.models.planificacion import EvmSnapshot

    dia = dia or timeutil.today()
    d = evm_de_proyecto(db, proyecto, dia=dia)
    fila = (db.query(EvmSnapshot)
            .filter(EvmSnapshot.project_id == proyecto.id, EvmSnapshot.snapshot_date == dia).first())
    if fila is None:
        fila = EvmSnapshot(organization_id=proyecto.organization_id, project_id=proyecto.id, snapshot_date=dia)
        db.add(fila)
        # La sesion no hace autoflush: sin esto, un segundo punto del mismo dia en la
        # misma transaccion no ve el primero y choca con la unica (proyecto, dia).
        db.flush()
    fila.baseline_id = d["baseline_id"]
    fila.bac, fila.pv, fila.ev, fila.ac = d["bac"], d["pv"], d["ev"], d["ac"]
    fila.cpi, fila.spi = d["cpi"], d["spi"]
    fila.pct_complete, fila.pct_planned = d["pct_complete"], d["pct_planned"]


def guardar_puntos_de_la_organizacion(db: Session, org_id: Optional[str]) -> dict:
    """Trabajo diario del worker: un punto por proyecto activo o en pausa."""
    from app.services.settings_service import get_runtime_bool
    if not get_runtime_bool(db, "EVM_SNAPSHOTS_ENABLED", org_id):
        return {"skipped": "EVM_SNAPSHOTS_ENABLED desactivado"}
    proyectos = db.query(Project).filter(
        Project.organization_id == org_id,
        Project.status.in_([ProjectStatus.active, ProjectStatus.on_hold]),
        Project.is_active.is_(True)).all()
    for p in proyectos:
        guardar_punto(db, p)
    db.commit()
    return {"projects": len(proyectos)}


def curva_s(db: Session, user, project_id: str) -> dict:
    """Histórico (PV, EV, AC reales de cada día guardado) y el PV previsto de la
    línea base hasta su fin, semana a semana, para dibujar la curva completa."""
    from app.models.planificacion import EvmSnapshot
    from app.services.planificador.calendario import calendario_de_empresa
    from app.services.planificador.servicio import proyecto_visible
    from app.services.settings_service import get_runtime_int

    proyecto = proyecto_visible(db, user, project_id)
    tope = get_runtime_int(db, "EVM_CURVE_MAX_POINTS", proyecto.organization_id) or 0
    filas = (db.query(EvmSnapshot).filter(EvmSnapshot.project_id == project_id)
             .order_by(EvmSnapshot.snapshot_date.desc()).limit(max(1, tope)).all())
    historico = [{
        "date": f.snapshot_date.isoformat(), "pv": f.pv, "ev": f.ev, "ac": f.ac,
        "cpi": f.cpi, "spi": f.spi, "pct_complete": f.pct_complete, "pct_planned": f.pct_planned,
    } for f in reversed(filas)]

    hoy_d = evm_de_proyecto(db, proyecto)
    partidas = hoy_d.pop("_partidas")
    cal = calendario_de_empresa(db, proyecto.organization_id)
    fechas = [p.inicio for p in partidas if p.inicio] + [p.fin for p in partidas if p.fin]
    plan = []
    if fechas:
        d, fin = min(fechas), max(fechas)
        while d <= fin + timedelta(days=6):
            plan.append({"date": d.isoformat(), "pv": round(_pv_a(partidas, d, cal) or 0, 2)})
            d += timedelta(days=7)
    return {"project_id": project_id, "today": {k: v for k, v in hoy_d.items()},
            "history": historico, "planned": plan}


def guardar_punto_de_hoy(db: Session, proyecto: Project) -> None:
    """«Guardar hoy un punto de la curva S» desde la pantalla: guarda y confirma."""
    guardar_punto(db, proyecto)
    db.commit()
