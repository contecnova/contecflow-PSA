from datetime import date
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin, require_any_manager
from app.db.session import get_db
from app.models.billing_reports import InvoiceStatus
from app.models.user import User
from app.services.audit import audit_log
from app.services import currency_rates_service
from app.schemas.currency_rates import ExchangeRateCreate
from app.core.responses import APIListResponse, APIResponse
from app.core import timeutil

router = APIRouter()


class ConvertCurrencyRequest(BaseModel):
    amount: float
    from_currency: str
    to_currency: str
    as_of_date: Optional[date] = Field(default=None, alias="date")

    model_config = {
        "populate_by_name": True,
    }


def _validate_currency_code(code: str) -> str:
    normalized = (code or "").upper().strip()
    if len(normalized) != 3 or not normalized.isalpha():
        raise HTTPException(status_code=422, detail="Currency codes must be 3-letter ISO values")
    return normalized


@router.get("/currency/rates", summary="List exchange rates")
def list_exchange_rates(
    base_currency: Optional[str] = Query(None),
    target_currency: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rates = currency_rates_service.list_exchange_rates(db, base_currency, target_currency)
    items = [
        {
            "id": r.id,
            "from_currency": r.from_currency,
            "to_currency": r.to_currency,
            "rate": r.rate,
            "effective_date": str(r.effective_date),
            "source": r.source,
        }
        for r in rates
    ]
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/currency/rates", summary="Create/update exchange rate", status_code=201)
def upsert_exchange_rate(
    payload: ExchangeRateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    from_c = _validate_currency_code(payload.from_currency)
    to_c = _validate_currency_code(payload.to_currency)
    if payload.rate <= 0:
        raise HTTPException(status_code=400, detail="Rate must be positive")
    eff = payload.effective_date or timeutil.today()
    rate_obj, created, previous_snapshot = currency_rates_service.upsert_exchange_rate(
        db,
        from_currency=from_c,
        to_currency=to_c,
        rate=payload.rate,
        effective_date=eff,
        source=payload.source or "manual",
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
    if created:
        return APIResponse.ok(data={
            "id": rate_obj.id,
            "from_currency": rate_obj.from_currency,
            "to_currency": rate_obj.to_currency,
            "rate": rate_obj.rate,
            "effective_date": str(rate_obj.effective_date),
            "source": rate_obj.source,
            "created": True,
        })
    return APIResponse.ok(data={
        "id": rate_obj.id,
        "from_currency": rate_obj.from_currency,
        "to_currency": rate_obj.to_currency,
        "rate": rate_obj.rate,
        "effective_date": str(rate_obj.effective_date),
        "source": rate_obj.source,
        "updated": True,
    })


def _convert_currency_impl(
    *,
    amount: float,
    from_currency: str,
    to_currency: str,
    as_of_date: Optional[date],
    db: Session,
    current_user: User,
):
    from_c = _validate_currency_code(from_currency)
    to_c = _validate_currency_code(to_currency)
    if amount < 0:
        raise HTTPException(status_code=422, detail="Amount must be non-negative")

    if from_c == to_c:
        return {
            "amount": amount,
            "from": from_c,
            "to": to_c,
            "rate": 1.0,
            "converted": amount,
            "converted_amount": amount,
        }

    ref_date = as_of_date or timeutil.today()
    snapshot = currency_rates_service.resolve_rate_with_snapshot(db, from_c, to_c, ref_date)
    if snapshot["source"] == "fallback":
        raise HTTPException(status_code=404, detail=f"No exchange rate found for {from_c}->{to_c}")

    converted = amount * snapshot["rate"]
    currency_rates_service.log_currency_conversion(
        db,
        organization_id=getattr(current_user, "organization_id", None),
        entity_type="currency_conversion",
        entity_id=str(uuid.uuid4()),
        from_currency=from_c,
        to_currency=to_c,
        original_amount=amount,
        converted_amount=round(converted, 2),
        rate_used=float(snapshot["rate"]),
        rate_date=date.fromisoformat(snapshot["rate_date"]),
    )
    db.commit()

    return {
        "amount": amount,
        "from": from_c,
        "to": to_c,
        "rate": round(float(snapshot["rate"]), 6),
        "converted": round(converted, 2),
        "converted_amount": round(converted, 2),
        "rate_date": snapshot["rate_date"],
        "source": snapshot["source"],
        "rate_id": snapshot["rate_id"],
    }


@router.get("/currency/convert", summary="Convert amount between currencies")
def convert_currency(
    amount: float = Query(...),
    from_currency: str = Query(...),
    to_currency: str = Query(...),
    as_of_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data=_convert_currency_impl(
        amount=amount,
        from_currency=from_currency,
        to_currency=to_currency,
        as_of_date=as_of_date,
        db=db,
        current_user=current_user,
    ))


@router.post("/currency/convert", summary="Convert amount between currencies (legacy POST)")
def convert_currency_post(
    payload: ConvertCurrencyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data=_convert_currency_impl(
        amount=payload.amount,
        from_currency=payload.from_currency,
        to_currency=payload.to_currency,
        as_of_date=payload.as_of_date,
        db=db,
        current_user=current_user,
    ))


@router.get("/currency/report", summary="Multi-currency consolidated report")
def multicurrency_report(
    report_currency: str = Query(default="EUR", description="Target currency for consolidation"),
    as_of_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    ref_date = as_of_date or timeutil.today()
    target = report_currency.upper()

    def _get_rate(from_c: str) -> float:
        return currency_rates_service.resolve_rate(db, from_c, target, ref_date)

    invoices, expenses = currency_rates_service.get_report_data(db, target, ref_date)

    inv_total = sum((i.total or 0) * _get_rate(i.currency or target) for i in invoices)
    inv_paid = sum((i.total or 0) * _get_rate(i.currency or target) for i in invoices if i.status == InvoiceStatus.paid)
    exp_total = sum((e.amount or 0) * _get_rate(e.currency or target) for e in expenses if e.status in ("approved", "paid"))

    currencies_seen = set(i.currency for i in invoices if i.currency) | set(e.currency for e in expenses if e.currency)
    breakdown = []
    for curr in sorted(currencies_seen):
        rate = _get_rate(curr)
        breakdown.append(
            {
                "currency": curr,
                "rate_to_target": rate,
                "invoices_total": round(sum((i.total or 0) for i in invoices if i.currency == curr), 2),
                "invoices_in_target": round(sum((i.total or 0) * rate for i in invoices if i.currency == curr), 2),
                "expenses_total": round(
                    sum((e.amount or 0) for e in expenses if e.currency == curr and e.status in ("approved", "paid")),
                    2,
                ),
            }
        )

    return APIResponse.ok(data={
        "report_currency": target,
        "as_of_date": str(ref_date),
        "consolidated": {
            "total_invoiced": round(inv_total, 2),
            "total_paid": round(inv_paid, 2),
            "total_outstanding": round(inv_total - inv_paid, 2),
            "total_expenses": round(exp_total, 2),
        },
        "by_currency": breakdown,
    })
