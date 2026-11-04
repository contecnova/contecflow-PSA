"""
auth_service.py — Business logic helpers extracted from auth router.
Covers: SSO state management, login rate-limiting, MFA challenge helpers,
password-reset token flow, cookie utilities, ephemeral tokens.
"""
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import base64
import ipaddress
import logging
import os
import smtplib
import socket
import threading
import time
import uuid
from typing import Optional
import json as _json
from urllib.parse import urlparse

from fastapi import HTTPException, Request, Response
from jose import jwt as jose_jwt, JWTError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.network import extract_client_ip
from app.core.security import (
    create_mfa_challenge_token,
    decode_token,
)
from app.db.session import is_postgres
from app.models.mfa import MFAChallenge, Organization, WebAuthnCredential
from app.models.sessions import UserSession
from app.models.user import User, UserRole, UserStatus
from app.services.key_management import get_jwt_signing_key, get_jwt_verification_keys
from app.services.security_observability import SecurityEventService
from app.models.enterprise import SSOConfig

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

SSO_STATE_TTL = 600  # seconds
SSO_KEY_PREFIX = "contecflow:sso_state:"

LOGIN_FAIL_PREFIX = "contecflow:login:fail:"
LOGIN_LOCK_PREFIX = "contecflow:login:lock:"

PASSWORD_RESET_TTL_SECONDS = 30 * 60
PASSWORD_RESET_REQUEST_WINDOW_SECONDS = 15 * 60
PASSWORD_RESET_REQUEST_MAX_PER_WINDOW = 5
PASSWORD_RESET_JTI_PREFIX = "contecflow:password_reset:jti:"  # noqa: S105

# In-memory fallback stores  ──────────────────────────────────────────────────
# (expiración, payload JSON) por estado. Antes sólo la expiración: no había
# dónde llevar el code_verifier de PKCE ni el nonce (auditoría 2026-08, P2-13).
_sso_states_fallback: dict[str, tuple[float, str]] = {}
_sso_states_lock = threading.Lock()
_redis_client = None
_redis_client_init = False
_login_fail_fallback: dict[str, dict[str, float]] = {}
_password_reset_req_fallback: dict[str, dict[str, float]] = {}
_password_reset_jti_fallback: dict[str, tuple[str, float]] = {}


# ── SOC helper ────────────────────────────────────────────────────────────────

def organizacion_exige_mfa(db, user) -> bool:
    """Devuelve si la organizacion de este usuario obliga a segundo factor.

    Auditoria 2026-08 (hallazgo 22): la consulta estaba en
    `routers/auth_core.py`. `Organization` es el unico modelo sin columna de
    tenant y `TenantSession` no lo filtra, asi que se busca por el id que trae
    el propio usuario — nunca por uno que venga del cliente.
    """
    from app.models.mfa import Organization

    org_id = getattr(user, "organization_id", None)
    if not org_id:
        return False
    org = db.query(Organization).filter(Organization.id == org_id).first()
    return bool(org and getattr(org, "require_mfa", False))


def guardar_secreto_de_mfa(db, user, secreto_cifrado: str) -> None:
    """Guarda el secreto TOTP del usuario y deja el MFA sin activar. No confirma.

    Auditoria 2026-08 (hallazgo 22): esto estaba en `routers/auth_mfa.py`. El
    `db.add()` sobre una fila que ya esta en la sesion no hace falta —SQLAlchemy
    la sigue por identidad— pero se conserva: cambiar el comportamiento de un
    camino de autenticacion en una tanda de reordenacion no toca.

    `mfa_enabled` se queda en `False` a proposito: el secreto existe pero el
    segundo factor no cuenta hasta que el usuario verifica un codigo.
    """
    user.mfa_secret = secreto_cifrado
    user.mfa_enabled = False
    db.add(user)


def soc_svc(db, user) -> "SecurityEventService | None":
    """Return a SecurityEventService if the user has an org; else None."""
    try:
        org_id = str(user.organization_id) if user and user.organization_id else None
        return SecurityEventService(db=db, org_id=org_id) if org_id else None
    except Exception:
        logger.warning("Error inicializando SecurityEventService para user=%s", getattr(user, "id", None), exc_info=True)
        return None


# ── Client IP ─────────────────────────────────────────────────────────────────

def client_ip(request: Request) -> str:
    return extract_client_ip(request)


# ── MFA challenge helpers ─────────────────────────────────────────────────────

def mfa_challenge_query(db: Session):
    q = db.query(MFAChallenge)
    if is_postgres():
        q = q.with_for_update()
    return q


def issue_mfa_challenge(db: Session, user: User) -> str:
    token, jti = create_mfa_challenge_token(user.id)
    db.query(MFAChallenge).filter(
        MFAChallenge.user_id == user.id,
        MFAChallenge.consumed_at.is_(None),
    ).update({"consumed_at": datetime.now(timezone.utc)})
    db.add(MFAChallenge(
        user_id=user.id,
        token_jti=jti,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    ))
    db.commit()
    return token


def read_mfa_challenge(db: Session, challenge_token: str) -> tuple[dict, MFAChallenge]:
    challenge_data = decode_token(challenge_token)
    if not challenge_data or challenge_data.get("type") != "mfa_challenge":
        raise HTTPException(401, "mfa_challenge_token inválido o expirado")

    challenge_jti = challenge_data.get("jti")
    user_id = challenge_data.get("sub")
    if not challenge_jti or not user_id:
        raise HTTPException(401, "mfa_challenge_token inválido")

    row = mfa_challenge_query(db).filter(
        MFAChallenge.user_id == user_id,
        MFAChallenge.token_jti == challenge_jti,
    ).first()
    expires_at = row.expires_at if row else None
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if not row or not expires_at or expires_at <= datetime.now(timezone.utc):
        raise HTTPException(401, "mfa_challenge_token inválido o expirado")
    if row.consumed_at is not None:
        raise HTTPException(401, "mfa_challenge_token ya utilizado")
    return challenge_data, row


def consume_mfa_challenge(row: MFAChallenge) -> None:
    row.consumed_at = datetime.now(timezone.utc)


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
        raise HTTPException(409, "La organización asignada al proveedor SSO no existe o está inactiva")

    raise HTTPException(
        409,
        "La configuración SSO no tiene organization_id asignado; no se pueden autocrear usuarios sin tenant",
    )


def validate_https_discovery_url(discovery_url: str) -> str:
    """Validate OIDC discovery URL to avoid SSRF to private/internal networks."""
    parsed = urlparse(discovery_url or "")
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise HTTPException(400, "oidc_discovery_url debe ser una URL HTTPS válida")

    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        raise HTTPException(400, "oidc_discovery_url debe incluir hostname")

    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        raise HTTPException(400, "oidc_discovery_url no puede apuntar a hosts locales")

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
        raise HTTPException(400, "oidc_discovery_url apunta a una red no permitida")

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
            raise HTTPException(400, "oidc_discovery_url resuelve a una red no permitida")

    return discovery_url


# ── Redis / SSO state store ───────────────────────────────────────────────────

# Cuándo reintentar conectar a Redis tras un fallo (segundos).
#
# Multi-worker note: cada worker mantiene su propio circuit breaker en
# memoria. Mientras dura el backoff, el rate limiter degrada a in-memory
# por-worker (un atacante que rota IPs alcanzaría el límite por worker
# independientemente). Mantenemos el backoff corto para que cualquier flap
# transitorio de Redis se recupere automáticamente antes de comprometer
# la protección global.
_REDIS_RECONNECT_BACKOFF = float(os.getenv("REDIS_RECONNECT_BACKOFF_SECONDS", "30"))
# Última vez que intentamos crear el cliente (epoch seconds).
_redis_last_attempt_at: float = 0.0


def force_redis_reconnect() -> None:
    """Forzar reintento de conexión a Redis en la siguiente llamada.

    Útil para administración (endpoint admin / repl) cuando se sabe que
    Redis ha vuelto y no se quiere esperar al backoff. Es thread-safe en
    cuanto a corrupciones — la próxima llamada a get_sso_redis() volverá a
    crear el cliente bajo el bloqueo implícito de Python (GIL).
    """
    global _redis_client, _redis_client_init, _redis_last_attempt_at
    _redis_client = None
    _redis_client_init = False
    _redis_last_attempt_at = 0.0


def get_sso_redis():
    """Return a shared Redis client if Redis is reachable, else None.

    Si Redis estaba caído al primer intento, antes el cliente se quedaba
    cacheado como None para siempre. Ahora reintentamos cada
    `_REDIS_RECONNECT_BACKOFF` segundos para recuperarnos automáticamente
    tras una caída transitoria.
    """
    global _redis_client, _redis_client_init, _redis_last_attempt_at
    now = time.time()
    # Si el cliente está disponible, lo devolvemos directamente.
    if _redis_client_init and _redis_client is not None:
        return _redis_client
    # Si la última inicialización falló y aún no ha pasado el backoff,
    # devolvemos None sin volver a intentarlo (evita tormenta de reintentos).
    if _redis_client_init and _redis_client is None:
        if (now - _redis_last_attempt_at) < _REDIS_RECONNECT_BACKOFF:
            return None
    _redis_client_init = True
    _redis_last_attempt_at = now
    try:
        import redis as _redis_module
        r = _redis_module.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=2,
            socket_timeout=2,
            decode_responses=True,
        )
        r.ping()
        _redis_client = r
        logger.info("SSO state store: using Redis (%s)", (settings.REDIS_URL or "").split("@")[-1])
    except Exception as _e:
        if settings.ENVIRONMENT == "development" and os.getenv("TESTING") != "1":
            logger.info(
                "SSO state store: Redis unavailable in development (%s). Using in-memory fallback "
                "(reintento en %ss).",
                _e, int(_REDIS_RECONNECT_BACKOFF),
            )
        else:
            logger.warning(
                "SSO state store: Redis unavailable (%s). Falling back to in-memory — "
                "NOT SAFE for multi-worker deployments. Reintentando en %ss. Set REDIS_URL to fix.",
                _e, int(_REDIS_RECONNECT_BACKOFF),
            )
        _redis_client = None
    return _redis_client


def register_sso_state(state_raw: str, payload: Optional[dict] = None) -> None:
    """Guarda el estado OIDC y, opcionalmente, datos ligados a esa transacción.

    Auditoría 2026-08 (P2-13): antes el valor almacenado era la cadena "1", así
    que no había dónde llevar el `code_verifier` de PKCE ni el `nonce`. Ahora se
    guarda un JSON con lo que el callback necesita para verificarlos. El estado
    sigue siendo de un solo uso.
    """
    valor = _json.dumps(payload or {})
    r = get_sso_redis()
    if r is not None:
        try:
            r.setex(f"{SSO_KEY_PREFIX}{state_raw}", SSO_STATE_TTL, valor)
            return
        except Exception as _e:
            _redis_circuit_break(f"SSO setex: {_e}")
    with _sso_states_lock:
        now = time.time()
        expired = [k for k, v in _sso_states_fallback.items() if v[0] < now]
        for k in expired:
            del _sso_states_fallback[k]
        _sso_states_fallback[state_raw] = (now + SSO_STATE_TTL, valor)


def consume_sso_state(state_raw: str) -> bool:
    """True si el estado existía y no había expirado. Lo elimina (un solo uso)."""
    return consume_sso_state_payload(state_raw) is not None


def consume_sso_state_payload(state_raw: str) -> Optional[dict]:
    """Consume el estado y devuelve su payload, o None si no era válido.

    Atómico frente a replay: el estado se borra al leerlo, así que un segundo
    intento con el mismo `state` no encuentra nada.
    """
    r = get_sso_redis()
    if r is not None:
        try:
            # GETDEL es atómico: lee y borra en una sola operación, así que dos
            # callbacks simultáneos con el mismo state no pueden pasar los dos.
            raw = r.getdel(f"{SSO_KEY_PREFIX}{state_raw}")
            if raw is None:
                return None
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="ignore")
            try:
                return _json.loads(raw) if raw else {}
            except ValueError:
                return {}
        except Exception as _e:
            _redis_circuit_break(f"SSO getdel: {_e}")
    with _sso_states_lock:
        entry = _sso_states_fallback.pop(state_raw, None)
    if entry is None:
        return None
    expiry, valor = entry
    if time.time() >= expiry:
        return None
    try:
        return _json.loads(valor) if valor else {}
    except ValueError:
        return {}


# ── Login rate-limiting ───────────────────────────────────────────────────────

def login_bucket(username: str, request: Request) -> str:
    ip = request.client.host if request.client and request.client.host else "unknown"
    return f"{username.strip().lower()}|{ip}"


def login_lock_ttl(bucket: str) -> int:
    if settings.ENVIRONMENT == "development" and os.getenv("TESTING") != "1":
        return 0
    r = get_sso_redis()
    lock_key = f"{LOGIN_LOCK_PREFIX}{bucket}"
    if r is not None:
        try:
            ttl = r.ttl(lock_key)
            return int(ttl) if ttl and ttl > 0 else 0
        except Exception as exc:
            _redis_circuit_break(f"login lockout TTL read: {exc}")
    with _sso_states_lock:
        st = _login_fail_fallback.get(bucket)
        if not st:
            return 0
        lock_until = st.get("lock_until", 0)
        now = time.time()
        if lock_until > now:
            return int(lock_until - now)
        return 0


def _redis_circuit_break(reason: str) -> None:
    """Marcar el cliente como caído para que get_sso_redis() haga reintento
    según el backoff configurado. Aísla el coste de fallos intermitentes."""
    global _redis_client
    logger.warning("Redis op failed (%s) — entrando en circuit-break", reason)
    _redis_client = None  # _redis_client_init stays True; backoff aplica


def register_login_failure(bucket: str) -> int:
    """Register failed login and return lockout seconds if account got locked."""
    if settings.ENVIRONMENT == "development" and os.getenv("TESTING") != "1":
        return 0
    r = get_sso_redis()
    fail_key = f"{LOGIN_FAIL_PREFIX}{bucket}"
    lock_key = f"{LOGIN_LOCK_PREFIX}{bucket}"
    if r is not None:
        try:
            fails = int(r.incr(fail_key))
            if fails == 1:
                r.expire(fail_key, settings.LOGIN_ATTEMPT_WINDOW_SECONDS)
            if fails >= settings.LOGIN_MAX_ATTEMPTS:
                r.setex(lock_key, settings.LOGIN_LOCKOUT_SECONDS, "1")
                r.delete(fail_key)
                return settings.LOGIN_LOCKOUT_SECONDS
            return 0
        except Exception as exc:
            _redis_circuit_break(str(exc))

    now = time.time()
    with _sso_states_lock:
        state = _login_fail_fallback.get(bucket)
        if not state or state.get("window_until", 0) < now:
            state = {
                "count": 0,
                "window_until": now + settings.LOGIN_ATTEMPT_WINDOW_SECONDS,
                "lock_until": 0,
            }
        state["count"] = int(state.get("count", 0)) + 1
        if state["count"] >= settings.LOGIN_MAX_ATTEMPTS:
            state["count"] = 0
            state["lock_until"] = now + settings.LOGIN_LOCKOUT_SECONDS
            _login_fail_fallback[bucket] = state
            return settings.LOGIN_LOCKOUT_SECONDS
        _login_fail_fallback[bucket] = state
    return 0


def clear_login_failure(bucket: str) -> None:
    r = get_sso_redis()
    if r is not None:
        try:
            r.delete(f"{LOGIN_FAIL_PREFIX}{bucket}")
            r.delete(f"{LOGIN_LOCK_PREFIX}{bucket}")
            return
        except Exception as exc:
            _redis_circuit_break(f"login lockout clear: {exc}")
    with _sso_states_lock:
        _login_fail_fallback.pop(bucket, None)


# ── Password reset rate-limiting ──────────────────────────────────────────────

def password_reset_bucket(identifier: str, request: Request) -> str:
    ip = request.client.host if request.client and request.client.host else "unknown"
    return f"{identifier.strip().lower()}|{ip}"


def register_password_reset_request(bucket: str) -> int:
    """Register password reset request and return lockout seconds if throttled."""
    now = time.time()
    with _sso_states_lock:
        st = _password_reset_req_fallback.get(bucket)
        if not st or st.get("window_until", 0) < now:
            st = {
                "count": 0,
                "window_until": now + PASSWORD_RESET_REQUEST_WINDOW_SECONDS,
            }
        st["count"] = int(st.get("count", 0)) + 1
        _password_reset_req_fallback[bucket] = st
        if st["count"] > PASSWORD_RESET_REQUEST_MAX_PER_WINDOW:
            return int(max(st["window_until"] - now, 1))
    return 0


# ── Base64url helpers ─────────────────────────────────────────────────────────

def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def b64url_decode(data: str) -> bytes:
    padding = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + padding)


# ── Ephemeral tokens ──────────────────────────────────────────────────────────

def create_ephemeral_token(
    token_type: str,
    subject: str,
    challenge: str,
    ttl_seconds: int = 300,
    token_jti: Optional[str] = None,
) -> str:
    expire = datetime.now(timezone.utc).timestamp() + ttl_seconds
    jti = token_jti or uuid.uuid4().hex
    payload = {
        "sub": subject,
        "exp": int(expire),
        "type": token_type,
        "challenge": challenge,
        "jti": jti,
    }
    kid, key = get_jwt_signing_key()
    return jose_jwt.encode(payload, key, algorithm="HS256", headers={"kid": kid})


def read_ephemeral_token(token: str, expected_type: str) -> dict:
    payload = None
    for key in get_jwt_verification_keys().values():
        try:
            payload = jose_jwt.decode(token, key, algorithms=["HS256"])
            break
        except JWTError:
            continue
    if payload is None:
        raise HTTPException(401, "Token de challenge inválido o expirado")
    if payload.get("type") != expected_type:
        raise HTTPException(401, "Token de challenge inválido")

    if expected_type == "password_reset":
        user_id = payload.get("sub")
        token_jti = payload.get("jti")
        if not user_id or not token_jti or not is_current_password_reset_jti(user_id, token_jti):
            raise HTTPException(401, "Token de restablecimiento inválido o reemplazado")
    return payload


# ── Auth cookies ──────────────────────────────────────────────────────────────

COOKIE_OPTS = {
    "httponly": True,
    "samesite": "lax",
    # Audit (Sprint 3-4): require HTTPS-only cookies in staging too, not just
    # production. Only local development serves over plain HTTP.
    "secure": settings.ENVIRONMENT in {"production", "staging"},
}


def set_auth_cookies(response: Response, access_token: str, refresh_token: str, db: Optional[Session] = None, org_id: Optional[str] = None) -> None:
    if db is not None:
        from app.services.settings_service import get_runtime_int
        access_minutes = get_runtime_int(db, "ACCESS_TOKEN_EXPIRE_MINUTES", org_id) or settings.ACCESS_TOKEN_EXPIRE_MINUTES
        refresh_days   = get_runtime_int(db, "REFRESH_TOKEN_EXPIRE_DAYS",   org_id) or settings.REFRESH_TOKEN_EXPIRE_DAYS
    else:
        access_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        refresh_days   = settings.REFRESH_TOKEN_EXPIRE_DAYS
    response.set_cookie(
        "access_token",
        access_token,
        max_age=access_minutes * 60,
        **COOKIE_OPTS,
    )
    # Audit (Sprint 3-4): refresh cookie is only ever sent to the dedicated
    # refresh endpoint via same-origin XHR, so SameSite=Strict is safe here and
    # blocks it from riding along on any cross-site navigation.
    response.set_cookie(
        "refresh_token",
        refresh_token,
        max_age=refresh_days * 86400,
        path="/api/v1/auth/refresh",
        **{**COOKIE_OPTS, "samesite": "strict"},
    )
    # Audit #C1: also mint a CSRF token cookie on every login/refresh. The
    # cookie is readable by JS so the SPA can echo it back via X-CSRF-Token
    # when CSRF_DOUBLE_SUBMIT=1 is enabled. No-op effect on clients that don't
    # opt in; pure preparation.
    try:
        from app.core.csrf import issue_csrf_cookie
        issue_csrf_cookie(response)
    except Exception:
        # Never block auth on CSRF token minting issues — log and continue.
        import logging as _logging
        _logging.getLogger(__name__).warning("issue_csrf_cookie failed", exc_info=True)


def current_refresh_jti(request: Request) -> Optional[str]:
    raw_refresh = request.cookies.get("refresh_token")
    if not raw_refresh:
        return None
    token_data = decode_token(raw_refresh)
    if not token_data or token_data.get("type") != "refresh":
        return None
    return token_data.get("jti")


# ── Password reset ────────────────────────────────────────────────────────────

def issue_password_reset_token(user: User) -> str:
    challenge = uuid.uuid4().hex
    jti = uuid.uuid4().hex
    store_password_reset_jti(user.id, jti, PASSWORD_RESET_TTL_SECONDS)
    return create_ephemeral_token(
        token_type="password_reset",  # noqa: S106
        subject=user.id,
        challenge=challenge,
        ttl_seconds=PASSWORD_RESET_TTL_SECONDS,
        token_jti=jti,
    )


def store_password_reset_jti(user_id: str, jti: str, ttl_seconds: int) -> None:
    r = get_sso_redis()
    key = f"{PASSWORD_RESET_JTI_PREFIX}{user_id}"
    if r is not None:
        try:
            r.setex(key, ttl_seconds, jti)
            return
        except Exception as exc:
            logger.warning("Redis setex failed for password reset jti: %s", exc)

    with _sso_states_lock:
        _password_reset_jti_fallback[user_id] = (jti, time.time() + ttl_seconds)


def is_current_password_reset_jti(user_id: str, jti: str) -> bool:
    r = get_sso_redis()
    key = f"{PASSWORD_RESET_JTI_PREFIX}{user_id}"
    if r is not None:
        try:
            stored = r.get(key)
            return bool(stored) and stored == jti
        except Exception as exc:
            logger.warning("Redis get failed for password reset jti: %s", exc)

    with _sso_states_lock:
        current = _password_reset_jti_fallback.get(user_id)
        if not current:
            return False
        current_jti, expires_at = current
        if expires_at <= time.time():
            _password_reset_jti_fallback.pop(user_id, None)
            return False
        return current_jti == jti


def consume_password_reset_token(user_id: str, jti: Optional[str]) -> None:
    if not user_id:
        return
    r = get_sso_redis()
    key = f"{PASSWORD_RESET_JTI_PREFIX}{user_id}"
    if r is not None:
        try:
            if jti:
                stored = r.get(key)
                if stored and stored == jti:
                    r.delete(key)
            else:
                r.delete(key)
            return
        except Exception as exc:
            logger.warning("Redis delete failed for password reset jti: %s", exc)

    with _sso_states_lock:
        if jti:
            current = _password_reset_jti_fallback.get(user_id)
            if current and current[0] == jti:
                _password_reset_jti_fallback.pop(user_id, None)
        else:
            _password_reset_jti_fallback.pop(user_id, None)


def send_password_reset_email(recipient: str, reset_link: str, db: Optional[Session] = None, org_id: Optional[str] = None) -> None:
    subject = "Contecflow PSA - Restablecer contraseña"
    body = (
        "Has solicitado restablecer tu contraseña de Contecflow PSA.\n\n"
        f"Enlace de restablecimiento (válido {PASSWORD_RESET_TTL_SECONDS // 60} minutos):\n"
        f"{reset_link}\n\n"
        "Si no solicitaste este cambio, ignora este correo."
    )

    if db is not None:
        from app.services.integration_credentials_service import get_provider_config
        cfg = get_provider_config(db, "smtp", org_id=org_id)
        smtp_host = cfg.get("host")
        smtp_user = cfg.get("user")
        smtp_port = cfg.get("port") or 587
        smtp_pass = cfg.get("password")
        smtp_from = cfg.get("from") or smtp_user
    else:
        smtp_host = settings.SMTP_HOST
        smtp_user = settings.SMTP_USER
        smtp_port = settings.SMTP_PORT
        smtp_pass = settings.SMTP_PASS
        smtp_from = settings.SMTP_FROM or smtp_user

    if smtp_host and smtp_user and smtp_from:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = smtp_from
        msg["To"] = recipient
        msg.set_content(body)
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            if smtp_pass:
                server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        return

    logger.info("Password reset requested for %s (email backend not configured)", recipient)


# ── DB helpers ────────────────────────────────────────────────────────────────

def commit_db(db: Session) -> None:
    """Commit the current DB transaction."""
    db.commit()


# ── User lookups ──────────────────────────────────────────────────────────────

def lookup_user_by_id_active(db: Session, user_id: str):
    """Return an active User by id, or None."""
    return db.query(User).filter(User.id == user_id, User.is_active == True).first()


def lookup_user_by_credentials(db: Session, username: str):
    """Return an active User matching username or email, or None."""
    return db.query(User).filter(
        (User.username == username) | (User.email == username),
        User.is_active == True,
    ).first()


def lookup_user_by_identifier(db: Session, identifier: str):
    """Return an active User matching email or username, or None. Used by password reset."""
    return db.query(User).filter(
        (User.email == identifier) | (User.username == identifier),
        User.is_active == True,
    ).first()


# ── Session helpers ───────────────────────────────────────────────────────────

def lookup_active_refresh_session(db: Session, user_id: str, token_jti: str):
    """Return the active UserSession matching the given JTI, or None."""
    now = datetime.now(timezone.utc)
    return db.query(UserSession).filter(
        UserSession.user_id == user_id,
        UserSession.refresh_token_jti == token_jti,
        UserSession.revoked_at.is_(None),
        UserSession.expires_at > now,
    ).first()


def get_active_user_sessions(db: Session, user_id: str, now):
    """Return all non-expired, non-revoked sessions for user ordered by last activity."""
    return (
        db.query(UserSession)
        .filter(
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        )
        .order_by(UserSession.last_seen_at.desc())
        .all()
    )


def revoke_one_session(db: Session, session_id: str, user_id: str):
    """Revoke a specific session. Raises 404 if not found or not owned by user."""
    session = db.query(UserSession).filter(
        UserSession.id == session_id,
        UserSession.user_id == user_id,
    ).first()
    if not session:
        raise HTTPException(404, "Sesión no encontrada")
    session.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True, "revoked": session_id}


def revoke_all_user_sessions_except_current(db: Session, user_id: str, current_jti) -> int:
    """Revoke all active sessions except the current one. Returns count revoked."""
    now = datetime.now(timezone.utc)
    q = db.query(UserSession).filter(
        UserSession.user_id == user_id,
        UserSession.revoked_at.is_(None),
    )
    if current_jti:
        q = q.filter(UserSession.refresh_token_jti != current_jti)
    sessions = q.all()
    for s in sessions:
        s.revoked_at = now
    db.commit()
    return len(sessions)


# ── Password reset ────────────────────────────────────────────────────────────

def complete_password_reset(db: Session, user: User, new_hash: str) -> None:
    """Update user password hash and commit."""
    user.hashed_password = new_hash
    db.commit()


# ── SSO helpers ───────────────────────────────────────────────────────────────

def get_active_sso_providers(db: Session):
    """Return list of active SSO provider dicts."""
    # Auditoria 2026-11: leia `c.name`, que no existia, y la excepcion dejaba
    # el login sin botones. SAML no esta implementado: no se ofrece.
    configs = db.query(SSOConfig).filter(SSOConfig.is_active == True, SSOConfig.is_deleted == False,
                                         SSOConfig.provider != "saml").all()
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
        raise HTTPException(404, "SSO no encontrado")
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
        raise HTTPException(403, "El dominio de este correo no está permitido en este proveedor SSO")
    email = email.strip().lower()
    from sqlalchemy import func as _func
    q = db.query(User).filter(_func.lower(User.email) == email)
    user = q.first()
    if user is not None and config.organization_id and user.organization_id != config.organization_id:
        raise HTTPException(409, "Este correo pertenece a otra organización")
    rol_mapeado = rol_desde_grupos(config, claims)
    if not user:
        if not config.auto_create_users:
            raise HTTPException(403, "El proveedor SSO no permite autocrear usuarios")
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
        raise HTTPException(403, "Usuario desactivado")
    org = db.query(Organization).filter(Organization.id == user.organization_id).first()
    if org is not None and not org.is_active:
        raise HTTPException(403, "La organización de este usuario está desactivada")
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


# ── WebAuthn helpers ──────────────────────────────────────────────────────────

def user_has_passkeys(db: Session, user_id: str) -> bool:
    """Return True if user has at least one active WebAuthn credential."""
    return (
        db.query(WebAuthnCredential.id)
        .filter(WebAuthnCredential.user_id == user_id, WebAuthnCredential.is_active == True)
        .first()
        is not None
    )


def get_active_user_credentials(db: Session, user_id: str):
    """Return all active WebAuthn credentials for a user, newest first."""
    return (
        db.query(WebAuthnCredential)
        .filter(WebAuthnCredential.user_id == user_id, WebAuthnCredential.is_active == True)
        .order_by(WebAuthnCredential.created_at.desc())
        .all()
    )


def get_active_webauthn_credential(db: Session, pk_id: str, user_id: str):
    """Find active WebAuthnCredential by pk UUID and user_id."""
    return db.query(WebAuthnCredential).filter(
        WebAuthnCredential.id == pk_id,
        WebAuthnCredential.user_id == user_id,
        WebAuthnCredential.is_active == True,
    ).first()


def has_remaining_active_credentials(db: Session, user_id: str, exclude_pk_id: str) -> bool:
    """Return True if user has other active credentials besides exclude_pk_id."""
    return (
        db.query(WebAuthnCredential.id)
        .filter(
            WebAuthnCredential.user_id == user_id,
            WebAuthnCredential.is_active == True,
            WebAuthnCredential.id != exclude_pk_id,
        )
        .first()
        is not None
    )


def get_webauthn_credential_for_auth(db: Session, user_id: str, credential_id: str):
    """Find active WebAuthnCredential by user_id and webauthn credential_id for authentication."""
    return db.query(WebAuthnCredential).filter(
        WebAuthnCredential.user_id == user_id,
        WebAuthnCredential.credential_id == credential_id,
        WebAuthnCredential.is_active == True,
    ).first()


def get_credential_by_credential_id(db: Session, credential_id: str):
    """Find a WebAuthnCredential by its webauthn credential_id (any user)."""
    return db.query(WebAuthnCredential).filter(
        WebAuthnCredential.credential_id == credential_id,
    ).first()


def upsert_webauthn_credential(
    db: Session,
    current_user_id: str,
    credential_id: str,
    public_key: str,
    sign_count: int,
    transports: str,
    nickname,
) -> None:
    """Add or update a WebAuthn credential. Raises 409 if credential belongs to another user."""
    existing = get_credential_by_credential_id(db, credential_id)
    if existing and existing.user_id != current_user_id:
        raise HTTPException(409, "La passkey ya está registrada para otro usuario")
    if existing:
        existing.public_key = public_key
        existing.sign_count = sign_count
        existing.is_active = True
        if nickname:
            existing.name = nickname
    else:
        db.add(WebAuthnCredential(
            user_id=current_user_id,
            credential_id=credential_id,
            public_key=public_key,
            sign_count=sign_count,
            transports=transports,
            name=nickname,
            is_active=True,
        ))


def organizacion_desactivada(db: Session, organization_id) -> bool:
    """Si la organizacion del usuario existe y esta desactivada (acceso con passkey)."""
    from app.models.mfa import Organization
    org = db.query(Organization).filter(Organization.id == organization_id).first()
    return org is not None and not org.is_active


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
        return float(_cfg.SSO_HTTP_TIMEOUT_SECONDS)
