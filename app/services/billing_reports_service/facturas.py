"""Facturas: alta, edicion, estados, resumen y enlace de cobro.

Parte de `app.services.billing_reports_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import enum
import json
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import OperationalError
from typing import Optional
from app.core.config import settings
from app.models.user import User
from app.models.imputation import Imputation
from app.models.billing_reports import Invoice, InvoiceLine
from app.services.audit import audit_log
from app.services.numbering import next_numbered_code
from app.schemas.billing_reports import InvoiceOut, InvoiceLineOut
from app.models.billing_reports import InvoiceLine as _InvoiceLine
from app.db.session import is_postgres
from app.core import timeutil
from app.core.errores import ErrorDeDominio

from app.services.billing_reports_service._comun import (
    _is_serialization_failure,
    _lock_project_for_update,
    _logger,
    _scope_invoice_query,
    _set_serializable_if_postgres,
    _tenant_org_id,
)


# Obtener una factura por ID
def get_invoice_by_id(db: Session, invoice_id: str):
    return _scope_invoice_query(db).filter(Invoice.id == invoice_id).first()


def crear_enlace_de_pago(db: Session, invoice_id: str) -> dict:
    """Enlace de cobro de Stripe para la factura; lo guarda en ella y confirma.

    Reutiliza el enlace ya generado (idempotente de cara al usuario).
    """
    from app.models.billing_reports import InvoiceStatus
    from app.services import stripe_service

    invoice = get_invoice_by_id(db, invoice_id)
    if not invoice:
        raise ErrorDeDominio(status_code=404, detail="Invoice not found")
    if not stripe_service.is_configured():
        # Honesto: la funcionalidad no está disponible hasta configurar Stripe,
        # en vez de un 503 que sugiere un fallo transitorio.
        raise ErrorDeDominio(
            status_code=501,
            detail="El cobro con Stripe no está disponible: configura STRIPE_SECRET_KEY.",
        )
    if invoice.status == InvoiceStatus.paid:
        raise ErrorDeDominio(status_code=409, detail="La factura ya está pagada.")
    if invoice.stripe_payment_link_url:
        return {"url": invoice.stripe_payment_link_url, "id": invoice.stripe_payment_link_id, "reused": True}
    try:
        session = stripe_service.create_checkout_session(
            invoice_id=invoice.id,
            invoice_number=invoice.number,
            amount=invoice.total or 0,
            currency=invoice.currency or settings.DEFAULT_CURRENCY,
            success_url=f"{settings.FRONTEND_URL}/invoices/{invoice.id}?paid=1",
            cancel_url=f"{settings.FRONTEND_URL}/invoices/{invoice.id}?canceled=1",
            customer_email=invoice.client_email,
        )
    except stripe_service.StripeError as e:
        raise ErrorDeDominio(status_code=502, detail=str(e))
    invoice.stripe_payment_link_url = session["url"]
    invoice.stripe_payment_link_id = session["id"]
    if session.get("payment_intent"):
        invoice.stripe_payment_intent_id = session["payment_intent"]
    db.commit()
    return {"url": session["url"], "id": session["id"], "reused": False}


# Devuelve un query filtrable y el total para paginación de facturas
def query_invoices(db: Session, project_id=None, status=None):
    q = _scope_invoice_query(db)
    if project_id:
        q = q.filter(Invoice.project_id == project_id)
    if status:
        q = q.filter(Invoice.status == status)
    total = q.count()
    return q.order_by(Invoice.issue_date.desc()), total


# ═══════════════════════════════════════════════════════════════════════════════
# INVOICE HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def next_invoice_number(db: Session) -> str:
    return next_numbered_code(
        db,
        "invoice",
        prefix="INV",
        padding=4,
        include_year=True,
        reset_yearly=True,
        year_separator="-",
    )


def invoice_out(inv: Invoice) -> dict:
    return InvoiceOut(
        id=inv.id,
        number=inv.number,
        project_id=inv.project_id,
        client_id=inv.client_id,
        project_name=inv.project.name if inv.project else None,
        project_code=inv.project.code if inv.project else None,
        client_name=inv.client_name,
        client_email=inv.client_email,
        client_vat=inv.client_vat,
        subtotal=inv.subtotal,
        tax_rate=inv.tax_rate,
        tax_amount=inv.tax_amount,
        total=inv.total,
        currency=inv.currency,
        issue_date=inv.issue_date,
        due_date=inv.due_date,
        paid_date=inv.paid_date,
        status=inv.status,
        notes=inv.notes,
        po_reference=inv.po_reference,
        period_from=inv.period_from,
        period_to=inv.period_to,
        lines=[
            InvoiceLineOut(
                id=l.id, order=l.order, description=l.description,
                quantity=l.quantity, unit=l.unit,
                unit_price=l.unit_price, discount_pct=l.discount_pct,
                amount=l.amount, source_type=l.source_type,
            )
            for l in inv.lines
        ],
        created_at=inv.created_at.date() if inv.created_at else None,
    ).model_dump()


# ═══════════════════════════════════════════════════════════════════════════════
# INVOICE CRUD
# ═══════════════════════════════════════════════════════════════════════════════

def create_invoice(payload, current_user: User, db: Session) -> dict:
    _set_serializable_if_postgres(db)
    project = None
    if payload.project_id:
        project = _lock_project_for_update(db, payload.project_id)
        if not project:
            raise ErrorDeDominio(status_code=404, detail="Proyecto no encontrado o no accesible")

    client_name = payload.client_name or (project.client_name if project else None) or "Sin cliente"
    # Revisión 2026-11: el importe de cada línea lo calcula el servidor (antes se
    # aceptaba el `amount` que mandara el navegador).
    for l in payload.lines:
        l["amount"] = importe_de_linea(l)
    subtotal = sum(l.get("amount", 0) for l in payload.lines)
    tax_amount = round(subtotal * payload.tax_rate / 100, 2)
    total = round(subtotal + tax_amount, 2)

    inv = Invoice(
        number=next_invoice_number(db),
        organization_id=(getattr(current_user, "organization_id", None) if not getattr(current_user, "is_superadmin", False) else getattr(project, "organization_id", None)),
        project_id=payload.project_id,
        contract_id=payload.contract_id,
        client_name=client_name,
        client_address=payload.client_address,
        client_vat=payload.client_vat,
        client_email=payload.client_email,
        issue_date=payload.issue_date,
        due_date=payload.due_date,
        tax_rate=payload.tax_rate,
        tax_amount=tax_amount,
        subtotal=round(subtotal, 2),
        total=total,
        currency=payload.currency,
        notes=payload.notes,
        po_reference=payload.po_reference,
        period_from=payload.period_from,
        period_to=payload.period_to,
        created_by=current_user.id,
    )
    db.add(inv)
    db.flush()

    for i, line_data in enumerate(payload.lines):
        line = InvoiceLine(
            invoice_id=inv.id, order=i,
            description=line_data.get("description", ""),
            quantity=line_data.get("quantity", 1),
            unit=line_data.get("unit", "h"),
            unit_price=line_data.get("unit_price", 0),
            discount_pct=line_data.get("discount_pct", 0),
            amount=line_data.get("amount", 0),
            source_type=line_data.get("source_type"),
            source_ids=json.dumps(line_data.get("source_ids", [])),
        )
        db.add(line)

    for line_data in payload.lines:
        if line_data.get("source_type") == "timesheet":
            raw_ids = line_data.get("source_ids", [])
            imp_ids = json.loads(raw_ids) if isinstance(raw_ids, str) else raw_ids
            if imp_ids:
                db.query(Imputation).filter(Imputation.id.in_(imp_ids)).update(
                    {"is_invoiced": True, "invoiced_invoice_id": inv.id},
                    synchronize_session=False,
                )

    audit_log(db, current_user, "CREATE", "invoices", inv.id, inv.number)
    try:
        db.commit()
    except OperationalError as exc:
        db.rollback()
        if _is_serialization_failure(exc):
            raise ErrorDeDominio(status_code=409, detail="Concurrent financial update detected. Please retry.")
        raise
    try:
        from app.core.metrics import invoices_created_total
        _status = getattr(inv, "status", None)
        invoices_created_total.labels(
            tenant_id=str(getattr(inv, "organization_id", None) or "unknown"),
            status=str(getattr(_status, "value", _status) or "draft"),
        ).inc()
    except Exception:
        _logger.debug("create_invoice: fallo best-effort ignorado", exc_info=True)
    inv = db.query(Invoice).options(
        joinedload(Invoice.project), joinedload(Invoice.lines)
    ).filter(Invoice.id == inv.id).first()
    return invoice_out(inv)


def importe_de_linea(linea: dict) -> float:
    """cantidad × precio × (1 − descuento %), redondeado a céntimos."""
    cantidad = float(linea.get("quantity", 1) or 0)
    precio = float(linea.get("unit_price", 0) or 0)
    descuento = float(linea.get("discount_pct", 0) or 0)
    return round(cantidad * precio * (1 - descuento / 100), 2)


# ── Ficha, edición y borrado (revisión 2026-11) ─────────────────────────────
# La pantalla sólo dejaba enviar, marcar como pagada y bajar el PDF: no había
# forma de abrir una factura ni de corregir un borrador. Una factura ENVIADA no
# se modifica (es un documento emitido): se anula y se hace otra.

_CABECERA_EDITABLE = ("client_name", "client_address", "client_vat", "client_email", "issue_date", "due_date",
                      "tax_rate", "notes", "po_reference", "period_from", "period_to", "currency")


def _factura(db: Session, invoice_id: str, *, bloquear: bool = False) -> Invoice:
    q = _scope_invoice_query(db).options(joinedload(Invoice.project), joinedload(Invoice.lines)) \
        .filter(Invoice.id == invoice_id)
    if bloquear and is_postgres():
        q = q.with_for_update(of=Invoice)   # sólo la factura: las uniones externas no se pueden bloquear
    inv = q.first()
    if not inv:
        raise ErrorDeDominio(404, "Factura no encontrada")
    return inv


def _exigir_borrador(inv: Invoice) -> None:
    estado = inv.status.value if isinstance(inv.status, enum.Enum) else str(inv.status)
    if estado != "draft":
        raise ErrorDeDominio(409, "Sólo se modifica un borrador: una factura emitida se anula y se hace otra")


def _imputaciones_de(lineas: list) -> set:
    ids = set()
    for l in lineas:
        if l.get("source_type") == "timesheet":
            crudo = l.get("source_ids") or []
            ids |= set(json.loads(crudo) if isinstance(crudo, str) else crudo)
    return ids


def obtener_factura(db: Session, invoice_id: str) -> dict:
    return invoice_out(_factura(db, invoice_id))


def editar_factura(db: Session, current_user: User, invoice_id: str, datos: dict) -> dict:
    """Cabecera y/o líneas de un borrador; los totales se recalculan."""
    inv = _factura(db, invoice_id, bloquear=True)
    _exigir_borrador(inv)
    antes = {"total": float(inv.total or 0), "lines": len(inv.lines)}
    for campo in _CABECERA_EDITABLE:
        if campo in datos:
            setattr(inv, campo, datos[campo])
    if "lines" in datos:
        nuevas = list(datos["lines"] or [])
        # Las horas que deja de facturar vuelven a estar libres; las nuevas se marcan.
        db.query(Imputation).filter(Imputation.invoiced_invoice_id == inv.id).update(
            {"is_invoiced": False, "invoiced_invoice_id": None}, synchronize_session=False)
        for l in list(inv.lines):
            db.delete(l)
        db.flush()
        for i, l in enumerate(nuevas):
            db.add(InvoiceLine(invoice_id=inv.id, order=i, description=l.get("description", ""),
                               quantity=l.get("quantity", 1), unit=l.get("unit", "h"),
                               unit_price=l.get("unit_price", 0), discount_pct=l.get("discount_pct", 0),
                               amount=importe_de_linea(l), source_type=l.get("source_type"),
                               source_ids=json.dumps(l.get("source_ids", []) if not isinstance(l.get("source_ids"), str)
                                                     else json.loads(l["source_ids"])),
                               organization_id=inv.organization_id))
        horas = _imputaciones_de(nuevas)
        if horas:
            db.query(Imputation).filter(Imputation.id.in_(horas)).update(
                {"is_invoiced": True, "invoiced_invoice_id": inv.id}, synchronize_session=False)
        subtotal = round(sum(importe_de_linea(l) for l in nuevas), 2)
    else:
        subtotal = round(sum(float(l.amount or 0) for l in inv.lines), 2)
    inv.subtotal = subtotal
    inv.tax_amount = round(subtotal * float(inv.tax_rate or 0) / 100, 2)
    inv.total = round(subtotal + float(inv.tax_amount), 2)
    audit_log(db, current_user, "UPDATE", "invoices", inv.id, inv.number, old_values=antes,
              new_values={"total": float(inv.total), "lines": len(datos.get("lines", inv.lines))})
    db.commit()
    db.expire_all()
    return obtener_factura(db, invoice_id)


def liberar_lo_facturado(db: Session, inv) -> None:
    """Devuelve a «por facturar» lo que esta factura había marcado.

    Revisión 2026-11. Medido antes: anular una factura no soltaba sus horas
    (`Imputation.is_invoiced`) ni sus hitos (`billing_status="invoiced"`), así
    que no se podían volver a facturar nunca; borrar un borrador soltaba las
    horas pero no los hitos. Ahora borrar y anular pasan por aquí.
    """
    from app.models.financial import ProjectMilestone
    db.query(Imputation).filter(Imputation.invoiced_invoice_id == inv.id).update(
        {"is_invoiced": False, "invoiced_invoice_id": None}, synchronize_session=False)
    db.query(ProjectMilestone).filter(ProjectMilestone.invoice_id == inv.id).update(
        {"invoice_id": None, "is_billed": False, "billed_at": None, "billing_status": "approved"},
        synchronize_session=False)


def borrar_factura(db: Session, current_user: User, invoice_id: str) -> None:
    inv = _factura(db, invoice_id, bloquear=True)
    _exigir_borrador(inv)
    liberar_lo_facturado(db, inv)
    audit_log(db, current_user, "DELETE", "invoices", inv.id, inv.number, old_values={"total": float(inv.total or 0)})
    db.delete(inv)
    db.commit()


def _aprobacion_antes_de_enviar(inv, current_user: User, db: Session) -> None:
    """Con un flujo por defecto para facturas, enviarla pasa por la bandeja.

    Auditoria 2026-11: el disenador ofrecia el tipo «factura» y nada abria la
    solicitud. Sin flujo, todo sigue igual. Con flujo: la primera vez se abre
    la solicitud y la factura se queda en borrador (409 con el motivo); al
    aprobarse en la bandeja pasa a enviada.
    """
    from app.services.approval_engine import fuentes
    from app.services.approval_engine._base import elegir_flujo
    if not elegir_flujo(db, "invoice", {"amount": float(inv.total or 0),
                                        "department": getattr(current_user, "department", None)}):
        return
    estado = fuentes.estado(db, "invoice", inv.id)
    if estado == "approved":
        return
    if estado == "pending":
        raise ErrorDeDominio(409, "La factura está pendiente de aprobación en la bandeja")
    db.rollback()
    fuentes.abrir(db, "invoice", inv.id, f"Factura {inv.number} — {inv.client_name or ''}".strip(" —"),
                  current_user.id, {"amount": float(inv.total or 0), "project_id": inv.project_id})
    raise ErrorDeDominio(409, "La factura necesita aprobación: se ha enviado a la bandeja de aprobaciones")


def update_invoice_status(invoice_id: str, payload: dict, current_user: User, db: Session) -> dict:
    _set_serializable_if_postgres(db)
    inv_q = _scope_invoice_query(db).filter(Invoice.id == invoice_id)
    if is_postgres():
        inv_q = inv_q.with_for_update()
    inv = inv_q.first()
    if not inv:
        raise ErrorDeDominio(404)
    old_status = inv.status.value if isinstance(inv.status, enum.Enum) else str(inv.status)
    new_status = payload.get("status", old_status)
    # Definir transiciones válidas
    allowed_transitions = {
        "draft":    ["sent", "cancelled"],
        "sent":     ["paid", "overdue", "cancelled"],
        "overdue":  ["paid", "cancelled"],
        "paid":     [],
        "cancelled": [],
    }
    if new_status == old_status:
        db.commit()
        return invoice_out(inv)
    if new_status not in allowed_transitions.get(old_status, []):
        raise ErrorDeDominio(400, f"Transición de estado no permitida: {old_status} → {new_status}")
    if old_status == "draft" and new_status == "sent":
        _aprobacion_antes_de_enviar(inv, current_user, db)
    # Assign as Enum if possible
    from app.models.billing_reports import InvoiceStatus
    try:
        inv.status = InvoiceStatus(new_status)
    except Exception:
        _logger.warning("Estado de factura no es enum válido, usando string crudo: %s", new_status)
        inv.status = new_status
    if new_status == "paid":
        inv.paid_date = timeutil.today()
    if new_status == "cancelled":
        liberar_lo_facturado(db, inv)
    audit_log(db, current_user, "UPDATE", "invoices", inv.id, inv.number,
              old_values={"status": old_status}, new_values={"status": inv.status.value if isinstance(inv.status, enum.Enum) else str(inv.status)})
    try:
        db.commit()
    except OperationalError as exc:
        db.rollback()
        if _is_serialization_failure(exc):
            raise ErrorDeDominio(status_code=409, detail="Concurrent financial update detected. Please retry.")
        raise
    return invoice_out(inv)


def _a_moneda_base(db: Session, importe: float, moneda: str, base: str, fecha) -> Optional[float]:
    """El importe en la moneda de la empresa con el tipo vigente en la fecha; None si no hay tipo."""
    from app.services.currency_rates_service import get_rate, get_rate_inverse
    if not importe or (moneda or base) == base:
        return float(importe or 0)
    r = get_rate(db, moneda, base, fecha)
    if r and r.rate:
        return float(importe) * r.rate
    r = get_rate_inverse(db, moneda, base, fecha)
    return float(importe) / r.rate if r and r.rate else None


def get_invoice_summary(db: Session) -> dict:
    """Totales por estado en la moneda de la empresa (`DEFAULT_CURRENCY`).

    Revisión 2026-11: antes se sumaban los importes tal cual, en la moneda de
    cada factura. Ahora cada una se convierte con el tipo de su fecha de emisión;
    la que no tiene tipo de cambio no se suma y se dice aparte, por moneda.
    """
    from app.services.settings_service import get_runtime_str
    org_id = _tenant_org_id(db)
    base = (get_runtime_str(db, "DEFAULT_CURRENCY", org_id) or settings.DEFAULT_CURRENCY).upper()
    invoices = _scope_invoice_query(db).all()
    hoy = timeutil.today()
    by_status: dict = {}
    sin_tipo: dict = {}
    convertido: dict = {}
    for inv in invoices:
        v = _a_moneda_base(db, inv.total or 0, (inv.currency or base).upper(), base, inv.issue_date or hoy)
        if v is None:
            sin_tipo[inv.currency] = round(sin_tipo.get(inv.currency, 0) + float(inv.total or 0), 2)
        convertido[inv.id] = v or 0.0
        e = by_status.setdefault(inv.status, {"count": 0, "total": 0.0})
        e["count"] += 1
        e["total"] += convertido[inv.id]

    def suma(lista):
        return round(sum(convertido[i.id] for i in lista), 2)
    overdue = [i for i in invoices if i.status == "sent" and i.due_date and i.due_date < hoy]
    return {
        "currency": base,
        "by_status": {k: {"count": v["count"], "total": round(v["total"], 2)} for k, v in by_status.items()},
        "total_invoiced": suma(invoices),
        "total_paid": suma([i for i in invoices if i.status == "paid"]),
        "total_pending": suma([i for i in invoices if i.status in ["sent", "overdue"]]),
        "overdue_count": len(overdue),
        "overdue_amount": suma(overdue),
        "sin_tipo_de_cambio": sin_tipo,
    }


def list_invoices(project_id: str | None, status: str | None, db: Session) -> list:
    q = db.query(Invoice).options(joinedload(Invoice.project), joinedload(Invoice.lines))
    if project_id:
        q = q.filter(Invoice.project_id == project_id)
    if status:
        q = q.filter(Invoice.status == status)
    return [invoice_out(i) for i in q.order_by(Invoice.issue_date.desc()).all()]


def get_invoice_for_pdf(invoice_id: str, db: Session):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise ErrorDeDominio(404, "Factura no encontrada")
    lines = db.query(_InvoiceLine).filter(_InvoiceLine.invoice_id == invoice_id).order_by(_InvoiceLine.order).all()
    return inv, lines
