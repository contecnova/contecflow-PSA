"""
audit.py — Centralized audit logging service.

Usage in any endpoint:
    from app.services.audit import audit_log
    audit_log(db, user, "UPDATE", "projects", project.id, project.name,
              old_values={"status": "planning"}, new_values={"status": "active"})
"""
import json
from typing import Optional
from sqlalchemy.orm import Session
from app.models.enterprise import AuditLog
from app.models.user import User


def audit_log(
    db: Session,
    user: Optional[User],
    action: str,
    resource: str,
    resource_id: Optional[str] = None,
    resource_name: Optional[str] = None,
    old_values: Optional[dict] = None,
    new_values: Optional[dict] = None,
    metadata: Optional[dict] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> AuditLog:
    """
    Write an audit log entry. Call this on every significant state change.

    Actions: CREATE, UPDATE, DELETE, LOGIN, LOGOUT, EXPORT, APPROVE,
             REJECT, SUBMIT, ASSIGN, ESCALATE, VIEW_FINANCIAL
    """
    suplantador = (getattr(db, "info", None) or {}).get("suplantado_por")
    if suplantador:
        # «Entrar como» (revision multitenant 2026-11b): la accion figura a nombre
        # del usuario suplantado, y aqui queda quien la hizo de verdad.
        metadata = {**(metadata or {}), "impersonated_by": suplantador}
    entry = AuditLog(
        user_id=user.id if user else None,
        user_name=user.full_name if user else "System",
        action=action.upper(),
        resource=resource,
        resource_id=resource_id,
        resource_name=resource_name,
        old_values=json.dumps(old_values, default=str) if old_values else None,
        new_values=json.dumps(new_values, default=str) if new_values else None,
        metadata_=json.dumps(metadata, default=str) if metadata else None,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(entry)
    # Note: caller is responsible for db.commit()
    return entry
