"""Agrupación mensual de instantes en la zona de quien mira el informe.

Auditoría 2026-08 (P2-14). Tres métricas mensuales agrupaban con
`extract("month", columna)` sobre columnas de fecha-HORA:

  · `SLABreachLog.breached_at`  — incumplimientos de SLA por mes
  · `ClientNPS.created_at`      — NPS medio por mes
  · `Task.completed_at`         — tareas completadas por mes

Esas tres columnas son `DateTime(timezone=True)` y guardan UTC, así que
`extract` agrupaba por el mes **UTC**: el mes en que la fila está almacenada, no
el mes en que ocurrió para quien mira el informe. Las filas de las primeras o
últimas horas de un mes caían en el mes contiguo. Una incidencia de SLA de las
23:30 del 31 de julio en Madrid se contaba en agosto.

Las otras cinco métricas mensuales del paquete NO estaban afectadas y no se han
tocado: `Invoice.issue_date`, `Timesheet.week_start`, `Expense.expense_date` y
`Imputation.date` son columnas `Date`, días de calendario sin instante. No tienen
zona que aplicar y su `extract` ya era correcto. Comprobado columna por columna
antes de cambiar nada.

── Por qué se agrupa en Python y no en SQL ──────────────────────────────────
`AT TIME ZONE` existe en PostgreSQL pero no en SQLite, así que una consulta con
esa cláusula dejaría de funcionar en desarrollo y en los tests. Esa divergencia
entre motores es exactamente lo que causó el hallazgo 11 (dos sistemas de esquema
que nunca se ejecutaban por la misma vía). Convertir en Python funciona igual en
los dos y el coste es irrelevante: son series de 12 a 24 puntos.
"""
from __future__ import annotations

from typing import Callable, Iterable, Optional

from app.core import timeutil


def agrupar_por_mes(
    filas: Iterable,
    instante: Callable[[object], object],
    *,
    valor: Optional[Callable[[object], float]] = None,
    zone=None,
) -> dict[str, tuple[float, int]]:
    """Reparte filas en cubos «AAAA-MM» según la zona indicada.

    `instante` extrae de cada fila la fecha-hora que decide el mes. `valor`
    extrae el número a acumular; si no se da, se cuentan filas.

    Devuelve {etiqueta: (acumulado, número de filas)}. Se devuelven las dos
    cifras porque una media necesita ambas, y calcularla aquí obligaría a este
    ayudante a saber si la métrica es una suma o un promedio.

    Las filas sin instante se descartan: no hay mes al que asignarlas, y
    colocarlas en uno inventado falsearía la serie.
    """
    if zone is None:
        # La zona de la petición: quien mira el informe lo ve en SU calendario.
        # Fuera de una petición vale UTC, que es el comportamiento anterior.
        zone = timeutil.current_zone()

    cubos: dict[str, tuple[float, int]] = {}
    for fila in filas:
        cuando = instante(fila)
        if cuando is None:
            continue
        etiqueta = timeutil.month_label_in(cuando, zone)
        acumulado, n = cubos.get(etiqueta, (0.0, 0))
        cubos[etiqueta] = (
            acumulado + (float(valor(fila)) if valor is not None else 1.0),
            n + 1,
        )
    return cubos


def serie_de_cuentas(cubos: dict[str, tuple[float, int]]) -> list[dict]:
    """Serie ordenada de conteos. Las etiquetas «AAAA-MM» ordenan bien como texto."""
    return [
        {"label": etiqueta, "value": int(cubos[etiqueta][0])}
        for etiqueta in sorted(cubos)
    ]
