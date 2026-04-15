"""
Enterprise endpoint — covers all enterprise-grade features:
  GET/POST /enterprise/audit-log
  GET/POST/PATCH/DELETE /enterprise/project-permissions/{project_id}
  GET/POST/PATCH/DELETE /enterprise/webhooks
  POST /enterprise/webhooks/{id}/test
  GET/POST/PATCH /enterprise/sso
  GET /enterprise/notifications  (my notifications)
  POST /enterprise/notifications/read-all
  GET/POST/PATCH/DELETE /enterprise/subcontractors
  GET/POST /enterprise/subcontractors/{id}/assignments
  GET/POST /enterprise/revenue-forecast/{project_id}
  GET /enterprise/revenue-forecast/portfolio
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from typing import Optional, List
from datetime import date, datetime, timedelta, timezone
from pydantic import BaseModel, field_validator
import json

from app.db.session import get_db
from app.core.config import settings
from app.core.encryption import encrypt_value
from app.core.deps import get_current_user, require_any_manager, require_admin
from app.models.user import User
from app.models.project import Project
from app.models.enterprise import (
    AuditLog, ProjectPermission, Webhook, WebhookDelivery, WebhookEvent,
    SSOConfig, Notification,
    Subcontractor, SubcontractorRate, SubcontractorAssignment,
    SubcontractorWorker, SubcontractorWorkerSkill,
    RevenueForecast,
)
from app.services.audit import audit_log
from app.services.notifications import notify_user
import app.services.enterprise_service as _svc

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════════
# AUDIT LOG
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/audit-log", summary="Registro de auditoría global")
def get_audit_log(
    resource: Optional[str] = None,
    resource_id: Optional[str] = None,
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    q = db.query(AuditLog)
    if resource:   q = q.filter(AuditLog.resource == resource)
    if resource_id: q = q.filter(AuditLog.resource_id == resource_id)
    if user_id:    q = q.filter(AuditLog.user_id == user_id)
    if action:     q = q.filter(AuditLog.action == action.upper())
    if date_from:  q = q.filter(AuditLog.created_at >= date_from)
    if date_to:    q = q.filter(AuditLog.created_at <= datetime.combine(date_to, datetime.max.time()))

    total = q.count()
    logs = q.order_by(AuditLog.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()

    return {
        "total": total, "page": page, "pages": -(-total // page_size),
        "logs": [{
            "id": l.id, "user_name": l.user_name, "ip_address": l.ip_address,
            "action": l.action, "resource": l.resource,
            "resource_id": l.resource_id, "resource_name": l.resource_name,
            "old_values": json.loads(l.old_values) if l.old_values else None,
            "new_values": json.loads(l.new_values) if l.new_values else None,
            "created_at": str(l.created_at)[:19],
        } for l in logs]
    }


@router.get("/audit-log/stats", summary="Estadísticas del audit log")
def audit_stats(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return _svc.compute_audit_stats(db, days)


# ═══════════════════════════════════════════════════════════════════════════════
# PROJECT PERMISSIONS
# ═══════════════════════════════════════════════════════════════════════════════

class PermissionCreate(BaseModel):
    user_id: str
    level: str = "member"
    can_see_financials: bool = False
    can_see_rates: bool = False
    can_export: bool = True
    expires_at: Optional[datetime] = None
    note: Optional[str] = None

class PermissionUpdate(BaseModel):
    level: Optional[str] = None
    can_see_financials: Optional[bool] = None
    can_see_rates: Optional[bool] = None
    can_export: Optional[bool] = None
    expires_at: Optional[datetime] = None
    note: Optional[str] = None


@router.get("/project-permissions/{project_id}", summary="Permisos de un proyecto")
def get_project_permissions(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    perms = db.query(ProjectPermission).options(
        joinedload(ProjectPermission.user)
    ).filter(ProjectPermission.project_id == project_id).all()

    return [{
        "id": p.id,
        "user_id": p.user_id,
        "user_name": p.user.full_name if p.user else None,
        "user_email": p.user.email if p.user else None,
        "user_role": p.user.role if p.user else None,
        "level": p.level,
        "can_see_financials": p.can_see_financials,
        "can_see_rates": p.can_see_rates,
        "can_export": p.can_export,
        "granted_by": p.granted_by,
        "granted_at": str(p.granted_at)[:10] if p.granted_at else None,
        "expires_at": str(p.expires_at)[:10] if p.expires_at else None,
        "note": p.note,
    } for p in perms]


@router.post("/project-permissions/{project_id}", summary="Conceder acceso a proyecto")
def grant_project_permission(
    project_id: str,
    payload: PermissionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    # Check project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project: raise HTTPException(404, "Proyecto no encontrado")

    # Upsert permission
    existing = db.query(ProjectPermission).filter(
        ProjectPermission.project_id == project_id,
        ProjectPermission.user_id == payload.user_id,
    ).first()

    if existing:
        for k, v in payload.model_dump(exclude_unset=True).items():
            setattr(existing, k, v)
        perm = existing
    else:
        perm = ProjectPermission(
            project_id=project_id,
            granted_by=current_user.id,
            **payload.model_dump(),
        )
        db.add(perm)

    audit_log(db, current_user, "GRANT_PERMISSION", "projects", project_id, project.name,
              new_values={"user_id": payload.user_id, "level": payload.level})
    db.commit()

    # Notify the user
    user = db.query(User).filter(User.id == payload.user_id).first()
    if user:
        notify_user(db, user.id, "system",
                   f"Acceso concedido al proyecto {project.name}",
                   f"{current_user.full_name} te ha dado acceso como {payload.level}",
                   resource="projects", resource_id=project_id,
                   action_url="/projects")
        db.commit()

    return {"ok": True}


@router.patch("/project-permissions/{project_id}/{permission_id}", summary="Actualizar permiso")
def update_project_permission(
    project_id: str,
    permission_id: str,
    payload: PermissionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    perm = db.query(ProjectPermission).filter(
        ProjectPermission.id == permission_id,
        ProjectPermission.project_id == project_id,
    ).first()
    if not perm: raise HTTPException(404)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(perm, k, v)
    db.commit()
    return {"ok": True}


@router.delete("/project-permissions/{project_id}/{permission_id}", summary="Revocar acceso")
def revoke_project_permission(
    project_id: str,
    permission_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    perm = db.query(ProjectPermission).filter(
        ProjectPermission.id == permission_id,
        ProjectPermission.project_id == project_id,
    ).first()
    if not perm: raise HTTPException(404)
    audit_log(db, current_user, "REVOKE_PERMISSION", "projects", project_id,
              new_values={"user_id": perm.user_id})
    db.delete(perm)
    db.commit()
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# WEBHOOKS
# ═══════════════════════════════════════════════════════════════════════════════

class WebhookCreate(BaseModel):
    name: str
    url: str
    secret: Optional[str] = None
    events: List[str]
    project_id: Optional[str] = None

class WebhookUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    secret: Optional[str] = None
    events: Optional[List[str]] = None
    is_active: Optional[bool] = None


_hook_out = _svc.serialize_webhook


@router.get("/webhooks", summary="Listar webhooks")
def list_webhooks(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    hooks = db.query(Webhook).options(joinedload(Webhook.project)).order_by(Webhook.created_at.desc()).all()
    return [_hook_out(h) for h in hooks]


@router.get("/webhooks/events", summary="Lista de eventos disponibles")
def list_webhook_events(current_user: User = Depends(get_current_user)):
    return [{"value": e.value, "label": e.value.replace(".", " › ").replace("_", " ").title()} for e in WebhookEvent]


@router.post("/webhooks", summary="Crear webhook")
def create_webhook(
    payload: WebhookCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    hook = Webhook(
        name=payload.name,
        url=payload.url,
        secret=encrypt_value(payload.secret) if payload.secret else None,
        events=json.dumps(payload.events),
        project_id=payload.project_id,
        created_by=current_user.id,
    )
    db.add(hook)
    audit_log(db, current_user, "CREATE", "webhooks", hook.id, hook.name)
    db.commit()
    return _hook_out(hook)


@router.patch("/webhooks/{hook_id}", summary="Actualizar webhook")
def update_webhook(
    hook_id: str,
    payload: WebhookUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    hook = db.query(Webhook).filter(Webhook.id == hook_id).first()
    if not hook: raise HTTPException(404)
    data = payload.model_dump(exclude_unset=True)
    if "events" in data:
        data["events"] = json.dumps(data["events"])
    if "secret" in data and data["secret"]:
        data["secret"] = encrypt_value(data["secret"])
    for k, v in data.items():
        setattr(hook, k, v)
    db.commit()
    return _hook_out(hook)


@router.delete("/webhooks/{hook_id}", summary="Eliminar webhook")
def delete_webhook(
    hook_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    hook = db.query(Webhook).filter(Webhook.id == hook_id).first()
    if not hook: raise HTTPException(404)
    audit_log(db, current_user, "DELETE", "webhooks", hook.id, hook.name)
    db.delete(hook); db.commit()
    return {"ok": True}


@router.post("/webhooks/{hook_id}/test", summary="Enviar payload de prueba")
def test_webhook(
    hook_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    hook = db.query(Webhook).filter(Webhook.id == hook_id).first()
    if not hook: raise HTTPException(404)
    return _svc.test_webhook_delivery(hook, current_user)


@router.get("/webhooks/{hook_id}/deliveries", summary="Historial de entregas")
def get_deliveries(
    hook_id: str,
    limit: int = Query(20, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    deliveries = db.query(WebhookDelivery).filter(
        WebhookDelivery.webhook_id == hook_id
    ).order_by(WebhookDelivery.created_at.desc()).limit(limit).all()
    return [{
        "id": d.id, "event": d.event,
        "status_code": d.status_code, "success": d.success,
        "error": d.error, "duration_ms": d.duration_ms,
        "created_at": str(d.created_at)[:19],
    } for d in deliveries]


# ═══════════════════════════════════════════════════════════════════════════════
# SSO CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

class SSOCreate(BaseModel):
    provider: str
    organization_id: Optional[str] = None
    saml_entity_id: Optional[str] = None
    saml_sso_url: Optional[str] = None
    saml_slo_url: Optional[str] = None
    saml_certificate: Optional[str] = None
    saml_attribute_email: str = "email"
    saml_attribute_name: str = "displayName"
    saml_attribute_role: Optional[str] = None
    oidc_client_id: Optional[str] = None
    oidc_client_secret: Optional[str] = None
    oidc_discovery_url: Optional[str] = None
    oidc_scopes: str = "openid email profile"
    role_mapping: Optional[dict] = None
    auto_create_users: bool = True
    default_role: str = "employee"
    allowed_domains: Optional[str] = None

    @field_validator("oidc_discovery_url", "saml_sso_url", "saml_slo_url", mode="before")
    @classmethod
    def _require_https(cls, v: Optional[str]) -> Optional[str]:
        """Reject non-HTTPS URLs to prevent SSRF via internal network requests."""
        if v and not v.startswith("https://"):
            raise ValueError("Solo se permiten URLs HTTPS para configuraciones SSO/OIDC")
        return v

class SSOUpdate(SSOCreate):
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None


_sso_out = _svc.serialize_sso


@router.get("/sso", summary="Configuraciones SSO")
def list_sso(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    configs = db.query(SSOConfig).all()
    return [_sso_out(c) for c in configs]


@router.post("/sso", summary="Crear configuración SSO")
def create_sso(
    payload: SSOCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    data = {
        k: (json.dumps(v) if k == "role_mapping" and v else v)
        for k, v in payload.model_dump().items()
    }
    if current_user.organization_id and not data.get("organization_id"):
        data["organization_id"] = current_user.organization_id
    if data.get("oidc_client_secret"):
        data["oidc_client_secret"] = encrypt_value(data["oidc_client_secret"])
    config = SSOConfig(created_by=current_user.id, **data)
    db.add(config)
    audit_log(db, current_user, "CREATE", "sso_configs", config.id, payload.provider)
    db.commit()
    return _sso_out(config)


@router.patch("/sso/{config_id}", summary="Actualizar SSO")
def update_sso(
    config_id: str,
    payload: SSOUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    config = db.query(SSOConfig).filter(SSOConfig.id == config_id).first()
    if not config: raise HTTPException(404)
    data = payload.model_dump(exclude_unset=True)
    if current_user.organization_id and data.get("organization_id") not in (None, current_user.organization_id):
        raise HTTPException(403, "No puedes mover la configuración SSO a otra organización")
    if "role_mapping" in data and data["role_mapping"] is not None:
        data["role_mapping"] = json.dumps(data["role_mapping"])
    if "oidc_client_secret" in data and data["oidc_client_secret"]:
        data["oidc_client_secret"] = encrypt_value(data["oidc_client_secret"])
    for k, v in data.items():
        setattr(config, k, v)
    db.commit()
    return _sso_out(config)


@router.delete("/sso/{config_id}", summary="Eliminar SSO")
def delete_sso(
    config_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    config = db.query(SSOConfig).filter(SSOConfig.id == config_id).first()
    if not config: raise HTTPException(404)
    db.delete(config); db.commit()
    return {"ok": True}


@router.post("/sso/{config_id}/test", summary="Validar configuración SSO")
def test_sso(
    config_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    config = db.query(SSOConfig).filter(SSOConfig.id == config_id).first()
    if not config: raise HTTPException(404)
    return _svc.validate_sso_config(config)


# ═══════════════════════════════════════════════════════════════════════════════
# NOTIFICATIONS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/notifications", summary="Mis notificaciones")
def my_notifications(
    unread_only: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Notification).filter(Notification.user_id == current_user.id)
    if unread_only:
        q = q.filter(Notification.is_read == False)
    total = q.count()
    unread_count = db.query(func.count(Notification.id)).filter(
        Notification.user_id == current_user.id, Notification.is_read == False
    ).scalar()
    items = q.order_by(Notification.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    return {
        "total": total,
        "unread_count": unread_count,
        "page": page,
        "notifications": [{
            "id": n.id, "type": n.type, "title": n.title, "body": n.body,
            "icon": n.icon, "color": n.color,
            "resource": n.resource, "resource_id": n.resource_id,
            "action_url": n.action_url,
            "is_read": n.is_read, "read_at": str(n.read_at)[:16] if n.read_at else None,
            "created_at": str(n.created_at)[:16],
        } for n in items]
    }


@router.post("/notifications/read-all", summary="Marcar todas como leídas")
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    db.query(Notification).filter(
        Notification.user_id == current_user.id, Notification.is_read == False
    ).update({"is_read": True, "read_at": now})
    db.commit()
    return {"ok": True}


@router.post("/notifications/{notif_id}/read", summary="Marcar como leída")
def mark_read(
    notif_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    n = db.query(Notification).filter(
        Notification.id == notif_id, Notification.user_id == current_user.id
    ).first()
    if not n: raise HTTPException(404)
    n.is_read = True
    n.read_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


@router.delete("/notifications/clear-old", summary="Limpiar notificaciones antiguas")
def clear_old_notifications(
    days: int = Query(90, ge=30),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    deleted = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == True,
        Notification.created_at < cutoff,
    ).delete()
    db.commit()
    return {"deleted": deleted}


# ═══════════════════════════════════════════════════════════════════════════════
# SUBCONTRACTORS
# ═══════════════════════════════════════════════════════════════════════════════

class SubCreate(BaseModel):
    name: str
    company: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    country: Optional[str] = None
    vat_number: Optional[str] = None
    currency: str = settings.DEFAULT_CURRENCY
    notes: Optional[str] = None

class SubUpdate(SubCreate):
    is_active: Optional[bool] = None
    name: Optional[str] = None

class RateCreate(BaseModel):
    description: str
    cost_rate: float
    sell_rate: Optional[float] = None
    currency: str = settings.DEFAULT_CURRENCY
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None

class AssignmentCreate(BaseModel):
    project_id: str
    worker_id: Optional[str] = None
    rate_id: Optional[str] = None
    po_number: Optional[str] = None
    po_amount: Optional[float] = None
    hours_contracted: Optional[float] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    notes: Optional[str] = None


_sub_out = _svc.serialize_subcontractor


def _next_sub_code(db: Session) -> str:
    return _svc.next_sub_code(db)


@router.get("/subcontractors", summary="Listar subcontratistas")
def list_subcontractors(
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    q = db.query(Subcontractor).options(
        joinedload(Subcontractor.rates),
        joinedload(Subcontractor.assignments),
        joinedload(Subcontractor.workers),
    )
    if is_active is not None: q = q.filter(Subcontractor.is_active == is_active)
    return [_sub_out(s) for s in q.order_by(Subcontractor.name).all()]


@router.post("/subcontractors", summary="Crear subcontratista")
def create_subcontractor(
    payload: SubCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    sub = Subcontractor(code=_next_sub_code(db), **payload.model_dump())
    db.add(sub)
    audit_log(db, current_user, "CREATE", "subcontractors", sub.id, sub.name)
    db.commit()
    db.refresh(sub)
    return _sub_out(sub)


@router.patch("/subcontractors/{sub_id}", summary="Actualizar subcontratista")
def update_subcontractor(
    sub_id: str,
    payload: SubUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    sub = db.query(Subcontractor).filter(Subcontractor.id == sub_id).first()
    if not sub: raise HTTPException(404)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(sub, k, v)
    db.commit()
    sub = db.query(Subcontractor).options(joinedload(Subcontractor.rates), joinedload(Subcontractor.assignments), joinedload(Subcontractor.workers)).filter(Subcontractor.id == sub_id).first()
    return _sub_out(sub)


@router.delete("/subcontractors/{sub_id}", summary="Eliminar subcontratista (soft delete)")
def delete_subcontractor(
    sub_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    sub = db.query(Subcontractor).filter(Subcontractor.id == sub_id).first()
    if not sub: raise HTTPException(404, "Subcontratista no encontrado")
    sub.is_active = False
    db.commit()
    return {"ok": True}


@router.post("/subcontractors/{sub_id}/rates", summary="Añadir tarifa")
def add_rate(
    sub_id: str,
    payload: RateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    sub = db.query(Subcontractor).filter(Subcontractor.id == sub_id).first()
    if not sub: raise HTTPException(404)
    rate = SubcontractorRate(subcontractor_id=sub_id, **payload.model_dump())
    db.add(rate); db.commit()
    return {"id": rate.id, "description": rate.description, "cost_rate": rate.cost_rate, "sell_rate": rate.sell_rate}


@router.delete("/subcontractors/{sub_id}/rates/{rate_id}", summary="Eliminar tarifa")
def delete_rate(
    sub_id: str, rate_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    rate = db.query(SubcontractorRate).filter(
        SubcontractorRate.id == rate_id, SubcontractorRate.subcontractor_id == sub_id
    ).first()
    if not rate: raise HTTPException(404)
    db.delete(rate); db.commit()
    return {"ok": True}


@router.get("/subcontractors/{sub_id}/assignments", summary="Asignaciones del subcontratista")
def get_assignments(
    sub_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    assignments = db.query(SubcontractorAssignment).options(
        joinedload(SubcontractorAssignment.project),
        joinedload(SubcontractorAssignment.rate),
    ).filter(SubcontractorAssignment.subcontractor_id == sub_id).all()
    return [{
        "id": a.id,
        "project_id": a.project_id,
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


@router.post("/subcontractors/{sub_id}/assignments", summary="Asignar a proyecto")
def create_assignment(
    sub_id: str,
    payload: AssignmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    sub = db.query(Subcontractor).filter(Subcontractor.id == sub_id).first()
    if not sub: raise HTTPException(404)
    assignment = SubcontractorAssignment(subcontractor_id=sub_id, **payload.model_dump())
    db.add(assignment)
    audit_log(db, current_user, "CREATE", "subcontractor_assignments", assignment.id, sub.name)
    db.commit()
    return {"ok": True, "id": assignment.id}


# ═══════════════════════════════════════════════════════════════════════════════
# SUBCONTRACTOR WORKERS
# ═══════════════════════════════════════════════════════════════════════════════

class WorkerCreate(BaseModel):
    name: str
    role: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    cost_rate: Optional[float] = None
    sell_rate: Optional[float] = None
    currency: str = settings.DEFAULT_CURRENCY
    available_from: Optional[date] = None
    available_until: Optional[date] = None
    weekly_capacity_hours: Optional[float] = None
    notes: Optional[str] = None

class WorkerUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    cost_rate: Optional[float] = None
    sell_rate: Optional[float] = None
    currency: Optional[str] = None
    available_from: Optional[date] = None
    available_until: Optional[date] = None
    weekly_capacity_hours: Optional[float] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None

class WorkerSkillCreate(BaseModel):
    skill_id: str
    level: str = "intermediate"
    years_experience: Optional[float] = None
    certified: bool = False
    cert_name: Optional[str] = None
    notes: Optional[str] = None


_worker_out = _svc.serialize_worker


@router.get("/subcontractors/workers", summary="Buscar trabajadores de subcontratistas")
def list_all_workers(
    skill_id: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.enterprise import SubcontractorWorker, SubcontractorWorkerSkill
    from sqlalchemy.orm import joinedload
    q = db.query(SubcontractorWorker).options(
        joinedload(SubcontractorWorker.skills).joinedload(SubcontractorWorkerSkill.skill),
        joinedload(SubcontractorWorker.assignments),
        joinedload(SubcontractorWorker.subcontractor),
        joinedload(SubcontractorWorker.user),
    )
    if is_active is not None: q = q.filter(SubcontractorWorker.is_active == is_active)
    if skill_id:
        q = q.join(SubcontractorWorkerSkill, SubcontractorWorker.id == SubcontractorWorkerSkill.worker_id).filter(
            SubcontractorWorkerSkill.skill_id == skill_id
        )
    workers = q.order_by(SubcontractorWorker.name).all()
    result = []
    for w in workers:
        d = _worker_out(w)
        d["company_name"] = w.subcontractor.name if w.subcontractor else None
        d["company_code"] = w.subcontractor.code if w.subcontractor else None
        result.append(d)
    return result


@router.get("/subcontractors/{sub_id}/workers", summary="Trabajadores del subcontratista")
def get_workers(
    sub_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.enterprise import SubcontractorWorker, SubcontractorWorkerSkill
    from sqlalchemy.orm import joinedload
    sub = db.query(Subcontractor).filter(Subcontractor.id == sub_id).first()
    if not sub: raise HTTPException(404)
    workers = db.query(SubcontractorWorker).options(
        joinedload(SubcontractorWorker.skills).joinedload(SubcontractorWorkerSkill.skill),
        joinedload(SubcontractorWorker.assignments),
        joinedload(SubcontractorWorker.user),
    ).filter(SubcontractorWorker.subcontractor_id == sub_id).order_by(SubcontractorWorker.name).all()
    return [_worker_out(w) for w in workers]


@router.post("/subcontractors/{sub_id}/workers", summary="Añadir trabajador al subcontratista", status_code=201)
def create_worker(
    sub_id: str,
    payload: WorkerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    sub = db.query(Subcontractor).filter(Subcontractor.id == sub_id).first()
    if not sub: raise HTTPException(404)
    return _svc.create_worker_with_user(sub, payload, current_user, db)


@router.patch("/subcontractors/workers/{worker_id}", summary="Actualizar trabajador")
def update_worker(
    worker_id: str,
    payload: WorkerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.enterprise import SubcontractorWorker, SubcontractorWorkerSkill
    from sqlalchemy.orm import joinedload
    worker = db.query(SubcontractorWorker).options(
        joinedload(SubcontractorWorker.skills).joinedload(SubcontractorWorkerSkill.skill),
        joinedload(SubcontractorWorker.assignments),
        joinedload(SubcontractorWorker.user),
    ).filter(SubcontractorWorker.id == worker_id).first()
    if not worker: raise HTTPException(404)

    update_data = payload.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(worker, k, v)

    # Sync the linked User record
    if worker.user_id:
        linked_user = db.query(User).filter(User.id == worker.user_id).first()
        if linked_user:
            if "name" in update_data:
                linked_user.full_name = update_data["name"]
                parts = update_data["name"].strip().split(" ", 1)
                linked_user.first_name = parts[0]
                linked_user.last_name = parts[1] if len(parts) > 1 else None
            if "role" in update_data:
                linked_user.job_title = update_data["role"]
            if "phone" in update_data:
                linked_user.phone = update_data["phone"]
            if "cost_rate" in update_data:
                linked_user.hourly_rate = update_data["cost_rate"]
            if "currency" in update_data:
                linked_user.currency = update_data["currency"]
            if "weekly_capacity_hours" in update_data and update_data["weekly_capacity_hours"] is not None:
                linked_user.weekly_capacity_hours = update_data["weekly_capacity_hours"]
            if "is_active" in update_data:
                linked_user.is_active = update_data["is_active"]
            if "email" in update_data and update_data["email"]:
                # Only update email if it doesn't conflict with another user
                conflict = db.query(User).filter(
                    User.email == update_data["email"],
                    User.id != linked_user.id,
                ).first()
                if not conflict:
                    linked_user.email = update_data["email"]

    db.commit()
    db.refresh(worker)
    return _worker_out(worker)


@router.delete("/subcontractors/workers/{worker_id}", summary="Desactivar trabajador (soft delete)")
def delete_worker(
    worker_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.enterprise import SubcontractorWorker
    worker = db.query(SubcontractorWorker).filter(SubcontractorWorker.id == worker_id).first()
    if not worker: raise HTTPException(404)
    worker.is_active = False
    # Also deactivate the linked User resource
    if worker.user_id:
        linked_user = db.query(User).filter(User.id == worker.user_id).first()
        if linked_user:
            linked_user.is_active = False
    db.commit()
    return {"ok": True}


@router.post("/subcontractors/workers/{worker_id}/skills", summary="Asignar skill al trabajador", status_code=201)
def add_worker_skill(
    worker_id: str,
    payload: WorkerSkillCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.enterprise import SubcontractorWorker, SubcontractorWorkerSkill
    worker = db.query(SubcontractorWorker).filter(SubcontractorWorker.id == worker_id).first()
    if not worker: raise HTTPException(404)
    # Prevent duplicate skill
    existing = db.query(SubcontractorWorkerSkill).filter(
        SubcontractorWorkerSkill.worker_id == worker_id,
        SubcontractorWorkerSkill.skill_id == payload.skill_id,
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


@router.delete("/subcontractors/workers/{worker_id}/skills/{skill_id}", summary="Eliminar skill del trabajador")
def remove_worker_skill(
    worker_id: str,
    skill_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.enterprise import SubcontractorWorkerSkill
    ws = db.query(SubcontractorWorkerSkill).filter(
        SubcontractorWorkerSkill.worker_id == worker_id,
        SubcontractorWorkerSkill.skill_id == skill_id,
    ).first()
    if not ws: raise HTTPException(404)
    db.delete(ws)
    db.commit()
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# REVENUE FORECAST
# ═══════════════════════════════════════════════════════════════════════════════

class ForecastUpdate(BaseModel):
    revenue_planned: Optional[float] = None
    revenue_actual: Optional[float] = None
    revenue_forecast: Optional[float] = None
    cost_planned: Optional[float] = None
    cost_actual: Optional[float] = None
    hours_planned: Optional[float] = None
    hours_actual: Optional[float] = None
    notes: Optional[str] = None


_forecast_out = _svc.serialize_forecast


@router.get("/revenue-forecast/portfolio", summary="Previsión de ingresos de toda la cartera")
def portfolio_forecast(
    year: int = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    if not year:
        year = datetime.now(timezone.utc).year
    return _svc.get_portfolio_forecast(db, year)


@router.get("/revenue-forecast/{project_id}", summary="Previsión de un proyecto")
def project_forecast(
    project_id: str,
    year: int = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    if not year:
        year = datetime.now(timezone.utc).year

    forecasts = db.query(RevenueForecast).filter(
        RevenueForecast.project_id == project_id,
        RevenueForecast.year == year,
    ).order_by(RevenueForecast.month).all()

    # Fill in missing months with zeros
    existing = {f.month: f for f in forecasts}
    result = []
    for month in range(1, 13):
        if month in existing:
            result.append(_forecast_out(existing[month]))
        else:
            result.append({
                "id": None, "project_id": project_id, "year": year, "month": month,
                "revenue_planned": 0, "revenue_actual": 0, "revenue_forecast": 0,
                "cost_planned": 0, "cost_actual": 0,
                "hours_planned": 0, "hours_actual": 0, "margin_pct": None, "notes": None,
            })
    return {"year": year, "project_id": project_id, "monthly": result}


@router.post("/revenue-forecast/{project_id}/{year}/{month}", summary="Crear/actualizar previsión mensual")
def upsert_forecast(
    project_id: str,
    year: int,
    month: int,
    payload: ForecastUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    if not 1 <= month <= 12: raise HTTPException(400, "Mes inválido (1-12)")
    existing = db.query(RevenueForecast).filter(
        RevenueForecast.project_id == project_id,
        RevenueForecast.year == year,
        RevenueForecast.month == month,
    ).first()
    if existing:
        for k, v in payload.model_dump(exclude_unset=True).items():
            setattr(existing, k, v)
        # Recalculate margin
        rev = existing.revenue_forecast or existing.revenue_planned or 0
        cost = existing.cost_actual or existing.cost_planned or 0
        existing.margin_pct = round((rev - cost) / rev * 100, 1) if rev > 0 else None
        db.commit()
        return _forecast_out(existing)
    else:
        data = payload.model_dump()
        rev = data.get("revenue_forecast") or data.get("revenue_planned") or 0
        cost = data.get("cost_actual") or data.get("cost_planned") or 0
        margin = round((rev - cost) / rev * 100, 1) if rev > 0 else None
        forecast = RevenueForecast(
            project_id=project_id, year=year, month=month,
            margin_pct=margin, **data,
        )
        db.add(forecast); db.commit(); db.refresh(forecast)
        return _forecast_out(forecast)


# ── Subcontractor Time Logs ────────────────────────────────────────────────────

@router.get("/subcontractors/{sub_id}/timelogs", summary="Registros de horas del subcontratista")
def get_timelogs(
    sub_id: str,
    project_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.enterprise import SubcontractorTimeLog
    q = db.query(SubcontractorTimeLog).filter(SubcontractorTimeLog.subcontractor_id == sub_id)
    if project_id: q = q.filter(SubcontractorTimeLog.project_id == project_id)
    logs = q.order_by(SubcontractorTimeLog.log_date.desc()).all()
    return [{
        "id": l.id, "log_date": str(l.log_date), "hours": l.hours,
        "description": l.description, "task_reference": l.task_reference,
        "cost_amount": l.cost_amount, "is_invoiced": l.is_invoiced,
        "project_id": l.project_id,
        "project_name": l.project.name if l.project else None,
    } for l in logs]


@router.post("/subcontractors/{sub_id}/timelogs", summary="Registrar horas de subcontratista")
def create_timelog(
    sub_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.enterprise import Subcontractor, SubcontractorTimeLog, SubcontractorAssignment
    import uuid as _uuid

    sub = db.query(Subcontractor).filter(Subcontractor.id == sub_id).first()
    if not sub: raise HTTPException(404)

    # Calcular coste automáticamente desde la tarifa de la asignación
    cost_amount = payload.get("cost_amount")
    assignment_id = payload.get("assignment_id")
    if not cost_amount and assignment_id:
        assignment = db.query(SubcontractorAssignment).filter(
            SubcontractorAssignment.id == assignment_id
        ).first()
        if assignment and assignment.rate:
            cost_amount = round(float(payload.get("hours", 0)) * assignment.rate.cost_rate, 2)

    log = SubcontractorTimeLog(
        id=str(_uuid.uuid4()),
        subcontractor_id=sub_id,
        assignment_id=assignment_id,
        project_id=payload.get("project_id"),
        log_date=payload.get("log_date"),
        hours=float(payload.get("hours", 0)),
        description=payload.get("description"),
        task_reference=payload.get("task_reference"),
        cost_amount=cost_amount,
    )
    db.add(log)

    # Actualizar horas_logged en la asignación
    if assignment_id:
        assignment = db.query(SubcontractorAssignment).filter(
            SubcontractorAssignment.id == assignment_id
        ).first()
        if assignment:
            assignment.hours_logged = (assignment.hours_logged or 0) + float(payload.get("hours", 0))

    db.commit()
    return {"ok": True, "id": log.id, "cost_amount": cost_amount}


@router.delete("/subcontractors/{sub_id}/timelogs/{log_id}", summary="Eliminar registro de horas")
def delete_timelog(
    sub_id: str, log_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.enterprise import SubcontractorTimeLog
    log = db.query(SubcontractorTimeLog).filter(
        SubcontractorTimeLog.id == log_id,
        SubcontractorTimeLog.subcontractor_id == sub_id,
    ).first()
    if not log: raise HTTPException(404)
    if log.is_invoiced: raise HTTPException(400, "No se puede eliminar un registro ya facturado")
    db.delete(log); db.commit()
    return {"ok": True}


# ── Subcontractor Invoices ─────────────────────────────────────────────────────

@router.get("/subcontractors/{sub_id}/invoices", summary="Facturas recibidas del subcontratista")
def get_sub_invoices(
    sub_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.enterprise import SubcontractorInvoice
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


@router.post("/subcontractors/{sub_id}/invoices", summary="Registrar factura recibida")
def create_sub_invoice(
    sub_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.enterprise import Subcontractor, SubcontractorInvoice, SubcontractorTimeLog
    import uuid as _uuid

    sub = db.query(Subcontractor).filter(Subcontractor.id == sub_id).first()
    if not sub: raise HTTPException(404)

    amount = float(payload.get("amount", 0))
    tax_pct = float(payload.get("tax_pct", settings.DEFAULT_TAX_RATE))
    total = round(amount * (1 + tax_pct / 100), 2)

    inv = SubcontractorInvoice(
        id=str(_uuid.uuid4()),
        subcontractor_id=sub_id,
        assignment_id=payload.get("assignment_id"),
        invoice_number=payload.get("invoice_number", f"SUB-INV-{_uuid.uuid4().hex[:6].upper()}"),
        issue_date=payload.get("issue_date"),
        due_date=payload.get("due_date"),
        amount=amount,
        tax_pct=tax_pct,
        total=total,
        currency=payload.get("currency", sub.currency or settings.DEFAULT_CURRENCY),
        description=payload.get("description"),
    )
    db.add(inv)

    # Marcar timelogs del assignment como facturados
    if payload.get("timelog_ids"):
        db.query(SubcontractorTimeLog).filter(
            SubcontractorTimeLog.id.in_(payload["timelog_ids"])
        ).update({"is_invoiced": True, "invoice_id": inv.id}, synchronize_session=False)

    db.commit()
    audit_log(db, current_user, "CREATE", "subcontractor_invoices", inv.id, sub.name)
    return {"ok": True, "id": inv.id, "total": total}


@router.patch("/subcontractors/{sub_id}/invoices/{inv_id}", summary="Actualizar estado de factura")
def update_sub_invoice(
    sub_id: str, inv_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.enterprise import SubcontractorInvoice
    inv = db.query(SubcontractorInvoice).filter(
        SubcontractorInvoice.id == inv_id,
        SubcontractorInvoice.subcontractor_id == sub_id,
    ).first()
    if not inv: raise HTTPException(404)
    for k in ["status", "paid_date", "description"]:
        if k in payload: setattr(inv, k, payload[k])
    db.commit()
    return {"ok": True}


# ── Subcontractor Dashboard ────────────────────────────────────────────────────

@router.get("/subcontractors-dashboard", summary="Dashboard global de subcontratistas")
def subcontractors_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.enterprise import (
        Subcontractor, SubcontractorAssignment, SubcontractorInvoice, SubcontractorTimeLog
    )
    # func importado globalmente al inicio del módulo

    total_subs   = db.query(func.count(Subcontractor.id)).filter(Subcontractor.is_active == True).scalar()
    active_assgn = db.query(func.count(SubcontractorAssignment.id)).scalar()
    pending_invs = db.query(func.count(SubcontractorInvoice.id)).filter(
        SubcontractorInvoice.status == "received"
    ).scalar()
    total_cost   = db.query(func.sum(SubcontractorInvoice.total)).filter(
        SubcontractorInvoice.status.in_(["approved", "paid"])
    ).scalar() or 0
    pending_cost = db.query(func.sum(SubcontractorInvoice.total)).filter(
        SubcontractorInvoice.status == "received"
    ).scalar() or 0
    total_hours  = db.query(func.sum(SubcontractorTimeLog.hours)).scalar() or 0

    return {
        "total_active_subs":      total_subs,
        "active_assignments":     active_assgn,
        "pending_invoices":       pending_invs,
        "total_paid_cost":        round(total_cost, 2),
        "pending_approval_cost":  round(pending_cost, 2),
        "total_hours_logged":     round(total_hours, 1),
    }
