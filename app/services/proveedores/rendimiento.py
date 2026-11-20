"""Cuadro de mando del proveedor (scorecard), por periodo (por defecto, 90 dias).

Dimensiones (0-100) y peso; las que no tienen datos en el periodo no cuentan y
el resto se reponderan:

- `sla` (30 %): cumplimiento de resolucion de sus servicios en su cola.
- `on_time` (20 %): paquetes aceptados entregados no mas tarde de lo previsto.
- `acceptance` (15 %): paquetes aceptados a la primera (sin rechazos).
- `billing` (15 %): estados de cuenta del periodo sin disputa.
- `compliance` (10 %): requisitos de GRC (100 ok, 50 atencion, 0 bloqueado).
- `hours` (10 %): asignaciones con horas dentro de lo contratado.

Tono con el umbral `sla` de la empresa (`app/core/umbrales.py`).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core import timeutil

PESOS = {"sla": 0.30, "on_time": 0.20, "acceptance": 0.15, "billing": 0.15, "compliance": 0.10, "hours": 0.10}


def _pct(a: float, b: float) -> Optional[float]:
    return round(a / b * 100, 1) if b else None


def cuadro(db: Session, sub, desde: Optional[date] = None, hasta: Optional[date] = None) -> dict:
    from app.core.umbrales import tono_de
    from app.models.enterprise import SubcontractorAssignment
    from app.models.proveedores import SupplierService, SupplierStatement, SupplierWorkPackage
    from app.services.proveedores import grc, servicios
    hasta = hasta or timeutil.today()
    desde = desde or hasta - timedelta(days=90)
    valores: dict = {}
    detalle: dict = {}

    slas = [servicios.sla(db, s, desde, hasta) for s in db.query(SupplierService).filter(
        SupplierService.subcontractor_id == sub.id, SupplierService.agent_group_id.isnot(None)).all()]
    medidos = [m for m in slas if m["compliance_pct"] is not None]
    if medidos:
        total = sum(m["tickets_resolved"] for m in medidos)
        valores["sla"] = round(sum(m["compliance_pct"] * m["tickets_resolved"] for m in medidos) / total, 1)
        detalle["sla"] = {"services": len(medidos), "tickets_resolved": total}

    aceptados = db.query(SupplierWorkPackage).filter(SupplierWorkPackage.subcontractor_id == sub.id,
                                                     SupplierWorkPackage.status == "accepted",
                                                     SupplierWorkPackage.accepted_at >= desde,
                                                     SupplierWorkPackage.accepted_at <= hasta).all()
    con_plazo = [w for w in aceptados if w.planned_end]
    if con_plazo:
        a_tiempo = sum(1 for w in con_plazo if (w.delivered_at or w.accepted_at) <= w.planned_end)
        valores["on_time"] = _pct(a_tiempo, len(con_plazo))
        detalle["on_time"] = {"accepted": len(con_plazo), "on_time": a_tiempo}
    if aceptados:
        primera = sum(1 for w in aceptados if not w.rejections)
        valores["acceptance"] = _pct(primera, len(aceptados))
        detalle["acceptance"] = {"accepted": len(aceptados), "first_time": primera}

    estados = db.query(SupplierStatement).filter(SupplierStatement.subcontractor_id == sub.id,
                                                 SupplierStatement.period_end >= desde,
                                                 SupplierStatement.period_end <= hasta,
                                                 SupplierStatement.invoice_id.isnot(None)).all()
    if estados:
        disputados = sum(1 for s in estados if s.status == "disputed" or s.dispute_reason)
        valores["billing"] = _pct(len(estados) - disputados, len(estados))
        detalle["billing"] = {"statements": len(estados), "disputed": disputados}

    c = grc.cumplimiento(db, sub)
    valores["compliance"] = {"ok": 100.0, "attention": 50.0, "blocked": 0.0}[c["status"]]
    detalle["compliance"] = {"status": c["status"], "missing": c["missing"]}

    asig = db.query(SubcontractorAssignment).filter(SubcontractorAssignment.subcontractor_id == sub.id,
                                                    SubcontractorAssignment.hours_contracted.isnot(None),
                                                    SubcontractorAssignment.hours_contracted > 0).all()
    if asig:
        dentro = sum(1 for a in asig if (a.hours_logged or 0) <= a.hours_contracted)
        valores["hours"] = _pct(dentro, len(asig))
        detalle["hours"] = {"assignments": len(asig), "within": dentro}

    con_dato = {k: v for k, v in valores.items() if v is not None}
    peso = sum(PESOS[k] for k in con_dato)
    score = round(sum(v * PESOS[k] for k, v in con_dato.items()) / peso, 1) if peso else None
    return {
        "subcontractor_id": sub.id, "period_start": str(desde), "period_end": str(hasta), "score": score,
        "tone": tono_de("sla", score, db, db.info.get("organization_id")) if score is not None else None,
        "dimensions": [{"key": k, "value": valores.get(k), "weight": PESOS[k], "detail": detalle.get(k, {})}
                       for k in PESOS],
    }
