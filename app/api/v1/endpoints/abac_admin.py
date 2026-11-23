"""
ABAC Admin Dashboard + Policy Effectiveness Analytics.

Endpoints:
  GET  /abac/admin/overview              — KPI tiles for admin dashboard
  GET  /abac/admin/attributes/summary    — attribute coverage across org users
  GET  /abac/admin/policies/effectiveness — per-policy hit-rates, deny/allow ratios
  GET  /abac/admin/access-patterns       — who's hitting what, top denied resources
  GET  /abac/admin/users/{user_id}/access-profile — full attribute + policy view for one user
  GET  /abac/admin/audit-log             — filtered policy audit log
  GET  /abac/admin/audit-log/stats       — aggregate stats

Periodo libre (16-11-2026): los informes con ventana aceptan `desde`/`hasta`
(cualquier intervalo, con hora: las decisiones ABAC son instantes) y siguen
aceptando `days`. Ver `app/core/periodo.py`.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user, requiere_capacidad
from app.core.periodo import CON_HORA, Periodo, periodo
from app.core.responses import APIListResponse, APIResponse
from app.models.user import User
from app.services.abac import (
    get_admin_overview,
    get_attribute_summary,
    get_policy_effectiveness,
    get_access_patterns,
    get_user_access_profile,
    get_audit_log,
    get_audit_stats,
    get_org_id as _org,
)
from app.core.constantes import MAX_TAMANO_DE_PAGINA


# Auditoría 22-11-2026 (M9): `_permiso_de_gobierno` (guarda a mano: admin o superadmin)
# pasa a la capacidad `gobierno.administrar` (mismos roles), en la firma y LA PRIMERA,
# para que el 403 salga antes que el 422 del periodo (16-11-2026).

router = APIRouter(prefix="/abac/admin", tags=["ABAC Admin"])


# _org delegated to abac.get_org_id (see import above)


# ── Overview KPIs ─────────────────────────────────────────────────────────────

@router.get("/overview", summary="ABAC admin overview KPIs")
def abac_overview(
    _permiso: User = Depends(requiere_capacidad("gobierno.administrar")),
    p: Periodo = Depends(periodo(dias_por_defecto=30, granularidades=CON_HORA, serie=False,
                                 dias_alias_max=365)),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org = _org(current_user)
    data = get_admin_overview(db, org, p.desde, round(p.dias, 4), until=p.hasta)
    data["periodo"] = p.a_dict()
    return APIResponse.ok(data=data)


# ── Attribute coverage ────────────────────────────────────────────────────────

@router.get("/attributes/summary", summary="Attribute coverage across org users")
def attribute_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("gobierno.administrar")),
):
    org = _org(current_user)
    return APIListResponse.ok(items=get_attribute_summary(db, org))


# ── Policy effectiveness ──────────────────────────────────────────────────────

@router.get("/policies/effectiveness", summary="Per-policy hit-rates and deny/allow ratios")
def policy_effectiveness(
    _permiso: User = Depends(requiere_capacidad("gobierno.administrar")),
    p: Periodo = Depends(periodo(dias_por_defecto=30, granularidades=CON_HORA, serie=False,
                                 dias_alias_max=365)),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org = _org(current_user)
    # `hit_rate` es por dia: con un periodo de horas se usa la fraccion de dia real.
    return APIListResponse.ok(items=get_policy_effectiveness(db, org, p.desde, round(p.dias, 4), until=p.hasta))


# ── Access patterns ───────────────────────────────────────────────────────────

@router.get("/access-patterns", summary="Access patterns — top denied resources, top denied users")
def access_patterns(
    _permiso: User = Depends(requiere_capacidad("gobierno.administrar")),
    p: Periodo = Depends(periodo(dias_por_defecto=7, granularidades=CON_HORA, serie=True,
                                 dias_alias_max=90)),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """`daily_trend` va por tramos de `granularidad` (relleno con ceros); cada
    punto lleva `t` (ISO), `clave` y, por compatibilidad, `date`."""
    org = _org(current_user)
    data = get_access_patterns(db, org, p.desde, round(p.dias, 4), limit, p=p)
    data["periodo"] = p.a_dict()
    return APIResponse.ok(data=data)


# ── Per-user access profile ───────────────────────────────────────────────────

@router.get("/users/{user_id}/access-profile", summary="Full attribute + matching policy view for a user")
def user_access_profile(
    user_id: str,
    resource_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("gobierno.administrar")),
):
    org = _org(current_user)
    return APIResponse.ok(data=get_user_access_profile(db, org, user_id, resource_type))


# ── Audit log ─────────────────────────────────────────────────────────────────

@router.get("/audit-log", summary="Filtered ABAC policy audit log")
def abac_audit_log(
    _permiso: User = Depends(requiere_capacidad("gobierno.administrar")),
    result:        Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    user_id:       Optional[str] = Query(None),
    p: Periodo                   = Depends(periodo(dias_por_defecto=30, granularidades=CON_HORA,
                                                   serie=False, dias_alias_max=365)),
    page:          int           = Query(1, ge=1),
    page_size:     int           = Query(50, ge=1, le=MAX_TAMANO_DE_PAGINA),
    db: Session                  = Depends(get_db),
    current_user: User           = Depends(get_current_user),
):
    org   = _org(current_user)
    data = get_audit_log(db, org, p.desde, result, resource_type, user_id, page, page_size, until=p.hasta)
    data["periodo"] = p.a_dict()
    return APIResponse.ok(data=data)


@router.get("/audit-log/stats", summary="Aggregate deny/allow stats")
def abac_audit_stats(
    _permiso: User = Depends(requiere_capacidad("gobierno.administrar")),
    p: Periodo = Depends(periodo(dias_por_defecto=30, granularidades=CON_HORA, serie=False,
                                 dias_alias_max=365)),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org   = _org(current_user)
    data = get_audit_stats(db, org, p.desde, round(p.dias, 4), until=p.hasta)
    data["periodo"] = p.a_dict()
    return APIResponse.ok(data=data)
