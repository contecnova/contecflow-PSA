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
        "domain": org.domain, "suspension_reason": org.suspension_reason,
        "deletion_purge_after": org.deletion_purge_after.isoformat() if org.deletion_purge_after else None,
        "created_at": str(org.created_at)[:10] if org.created_at else None,
        # El mismo recuento que el limite (`exigir_cupo`): ficha o pertenencia.
        "user_count": _usuarios_de(db, org.id),
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
    admin_name = payload_dict.pop("admin_name", None)
    _validar_dominio(db, payload_dict.get("domain"))
    org = Organization(**payload_dict)
    db.add(org)
    db.flush()
    # Revision multitenant 2026-11: sin un primer admin nadie podia entrar en
    # la empresa nueva. Si se da su correo, se crea con una contrasena inicial.
    inicial = crear_primer_admin(db, org, org.admin_email, admin_name) if org.admin_email else None
    db.commit(); db.refresh(org)
    audit_log(db, current_user, "ORG_CREATED", "organizations", org.id, org.name)
    db.commit()
    return {"ok": True, "id": org.id, "slug": org.slug,
            "admin_email": org.admin_email if inicial else None, "initial_password": inicial}


def _validar_dominio(db: Session, dominio, org_id=None) -> None:
    if not dominio:
        return
    otra = db.query(Organization).filter(Organization.domain == dominio.strip().lower()).first()
    if otra is not None and otra.id != org_id:
        raise ValueError(f"El dominio {dominio} ya es de otra empresa")


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
        "domain": org.domain, "suspension_reason": org.suspension_reason,
        "deletion_purge_after": org.deletion_purge_after.isoformat() if org.deletion_purge_after else None,
        "admin_email": org.admin_email, "timezone": org.timezone,
        "locale": org.locale, "primary_color": org.primary_color,
        "require_mfa": bool(org.require_mfa),
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
               "require_mfa", "domain", "suspension_reason"}
    # Suspender pide motivo (se guarda y se ensena); reactivar lo borra. La
    # suspension corta en el acto las sesiones abiertas (deps.get_current_user).
    if payload.get("is_active") is False and not (payload.get("suspension_reason") or "").strip():
        raise ValueError("motivo_requerido")
    if payload.get("is_active") is True:
        payload["suspension_reason"] = None
    if "domain" in payload:
        payload["domain"] = (payload["domain"] or "").strip().lower() or None
        _validar_dominio(db, payload["domain"], org_id)
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


# ── Revision multitenant 2026-11: alta con primer admin, cupos, suspension ──

def _usuarios_de(db: Session, org_id: str) -> int:
    """Usuarios activos de la empresa: los de su ficha y los de pertenencia."""
    from sqlalchemy import or_, select
    return db.query(func.count(User.id)).filter(
        User.is_active.is_(True), User.is_superadmin.isnot(True),
        or_(User.organization_id == org_id,
            User.id.in_(select(UserOrganizationMembership.user_id)
                        .where(UserOrganizationMembership.organization_id == org_id))),
    ).scalar() or 0


def exigir_cupo(db: Session, org_id, recurso: str) -> None:
    """409 si la empresa ya llego al limite de su plan para `recurso`.

    Antes los limites solo se miraban al asignar un usuario existente: crear
    usuarios o proyectos no los respetaba.
    """
    if not org_id:
        return
    from fastapi import HTTPException
    from app.db.session import sin_filtro_de_tenant
    with sin_filtro_de_tenant(db):
        org = db.get(Organization, org_id)
        if org is None:
            return
        if recurso == "users":
            usados, limite = _usuarios_de(db, org_id), org.max_users
        else:
            usados = db.query(func.count(Project.id)).filter(Project.organization_id == org_id).scalar() or 0
            limite = org.max_projects
    if limite is not None and usados >= limite:
        nombre = "usuarios" if recurso == "users" else "proyectos"
        raise HTTPException(409, f"La empresa ha llegado al límite de {limite} {nombre} de su plan")


def crear_primer_admin(db: Session, org: Organization, email: str, nombre: str) -> str:
    """El administrador de la empresa nueva; devuelve su contrasena inicial (se ensena una vez)."""
    import secrets
    from app.core.security import get_password_hash
    from app.models.user import UserRole
    email = email.strip().lower()
    if db.query(User).filter(User.email == email).first():
        raise ValueError(f"Ya existe un usuario con el correo {email}: asígnalo a la empresa desde su ficha")
    inicial = secrets.token_urlsafe(12) + "Aa1!"
    admin = User(username=email, email=email, full_name=nombre or email, role=UserRole.admin,
                 is_active=True, organization_id=org.id, hashed_password=get_password_hash(inicial))
    db.add(admin)
    db.flush()
    db.add(UserOrganizationMembership(user_id=admin.id, organization_id=org.id))
    return inicial
