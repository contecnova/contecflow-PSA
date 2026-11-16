"""Conciliación contrato ↔ factura del proveedor ↔ gasto (licencias y hardware, fase 3 — 16-11-2026).

Una factura de proveedor (`ALMFacturaProveedor`) se compara con:

- lo que el **contrato** (o la licencia) dice que cuesta ese periodo
  (`importe_esperado`: meses enteros = cuota anual / 12 × meses; si no,
  cuota anual / 365 × días);
- el **gasto** que la paga (`Expense`, de una categoría de
  `ALM_EXPENSE_CATEGORIES`, aprobado o reembolsado).

Con tolerancia `ALM_RECONCILIATION_TOLERANCE_PCT`. El resultado es
``matched`` o ``discrepancy`` con una lista de códigos (los traduce la
interfaz: `alm.rec_<código>`); una discrepancia revisada se puede aceptar con
una nota (``accepted``).

Un gasto enlazado a una factura deja de contar en «gastos» de la rentabilidad
del proyecto (`costes_de_proyecto`): ese coste ya está en el reparto diario de
ALM. Y el mes que cubre deja de contar como comprometido en presupuestos
(`alm_costes.meses_facturados`).
"""
from __future__ import annotations

import calendar
import json
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core import timeutil
from app.core.errores import ErrorDeDominio
from app.models.alm import ALMContract, ALMFacturaProveedor, ALMLicense, ALMVendor

CODIGOS = (
    "no_contract", "amount_mismatch", "outside_contract", "contract_not_active", "vendor_mismatch",
    "no_expense", "expense_amount_mismatch", "expense_currency_mismatch", "expense_category",
    "expense_not_approved", "currency_mismatch", "no_period",
)


def _fecha(v, campo):
    if v in (None, ""):
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise ErrorDeDominio(422, f"alm_fecha_invalida:{campo}")


def _num(v, campo, obligatorio=False):
    if v in (None, ""):
        if obligatorio:
            raise ErrorDeDominio(422, f"alm_importe_invalido:{campo}")
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        raise ErrorDeDominio(422, f"alm_importe_invalido:{campo}")


def _tolerancia(db: Session, org) -> float:
    from app.services.alm_ajustes import ajuste_float
    return max(0.0, ajuste_float(db, "ALM_RECONCILIATION_TOLERANCE_PCT", org)) / 100.0


def _cerca(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= max(0.01, abs(b) * tol)


def _meses_enteros(desde: date, hasta: date) -> Optional[int]:
    if desde.day != 1 or hasta.day != calendar.monthrange(hasta.year, hasta.month)[1]:
        return None
    return (hasta.year - desde.year) * 12 + hasta.month - desde.month + 1


def importe_esperado(cuota_anual: Optional[float], desde: Optional[date], hasta: Optional[date]) -> Optional[float]:
    if not cuota_anual or desde is None or hasta is None or hasta < desde:
        return None
    meses = _meses_enteros(desde, hasta)
    if meses:
        return round(float(cuota_anual) / 12 * meses, 2)
    return round(float(cuota_anual) / 365 * ((hasta - desde).days + 1), 2)


# ── CRUD ──────────────────────────────────────────────────────────────────────

CAMPOS = ("vendor_id", "contract_id", "license_id", "number", "issue_date", "period_from", "period_to",
          "amount", "tax_amount", "currency", "notes")


def _limpiar(db: Session, data: dict, f: Optional[ALMFacturaProveedor] = None) -> dict:
    out = {}
    for k in CAMPOS:
        if k not in data:
            continue
        v = data[k]
        if k in ("issue_date", "period_from", "period_to"):
            v = _fecha(v, k)
        elif k in ("amount", "tax_amount"):
            v = _num(v, k, obligatorio=(k == "amount"))
        elif isinstance(v, str):
            v = v.strip() or None
        out[k] = v
    for k, modelo, codigo in (("vendor_id", ALMVendor, "alm_proveedor_no_encontrado"),
                              ("contract_id", ALMContract, "alm_contrato_no_encontrado"),
                              ("license_id", ALMLicense, "alm_licencia_no_encontrada")):
        if out.get(k) and db.query(modelo.id).filter(modelo.id == out[k]).first() is None:
            raise ErrorDeDominio(404, codigo)
    if out.get("contract_id") and not out.get("vendor_id") and (f is None or not f.vendor_id):
        c = db.get(ALMContract, out["contract_id"])
        out["vendor_id"] = c.vendor_id
    if out.get("currency"):
        out["currency"] = out["currency"].upper()[:3]
    return out


def crear(db: Session, actor, data: dict) -> dict:
    datos = _limpiar(db, data)
    if not datos.get("number"):
        raise ErrorDeDominio(422, "alm_factura_sin_numero")
    if datos.get("issue_date") is None:
        raise ErrorDeDominio(422, "alm_factura_sin_fecha")
    if datos.get("amount") is None:
        raise ErrorDeDominio(422, "alm_importe_invalido:amount")
    _sin_duplicado(db, datos.get("vendor_id"), datos["number"])
    f = ALMFacturaProveedor(**datos, created_by=getattr(actor, "id", None))
    if not f.currency and f.contract_id:
        f.currency = db.get(ALMContract, f.contract_id).currency
    db.add(f)
    db.flush()
    conciliar(db, f, actor, commit=False)
    db.commit()
    return serializar(db, f)


def _sin_duplicado(db: Session, vendor_id, numero, excepto=None) -> None:
    q = db.query(ALMFacturaProveedor.id).filter(ALMFacturaProveedor.number == numero,
                                                ALMFacturaProveedor.is_active.isnot(False))
    q = q.filter(ALMFacturaProveedor.vendor_id == vendor_id) if vendor_id else q.filter(
        ALMFacturaProveedor.vendor_id.is_(None))
    if excepto:
        q = q.filter(ALMFacturaProveedor.id != excepto)
    if q.first() is not None:
        raise ErrorDeDominio(409, "alm_factura_duplicada")


def factura(db: Session, fid: str) -> ALMFacturaProveedor:
    f = db.query(ALMFacturaProveedor).filter(ALMFacturaProveedor.id == fid,
                                             ALMFacturaProveedor.is_active.isnot(False)).first()
    if f is None:
        raise ErrorDeDominio(404, "alm_factura_no_encontrada")
    return f


def actualizar(db: Session, actor, fid: str, data: dict) -> dict:
    f = factura(db, fid)
    datos = _limpiar(db, data, f)
    if "number" in datos or "vendor_id" in datos:
        _sin_duplicado(db, datos.get("vendor_id", f.vendor_id), datos.get("number", f.number), excepto=f.id)
    for k, v in datos.items():
        setattr(f, k, v)
    if f.status == "accepted":
        f.status = "pending"
    conciliar(db, f, actor, commit=False)
    db.commit()
    return serializar(db, f)


def borrar(db: Session, fid: str) -> dict:
    f = factura(db, fid)
    f.is_active = False
    f.expense_id = None
    db.commit()
    return {"ok": True}


# ── Conciliar ─────────────────────────────────────────────────────────────────

def conciliar(db: Session, f: ALMFacturaProveedor, actor=None, commit: bool = True) -> ALMFacturaProveedor:
    from app.models.expenses import Expense
    from app.services.alm_ajustes import ajuste_lista
    tol = _tolerancia(db, f.organization_id)
    problemas: list[str] = []
    contrato = db.get(ALMContract, f.contract_id) if f.contract_id else None
    licencia = db.get(ALMLicense, f.license_id) if f.license_id else None
    cuota = None
    if contrato is not None:
        cuota = contrato.annual_value
        if getattr(contrato.status, "value", contrato.status) not in ("active",):
            problemas.append("contract_not_active")
        if contrato.vendor_id and f.vendor_id and contrato.vendor_id != f.vendor_id:
            problemas.append("vendor_mismatch")
        if f.currency and contrato.currency and f.currency != contrato.currency:
            problemas.append("currency_mismatch")
        desde, hasta = f.period_from or f.issue_date, f.period_to or f.issue_date
        if (contrato.start_date and desde < contrato.start_date) or (contrato.end_date and hasta > contrato.end_date):
            problemas.append("outside_contract")
    if licencia is not None and cuota is None:
        cuota = licencia.annual_cost
    if contrato is None and licencia is None:
        problemas.append("no_contract")
    esperado = importe_esperado(cuota, f.period_from, f.period_to)
    if cuota and esperado is None:
        problemas.append("no_period")
    if esperado is not None and not _cerca(f.amount, esperado, tol):
        problemas.append("amount_mismatch")
    if f.expense_id:
        g = db.get(Expense, f.expense_id)
        from app.services.gastos_avanzados import COSTE
        if g is None:
            problemas.append("no_expense")
        else:
            if not _cerca(float(g.amount or 0), float(f.amount) + float(f.tax_amount or 0), tol) \
                    and not _cerca(float(g.amount or 0), float(f.amount), tol):
                problemas.append("expense_amount_mismatch")
            if f.currency and g.currency and g.currency != f.currency:
                problemas.append("expense_currency_mismatch")
            if getattr(g.category, "value", g.category) not in ajuste_lista(db, "ALM_EXPENSE_CATEGORIES", f.organization_id):
                problemas.append("expense_category")
            if g.status not in COSTE:
                problemas.append("expense_not_approved")
    else:
        problemas.append("no_expense")
    f.expected_amount = esperado
    f.difference = round(f.amount - esperado, 2) if esperado is not None else None
    f.issues = json.dumps(problemas)
    if f.status != "accepted":
        f.status = "matched" if not problemas else "discrepancy"
    f.reconciled_by = getattr(actor, "id", None)
    f.reconciled_at = timeutil.utcnow()
    if commit:
        db.commit()
    return f


def candidatos(db: Session, fid: str) -> list[dict]:
    """Gastos que pueden pagar la factura: categoría de ALM, importe dentro de la tolerancia,
    fecha cerca de la de la factura y sin enlazar a otra."""
    from app.models.expenses import Expense
    from app.services.alm_ajustes import ajuste_int, ajuste_lista
    f = factura(db, fid)
    tol = _tolerancia(db, f.organization_id)
    ventana = ajuste_int(db, "ALM_RECONCILIATION_EXPENSE_WINDOW_DAYS", f.organization_id)
    usados = {e for (e,) in db.query(ALMFacturaProveedor.expense_id).filter(
        ALMFacturaProveedor.expense_id.isnot(None), ALMFacturaProveedor.is_active.isnot(False),
        ALMFacturaProveedor.id != f.id)}
    categorias = ajuste_lista(db, "ALM_EXPENSE_CATEGORIES", f.organization_id)
    q = db.query(Expense).filter(Expense.is_active.isnot(False), Expense.category.in_(categorias),
                                 Expense.expense_date >= f.issue_date - timedelta(days=ventana),
                                 Expense.expense_date <= f.issue_date + timedelta(days=ventana))
    objetivo = [float(f.amount), float(f.amount) + float(f.tax_amount or 0)]
    salida = []
    for g in q.all():
        if g.id in usados:
            continue
        if not any(_cerca(float(g.amount or 0), o, tol) for o in objetivo):
            continue
        salida.append({"id": g.id, "code": g.code, "description": g.description, "amount": float(g.amount or 0),
                       "currency": g.currency, "expense_date": g.expense_date.isoformat() if g.expense_date else None,
                       "status": getattr(g.status, "value", g.status), "category": getattr(g.category, "value", g.category),
                       "project_id": g.project_id,
                       "days_from_invoice": abs((g.expense_date - f.issue_date).days) if g.expense_date else None})
    return sorted(salida, key=lambda c: (c["days_from_invoice"] or 0))


def vincular_gasto(db: Session, actor, fid: str, expense_id: Optional[str]) -> dict:
    from app.models.expenses import Expense
    f = factura(db, fid)
    if expense_id:
        if db.query(Expense.id).filter(Expense.id == expense_id).first() is None:
            raise ErrorDeDominio(404, "alm_gasto_no_encontrado")
        otra = db.query(ALMFacturaProveedor.id).filter(ALMFacturaProveedor.expense_id == expense_id,
                                                       ALMFacturaProveedor.id != f.id,
                                                       ALMFacturaProveedor.is_active.isnot(False)).first()
        if otra is not None:
            raise ErrorDeDominio(409, "alm_gasto_ya_enlazado")
    f.expense_id = expense_id or None
    if f.status == "accepted":
        f.status = "pending"
    conciliar(db, f, actor, commit=False)
    db.commit()
    return serializar(db, f)


def aceptar(db: Session, actor, fid: str, nota: Optional[str]) -> dict:
    f = factura(db, fid)
    if f.status != "discrepancy":
        raise ErrorDeDominio(409, "alm_factura_sin_discrepancia")
    if not (nota or "").strip():
        raise ErrorDeDominio(422, "alm_motivo_obligatorio")
    f.status = "accepted"
    f.notes = ((f.notes + "\n") if f.notes else "") + nota.strip()
    f.reconciled_by = getattr(actor, "id", None)
    f.reconciled_at = timeutil.utcnow()
    from app.services.audit import audit_log
    audit_log(db, actor, "APPROVE", "alm_vendor_invoice", f.id, f.number, new_values={"status": "accepted", "note": nota})
    db.commit()
    return serializar(db, f)


# ── Lectura ───────────────────────────────────────────────────────────────────

def serializar(db: Session, f: ALMFacturaProveedor) -> dict:
    try:
        problemas = json.loads(f.issues or "[]")
    except ValueError:
        problemas = []
    gasto = None
    if f.expense_id:
        from app.models.expenses import Expense
        g = db.get(Expense, f.expense_id)
        if g is not None:
            gasto = {"id": g.id, "code": g.code, "amount": float(g.amount or 0), "currency": g.currency,
                     "status": getattr(g.status, "value", g.status),
                     "expense_date": g.expense_date.isoformat() if g.expense_date else None}
    return {
        "id": f.id, "number": f.number, "vendor_id": f.vendor_id, "vendor_name": f.vendor.name if f.vendor else None,
        "contract_id": f.contract_id, "contract_title": f.contract.title if f.contract else None,
        "license_id": f.license_id, "license_name": f.license.name if f.license else None,
        "issue_date": f.issue_date.isoformat() if f.issue_date else None,
        "period_from": f.period_from.isoformat() if f.period_from else None,
        "period_to": f.period_to.isoformat() if f.period_to else None,
        "amount": f.amount, "tax_amount": f.tax_amount, "currency": f.currency,
        "expense_id": f.expense_id, "expense": gasto, "status": f.status,
        "expected_amount": f.expected_amount, "difference": f.difference, "issues": problemas,
        "notes": f.notes, "reconciled_at": f.reconciled_at.isoformat() if f.reconciled_at else None,
    }


def listar(db: Session, *, status=None, vendor_id=None, contract_id=None, pagina=None):
    from app.core.paginacion import paginar
    q = db.query(ALMFacturaProveedor).filter(ALMFacturaProveedor.is_active.isnot(False))
    if status:
        q = q.filter(ALMFacturaProveedor.status == status)
    if vendor_id:
        q = q.filter(ALMFacturaProveedor.vendor_id == vendor_id)
    if contract_id:
        q = q.filter(ALMFacturaProveedor.contract_id == contract_id)
    return paginar(q.order_by(ALMFacturaProveedor.issue_date.desc()), pagina, "alm.invoices").mapear(
        lambda f: serializar(db, f))


def periodos_sin_factura(db: Session, meses: int = 12) -> list[dict]:
    """Periodos de facturación de contratos activos de los últimos ``meses`` sin factura que los cubra."""
    from app.services.alm_renovaciones import MESES_POR_CICLO, sumar_meses
    hoy = timeutil.today()
    inicio_ventana = sumar_meses(date(hoy.year, hoy.month, 1), -max(1, meses))
    salida = []
    for c in db.query(ALMContract).filter(ALMContract.is_active.isnot(False), ALMContract.annual_value.isnot(None)).all():
        ciclo = getattr(c.billing_cycle, "value", c.billing_cycle) or "annual"
        if ciclo == "one_time" or getattr(c.status, "value", c.status) != "active" or not c.start_date:
            continue
        paso = MESES_POR_CICLO.get(ciclo, 12)
        facturas = [(f.period_from or f.issue_date, f.period_to or f.issue_date) for f in db.query(ALMFacturaProveedor)
                    .filter(ALMFacturaProveedor.contract_id == c.id, ALMFacturaProveedor.is_active.isnot(False))]
        p0 = c.start_date
        while p0 <= hoy:
            p1 = sumar_meses(p0, paso) - timedelta(days=1)
            if c.end_date and p0 > c.end_date:
                break
            if p1 >= inicio_ventana and p1 < hoy:
                cubierto = any(d <= p0 + timedelta(days=15) and h >= p1 - timedelta(days=15) for d, h in facturas)
                if not cubierto:
                    salida.append({"contract_id": c.id, "contract_title": c.title,
                                   "vendor_name": c.vendor.name if c.vendor else None, "period_from": p0.isoformat(),
                                   "period_to": p1.isoformat(), "expected_amount": importe_esperado(c.annual_value, p0, p1),
                                   "currency": c.currency, "billing_cycle": ciclo})
            p0 = sumar_meses(p0, paso)
    return salida


def gastos_conciliados(db: Session) -> set:
    """Ids de gastos que pagan una factura de ALM (no cuentan dos veces en la rentabilidad)."""
    return {e for (e,) in db.query(ALMFacturaProveedor.expense_id).filter(
        ALMFacturaProveedor.expense_id.isnot(None), ALMFacturaProveedor.is_active.isnot(False))}
