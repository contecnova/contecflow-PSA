"""Calendario laboral: qué días se trabaja y cuántas horas.

Proyectos — planificador (16-11-2026). El camino crítico de antes contaba días
naturales y dividía las horas entre un 8 escrito en el código. Ahora cada tarea
se planifica con el calendario de quien la hace:

  · **empresa**: días laborables del ajuste `PLANNING_WORKDAYS`, jornada de
    `DEFAULT_WORKING_HOURS_PER_DAY` y los festivos de Configuración › Festivos
    que valen para todos (los que no llevan `applies_to`);
  · **persona** (rev. 180): su HORARIO EFECTIVO día a día
    (`app/services/horario`): el turno del cuadrante o de su rotación (mañana,
    tarde, noche, partido, que cruza la medianoche), su jornada asignada
    (verano, reducida… con vigencia) o la de la empresa; menos los festivos de
    la empresa y de SU SEDE, sus ausencias **aprobadas** (también por horas:
    un día con dos horas de permiso tiene dos horas menos) y los días fuera de
    contrato de un externo. Se calcula para `PLANNING_SCHEDULE_HORIZON_DAYS`
    días desde el inicio; más allá, el patrón de la empresa con su jornada
    media.

La clase es pura —sin base de datos— para que el CPM y sus tests no dependan de
nada; `cargar_calendarios` es lo único que lee tablas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable, Mapping, Optional

from sqlalchemy.orm import Session

from app.core import timeutil
from app.core.codigos_de_error import ErrorConCodigo, desde_valor


def interpretar_dias_laborables(texto: Optional[str]) -> frozenset[int]:
    """«1,2,3,4,5» → {1..5}. Valores fuera de 1-7 o ilegibles se descartan.

    Un calendario sin ningún día laborable no se puede usar (ninguna tarea
    terminaría nunca): se rechaza aquí y no en mitad de un cálculo.
    """
    dias = set()
    for trozo in (texto or "").replace(";", ",").split(","):
        trozo = trozo.strip()
        if trozo.isdigit() and 1 <= int(trozo) <= 7:
            dias.add(int(trozo))
    if not dias:
        raise ErrorConCodigo("error_interno", detail="PLANNING_WORKDAYS no tiene ningún día laborable válido (1-7)")
    return frozenset(dias)


@dataclass(frozen=True)
class Calendario:
    """Días laborables (ISO), días sueltos que no se trabajan y jornada.

    `horas_por_fecha` (rev. 180) manda en los días que trae: las horas que se
    trabajan ESE día (0 = no laborable), del horario efectivo de la persona.
    Fuera de ellos, el patrón (`dias_laborables`, `no_laborables`,
    `horas_por_dia`). `horas_por_dia` es la jornada media (estimaciones en días).
    """

    dias_laborables: frozenset[int]
    no_laborables: frozenset[date] = field(default_factory=frozenset)
    horas_por_dia: float = 8.0
    horas_por_fecha: Mapping[date, float] = field(default_factory=dict, compare=False, hash=False)

    def __post_init__(self) -> None:
        if not self.dias_laborables:
            raise ErrorConCodigo("calendario_sin_dias_laborables")
        if self.horas_por_dia <= 0:
            raise ErrorConCodigo("jornada_mayor_que_cero")

    # ── Consultas de un día ──────────────────────────────────────────────────
    def es_laborable(self, d: date) -> bool:
        h = self.horas_por_fecha.get(d)
        if h is not None:
            return h > 0
        return d.isoweekday() in self.dias_laborables and d not in self.no_laborables

    def horas(self, d: date) -> float:
        """Horas de trabajo de ese día (0 si no es laborable)."""
        h = self.horas_por_fecha.get(d)
        if h is not None:
            return h
        return self.horas_por_dia if self.es_laborable(d) else 0.0

    def horas_en(self, desde: date, hasta: date) -> float:
        """Horas de trabajo en [desde, hasta], ambos incluidos."""
        total, d = 0.0, desde
        while d <= hasta:
            total += self.horas(d)
            d += timedelta(days=1)
        return total

    def siguiente(self, d: date) -> date:
        """`d` si es laborable; si no, el primer laborable después."""
        while not self.es_laborable(d):
            d += timedelta(days=1)
        return d

    def anterior(self, d: date) -> date:
        """`d` si es laborable; si no, el último laborable antes."""
        while not self.es_laborable(d):
            d -= timedelta(days=1)
        return d

    # ── Aritmética en días laborables ────────────────────────────────────────
    def adelante(self, d: date, n: int) -> date:
        """n días laborables después de `d` (n = 0: `siguiente(d)`)."""
        if n < 0:
            return self.atras(d, -n)
        if n == 0:
            return self.siguiente(d)
        cuenta = 0
        while cuenta < n:
            d += timedelta(days=1)
            if self.es_laborable(d):
                cuenta += 1
        return d

    def atras(self, d: date, n: int) -> date:
        """n días laborables antes de `d` (n = 0: `anterior(d)`)."""
        if n < 0:
            return self.adelante(d, -n)
        if n == 0:
            return self.anterior(d)
        cuenta = 0
        while cuenta < n:
            d -= timedelta(days=1)
            if self.es_laborable(d):
                cuenta += 1
        return d

    def laborables_en(self, desde: date, hasta: date) -> int:
        """Días laborables en [desde, hasta], ambos incluidos (0 si hasta < desde)."""
        if hasta < desde:
            return 0
        n, d = 0, desde
        while d <= hasta:
            if self.es_laborable(d):
                n += 1
            d += timedelta(days=1)
        return n

    def distancia(self, a: date, b: date) -> int:
        """Días laborables con signo para ir de `a` a `b` (0 si es el mismo día).

        Es la holgura: positiva si `b` es posterior, negativa si es anterior.
        """
        if b >= a:
            return self.laborables_en(a + timedelta(days=1), b)
        return -self.laborables_en(b + timedelta(days=1), a)

    def duracion(self, inicio: date, fin: date) -> int:
        """Días laborables de una tarea de `inicio` a `fin`; al menos 1."""
        return max(1, self.laborables_en(inicio, fin))

    def fin_desde(self, inicio: date, duracion: int) -> date:
        """Último día de una tarea de `duracion` días que empieza en `inicio`."""
        return self.adelante(self.siguiente(inicio), max(1, duracion) - 1)

    def inicio_desde(self, fin: date, duracion: int) -> date:
        """Primer día de una tarea de `duracion` días que acaba en `fin`."""
        return self.atras(self.anterior(fin), max(1, duracion) - 1)

    def con_ausencias(self, dias: Iterable[date], horas_por_dia: Optional[float] = None) -> "Calendario":
        """El mismo calendario quitando más días (las ausencias de una persona)."""
        quitar = frozenset(dias)
        return Calendario(
            dias_laborables=self.dias_laborables,
            no_laborables=frozenset(self.no_laborables) | quitar,
            horas_por_dia=horas_por_dia or self.horas_por_dia,
            horas_por_fecha={**self.horas_por_fecha, **{d: 0.0 for d in quitar if d in self.horas_por_fecha}},
        )

    def con_horario(self, horas_por_fecha: Mapping[date, float], horas_por_dia: Optional[float] = None) -> "Calendario":
        """El mismo patrón con las horas de cada día del horario efectivo de una persona."""
        return Calendario(
            dias_laborables=self.dias_laborables,
            no_laborables=self.no_laborables,
            horas_por_dia=horas_por_dia or self.horas_por_dia,
            horas_por_fecha=dict(horas_por_fecha),
        )


# ── Carga desde la base de datos ─────────────────────────────────────────────

def calendario_de_empresa(db: Session, org_id: Optional[str]) -> Calendario:
    """El calendario de la empresa: días, jornada y festivos que valen para todos."""
    from app.models.settings import Holiday
    from app.services.settings_service import get_runtime_float, get_runtime_str

    try:
        dias = interpretar_dias_laborables(get_runtime_str(db, "PLANNING_WORKDAYS", org_id))
    except ValueError as exc:
        raise desde_valor(422, exc)
    horas = get_runtime_float(db, "DEFAULT_WORKING_HOURS_PER_DAY", org_id) or 0
    q = db.query(Holiday.date, Holiday.applies_to)
    if org_id:
        q = q.filter(Holiday.organization_id == org_id)
    festivos = {d for d, destino in q.all() if d is not None and not (destino or "").strip()}
    return Calendario(dias_laborables=dias, no_laborables=frozenset(festivos), horas_por_dia=horas)


def cargar_calendarios(
    db: Session, org_id: Optional[str], user_ids: Iterable[str], desde: Optional[date] = None,
) -> tuple[Calendario, dict[str, Calendario]]:
    """El de la empresa y uno por persona.

    El de cada persona sale de su horario efectivo (`app/services/horario`,
    rev. 180) día a día en [desde, desde + PLANNING_SCHEDULE_HORIZON_DAYS]:
    turnos, jornada, festivos de su sede, ausencias aprobadas (también por
    horas) y ventana de contrato de un externo. Fuera de ese horizonte, el
    patrón de la empresa con su jornada media.
    """
    from app.services.horario import efectivo as hor
    from app.services.settings_service import get_runtime_int

    empresa = calendario_de_empresa(db, org_id)
    ids = {u for u in user_ids if u}
    if not ids:
        return empresa, {}
    base = desde or timeutil.today()
    horizonte = max(1, int(get_runtime_int(db, "PLANNING_SCHEDULE_HORIZON_DAYS", org_id) or 730))
    inicio, fin = base - timedelta(days=31), base + timedelta(days=horizonte)
    todos = hor.horarios(db, ids, inicio, fin, org=org_id)
    personas = {}
    for uid in ids:
        dias_persona = todos.get(uid) or {}
        media = hor.media_diaria(dias_persona, empresa.horas_por_dia) if dias_persona else empresa.horas_por_dia
        personas[uid] = empresa.con_horario({d: round(x.horas, 4) for d, x in dias_persona.items()}, media)
    return empresa, personas
