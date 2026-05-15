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
PASSWORD_RESET_JTI_PREFIX = "contecflow:password_reset:jti:"

# In-memory fallback stores  ──────────────────────────────────────────────────
_sso_states_fallback: dict[str, float] = {}
_sso_states_lock = threading.Lock()
_redis_client = None
_redis_client_init = False
_login_fail_fallback: dict[str, dict[str, float]] = {}
_password_reset_req_fallback: dict[str, dict[str, float]] = {}
_password_reset_jti_fallback: dict[str, tuple[str, float]] = {}


# ── SOC helper ────────────────────────────────────────────────────────────────

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
        logger.info("SSO state store: using Redis (%s)", settings.REDIS_URL.split("@")[-1])
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


def register_sso_state(state_raw: str) -> None:
    r = get_sso_redis()
    if r is not None:
        try:
            r.setex(f"{SSO_KEY_PREFIX}{state_raw}", SSO_STATE_TTL, "1")
            return
        except Exception as _e:
            _redis_circuit_break(f"SSO setex: {_e}")
    with _sso_states_lock:
        now = time.time()
        expired = [k for k, v in _sso_states_fallback.items() if v < now]
        for k in expired:
            del _sso_states_fallback[k]
        _sso_states_fallback[state_raw] = now + SSO_STATE_TTL


def consume_sso_state(state_raw: str) -> bool:
    """Return True and atomically remove the state if it exists and has not expired."""
    r = get_sso_redis()
    if r is not None:
        try:
            deleted = r.delete(f"{SSO_KEY_PREFIX}{state_raw}")
            return deleted > 0
        except Exception as _e:
            _redis_circuit_break(f"SSO delete: {_e}")
    with _sso_states_lock:
        expiry = _sso_states_fallback.pop(state_raw, None)
    return expiry is not None and time.time() < expiry


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
    "secure": settings.ENVIRONMENT == "production",
}


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    response.set_cookie(
        "access_token",
        access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        **COOKIE_OPTS,
    )
    response.set_cookie(
        "refresh_token",
        refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/v1/auth/refresh",
        **COOKIE_OPTS,
    )


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
        token_type="password_reset",
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


def send_password_reset_email(recipient: str, reset_link: str) -> None:
    subject = "Contecflow PSA - Restablecer contraseña"
    body = (
        "Has solicitado restablecer tu contraseña de Contecflow PSA.\n\n"
        f"Enlace de restablecimiento (válido {PASSWORD_RESET_TTL_SECONDS // 60} minutos):\n"
        f"{reset_link}\n\n"
        "Si no solicitaste este cambio, ignora este correo."
    )

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
    configs = db.query(SSOConfig).filter(SSOConfig.is_active == True).all()
    return [
        {
            "id":       c.id,
            "provider": c.provider,
            "name":     c.name or c.provider.replace("_", " ").title(),
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
        if c.allowed_domains:
            for domain in (c.allowed_domains or []):
                if not isinstance(domain, str) or "." not in domain:
                    issues.append(f"invalid_domain:{domain}")
        out.append({
            "id":        c.id,
            "name":      c.name,
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


def create_or_update_sso_user(db: Session, config, email: str, name, claims: dict):
    """Find or create a user from SSO claims. Returns User."""
    user = db.query(User).filter(User.email == email).first()
    if not user:
        if not config.auto_create_users:
            raise HTTPException(403, "El proveedor SSO no permite autocrear usuarios")
        user = User(
            id=str(uuid.uuid4()),
            email=email,
            full_name=name or email.split("@")[0],
            username=email.split("@")[0],
            role=resolve_sso_role(config.default_role),
            status=UserStatus.active,
            is_active=True,
            organization_id=resolve_sso_organization_id(db, config, email),
            sso_provider=config.provider,
            sso_subject=claims.get("sub"),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    elif not user.is_active:
        raise HTTPException(403, "Usuario desactivado")
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
