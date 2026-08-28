"""
Enterprise service — business logic extracted from enterprise.py router.
Covers: serializers, subcontractor worker creation, revenue forecast aggregation,
        audit stats computation, webhook test, SSO config validation.
"""
from __future__ import annotations

import ipaddress
import logging
import socket
import urllib.parse as _urlparse
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy import func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Networks that must never be reachable from an outbound webhook delivery.
# Covers: loopback, RFC 1918, link-local (incl. AWS/GCP/Azure metadata),
# CGN (RFC 6598), documentation, IPv6 ULA, IPv6 link-local.
_BLOCKED_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),   # link-local / AWS+GCP metadata
    ipaddress.ip_network("100.64.0.0/10"),    # CGN (RFC 6598)
    ipaddress.ip_network("192.0.2.0/24"),     # TEST-NET-1 (RFC 5737)
    ipaddress.ip_network("198.51.100.0/24"),  # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),   # TEST-NET-3
    ipaddress.ip_network("::1/128"),          # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),         # IPv6 ULA
    ipaddress.ip_network("fe80::/10"),        # IPv6 link-local
]
_BLOCKED_HOSTNAMES: frozenset[str] = frozenset({
    "169.254.169.254",           # AWS/GCP/Azure IMDS
    "metadata.google.internal",
    "metadata.google",
    "metadata",
})


def _validate_webhook_url(url: str) -> None:
    """Raise ValueError if *url* is not safe for outbound webhook delivery.

    Checks:
    - Scheme must be https.
    - Hostname must not be a known metadata endpoint.
    - Resolved IP addresses must not fall in any RFC 1918 / loopback /
      link-local / reserved range (SSRF prevention).

    Raises:
        ValueError: with a human-readable reason; caller should log this.
    """
    try:
        parsed = _urlparse.urlparse(url)
    # intentional: chained re-raise preserves context
    except Exception as exc:
        raise ValueError(f"URL malformada: {url!r}") from exc

    if parsed.scheme != "https":
        raise ValueError("Solo se permiten destinos HTTPS en webhooks")

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise ValueError("URL de webhook sin hostname")

    if hostname in _BLOCKED_HOSTNAMES:
        raise ValueError(f"Hostname de metadata bloqueado: {hostname!r}")

    # Resolve all addresses the hostname maps to and reject any internal one.
    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    # intentional: chained re-raise preserves context
    except socket.gaierror as exc:
        raise ValueError(f"No se pudo resolver el hostname {hostname!r}: {exc}") from exc

    for _family, _type, _proto, _canonname, sockaddr in addr_infos:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if ip.is_loopback or ip.is_link_local or ip.is_private or ip.is_reserved or ip.is_unspecified:
            raise ValueError(f"Destino bloqueado — IP interna/reservada: {ip_str}")
        for net in _BLOCKED_NETWORKS:
            if ip in net:
                raise ValueError(f"Destino bloqueado — red interna {net}: {ip_str}")

from app.core.config import settings
from app.core.encryption import encrypt_value
from app.core.security import get_password_hash
from app.models.enterprise import AuditLog
from app.models.enterprise import RevenueForecast
from app.models.enterprise import Subcontractor
from app.models.enterprise import SubcontractorWorker
from app.models.enterprise import ProjectPermission
from app.models.enterprise import Webhook
from app.models.enterprise import WebhookDelivery
from app.models.enterprise import SSOConfig
from app.models.enterprise import Notification
from app.models.enterprise import SubcontractorRate
from app.models.enterprise import SubcontractorAssignment
from app.models.enterprise import SubcontractorWorkerSkill
from app.models.enterprise import SubcontractorTimeLog
from app.models.enterprise import SubcontractorInvoice
from app.models.project import Project
from app.models.user import User, UserRole as ModelUserRole, UserStatus
from app.services.audit import audit_log
from app.services.notifications import notify_user
from datetime import timedelta
from datetime import datetime as _dt
from sqlalchemy import func as _func
from sqlalchemy.orm import joinedload

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
        } for r in (s.rates or []) if r.is_active],
        "assignment_count": len(s.assignments or []),
        "worker_count": len([w for w in (s.workers or []) if w.is_active]),
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
        } for sk in (w.skills or []) if sk.is_active],
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
    from app.models.enterprise import Subcontractor as _Subcontractor  # local import to avoid circular dependency
    max_code = db.query(func.max(_Subcontractor.code)).scalar()
    if max_code:
        m = re.search(r"(\d+)$", max_code)
        next_num = (int(m.group(1)) + 1) if m else 1
    else:
        next_num = 1
    return f"SUB-{next_num:04d}"


def compute_audit_stats(db: Session, days: int) -> dict:
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
    """Send a test payload to a webhook URL and return result.

    The destination URL is validated against SSRF risks before the request
    is made.  Blocked attempts are logged as warnings for audit purposes.
    """
    import httpx
    import json
    import time

    # ── SSRF guard — must happen before any network I/O ──────────────────────
    try:
        _validate_webhook_url(hook.url)
    except ValueError as exc:
        actor = getattr(current_user, "email", "unknown")
        logger.warning(
            "Webhook SSRF attempt blocked: actor=%s hook_id=%s url=%r reason=%s",
            actor,
            getattr(hook, "id", "?"),
            hook.url,
            exc,
        )
        return {"ok": False, "blocked": True, "error": f"URL no permitida: {exc}"}

    test_payload = {
        "event": "test",
        "message": "This is a test delivery from Contecflow",
        "triggered_by": current_user.full_name,
    }
    try:
        body = json.dumps({"event": "test", "data": test_payload}, default=str)
        start = time.time()
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                hook.url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "Contecflow-Test/11.0",
                },
            )
        return {
            "ok": resp.status_code < 400,
            "status_code": resp.status_code,
            "response": resp.text[:200],
            "duration_ms": int((time.time() - start) * 1000),
        }
    except httpx.TimeoutException as exc:
        logger.warning("Webhook delivery timeout: url=%r error=%s", hook.url, exc)
        return {"ok": False, "error": "Timeout al conectar con el destino del webhook"}
    except httpx.RequestError as exc:
        logger.warning("Webhook delivery network error: url=%r error=%s", hook.url, exc)
        return {"ok": False, "error": f"Error de red: {exc}"}


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


def get_subcontractor(db: Session, sub_id: str):
    return db.query(Subcontractor).filter(Subcontractor.id == sub_id, Subcontractor.is_active == True).first()


def create_worker_with_user(sub, payload, current_user, db: Session) -> dict:
    """Create a SubcontractorWorker and its linked User record."""
    import re, secrets

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


# ── Audit log ─────────────────────────────────────────────────────────────────

def get_audit_log(db: Session, resource, resource_id, user_id, action, date_from, date_to, page, page_size) -> dict:
    import json as _json
    q = db.query(AuditLog)
    if resource:    q = q.filter(AuditLog.resource == resource)
    if resource_id: q = q.filter(AuditLog.resource_id == resource_id)
    if user_id:     q = q.filter(AuditLog.user_id == user_id)
    if action:      q = q.filter(AuditLog.action == action.upper())
    if date_from:   q = q.filter(AuditLog.created_at >= date_from)
    if date_to:     q = q.filter(AuditLog.created_at <= _dt.combine(date_to, _dt.max.time()))
    total = q.count()
    logs = q.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total, "page": page, "pages": -(-total // page_size),
        "logs": [{
            "id": l.id, "user_name": l.user_name, "ip_address": l.ip_address,
            "action": l.action, "resource": l.resource,
            "resource_id": l.resource_id, "resource_name": l.resource_name,
            "old_values": _json.loads(l.old_values) if l.old_values else None,
            "new_values": _json.loads(l.new_values) if l.new_values else None,
            "created_at": str(l.created_at)[:19],
        } for l in logs],
    }


# ── Project Permissions ───────────────────────────────────────────────────────

def get_project_permissions(project_id: str, db: Session) -> list:
    perms = db.query(ProjectPermission).options(
        joinedload(ProjectPermission.user)
    ).filter(
        ProjectPermission.project_id == project_id,
        ProjectPermission.is_active == True,
    ).all()
    return [{
        "id": p.id, "user_id": p.user_id,
        "user_name": p.user.full_name if p.user else None,
        "user_email": p.user.email if p.user else None,
        "user_role": p.user.role if p.user else None,
        "level": p.level, "can_see_financials": p.can_see_financials,
        "can_see_rates": p.can_see_rates, "can_export": p.can_export,
        "granted_by": p.granted_by,
        "granted_at": str(p.granted_at)[:10] if p.granted_at else None,
        "expires_at": str(p.expires_at)[:10] if p.expires_at else None,
        "note": p.note,
    } for p in perms]


def grant_project_permission(project_id: str, payload, current_user, db: Session) -> dict:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("Proyecto no encontrado")
    existing = db.query(ProjectPermission).filter(
        ProjectPermission.project_id == project_id,
        ProjectPermission.user_id == payload.user_id,
        ProjectPermission.is_active == True,
    ).first()
    if existing:
        for k, v in payload.model_dump(exclude_unset=True).items():
            setattr(existing, k, v)
    else:
        existing = ProjectPermission(project_id=project_id, granted_by=current_user.id, **payload.model_dump())
        db.add(existing)
    audit_log(db, current_user, "GRANT_PERMISSION", "projects", project_id, project.name,
              new_values={"user_id": payload.user_id, "level": payload.level})
    db.commit()
    user = db.query(User).filter(User.id == payload.user_id).first()
    if user:
        notify_user(db, user.id, "system",
                    f"Acceso concedido al proyecto {project.name}",
                    f"{current_user.full_name} te ha dado acceso como {payload.level}",
                    resource="projects", resource_id=project_id, action_url="/projects")
        db.commit()
    return {"ok": True}


def update_project_permission(project_id: str, permission_id: str, payload, db: Session) -> dict:
    perm = db.query(ProjectPermission).filter(
        ProjectPermission.id == permission_id,
        ProjectPermission.project_id == project_id,
        ProjectPermission.is_active == True,
    ).first()
    if not perm:
        raise ValueError("not_found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(perm, k, v)
    db.commit()
    return {"ok": True}


def revoke_project_permission(project_id: str, permission_id: str, current_user, db: Session) -> dict:
    perm = db.query(ProjectPermission).filter(
        ProjectPermission.id == permission_id,
        ProjectPermission.project_id == project_id,
        ProjectPermission.is_active == True,
    ).first()
    if not perm:
        raise ValueError("not_found")
    audit_log(db, current_user, "REVOKE_PERMISSION", "projects", project_id,
              new_values={"user_id": perm.user_id})
    perm.is_active = False
    db.commit()
    return {"ok": True, "message": "Permiso revocado correctamente"}


# ── Webhooks ──────────────────────────────────────────────────────────────────

def list_webhooks(db: Session) -> list:
    hooks = db.query(Webhook).options(joinedload(Webhook.project)).filter(
        Webhook.is_active == True
    ).order_by(Webhook.created_at.desc()).all()
    return [serialize_webhook(h) for h in hooks]


def create_webhook(payload, current_user, db: Session) -> dict:
    import json as _json
    # SSRF guard at the source: never persist a webhook pointing at an internal
    # or non-HTTPS destination. Raises ValueError → mapped to 400 by the router.
    _validate_webhook_url(payload.url)
    hook = Webhook(
        name=payload.name, url=payload.url,
        secret=encrypt_value(payload.secret) if payload.secret else None,
        events=_json.dumps(payload.events),
        project_id=payload.project_id,
        created_by=current_user.id,
    )
    db.add(hook)
    audit_log(db, current_user, "CREATE", "webhooks", hook.id, hook.name)
    db.commit()
    return serialize_webhook(hook)


def update_webhook(hook_id: str, payload, current_user, db: Session) -> dict:
    import json as _json
    hook = db.query(Webhook).filter(Webhook.id == hook_id, Webhook.is_active == True).first()
    if not hook:
        raise ValueError("not_found")
    data = payload.model_dump(exclude_unset=True)
    if data.get("url"):
        _validate_webhook_url(data["url"])
    if "events" in data:
        data["events"] = _json.dumps(data["events"])
    if "secret" in data and data["secret"]:
        data["secret"] = encrypt_value(data["secret"])
    for k, v in data.items():
        setattr(hook, k, v)
    db.commit()
    return serialize_webhook(hook)


def delete_webhook(hook_id: str, current_user, db: Session) -> dict:
    hook = db.query(Webhook).filter(Webhook.id == hook_id, Webhook.is_active == True).first()
    if not hook:
        raise ValueError("not_found")
    audit_log(db, current_user, "DELETE", "webhooks", hook.id, hook.name)
    hook.is_active = False
    db.commit()
    return {"ok": True, "message": "Webhook eliminado correctamente"}


def get_webhook_deliveries(hook_id: str, limit: int, db: Session) -> list:
    deliveries = db.query(WebhookDelivery).filter(
        WebhookDelivery.webhook_id == hook_id
    ).order_by(WebhookDelivery.created_at.desc()).limit(limit).all()
    return [{
        "id": d.id, "event": d.event, "status_code": d.status_code,
        "success": d.success, "error": d.error, "duration_ms": d.duration_ms,
        "created_at": str(d.created_at)[:19],
    } for d in deliveries]


def get_webhook_for_test(hook_id: str, db: Session):
    return db.query(Webhook).filter(Webhook.id == hook_id, Webhook.is_active == True).first()


# ── SSO ───────────────────────────────────────────────────────────────────────

def list_sso_configs(db: Session) -> list:
    return [serialize_sso(c) for c in db.query(SSOConfig).filter(SSOConfig.is_deleted == False).all()]


def create_sso_config(payload, current_user, db: Session) -> dict:
    import json as _json
    data = {k: (_json.dumps(v) if k == "role_mapping" and v else v) for k, v in payload.model_dump().items()}
    if current_user.organization_id and not data.get("organization_id"):
        data["organization_id"] = current_user.organization_id
    if data.get("oidc_client_secret"):
        data["oidc_client_secret"] = encrypt_value(data["oidc_client_secret"])
    config = SSOConfig(created_by=current_user.id, **data)
    db.add(config)
    audit_log(db, current_user, "CREATE", "sso_configs", config.id, payload.provider)
    db.commit()
    return serialize_sso(config)


def update_sso_config(config_id: str, payload, current_user, db: Session) -> dict:
    import json as _json
    config = db.query(SSOConfig).filter(SSOConfig.id == config_id, SSOConfig.is_deleted == False).first()
    if not config:
        raise ValueError("not_found")
    data = payload.model_dump(exclude_unset=True)
    if current_user.organization_id and data.get("organization_id") not in (None, current_user.organization_id):
        raise ValueError("org_mismatch")
    if "role_mapping" in data and data["role_mapping"] is not None:
        data["role_mapping"] = _json.dumps(data["role_mapping"])
    if "oidc_client_secret" in data and data["oidc_client_secret"]:
        data["oidc_client_secret"] = encrypt_value(data["oidc_client_secret"])
    for k, v in data.items():
        setattr(config, k, v)
    db.commit()
    return serialize_sso(config)


def delete_sso_config(config_id: str, db: Session) -> dict:
    config = db.query(SSOConfig).filter(SSOConfig.id == config_id, SSOConfig.is_deleted == False).first()
    if not config:
        raise ValueError("not_found")
    config.is_active = False
    config.is_deleted = True
    db.commit()
    return {"ok": True, "message": "Configuracion SSO eliminada correctamente"}


def get_sso_config_for_test(config_id: str, db: Session):
    return db.query(SSOConfig).filter(SSOConfig.id == config_id, SSOConfig.is_deleted == False).first()


# ── Notifications ─────────────────────────────────────────────────────────────

def get_my_notifications(current_user, unread_only: bool, page: int, page_size: int, db: Session) -> dict:
    q = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_active == True,
    )
    if unread_only:
        q = q.filter(Notification.is_read == False)
    total = q.count()
    unread_count = db.query(_func.count(Notification.id)).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False,
        Notification.is_active == True,
    ).scalar()
    items = q.order_by(Notification.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total, "unread_count": unread_count, "page": page,
        "notifications": [{
            "id": n.id, "type": n.type, "title": n.title, "body": n.body,
            "icon": n.icon, "color": n.color, "resource": n.resource,
            "resource_id": n.resource_id, "action_url": n.action_url,
            "is_read": n.is_read, "read_at": str(n.read_at)[:16] if n.read_at else None,
            "created_at": str(n.created_at)[:16],
        } for n in items],
    }


def mark_all_notifications_read(current_user, db: Session) -> dict:
    now = datetime.now(timezone.utc)
    db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False,
        Notification.is_active == True,
    ).update({"is_read": True, "read_at": now})
    db.commit()
    return {"ok": True}


def mark_notification_read(notif_id: str, current_user, db: Session) -> dict:
    n = db.query(Notification).filter(
        Notification.id == notif_id,
        Notification.user_id == current_user.id,
        Notification.is_active == True,
    ).first()
    if not n:
        raise ValueError("not_found")
    n.is_read = True
    n.read_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


def clear_old_notifications(current_user, days: int, db: Session) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    deleted = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_active == True,
        Notification.is_read == True,
        Notification.created_at < cutoff,
    ).update({"is_active": False}, synchronize_session=False)
    db.commit()
    return {"ok": True, "deleted": deleted, "message": "Notificaciones antiguas eliminadas correctamente"}


# ── Subcontractors ────────────────────────────────────────────────────────────

def list_subcontractors(is_active, db: Session) -> list:
    q = db.query(Subcontractor).options(
        joinedload(Subcontractor.rates),
        joinedload(Subcontractor.assignments),
        joinedload(Subcontractor.workers),
    )
    if is_active is not None:
        q = q.filter(Subcontractor.is_active == is_active)
    return [serialize_subcontractor(s) for s in q.order_by(Subcontractor.name).all()]


def create_subcontractor(payload, current_user, db: Session) -> dict:
    sub = Subcontractor(code=next_sub_code(db), **payload.model_dump())
    db.add(sub)
    audit_log(db, current_user, "CREATE", "subcontractors", sub.id, sub.name)
    db.commit()
    db.refresh(sub)
    return serialize_subcontractor(sub)


def update_subcontractor(sub_id: str, payload, db: Session) -> dict:
    sub = db.query(Subcontractor).filter(Subcontractor.id == sub_id, Subcontractor.is_active == True).first()
    if not sub:
        raise ValueError("not_found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(sub, k, v)
    db.commit()
    sub = db.query(Subcontractor).options(
        joinedload(Subcontractor.rates),
        joinedload(Subcontractor.assignments),
        joinedload(Subcontractor.workers),
    ).filter(Subcontractor.id == sub_id).first()
    return serialize_subcontractor(sub)


def delete_subcontractor(sub_id: str, db: Session) -> dict:
    sub = db.query(Subcontractor).filter(Subcontractor.id == sub_id, Subcontractor.is_active == True).first()
    if not sub:
        raise ValueError("not_found")
    dependencies = []
    assignment_count = db.query(_func.count(SubcontractorAssignment.id)).filter(
        SubcontractorAssignment.subcontractor_id == sub_id
    ).scalar() or 0
    if assignment_count > 0:
        dependencies.append(f"{assignment_count} asignaciones")

    worker_count = db.query(_func.count(SubcontractorWorker.id)).filter(
        SubcontractorWorker.subcontractor_id == sub_id,
        SubcontractorWorker.is_active == True,
    ).scalar() or 0
    if worker_count > 0:
        dependencies.append(f"{worker_count} trabajadores activos")

    timelog_count = db.query(_func.count(SubcontractorTimeLog.id)).filter(
        SubcontractorTimeLog.subcontractor_id == sub_id,
        SubcontractorTimeLog.is_active == True,
    ).scalar() or 0
    if timelog_count > 0:
        dependencies.append(f"{timelog_count} partes de horas")

    if dependencies:
        raise ValueError(f"has_dependencies:{', '.join(dependencies)}")

    sub.is_active = False
    db.query(SubcontractorRate).filter(
        SubcontractorRate.subcontractor_id == sub_id,
        SubcontractorRate.is_active == True,
    ).update({"is_active": False}, synchronize_session=False)
    db.query(SubcontractorWorker).filter(
        SubcontractorWorker.subcontractor_id == sub_id,
        SubcontractorWorker.is_active == True,
    ).update({"is_active": False}, synchronize_session=False)
    db.commit()
    return {"ok": True, "message": "Subcontratista eliminado correctamente"}


def add_subcontractor_rate(sub_id: str, payload, db: Session) -> dict:
    sub = db.query(Subcontractor).filter(Subcontractor.id == sub_id, Subcontractor.is_active == True).first()
    if not sub:
        raise ValueError("not_found")
    rate = SubcontractorRate(subcontractor_id=sub_id, **payload.model_dump())
    db.add(rate)
    db.commit()
    return {"id": rate.id, "description": rate.description, "cost_rate": rate.cost_rate, "sell_rate": rate.sell_rate}


def delete_subcontractor_rate(sub_id: str, rate_id: str, db: Session) -> dict:
    rate = db.query(SubcontractorRate).filter(
        SubcontractorRate.id == rate_id,
        SubcontractorRate.subcontractor_id == sub_id,
        SubcontractorRate.is_active == True,
    ).first()
    if not rate:
        raise ValueError("not_found")
    assignments_using_rate = db.query(_func.count(SubcontractorAssignment.id)).filter(
        SubcontractorAssignment.rate_id == rate_id
    ).scalar() or 0
    if assignments_using_rate > 0:
        raise ValueError("has_dependencies")
    rate.is_active = False
    db.commit()
    return {"ok": True, "message": "Tarifa eliminada correctamente"}


def get_subcontractor_assignments(sub_id: str, db: Session) -> list:
    assignments = db.query(SubcontractorAssignment).options(
        joinedload(SubcontractorAssignment.project),
        joinedload(SubcontractorAssignment.rate),
    ).filter(SubcontractorAssignment.subcontractor_id == sub_id).all()
    return [{
        "id": a.id, "project_id": a.project_id,
        "project_name": a.project.name if a.project else None,
        "project_code": a.project.code if a.project else None,
        "rate": {"description": a.rate.description, "cost_rate": a.rate.cost_rate} if a.rate else None,
        "po_number": a.po_number, "po_amount": a.po_amount,
        "hours_contracted": a.hours_contracted, "hours_logged": a.hours_logged,
        "budget_used_pct": round((a.hours_logged / a.hours_contracted) * 100, 1) if a.hours_contracted else None,
        "start_date": str(a.start_date) if a.start_date else None,
        "end_date": str(a.end_date) if a.end_date else None,
        "notes": a.notes,
    } for a in assignments]


def create_subcontractor_assignment(sub_id: str, payload, current_user, db: Session) -> dict:
    sub = db.query(Subcontractor).filter(Subcontractor.id == sub_id, Subcontractor.is_active == True).first()
    if not sub:
        raise ValueError("not_found")
    assignment = SubcontractorAssignment(subcontractor_id=sub_id, **payload.model_dump())
    db.add(assignment)
    audit_log(db, current_user, "CREATE", "subcontractor_assignments", assignment.id, sub.name)
    db.commit()
    return {"ok": True, "id": assignment.id}


# ── Subcontractor Workers ─────────────────────────────────────────────────────

def list_all_workers(skill_id, is_active, db: Session) -> list:
    q = db.query(SubcontractorWorker).options(
        joinedload(SubcontractorWorker.skills).joinedload(SubcontractorWorkerSkill.skill),
        joinedload(SubcontractorWorker.assignments),
        joinedload(SubcontractorWorker.subcontractor),
        joinedload(SubcontractorWorker.user),
    )
    if is_active is not None:
        q = q.filter(SubcontractorWorker.is_active == is_active)
    if skill_id:
        q = q.join(SubcontractorWorkerSkill, SubcontractorWorker.id == SubcontractorWorkerSkill.worker_id).filter(
            SubcontractorWorkerSkill.skill_id == skill_id,
            SubcontractorWorkerSkill.is_active == True,
        )
    result = []
    for w in q.order_by(SubcontractorWorker.name).all():
        d = serialize_worker(w)
        d["company_name"] = w.subcontractor.name if w.subcontractor else None
        d["company_code"] = w.subcontractor.code if w.subcontractor else None
        result.append(d)
    return result


def get_workers_for_subcontractor(sub_id: str, db: Session) -> list:
    sub = db.query(Subcontractor).filter(Subcontractor.id == sub_id, Subcontractor.is_active == True).first()
    if not sub:
        raise ValueError("not_found")
    workers = db.query(SubcontractorWorker).options(
        joinedload(SubcontractorWorker.skills).joinedload(SubcontractorWorkerSkill.skill),
        joinedload(SubcontractorWorker.assignments),
        joinedload(SubcontractorWorker.user),
    ).filter(
        SubcontractorWorker.subcontractor_id == sub_id,
        SubcontractorWorker.is_active == True,
    ).order_by(SubcontractorWorker.name).all()
    return [serialize_worker(w) for w in workers]


def update_worker(worker_id: str, payload, db: Session) -> dict:
    worker = db.query(SubcontractorWorker).options(
        joinedload(SubcontractorWorker.skills).joinedload(SubcontractorWorkerSkill.skill),
        joinedload(SubcontractorWorker.assignments),
        joinedload(SubcontractorWorker.user),
    ).filter(SubcontractorWorker.id == worker_id, SubcontractorWorker.is_active == True).first()
    if not worker:
        raise ValueError("not_found")
    update_data = payload.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(worker, k, v)
    if worker.user_id:
        linked_user = db.query(User).filter(User.id == worker.user_id).first()
        if linked_user:
            if "name" in update_data:
                linked_user.full_name = update_data["name"]
                parts = update_data["name"].strip().split(" ", 1)
                linked_user.first_name = parts[0]
                linked_user.last_name = parts[1] if len(parts) > 1 else None
            if "role" in update_data: linked_user.job_title = update_data["role"]
            if "phone" in update_data: linked_user.phone = update_data["phone"]
            if "cost_rate" in update_data: linked_user.hourly_rate = update_data["cost_rate"]
            if "currency" in update_data: linked_user.currency = update_data["currency"]
            if "weekly_capacity_hours" in update_data and update_data["weekly_capacity_hours"] is not None:
                linked_user.weekly_capacity_hours = update_data["weekly_capacity_hours"]
            if "is_active" in update_data: linked_user.is_active = update_data["is_active"]
            if "email" in update_data and update_data["email"]:
                conflict = db.query(User).filter(User.email == update_data["email"], User.id != linked_user.id).first()
                if not conflict:
                    linked_user.email = update_data["email"]
    db.commit()
    db.refresh(worker)
    return serialize_worker(worker)


def delete_worker(worker_id: str, db: Session) -> dict:
    worker = db.query(SubcontractorWorker).filter(
        SubcontractorWorker.id == worker_id,
        SubcontractorWorker.is_active == True,
    ).first()
    if not worker:
        raise ValueError("not_found")
    assignment_count = db.query(_func.count(SubcontractorAssignment.id)).filter(
        SubcontractorAssignment.worker_id == worker_id
    ).scalar() or 0
    if assignment_count > 0:
        raise ValueError("has_dependencies")
    worker.is_active = False
    if worker.user_id:
        linked_user = db.query(User).filter(User.id == worker.user_id).first()
        if linked_user:
            linked_user.is_active = False
    db.commit()
    return {"ok": True, "message": "Trabajador eliminado correctamente"}


def add_worker_skill(worker_id: str, payload, db: Session) -> dict:
    worker = db.query(SubcontractorWorker).filter(
        SubcontractorWorker.id == worker_id,
        SubcontractorWorker.is_active == True,
    ).first()
    if not worker:
        raise ValueError("not_found")
    existing = db.query(SubcontractorWorkerSkill).filter(
        SubcontractorWorkerSkill.worker_id == worker_id,
        SubcontractorWorkerSkill.skill_id == payload.skill_id,
        SubcontractorWorkerSkill.is_active == True,
    ).first()
    if existing:
        for k, v in payload.model_dump(exclude_unset=True).items():
            setattr(existing, k, v)
        db.commit()
        return {"ok": True, "id": existing.id, "updated": True}
    ws = SubcontractorWorkerSkill(worker_id=worker_id, **payload.model_dump())
    db.add(ws)
    db.commit()
    return {"ok": True, "id": ws.id, "updated": False}


def remove_worker_skill(worker_id: str, skill_id: str, db: Session) -> dict:
    ws = db.query(SubcontractorWorkerSkill).filter(
        SubcontractorWorkerSkill.worker_id == worker_id,
        SubcontractorWorkerSkill.skill_id == skill_id,
        SubcontractorWorkerSkill.is_active == True,
    ).first()
    if not ws:
        raise ValueError("not_found")
    ws.is_active = False
    db.commit()
    return {"ok": True, "message": "Skill eliminada correctamente"}


# ── Subcontractor Time Logs ───────────────────────────────────────────────────

def get_timelogs(sub_id: str, project_id, db: Session) -> list:
    q = db.query(SubcontractorTimeLog).filter(
        SubcontractorTimeLog.subcontractor_id == sub_id,
        SubcontractorTimeLog.is_active == True,
    )
    if project_id:
        q = q.filter(SubcontractorTimeLog.project_id == project_id)
    return [{
        "id": l.id, "log_date": str(l.log_date), "hours": l.hours,
        "description": l.description, "task_reference": l.task_reference,
        "cost_amount": l.cost_amount, "is_invoiced": l.is_invoiced,
        "project_id": l.project_id,
        "project_name": l.project.name if l.project else None,
    } for l in q.order_by(SubcontractorTimeLog.log_date.desc()).all()]


def create_timelog(sub_id: str, payload: dict, db: Session) -> dict:
    import uuid as _uuid
    sub = db.query(Subcontractor).filter(Subcontractor.id == sub_id, Subcontractor.is_active == True).first()
    if not sub:
        raise ValueError("not_found")
    cost_amount = payload.get("cost_amount")
    assignment_id = payload.get("assignment_id")
    if not cost_amount and assignment_id:
        assignment = db.query(SubcontractorAssignment).filter(SubcontractorAssignment.id == assignment_id).first()
        if assignment and assignment.rate:
            cost_amount = round(float(payload.get("hours", 0)) * assignment.rate.cost_rate, 2)
    log = SubcontractorTimeLog(
        id=str(_uuid.uuid4()), subcontractor_id=sub_id,
        assignment_id=assignment_id, project_id=payload.get("project_id"),
        log_date=payload.get("log_date"), hours=float(payload.get("hours", 0)),
        description=payload.get("description"), task_reference=payload.get("task_reference"),
        cost_amount=cost_amount,
    )
    db.add(log)
    if assignment_id:
        assignment = db.query(SubcontractorAssignment).filter(SubcontractorAssignment.id == assignment_id).first()
        if assignment:
            assignment.hours_logged = (assignment.hours_logged or 0) + float(payload.get("hours", 0))
    db.commit()
    return {"ok": True, "id": log.id, "cost_amount": cost_amount}


def delete_timelog(sub_id: str, log_id: str, db: Session) -> dict:
    log = db.query(SubcontractorTimeLog).filter(
        SubcontractorTimeLog.id == log_id,
        SubcontractorTimeLog.subcontractor_id == sub_id,
        SubcontractorTimeLog.is_active == True,
    ).first()
    if not log:
        raise ValueError("not_found")
    if log.is_invoiced:
        raise ValueError("already_invoiced")
    log.is_active = False
    db.commit()
    return {"ok": True, "message": "Parte de horas eliminado correctamente"}


# ── Subcontractor Invoices ────────────────────────────────────────────────────

def get_sub_invoices(sub_id: str, db: Session) -> list:
    invs = db.query(SubcontractorInvoice).filter(
        SubcontractorInvoice.subcontractor_id == sub_id
    ).order_by(SubcontractorInvoice.issue_date.desc()).all()
    return [{
        "id": i.id, "invoice_number": i.invoice_number,
        "issue_date": str(i.issue_date), "due_date": str(i.due_date) if i.due_date else None,
        "amount": i.amount, "tax_pct": i.tax_pct, "total": i.total,
        "currency": i.currency, "status": i.status,
        "paid_date": str(i.paid_date) if i.paid_date else None,
        "description": i.description,
    } for i in invs]


def create_sub_invoice(sub_id: str, payload: dict, current_user, db: Session) -> dict:
    import uuid as _uuid
    sub = db.query(Subcontractor).filter(Subcontractor.id == sub_id, Subcontractor.is_active == True).first()
    if not sub:
        raise ValueError("not_found")
    amount = float(payload.get("amount", 0))
    tax_pct = float(payload.get("tax_pct", settings.DEFAULT_TAX_RATE))
    total = round(amount * (1 + tax_pct / 100), 2)
    inv = SubcontractorInvoice(
        id=str(_uuid.uuid4()), subcontractor_id=sub_id,
        assignment_id=payload.get("assignment_id"),
        invoice_number=payload.get("invoice_number", f"SUB-INV-{_uuid.uuid4().hex[:6].upper()}"),
        issue_date=payload.get("issue_date"), due_date=payload.get("due_date"),
        amount=amount, tax_pct=tax_pct, total=total,
        currency=payload.get("currency", sub.currency or settings.DEFAULT_CURRENCY),
        description=payload.get("description"),
    )
    db.add(inv)
    if payload.get("timelog_ids"):
        db.query(SubcontractorTimeLog).filter(
            SubcontractorTimeLog.id.in_(payload["timelog_ids"]),
            SubcontractorTimeLog.subcontractor_id == sub_id,
            SubcontractorTimeLog.is_active == True,
        ).update({"is_invoiced": True, "invoice_id": inv.id}, synchronize_session=False)
    db.commit()
    audit_log(db, current_user, "CREATE", "subcontractor_invoices", inv.id, sub.name)
    return {"ok": True, "id": inv.id, "total": total}


def update_sub_invoice(sub_id: str, inv_id: str, payload: dict, db: Session) -> dict:
    inv = db.query(SubcontractorInvoice).filter(
        SubcontractorInvoice.id == inv_id, SubcontractorInvoice.subcontractor_id == sub_id
    ).first()
    if not inv:
        raise ValueError("not_found")
    for k in ["status", "paid_date", "description"]:
        if k in payload:
            setattr(inv, k, payload[k])
    db.commit()
    return {"ok": True}


# ── Subcontractor Dashboard ───────────────────────────────────────────────────

def get_subcontractors_dashboard(db: Session) -> dict:
    total_subs   = db.query(func.count(Subcontractor.id)).filter(Subcontractor.is_active == True).scalar()
    active_assgn = db.query(func.count(SubcontractorAssignment.id)).scalar()
    pending_invs = db.query(func.count(SubcontractorInvoice.id)).filter(SubcontractorInvoice.status == "received").scalar()
    total_cost   = db.query(func.sum(SubcontractorInvoice.total)).filter(SubcontractorInvoice.status.in_(["approved", "paid"])).scalar() or 0
    pending_cost = db.query(func.sum(SubcontractorInvoice.total)).filter(SubcontractorInvoice.status == "received").scalar() or 0
    total_hours  = db.query(func.sum(SubcontractorTimeLog.hours)).filter(SubcontractorTimeLog.is_active == True).scalar() or 0
    return {
        "total_active_subs": total_subs, "active_assignments": active_assgn,
        "pending_invoices": pending_invs, "total_paid_cost": round(total_cost, 2),
        "pending_approval_cost": round(pending_cost, 2), "total_hours_logged": round(total_hours, 1),
    }


# ── Revenue Forecast ──────────────────────────────────────────────────────────

def get_project_forecast(project_id: str, year: int, db: Session) -> dict:
    forecasts = db.query(RevenueForecast).filter(
        RevenueForecast.project_id == project_id, RevenueForecast.year == year
    ).order_by(RevenueForecast.month).all()
    existing = {f.month: f for f in forecasts}
    result = []
    for month in range(1, 13):
        if month in existing:
            result.append(serialize_forecast(existing[month]))
        else:
            result.append({
                "id": None, "project_id": project_id, "year": year, "month": month,
                "revenue_planned": 0, "revenue_actual": 0, "revenue_forecast": 0,
                "cost_planned": 0, "cost_actual": 0, "hours_planned": 0, "hours_actual": 0,
                "margin_pct": None, "notes": None,
            })
    return {"year": year, "project_id": project_id, "monthly": result}


def upsert_forecast(project_id: str, year: int, month: int, payload, db: Session) -> dict:
    existing = db.query(RevenueForecast).filter(
        RevenueForecast.project_id == project_id,
        RevenueForecast.year == year,
        RevenueForecast.month == month,
    ).first()
    if existing:
        for k, v in payload.model_dump(exclude_unset=True).items():
            setattr(existing, k, v)
        rev = existing.revenue_forecast or existing.revenue_planned or 0
        cost = existing.cost_actual or existing.cost_planned or 0
        existing.margin_pct = round((rev - cost) / rev * 100, 1) if rev > 0 else None
        db.commit()
        return serialize_forecast(existing)
    else:
        data = payload.model_dump()
        rev = data.get("revenue_forecast") or data.get("revenue_planned") or 0
        cost = data.get("cost_actual") or data.get("cost_planned") or 0
        margin = round((rev - cost) / rev * 100, 1) if rev > 0 else None
        forecast = RevenueForecast(project_id=project_id, year=year, month=month, margin_pct=margin, **data)
        db.add(forecast)
        db.commit()
        db.refresh(forecast)
        return serialize_forecast(forecast)
