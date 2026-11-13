"""
user_costs.py — REST API for the user cost-profile registry and country presets.

Endpoints:
  GET    /user-costs/countries                  — list country presets (org + global)
  POST   /user-costs/countries                  — create/update org-specific country preset
  POST   /user-costs/countries/seed             — seed default global presets
  PATCH  /user-costs/countries/{id}             — update preset
  DELETE /user-costs/countries/{id}             — delete preset (org-scoped only)

  GET    /user-costs/users/{user_id}/profiles                — list versions of a user
  POST   /user-costs/users/{user_id}/profiles                — create new profile
  GET    /user-costs/users/{user_id}/active                  — active profile + cost/hr today
  GET    /user-costs/users/{user_id}/preview                 — derive total + cost/hr from inputs
  PATCH  /user-costs/profiles/{profile_id}                   — update one profile
  DELETE /user-costs/profiles/{profile_id}                   — delete one profile

  GET    /user-costs/summary                                 — bulk cost/hr for all users (admin/hr)

All endpoints require admin or hr role — this is confidential information.
"""
from datetime import date as Date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.abac_enforce import enforce_abac
from app.core.deps import require_admin_or_hr
from app.db.session import get_db
from app.models.user import User
from app.core.responses import APIListResponse, APIResponse
from app.core.config import settings
from app.core.constantes import HORAS_PRODUCTIVAS_ANUALES_POR_DEFECTO, PORCENTAJE_COSTE_EMPRESA_POR_DEFECTO
import app.services.cost_service as svc
from app.services.presets_de_pais import actualizar_preset_de_pais

router = APIRouter(tags=["User Costs"])


# ── Schemas ───────────────────────────────────────────────────────────────────
class CountryPresetIn(BaseModel):
    country_code: str
    country_name: str
    currency: str = settings.DEFAULT_CURRENCY
    employer_cost_pct: float = PORCENTAJE_COSTE_EMPRESA_POR_DEFECTO
    productive_hours_year: float = HORAS_PRODUCTIVAS_ANUALES_POR_DEFECTO
    notes: Optional[str] = None


class CountryPresetUpdate(BaseModel):
    country_name: Optional[str] = None
    currency: Optional[str] = None
    employer_cost_pct: Optional[float] = None
    productive_hours_year: Optional[float] = None
    notes: Optional[str] = None


class ProfileIn(BaseModel):
    valid_from: Date
    gross_annual_salary: float
    employer_cost_pct: float = PORCENTAJE_COSTE_EMPRESA_POR_DEFECTO
    extra_annual_costs: float = 0.0
    productive_hours_year: float = HORAS_PRODUCTIVAS_ANUALES_POR_DEFECTO
    country_code: Optional[str] = None
    currency: str = settings.DEFAULT_CURRENCY
    notes: Optional[str] = None


class ProfileUpdate(BaseModel):
    valid_from: Optional[Date] = None
    valid_to: Optional[Date] = None
    gross_annual_salary: Optional[float] = None
    employer_cost_pct: Optional[float] = None
    extra_annual_costs: Optional[float] = None
    productive_hours_year: Optional[float] = None
    country_code: Optional[str] = None
    currency: Optional[str] = None
    notes: Optional[str] = None


class PreviewIn(BaseModel):
    gross_annual_salary: float
    employer_cost_pct: float
    extra_annual_costs: float = 0.0
    productive_hours_year: float = HORAS_PRODUCTIVAS_ANUALES_POR_DEFECTO


# ── Country presets ──────────────────────────────────────────────────────────
@router.get("/countries", summary="List country presets")
def list_countries(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_hr),
):
    org_id = getattr(current_user, "organization_id", None)
    rows = svc.list_country_presets(db, organization_id=org_id)
    items = [svc.serialize_country(c) for c in rows]
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/countries", summary="Create or override an org-specific country preset")
def create_country(
    payload: CountryPresetIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_hr),
):
    row = svc.guardar_preset_de_pais(db, current_user, payload.model_dump())
    return APIResponse.ok(data=svc.serialize_country(row))


@router.post("/countries/seed", summary="Seed default global country presets")
def seed_countries(
    force: bool = Query(False),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_hr),
):
    return APIResponse.ok(data=svc.seed_country_presets(db, force=force))


@router.patch("/countries/{preset_id}", summary="Update a country preset")
def update_country(
    preset_id: str,
    payload: CountryPresetUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_hr),
):
    enforce_abac(db, current_user, "country_preset", preset_id, action="update")
    row = actualizar_preset_de_pais(db, current_user, preset_id, payload.model_dump(exclude_none=True))
    return APIResponse.ok(data=svc.serialize_country(row))


@router.delete("/countries/{preset_id}", summary="Delete a country preset (org-scoped only)")
def delete_country(
    preset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_hr),
):
    enforce_abac(db, current_user, "country_preset", preset_id, action="delete")
    svc.borrar_preset_de_pais(db, current_user, preset_id)
    return APIResponse.ok(data={"ok": True})


# ── User cost profiles ───────────────────────────────────────────────────────
@router.get("/users/{user_id}/profiles", summary="List a user's cost profile history")
def list_user_profiles(
    user_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_hr),
):
    profiles = svc.list_profiles(db, user_id)
    items = [svc.serialize_profile(p) for p in profiles]
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/users/{user_id}/profiles", summary="Create a new cost profile for a user")
def create_user_profile(
    user_id: str,
    payload: ProfileIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_hr),
):
    svc.usuario_propio(db, current_user, user_id)
    org_id = getattr(current_user, "organization_id", None)
    profile = svc.create_profile(
        db,
        user_id=user_id,
        valid_from=payload.valid_from,
        gross_annual_salary=payload.gross_annual_salary,
        employer_cost_pct=payload.employer_cost_pct,
        extra_annual_costs=payload.extra_annual_costs,
        productive_hours_year=payload.productive_hours_year,
        country_code=payload.country_code,
        currency=payload.currency,
        notes=payload.notes,
        organization_id=org_id,
        created_by_user_id=current_user.id,
    )
    return APIResponse.ok(data=svc.serialize_profile(profile))


@router.get("/users/{user_id}/active", summary="Get the user's active cost profile + cost/hour")
def get_active(
    user_id: str,
    on: Optional[Date] = Query(None, description="Resolve as of this date (default: today)"),
    db: Session = Depends(get_db),
    # Antes esta dependencia se descartaba con `_`, y por eso nunca se escribio
    # la comprobacion de organizacion: el sujeto estaba ahi y se tiraba.
    current_user: User = Depends(require_admin_or_hr),
):
    # Este endpoint devuelve el perfil de coste y el `legacy_hourly_rate`: son
    # datos salariales, asi que la persona tiene que ser de la organizacion de
    # quien pregunta y no basta con que exista.
    user = svc.usuario_propio(db, current_user, user_id)
    profile = svc.get_active_profile(db, user_id, on)
    rate = svc.cost_per_hour(db, user, on)
    return APIResponse.ok(data={
        "user_id": user_id,
        "as_of": (on or Date.today()).isoformat(),
        "profile": svc.serialize_profile(profile) if profile else None,
        "cost_per_hour": rate,
        "source": "profile" if profile else ("legacy_hourly_rate" if rate else "none"),
        "legacy_hourly_rate": user.hourly_rate,
    })


@router.post("/users/{user_id}/preview", summary="Preview total annual cost + cost/hour from inputs")
def preview_cost(
    user_id: str,
    payload: PreviewIn,
    _: User = Depends(require_admin_or_hr),
):
    total, per_hour = svc.derive_cost(
        payload.gross_annual_salary,
        payload.employer_cost_pct,
        payload.extra_annual_costs,
        payload.productive_hours_year,
    )
    return APIResponse.ok(data={"total_annual_cost": total, "cost_per_hour": per_hour})


@router.patch("/profiles/{profile_id}", summary="Update a cost profile")
def update_profile(
    profile_id: str,
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_hr),
):
    enforce_abac(db, current_user, "user_cost_profile", profile_id, action="update")
    svc.perfil_propio(db, current_user, profile_id)
    p = svc.update_profile(db, profile_id, **payload.model_dump(exclude_none=True))
    return APIResponse.ok(data=svc.serialize_profile(p))


@router.delete("/profiles/{profile_id}", summary="Delete a cost profile")
def delete_profile(
    profile_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_hr),
):
    enforce_abac(db, current_user, "user_cost_profile", profile_id, action="delete")
    svc.perfil_propio(db, current_user, profile_id)
    svc.delete_profile(db, profile_id)
    return APIResponse.ok(data={"ok": True})


# ── Bulk summary for dashboards ──────────────────────────────────────────────
# Hard cap to evitar OOM en organizaciones grandes — el endpoint es para
# dashboards, no para enumerar todos los usuarios.
COST_SUMMARY_HARD_CAP = 2000


@router.get("/summary", summary="Bulk cost/hour and totals for all users")
def cost_summary(
    on: Optional[Date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_hr),
):
    on = on or Date.today()
    users = svc.usuarios_activos_de_la_organizacion(
        db, current_user, tope=COST_SUMMARY_HARD_CAP + 1)
    truncated = len(users) > COST_SUMMARY_HARD_CAP
    if truncated:
        users = users[:COST_SUMMARY_HARD_CAP]
    user_ids = [u.id for u in users]
    rates = svc.cost_per_hour_bulk(db, user_ids, on)
    items = []
    total_users_with_cost = 0
    sum_hourly = 0.0
    for u in users:
        rate = rates.get(u.id)
        has_profile = svc.get_active_profile(db, u.id, on) is not None
        items.append({
            "user_id": u.id,
            "full_name": u.full_name,
            "department": u.department,
            "cost_per_hour": rate,
            "source": "profile" if has_profile else ("legacy_hourly_rate" if rate else "none"),
        })
        if rate:
            total_users_with_cost += 1
            sum_hourly += rate
    return APIResponse.ok(data={
        "as_of": on.isoformat(),
        "users": items,
        "total_users": len(users),
        "users_with_cost": total_users_with_cost,
        "users_missing_cost": len(users) - total_users_with_cost,
        "avg_cost_per_hour": round(sum_hourly / total_users_with_cost, 2) if total_users_with_cost else 0,
        "truncated": truncated,
        "limit": COST_SUMMARY_HARD_CAP,
    })
