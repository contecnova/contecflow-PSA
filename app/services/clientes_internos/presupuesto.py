"""Presupuesto anual de una unidad interna y su consumo (docs/CLIENTES_INTERNOS.md §4).

No hay presupuesto propio: es el de Presupuestos (`budgets`) aprobado y vigente
con `cliente_id` de la unidad. Consumo = coste del año hasta hoy (o hasta
`hasta`). Semáforo: métrica `presupuesto` de `app/core/umbrales.py`.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.core import timeutil, umbrales


def presupuestos(db: Session, unidad, year: int) -> list:
    from app.models.mfa import Budget
    return db.query(Budget).filter(Budget.cliente_id == unidad.id, Budget.year == year,
                                   Budget.estado == "aprobado").all()


def importe_presupuestado(db: Session, unidad, year: int) -> float:
    return round(sum(float(b.total_amount or 0) for b in presupuestos(db, unidad, year)), 2)


def estado(db: Session, unidad, year: Optional[int] = None, hasta: Optional[date] = None,
           extra: float = 0.0, consumido: Optional[float] = None) -> dict:
    """Presupuesto, consumo (+ `extra`), % y tono del año."""
    from app.services.clientes_internos.costes import coste
    from app.services.settings_service import por_empresa
    hoy = timeutil.today()
    year = year or hoy.year
    hasta = hasta or min(date(year, 12, 31), hoy)
    filas = presupuestos(db, unidad, year)
    total = round(sum(float(b.total_amount or 0) for b in filas), 2)
    if consumido is None:
        consumido = coste(db, unidad, date(year, 1, 1), hasta)["total"] if hasta >= date(year, 1, 1) else 0.0
    consumido = round(consumido + extra, 2)
    pct = round(100 * consumido / total, 1) if total else None
    return {"year": year, "budget": total, "consumed": consumido, "pct": pct,
            "tone": umbrales.tono_de("presupuesto", pct, db, unidad.organization_id) if pct is not None else None,
            "currency": por_empresa.moneda_de_empresa(db, unidad.organization_id),
            "budget_ids": [b.id for b in filas]}
