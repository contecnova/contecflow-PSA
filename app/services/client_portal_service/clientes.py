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

from app.core.paginacion import Pagina, Paginacion, paginar

from app.services.client_portal_service.autenticacion import (
    create_client_token,
    hash_password,
    verify_password,
)
from app.core.codigos_de_error import ErrorConCodigo


# ── Client Management ─────────────────────────────────────────────────────────

def list_clients(project_id: Optional[str], client_org_id: Optional[str], db: Session,
                 pagina: Optional[Paginacion] = None, incluir_archivados: bool = False) -> Pagina:
    """Usuarios del portal, por nombre. Pagina con el mecanismo comun
    (`app.core.paginacion`): sin `pagina`, la lista entera hasta LIST_MAX_ROWS.
    23-11-2026: los archivados solo con `incluir_archivados` («Ver archivados»)."""
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
    if not incluir_archivados:
        q = q.filter(ClientUser.archived_at.is_(None))
    resultado = paginar(q.order_by(ClientUser.full_name, ClientUser.id), pagina, "portal.clients")
    return resultado.mapear(lambda c: {
        "id": c.id,
        "project_id": c.project_id,
        "project_ids": c.get_project_ids(),
        "project_name": c.project.name if c.project else (c.projects[0].name if c.projects else None),
        "client_org_id": c.client_org_id,
        "full_name": c.full_name, "email": c.email,
        "job_title": c.job_title, "company": c.company,
        "phone": c.phone,
        "is_active": c.is_active,
        "archived_at": c.archived_at.isoformat() if c.archived_at else None,
        "can_approve_deliverables": c.can_approve_deliverables,
        "can_request_changes": c.can_request_changes,
        "can_view_budget": c.can_view_budget,
        "can_view_team": c.can_view_team,
        "last_login": str(c.last_login)[:16] if c.last_login else None,
        "created_at": str(c.created_at)[:10],
        "portal_url": "/portal",
    })


def generar_contrasena() -> str:
    """Contraseña inicial aleatoria (16 caracteres URL-safe, ~96 bits)."""
    import secrets
    return secrets.token_urlsafe(12)


# 23-11-2026: el correo de acceso sale de `textos_de_salida` (`portal.acceso.*`, 8 idiomas del portal).


def enviar_acceso(client: ClientUser, clave: str) -> bool:
    """Manda al cliente su acceso (23-11-2026, M10 del 04b).

    La contraseña solo viaja al buzón del titular: no se devuelve a la pantalla
    del equipo ni se registra. Devuelve si el correo salió (sin SMTP, False: el
    equipo puede reenviar el acceso cuando el correo esté configurado).
    """
    from html import escape
    from app.core.config import settings
    from app.services.notification_service import enviar_correo
    from app.services.formato_regional import idioma as idioma_por_defecto
    # Sin idioma del cliente: el de la empresa (DEFAULT_LANGUAGE), no "es" en duro.
    idioma = (getattr(client, "language", None) or idioma_por_defecto(org_id=getattr(client, "organization_id", None)))[:2]
    from app.services.textos_de_salida import texto
    asunto = texto("portal.acceso.asunto", idioma)
    url = f"{settings.FRONTEND_URL.rstrip('/')}/portal"
    html = texto("portal.acceso.cuerpo", idioma, nombre=escape(client.full_name or ""), url=escape(url),
                 email=escape(client.email or ""), contrasena=escape(clave))
    return enviar_correo(client.email, asunto, html).enviado


def reenviar_acceso(client_id: str, db: Session) -> dict:
    """Nueva contraseña generada y enviada al titular; la anterior deja de valer."""
    client = db.query(ClientUser).filter(ClientUser.id == client_id).first()
    if not client:
        raise ErrorConCodigo("cliente_no_encontrado")
    if client.archived_at is not None:
        raise ErrorConCodigo("portal_usuario_archivado")
    clave = generar_contrasena()
    client.hashed_password = hash_password(clave)
    client.must_change_password = True
    db.commit()
    return {"id": client.id, "email": client.email, "credenciales_enviadas": enviar_acceso(client, clave)}


def reenviar_acceso_y_auditar(client_id: str, db: Session, actor) -> dict:
    """Reenvía el acceso, deja la auditoría (sin la contraseña) y confirma."""
    from app.services.audit import audit_log
    resultado = reenviar_acceso(client_id, db)
    audit_log(db, actor, "UPDATE", "client_user", client_id, resultado.get("email"),
              metadata={"accion": "reenviar_acceso", "enviado": resultado.get("credenciales_enviadas")})
    db.commit()
    return resultado


def create_client(payload, db: Session, actor=None) -> dict:
    """Alta de un usuario del portal.

    Sin `password`, el servidor genera una y la manda al titular (cambio
    obligatorio). Con `password` (puesta a mano, 23-11-2026): pasa la política
    de la empresa, obliga a cambiarla si `must_change_password` y se manda por
    correo si `send_access`. La contraseña nunca vuelve en la respuesta ni va a
    la auditoría (`PORTAL_USER_CREATED`, si hay `actor`).
    """

    all_project_ids = list(dict.fromkeys([
        *(payload.project_ids or []),
        *([payload.project_id] if payload.project_id else [])
    ]))
    if not all_project_ids and not payload.client_org_id:
        raise ErrorConCodigo("portal_usuario_sin_alcance", detail="Debe especificar al menos un proyecto o una empresa cliente")
    # Revisión 2026-11: el tope de usuarios por cliente sólo lo aplicaba un
    # segundo camino de alta sin pantalla (/clients/{id}/portal-users, retirado).
    if payload.client_org_id:
        from app.models.clients import ClientPortalConfig
        cfg = db.query(ClientPortalConfig).filter(ClientPortalConfig.client_id == payload.client_org_id).first()
        if cfg and cfg.max_portal_users:
            activos = db.query(ClientUser).filter(ClientUser.client_org_id == payload.client_org_id,
                                                  ClientUser.is_active == True).count()  # noqa: E712
            if activos >= cfg.max_portal_users:
                raise ErrorConCodigo("portal_limite_usuarios", max=cfg.max_portal_users)
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
    organizacion = organizacion or (db.info or {}).get("organization_id") or getattr(actor, "organization_id", None)
    # Migración 208: el correo es único POR EMPRESA (sin distinguir mayúsculas);
    # el mismo correo en otra empresa es otra cuenta.
    from sqlalchemy import func as _func
    existente = db.query(ClientUser).filter(_func.lower(ClientUser.email) == str(payload.email).strip().lower(),
                                            ClientUser.organization_id == organizacion).first()
    if existente is not None and existente.archived_at is not None:
        raise ErrorConCodigo("portal_usuario_email_archivado")
    if existente is not None:
        raise ErrorConCodigo("email_ya_registrado", detail="Ya existe un usuario de portal con ese email")
    manual = bool(payload.password)
    if manual:
        from app.services.client_portal_service.usuarios import validar_alta_con_contrasena
        validar_alta_con_contrasena(db, email=payload.email, full_name=payload.full_name,
                                    organization_id=organizacion, clave=payload.password)
    clave_generada = None if manual else generar_contrasena()
    # Contraseña a mano: obliga a cambiarla solo si se pide (la pantalla lo marca
    # por defecto; la API sin el campo, como antes). La generada, siempre.
    obligar = bool(payload.must_change_password) if manual else True
    enviar_manual = manual and bool(payload.send_access)
    create_data = {k: v for k, v in payload.model_dump().items()
                   if k not in ("password", "company", "project_ids", "project_id", "organization_id",
                                "must_change_password", "send_access")}
    client = ClientUser(
        **create_data,
        organization_id=organizacion,
        project_id=payload.project_id or (all_project_ids[0] if all_project_ids else None),
        company=company,
        hashed_password=hash_password(payload.password or clave_generada),
        # La contrasena generada solo la conoce el sistema y el buzon: se cambia al entrar.
        must_change_password=obligar,
        avatar_initials=payload.full_name[:2].upper(),
    )
    db.add(client)
    db.flush()
    if all_project_ids:
        for pid in all_project_ids:
            proj = db.query(ProjectModel).filter(ProjectModel.id == pid).first()
            if proj and proj not in client.projects:
                client.projects.append(proj)
    # 18-11-2026: el usuario del portal es una persona del cliente: existe como contacto suyo.
    from app.services.client_service import vincular_usuario_del_portal
    vincular_usuario_del_portal(db, client)
    db.commit()
    db.refresh(client)
    # Con contraseña generada, se envía al titular y no vuelve en la respuesta;
    # la puesta a mano, solo si se pidió.
    if clave_generada:
        enviadas = enviar_acceso(client, clave_generada)
    elif enviar_manual:
        enviadas = enviar_acceso(client, payload.password)
    else:
        enviadas = None
    if actor is not None:
        from app.services.seguridad_de_cuentas.auditoria import auditar
        auditar(db, actor, "PORTAL_USER_CREATED", client, org_id=client.organization_id, recurso="client_user",
                datos={"password_manual": manual, "must_change_password": obligar,
                       "send_requested": enviar_manual or not manual, "sent": bool(enviadas)})
        db.commit()
    return {
        "id": client.id,
        "email": client.email,
        "project_ids": client.get_project_ids(),
        "portal_url": "/portal",
        "credenciales_enviadas": enviadas,
        "message": f"Usuario creado. Puede acceder en /portal con {client.email}."
    }


def update_client(client_id: str, payload: dict, db: Session) -> dict:

    client = db.query(ClientUser).filter(ClientUser.id == client_id).first()
    if not client:
        raise ErrorConCodigo("cliente_no_encontrado")
    allowed = ["full_name", "email", "job_title", "company", "phone", "is_active", "project_id",
               "can_approve_deliverables", "can_request_changes", "can_view_budget", "can_view_team", "language"]
    project_ids_payload = None
    if "project_ids" in payload:
        project_ids_payload = [pid for pid in (payload.get("project_ids") or []) if pid]
    elif "project_id" in payload:
        project_ids_payload = [payload["project_id"]] if payload.get("project_id") else []
    # 23-11-2026 (portal_usuarios): la contraseña ya no se cambia por aquí (sin
    # política, sin cerrar sesiones y sin auditoría): «Establecer contraseña».
    if "password" in payload:
        raise ErrorConCodigo("portal_usuario_contrasena_solo_con_su_accion")
    # Un archivado no se reactiva con «Reactivar»: se restaura (queda auditado).
    if client.archived_at is not None and payload.get("is_active"):
        raise ErrorConCodigo("portal_usuario_archivado")
    nuevo = str(payload.get("email") or "").strip().lower() if "email" in payload else ""
    if nuevo and nuevo != (client.email or "").lower():
        from sqlalchemy import func as _func
        otro = db.query(ClientUser.id).filter(_func.lower(ClientUser.email) == nuevo,
                                              ClientUser.organization_id == client.organization_id,
                                              ClientUser.id != client.id).first()
        if otro:   # migración 208: único por empresa
            raise ErrorConCodigo("email_ya_registrado", detail="Ya existe un usuario de portal con ese email")
    for k, v in payload.items():
        if k in allowed and k != "project_id":
            setattr(client, k, v)
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
    if any(k in payload for k in ("full_name", "email", "phone", "job_title")):
        # Su contacto lleva los mismos datos (desactivarlo no toca el contacto).
        from app.services.client_service import vincular_usuario_del_portal
        vincular_usuario_del_portal(db, client)
    db.commit()
    return {"ok": True, "project_ids": client.get_project_ids()}


# 23-11-2026: `delete_client` (borrado siempre, con SET NULL en el historial) lo
# sustituye `usuarios.eliminar_o_archivar`: sin historial borra, con historial archiva.


# ── Auth ──────────────────────────────────────────────────────────────────────

def get_active_client_by_id(db: Session, client_id: str) -> Optional[ClientUser]:
    """Return an active ClientUser by id, or None if not found / inactive."""
    return db.query(ClientUser).filter(ClientUser.id == client_id, ClientUser.is_active == True).first()


def cuentas_del_portal(db: Session, correo: str, empresa: Optional[str] = None) -> list:
    """Usuarios activos del portal con ese correo (sin distinguir mayúsculas), de
    `empresa` si se sabe. Migración 208: el correo es único POR EMPRESA."""
    from sqlalchemy import func
    q = db.query(ClientUser).filter(func.lower(ClientUser.email) == (correo or "").strip().lower(),
                                    ClientUser.is_active == True)  # noqa: E712
    if empresa:
        q = q.filter(ClientUser.organization_id == empresa)
    return q.all()


def _empresas_activas(db: Session, ids) -> dict:
    from app.models.mfa import Organization
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {o.id: o.name for o in db.query(Organization).filter(Organization.id.in_(ids),
                                                              Organization.is_active == True).all()}  # noqa: E712


def client_login(email: str, password: str, db: Session, *, organization_id: Optional[str] = None,
                 codigo: Optional[str] = None, host: Optional[str] = None, origen=None) -> dict:
    """Login del portal. Migración 208 (24-11-2026): el correo es único por empresa.

    La empresa sale, por este orden, de la elegida (`organization_id`, segunda
    vuelta), del código de acceso del portal o del host
    (`empresa_por_codigo_o_host`). Si no sale y la contraseña vale en VARIAS
    empresas, no hay token: devuelve `{"choose_organization": True,
    "organizations": [{id, name}]}` solo con las empresas en las que la
    contraseña vale (las demás no se revelan) y el portal vuelve a llamar con la
    elegida. Elegir empresa (o resolverla por código u host habiendo varias
    cuentas con ese correo) queda en la auditoría: `PORTAL_LOGIN_EMPRESA_ELEGIDA`.
    """
    from app.services.client_portal_service.autenticacion import empresa_por_codigo_o_host
    empresa, via = empresa_por_codigo_o_host(db, codigo, host)
    todas = cuentas_del_portal(db, email)
    cuentas = [c for c in todas if not empresa or c.organization_id == empresa]
    validas = [c for c in cuentas if c.hashed_password and verify_password(password, c.hashed_password)]
    if not validas:
        raise ErrorConCodigo("credenciales_incorrectas")
    n_ofrecidas = 1
    if len(validas) > 1 or organization_id:
        # Con varias, solo las empresas activas (una desactivada no se ofrece).
        activas = _empresas_activas(db, [c.organization_id for c in validas])
        candidatas = [c for c in validas if c.organization_id in activas]
        n_ofrecidas = len(candidatas)
        if organization_id:
            elegida = [c for c in candidatas if c.organization_id == organization_id]
            if not elegida:
                raise ErrorConCodigo("credenciales_incorrectas")
            validas, via = elegida, "eleccion"
        elif len(candidatas) > 1:
            return {"choose_organization": True,
                    "organizations": sorted(({"id": c.organization_id, "name": activas[c.organization_id]}
                                             for c in candidatas), key=lambda e: (e["name"] or "").lower())}
        elif candidatas:
            validas = candidatas
    client = validas[0]
    # Revision multitenant 2026-11b: el login del portal emitia token aunque la
    # empresa estuviera desactivada (luego cada llamada daba 403).
    from app.db.session import exigir_organizacion_activa
    exigir_organizacion_activa(db, client.organization_id)
    client.last_login = datetime.now(timezone.utc)
    if via == "eleccion" or (via and len(todas) > 1):
        from app.services.seguridad_de_cuentas.auditoria import auditar
        auditar(db, None, "PORTAL_LOGIN_EMPRESA_ELEGIDA", client, org_id=client.organization_id, origen=origen,
                recurso="client_user", datos={"via": via, "cuentas_con_ese_correo": len(todas),
                                              "empresas_ofrecidas": n_ofrecidas})
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
            "language": idioma_de_la_interfaz_del_portal(db, client),
            "project_ids": project_ids,
            "projects": projects,
            # 23-11-2026: el portal lleva a la pantalla de cambio de contrasena.
            "must_change_password": bool(client.must_change_password),
        }
    }


def idioma_de_la_interfaz_del_portal(db: Session, client) -> Optional[str]:
    """Idioma con el que se abre el portal (incidencia 5 de usuarios, 23-11-2026).

    Preferencia del usuario del portal > idioma del portal de su empresa
    cliente (`ClientPortalConfig.default_language`) > idioma que eligió la
    empresa proveedora > `None`: el portal usa entonces el del navegador si es
    uno de los 8 y, si no, inglés (`IDIOMA_POR_DEFECTO` del portal). Antes el
    alta guardaba el `DEFAULT_LANGUAGE` del entorno (castellano) como si fuera
    la preferencia del usuario.
    """
    if getattr(client, "language", None):
        return client.language
    org_cliente = getattr(client, "client_org_id", None)
    if org_cliente:
        from app.models.clients import ClientPortalConfig
        cfg = db.query(ClientPortalConfig.default_language).filter(
            ClientPortalConfig.client_id == org_cliente).first()
        if cfg and cfg[0]:
            return cfg[0]
    from app.services.settings_service.por_empresa import idioma_elegido_de_empresa
    return idioma_elegido_de_empresa(db, getattr(client, "organization_id", None))


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
        "language": idioma_de_la_interfaz_del_portal(db, current_client),
        "must_change_password": bool(getattr(current_client, "must_change_password", False)),
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
        raise ErrorConCodigo("perfil_no_editable")
    BLOCKED = {"email", "hashed_password", "current_password", "can_approve_deliverables",
               "can_request_changes", "can_view_budget", "can_view_team",
               "project_id", "client_org_id", "is_active", "id"}

    for k, v in payload.items():
        if k in BLOCKED:
            continue
        if k == "password":
            # El cambio obligatorio (contrasena generada) se permite siempre.
            if not allow_pwd and not current_client.must_change_password:
                raise ErrorConCodigo("cambio_contrasena_desactivado")
            # Auditoria 2026-11: sin la actual, una sesion robada o un equipo
            # desbloqueado bastaba para quedarse la cuenta.
            actual = payload.get("current_password")
            if not actual or not verify_password(str(actual), current_client.hashed_password or ""):
                raise ErrorConCodigo("contrasena_actual_incorrecta")
            # 23-11-2026: la política de contraseñas de la empresa también en el
            # portal (docs/seguridad/politicas_de_cuenta.md §3).
            from app.services.seguridad_de_cuentas.contrasenas import validar_del_portal
            validar_del_portal(db, current_client, str(v), min_password_length)
            if verify_password(str(v), current_client.hashed_password or ""):
                raise ErrorConCodigo("portal_contrasena_igual_a_la_anterior")
            current_client.hashed_password = hash_password(str(v))
            current_client.must_change_password = False
        elif k in SAFE_FIELDS:
            setattr(current_client, k, v)
    if any(k in payload for k in ("full_name", "phone", "job_title")):
        from app.services.client_service import vincular_usuario_del_portal
        vincular_usuario_del_portal(db, current_client)

    db.commit()
    db.refresh(current_client)
    return {
        "id": current_client.id,
        "full_name": current_client.full_name,
        "email": current_client.email,
        "phone": current_client.phone,
        "job_title": current_client.job_title,
        "language": current_client.language,
        "must_change_password": bool(current_client.must_change_password),
        "message": "Perfil actualizado correctamente",
    }
