"""Credenciales del portal: contrasenas, tokens de cliente, enlaces publicos y configuracion de sesion.

Parte de `app.services.client_portal_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
import logging
import bcrypt
from jose import jwt, JWTError
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
    except JWTError:
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
    except JWTError:
        return None
