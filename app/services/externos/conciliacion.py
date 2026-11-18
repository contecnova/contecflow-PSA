"""Facturas del proveedor contra las horas imputadas (rentabilidad del externo).

Para cada factura (`SubcontractorInvoice`) se calcula lo esperado: las horas
del periodo que cubre —imputaciones de sus personas + partes manuales sin
duplicar— por su tarifa vigente (el `cost_amount` ya guardado con ella). El
periodo va del dia siguiente a la factura anterior del mismo ambito (proveedor
o asignacion) hasta la fecha de la factura. Diferencia = importe facturado
(sin IVA) − esperado: positiva, el proveedor factura mas de lo imputado.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session


def _esperado(db: Session, sub_id: str, asignaciones: list, desde, hasta) -> tuple[float, float, float]:
    from app.models.enterprise import SubcontractorTimeLog as TL
    from app.models.imputation import Imputation as I
    from app.services.externos.horas import partes_sin_duplicar
    h_imp = coste = 0.0
    for a in asignaciones:
        w = a.worker
        if w is None or not w.user_id:
            continue
        q = db.query(func.coalesce(func.sum(I.hours), 0.0), func.coalesce(func.sum(I.cost_amount), 0.0)).filter(
            I.user_id == w.user_id, I.project_id == a.project_id, I.date <= hasta)
        if desde:
            q = q.filter(I.date >= desde)
        if a.start_date:
            q = q.filter(I.date >= a.start_date)
        if a.end_date:
            q = q.filter(I.date <= a.end_date)
        h, c = q.one()
        h_imp += float(h or 0)
        coste += float(c or 0)
    tq = db.query(TL).filter(TL.subcontractor_id == sub_id, TL.is_active.isnot(False), TL.log_date <= hasta,
                             TL.assignment_id.in_([a.id for a in asignaciones]) if asignaciones else TL.id.is_(None))
    if desde:
        tq = tq.filter(TL.log_date >= desde)
    tq = partes_sin_duplicar(db, tq)
    h_man, c_man = tq.with_entities(func.coalesce(func.sum(TL.hours), 0.0),
                                    func.coalesce(func.sum(TL.cost_amount), 0.0)).one()
    return h_imp, float(h_man or 0), coste + float(c_man or 0)


def conciliar(db: Session, sub_id: str) -> list[dict]:
    from app.models.enterprise import SubcontractorAssignment, SubcontractorInvoice
    facturas = db.query(SubcontractorInvoice).filter(
        SubcontractorInvoice.subcontractor_id == sub_id, SubcontractorInvoice.status != "rejected",
    ).order_by(SubcontractorInvoice.issue_date).all()
    todas = db.query(SubcontractorAssignment).filter(SubcontractorAssignment.subcontractor_id == sub_id).all()
    # 18-11-2026: moneda de la empresa del externo, no la global del entorno.
    from app.models.enterprise import Subcontractor
    from app.services.settings_service.por_empresa import moneda_de_empresa
    moneda = moneda_de_empresa(db, registro=db.get(Subcontractor, sub_id))
    ultima: dict = {}
    salida = []
    for f in facturas:
        ambito = f.assignment_id or "*"
        asignaciones = [a for a in todas if a.id == f.assignment_id] if f.assignment_id else todas
        desde = ultima.get(ambito)
        h_imp, h_man, esperado = _esperado(db, sub_id, asignaciones, desde, f.issue_date)
        ultima[ambito] = f.issue_date + timedelta(days=1)
        # El coste imputado esta en la moneda de la empresa: la factura se pasa
        # a esa moneda con el tipo de su fecha para comparar.
        importe = float(f.amount or 0)
        if f.currency and f.currency.upper() != moneda:
            from app.services.profitability_service import get_fx_rate
            importe *= get_fx_rate(db, f.currency.upper(), moneda, f.issue_date)
        dif = round(importe - esperado, 2)
        a0 = asignaciones[0] if f.assignment_id and asignaciones else None
        salida.append({
            "invoice_id": f.id, "invoice_number": f.invoice_number, "issue_date": str(f.issue_date),
            "assignment_id": f.assignment_id,
            "project_name": a0.project.name if a0 and a0.project else None,
            "period_from": str(desde) if desde else None, "period_to": str(f.issue_date),
            "amount": round(importe, 2), "invoice_amount": round(f.amount or 0, 2),
            "invoice_currency": f.currency, "hours_imputed": round(h_imp, 2), "hours_manual": round(h_man, 2),
            "expected_amount": round(esperado, 2), "difference": dif,
            "difference_pct": round(dif / esperado * 100, 1) if esperado else None,
            "currency": moneda, "status": f.status,
        })
    return list(reversed(salida))
