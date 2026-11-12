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
    from app.services.exchange_rate_service import PROPIOS_PRIMERO
    return q.order_by(ExchangeRate.effective_date.desc(), PROPIOS_PRIMERO).limit(200).all()


def upsert_exchange_rate(
    db: Session,
    from_currency: str,
    to_currency: str,
    rate: float,
    effective_date: date,
    source: str = "manual",
) -> tuple:
    """Returns (rate_obj, created: bool, previous_snapshot: dict|None).

    Revisión 2026-11: el tipo manual es de la empresa de la sesión (sin empresa:
    global). Antes actualizaba el primero que encontrara, también el global.
    """
    from app.services.exchange_rate_service import org_de_la_sesion, solo_de
    org = org_de_la_sesion(db)
    existing_q = solo_de(db.query(ExchangeRate), org).filter(
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
        organization_id=org,
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


def registrar_tipo_de_cambio(
    db: Session,
    current_user,
    *,
    from_currency: str,
    to_currency: str,
    rate: float,
    effective_date: date,
    source: str = "manual",
) -> tuple:
    """Alta o actualizacion manual del tipo, con su auditoria, y confirma.

    Devuelve (rate_obj, created).
    """
    from app.services.audit import audit_log

    rate_obj, created, previous_snapshot = upsert_exchange_rate(
        db,
        from_currency=from_currency,
        to_currency=to_currency,
        rate=rate,
        effective_date=effective_date,
        source=source,
    )
    audit_log(
        db,
        current_user,
        "CREATE" if created else "UPDATE",
        "exchange_rates",
        rate_obj.id,
        f"{rate_obj.from_currency}->{rate_obj.to_currency}@{rate_obj.effective_date}",
        old_values=previous_snapshot,
        new_values={
            "id": rate_obj.id,
            "rate": rate_obj.rate,
            "source": rate_obj.source,
            "effective_date": str(rate_obj.effective_date),
        },
    )
    db.commit()
    return rate_obj, created


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
        .order_by(ExchangeRate.effective_date.desc(), ExchangeRate.organization_id.is_(None))
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
        .order_by(ExchangeRate.effective_date.desc(), ExchangeRate.organization_id.is_(None))
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


def registrar_conversion(db: Session, **datos) -> None:
    """`log_currency_conversion` y confirma: la traza de una conversion pedida por la API."""
    log_currency_conversion(db, **datos)
    db.commit()


def get_report_data(
    db: Session,
    target: str,
    ref_date: date,
) -> tuple:
    """Return (invoices, expenses) for the multi-currency report."""

    invoices = db.query(Invoice).filter(Invoice.status != InvoiceStatus.cancelled).all()
    expenses = db.query(Expense).all()
    return invoices, expenses
