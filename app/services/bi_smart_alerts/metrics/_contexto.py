"""Contexto de calculo de una serie (organizacion, periodo, sesion) y el logger comun.

Parte de `app.services.bi_smart_alerts.metrics` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session


logger = logging.getLogger("app.services.bi_smart_alerts.metrics")


@dataclass
class _Ctx:
    """Lo que toda metrica necesita del entorno para calcular su serie.

    `series` es la rejilla de meses de referencia: todas las metricas devuelven
    una serie de su misma longitud para que los paneles puedan compararlas entre
    si. Los cuatro ayudantes eran cierres dentro de la funcion original y su
    cuerpo se conserva igual.
    """

    db: Session
    key: str
    org_id: Optional[str]
    series: list[dict] = field(default_factory=list)
    start_date: Optional[date] = None

    def empty_like(self) -> list[float]:
        """Serie a cero de la longitud correcta. Es la respuesta a «no hay dato»."""
        return [0.0 for _ in self.series]

    def bucket_count(self, rows, date_field_idx=0, *, start: date) -> list[float]:
        """Cuenta filas por mes. `start` se conserva en la firma por
        compatibilidad con las llamadas: el cuerpo original no lo usaba."""
        bkt: dict[str, float] = defaultdict(float)
        for row in rows:
            d = row[date_field_idx] if isinstance(row, (list, tuple)) else row
            if d:
                bkt[f"{d.year:04d}-{d.month:02d}"] += 1.0
        return [float(bkt.get(m["month"], 0.0)) for m in self.series]

    def bucket_sum(self, rows, date_idx=0, value_idx=1, *, start: date) -> list[float]:
        """Suma un valor por mes. `start`, igual que arriba."""
        bkt: dict[str, float] = defaultdict(float)
        for row in rows:
            d, v = row[date_idx], row[value_idx]
            if d and v is not None:
                bkt[f"{d.year:04d}-{d.month:02d}"] += float(v)
        return [float(bkt.get(m["month"], 0.0)) for m in self.series]

    def current(self, val: float) -> list[float]:
        """Un valor instantaneo repetido en toda la serie.

        Se usa en las metricas que solo tienen «ahora» (cuantos proyectos hay
        activos), donde no existe historico mensual que reconstruir.
        """
        return [val] * len(self.series)


def _construir_contexto(db: Session, metric_key: str, organization_id: Optional[str]) -> _Ctx:
    """Prepara la rejilla de meses. Era el prologo de la funcion original."""
    from app.services.bi_intelligence_service import _month_series

    try:
        series = _month_series(db, organization_id, months_history=24)
    except Exception:
        logger.warning(
            "Failed to load _month_series for smart alerts org=%s",
            organization_id, exc_info=True,
        )
        series = []
    if not series:
        # Sin historico se devuelve una rejilla del ano en curso a cero, para que
        # las series sigan teniendo la misma longitud y los paneles no se
        # descuadren.
        _cur_year = datetime.now(timezone.utc).year
        series = [
            {"month": f"{_cur_year}-{m:02d}", "revenue": 0.0, "cost": 0.0, "hours": 0.0}
            for m in range(1, 13)
        ]

    return _Ctx(
        db=db,
        key=metric_key,
        org_id=organization_id,
        series=series,
        start_date=date.fromisoformat(series[0]["month"] + "-01"),
    )
