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

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user
from app.core.security import verify_admin_or_governance_role
from app.models.user import User
from app.models.abac import ABACPolicy, UserAttribute, AttributeDefinition, PolicyAudit
from app.services.abac import ABACService

router = APIRouter(prefix="/abac/admin", tags=["ABAC Admin"])


def _org(user: User) -> str:
    if not user.organization_id:
        raise HTTPException(400, "User has no organization")
    return str(user.organization_id)


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

    total_policies  = db.query(func.count(ABACPolicy.id)).filter(ABACPolicy.org_id == org).scalar() or 0
    active_policies = db.query(func.count(ABACPolicy.id)).filter(
        ABACPolicy.org_id == org, ABACPolicy.is_active == True  # noqa
    ).scalar() or 0

    total_users_with_attrs = db.query(func.count(func.distinct(UserAttribute.user_id))).filter(
        UserAttribute.org_id == org
    ).scalar() or 0

    total_attr_defs = db.query(func.count(AttributeDefinition.id)).filter(
        AttributeDefinition.org_id == org
    ).scalar() or 0

    base_audit = db.query(PolicyAudit).filter(
        PolicyAudit.org_id      == org,
        PolicyAudit.created_at  >= since,
    )
    total_evaluations = base_audit.count()
    total_denials     = base_audit.filter(PolicyAudit.result == "deny").count()
    total_allows      = base_audit.filter(PolicyAudit.result == "allow").count()
    deny_rate         = round(total_denials / total_evaluations, 4) if total_evaluations else 0.0

    # Expired attributes
    now = datetime.utcnow()
    expired_attrs = db.query(func.count(UserAttribute.id)).filter(
        UserAttribute.org_id    == org,
        UserAttribute.expires_at < now,
    ).scalar() or 0

    return {
        "window_days":         days,
        "total_policies":      total_policies,
        "active_policies":     active_policies,
        "inactive_policies":   total_policies - active_policies,
        "attribute_definitions":total_attr_defs,
        "users_with_attributes":total_users_with_attrs,
        "expired_attributes":  expired_attrs,
        "total_evaluations":   total_evaluations,
        "total_denials":       total_denials,
        "total_allows":        total_allows,
        "deny_rate":           deny_rate,
    }


# ── Attribute coverage ────────────────────────────────────────────────────────

@router.get("/attributes/summary", summary="Attribute coverage across org users")
def attribute_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    verify_admin_or_governance_role(current_user)
    org = _org(current_user)

    rows = db.query(
        UserAttribute.attribute_key,
        func.count(func.distinct(UserAttribute.user_id)).label("user_count"),
        func.count(UserAttribute.id).label("assignment_count"),
    ).filter(
        UserAttribute.org_id == org
    ).group_by(UserAttribute.attribute_key).all()

    now = datetime.utcnow()
    expiring_soon = db.query(
        UserAttribute.attribute_key,
        func.count(UserAttribute.id).label("expiring"),
    ).filter(
        UserAttribute.org_id     == org,
        UserAttribute.expires_at.isnot(None),
        UserAttribute.expires_at >  now,
        UserAttribute.expires_at <= now + timedelta(days=7),
    ).group_by(UserAttribute.attribute_key).all()

    expiring_map = {k: v for k, v in expiring_soon}

    return [
        {
            "attribute_key":    r.attribute_key,
            "user_count":       r.user_count,
            "assignment_count": r.assignment_count,
            "expiring_in_7d":   expiring_map.get(r.attribute_key, 0),
        }
        for r in rows
    ]


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

    policies = db.query(ABACPolicy).filter(ABACPolicy.org_id == org).all()

    result = []
    for p in policies:
        # Count audit log entries where this policy was matched
        total_hits = db.query(func.count(PolicyAudit.id)).filter(
            PolicyAudit.org_id     == org,
            PolicyAudit.created_at >= since,
            # matched_policies is a JSON array — check for policy id using SQL JSON contains
            func.json_extract(PolicyAudit.matched_policies, "$").like(f"%{p.id}%"),
        ).scalar() or 0

        deny_hits = db.query(func.count(PolicyAudit.id)).filter(
            PolicyAudit.org_id     == org,
            PolicyAudit.result     == "deny",
            PolicyAudit.created_at >= since,
            func.json_extract(PolicyAudit.matched_policies, "$").like(f"%{p.id}%"),
        ).scalar() or 0

        allow_hits = total_hits - deny_hits

        result.append({
            "policy_id":     p.id,
            "policy_name":   p.policy_name,
            "effect":        p.effect,
            "is_active":     p.is_active,
            "priority":      p.priority,
            "resource_types":p.resource_types or [],
            "total_hits":    total_hits,
            "deny_hits":     deny_hits,
            "allow_hits":    allow_hits,
            "hit_rate":      round(total_hits / max(1, days), 2),
            "deny_rate":     round(deny_hits / max(1, total_hits), 4) if total_hits else 0.0,
            "expires_at":    p.expires_at.isoformat() if p.expires_at else None,
        })

    result.sort(key=lambda x: -x["total_hits"])
    return result


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

    # Top denied users
    top_denied_users = db.query(
        PolicyAudit.user_id,
        func.count(PolicyAudit.id).label("deny_count"),
    ).filter(
        PolicyAudit.org_id     == org,
        PolicyAudit.result     == "deny",
        PolicyAudit.created_at >= since,
        PolicyAudit.user_id.isnot(None),
    ).group_by(PolicyAudit.user_id).order_by(text("deny_count DESC")).limit(limit).all()

    # Top denied resource types
    top_denied_resources = db.query(
        PolicyAudit.resource_type,
        func.count(PolicyAudit.id).label("deny_count"),
    ).filter(
        PolicyAudit.org_id        == org,
        PolicyAudit.result        == "deny",
        PolicyAudit.created_at    >= since,
        PolicyAudit.resource_type.isnot(None),
    ).group_by(PolicyAudit.resource_type).order_by(text("deny_count DESC")).limit(limit).all()

    # Deny trend (daily)
    all_entries = db.query(
        PolicyAudit.result,
        PolicyAudit.created_at,
    ).filter(
        PolicyAudit.org_id     == org,
        PolicyAudit.created_at >= since,
    ).all()

    daily: Dict[str, Dict[str, int]] = {}
    for result, ts in all_entries:
        day = ts.date().isoformat()
        if day not in daily:
            daily[day] = {"date": day, "allow": 0, "deny": 0}
        daily[day][result] = daily[day].get(result, 0) + 1
    trend = sorted(daily.values(), key=lambda x: x["date"])

    return {
        "window_days":       days,
        "top_denied_users":  [{"user_id": r.user_id, "deny_count": r.deny_count} for r in top_denied_users],
        "top_denied_resources": [{"resource_type": r.resource_type, "deny_count": r.deny_count} for r in top_denied_resources],
        "daily_trend":       trend,
    }


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

    svc = ABACService(db=db, org_id=org)
    attributes = svc.get_user_attributes(user_id)

    # Recent audit entries
    recent = db.query(PolicyAudit).filter(
        PolicyAudit.org_id   == org,
        PolicyAudit.user_id  == user_id,
    ).order_by(PolicyAudit.created_at.desc()).limit(20).all()

    # Active policies that could apply to this user
    user_obj = db.query(User).filter(User.id == user_id).first()
    user_role = (user_obj.role.value if hasattr(user_obj.role, "value") else str(user_obj.role)) if user_obj else ""

    all_policies = db.query(ABACPolicy).filter(
        ABACPolicy.org_id    == org,
        ABACPolicy.is_active == True,  # noqa
    ).all()

    applicable = []
    for p in all_policies:
        if p.applicable_roles and user_role not in p.applicable_roles:
            continue
        if p.subject_users and user_id not in p.subject_users:
            continue
        if resource_type and p.resource_types and resource_type not in p.resource_types:
            continue
        applicable.append({
            "policy_id":   p.id,
            "name":        p.policy_name,
            "effect":      p.effect,
            "priority":    p.priority,
            "resource_types": p.resource_types or [],
        })

    return {
        "user_id":            user_id,
        "user_role":          user_role,
        "attributes":         attributes,
        "applicable_policies": applicable,
        "recent_decisions":   [
            {
                "id":            e.id,
                "action":        e.action,
                "result":        e.result,
                "resource_type": e.resource_type,
                "resource_id":   e.resource_id,
                "created_at":    e.created_at.isoformat() if e.created_at else None,
            }
            for e in recent
        ],
    }


# ── Audit log ─────────────────────────────────────────────────────────────────

@router.get("/audit-log", summary="Filtered ABAC policy audit log")
def abac_audit_log(
    result:       Optional[str] = Query(None),
    resource_type:Optional[str] = Query(None),
    user_id:      Optional[str] = Query(None),
    days:         int           = Query(30, ge=1, le=365),
    page:         int           = Query(1, ge=1),
    page_size:    int           = Query(50, ge=1, le=200),
    db: Session                 = Depends(get_db),
    current_user: User          = Depends(get_current_user),
):
    verify_admin_or_governance_role(current_user)
    org   = _org(current_user)
    since = datetime.utcnow() - timedelta(days=days)

    q = db.query(PolicyAudit).filter(
        PolicyAudit.org_id     == org,
        PolicyAudit.created_at >= since,
    )
    if result:        q = q.filter(PolicyAudit.result        == result)
    if resource_type: q = q.filter(PolicyAudit.resource_type == resource_type)
    if user_id:       q = q.filter(PolicyAudit.user_id       == user_id)

    total = q.count()
    items = q.order_by(PolicyAudit.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()

    return {
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "items": [
            {
                "id":             e.id,
                "user_id":        e.user_id,
                "action":         e.action,
                "result":         e.result,
                "resource_type":  e.resource_type,
                "resource_id":    e.resource_id,
                "matched_policies":e.matched_policies,
                "created_at":     e.created_at.isoformat() if e.created_at else None,
            }
            for e in items
        ],
    }


@router.get("/audit-log/stats", summary="Aggregate deny/allow stats")
def abac_audit_stats(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    verify_admin_or_governance_role(current_user)
    org   = _org(current_user)
    since = datetime.utcnow() - timedelta(days=days)

    total  = db.query(func.count(PolicyAudit.id)).filter(
        PolicyAudit.org_id == org, PolicyAudit.created_at >= since
    ).scalar() or 0
    denials = db.query(func.count(PolicyAudit.id)).filter(
        PolicyAudit.org_id == org, PolicyAudit.created_at >= since, PolicyAudit.result == "deny"
    ).scalar() or 0
    allows = total - denials

    return {
        "window_days": days,
        "total":       total,
        "denials":     denials,
        "allows":      allows,
        "deny_rate":   round(denials / total, 4) if total else 0.0,
    }
