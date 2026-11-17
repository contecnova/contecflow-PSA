"""Calendario laboral: qué días se trabaja y cuántas horas.

Proyectos — planificador (16-11-2026). El camino crítico de antes contaba días
naturales y dividía las horas entre un 8 escrito en el código. Ahora cada tarea
se planifica con el calendario de quien la hace:

  · **empresa**: días laborables del ajuste `PLANNING_WORKDAYS`, jornada de
    `DEFAULT_WORKING_HOURS_PER_DAY` y los festivos de Configuración › Festivos
    que valen para todos (los que no llevan `applies_to`);
  · **persona**: el de la empresa, menos sus ausencias **aprobadas** (las
    pendientes no quitan días: aún pueden rechazarse) y con su jornada
    (`weekly_capacity_hours` / días laborables).

La clase es pura —sin base de datos— para que el CPM y sus tests no dependan de
nada; `cargar_calendarios` es lo único que lee tablas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.core import timeutil


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
        raise ValueError("PLANNING_WORKDAYS no tiene ningún día laborable válido (1-7)")
    return frozenset(dias)


@dataclass(frozen=True)
class Calendario:
    """Días laborables (ISO), días sueltos que no se trabajan y jornada."""

    dias_laborables: frozenset[int]
    no_laborables: frozenset[date] = field(default_factory=frozenset)
    horas_por_dia: float = 8.0

    def __post_init__(self) -> None:
        if not self.dias_laborables:
            raise ValueError("Un calendario necesita al menos un día laborable")
        if self.horas_por_dia <= 0:
            raise ValueError("La jornada tiene que ser mayor que cero")

    # ── Consultas de un día ──────────────────────────────────────────────────
    def es_laborable(self, d: date) -> bool:
        return d.isoweekday() in self.dias_laborables and d not in self.no_laborables

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
        return Calendario(
            dias_laborables=self.dias_laborables,
            no_laborables=frozenset(self.no_laborables) | frozenset(dias),
            horas_por_dia=horas_por_dia or self.horas_por_dia,
        )


# ── Carga desde la base de datos ─────────────────────────────────────────────

def calendario_de_empresa(db: Session, org_id: Optional[str]) -> Calendario:
    """El calendario de la empresa: días, jornada y festivos que valen para todos."""
    from app.models.settings import Holiday
    from app.services.settings_service import get_runtime_float, get_runtime_str

    from app.core.errores import ErrorDeDominio
    try:
        dias = interpretar_dias_laborables(get_runtime_str(db, "PLANNING_WORKDAYS", org_id))
    except ValueError as exc:
        raise ErrorDeDominio(422, str(exc))
    horas = get_runtime_float(db, "DEFAULT_WORKING_HOURS_PER_DAY", org_id) or 0
    q = db.query(Holiday.date, Holiday.applies_to)
    if org_id:
        q = q.filter(Holiday.organization_id == org_id)
    festivos = {d for d, destino in q.all() if d is not None and not (destino or "").strip()}
    return Calendario(dias_laborables=dias, no_laborables=frozenset(festivos), horas_por_dia=horas)


def cargar_calendarios(
    db: Session, org_id: Optional[str], user_ids: Iterable[str], desde: Optional[date] = None,
) -> tuple[Calendario, dict[str, Calendario]]:
    """El de la empresa y uno por persona, en dos consultas.

    `desde` acota las ausencias: las que terminaron antes no cambian nada.
    """
    from app.models.resources import Absence, AbsenceStatus
    from app.models.user import User

    empresa = calendario_de_empresa(db, org_id)
    ids = {u for u in user_ids if u}
    if not ids:
        return empresa, {}

    jornadas = {}
    for uid, semanales in db.query(User.id, User.weekly_capacity_hours).filter(User.id.in_(ids)).all():
        jornadas[uid] = (semanales / len(empresa.dias_laborables)) if semanales else None

    q = db.query(Absence.user_id, Absence.start_date, Absence.end_date).filter(
        Absence.user_id.in_(ids), Absence.status == AbsenceStatus.approved,
    )
    if desde is not None:
        q = q.filter(Absence.end_date >= desde)
    ausencias: dict[str, set[date]] = {}
    for uid, ini, fin in q.all():
        if not ini or not fin:
            continue
        d = ini
        while d <= fin:
            ausencias.setdefault(uid, set()).add(d)
            d += timedelta(days=1)

    # Externos (migracion 178): fuera de su ventana de contrato no trabajan.
    # Se quitan los dias de antes de `available_from` y de despues de
    # `available_until` dentro de un horizonte finito (un año antes de `desde`
    # y dos despues del fin): el calendario sigue siendo usable (ninguna
    # busqueda de «siguiente laborable» se queda sin fin).
    from app.services.externos.disponibilidad import ventanas
    base = desde or timeutil.today()
    for uid, v in ventanas(db, ids).items():
        fuera = ausencias.setdefault(uid, set())
        if v.desde and v.desde > base - timedelta(days=365):
            d = base - timedelta(days=365)
            while d < v.desde:
                fuera.add(d)
                d += timedelta(days=1)
        if v.hasta:
            d = v.hasta + timedelta(days=1)
            tope = max(v.hasta, base) + timedelta(days=730)
            while d <= tope:
                fuera.add(d)
                d += timedelta(days=1)

    personas = {
        uid: empresa.con_ausencias(ausencias.get(uid, ()), jornadas.get(uid))
        for uid in ids
    }
    return empresa, personas
