"""Clientes del portal: alta, edicion, acceso, perfil propio y marca.

Parte de `app.services.client_portal_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from app.models.client_portal import ClientUser, client_user_projects
from app.models.clients import ClientPortalConfig, Client
from app.models.clients import Client as ClientOrg
from app.models.project import Project as ProjectModel
from sqlalchemy.orm import joinedload

from app.services.client_portal_service.autenticacion import (
    create_client_token,
    hash_password,
    verify_password,
)


# ── Client Management ─────────────────────────────────────────────────────────

def list_clients(project_id: Optional[str], client_org_id: Optional[str], db: Session) -> list:
    import sqlalchemy as sa

    q = db.query(ClientUser).options(joinedload(ClientUser.project), joinedload(ClientUser.projects))
    if project_id:
        q = q.outerjoin(
            client_user_projects,
            ClientUser.id == client_user_projects.c.client_user_id,
        ).filter(
            sa.or_(
                ClientUser.project_id == project_id,
                client_user_projects.c.project_id == project_id,
            )
        ).distinct()
    if client_org_id:
        q = q.filter(ClientUser.client_org_id == client_org_id)
    clients = q.order_by(ClientUser.full_name).all()
    return [{
        "id": c.id,
        "project_id": c.project_id,
        "project_ids": c.get_project_ids(),
        "project_name": c.project.name if c.project else (c.projects[0].name if c.projects else None),
        "client_org_id": c.client_org_id,
        "full_name": c.full_name, "email": c.email,
        "job_title": c.job_title, "company": c.company,
        "phone": c.phone,
        "is_active": c.is_active,
        "can_approve_deliverables": c.can_approve_deliverables,
        "can_request_changes": c.can_request_changes,
        "can_view_budget": c.can_view_budget,
        "can_view_team": c.can_view_team,
        "last_login": str(c.last_login)[:16] if c.last_login else None,
        "created_at": str(c.created_at)[:10],
        "portal_url": "/portal",
    } for c in clients]


def create_client(payload, db: Session) -> dict:

    all_project_ids = list(dict.fromkeys([
        *(payload.project_ids or []),
        *([payload.project_id] if payload.project_id else [])
    ]))
    if not all_project_ids and not payload.client_org_id:
        raise ValueError("Debe especificar al menos un proyecto o una empresa cliente")
    if db.query(ClientUser).filter(ClientUser.email == payload.email).first():
        raise ValueError("Ya existe un usuario de portal con ese email")
    # Revisión 2026-11: el tope de usuarios por cliente sólo lo aplicaba un
    # segundo camino de alta sin pantalla (/clients/{id}/portal-users, retirado).
    if payload.client_org_id:
        from app.models.clients import ClientPortalConfig
        cfg = db.query(ClientPortalConfig).filter(ClientPortalConfig.client_id == payload.client_org_id).first()
        if cfg and cfg.max_portal_users:
            activos = db.query(ClientUser).filter(ClientUser.client_org_id == payload.client_org_id,
                                                  ClientUser.is_active == True).count()  # noqa: E712
            if activos >= cfg.max_portal_users:
                raise ValueError(f"Límite de usuarios de portal alcanzado ({cfg.max_portal_users})")
    company = payload.company
    empresa = db.query(ClientOrg).filter(ClientOrg.id == payload.client_org_id).first() if payload.client_org_id else None
    if empresa and not company:
        company = empresa.name
    # Auditoria 2026-11: la organizacion la ponia el sellado de la sesion (la
    # del empleado que lo crea), no la del cliente; el filtro de organizacion
    # del portal le ocultaba entonces sus proyectos. Es la de la empresa
    # cliente o, sin ella, la de su primer proyecto.
    organizacion = empresa.organization_id if empresa else None
    if organizacion is None and all_project_ids:
        primero = db.query(ProjectModel).filter(ProjectModel.id == all_project_ids[0]).first()
        organizacion = primero.organization_id if primero else None
    create_data = {k: v for k, v in payload.model_dump().items()
                   if k not in ("password", "company", "project_ids", "project_id", "organization_id")}
    client = ClientUser(
        **create_data,
        organization_id=organizacion,
        project_id=payload.project_id or (all_project_ids[0] if all_project_ids else None),
        company=company,
        hashed_password=hash_password(payload.password),
        avatar_initials=payload.full_name[:2].upper(),
    )
    db.add(client)
    db.flush()
    if all_project_ids:
        for pid in all_project_ids:
            proj = db.query(ProjectModel).filter(ProjectModel.id == pid).first()
            if proj and proj not in client.projects:
                client.projects.append(proj)
    db.commit()
    db.refresh(client)
    return {
        "id": client.id,
        "email": client.email,
        "project_ids": client.get_project_ids(),
        "portal_url": "/portal",
        "message": f"Usuario creado. Puede acceder en /portal con {client.email} y la contraseña indicada."
    }


def update_client(client_id: str, payload: dict, db: Session) -> dict:

    client = db.query(ClientUser).filter(ClientUser.id == client_id).first()
    if not client:
        raise ValueError("Cliente no encontrado")
    allowed = ["full_name", "email", "job_title", "company", "phone", "is_active", "project_id",
               "can_approve_deliverables", "can_request_changes", "can_view_budget", "can_view_team", "language"]
    project_ids_payload = None
    if "project_ids" in payload:
        project_ids_payload = [pid for pid in (payload.get("project_ids") or []) if pid]
    elif "project_id" in payload:
        project_ids_payload = [payload["project_id"]] if payload.get("project_id") else []
    for k, v in payload.items():
        if k in allowed and k != "project_id":
            setattr(client, k, v)
    if "password" in payload:
        client.hashed_password = hash_password(payload["password"])
    if project_ids_payload is not None:
        ordered_ids = list(dict.fromkeys(project_ids_payload))
        client.projects.clear()
        valid_ids = []
        for pid in ordered_ids:
            proj = db.query(ProjectModel).filter(ProjectModel.id == pid).first()
            if proj:
                client.projects.append(proj)
                valid_ids.append(pid)
        client.project_id = valid_ids[0] if valid_ids else None
    db.commit()
    return {"ok": True, "project_ids": client.get_project_ids()}


def delete_client(client_id: str, db: Session) -> dict:

    client = db.query(ClientUser).filter(ClientUser.id == client_id).first()
    if not client:
        raise ValueError("Cliente no encontrado")
    db.delete(client)
    db.commit()
    return {"ok": True}


# ── Auth ──────────────────────────────────────────────────────────────────────

def get_active_client_by_id(db: Session, client_id: str) -> Optional[ClientUser]:
    """Return an active ClientUser by id, or None if not found / inactive."""
    return db.query(ClientUser).filter(ClientUser.id == client_id, ClientUser.is_active == True).first()


def client_login(email: str, password: str, db: Session) -> dict:

    client = db.query(ClientUser).filter(ClientUser.email == email, ClientUser.is_active == True).first()
    if not client or not client.hashed_password:
        raise ValueError("Email o contraseña incorrectos")
    if not verify_password(password, client.hashed_password):
        raise ValueError("Email o contraseña incorrectos")
    # Revision multitenant 2026-11b: el login del portal emitia token aunque la
    # empresa estuviera desactivada (luego cada llamada daba 403).
    from app.db.session import exigir_organizacion_activa
    exigir_organizacion_activa(db, client.organization_id)
    client.last_login = datetime.now(timezone.utc)
    db.commit()
    token = create_client_token(client.id)
    project_ids = client.get_project_ids()
    projects = []
    if project_ids:
        projects = [{"id": p.id, "name": p.name, "code": p.code, "status": p.status}
                    for p in db.query(ProjectModel).filter(ProjectModel.id.in_(project_ids)).all()]
    return {
        "token": token,
        "client": {
            "id": client.id, "full_name": client.full_name, "email": client.email,
            "project_id": client.project_id,
            "can_approve_deliverables": client.can_approve_deliverables,
            "can_request_changes": client.can_request_changes,
            "can_view_budget": client.can_view_budget,
            "can_view_team": client.can_view_team,
            "language": client.language,
            "project_ids": project_ids,
            "projects": projects,
        }
    }


def get_me(current_client, db: Session) -> dict:

    project_ids = current_client.get_project_ids()
    projects_info = []
    if project_ids:
        projs = db.query(ProjectModel).filter(ProjectModel.id.in_(project_ids)).all()
        projects_info = [{"id": p.id, "name": p.name, "code": p.code, "status": p.status} for p in projs]
    return {
        "id": current_client.id, "full_name": current_client.full_name,
        "email": current_client.email, "job_title": current_client.job_title,
        # Auditoria 2026-11: sin el telefono, el formulario de perfil lo enviaba
        # vacio al guardar y lo borraba.
        "phone": getattr(current_client, "phone", None),
        "company": current_client.company, "project_id": current_client.project_id,
        "project_ids": project_ids,
        "projects": projects_info,
        "can_approve_deliverables": current_client.can_approve_deliverables,
        "can_request_changes": current_client.can_request_changes,
        "can_view_budget": current_client.can_view_budget,
        "can_view_team": current_client.can_view_team,
        "language": current_client.language,
    }


def get_portal_branding(current_client, db: Session) -> dict:

    cfg = None
    client_name = current_client.company
    if current_client.client_org_id:
        cfg = db.query(ClientPortalConfig).filter(
            ClientPortalConfig.client_id == current_client.client_org_id
        ).first()
        client_org = db.query(Client).filter(Client.id == current_client.client_org_id).first()
        if client_org and client_org.name:
            client_name = client_org.name
    return {
        "brand_name": client_name or "Portal Cliente",
        "logo_url": cfg.logo_url if cfg else None,
        "primary_color": cfg.accent_color if cfg and cfg.accent_color else "#00d4ff",
        # Las traducciones que el administrador personalizó: antes solo las leía
        # su propio navegador y al cliente no le llegaban nunca.
        "translations": _traducciones_del_portal_de(db, current_client),
    }


def _traducciones_del_portal_de(db: Session, current_client) -> dict:
    from app.services.branding_service import traducciones_del_portal
    org_id = getattr(current_client, "organization_id", None)
    return traducciones_del_portal(db, str(org_id)) if org_id else {}


def update_my_profile(payload: dict, current_client, db: Session, min_password_length: int = 8) -> dict:

    cfg = None
    if current_client.client_org_id:
        cfg = db.query(ClientPortalConfig).filter(
            ClientPortalConfig.client_id == current_client.client_org_id
        ).first()

    allow_edit = cfg.allow_profile_edit if cfg else True
    allow_pwd  = cfg.allow_pwd_change   if cfg else True

    SAFE_FIELDS = {"full_name", "phone", "language", "job_title"}
    has_safe_fields = any(k in SAFE_FIELDS for k in payload if k != "password")
    if not allow_edit and has_safe_fields:
        raise ValueError("Edición de perfil deshabilitada para este portal")
    BLOCKED = {"email", "hashed_password", "current_password", "can_approve_deliverables",
               "can_request_changes", "can_view_budget", "can_view_team",
               "project_id", "client_org_id", "is_active", "id"}

    for k, v in payload.items():
        if k in BLOCKED:
            continue
        if k == "password":
            if not allow_pwd:
                raise ValueError("El cambio de contraseña está desactivado")
            # Auditoria 2026-11: sin la actual, una sesion robada o un equipo
            # desbloqueado bastaba para quedarse la cuenta.
            actual = payload.get("current_password")
            if not actual or not verify_password(str(actual), current_client.hashed_password or ""):
                raise ValueError("La contraseña actual no es correcta")
            if len(str(v)) < min_password_length:
                raise ValueError(f"La contraseña debe tener al menos {min_password_length} caracteres")
            current_client.hashed_password = hash_password(str(v))
        elif k in SAFE_FIELDS:
            setattr(current_client, k, v)

    db.commit()
    db.refresh(current_client)
    return {
        "id": current_client.id,
        "full_name": current_client.full_name,
        "email": current_client.email,
        "phone": current_client.phone,
        "job_title": current_client.job_title,
        "language": current_client.language,
        "message": "Perfil actualizado correctamente",
    }
