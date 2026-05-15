from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin, require_any_manager
from app.db.session import get_db
from app.models.billing_reports import InvoiceStatus
from app.models.user import User
from app.services import currency_rates_service
from app.schemas.currency_rates import ExchangeRateCreate
from app.core.responses import APIListResponse

router = APIRouter()


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
    if payload.rate <= 0:
        raise HTTPException(status_code=400, detail="Rate must be positive")
    eff = payload.effective_date or date.today()
    rate_obj, created = currency_rates_service.upsert_exchange_rate(
        db,
        from_currency=payload.from_currency.upper(),
        to_currency=payload.to_currency.upper(),
        rate=payload.rate,
        effective_date=eff,
        source=payload.source or "manual",
    )
    if created:
        return {"id": rate_obj.id, "rate": rate_obj.rate, "created": True}
    return {"id": rate_obj.id, "rate": rate_obj.rate, "updated": True}


@router.get("/currency/convert", summary="Convert amount between currencies")
def convert_currency(
    amount: float = Query(...),
    from_currency: str = Query(...),
    to_currency: str = Query(...),
    as_of_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from_c = from_currency.upper()
    to_c = to_currency.upper()
    if from_c == to_c:
        return {"amount": amount, "from": from_c, "to": to_c, "rate": 1.0, "converted": amount}
    ref_date = as_of_date or date.today()
    rate_obj = currency_rates_service.get_rate(db, from_c, to_c, ref_date)
    if not rate_obj:
        rate_obj_inv = currency_rates_service.get_rate_inverse(db, from_c, to_c, ref_date)
        if rate_obj_inv and rate_obj_inv.rate > 0:
            rate = 1.0 / rate_obj_inv.rate
            return {
                "amount": amount,
                "from": from_c,
                "to": to_c,
                "rate": round(rate, 6),
                "converted": round(amount * rate, 2),
                "rate_date": str(rate_obj_inv.effective_date),
                "source": rate_obj_inv.source,
            }
        raise HTTPException(status_code=404, detail=f"No exchange rate found for {from_c}->{to_c}")
    converted = amount * rate_obj.rate
    return {
        "amount": amount,
        "from": from_c,
        "to": to_c,
        "rate": rate_obj.rate,
        "converted": round(converted, 2),
        "rate_date": str(rate_obj.effective_date),
        "source": rate_obj.source,
    }


@router.get("/currency/report", summary="Multi-currency consolidated report")
def multicurrency_report(
    report_currency: str = Query(default="EUR", description="Target currency for consolidation"),
    as_of_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    ref_date = as_of_date or date.today()
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

    return {
        "report_currency": target,
        "as_of_date": str(ref_date),
        "consolidated": {
            "total_invoiced": round(inv_total, 2),
            "total_paid": round(inv_paid, 2),
            "total_outstanding": round(inv_total - inv_paid, 2),
            "total_expenses": round(exp_total, 2),
        },
        "by_currency": breakdown,
    }
