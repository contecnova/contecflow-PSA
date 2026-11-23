"""Tipos de cambio de reservas y conversion de importes.

Parte de `app.services.bookings_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from datetime import date
from app.services.settings_service import por_empresa as _pe
from app.models.bookings import ExchangeRate
from sqlalchemy import func
from app.core import timeutil
from app.core.errores import ErrorDeDominio
from app.core.codigos_de_error import error


# ── Exchange Rates ────────────────────────────────────────────────────────────

def get_exchange_rates_data(base: str, db) -> dict:
    latest_rates = {}
    for row in db.query(
        ExchangeRate.from_currency, ExchangeRate.to_currency,
        func.max(ExchangeRate.effective_date).label("max_date")
    ).filter(ExchangeRate.from_currency == base).group_by(
        ExchangeRate.from_currency, ExchangeRate.to_currency
    ).all():
        rate = db.query(ExchangeRate).filter(
            ExchangeRate.from_currency == row.from_currency,
            ExchangeRate.to_currency == row.to_currency,
            ExchangeRate.effective_date == row.max_date,
        ).order_by(ExchangeRate.organization_id.is_(None)).first()   # el propio antes que el global
        if rate:
            latest_rates[rate.to_currency] = {
                "rate": rate.rate,
                "effective_date": str(rate.effective_date),
                "source": rate.source,
            }
    latest_rates[base] = {"rate": 1.0, "effective_date": str(timeutil.today()), "source": "base"}
    from app.services.settings_service import monedas
    return {"base": base, "rates": latest_rates, "currencies": monedas(db, db.info.get("organization_id"))}


def upsert_exchange_rate_record(payload: dict, db) -> dict:
    import re as _re
    from_currency = (payload.get("from_currency") or _pe.moneda_de_empresa(db)).upper()  # 18-11-2026
    # Auditoría 22-11-2026 (baja): sin "USD" por defecto; la moneda destino es obligatoria.
    to_currency   = (payload.get("to_currency") or "").upper()
    if not to_currency:
        raise error(422, "campo_obligatorio", campo="to_currency")
    _iso3 = _re.compile(r"^[A-Z]{3}$")
    if not _iso3.match(from_currency) or not _iso3.match(to_currency):
        raise error(422, "moneda_codigo_no_valido", detail="Currency codes must be 3-letter ISO codes (e.g. EUR, USD)")
    rate_value    = float(payload.get("rate", 1.0))
    if rate_value <= 0:
        raise error(400, "tipo_de_cambio_positivo")
    source = payload.get("source", "manual")
    effective_date = date.fromisoformat(payload.get("effective_date", str(timeutil.today())))
    primary_obj = None
    # Revisión 2026-11: el tipo manual es de la empresa de la sesión (sin
    # empresa: global); antes actualizaba el que hubiera, también el global.
    from app.services.exchange_rate_service import org_de_la_sesion, solo_de
    org = org_de_la_sesion(db)
    for idx, (fc, tc, r) in enumerate([(from_currency, to_currency, rate_value), (to_currency, from_currency, 1 / rate_value)]):   # M5: inverso sin redondear a 6 decimales
        existing = solo_de(db.query(ExchangeRate), org).filter(
            ExchangeRate.from_currency == fc,
            ExchangeRate.to_currency == tc,
            ExchangeRate.effective_date == effective_date,
        ).first()
        if existing:
            existing.rate = r
            existing.source = source
            if idx == 0:
                primary_obj = existing
        else:
            obj = ExchangeRate(organization_id=org, from_currency=fc, to_currency=tc, rate=r,
                               effective_date=effective_date, source=source)
            db.add(obj)
            if idx == 0:
                primary_obj = obj
    db.commit()
    if primary_obj:
        db.refresh(primary_obj)
    return {
        "from_currency": from_currency,
        "to_currency": to_currency,
        "rate": rate_value,
        "effective_date": str(effective_date),
        "source": source,
    }


def convert_currency_amount(payload: dict, db) -> dict:
    amount    = float(payload.get("amount", 0))
    from_curr = (payload.get("from_currency") or payload.get("from") or _pe.moneda_de_empresa(db)).upper()
    to_curr   = (payload.get("to_currency") or payload.get("to") or _pe.moneda_de_empresa(db)).upper()
    on_date   = date.fromisoformat(payload.get("date", str(timeutil.today()))) if payload.get("date") else timeutil.today()
    if from_curr == to_curr:
        return {"converted_amount": amount, "amount": amount, "from_currency": from_curr, "to_currency": to_curr, "rate": 1.0}
    # Auditoría 23-11-2026 (§7.3): era un quinto resolutor (solo directo). Ahora
    # el único: directo → inverso → cruzado por EUR; sin tipo, 404 con código.
    from app.services.currency_rates_service import resolve_rate_with_snapshot
    snap = resolve_rate_with_snapshot(db, from_curr, to_curr, on_date)
    if snap["rate"] is None:
        raise error(404, "tipo_de_cambio_no_configurado", desde=from_curr, hasta=to_curr)
    converted = round(amount * float(snap["rate"]), 2)
    return {
        "converted_amount": converted, "amount": amount,
        "from_currency": from_curr, "to_currency": to_curr,
        "rate": snap["rate"], "converted": converted,
        "effective_date": snap["rate_date"], "source": snap["source"],
    }
