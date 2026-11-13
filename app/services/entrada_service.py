"""En qué empresa (tenant) entra cada persona, y con qué empresa sigue cada petición.

Revisión multitenant 2026-11. Hasta aquí la empresa salía siempre de
`users.organization_id`: quien pertenecía a varias (`user_organization_memberships`)
no podía entrar en las otras ni cambiar de una a otra.

El modo lo elige cada despliegue en `.env` (`TENANT_ENTRY_MODE`); una máquina
usa uno solo:

- `email_selector` (por defecto): correo y contraseña. Con una empresa se entra
  directo; con varias, la respuesta pide elegir y trae un token corto que solo
  sirve para eso (como contecpos). Luego se puede cambiar desde la cabecera.
- `subdomain`: el host decide (`<slug>.TENANT_ROOT_DOMAIN` o el dominio propio de
  la empresa). Quien no es miembro de esa empresa no entra, y un token de otra
  empresa no vale en ese host.
- `org_field`: el login pide el código de la empresa (como contecrm).

La empresa elegida viaja en el claim `org` de los tokens y se vuelve a validar
en cada petición: pertenencia vigente y empresa activa.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.mfa import Organization
from app.models.user import UserOrganizationMembership
from app.core.errores import ErrorDeDominio

MODOS = ("email_selector", "subdomain", "org_field")
_MENSAJE_CREDENCIALES = "Credenciales incorrectas"


def modo() -> str:
    valor = (settings.TENANT_ENTRY_MODE or "email_selector").strip().lower()
    return valor if valor in MODOS else "email_selector"


class EleccionPendiente(Exception):
    """El usuario pertenece a varias empresas y tiene que elegir una."""

    def __init__(self, organizaciones: list):
        super().__init__("elegir organizacion")
        self.organizaciones = organizaciones


def _de_ficha(user):
    """La empresa de la ficha del usuario, aunque en esta peticion este en otra."""
    return getattr(user, "_organizacion_de_ficha", user.organization_id)


def organizaciones_del_usuario(db: Session, user) -> list:
    """Empresas ACTIVAS a las que pertenece: la de su ficha y las de sus pertenencias."""
    from app.db.session import sin_filtro_de_tenant
    ids = {_de_ficha(user)} if _de_ficha(user) else set()
    # Segunda auditoria 2026-11 (#26): en una sesion ya abierta el filtro de
    # tenant dejaba ver solo la pertenencia de la empresa activa, y cambiar a
    # otra empresa de la que se es miembro daba 401. Son las del propio usuario.
    with sin_filtro_de_tenant(db):
        ids |= {o for (o,) in db.query(UserOrganizationMembership.organization_id).filter(
            UserOrganizationMembership.user_id == user.id).all() if o}
    if not ids:
        return []
    return (db.query(Organization).filter(Organization.id.in_(ids), Organization.is_active == True)  # noqa: E712
            .order_by(Organization.name).all())


def pertenece(db: Session, user, organization_id: str) -> bool:
    if _de_ficha(user) == organization_id:
        return True
    return db.query(UserOrganizationMembership.id).filter(
        UserOrganizationMembership.user_id == user.id,
        UserOrganizationMembership.organization_id == organization_id,
    ).first() is not None


def organizacion_por_host(db: Session, request) -> Optional[Organization]:
    """La empresa del host: su dominio propio o `<slug>.TENANT_ROOT_DOMAIN`."""
    from app.core.network import extract_host
    host = extract_host(request)
    if not host:
        return None
    org = db.query(Organization).filter(Organization.domain == host).first()
    if org:
        return org
    raiz = (settings.TENANT_ROOT_DOMAIN or "").strip().lower().lstrip(".")
    if raiz and host.endswith("." + raiz):
        slug = host[: -len(raiz) - 1]
        if slug and "." not in slug:
            return db.query(Organization).filter(Organization.slug == slug).first()
    return None


def organizacion_por_codigo(db: Session, codigo: Optional[str]) -> Optional[Organization]:
    codigo = (codigo or "").strip()
    if not codigo:
        return None
    return db.query(Organization).filter(
        or_(Organization.slug == codigo.lower(), Organization.id == codigo)).first()


def decidir(db: Session, user, request, *, codigo: Optional[str] = None,
            elegida: Optional[str] = None) -> Optional[str]:
    """La empresa con la que entra `user`, o `EleccionPendiente` si tiene que elegir.

    Un superadmin de la plataforma no entra en ninguna (ve todas). Los rechazos
    por empresa responden lo mismo que una contraseña mala: no se revela a qué
    empresas pertenece nadie.
    """
    if getattr(user, "is_superadmin", False):
        return None
    activas = organizaciones_del_usuario(db, user)
    ids = {o.id for o in activas}
    if not activas:
        if _de_ficha(user) and not pertenece_a_activa(db, _de_ficha(user)):
            raise ErrorDeDominio(403, "La organización está desactivada")
        raise ErrorDeDominio(403, "No perteneces a ninguna organización activa")

    fijada = None
    if modo() == "subdomain":
        org = organizacion_por_host(db, request)
        fijada = org.id if org else None
    elif modo() == "org_field":
        org = organizacion_por_codigo(db, codigo)
        if org is None:
            raise ErrorDeDominio(401, _MENSAJE_CREDENCIALES)
        fijada = org.id
    if fijada is not None:
        if fijada not in ids:
            raise ErrorDeDominio(401, _MENSAJE_CREDENCIALES)
        return fijada

    if elegida:
        if elegida not in ids:
            raise ErrorDeDominio(401, _MENSAJE_CREDENCIALES)
        return elegida
    if len(activas) == 1:
        return activas[0].id
    raise EleccionPendiente(activas)


def pertenece_a_activa(db: Session, organization_id: str) -> bool:
    org = db.get(Organization, organization_id)
    return bool(org and org.is_active)


def organizacion_desactivada(db: Session, organization_id: Optional[str]) -> bool:
    """True si la fila es de una organizacion que existe y esta desactivada.

    Segunda auditoria 2026-11 (#10): los trabajos de fondo que recorren filas
    de todas las organizaciones (eventos de ticket, automatizaciones, BPMN)
    saltan las de una organizacion desactivada. Sin organizacion, no se salta.
    """
    if not organization_id:
        return False
    org = db.get(Organization, organization_id)
    return org is not None and not org.is_active


def resumen(org) -> dict:
    return {"id": org.id, "name": org.name, "slug": org.slug,
            "logo_url": org.logo_url, "primary_color": org.primary_color}


# ── Token de elección: prueba de que la contraseña ya se comprobó ────────────

def token_de_eleccion(user) -> str:
    from jose import jwt
    from app.core.security import ALGORITHM, get_jwt_signing_key
    minutos = int(settings.TENANT_SELECTION_TOKEN_MINUTES or 5)
    kid, key = get_jwt_signing_key()
    return jwt.encode({"sub": user.id, "type": "org_selection",
                       "exp": datetime.now(timezone.utc) + timedelta(minutes=minutos)},
                      key, algorithm=ALGORITHM, headers={"kid": kid})


def leer_token_de_eleccion(token: str) -> str:
    from app.core.security import decode_token
    datos = decode_token(token or "")
    if not datos or datos.get("type") != "org_selection" or not datos.get("sub"):
        raise ErrorDeDominio(401, "La elección de organización ha caducado: vuelve a entrar")
    return datos["sub"]


# ── En cada petición ─────────────────────────────────────────────────────────

def organizacion_de_la_peticion(db: Session, user, payload: dict, request) -> Optional[str]:
    """La empresa activa de esta petición, validada. Fija `user.organization_id`.

    Se fija en memoria con `set_committed_value`: el objeto no queda modificado
    y nunca se guarda, pero todo el código que lee `current_user.organization_id`
    ve la empresa activa sin tocarlo.
    """
    if getattr(user, "is_superadmin", False):
        return None
    org = payload.get("org") or user.organization_id
    if org != _de_ficha(user) and not pertenece(db, user, org):
        # Ya no pertenece a la empresa del token: la sesion vuelve a la de su
        # ficha (lo de siempre). El acceso a la retirada se pierde igual.
        org = _de_ficha(user)
    if modo() == "subdomain":
        del_host = organizacion_por_host(db, request)
        if del_host is not None and del_host.id != org:
            raise ErrorDeDominio(403, "Esta sesión es de otra organización")
    return _fijar_en_memoria(user, org)


def _fijar_en_memoria(user, org: Optional[str]) -> Optional[str]:
    if org != user.organization_id:
        from sqlalchemy.orm.attributes import set_committed_value
        user._organizacion_de_ficha = _de_ficha(user)
        set_committed_value(user, "organization_id", org)
    return org


def fijar_organizacion_activa(db: Session, user, org: Optional[str]) -> Optional[str]:
    """Fuera de HTTP (worker, WebSocket): `user` trabaja en `org` si sigue perteneciendo.

    Revision multitenant 2026-11b. Lo que se encola o se abre desde una
    peticion (el agente en segundo plano) recargaba al usuario y publicaba su
    empresa de FICHA: con pertenencias en varias, el trabajo pedido en B leia y
    escribia A. Devuelve la empresa fijada; si ya no pertenece, la de su ficha.
    """
    if getattr(user, "is_superadmin", False) or not org:
        return getattr(user, "organization_id", None)
    if org != _de_ficha(user) and not pertenece(db, user, org):
        return _de_ficha(user)
    return _fijar_en_memoria(user, org)


def emitir_tokens(user, org: Optional[str]) -> tuple[str, str, str]:
    """(acceso, refresco, jti) de una sesion de `user` en la empresa `org`."""
    from app.core.security import create_access_token, create_refresh_token
    extra = {"role": user.role, **({"org": org} if org else {})}
    acceso = create_access_token(subject=user.id, extra=extra)
    refresco, jti = create_refresh_token(subject=user.id, org=org)
    return acceso, refresco, jti


def confirmar(db: Session, user, request, org: Optional[str]) -> Optional[str]:
    """Valida una empresa ya decidida (la del reto MFA, la del proveedor SSO)."""
    if getattr(user, "is_superadmin", False) or not org:
        return None if getattr(user, "is_superadmin", False) else decidir(db, user, request)
    if not pertenece(db, user, org) or not pertenece_a_activa(db, org):
        raise ErrorDeDominio(403, "La organización está desactivada o ya no perteneces a ella")
    if modo() == "subdomain":
        del_host = organizacion_por_host(db, request)
        if del_host is not None and del_host.id != org:
            raise ErrorDeDominio(403, "Esta sesión es de otra organización")
    return org


# ── «Entrar como» (soporte de plataforma) ───────────────────────────────────
# Como contecrm: solo un superadmin, con motivo, sesion corta, auditada en la
# empresa visitada y sin tocar credenciales. La cookie de refresco sigue siendo
# la del superadmin: al salir (o al caducar) el refresco le devuelve su sesion.

RUTAS_VEDADAS_AL_SUPLANTAR = (
    "/api/v1/auth/change-password", "/api/v1/auth/mfa", "/api/v1/auth/passkey",
    "/api/v1/auth/switch-organization", "/api/v1/bookings/api-keys", "/api/v1/organizations",
    "/api/v1/enterprise/sso", "/api/v1/developer/apps",
)


def entrar_como(db: Session, superadmin, org: Organization, usuario, motivo: str) -> str:
    """Token de acceso corto de `usuario` en `org`, marcado con quien lo usa de verdad."""
    from app.core.security import create_access_token
    from app.services.audit import audit_log
    from app.services.settings_service import get_runtime_bool, get_runtime_int
    if not get_runtime_bool(db, "IMPERSONATION_ENABLED"):
        raise ErrorDeDominio(403, "«Entrar como» está desactivado en este despliegue")
    if not (motivo or "").strip():
        raise ErrorDeDominio(422, "Indica el motivo")
    if getattr(usuario, "is_superadmin", False) or not usuario.is_active:
        raise ErrorDeDominio(400, "No se puede entrar como ese usuario")
    if not pertenece(db, usuario, org.id) or not org.is_active:
        raise ErrorDeDominio(400, "El usuario no pertenece a esa empresa activa")
    minutos = int(get_runtime_int(db, "IMPERSONATION_MAX_MINUTES") or settings.IMPERSONATION_MAX_MINUTES)
    token = create_access_token(
        subject=usuario.id,
        extra={"role": usuario.role, "org": org.id, "actor_real": superadmin.id, "motivo": motivo.strip()[:200]},
        expires_delta=timedelta(minutes=minutos),
    )
    # Queda en la auditoria de la propia empresa: su admin ve quien entro y por que.
    db.info["organization_id"], db.info["is_superadmin"] = org.id, False
    audit_log(db, superadmin, "IMPERSONATION_START", "users", usuario.id,
              f"{superadmin.email} entra como {usuario.email}: {motivo.strip()[:200]}")
    db.commit()
    return token


def comprobar_suplantacion(payload: dict, request) -> Optional[str]:
    """El id de quien suplanta (o None). Corta las rutas vedadas durante la suplantacion."""
    actor = payload.get("actor_real")
    if not actor:
        return None
    ruta = request.url.path
    if any(ruta.startswith(r) for r in RUTAS_VEDADAS_AL_SUPLANTAR):
        raise ErrorDeDominio(403, "No disponible mientras se entra como otro usuario")
    request.state.suplantado_por = actor
    return actor
