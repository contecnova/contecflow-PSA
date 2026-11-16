"""Camino crítico (CPM) con los cuatro tipos de vínculo, desfases, calendarios y restricciones.

Proyectos — planificador (16-11-2026). Sustituye al CPM de
`activity_service/planificacion.py`, que trataba todo vínculo como fin-inicio,
contaba días naturales como unidades abstractas y no conocía restricciones.

Todo es puro (sin base de datos): entra una lista de tareas con su calendario y
una lista de vínculos, y sale por tarea su inicio y fin temprano y tardío, la
holgura total y la libre. `servicio.py` es quien lee tablas y guarda.

Convenciones (las de MS Project con días enteros):

  · Una tarea de d días que empieza el día S termina el día F = S + (d-1)
    laborables; S y F son laborables de **su** calendario.
  · Los desfases se cuentan en días laborables del calendario del **proyecto**
    (la empresa); un desfase negativo es un solape.
  · FS: el sucesor empieza el laborable siguiente al fin del predecesor + desfase.
    SS: empieza en el inicio del predecesor + desfase.
    FF: termina en el fin del predecesor + desfase.
    SF: termina el laborable anterior al inicio del predecesor + desfase.
  · Restricciones: «no empezar antes de» (SNET), «debe empezar el» (MSO),
    «no terminar después de» (FNLT) y «debe terminar el» (MFO). Una fecha
    tardía por restricción puede dar **holgura negativa**: es la señal de que el
    plan no llega, y se enseña tal cual en vez de esconderla.
  · Un ciclo de dependencias es un dato malo, no una excepción: sus tareas se
    calculan al final ignorando los vínculos que cierran el ciclo y se devuelven
    en `ciclo` para que la pantalla lo diga.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from app.services.planificador.calendario import Calendario

TIPOS_DE_VINCULO = ("FS", "SS", "FF", "SF")
RESTRICCIONES = ("snet", "mso", "fnlt", "mfo")


@dataclass
class TareaPlan:
    id: str
    duracion: int                      # días laborables, >= 1
    calendario: Calendario
    inicio_fijado: Optional[date] = None   # ancla de una tarea sin predecesoras
    restriccion: Optional[str] = None      # snet | mso | fnlt | mfo
    fecha_restriccion: Optional[date] = None
    fijada: bool = False                   # terminada: sus fechas son reales y no se mueven
    inicio_real: Optional[date] = None
    fin_real: Optional[date] = None


@dataclass
class Vinculo:
    predecesora: str
    sucesora: str
    tipo: str = "FS"
    desfase: int = 0


@dataclass
class ResultadoTarea:
    inicio_temprano: date
    fin_temprano: date
    inicio_tardio: date
    fin_tardio: date
    holgura_total: int
    holgura_libre: int
    critica: bool


@dataclass
class ResultadoPlan:
    inicio_proyecto: date
    fin_proyecto: date
    tareas: dict[str, ResultadoTarea] = field(default_factory=dict)
    orden: list[str] = field(default_factory=list)
    ciclo: list[str] = field(default_factory=list)

    @property
    def camino_critico(self) -> list[str]:
        return [tid for tid in self.orden if self.tareas[tid].critica]


# ── Un vínculo, hacia delante y hacia atrás ──────────────────────────────────

def inicio_minimo(tipo: str, desfase: int, es_pred: date, ef_pred: date,
                  cal_proyecto: Calendario, cal_suc: Calendario, dur_suc: int) -> date:
    """El inicio más temprano que un vínculo permite a su sucesora."""
    if tipo == "SS":
        return cal_suc.siguiente(cal_proyecto.adelante(es_pred, desfase))
    if tipo == "FF":
        fin = cal_suc.siguiente(cal_proyecto.adelante(ef_pred, desfase))
        return cal_suc.inicio_desde(fin, dur_suc)
    if tipo == "SF":
        fin = cal_suc.siguiente(cal_proyecto.adelante(es_pred, desfase - 1))
        return cal_suc.inicio_desde(fin, dur_suc)
    # FS (y cualquier valor desconocido, que el modelo no deja guardar)
    return cal_suc.siguiente(cal_proyecto.adelante(ef_pred, desfase + 1))


def fin_maximo(tipo: str, desfase: int, ls_suc: date, lf_suc: date,
               cal_proyecto: Calendario, cal_pred: Calendario, dur_pred: int) -> date:
    """El fin más tardío que un vínculo permite a su predecesora sin retrasar a la sucesora."""
    if tipo == "SS":
        inicio = cal_pred.anterior(cal_proyecto.atras(ls_suc, desfase))
        return cal_pred.fin_desde(inicio, dur_pred)
    if tipo == "FF":
        return cal_pred.anterior(cal_proyecto.atras(lf_suc, desfase))
    if tipo == "SF":
        inicio = cal_pred.anterior(cal_proyecto.atras(lf_suc, desfase - 1))
        return cal_pred.fin_desde(inicio, dur_pred)
    return cal_pred.anterior(cal_proyecto.atras(ls_suc, desfase + 1))


# ── Orden ────────────────────────────────────────────────────────────────────

def _orden_topologico(ids: list[str], vinculos: list[Vinculo]) -> tuple[list[str], list[str]]:
    """Kahn. Lo que no entra por estar en un ciclo va al final y se devuelve aparte."""
    grado = {tid: 0 for tid in ids}
    sucesoras: dict[str, list[str]] = {tid: [] for tid in ids}
    for v in vinculos:
        grado[v.sucesora] += 1
        sucesoras[v.predecesora].append(v.sucesora)
    cola = [tid for tid in ids if grado[tid] == 0]
    orden: list[str] = []
    while cola:
        n = cola.pop(0)
        orden.append(n)
        for s in sucesoras[n]:
            grado[s] -= 1
            if grado[s] == 0:
                cola.append(s)
    vistos = set(orden)
    ciclo = [tid for tid in ids if tid not in vistos]
    return orden + ciclo, ciclo


# ── El cálculo ───────────────────────────────────────────────────────────────

def calcular(
    tareas: list[TareaPlan],
    vinculos: list[Vinculo],
    inicio_proyecto: date,
    cal_proyecto: Calendario,
    umbral_critico: float = 0.0,
) -> ResultadoPlan:
    """Pasada adelante, pasada atrás, holguras. Ver el docstring del módulo."""
    por_id = {t.id: t for t in tareas}
    vinculos = [v for v in vinculos
                if v.predecesora in por_id and v.sucesora in por_id and v.predecesora != v.sucesora]
    inicio_proyecto = cal_proyecto.siguiente(inicio_proyecto)
    if not tareas:
        return ResultadoPlan(inicio_proyecto=inicio_proyecto, fin_proyecto=inicio_proyecto)

    orden, ciclo = _orden_topologico([t.id for t in tareas], vinculos)
    posicion = {tid: i for i, tid in enumerate(orden)}
    preds: dict[str, list[Vinculo]] = {tid: [] for tid in por_id}
    sucs: dict[str, list[Vinculo]] = {tid: [] for tid in por_id}
    for v in vinculos:
        # Un vínculo que va «hacia atrás» en el orden cierra un ciclo: no se usa.
        if posicion[v.predecesora] < posicion[v.sucesora]:
            preds[v.sucesora].append(v)
            sucs[v.predecesora].append(v)

    es: dict[str, date] = {}
    ef: dict[str, date] = {}
    for tid in orden:
        t = por_id[tid]
        cal = t.calendario
        if t.fijada and t.inicio_real and t.fin_real:
            es[tid], ef[tid] = t.inicio_real, t.fin_real
            continue
        if preds[tid]:
            # Nada pendiente empieza antes que el proyecto, aunque su predecesora
            # (terminada, con fechas reales) acabara antes.
            inicio = max(
                cal.siguiente(inicio_proyecto),
                *(inicio_minimo(v.tipo, v.desfase, es[v.predecesora], ef[v.predecesora],
                                cal_proyecto, cal, t.duracion)
                  for v in preds[tid]),
            )
        else:
            inicio = cal.siguiente(max(inicio_proyecto, t.inicio_fijado or inicio_proyecto))
        if t.fecha_restriccion and t.restriccion == "snet":
            inicio = max(inicio, cal.siguiente(t.fecha_restriccion))
        elif t.fecha_restriccion and t.restriccion == "mso":
            inicio = cal.siguiente(t.fecha_restriccion)
        elif t.fecha_restriccion and t.restriccion == "mfo":
            inicio = cal.inicio_desde(t.fecha_restriccion, t.duracion)
        es[tid] = inicio
        ef[tid] = cal.fin_desde(inicio, t.duracion)

    fin_proyecto = max(ef.values())

    lf: dict[str, date] = {}
    ls: dict[str, date] = {}
    libre: dict[str, int] = {}
    for tid in reversed(orden):
        t = por_id[tid]
        cal = t.calendario
        fin = cal.anterior(fin_proyecto)
        fin_sin_mover_sucesoras = fin
        for v in sucs[tid]:
            fin = min(fin, fin_maximo(v.tipo, v.desfase, ls[v.sucesora], lf[v.sucesora],
                                      cal_proyecto, cal, t.duracion))
            fin_sin_mover_sucesoras = min(
                fin_sin_mover_sucesoras,
                fin_maximo(v.tipo, v.desfase, es[v.sucesora], ef[v.sucesora],
                           cal_proyecto, cal, t.duracion),
            )
        if t.fecha_restriccion and t.restriccion in ("fnlt", "mfo"):
            fin = min(fin, cal.anterior(t.fecha_restriccion))
        elif t.fecha_restriccion and t.restriccion == "mso":
            fin = min(fin, cal.fin_desde(t.fecha_restriccion, t.duracion))
        lf[tid] = fin
        ls[tid] = cal.inicio_desde(fin, t.duracion)
        libre[tid] = cal.distancia(ef[tid], fin_sin_mover_sucesoras)

    resultado = ResultadoPlan(inicio_proyecto=inicio_proyecto, fin_proyecto=fin_proyecto,
                              orden=orden, ciclo=ciclo)
    for tid in orden:
        t = por_id[tid]
        total = t.calendario.distancia(es[tid], ls[tid])
        resultado.tareas[tid] = ResultadoTarea(
            inicio_temprano=es[tid], fin_temprano=ef[tid],
            inicio_tardio=ls[tid], fin_tardio=lf[tid],
            holgura_total=total,
            holgura_libre=min(libre[tid], total) if not t.fijada else 0,
            critica=(not t.fijada) and total <= umbral_critico,
        )
    return resultado
