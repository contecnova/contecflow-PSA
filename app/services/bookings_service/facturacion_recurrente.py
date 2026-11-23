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
from app.core.codigos_de_error import error


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
            generate_recurring_now_record(r.id, db, current_user, solo_si_toca=True)
            generated.append(r.id)
        except Exception as e:
            # M17 (auditoría 22-11-2026): sin rollback, un fallo dejaba la sesión
            # abortada y las siguientes plantillas fallaban todas.
            db.rollback()
            logger.warning(f"Failed to generate recurring item {r.id}: {e}", exc_info=True)
    return {"processed": len(due), "generated": len(generated)}


def generate_recurring_now_record(rec_id: str, db, current_user, solo_si_toca: bool = False) -> dict:
    import calendar as _cal
    from decimal import ROUND_HALF_UP, Decimal
    from app.db.session import is_postgres
    q = db.query(RecurringInvoice).options(joinedload(RecurringInvoice.project)).filter(RecurringInvoice.id == rec_id)
    # M17: la plantilla se bloquea mientras se genera: dos clics o dos workers no
    # sacan dos facturas del mismo periodo (el segundo ve la `next_date` ya movida).
    if is_postgres():
        q = q.with_for_update(of=RecurringInvoice)
    r = q.first()
    if not r: raise ErrorDeDominio(404)
    if not r.is_active: raise error(400, "factura_recurrente_inactiva")
    if solo_si_toca and r.next_date and r.next_date > timeutil.today():
        return {"ok": True, "skipped": True, "next_date": str(r.next_date)}
    # Auditoría 22-11-2026 (M17): la secuencia de facturas (`next_invoice_number`,
    # bloqueada); antes `max(INV-año)+1` ignoraba la secuencia y dos clics daban
    # el mismo número.
    from app.services.billing_reports_service.facturas import next_invoice_number
    inv_number = next_invoice_number(db)
    # M17: importes en céntimos exactos (Decimal, redondeo comercial), no float.
    _c = Decimal("0.01")
    sub_d      = Decimal(str(r.amount or 0)).quantize(_c, rounding=ROUND_HALF_UP)
    tax_d      = (sub_d * Decimal(str(r.tax_rate or 0)) / 100).quantize(_c, rounding=ROUND_HALF_UP)
    subtotal, tax_amount, total = float(sub_d), float(tax_d), float(sub_d + tax_d)
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
