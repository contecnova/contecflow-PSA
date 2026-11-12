"""Facturas recurrentes: plantillas y generacion periodica.

Parte de `app.services.bookings_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from app.models.billing_reports import Invoice, InvoiceLine
from app.models.bookings import RecurringInvoice
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from app.core import timeutil
from app.core.asignacion import es_asignable
from app.core.errores import ErrorDeDominio

from app.services.bookings_service._comun import logger


def serialize_recurring(r) -> dict:
    return {
        "id": r.id, "name": r.name,
        "project_id": r.project_id,
        "project_name": r.project.name if r.project else None,
        "frequency": r.frequency,
        "next_date": str(r.next_date) if r.next_date else None,
        "end_date": str(r.end_date) if r.end_date else None,
        "is_active": r.is_active,
        "client_name": r.client_name,
        "client_email": r.client_email,
        "amount": r.amount, "tax_rate": r.tax_rate,
        "total": round(r.amount * (1 + r.tax_rate / 100), 2),
        "currency": r.currency,
        "description": r.description,
        "payment_terms_days": r.payment_terms_days,
        "last_generated_at": str(r.last_generated_at)[:10] if r.last_generated_at else None,
        "total_generated": r.total_generated or 0,
    }


# ── Recurring Invoices ────────────────────────────────────────────────────────

def list_recurring_records(db) -> list:
    items = db.query(RecurringInvoice).options(joinedload(RecurringInvoice.project)).order_by(RecurringInvoice.next_date).all()
    return [serialize_recurring(r) for r in items]


def create_recurring_record(payload, created_by_id, db) -> dict:
    r = RecurringInvoice(created_by=created_by_id, **payload.model_dump())
    db.add(r); db.commit(); db.refresh(r)
    return serialize_recurring(r)


def update_recurring_record(rec_id: str, payload: dict, db) -> dict:
    r = db.query(RecurringInvoice).filter(RecurringInvoice.id == rec_id).first()
    if not r: raise ErrorDeDominio(404)
    for k, v in payload.items():
        if es_asignable(r, k): setattr(r, k, v)
    db.commit()
    return {"ok": True}


def process_due_recurring_records(db, current_user) -> dict:
    today = timeutil.today()
    due = db.query(RecurringInvoice).filter(
        RecurringInvoice.is_active == True,
        RecurringInvoice.next_date <= today,
    ).all()
    generated = []
    for r in due:
        try:
            generate_recurring_now_record(r.id, db, current_user)
            generated.append(r.id)
        except Exception as e:
            logger.warning(f"Failed to generate recurring item {r.id}: {e}", exc_info=True)
    return {"processed": len(due), "generated": len(generated)}


def generate_recurring_now_record(rec_id: str, db, current_user) -> dict:
    import re as _re
    import calendar as _cal
    r = db.query(RecurringInvoice).options(joinedload(RecurringInvoice.project)).filter(RecurringInvoice.id == rec_id).first()
    if not r: raise ErrorDeDominio(404)
    if not r.is_active: raise ErrorDeDominio(400, "Factura recurrente inactiva")
    year = datetime.now(timezone.utc).year
    max_inv = db.query(func.max(Invoice.number)).filter(Invoice.number.like(f"INV-{year}-%")).scalar()
    if max_inv:
        _m = _re.search(r"(\d+)$", max_inv)
        next_inv_num = (int(_m.group(1)) + 1) if _m else 1
    else:
        next_inv_num = 1
    inv_number = f"INV-{year}-{next_inv_num:04d}"
    subtotal   = r.amount
    tax_amount = round(subtotal * r.tax_rate / 100, 2)
    total      = round(subtotal + tax_amount, 2)
    inv = Invoice(
        number=inv_number, project_id=r.project_id, contract_id=r.contract_id,
        client_name=r.client_name or (r.project.client_name if r.project else None),
        client_email=r.client_email, client_vat=r.client_vat,
        issue_date=timeutil.today(),
        due_date=timeutil.today() + timedelta(days=r.payment_terms_days),
        tax_rate=r.tax_rate, tax_amount=tax_amount,
        subtotal=subtotal, total=total, currency=r.currency,
        notes=f"Generada automáticamente de serie: {r.name}",
        created_by=current_user.id,
    )
    db.add(inv); db.flush()
    if r.description:
        db.add(InvoiceLine(
            invoice_id=inv.id, order=0,
            description=r.description or r.name,
            quantity=1, unit="servicio",
            unit_price=subtotal, discount_pct=0, amount=subtotal,
            source_type="recurring",
        ))
    freq = r.frequency.value if hasattr(r.frequency, "value") else str(r.frequency)
    if freq == "weekly":
        r.next_date = r.next_date + timedelta(weeks=1)
    elif freq == "monthly":
        m = r.next_date.month + 1
        y = r.next_date.year + (m - 1) // 12
        m = ((m - 1) % 12) + 1
        day = min(r.next_date.day, _cal.monthrange(y, m)[1])
        r.next_date = r.next_date.replace(year=y, month=m, day=day)
    elif freq == "quarterly":
        m = r.next_date.month + 3
        y = r.next_date.year + (m - 1) // 12
        m = ((m - 1) % 12) + 1
        day = min(r.next_date.day, _cal.monthrange(y, m)[1])
        r.next_date = r.next_date.replace(year=y, month=m, day=day)
    elif freq == "annually":
        y   = r.next_date.year + 1
        day = min(r.next_date.day, _cal.monthrange(y, r.next_date.month)[1])
        r.next_date = r.next_date.replace(year=y, day=day)
    if r.end_date and r.next_date > r.end_date:
        r.is_active = False
    r.last_generated_at = datetime.now(timezone.utc)
    r.total_generated   = (r.total_generated or 0) + 1
    db.commit()
    return {"ok": True, "invoice_id": inv.id, "invoice_number": inv_number, "next_date": str(r.next_date)}
