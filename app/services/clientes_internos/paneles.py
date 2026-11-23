"""Cuadro de dirección de las unidades internas (docs/CLIENTES_INTERNOS.md §8).

Coste de TI por unidad y por fuente, presupuesto frente a real con el semáforo
de `umbrales` y cartera (proyectos activos, peticiones abiertas) por unidad.
"""
from __future__ import annotations
import logging

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.core import timeutil, umbrales
from app.services.clientes_internos import costes as C
from app.services.clientes_internos import unidades as U
from app.services.clientes_internos.presupuesto import estado

CERRADAS = ("approved", "rejected", "converted", "cancelled", "withdrawn", "done")


def _peticiones_abiertas(db: Session, unidad) -> int:
    from app.models.portfolio import PortfolioProposal
    n = db.query(PortfolioProposal).filter(PortfolioProposal.client_id == unidad.id,
                                           PortfolioProposal.status.notin_(CERRADAS)).count()
    # Baja (auditoría 22-11-2026): sin `try/hasattr` (el flujo de demanda existe
    # desde la migración 195); un error ya no se esconde contando de menos.
    from app.models.demanda import DemandRequest
    n += db.query(DemandRequest).filter(DemandRequest.client_id == unidad.id,
                                        DemandRequest.status.notin_(CERRADAS)).count()
    return n


def overview(db: Session, usuario, year: Optional[int] = None) -> dict:
    from app.services.settings_service import por_empresa
    hoy = timeutil.today()
    year = year or hoy.year
    desde, hasta = date(year, 1, 1), min(date(year, 12, 31), hoy)
    filas = []
    por_fuente = {f: 0.0 for f in C.FUENTES}
    total_coste = total_presupuesto = 0.0
    for u in U.unidades(db, usuario):
        c = C.coste(db, u, desde, hasta) if hasta >= desde else {"total": 0.0, "by_source": {}}
        e = estado(db, u, year, hasta=hasta, consumido=c["total"])
        for f, v in c["by_source"].items():
            por_fuente[f] = round(por_fuente[f] + v, 2)
        total_coste += c["total"]
        total_presupuesto += e["budget"]
        owner = u.business_owner
        filas.append({"id": u.id, "name": u.name, "internal_type": u.internal_type, "finance_mode": u.finance_mode,
                      "business_owner_name": owner.full_name if owner else None, "budget": e["budget"],
                      "cost": c["total"], "pct": e["pct"], "tone": e["tone"],
                      "projects_active": sum(1 for p in C.proyectos_de(db, u)
                                             if getattr(p.status, "value", p.status) in ("planning", "active",
                                                                                         "on_hold", "paused")),
                      "requests_open": _peticiones_abiertas(db, u), "warnings": U.avisos(db, u, e)})
    pct = round(100 * total_coste / total_presupuesto, 1) if total_presupuesto else None
    org = getattr(usuario, "organization_id", None)
    from app.services.clientes_internos.cargos import cuenta_de_ti
    avisos = []
    if any(f["finance_mode"] == "chargeback" for f in filas) and not cuenta_de_ti(db, org):
        avisos.append("interno_sin_cuenta_ti")
    return {"year": year, "currency": por_empresa.moneda_de_empresa(db, org), "warnings": avisos,
            "totals": {"budget": round(total_presupuesto, 2), "cost": round(total_coste, 2), "pct": pct,
                       "tone": umbrales.tono_de("presupuesto", pct, db, org) if pct is not None else None},
            "by_source": [{"source": f, "amount": v} for f, v in por_fuente.items()],
            "units": sorted(filas, key=lambda x: -x["cost"])}
