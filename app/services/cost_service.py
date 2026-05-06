"""
cost_service.py — Date-aware cost-per-hour resolution for users.

Single source of truth for "what does an hour of work from user X cost the
company on date D?". Used by imputation, profitability, project cost forecasts,
dashboards.

Resolution order:
  1. UserCostProfile active on `date` (versioned per user).
  2. Legacy `User.hourly_rate` (treated as already-loaded internal cost).
  3. None — caller decides whether to skip or zero-out.
"""
from __future__ import annotations

from datetime import date as Date
from typing import Iterable, Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.user_cost import CountryEmployerCost, UserCostProfile


# ── Default presets seeded on first run ──────────────────────────────────────
DEFAULT_COUNTRY_PRESETS: list[dict] = [
    # employer_cost_pct = SS empresa + bonuses + benefits prorated.
    # productive_hours_year = annual hours minus vacation/holidays/sick/training.
    # Source: rough industry standard; admin can override per organisation.
    {"country_code": "ES", "country_name": "España",         "currency": "EUR", "employer_cost_pct": 0.32, "productive_hours_year": 1700,
     "notes": "SS empresa ~30%, vacaciones 22d + festivos ~12d"},
    {"country_code": "PT", "country_name": "Portugal",       "currency": "EUR", "employer_cost_pct": 0.2375, "productive_hours_year": 1720,
     "notes": "TSU 23.75%, vacaciones 22d + festivos"},
    {"country_code": "FR", "country_name": "France",         "currency": "EUR", "employer_cost_pct": 0.42, "productive_hours_year": 1607,
     "notes": "Charges patronales ~42%, 35h/semaine, 5 sem CP"},
    {"country_code": "DE", "country_name": "Deutschland",    "currency": "EUR", "employer_cost_pct": 0.21, "productive_hours_year": 1700,
     "notes": "Sozialabgaben Arbeitgeber ~21%"},
    {"country_code": "IT", "country_name": "Italia",         "currency": "EUR", "employer_cost_pct": 0.30, "productive_hours_year": 1720,
     "notes": "Contributi datore ~30%, ferie 26d + festività"},
    {"country_code": "GB", "country_name": "United Kingdom", "currency": "GBP", "employer_cost_pct": 0.155, "productive_hours_year": 1750,
     "notes": "NI employer 13.8% + pension auto-enrol ~3%"},
    {"country_code": "IE", "country_name": "Ireland",        "currency": "EUR", "employer_cost_pct": 0.115, "productive_hours_year": 1750,
     "notes": "PRSI employer 11.05% + pension"},
    {"country_code": "NL", "country_name": "Nederland",      "currency": "EUR", "employer_cost_pct": 0.20, "productive_hours_year": 1720,
     "notes": "Werkgeverslasten ~20%"},
    {"country_code": "PL", "country_name": "Polska",         "currency": "PLN", "employer_cost_pct": 0.205, "productive_hours_year": 1750,
     "notes": "ZUS pracodawcy ~20.5%"},
    {"country_code": "US", "country_name": "United States",  "currency": "USD", "employer_cost_pct": 0.25, "productive_hours_year": 1880,
     "notes": "FICA 7.65% + benefits + 401k + healthcare ~25%"},
    {"country_code": "MX", "country_name": "México",         "currency": "MXN", "employer_cost_pct": 0.30, "productive_hours_year": 1900,
     "notes": "IMSS + INFONAVIT + aguinaldo + prima ~30%"},
    {"country_code": "BR", "country_name": "Brasil",         "currency": "BRL", "employer_cost_pct": 0.70, "productive_hours_year": 1900,
     "notes": "Encargos sociais (INSS, FGTS, 13º, férias) ~70%"},
    {"country_code": "AR", "country_name": "Argentina",      "currency": "ARS", "employer_cost_pct": 0.27, "productive_hours_year": 1880,
     "notes": "Cargas sociales empleador ~27%"},
    {"country_code": "CO", "country_name": "Colombia",       "currency": "COP", "employer_cost_pct": 0.45, "productive_hours_year": 1880,
     "notes": "Aportes parafiscales + prestaciones ~45%"},
    {"country_code": "CH", "country_name": "Schweiz",        "currency": "CHF", "employer_cost_pct": 0.135, "productive_hours_year": 1850,
     "notes": "AHV/IV/EO ~6.4% + LPP/UVG"},
    {"country_code": "BE", "country_name": "Belgique",       "currency": "EUR", "employer_cost_pct": 0.25, "productive_hours_year": 1700,
     "notes": "ONSS employeur ~25%"},
    {"country_code": "SE", "country_name": "Sverige",        "currency": "SEK", "employer_cost_pct": 0.3142, "productive_hours_year": 1700,
     "notes": "Arbetsgivaravgift 31.42%"},
    {"country_code": "AT", "country_name": "Österreich",     "currency": "EUR", "employer_cost_pct": 0.22, "productive_hours_year": 1700,
     "notes": "Lohnnebenkosten ~22%"},
]


# ── Cost computation ─────────────────────────────────────────────────────────
def derive_cost(gross_annual_salary: float, employer_cost_pct: float,
                extra_annual_costs: float, productive_hours_year: float) -> tuple[float, float]:
    """Return (total_annual_cost, cost_per_hour)."""
    total = (gross_annual_salary or 0) * (1 + (employer_cost_pct or 0)) + (extra_annual_costs or 0)
    hrs = productive_hours_year if productive_hours_year and productive_hours_year > 0 else 1700
    return round(total, 2), round(total / hrs, 2)


# ── Resolution ───────────────────────────────────────────────────────────────
def get_active_profile(db: Session, user_id: str, on_date: Optional[Date] = None) -> Optional[UserCostProfile]:
    """Return the cost profile in effect for `user_id` on `on_date` (or today)."""
    on_date = on_date or Date.today()
    return (db.query(UserCostProfile)
              .filter(UserCostProfile.user_id == user_id,
                      UserCostProfile.valid_from <= on_date,
                      or_(UserCostProfile.valid_to.is_(None),
                          UserCostProfile.valid_to >= on_date))
              .order_by(UserCostProfile.valid_from.desc())
              .first())


def cost_per_hour(db: Session, user: User, on_date: Optional[Date] = None) -> Optional[float]:
    """Resolve the user's cost per hour on the given date.

    Falls back to the legacy `User.hourly_rate` if no profile exists. Returns
    None if neither source has data — callers decide whether to treat as zero.
    """
    if user is None:
        return None
    profile = get_active_profile(db, user.id, on_date)
    if profile is not None:
        return profile.cost_per_hour
    if user.hourly_rate and user.hourly_rate > 0:
        return float(user.hourly_rate)
    return None


def cost_amount(db: Session, user: User, hours: float, on_date: Optional[Date] = None) -> float:
    """Return the cost in the org's default currency for `hours` worked by user."""
    rate = cost_per_hour(db, user, on_date) or 0.0
    return round(rate * (hours or 0), 2)


# ── Country preset access ───────────────────────────────────────────────────
def get_country_preset(db: Session, country_code: str,
                       organization_id: Optional[str] = None) -> Optional[CountryEmployerCost]:
    """Return the org-specific preset, or fall back to the global one."""
    code = (country_code or "").upper()
    q = db.query(CountryEmployerCost).filter(CountryEmployerCost.country_code == code)
    if organization_id is not None:
        org_specific = q.filter(CountryEmployerCost.organization_id == organization_id).first()
        if org_specific:
            return org_specific
    return q.filter(CountryEmployerCost.organization_id.is_(None)).first()


def list_country_presets(db: Session, organization_id: Optional[str] = None) -> list[CountryEmployerCost]:
    """List all presets visible to the org: global + org-specific."""
    q = db.query(CountryEmployerCost)
    if organization_id is None:
        q = q.filter(CountryEmployerCost.organization_id.is_(None))
    else:
        q = q.filter(or_(CountryEmployerCost.organization_id == organization_id,
                         CountryEmployerCost.organization_id.is_(None)))
    return q.order_by(CountryEmployerCost.country_name).all()


# ── CRUD helpers ────────────────────────────────────────────────────────────
def create_profile(db: Session, *, user_id: str, valid_from: Date,
                   gross_annual_salary: float, employer_cost_pct: float,
                   extra_annual_costs: float = 0.0, productive_hours_year: float = 1700,
                   country_code: Optional[str] = None, currency: str = "EUR",
                   notes: Optional[str] = None,
                   organization_id: Optional[str] = None,
                   created_by_user_id: Optional[str] = None) -> UserCostProfile:
    """Create a new cost profile and close any open profile that overlaps."""
    total, per_hour = derive_cost(gross_annual_salary, employer_cost_pct,
                                  extra_annual_costs, productive_hours_year)

    # Close any open profile that would overlap (set valid_to = day before new valid_from)
    from datetime import timedelta
    prev = (db.query(UserCostProfile)
              .filter(UserCostProfile.user_id == user_id,
                      UserCostProfile.valid_to.is_(None))
              .first())
    if prev and prev.valid_from < valid_from:
        prev.valid_to = valid_from - timedelta(days=1)

    profile = UserCostProfile(
        user_id=user_id, organization_id=organization_id,
        country_code=(country_code or "").upper() or None, currency=currency,
        gross_annual_salary=gross_annual_salary,
        employer_cost_pct=employer_cost_pct,
        extra_annual_costs=extra_annual_costs,
        productive_hours_year=productive_hours_year,
        total_annual_cost=total, cost_per_hour=per_hour,
        valid_from=valid_from, valid_to=None,
        notes=notes, created_by_user_id=created_by_user_id,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def update_profile(db: Session, profile_id: str, **fields) -> Optional[UserCostProfile]:
    p = db.query(UserCostProfile).filter(UserCostProfile.id == profile_id).first()
    if not p:
        return None
    for k, v in fields.items():
        if v is None:
            continue
        if hasattr(p, k):
            setattr(p, k, v)
    # Recompute derived values
    p.total_annual_cost, p.cost_per_hour = derive_cost(
        p.gross_annual_salary, p.employer_cost_pct,
        p.extra_annual_costs, p.productive_hours_year,
    )
    db.commit()
    db.refresh(p)
    return p


def delete_profile(db: Session, profile_id: str) -> bool:
    p = db.query(UserCostProfile).filter(UserCostProfile.id == profile_id).first()
    if not p:
        return False
    db.delete(p)
    db.commit()
    return True


def list_profiles(db: Session, user_id: str) -> list[UserCostProfile]:
    return (db.query(UserCostProfile)
              .filter(UserCostProfile.user_id == user_id)
              .order_by(UserCostProfile.valid_from.desc())
              .all())


# ── Bulk resolution (for dashboards / lists) ────────────────────────────────
def cost_per_hour_bulk(db: Session, user_ids: Iterable[str],
                       on_date: Optional[Date] = None) -> dict[str, float]:
    """Resolve cost-per-hour for many users at once. Returns {user_id: rate}."""
    on_date = on_date or Date.today()
    user_ids = list(user_ids)
    if not user_ids:
        return {}
    profiles = (db.query(UserCostProfile)
                  .filter(UserCostProfile.user_id.in_(user_ids),
                          UserCostProfile.valid_from <= on_date,
                          or_(UserCostProfile.valid_to.is_(None),
                              UserCostProfile.valid_to >= on_date))
                  .all())
    # Collect the most-recent valid_from per user (in case of overlapping rows)
    by_user: dict[str, UserCostProfile] = {}
    for p in profiles:
        cur = by_user.get(p.user_id)
        if cur is None or p.valid_from > cur.valid_from:
            by_user[p.user_id] = p
    out: dict[str, float] = {}
    # Profiles take precedence; fall back to user.hourly_rate for those without
    missing = [uid for uid in user_ids if uid not in by_user]
    if missing:
        users = db.query(User).filter(User.id.in_(missing)).all()
        for u in users:
            if u.hourly_rate and u.hourly_rate > 0:
                out[u.id] = float(u.hourly_rate)
    for uid, p in by_user.items():
        out[uid] = p.cost_per_hour
    return out


# ── Seeding ─────────────────────────────────────────────────────────────────
def seed_country_presets(db: Session, *, force: bool = False) -> dict:
    """Insert default global country presets. Existing rows are skipped unless force=True."""
    created = 0
    updated = 0
    skipped = 0
    for entry in DEFAULT_COUNTRY_PRESETS:
        existing = (db.query(CountryEmployerCost)
                      .filter(CountryEmployerCost.country_code == entry["country_code"],
                              CountryEmployerCost.organization_id.is_(None))
                      .first())
        if existing is None:
            row = CountryEmployerCost(organization_id=None, **entry)
            db.add(row)
            created += 1
        elif force:
            for k, v in entry.items():
                setattr(existing, k, v)
            updated += 1
        else:
            skipped += 1
    db.commit()
    return {"created": created, "updated": updated, "skipped": skipped, "total": len(DEFAULT_COUNTRY_PRESETS)}


# ── Serializers ─────────────────────────────────────────────────────────────
def serialize_country(c: CountryEmployerCost) -> dict:
    return {
        "id": c.id,
        "organization_id": c.organization_id,
        "country_code": c.country_code,
        "country_name": c.country_name,
        "currency": c.currency,
        "employer_cost_pct": c.employer_cost_pct,
        "productive_hours_year": c.productive_hours_year,
        "notes": c.notes,
        "is_default": c.organization_id is None,
    }


def serialize_profile(p: UserCostProfile) -> dict:
    return {
        "id": p.id,
        "user_id": p.user_id,
        "country_code": p.country_code,
        "currency": p.currency,
        "gross_annual_salary": p.gross_annual_salary,
        "employer_cost_pct": p.employer_cost_pct,
        "extra_annual_costs": p.extra_annual_costs,
        "productive_hours_year": p.productive_hours_year,
        "total_annual_cost": p.total_annual_cost,
        "cost_per_hour": p.cost_per_hour,
        "valid_from": p.valid_from.isoformat() if p.valid_from else None,
        "valid_to": p.valid_to.isoformat() if p.valid_to else None,
        "notes": p.notes,
        "is_active": p.valid_to is None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }
