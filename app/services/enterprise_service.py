"""
Enterprise service — business logic extracted from enterprise.py router.
Covers: serializers, subcontractor worker creation, revenue forecast aggregation,
        audit stats computation, webhook test, SSO config validation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.encryption import encrypt_value

if TYPE_CHECKING:
    from app.models.enterprise import (
        Webhook, SSOConfig, Subcontractor, RevenueForecast,
    )


# ── Serializers ───────────────────────────────────────────────────────────────

def serialize_webhook(h) -> dict:
    import json
    return {
        "id": h.id, "name": h.name, "url": h.url,
        "has_secret": bool(h.secret),
        "events": json.loads(h.events) if h.events else [],
        "is_active": h.is_active,
        "project_id": h.project_id,
        "project_name": h.project.name if h.project else None,
        "total_deliveries": h.total_deliveries or 0,
        "failed_deliveries": h.failed_deliveries or 0,
        "last_triggered_at": str(h.last_triggered_at)[:16] if h.last_triggered_at else None,
        "created_at": str(h.created_at)[:10] if h.created_at else None,
    }


def serialize_sso(s) -> dict:
    import json
    return {
        "id": s.id, "provider": s.provider,
        "is_active": s.is_active, "is_default": s.is_default,
        "saml_entity_id": s.saml_entity_id,
        "saml_sso_url": s.saml_sso_url,
        "saml_slo_url": s.saml_slo_url,
        "has_certificate": bool(s.saml_certificate),
        "saml_attribute_email": s.saml_attribute_email,
        "saml_attribute_name": s.saml_attribute_name,
        "saml_attribute_role": s.saml_attribute_role,
        "oidc_client_id": s.oidc_client_id,
        "has_oidc_secret": bool(s.oidc_client_secret),
        "oidc_discovery_url": s.oidc_discovery_url,
        "oidc_scopes": s.oidc_scopes,
        "role_mapping": json.loads(s.role_mapping) if s.role_mapping else {},
        "organization_id": s.organization_id,
        "auto_create_users": s.auto_create_users,
        "default_role": s.default_role,
        "allowed_domains": s.allowed_domains,
        "created_at": str(s.created_at)[:10] if s.created_at else None,
        "sp_entity_id": f"{settings.BASE_URL}/api/v1/auth/saml/metadata",
        "sp_acs_url": f"{settings.BASE_URL}/api/v1/auth/saml/callback",
        "sp_slo_url": f"{settings.BASE_URL}/api/v1/auth/saml/logout",
    }


def serialize_subcontractor(s) -> dict:
    return {
        "id": s.id, "code": s.code, "name": s.name, "company": s.company,
        "email": s.email, "phone": s.phone, "country": s.country,
        "vat_number": s.vat_number, "currency": s.currency,
        "is_active": s.is_active, "notes": s.notes,
        "rates": [{
            "id": r.id, "description": r.description,
            "cost_rate": r.cost_rate, "sell_rate": r.sell_rate,
            "currency": r.currency,
            "valid_from": str(r.valid_from) if r.valid_from else None,
            "valid_until": str(r.valid_until) if r.valid_until else None,
        } for r in (s.rates or [])],
        "assignment_count": len(s.assignments or []),
        "worker_count": len(s.workers or []),
    }


def serialize_worker(w) -> dict:
    return {
        "id": w.id,
        "subcontractor_id": w.subcontractor_id,
        "user_id": w.user_id,
        "login_username": w.user.username if w.user else None,
        "name": w.name,
        "role": w.role,
        "email": w.email,
        "phone": w.phone,
        "cost_rate": w.cost_rate,
        "sell_rate": w.sell_rate,
        "currency": w.currency,
        "available_from": str(w.available_from) if w.available_from else None,
        "available_until": str(w.available_until) if w.available_until else None,
        "weekly_capacity_hours": w.weekly_capacity_hours,
        "is_active": w.is_active,
        "notes": w.notes,
        "skills": [{
            "id": sk.id,
            "skill_id": sk.skill_id,
            "skill_name": sk.skill.name if sk.skill else None,
            "skill_category": sk.skill.category.value if sk.skill and sk.skill.category else None,
            "level": sk.level,
            "years_experience": sk.years_experience,
            "certified": sk.certified,
            "cert_name": sk.cert_name,
            "notes": sk.notes,
        } for sk in (w.skills or [])],
        "assignment_count": len(w.assignments or []),
    }


def serialize_forecast(f) -> dict:
    revenue = f.revenue_forecast or f.revenue_planned or 0
    cost = f.cost_actual or f.cost_planned or 0
    margin = round((revenue - cost) / revenue * 100, 1) if revenue > 0 else None
    return {
        "id": f.id, "project_id": f.project_id, "year": f.year, "month": f.month,
        "revenue_planned": f.revenue_planned or 0,
        "revenue_actual": f.revenue_actual or 0,
        "revenue_forecast": f.revenue_forecast or 0,
        "cost_planned": f.cost_planned or 0,
        "cost_actual": f.cost_actual or 0,
        "hours_planned": f.hours_planned or 0,
        "hours_actual": f.hours_actual or 0,
        "margin_pct": margin,
        "notes": f.notes,
    }


# ── Business logic ─────────────────────────────────────────────────────────────

def next_sub_code(db: Session) -> str:
    import re
    max_code = db.query(func.max(__import__('app.models.enterprise', fromlist=['Subcontractor']).Subcontractor.code)).scalar()
    if max_code:
        m = re.search(r"(\d+)$", max_code)
        next_num = (int(m.group(1)) + 1) if m else 1
    else:
        next_num = 1
    return f"SUB-{next_num:04d}"


def compute_audit_stats(db: Session, days: int) -> dict:
    from app.models.enterprise import AuditLog
    from datetime import timedelta
    since = datetime.now(timezone.utc) - timedelta(days=days)
    logs = db.query(AuditLog).filter(AuditLog.created_at >= since).all()
    by_action: dict = {}
    by_resource: dict = {}
    by_user: dict = {}
    for l in logs:
        by_action[l.action] = by_action.get(l.action, 0) + 1
        by_resource[l.resource] = by_resource.get(l.resource, 0) + 1
        if l.user_name:
            by_user[l.user_name] = by_user.get(l.user_name, 0) + 1
    return {
        "total_events": len(logs),
        "period_days": days,
        "by_action": dict(sorted(by_action.items(), key=lambda x: -x[1])[:10]),
        "by_resource": dict(sorted(by_resource.items(), key=lambda x: -x[1])[:10]),
        "top_users": dict(sorted(by_user.items(), key=lambda x: -x[1])[:10]),
    }


def test_webhook_delivery(hook, current_user) -> dict:
    """Send a test payload to a webhook URL and return result."""
    import httpx, time, json
    test_payload = {
        "event": "test",
        "message": "This is a test delivery from Clarive",
        "triggered_by": current_user.full_name,
    }
    try:
        body = json.dumps({"event": "test", "data": test_payload}, default=str)
        start = time.time()
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(hook.url, content=body,
                               headers={"Content-Type": "application/json",
                                        "User-Agent": "Clarive-Test/11.0"})
        return {
            "ok": resp.status_code < 400,
            "status_code": resp.status_code,
            "response": resp.text[:200],
            "duration_ms": int((time.time() - start) * 1000),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def validate_sso_config(config) -> dict:
    """Validate SSO configuration fields without authenticating."""
    issues = []
    if config.provider == "saml":
        if not config.saml_entity_id: issues.append("Falta Entity ID del IdP")
        if not config.saml_sso_url:   issues.append("Falta SSO URL del IdP")
        if not config.saml_certificate: issues.append("Falta certificado X.509 del IdP")
    elif config.provider in ["oidc", "google", "azure_ad", "okta"]:
        if not config.oidc_client_id:     issues.append("Falta Client ID")
        if not config.oidc_client_secret: issues.append("Falta Client Secret")
        if config.provider == "oidc" and not config.oidc_discovery_url:
            issues.append("Falta Discovery URL (OIDC)")
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "provider": config.provider,
        "sp_metadata_url": "GET /api/v1/auth/saml/metadata",
    }


def get_portfolio_forecast(db: Session, year: int) -> dict:
    """Aggregate revenue forecast across all projects for a given year."""
    from app.models.enterprise import RevenueForecast
    from sqlalchemy.orm import joinedload

    forecasts = db.query(RevenueForecast).options(
        joinedload(RevenueForecast.project)
    ).filter(RevenueForecast.year == year).all()

    by_month: dict = {}
    for f in forecasts:
        m = f.month
        if m not in by_month:
            by_month[m] = {
                "month": m, "revenue_planned": 0, "revenue_actual": 0,
                "revenue_forecast": 0, "cost_planned": 0, "cost_actual": 0,
                "hours_planned": 0, "hours_actual": 0,
            }
        by_month[m]["revenue_planned"] += f.revenue_planned or 0
        by_month[m]["revenue_actual"] += f.revenue_actual or 0
        by_month[m]["revenue_forecast"] += f.revenue_forecast or 0
        by_month[m]["cost_planned"] += f.cost_planned or 0
        by_month[m]["cost_actual"] += f.cost_actual or 0
        by_month[m]["hours_planned"] += f.hours_planned or 0
        by_month[m]["hours_actual"] += f.hours_actual or 0

    monthly = [by_month[m] for m in sorted(by_month.keys())]
    total_forecast = sum(m["revenue_forecast"] for m in monthly)
    total_actual   = sum(m["revenue_actual"] for m in monthly)
    total_cost     = sum(m["cost_actual"] for m in monthly)
    total_margin   = round((total_forecast - total_cost) / total_forecast * 100, 1) if total_forecast else None

    return {
        "year": year,
        "monthly": monthly,
        "totals": {
            "revenue_forecast": round(total_forecast, 2),
            "revenue_actual": round(total_actual, 2),
            "cost_actual": round(total_cost, 2),
            "margin_pct": total_margin,
        },
        "projects": len(set(f.project_id for f in forecasts)),
    }


def create_worker_with_user(sub, payload, current_user, db: Session) -> dict:
    """Create a SubcontractorWorker and its linked User record."""
    import re, secrets
    from app.models.enterprise import SubcontractorWorker
    from app.models.user import User, UserRole as ModelUserRole, UserStatus
    from app.core.security import get_password_hash
    from app.services.audit import audit_log

    base = re.sub(r"[^a-z0-9]", ".", payload.name.lower().strip())
    base = re.sub(r"\.{2,}", ".", base).strip(".")
    base_username = f"{base}.{sub.code.lower()}"
    username = base_username
    suffix = 0
    while db.query(User).filter(User.username == username).first():
        suffix += 1
        username = f"{base_username}{suffix}"

    email = payload.email
    if email:
        if db.query(User).filter(User.email == email).first():
            email = f"{username}@subcontractor.internal"
    else:
        email = f"{username}@subcontractor.internal"

    name_parts = payload.name.strip().split(" ", 1)
    first_name = name_parts[0]
    last_name = name_parts[1] if len(name_parts) > 1 else None

    temp_password = secrets.token_urlsafe(12)

    linked_user = User(
        username=username,
        email=email,
        full_name=payload.name,
        first_name=first_name,
        last_name=last_name,
        job_title=payload.role,
        department=sub.name,
        role=ModelUserRole.subcontractor,
        status=UserStatus.active,
        weekly_capacity_hours=payload.weekly_capacity_hours or settings.DEFAULT_WEEKLY_CAPACITY_HOURS,
        hourly_rate=payload.cost_rate,
        currency=payload.currency,
        phone=payload.phone,
        is_active=True,
        organization_id=current_user.organization_id,
        hashed_password=get_password_hash(temp_password),
    )
    db.add(linked_user)
    db.flush()

    worker = SubcontractorWorker(
        subcontractor_id=sub.id,
        user_id=linked_user.id,
        weekly_capacity_hours=payload.weekly_capacity_hours,
        **{k: v for k, v in payload.model_dump().items() if k != "weekly_capacity_hours"},
    )
    db.add(worker)
    audit_log(db, current_user, "CREATE", "subcontractor_workers", worker.id, worker.name)
    db.commit()
    db.refresh(worker)
    result = serialize_worker(worker)
    result["login_username"] = linked_user.username
    result["temp_password"] = temp_password
    return result
