"""SSO: rol y organizacion del usuario, URL de descubrimiento, proveedores, salud SAML y alta del usuario federado.

Parte de `app.services.auth_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
import logging
import ipaddress
import socket
import uuid
from typing import Optional
from urllib.parse import urlparse
from sqlalchemy.orm import Session
from app.models.mfa import Organization
from app.models.user import User, UserRole, UserStatus
from app.models.enterprise import SSOConfig
from app.core.errores import ErrorDeDominio

from app.services.auth_service._comun import logger


# ── SSO helpers ───────────────────────────────────────────────────────────────

def resolve_sso_role(default_role: str):
    try:
        return UserRole(default_role)
    # intentional: best-effort fallback, log noise outweighs diagnostic value
    except ValueError:
        return UserRole.employee


def resolve_sso_organization_id(db: Session, config, email: str) -> str:
    if config.organization_id:
        org = db.query(Organization).filter(
            Organization.id == config.organization_id,
            Organization.is_active == True,
        ).first()
        if org:
            return org.id
        raise ErrorDeDominio(409, "La organización asignada al proveedor SSO no existe o está inactiva")

    raise ErrorDeDominio(
        409,
        "La configuración SSO no tiene organization_id asignado; no se pueden autocrear usuarios sin tenant",
    )


def validate_https_discovery_url(discovery_url: str) -> str:
    """Validate OIDC discovery URL to avoid SSRF to private/internal networks."""
    parsed = urlparse(discovery_url or "")
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise ErrorDeDominio(400, "oidc_discovery_url debe ser una URL HTTPS válida")

    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        raise ErrorDeDominio(400, "oidc_discovery_url debe incluir hostname")

    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        raise ErrorDeDominio(400, "oidc_discovery_url no puede apuntar a hosts locales")

    try:
        ip_obj = ipaddress.ip_address(hostname)
    # intentional: best-effort fallback, log noise outweighs diagnostic value
    except ValueError:
        ip_obj = None

    if ip_obj is not None and (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    ):
        raise ErrorDeDominio(400, "oidc_discovery_url apunta a una red no permitida")

    try:
        addrinfo = socket.getaddrinfo(hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except Exception:
        logger.warning("Error resolviendo getaddrinfo para hostname=%s puerto=%s", hostname, parsed.port or 443, exc_info=True)
        addrinfo = []

    for entry in addrinfo:
        ip_raw = entry[4][0]
        resolved_ip = ipaddress.ip_address(ip_raw)
        if (
            resolved_ip.is_private
            or resolved_ip.is_loopback
            or resolved_ip.is_link_local
            or resolved_ip.is_multicast
            or resolved_ip.is_reserved
            or resolved_ip.is_unspecified
        ):
            raise ErrorDeDominio(400, "oidc_discovery_url resuelve a una red no permitida")

    return discovery_url


# ── SSO helpers ───────────────────────────────────────────────────────────────

def _dominio_de(valor: Optional[str]) -> str:
    """`ana@acme.com` o `acme.com` -> `acme.com` (minusculas); vacio si no hay."""
    return (valor or "").strip().rsplit("@", 1)[-1].strip().lower().lstrip("@")


def _ofrece_el_dominio(config, dominio: str) -> bool:
    """Si el proveedor sirve para correos de `dominio` en la pantalla de login.

    Segunda auditoria 2026-11 (#11): el de una empresa tiene que listar el
    dominio en `allowed_domains`; uno global (sin empresa) y sin restriccion de
    dominios no es de nadie y se ofrece igual.
    """
    dominios = [d.strip().lower().lstrip("@") for d in (config.allowed_domains or "").split(",") if d.strip()]
    if not dominios:
        return config.organization_id is None
    return dominio in dominios


def get_active_sso_providers(db: Session, request=None, dominio: Optional[str] = None):
    """Return list of active SSO provider dicts.

    En modo `email_selector` (con `request`) solo los del dominio de `dominio`
    (correo o dominio); sin dominio, ninguno.
    """
    # Auditoria 2026-11: leia `c.name`, que no existia, y la excepcion dejaba
    # el login sin botones. SAML no esta implementado: no se ofrece.
    from sqlalchemy import or_, select
    from app.models.mfa import Organization
    consulta = db.query(SSOConfig).filter(
        SSOConfig.is_active == True, SSOConfig.is_deleted == False, SSOConfig.provider != "saml",
        # Revision multitenant 2026-11b: ni los de empresas desactivadas…
        or_(SSOConfig.organization_id.is_(None),
            SSOConfig.organization_id.in_(select(Organization.id).where(Organization.is_active == True))))  # noqa: E712
    if request is not None:
        # …ni, en modo subdominio, los de otras empresas: el host ya dice cual.
        from app.services import entrada_service as _entrada
        if _entrada.modo() == "subdomain":
            del_host = _entrada.organizacion_por_host(db, request)
            if del_host is not None:
                consulta = consulta.filter(or_(SSOConfig.organization_id.is_(None),
                                               SSOConfig.organization_id == del_host.id))
    configs = consulta.all()
    if request is not None:
        from app.services import entrada_service as _entrada
        if _entrada.modo() == "email_selector":
            dominio = _dominio_de(dominio)
            configs = [c for c in configs if dominio and _ofrece_el_dominio(c, dominio)]
    return [
        {
            "id":       c.id,
            "provider": c.provider,
            "name":     c.name or str(getattr(c.provider, "value", c.provider)).replace("_", " ").title(),
            "icon":     {"azure_ad": "🔵", "okta": "🟠", "google": "🔴", "saml": "🔐", "oidc": "🔑"}.get(c.provider, "🔑"),
        }
        for c in configs
    ]


def get_saml_health(db: Session):
    """Return SAML config health list."""
    configs = db.query(SSOConfig).filter(SSOConfig.provider == "saml").all()
    out = []
    for c in configs:
        issues = []
        if not c.saml_entity_id:
            issues.append("missing_entity_id")
        if not c.saml_sso_url:
            issues.append("missing_sso_url")
        if not c.saml_certificate:
            issues.append("missing_certificate")
        cert = (c.saml_certificate or "").strip()
        if cert and "BEGIN CERTIFICATE" not in cert:
            issues.append("certificate_not_pem")
        # allowed_domains es texto separado por comas: recorrerlo tal cual
        # iteraba letra a letra y daba cada una por dominio inválido.
        for domain in (c.allowed_domains or "").split(","):
            domain = domain.strip()
            if domain and "." not in domain:
                issues.append(f"invalid_domain:{domain}")
        out.append({
            "id":        c.id,
            # SSOConfig no tiene nombre; lo que la identifica es el proveedor.
            "name":      getattr(c.provider, "value", c.provider),
            "is_active": c.is_active,
            "issues":    issues,
            "status":    "ok" if not issues else "warning",
        })
    return out


def get_sso_config_or_404(db: Session, config_id: str):
    """Return an active SSOConfig or raise 404."""
    config = db.query(SSOConfig).filter(
        SSOConfig.id == config_id, SSOConfig.is_active == True
    ).first()
    if not config:
        raise ErrorDeDominio(404, "SSO no encontrado")
    return config


def rol_desde_grupos(config, claims: dict):
    """Rol por los grupos del IdP (`role_mapping` {grupo: rol}) o None si no casa.

    Si varios grupos casan, gana el rol con mas privilegios. Portado de
    contecintelligence (`security/sso.py: map_role`), adaptado a `UserRole`.
    """
    import json as _json
    try:
        mapa = _json.loads(config.role_mapping) if config.role_mapping else {}
    except ValueError:
        mapa = {}
    if not mapa:
        return None
    grupos = claims.get(config.groups_claim or "groups") or []
    if isinstance(grupos, str):
        grupos = [grupos]
    orden = ["admin", "pm", "hr", "team_lead", "employee", "subcontractor"]
    candidatos = [mapa[g] for g in grupos if g in mapa and mapa[g] in orden]
    return UserRole(min(candidatos, key=orden.index)) if candidatos else None


def _dominio_permitido(config, email: str) -> bool:
    dominios = [d.strip().lower().lstrip("@") for d in (config.allowed_domains or "").split(",") if d.strip()]
    return not dominios or email.rsplit("@", 1)[-1].lower() in dominios


def create_or_update_sso_user(db: Session, config, email: str, name, claims: dict):
    """Busca o crea al usuario del SSO. Returns User.

    Auditoria 2026-11 (comparado con contecintelligence):
      - la busqueda se acota a la organizacion del proveedor: un correo de otra
        organizacion no se puede usar para entrar en ella (409);
      - `allowed_domains` se aplica; la organizacion tiene que estar activa
        tambien para usuarios ya existentes;
      - el limite de usuarios de la organizacion se respeta al autocrear;
      - el rol se sincroniza en cada inicio de sesion si hay mapeo de grupos.
    """
    # Organization ya viene importado arriba (app.models.mfa).
    if not _dominio_permitido(config, email):
        raise ErrorDeDominio(403, "El dominio de este correo no está permitido en este proveedor SSO")
    email = email.strip().lower()
    from sqlalchemy import func as _func
    q = db.query(User).filter(_func.lower(User.email) == email)
    user = q.first()
    if user is not None and config.organization_id and user.organization_id != config.organization_id:
        raise ErrorDeDominio(409, "Este correo pertenece a otra organización")
    rol_mapeado = rol_desde_grupos(config, claims)
    if not user:
        if not config.auto_create_users:
            raise ErrorDeDominio(403, "El proveedor SSO no permite autocrear usuarios")
        org_id = resolve_sso_organization_id(db, config, email)
        org = db.query(Organization).filter(Organization.id == org_id).first()
        if org is not None:
            from app.services.organizations_service import check_org_user_limit
            check_org_user_limit(org, db)
        user = User(
            id=str(uuid.uuid4()),
            email=email,
            full_name=name or email.split("@")[0],
            username=email.split("@")[0],
            role=rol_mapeado or resolve_sso_role(config.default_role),
            status=UserStatus.active,
            is_active=True,
            organization_id=org_id,
            sso_provider=getattr(config.provider, "value", config.provider),
            sso_subject=claims.get("sub"),
        )
        db.add(user)
        db.flush()
        try:
            from app.models.user import UserOrganizationMembership
            db.add(UserOrganizationMembership(user_id=user.id, organization_id=org_id))
        except Exception:
            logger.debug("sin pertenencia para el usuario SSO", exc_info=True)
        db.commit()
        db.refresh(user)
        return user
    if not user.is_active:
        raise ErrorDeDominio(403, "Usuario desactivado")
    # Auditoria 2026-11: el IdP lo controla el admin de una empresa; no puede
    # emitir la identidad del superadmin de la plataforma.
    if user.is_superadmin:
        raise ErrorDeDominio(403, "El superadministrador no puede entrar por SSO")
    # Patron nOAuth: si la cuenta ya esta ligada a un `sub`, otro `sub` con el
    # mismo email (p. ej. otro tenant de Azure) no entra.
    sub = claims.get("sub")
    if user.sso_subject and sub and user.sso_subject != sub:
        raise ErrorDeDominio(403, "Esta cuenta está vinculada a otra identidad del proveedor SSO")
    org = db.query(Organization).filter(Organization.id == user.organization_id).first()
    if org is not None and not org.is_active:
        raise ErrorDeDominio(403, "La organización de este usuario está desactivada")
    cambios = False
    if rol_mapeado is not None and user.role != rol_mapeado and not user.is_superadmin:
        user.role = rol_mapeado
        cambios = True
    if not user.sso_provider:
        user.sso_provider = getattr(config.provider, "value", config.provider)
        user.sso_subject = user.sso_subject or claims.get("sub")
        cambios = True
    if cambios:
        db.commit()
    return user


def sso_timeout_http() -> float:
    """Tiempo de espera de las llamadas al proveedor SSO (ajuste global, sin tenant)."""
    from app.core.config import settings as _cfg
    try:
        from app.db.session import SessionLocal
        from app.services.settings_service import get_runtime_float
        with SessionLocal() as _db:
            v = get_runtime_float(_db, "SSO_HTTP_TIMEOUT_SECONDS")
        return float(v) if v else float(_cfg.SSO_HTTP_TIMEOUT_SECONDS)
    except Exception:
        logging.getLogger(__name__).debug("sso_timeout_http: excepcion ignorada", exc_info=True)
        return float(_cfg.SSO_HTTP_TIMEOUT_SECONDS)


def sso_holgura_de_reloj() -> int:
    """Segundos de holgura de reloj al validar el id_token (ajuste global, sin tenant).

    Revisión 2026-11 (medido: estaba en Admin y se leía solo de `.env`).
    """
    from app.core.config import settings as _cfg
    try:
        from app.db.session import SessionLocal
        from app.services.settings_service import get_runtime_int
        with SessionLocal() as _db:
            v = get_runtime_int(_db, "SSO_CLOCK_SKEW_SECONDS")
        return int(v) if v is not None else int(_cfg.SSO_CLOCK_SKEW_SECONDS)
    except Exception:
        logging.getLogger(__name__).debug("sso_holgura_de_reloj: excepcion ignorada", exc_info=True)
        return int(_cfg.SSO_CLOCK_SKEW_SECONDS)
