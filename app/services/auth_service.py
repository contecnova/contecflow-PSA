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
from app.models.mfa import MFAChallenge, Organization
from app.models.user import User, UserRole
from app.services.key_management import get_jwt_signing_key, get_jwt_verification_keys
from app.services.security_observability import SecurityEventService

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

SSO_STATE_TTL = 600  # seconds
SSO_KEY_PREFIX = "clarive:sso_state:"

LOGIN_FAIL_PREFIX = "clarive:login:fail:"
LOGIN_LOCK_PREFIX = "clarive:login:lock:"

PASSWORD_RESET_TTL_SECONDS = 30 * 60
PASSWORD_RESET_REQUEST_WINDOW_SECONDS = 15 * 60
PASSWORD_RESET_REQUEST_MAX_PER_WINDOW = 5

# In-memory fallback stores  ──────────────────────────────────────────────────
_sso_states_fallback: dict[str, float] = {}
_sso_states_lock = threading.Lock()
_redis_client = None
_redis_client_init = False
_login_fail_fallback: dict[str, dict[str, float]] = {}
_password_reset_req_fallback: dict[str, dict[str, float]] = {}


# ── SOC helper ────────────────────────────────────────────────────────────────

def soc_svc(db, user) -> "SecurityEventService | None":
    """Return a SecurityEventService if the user has an org; else None."""
    try:
        org_id = str(user.organization_id) if user and user.organization_id else None
        return SecurityEventService(db=db, org_id=org_id) if org_id else None
    except Exception:
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

def get_sso_redis():
    """Return a shared Redis client if Redis is reachable, else None."""
    global _redis_client, _redis_client_init
    if _redis_client_init:
        return _redis_client
    _redis_client_init = True
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
                "SSO state store: Redis unavailable in development (%s). Using in-memory fallback.",
                _e,
            )
        else:
            logger.warning(
                "SSO state store: Redis unavailable (%s). Falling back to in-memory — "
                "NOT SAFE for multi-worker deployments. Set REDIS_URL to fix.",
                _e,
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
            logger.warning("Redis setex failed for SSO state: %s — using in-memory fallback", _e)
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
            logger.warning("Redis delete failed for SSO state: %s — using in-memory fallback", _e)
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
            logger.warning("Redis TTL read failed for login lockout: %s", exc)
    with _sso_states_lock:
        st = _login_fail_fallback.get(bucket)
        if not st:
            return 0
        lock_until = st.get("lock_until", 0)
        now = time.time()
        if lock_until > now:
            return int(lock_until - now)
        return 0


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
            logger.warning("Redis write failed for login lockout: %s", exc)

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
            logger.warning("Redis clear failed for login lockout: %s", exc)
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
    token_type: str, subject: str, challenge: str, ttl_seconds: int = 300
) -> str:
    expire = datetime.now(timezone.utc).timestamp() + ttl_seconds
    payload = {
        "sub": subject,
        "exp": int(expire),
        "type": token_type,
        "challenge": challenge,
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
    return create_ephemeral_token(
        token_type="password_reset",
        subject=user.id,
        challenge=challenge,
        ttl_seconds=PASSWORD_RESET_TTL_SECONDS,
    )


def send_password_reset_email(recipient: str, reset_link: str) -> None:
    subject = "Clarive PSA - Restablecer contraseña"
    body = (
        "Has solicitado restablecer tu contraseña de Clarive PSA.\n\n"
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

    logger.info("Password reset link for %s: %s", recipient, reset_link)
