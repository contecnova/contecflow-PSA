"""Registro de auditoria (consulta, estadisticas, exportacion firmada) y permisos por proyecto.

Parte de `app.services.enterprise_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.enterprise import AuditLog
from app.models.enterprise import ProjectPermission
from app.models.project import Project
from app.models.user import User
from app.services.audit import audit_log
from app.services.notifications import notify_user
from datetime import timedelta
from datetime import datetime as _dt
from sqlalchemy.orm import joinedload


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


def exportar_cadena_de_auditoria(db: Session, current_user) -> dict:
    """Exportacion firmada del registro de auditoria; deja traza de la exportacion y confirma."""
    from app.db import cadena_auditoria
    from app.services.settings_service import get_runtime_int
    limite = int(get_runtime_int(db, "AUDIT_EXPORT_MAX_ROWS", current_user.organization_id) or 0) or 1
    doc = cadena_auditoria.exportar(db, current_user.organization_id, limite)
    audit_log(db, current_user, "EXPORT", "audit_chain", resource_name="signed export",
              metadata={"rows": len(doc["entries"]), "head": doc["head"], "ok": doc["verification"]["ok"]})
    db.commit()
    return doc
