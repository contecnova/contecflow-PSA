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
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user
from app.core.security import verify_admin_or_governance_role
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

router = APIRouter(prefix="/abac/admin", tags=["ABAC Admin"])


# _org delegated to abac.get_org_id (see import above)


# ── Overview KPIs ─────────────────────────────────────────────────────────────

@router.get("/overview", summary="ABAC admin overview KPIs")
def abac_overview(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    verify_admin_or_governance_role(current_user)
    org = _org(current_user)
    since = datetime.utcnow() - timedelta(days=days)
    return get_admin_overview(db, org, since, days)


# ── Attribute coverage ────────────────────────────────────────────────────────

@router.get("/attributes/summary", summary="Attribute coverage across org users")
def attribute_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    verify_admin_or_governance_role(current_user)
    org = _org(current_user)
    return get_attribute_summary(db, org)


# ── Policy effectiveness ──────────────────────────────────────────────────────

@router.get("/policies/effectiveness", summary="Per-policy hit-rates and deny/allow ratios")
def policy_effectiveness(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    verify_admin_or_governance_role(current_user)
    org = _org(current_user)
    since = datetime.utcnow() - timedelta(days=days)
    return get_policy_effectiveness(db, org, since, days)


# ── Access patterns ───────────────────────────────────────────────────────────

@router.get("/access-patterns", summary="Access patterns — top denied resources, top denied users")
def access_patterns(
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    verify_admin_or_governance_role(current_user)
    org = _org(current_user)
    since = datetime.utcnow() - timedelta(days=days)
    return get_access_patterns(db, org, since, days, limit)


# ── Per-user access profile ───────────────────────────────────────────────────

@router.get("/users/{user_id}/access-profile", summary="Full attribute + matching policy view for a user")
def user_access_profile(
    user_id: str,
    resource_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    verify_admin_or_governance_role(current_user)
    org = _org(current_user)
    return get_user_access_profile(db, org, user_id, resource_type)


# ── Audit log ─────────────────────────────────────────────────────────────────

@router.get("/audit-log", summary="Filtered ABAC policy audit log")
def abac_audit_log(
    result:        Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    user_id:       Optional[str] = Query(None),
    days:          int           = Query(30, ge=1, le=365),
    page:          int           = Query(1, ge=1),
    page_size:     int           = Query(50, ge=1, le=200),
    db: Session                  = Depends(get_db),
    current_user: User           = Depends(get_current_user),
):
    verify_admin_or_governance_role(current_user)
    org   = _org(current_user)
    since = datetime.utcnow() - timedelta(days=days)
    return get_audit_log(db, org, since, result, resource_type, user_id, page, page_size)


@router.get("/audit-log/stats", summary="Aggregate deny/allow stats")
def abac_audit_stats(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    verify_admin_or_governance_role(current_user)
    org   = _org(current_user)
    since = datetime.utcnow() - timedelta(days=days)
    return get_audit_stats(db, org, since, days)
