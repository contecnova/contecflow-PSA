"""Organizaciones: alta, consulta, edicion y asignacion de usuarios.

Auditoria 2026-08 (hallazgo 22). Este codigo vivia en `mfa_service.py`, un
fichero de 1.435 lineas que contenia OCHO dominios sin relacion entre si —MFA,
organizaciones, Slack, presupuestos, planificacion asistida, escenarios, PDF y
tokens de BI— servidos ademas por un unico router llamado `mfa.py` con 38 rutas.

El reparto se pudo hacer mecanicamente porque los ocho dominios nunca estuvieron
acoplados, solo apilados: se comprobo por AST que no habia ni una llamada entre
grupos ni un solo ciclo. Los cuerpos se movieron verbatim.
"""

from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.user import User
from app.models.user import UserOrganizationMembership
from app.models.project import Project
from app.models.mfa import (
    Organization,
)
from app.services.audit import audit_log


def serialize_organization(org: Organization, db: Session) -> dict:
    return {
        "id": org.id, "name": org.name, "slug": org.slug,
        "plan": org.plan, "is_active": org.is_active,
        "max_users": org.max_users, "max_projects": org.max_projects,
        "admin_email": org.admin_email,
        "created_at": str(org.created_at)[:10] if org.created_at else None,
        "user_count": db.query(func.count(func.distinct(UserOrganizationMembership.user_id))).filter(
            UserOrganizationMembership.organization_id == org.id
        ).scalar(),
        "project_count": db.query(func.count(Project.id)).filter(Project.organization_id == org.id).scalar() if hasattr(Project, 'organization_id') else 0,
    }


def check_org_user_limit(org: Organization, db: Session) -> None:
    count = db.query(func.count(func.distinct(UserOrganizationMembership.user_id))).filter(
        UserOrganizationMembership.organization_id == org.id
    ).scalar()
    if count >= org.max_users:
        raise ValueError(f"Límite de {org.max_users} usuarios alcanzado para este plan")


def list_organizations(db: Session) -> list:
    orgs = db.query(Organization).order_by(Organization.name).limit(200).all()
    return [serialize_organization(o, db) for o in orgs]


def create_organization(payload_dict: dict, current_user: User, db: Session) -> dict:
    existing = db.query(Organization).filter(Organization.slug == payload_dict["slug"]).first()
    if existing:
        raise ValueError(f"Slug '{payload_dict['slug']}' ya está en uso")
    org = Organization(**payload_dict)
    db.add(org); db.commit(); db.refresh(org)
    audit_log(db, current_user, "ORG_CREATED", "organizations", org.id, org.name)
    db.commit()
    return {"ok": True, "id": org.id, "slug": org.slug}


def get_organization(org_id: str, db: Session) -> dict:
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise ValueError("not_found")
    users = db.query(User).join(
        UserOrganizationMembership,
        UserOrganizationMembership.user_id == User.id,
    ).filter(
        UserOrganizationMembership.organization_id == org_id,
    ).all()
    return {
        "id": org.id, "name": org.name, "slug": org.slug,
        "plan": org.plan, "is_active": org.is_active,
        "max_users": org.max_users, "max_projects": org.max_projects,
        "admin_email": org.admin_email, "timezone": org.timezone,
        "locale": org.locale, "primary_color": org.primary_color,
        "users": [{"id": u.id, "full_name": u.full_name, "email": u.email, "role": u.role} for u in users],
    }


def update_organization(org_id: str, payload: dict, db: Session) -> dict:
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise ValueError("not_found")
    # `require_mfa` es política de seguridad — además de whitelist, lo
    # registramos en audit_log cuando cambia para que el toggle sea trazable.
    allowed = {"name", "plan", "max_users", "max_projects", "is_active", "admin_email",
               "timezone", "locale", "primary_color", "logo_url",
               "require_mfa"}
    require_mfa_before = bool(getattr(org, "require_mfa", False))
    for k, v in payload.items():
        if k in allowed:
            setattr(org, k, v)
    require_mfa_after = bool(getattr(org, "require_mfa", False))
    db.commit()
    if require_mfa_before != require_mfa_after:
        # Cambio de política MFA: auditarlo de manera explícita
        try:
            import json
            from app.models.enterprise import AuditLog
            db.add(AuditLog(
                action="UPDATE",
                resource="organizations",
                resource_id=org.id,
                metadata_=json.dumps({
                    "field": "require_mfa",
                    "before": require_mfa_before,
                    "after": require_mfa_after,
                }),
            ))
            db.commit()
        except Exception:  # pragma: no cover — audit best-effort
            import logging
            logging.getLogger(__name__).exception("require_mfa audit failed")
    return {"ok": True}


def assign_user_to_org(org_id: str, user_id: str, db: Session) -> dict:
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise ValueError("404:Organización no encontrada")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError("404:Usuario no encontrado")
    if user.is_active is False:
        raise ValueError("No puedes asignar usuarios inactivos")
    membership = db.query(UserOrganizationMembership).filter(
        UserOrganizationMembership.user_id == user.id,
        UserOrganizationMembership.organization_id == org_id,
    ).first()
    if membership:
        raise ValueError("El usuario ya está asignado a esta organización")
    check_org_user_limit(org, db)
    db.add(UserOrganizationMembership(user_id=user.id, organization_id=org_id))
    if not user.organization_id:
        user.organization_id = org_id
    db.commit()
    audit_log(db, user, "ORG_ASSIGN", "organizations", org.id, f"Asignado a organización {org.name}")
    from app.core.events import emit_event, EventType
    emit_event(db, EventType.ORG_USER_ADDED, {"org_id": org.id, "user_id": user.id, "user_name": user.full_name},
               org_id=org.id, resource_type="organization", resource_id=org.id)
    return {"ok": True, "user": user.full_name, "org": org.name}


def remove_user_from_org(org_id: str, user_id: str, db: Session) -> dict:
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise ValueError("404:Organización no encontrada")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError("404:Usuario no encontrado en esta organización")
    membership = db.query(UserOrganizationMembership).filter(
        UserOrganizationMembership.user_id == user.id,
        UserOrganizationMembership.organization_id == org_id,
    ).first()
    if not membership:
        raise ValueError("404:Usuario no encontrado en esta organización")
    user_count = db.query(func.count(func.distinct(UserOrganizationMembership.user_id))).filter(
        UserOrganizationMembership.organization_id == org_id
    ).scalar()
    if user_count <= 1:
        raise ValueError("No puedes quitar el último usuario de la organización")
    user_org_count = db.query(func.count(UserOrganizationMembership.id)).filter(
        UserOrganizationMembership.user_id == user.id
    ).scalar()
    if user_org_count <= 1:
        raise ValueError("No puedes quitar al usuario de su última organización")
    user_name = user.full_name
    db.delete(membership)
    if str(user.organization_id) == str(org_id):
        fallback = db.query(UserOrganizationMembership).filter(
            UserOrganizationMembership.user_id == user.id
        ).first()
        user.organization_id = fallback.organization_id if fallback else None
    db.commit()
    audit_log(db, user, "ORG_REMOVE", "organizations", org.id, f"Desvinculado de organización {org.name}")
    from app.core.events import emit_event, EventType
    emit_event(db, EventType.ORG_USER_REMOVED, {"org_id": org.id, "user_id": user.id, "user_name": user_name},
               org_id=org.id, resource_type="organization", resource_id=org.id)
    return {"ok": True, "user": user_name, "org": org.name}
