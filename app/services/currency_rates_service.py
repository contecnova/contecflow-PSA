from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.db.session import is_postgres
from app.models.billing_reports import Invoice, InvoiceStatus
from app.models.bookings import ExchangeRate
from app.models.exchange_rates_log import CurrencyConversionLog
from app.models.expenses import Expense
import logging

logger = logging.getLogger(__name__)


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
    """Returns (rate_obj, created: bool, previous_snapshot: dict|None)."""
    existing_q = db.query(ExchangeRate).filter(
        ExchangeRate.from_currency == from_currency,
        ExchangeRate.to_currency == to_currency,
        ExchangeRate.effective_date == effective_date,
    )
    if is_postgres():
        existing_q = existing_q.with_for_update()
    existing = existing_q.first()
    if existing:
        previous = {
            "id": existing.id,
            "rate": existing.rate,
            "source": existing.source,
            "effective_date": str(existing.effective_date),
        }
        existing.rate = rate
        existing.source = source
        db.commit()
        db.refresh(existing)
        return existing, False, previous
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
    return rate_obj, True, None


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


def resolve_rate_with_snapshot(db: Session, from_c: str, to_c: str, ref_date: date) -> dict:
    """Resolve FX rate plus immutable snapshot metadata used for auditing."""
    if from_c == to_c:
        return {
            "rate": 1.0,
            "rate_id": None,
            "rate_date": str(ref_date),
            "source": "identity",
        }

    direct = get_rate(db, from_c, to_c, ref_date)
    if direct:
        return {
            "rate": direct.rate,
            "rate_id": direct.id,
            "rate_date": str(direct.effective_date),
            "source": direct.source,
        }

    inverse = get_rate_inverse(db, from_c, to_c, ref_date)
    if inverse and inverse.rate:
        return {
            "rate": 1.0 / inverse.rate,
            "rate_id": inverse.id,
            "rate_date": str(inverse.effective_date),
            "source": f"inverse:{inverse.source}",
        }

    return {
        "rate": 1.0,
        "rate_id": None,
        "rate_date": str(ref_date),
        "source": "fallback",
    }


def log_currency_conversion(
    db: Session,
    *,
    organization_id: Optional[str],
    entity_type: str,
    entity_id: str,
    from_currency: str,
    to_currency: str,
    original_amount: float,
    converted_amount: float,
    rate_used: float,
    rate_date: date,
) -> None:
    db.add(
        CurrencyConversionLog(
            organization_id=organization_id,
            entity_type=entity_type,
            entity_id=entity_id,
            from_currency=from_currency,
            to_currency=to_currency,
            original_amount=original_amount,
            converted_amount=converted_amount,
            rate_used=rate_used,
            rate_date=rate_date,
        )
    )


def get_report_data(
    db: Session,
    target: str,
    ref_date: date,
) -> tuple:
    """Return (invoices, expenses) for the multi-currency report."""

    invoices = db.query(Invoice).filter(Invoice.status != InvoiceStatus.cancelled).all()
    expenses = db.query(Expense).all()
    return invoices, expenses
