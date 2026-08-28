"""
Exchange rate service — fetches daily rates from the European Central Bank (ECB)
free XML feed and optionally from OpenExchangeRates if an App ID is configured.

Usage:
  from app.services.exchange_rate_service import sync_ecb_rates
  updated = await sync_ecb_rates(db)

ECB endpoint: https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml
Returns EUR-based rates for ~30 major currencies, updated each business day ~16:00 CET.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

import httpx
from app.core import timeutil

# defusedxml protects against XXE / billion-laughs attacks when parsing the ECB feed.
# It is listed in requirements.txt; the stdlib fallback is kept only for offline tests.
try:
    from defusedxml.ElementTree import fromstring as _xml_fromstring
except ImportError:  # pragma: no cover
    from xml.etree.ElementTree import fromstring as _xml_fromstring  # type: ignore

from sqlalchemy.orm import Session

from app.models.bookings import ExchangeRate

logger = logging.getLogger(__name__)

ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
ECB_NS  = "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"

# Currencies supported by ECB feed
ECB_CURRENCIES = {
    "USD", "JPY", "BGN", "CZK", "DKK", "GBP", "HUF", "PLN", "RON", "SEK",
    "CHF", "ISK", "NOK", "HRK", "TRY", "AUD", "BRL", "CAD", "CNY", "HKD",
    "IDR", "ILS", "INR", "KRW", "MXN", "MYR", "NZD", "PHP", "SGD", "THB",
    "ZAR",
}


def sync_ecb_rates(db: Session, force: bool = False) -> dict:
    """
    Fetch the ECB daily reference rates and upsert into the exchange_rates table.
    All rates are EUR-based (EUR = 1.0).

    Returns:
        {"ok": True, "date": "YYYY-MM-DD", "upserted": N, "skipped": N, "source": "ecb"}
    """
    try:
        from app.services.settings_service import outbound_http_timeout
        with httpx.Client(timeout=outbound_http_timeout(db, default=15.0)) as client:
            resp = client.get(ECB_URL)
            resp.raise_for_status()
    except Exception as exc:
        logger.error("ECB rate fetch failed: %s", exc)
        return {"ok": False, "error": str(exc), "source": "ecb"}

    try:
        root = _xml_fromstring(resp.content)  # noqa: S314
        cube_time = root.find(f".//{{{ECB_NS}}}Cube[@time]")
        if cube_time is None:
            return {"ok": False, "error": "Unexpected ECB XML format", "source": "ecb"}

        rate_date_str = cube_time.attrib.get("time")
        rate_date = date.fromisoformat(rate_date_str)

        # Check if we already have today's data unless forced
        if not force:
            existing = db.query(ExchangeRate).filter(
                ExchangeRate.from_currency == "EUR",
                ExchangeRate.effective_date == rate_date,
            ).first()
            if existing:
                return {"ok": True, "date": str(rate_date), "upserted": 0,
                        "skipped": 1, "source": "ecb", "note": "already up to date"}

        upserted = 0
        # Always upsert EUR→EUR = 1.0 as anchor
        _upsert_pair(db, "EUR", "EUR", 1.0, rate_date)
        upserted += 1

        for cube in cube_time.findall(f"{{{ECB_NS}}}Cube"):
            currency = cube.attrib.get("currency", "").upper()
            rate_str = cube.attrib.get("rate")
            if not currency or not rate_str:
                continue
            try:
                rate_val = float(rate_str)
            except ValueError:
                continue

            # EUR → CURRENCY
            _upsert_pair(db, "EUR", currency, rate_val, rate_date)
            # CURRENCY → EUR (inverse)
            _upsert_pair(db, currency, "EUR", round(1.0 / rate_val, 6), rate_date)
            upserted += 2

        db.commit()
        logger.info("ECB rates synced: %d pairs for %s", upserted, rate_date)
        return {"ok": True, "date": str(rate_date), "upserted": upserted,
                "skipped": 0, "source": "ecb"}

    except Exception as exc:
        db.rollback()
        logger.error("ECB rate parse/upsert failed: %s", exc)
        return {"ok": False, "error": str(exc), "source": "ecb"}


def _upsert_pair(db: Session, from_c: str, to_c: str, rate: float,
                 eff_date: date) -> None:
    # Handle pending objects first (important when session autoflush=False in tests).
    for pending in db.new:
        if not isinstance(pending, ExchangeRate):
            continue
        if (
            pending.from_currency == from_c
            and pending.to_currency == to_c
            and pending.effective_date == eff_date
        ):
            pending.rate = rate
            pending.source = "ecb"
            return

    existing = db.query(ExchangeRate).filter(
        ExchangeRate.from_currency == from_c,
        ExchangeRate.to_currency == to_c,
        ExchangeRate.effective_date == eff_date,
    ).first()
    if existing:
        existing.rate = rate
        existing.source = "ecb"
    else:
        db.add(ExchangeRate(
            from_currency=from_c,
            to_currency=to_c,
            rate=rate,
            effective_date=eff_date,
            source="ecb",
        ))


def sync_openexchangerates(db: Session, app_id: str,
                           base: str = "USD") -> dict:
    """
    Fetch latest rates from OpenExchangeRates (requires a free App ID).
    Stores USD-based rates (or selected base).
    """
    url = f"https://openexchangerates.org/api/latest.json?app_id={app_id}&base={base}"
    try:
        from app.services.settings_service import outbound_http_timeout
        with httpx.Client(timeout=outbound_http_timeout(db, default=15.0)) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.error("OpenExchangeRates fetch failed: %s", exc)
        return {"ok": False, "error": str(exc), "source": "openexchangerates"}

    rates_dict: dict = data.get("rates", {})
    rate_date = timeutil.today()
    upserted = 0

    for currency, rate_val in rates_dict.items():
        if not isinstance(rate_val, (int, float)) or rate_val <= 0:
            continue
        _upsert_pair(db, base.upper(), currency.upper(), float(rate_val), rate_date)
        if float(rate_val) > 0:
            _upsert_pair(db, currency.upper(), base.upper(),
                         round(1.0 / float(rate_val), 6), rate_date)
        upserted += 2

    db.commit()
    return {"ok": True, "date": str(rate_date), "upserted": upserted,
            "skipped": 0, "source": "openexchangerates"}


def get_rate(db: Session, from_c: str, to_c: str,
             as_of: Optional[date] = None) -> Optional[float]:
    """Return the latest exchange rate for a pair, optionally as of a given date."""
    from_c = from_c.upper()
    to_c   = to_c.upper()
    if from_c == to_c:
        return 1.0

    # Some test/session setups disable autoflush; flush explicitly so newly upserted
    # rates in the same transaction are visible to this read.
    db.flush()

    ref = as_of or timeutil.today()
    row = db.query(ExchangeRate).filter(
        ExchangeRate.from_currency == from_c,
        ExchangeRate.to_currency   == to_c,
        ExchangeRate.effective_date <= ref,
    ).order_by(ExchangeRate.effective_date.desc()).first()
    return row.rate if row else None
