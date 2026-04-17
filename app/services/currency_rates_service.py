from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.models.billing_reports import Invoice, InvoiceStatus
from app.models.bookings import ExchangeRate
from app.models.expenses import Expense


def list_exchange_rates(
    db: Session,
    base_currency: Optional[str] = None,
    target_currency: Optional[str] = None,
) -> list:
    q = db.query(ExchangeRate)
    if base_currency:
        q = q.filter(ExchangeRate.from_currency == base_currency.upper())
    if target_currency:
        q = q.filter(ExchangeRate.to_currency == target_currency.upper())
    return q.order_by(ExchangeRate.effective_date.desc()).limit(200).all()


def upsert_exchange_rate(
    db: Session,
    from_currency: str,
    to_currency: str,
    rate: float,
    effective_date: date,
    source: str = "manual",
) -> tuple:
    """Returns (rate_obj, created: bool)."""
    existing = db.query(ExchangeRate).filter(
        ExchangeRate.from_currency == from_currency,
        ExchangeRate.to_currency == to_currency,
        ExchangeRate.effective_date == effective_date,
    ).first()
    if existing:
        existing.rate = rate
        existing.source = source
        db.commit()
        db.refresh(existing)
        return existing, False
    rate_obj = ExchangeRate(
        from_currency=from_currency,
        to_currency=to_currency,
        rate=rate,
        effective_date=effective_date,
        source=source,
    )
    db.add(rate_obj)
    db.commit()
    db.refresh(rate_obj)
    return rate_obj, True


def get_rate(
    db: Session,
    from_c: str,
    to_c: str,
    ref_date: date,
) -> Optional[ExchangeRate]:
    """Return the latest ExchangeRate for from_c -> to_c on or before ref_date."""
    return (
        db.query(ExchangeRate)
        .filter(
            ExchangeRate.from_currency == from_c,
            ExchangeRate.to_currency == to_c,
            ExchangeRate.effective_date <= ref_date,
        )
        .order_by(ExchangeRate.effective_date.desc())
        .first()
    )


def get_rate_inverse(
    db: Session,
    from_c: str,
    to_c: str,
    ref_date: date,
) -> Optional[ExchangeRate]:
    """Return ExchangeRate for to_c -> from_c (inverse direction)."""
    return (
        db.query(ExchangeRate)
        .filter(
            ExchangeRate.from_currency == to_c,
            ExchangeRate.to_currency == from_c,
            ExchangeRate.effective_date <= ref_date,
        )
        .order_by(ExchangeRate.effective_date.desc())
        .first()
    )


def resolve_rate(db: Session, from_c: str, to_c: str, ref_date: date) -> float:
    """Resolve conversion rate from_c->to_c, falling back to inverse. Returns 1.0 if not found."""
    if from_c == to_c:
        return 1.0
    r = get_rate(db, from_c, to_c, ref_date)
    if r:
        return r.rate
    r2 = get_rate_inverse(db, from_c, to_c, ref_date)
    return (1.0 / r2.rate) if r2 and r2.rate else 1.0


def get_report_data(
    db: Session,
    target: str,
    ref_date: date,
) -> tuple:
    """Return (invoices, expenses) for the multi-currency report."""

    invoices = db.query(Invoice).filter(Invoice.status != InvoiceStatus.cancelled).all()
    expenses = db.query(Expense).all()
    return invoices, expenses
