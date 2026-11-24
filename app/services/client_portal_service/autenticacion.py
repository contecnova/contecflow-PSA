"""Credenciales del portal: contrasenas, tokens de cliente, enlaces publicos y configuracion de sesion.

Parte de `app.services.client_portal_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
import logging
import bcrypt
import jwt
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.settings import AppSetting


logger = logging.getLogger("contecflow.client_portal")

CLIENT_TOKEN_EXPIRE_HOURS = getattr(settings, "CLIENT_TOKEN_EXPIRE_HOURS", 72)
CLIENT_TOKEN_SECRET = settings.CLIENT_PORTAL_SECRET
PORTAL_SHARE_LINK_EXPIRE_HOURS = getattr(settings, "PORTAL_SHARE_LINK_EXPIRE_HOURS", 72)
ALGORITHM = getattr(settings, "JWT_ALGORITHM", "HS256")


# ── Auth helpers ──────────────────────────────────────────────────────────────

def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ── Cambio de contrasena obligatorio (23-11-2026) ────────────────────────────
# Con una contrasena generada por el sistema (alta o «Reenviar acceso»), el
# cliente solo puede leer su perfil, la marca y la sesion, y cambiarla; el resto
# de rutas del portal responden 403 `portal_cambio_de_contrasena_obligatorio`.

#: Rutas del portal que se pueden usar antes de cambiar la contrasena.
RUTAS_SIN_CAMBIO_DE_CONTRASENA = ("/portal/auth/me", "/portal/auth/session-config",
                                  "/portal/auth/logout", "/portal/branding")


def exigir_contrasena_cambiada(cliente, ruta: Optional[str] = None) -> None:
    """403 con codigo si el cliente debe cambiar la contrasena y la ruta no esta exenta."""
    if not getattr(cliente, "must_change_password", False):
        return
    if ruta and ruta.rstrip("/").endswith(RUTAS_SIN_CAMBIO_DE_CONTRASENA):
        return
    from app.core.codigos_de_error import error
    raise error(403, "portal_cambio_de_contrasena_obligatorio")


def create_client_token(client_id: str) -> str:
    import uuid

    expire = datetime.now(timezone.utc) + timedelta(hours=CLIENT_TOKEN_EXPIRE_HOURS)
    return jwt.encode(
        {"sub": client_id, "exp": expire, "type": "client", "jti": uuid.uuid4().hex},
        CLIENT_TOKEN_SECRET,
        algorithm=ALGORITHM,
    )


# ── Revocacion de tokens del portal (auditoria 2026-11 #23) ──────────────────
# El token del portal era un JWT de 72 h sin estado: cerrar sesion solo borraba
# la cookie (el token copiado seguia valiendo) y desactivar al contacto no lo
# paraba en `get_current_client` de `deps`. Ahora el token lleva `jti` y el
# cierre de sesion lo anota como revocado hasta que caduque (Redis, con
# respaldo en memoria de proceso, como el resto del estado efimero).

_PREFIJO_REVOCADO = "contecflow:portal:revoked:"
_revocados_en_memoria: dict[str, float] = {}


def revocar_token_de_cliente(token: Optional[str]) -> bool:
    """Anota el `jti` del token como revocado hasta su caducidad. True si lo anota."""
    import time

    if not token:
        return False
    try:
        payload = jwt.decode(token, CLIENT_TOKEN_SECRET, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return False
    jti = payload.get("jti")
    if not jti or payload.get("type") != "client":
        return False
    ttl = max(1, int(payload.get("exp", time.time() + 3600) - time.time()))
    from app.services.auth_service.estado_efimero import get_sso_redis
    r = get_sso_redis()
    if r is not None:
        try:
            r.setex(f"{_PREFIJO_REVOCADO}{jti}", ttl, "1")
            return True
        except Exception:
            logger.warning("No se pudo anotar en Redis el token de portal revocado", exc_info=True)
    ahora = time.time()
    for clave in [k for k, v in _revocados_en_memoria.items() if v < ahora]:
        _revocados_en_memoria.pop(clave, None)
    _revocados_en_memoria[jti] = ahora + ttl
    return True


def token_de_cliente_revocado(payload: dict) -> bool:
    """Si el token (ya decodificado) se revoco al cerrar sesion."""
    import time

    # 23-11-2026: restablecer o forzar el restablecimiento de la contrasena
    # cierra TODAS las sesiones del cliente (corte por cliente, sin esquema).
    from app.services.seguridad_de_cuentas.restablecimiento import sesion_del_portal_cortada
    if sesion_del_portal_cortada(payload):
        return True
    jti = (payload or {}).get("jti")
    if not jti:
        return False
    from app.services.auth_service.estado_efimero import get_sso_redis
    r = get_sso_redis()
    if r is not None:
        try:
            if r.exists(f"{_PREFIJO_REVOCADO}{jti}"):
                return True
        except Exception:
            logger.warning("No se pudo consultar en Redis el token de portal", exc_info=True)
    hasta = _revocados_en_memoria.get(jti)
    return bool(hasta and hasta > time.time())


def get_portal_session_config(db: Session) -> dict:
    """Return idle-timeout session policy for the client portal."""
    defaults = {
        "idle_timeout_enabled": "false",
        "idle_timeout_minutes": "30",
    }
    rows = db.query(AppSetting).filter(
        AppSetting.organization_id.is_(None),
        AppSetting.key.in_(list(defaults.keys())),
    ).all()
    values = {r.key: r.value for r in rows}

    enabled_raw = (values.get("idle_timeout_enabled") or defaults["idle_timeout_enabled"]).strip().lower()
    minutes_raw = values.get("idle_timeout_minutes") or defaults["idle_timeout_minutes"]
    try:
        minutes = max(1, int(minutes_raw))
    except Exception:
        logger.warning("Invalid idle_timeout_minutes=%r in portal settings; using default", minutes_raw, exc_info=True)
        minutes = int(defaults["idle_timeout_minutes"])

    return {
        "idle_timeout_enabled": enabled_raw in ("true", "1", "yes", "on"),
        "idle_timeout_minutes": minutes,
    }


# ── Empresa del portal sin preguntar (migración 208, 24-11-2026) ─────────────
# El correo del portal es único POR EMPRESA: la misma persona puede tener acceso
# en dos. Si la empresa sale del código de acceso del portal (`slug` de la
# empresa, `/portal?empresa=<código>`) o del host (dominio propio activo con el
# portal encendido, `OrgBranding.custom_domain`), el login y «¿Olvidaste tu
# contraseña?» la usan sin preguntar. Un código o host que no casa se ignora
# (se pregunta como sin ellos): no confirma ni niega que exista una empresa.

def empresa_por_codigo_o_host(db: Session, codigo: Optional[str] = None,
                              host: Optional[str] = None) -> tuple[Optional[str], Optional[str]]:
    """(id de empresa activa, vía: `codigo` | `host`) o (None, None)."""
    from app.models.mfa import Organization
    from app.db.session import sin_filtro_de_tenant
    codigo = (codigo or "").strip().lower()
    host = (host or "").strip().lower()
    with sin_filtro_de_tenant(db):
        if codigo:
            org = db.query(Organization.id).filter(Organization.slug == codigo,
                                                   Organization.is_active == True).first()  # noqa: E712
            if org:
                return org[0], "codigo"
        if host:
            from app.models.white_label import OrgBranding
            fila = db.query(OrgBranding.organization_id).join(
                Organization, Organization.id == OrgBranding.organization_id).filter(
                OrgBranding.custom_domain == host, OrgBranding.is_active == True,  # noqa: E712
                OrgBranding.enable_portal == True, Organization.is_active == True).first()  # noqa: E712
            if fila:
                return fila[0], "host"
    return None, None


def create_portal_share_token(project_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=PORTAL_SHARE_LINK_EXPIRE_HOURS)
    return jwt.encode(
        {"project_id": project_id, "exp": expire, "type": "portal_share"},
        CLIENT_TOKEN_SECRET,
        algorithm=ALGORITHM,
    )


def decode_portal_share_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, CLIENT_TOKEN_SECRET, algorithms=[ALGORITHM])
        if payload.get("type") != "portal_share":
            return None
        return payload.get("project_id")
    except jwt.PyJWTError:
        return None
