"""
User-cost metrics: surface UserCostProfile data on the metrics dashboard.

All metrics are date-aware: when the user requests a date range, the active
profile on `d_to` is used (current snapshot). Historical drift uses end-of-month
samples.
"""
from datetime import date, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.user_cost import CountryEmployerCost, UserCostProfile
from . import register_metric


def _profiles_active_on(db: Session, on_date: date) -> list[UserCostProfile]:
    """Return all cost profiles in effect on `on_date`."""
    return (db.query(UserCostProfile)
              .filter(UserCostProfile.valid_from <= on_date,
                      or_(UserCostProfile.valid_to.is_(None),
                          UserCostProfile.valid_to >= on_date))
              .all())


@register_metric("cost_per_hour_by_person")
def metric_cost_per_hour_by_person(db: Session, d_from: date, d_to: date,
                                    top_n: int, **kwargs) -> tuple[list[dict], dict]:
    """Coste/hora actual por persona (perfil activo en `d_to`)."""
    profiles = _profiles_active_on(db, d_to)
    user_ids = [p.user_id for p in profiles]
    users = {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}
    rows = []
    for p in profiles:
        u = users.get(p.user_id)
        if not u:
            continue
        rows.append({"label": u.full_name, "value": round(p.cost_per_hour or 0, 2)})
    rows.sort(key=lambda r: r["value"], reverse=True)
    return rows[:top_n], {}


@register_metric("cost_per_hour_by_department")
def metric_cost_per_hour_by_department(db: Session, d_from: date, d_to: date,
                                        top_n: int, **kwargs) -> tuple[list[dict], dict]:
    """Coste/hora medio por departamento (media simple sobre perfiles activos)."""
    profiles = _profiles_active_on(db, d_to)
    if not profiles:
        return [], {}
    users = {u.id: u for u in db.query(User).filter(User.id.in_([p.user_id for p in profiles])).all()}
    bucket: dict[str, list[float]] = {}
    for p in profiles:
        u = users.get(p.user_id)
        dept = (u.department if u else None) or "Sin departamento"
        bucket.setdefault(dept, []).append(p.cost_per_hour or 0)
    rows = [
        {"label": dept, "value": round(sum(vals) / len(vals), 2)}
        for dept, vals in bucket.items() if vals
    ]
    rows.sort(key=lambda r: r["value"], reverse=True)
    return rows[:top_n], {}


@register_metric("cost_per_hour_by_country")
def metric_cost_per_hour_by_country(db: Session, d_from: date, d_to: date,
                                     top_n: int, **kwargs) -> tuple[list[dict], dict]:
    """Coste/hora medio por país (multi-país)."""
    profiles = _profiles_active_on(db, d_to)
    if not profiles:
        return [], {}
    bucket: dict[str, list[float]] = {}
    for p in profiles:
        cc = p.country_code or "??"
        bucket.setdefault(cc, []).append(p.cost_per_hour or 0)
    # Resolve human-readable name from CountryEmployerCost
    names = {c.country_code: c.country_name for c in db.query(CountryEmployerCost).all()}
    rows = [
        {"label": f"{cc} · {names.get(cc, cc)}", "value": round(sum(vals) / len(vals), 2)}
        for cc, vals in bucket.items() if vals
    ]
    rows.sort(key=lambda r: r["value"], reverse=True)
    return rows[:top_n], {}


@register_metric("annual_cost_by_person")
def metric_annual_cost_by_person(db: Session, d_from: date, d_to: date,
                                  top_n: int, **kwargs) -> tuple[list[dict], dict]:
    """Coste empresa anual total por persona (bruto + SS + extras)."""
    profiles = _profiles_active_on(db, d_to)
    user_ids = [p.user_id for p in profiles]
    users = {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}
    rows = []
    for p in profiles:
        u = users.get(p.user_id)
        if not u:
            continue
        rows.append({"label": u.full_name, "value": round(p.total_annual_cost or 0, 2)})
    rows.sort(key=lambda r: r["value"], reverse=True)
    return rows[:top_n], {}


@register_metric("annual_cost_by_country")
def metric_annual_cost_by_country(db: Session, d_from: date, d_to: date,
                                   top_n: int, **kwargs) -> tuple[list[dict], dict]:
    """Coste empresa anual total agregado por país."""
    profiles = _profiles_active_on(db, d_to)
    if not profiles:
        return [], {}
    bucket: dict[str, float] = {}
    for p in profiles:
        cc = p.country_code or "??"
        bucket[cc] = bucket.get(cc, 0) + (p.total_annual_cost or 0)
    names = {c.country_code: c.country_name for c in db.query(CountryEmployerCost).all()}
    rows = [
        {"label": f"{cc} · {names.get(cc, cc)}", "value": round(v, 2)}
        for cc, v in bucket.items()
    ]
    rows.sort(key=lambda r: r["value"], reverse=True)
    return rows[:top_n], {}


@register_metric("cost_profile_coverage")
def metric_cost_profile_coverage(db: Session, d_from: date, d_to: date,
                                  top_n: int, **kwargs) -> tuple[list[dict], dict]:
    """Cobertura de perfiles de coste — usuarios activos con/sin perfil."""
    profiles = _profiles_active_on(db, d_to)
    users_with_profile = {p.user_id for p in profiles}
    total_active = db.query(User).filter(User.status == "active").count()
    with_n = sum(1 for u in db.query(User).filter(User.status == "active").all()
                 if u.id in users_with_profile)
    legacy_n = sum(1 for u in db.query(User).filter(User.status == "active").all()
                   if u.id not in users_with_profile and (u.hourly_rate or 0) > 0)
    none_n = total_active - with_n - legacy_n
    rows = [
        {"label": "Con perfil de coste", "value": with_n},
        {"label": "Sólo tarifa interna (legacy)", "value": legacy_n},
        {"label": "Sin datos de coste", "value": max(none_n, 0)},
    ]
    return rows, {"default_chart": "pie"}


@register_metric("employer_cost_pct_by_country")
def metric_employer_cost_pct_by_country(db: Session, d_from: date, d_to: date,
                                         top_n: int, **kwargs) -> tuple[list[dict], dict]:
    """% de coste empresa (SS empresa + extras) por país, según presets vigentes."""
    rows = [
        {"label": f"{c.country_code} · {c.country_name}",
         "value": round((c.employer_cost_pct or 0) * 100, 2)}
        for c in db.query(CountryEmployerCost).order_by(CountryEmployerCost.country_name).all()
    ]
    rows.sort(key=lambda r: r["value"], reverse=True)
    return rows[:top_n], {}


@register_metric("cost_per_hour_drift")
def metric_cost_per_hour_drift(db: Session, d_from: date, d_to: date,
                                top_n: int, **kwargs) -> tuple[list[dict], dict]:
    """Evolución del coste/hora medio mes a mes en el rango."""
    if d_from > d_to:
        return [], {}
    # Sample at end of each month
    samples: list[tuple[date, list[float]]] = []
    cursor = date(d_from.year, d_from.month, 1)
    while cursor <= d_to:
        # End of this month (or d_to)
        if cursor.month == 12:
            next_month = date(cursor.year + 1, 1, 1)
        else:
            next_month = date(cursor.year, cursor.month + 1, 1)
        sample_date = min(next_month - timedelta(days=1), d_to)
        profiles = _profiles_active_on(db, sample_date)
        rates = [p.cost_per_hour for p in profiles if p.cost_per_hour]
        samples.append((sample_date, rates))
        cursor = next_month
    months_es = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    rows = [
        {"label": f"{months_es[d.month - 1]} {d.year}",
         "value": round(sum(rates) / len(rates), 2) if rates else 0}
        for d, rates in samples
    ]
    return rows, {"default_chart": "line"}
