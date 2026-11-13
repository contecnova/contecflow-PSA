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

import json
import os
from datetime import date as Date
from typing import Iterable, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.user_cost import CountryEmployerCost, UserCostProfile
from app.core.asignacion import es_asignable
from app.core.errores import ErrorDeDominio
from app.core.config import settings as _settings


# ── Default presets seeded on first run ──────────────────────────────────────
# employer_cost_pct = SS empresa + bonuses + benefits prorated.
# productive_hours_year = annual hours minus vacation/holidays/sick/training.
# Source: rough industry standard; admin can override per organisation.
#
# Auditoria 2026-11 (hallazgo 30): las 18 filas estaban escritas aqui; ahora
# salen de `app/core/country_employer_costs.json` (mismos valores), y una
# instalacion puede usar el suyo con el ajuste `COUNTRY_EMPLOYER_COSTS_PATH`.
_PRESETS_POR_DEFECTO = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                    "core", "country_employer_costs.json")


def cargar_presets_de_pais() -> list[dict]:
    """Las tarifas de coste de empresa por pais (del JSON por defecto o del configurado)."""
    from app.core.config import settings
    ruta = settings.COUNTRY_EMPLOYER_COSTS_PATH or _PRESETS_POR_DEFECTO
    with open(ruta, encoding="utf-8") as fichero:
        return json.load(fichero)


DEFAULT_COUNTRY_PRESETS: list[dict] = cargar_presets_de_pais()


# ── Cost computation ─────────────────────────────────────────────────────────
def costes_por_defecto(db: Optional[Session], org_id: Optional[str] = None) -> tuple[float, float]:
    """(sobrecoste de empresa, horas productivas al año) por defecto de la empresa.

    Ajustes `DEFAULT_EMPLOYER_COST_PCT` y `DEFAULT_PRODUCTIVE_HOURS_YEAR` (por
    empresa, en vivo); sin sesion, los de Settings. Mandan sobre ellos la ficha
    de coste y el preset del pais.
    """
    if db is None:
        return _settings.DEFAULT_EMPLOYER_COST_PCT, _settings.DEFAULT_PRODUCTIVE_HOURS_YEAR
    from app.services import settings_service as _ss
    org_id = org_id or db.info.get("organization_id")
    return (_ss.get_runtime_float(db, "DEFAULT_EMPLOYER_COST_PCT", org_id),
            _ss.get_runtime_float(db, "DEFAULT_PRODUCTIVE_HOURS_YEAR", org_id))


def derive_cost(gross_annual_salary: float, employer_cost_pct: float,
                extra_annual_costs: float, productive_hours_year: float) -> tuple[float, float]:
    """Return (total_annual_cost, cost_per_hour)."""
    total = (gross_annual_salary or 0) * (1 + (employer_cost_pct or 0)) + (extra_annual_costs or 0)
    hrs = productive_hours_year if productive_hours_year and productive_hours_year > 0 else _settings.DEFAULT_PRODUCTIVE_HOURS_YEAR
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
    """Return the cost in the org's default currency for `hours` worked by user.

    The active cost profile may be denominated in a foreign currency
    (``profile.currency``). When it differs from the org's default currency we
    convert via the FX helper at `on_date` so the returned amount is always in
    the org currency.
    """
    if user is None:
        return 0.0
    on_date = on_date or Date.today()
    profile = get_active_profile(db, user.id, on_date)
    if profile is not None:
        rate = profile.cost_per_hour or 0.0
        src_currency = profile.currency
    else:
        rate = float(user.hourly_rate) if (user.hourly_rate and user.hourly_rate > 0) else 0.0
        src_currency = None  # legacy rate assumed already in org currency

    amount = rate * (hours or 0)

    from app.core.config import settings
    org_currency = settings.DEFAULT_CURRENCY
    if src_currency and src_currency != org_currency:
        from app.services.profitability_service import get_fx_rate
        fx = get_fx_rate(db, src_currency, org_currency, on_date)
        amount *= fx

    return round(amount, 2)


# ── Country preset access ───────────────────────────────────────────────────
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
                   extra_annual_costs: float = 0.0, productive_hours_year: Optional[float] = None,
                   country_code: Optional[str] = None, currency: Optional[str] = None,
                   notes: Optional[str] = None,
                   organization_id: Optional[str] = None,
                   created_by_user_id: Optional[str] = None) -> UserCostProfile:
    """Create a new cost profile and close any open profile that overlaps."""
    if not currency:
        from app.core.config import settings
        currency = settings.DEFAULT_CURRENCY
    if productive_hours_year is None:
        productive_hours_year = costes_por_defecto(db, organization_id)[1]
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
        if es_asignable(p, k, ("user_id",)):
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
    presets = cargar_presets_de_pais()  # se relee: el ajuste puede cambiar sin reiniciar
    for entry in presets:
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
    return {"created": created, "updated": updated, "skipped": skipped, "total": len(presets)}


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


# ── Guardas por organizacion, movidas del endpoint ───────────────────────────
#
# Auditoria 2026-08 (hallazgo 22). `endpoints/user_costs.py` era mas cuidadoso
# que la media —`update_country`, `delete_country` y `/summary` si comprueban la
# organizacion— pero cuatro sitios buscaban por id a secas, y aqui lo que se
# expone son **salarios**:
#
#   · `GET /users/{id}/active` devolvia el perfil de coste y el
#     `legacy_hourly_rate` de CUALQUIER usuario por id;
#   · `GET /users/{id}/profiles` devolvia el historico salarial completo;
#   · `update_profile` y `delete_profile` buscaban el perfil por id, asi que se
#     podia editar o borrar el de otro cliente.
#
# Lo unico que lo impedia era el filtro implicito de `TenantSession`.



def _org_de(user) -> Optional[str]:
    return getattr(user, "organization_id", None)


def usuario_propio(db: Session, actor, user_id: str) -> User:
    """El usuario, si comparte organizacion con quien pregunta. 404 si no.

    404 y no 403: confirmar que esa persona existe en otra organizacion ya seria
    contar algo.
    """
    fila = (
        db.query(User)
        .filter(User.id == user_id, User.organization_id == _org_de(actor))
        .first()
    )
    if not fila:
        raise ErrorDeDominio(404, "User not found")
    return fila


def perfil_propio(db: Session, actor, profile_id: str) -> UserCostProfile:
    """El perfil de coste, si es de la organizacion de quien pregunta."""
    fila = (
        db.query(UserCostProfile)
        .filter(
            UserCostProfile.id == profile_id,
            UserCostProfile.organization_id == _org_de(actor),
        )
        .first()
    )
    if not fila:
        raise ErrorDeDominio(404, "Profile not found")
    return fila


def preset_propio_o_global(db: Session, actor, preset_id: str) -> CountryEmployerCost:
    """El preset de pais: el propio o uno global. 404 si es de otro cliente.

    Los globales (`organization_id IS NULL`) son los valores que trae el
    producto y se pueden leer y sobrescribir por organizacion, asi que aqui se
    admiten; lo que no se admite es el de otro cliente.
    """
    fila = (
        db.query(CountryEmployerCost)
        .filter(CountryEmployerCost.id == preset_id)
        .filter(
            or_(
                CountryEmployerCost.organization_id == _org_de(actor),
                CountryEmployerCost.organization_id.is_(None),
            )
        )
        .first()
    )
    if not fila:
        raise ErrorDeDominio(404, "Preset not found")
    return fila


def guardar_preset_de_pais(db: Session, actor, datos: dict) -> CountryEmployerCost:
    """Crea o sobrescribe el preset de un pais para esta organizacion.

    El codigo de pais se normaliza a mayusculas: la unicidad es por
    `(country_code, organization_id)` y sin normalizar «es» y «ES» serian dos.
    """
    org_id = _org_de(actor)
    codigo = (datos.get("country_code") or "").upper()
    existente = (
        db.query(CountryEmployerCost)
        .filter(
            CountryEmployerCost.country_code == codigo,
            CountryEmployerCost.organization_id == org_id,
        )
        .first()
    )
    if existente:
        for clave, valor in datos.items():
            if clave == "country_code":
                continue
            setattr(existente, clave, valor)
        db.commit()
        db.refresh(existente)
        return existente

    fila = CountryEmployerCost(
        organization_id=org_id,
        **{**datos, "country_code": codigo},
    )
    db.add(fila)
    db.commit()
    db.refresh(fila)
    return fila


def borrar_preset_de_pais(db: Session, actor, preset_id: str) -> None:
    """Borra un preset propio. Los globales no se borran: se sobrescriben."""
    fila = preset_propio_o_global(db, actor, preset_id)
    if fila.organization_id is None:
        raise ErrorDeDominio(
            400, "Global presets cannot be deleted; override per-org instead.")
    db.delete(fila)
    db.commit()


def usuarios_activos_de_la_organizacion(db: Session, actor, *, tope: int) -> list:
    """Los usuarios activos de la organizacion, con un tope.

    El filtro de organizacion **no es condicional**: si el sujeto no tiene
    organizacion se listan los usuarios sin organizacion, no los de todos los
    clientes. Antes era `if org_id: q = q.filter(...)`, que es lo contrario.
    """
    return (
        db.query(User)
        .filter(User.status == "active",
                User.organization_id == _org_de(actor))
        .limit(tope)
        .all()
    )
