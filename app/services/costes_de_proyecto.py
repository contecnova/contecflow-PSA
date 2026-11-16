"""Costes reales de un proyecto además de las horas propias (revisión 2026-11).

Medido antes: la rentabilidad y EVM contaban como coste sólo las imputaciones
(`imputations.cost_amount`). Los gastos del proyecto y las horas de los
subcontratistas no llegaban a ningún margen ni al CPI, mientras que el BAC ya
era el presupuesto aprobado entero (con licencias, viajes y subcontratación).

- **Gastos**: aprobados o reembolsados, la parte del reparto entre proyectos
  (`gastos_avanzados.importe_por_proyecto`), en la fecha del gasto.
- **Subcontrata**: el coste de las horas registradas
  (`subcontractor_timelogs.cost_amount`, horas × tarifa de coste), en su fecha.
  Las facturas del proveedor pagan esas horas: no se suman otra vez.
  Externos como internos (migracion 178): el externo con acceso imputa como
  todos y su coste (tarifa del proveedor) ya esta en `imputations.cost_amount`;
  el parte manual es para externos sin acceso y, por diseno, un parte no cuenta
  si esa persona tiene imputacion en ese proyecto y dia
  (`externos.horas.partes_sin_duplicar`): nunca dos veces.

- **Licencias y equipos** (fase 3 de licencias y hardware, 16-11-2026): el
  coste diario de ALM imputado al proyecto (`alm_costes.coste_de_proyecto`):
  licencias y bolsas asignadas al proyecto o a su equipo con cargo al
  proyecto, equipos amortizados y lo ocioso de lo que es del proyecto. Un
  gasto que paga una factura de proveedor de ALM ya conciliada
  (`alm_conciliacion`) no cuenta en «gastos»: ese coste está repartido por
  días en ALM y contaría dos veces.

Cada importe se convierte a `moneda` con el tipo de su fecha (`get_fx_rate`).
"""
from __future__ import annotations

from sqlalchemy.orm import Session


def costes_externos(db: Session, project_id: str, moneda: str, desde=None, hasta=None) -> dict:
    """{"gastos": importe, "subcontrata": importe, "alm": importe} del proyecto, en `moneda`."""
    from sqlalchemy import or_

    from app.models.enterprise import Subcontractor, SubcontractorTimeLog
    from app.models.expenses import Expense, ExpenseAllocation
    from app.services.gastos_avanzados import COSTE, importe_por_proyecto
    from app.services.profitability_service import get_fx_rate
    cache: dict = {}

    def convertir(importe, de, fecha) -> float:
        de = (de or moneda).upper()
        return float(importe) * (get_fx_rate(db, de, moneda, fecha, _cache=cache) if de != moneda else 1.0)

    q = db.query(Expense).filter(Expense.status.in_(COSTE), Expense.is_active.isnot(False), or_(
        Expense.project_id == project_id,
        Expense.id.in_(db.query(ExpenseAllocation.expense_id).filter(ExpenseAllocation.project_id == project_id))))
    if desde:
        q = q.filter(Expense.expense_date >= desde)
    if hasta:
        q = q.filter(Expense.expense_date <= hasta)
    from app.services.alm_conciliacion import gastos_conciliados
    conciliados = gastos_conciliados(db)
    if conciliados:
        q = q.filter(Expense.id.notin_(conciliados))
    gastos = sum(convertir(imp, g.currency, g.expense_date) for g, imp in importe_por_proyecto(db, q.all(), project_id))

    t = db.query(SubcontractorTimeLog, Subcontractor.currency).join(
        Subcontractor, Subcontractor.id == SubcontractorTimeLog.subcontractor_id).filter(
        SubcontractorTimeLog.project_id == project_id, SubcontractorTimeLog.is_active.isnot(False),
        SubcontractorTimeLog.cost_amount.isnot(None))
    from app.services.externos.horas import partes_sin_duplicar
    t = partes_sin_duplicar(db, t)
    if desde:
        t = t.filter(SubcontractorTimeLog.log_date >= desde)
    if hasta:
        t = t.filter(SubcontractorTimeLog.log_date <= hasta)
    subcontrata = sum(convertir(log.cost_amount, cur, log.log_date) for log, cur in t.all())
    from app.services.alm_costes import coste_de_proyecto
    alm = coste_de_proyecto(db, project_id, moneda, desde, hasta)
    return {"gastos": round(gastos, 2), "subcontrata": round(subcontrata, 2), "alm": alm}
