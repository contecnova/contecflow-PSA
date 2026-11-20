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
  Proveedores (migracion 189): de los estados de cuenta aprobados, las lineas
  que no son horas (precio cerrado, unidades, cuotas, creditos, bonus, gastos)
  con proyecto (`proveedores.facturacion.partidas`). Las horas, no: ya estan.

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


def partidas_externas(db: Session, project_ids: list[str], moneda: str, desde=None, hasta=None) -> list[tuple]:
    """Gastos y subcontrata de varios proyectos con su fecha, en `moneda`:
    ``[(project_id, fecha, "gastos" | "subcontrata", importe)]``.

    Las reglas son las de `costes_externos` (que suma esto para un proyecto):
    gastos aprobados o reembolsados, la parte del reparto
    (`gastos_avanzados.importe_por_proyecto`), sin los conciliados con ALM;
    partes de subcontrata sin los que ya imputo esa persona ese dia. La
    evolucion del margen los reparte por tramo (`evolucion_del_margen`)."""
    from sqlalchemy import or_

    from app.models.enterprise import Subcontractor, SubcontractorTimeLog
    from app.models.expenses import Expense, ExpenseAllocation
    from app.services.alm_conciliacion import gastos_conciliados
    from app.services.externos.horas import partes_sin_duplicar
    from app.services.gastos_avanzados import COSTE, importe_por_proyecto
    from app.services.profitability_service import get_fx_rate
    if not project_ids:
        return []
    ids = list(project_ids)
    cache: dict = {}

    def convertir(importe, de, fecha) -> float:
        de = (de or moneda).upper()
        return float(importe) * (get_fx_rate(db, de, moneda, fecha, _cache=cache) if de != moneda else 1.0)

    q = db.query(Expense).filter(Expense.status.in_(COSTE), Expense.is_active.isnot(False), or_(
        Expense.project_id.in_(ids),
        Expense.id.in_(db.query(ExpenseAllocation.expense_id).filter(ExpenseAllocation.project_id.in_(ids)))))
    if desde:
        q = q.filter(Expense.expense_date >= desde)
    if hasta:
        q = q.filter(Expense.expense_date <= hasta)
    conciliados = gastos_conciliados(db)
    if conciliados:
        q = q.filter(Expense.id.notin_(conciliados))
    gastos = q.all()
    salida: list[tuple] = []
    for pid in ids:
        for g, imp in importe_por_proyecto(db, gastos, pid):
            salida.append((pid, g.expense_date, "gastos", convertir(imp, g.currency, g.expense_date)))

    t = db.query(SubcontractorTimeLog, Subcontractor.currency).join(
        Subcontractor, Subcontractor.id == SubcontractorTimeLog.subcontractor_id).filter(
        SubcontractorTimeLog.project_id.in_(ids), SubcontractorTimeLog.is_active.isnot(False),
        SubcontractorTimeLog.cost_amount.isnot(None))
    t = partes_sin_duplicar(db, t)
    if desde:
        t = t.filter(SubcontractorTimeLog.log_date >= desde)
    if hasta:
        t = t.filter(SubcontractorTimeLog.log_date <= hasta)
    for log, cur in t.all():
        salida.append((log.project_id, log.log_date, "subcontrata", convertir(log.cost_amount, cur, log.log_date)))
    # Migracion 189: estados de cuenta aprobados de proveedores, lo que no son horas
    # (precio cerrado, por unidad, cuota, creditos, bonus, gastos) con proyecto.
    from app.services.proveedores.facturacion import partidas as partidas_de_proveedores
    salida.extend(partidas_de_proveedores(db, ids, moneda, desde, hasta, convertir=convertir))
    return salida


def costes_externos(db: Session, project_id: str, moneda: str, desde=None, hasta=None) -> dict:
    """{"gastos": importe, "subcontrata": importe, "alm": importe} del proyecto, en `moneda`."""
    from app.services.alm_costes import coste_de_proyecto
    partidas = partidas_externas(db, [project_id], moneda, desde, hasta)
    gastos = sum(v for _, _, tipo, v in partidas if tipo == "gastos")
    subcontrata = sum(v for _, _, tipo, v in partidas if tipo == "subcontrata")
    alm = coste_de_proyecto(db, project_id, moneda, desde, hasta)
    return {"gastos": round(gastos, 2), "subcontrata": round(subcontrata, 2), "alm": alm}
