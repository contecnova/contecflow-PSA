from fastapi import APIRouter, Depends, HTTPException, Response, status, Query, Body, Request
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import base64
import json
import logging
import os
import smtplib
import time
import threading
import uuid
import ipaddress
import socket
from jose import jwt as jose_jwt, JWTError
from urllib.parse import urlparse

from app.db.session import get_db
from app.services.audit import audit_log
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    create_mfa_challenge_token,
    decode_token,
    validate_password_policy,
)
from app.core.network import extract_client_ip
from app.services.key_management import get_jwt_signing_key, get_jwt_verification_keys
from app.core.encryption import encrypt_value, decrypt_value
from app.core.deps import get_current_user, require_admin
from app.core.config import settings
from app.core.ratelimit import limiter
from app.db.session import is_postgres
from app.models.sessions import UserSession
from app.models.mfa import MFAChallenge, Organization, WebAuthnCredential
from app.models.user import User, UserRole
from app.schemas.auth import (
    LoginRequest,
    TokenResponse,
    RefreshRequest,
    PasswordForgotRequest,
    PasswordResetRequest,
    ActiveSessionOut,
)
from app.schemas.users import UserPublic
from app.services.session_security import (
    parse_risk_reasons,
    register_or_rotate_user_session,
    revoke_session_by_jti,
)
from app.services.security_observability import SecurityEventService
from app.models.security_observability import EventCategory, EventSeverity


def _soc_svc(db, user) -> "SecurityEventService | None":
    """Return a SecurityEventService if the user has an org; else None."""
    try:
        org_id = str(user.organization_id) if user and user.organization_id else None
        return SecurityEventService(db=db, org_id=org_id) if org_id else None
    except Exception:  # noqa: BLE001
        return None


def _client_ip(request: Request) -> str:
    return extract_client_ip(request)


def _mfa_challenge_query(db: Session):
    q = db.query(MFAChallenge)
    if is_postgres():
        q = q.with_for_update()
    return q


def _issue_mfa_challenge(db: Session, user: User) -> str:
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


def _read_mfa_challenge(db: Session, challenge_token: str) -> tuple[dict, MFAChallenge]:
    challenge_data = decode_token(challenge_token)
    if not challenge_data or challenge_data.get("type") != "mfa_challenge":
        raise HTTPException(401, "mfa_challenge_token inválido o expirado")

    challenge_jti = challenge_data.get("jti")
    user_id = challenge_data.get("sub")
    if not challenge_jti or not user_id:
        raise HTTPException(401, "mfa_challenge_token inválido")

    row = _mfa_challenge_query(db).filter(
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


def _consume_mfa_challenge(row: MFAChallenge) -> None:
    row.consumed_at = datetime.now(timezone.utc)


def _resolve_sso_role(default_role: str):
    try:
        return UserRole(default_role)
    except ValueError:
        return UserRole.employee


def _resolve_sso_organization_id(db: Session, config, email: str) -> str:
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


def _validate_https_discovery_url(discovery_url: str) -> str:
    """Validate OIDC discovery URL to avoid SSRF to private/internal networks."""
    parsed = urlparse(discovery_url or "")
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise HTTPException(400, "oidc_discovery_url debe ser una URL HTTPS válida")

    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        raise HTTPException(400, "oidc_discovery_url debe incluir hostname")

    # Fast-path blocks for obvious local targets.
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        raise HTTPException(400, "oidc_discovery_url no puede apuntar a hosts locales")

    # If hostname is an IP literal, reject local/private ranges directly.
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

    # Best-effort DNS resolution for hostnames. Do not hard-fail on resolution
    # errors to keep compatibility in offline/unit-test environments.
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

logger = logging.getLogger(__name__)

router = APIRouter()

# ── SSO state store (CSRF protection: one-time use + 10-min TTL) ──────────────
# Uses Redis when available so one-time states are shared across all uvicorn
# workers. Falls back to an in-process dict for local dev / single-worker
# deployments (not safe for multi-worker production without Redis).
_SSO_STATE_TTL = 600  # seconds
_SSO_KEY_PREFIX = "clarive:sso_state:"

# In-memory fallback
_sso_states_fallback: dict[str, float] = {}
_sso_states_lock = threading.Lock()

# Lazily-initialised Redis client (None = unavailable)
_redis_client = None
_redis_client_init = False

_LOGIN_FAIL_PREFIX = "clarive:login:fail:"
_LOGIN_LOCK_PREFIX = "clarive:login:lock:"
_login_fail_fallback: dict[str, dict[str, float]] = {}
_PASSWORD_RESET_TTL_SECONDS = 30 * 60
_PASSWORD_RESET_REQUEST_WINDOW_SECONDS = 15 * 60
_PASSWORD_RESET_REQUEST_MAX_PER_WINDOW = 5
_password_reset_req_fallback: dict[str, dict[str, float]] = {}


def _get_sso_redis():
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


def _register_sso_state(state_raw: str) -> None:
    r = _get_sso_redis()
    if r is not None:
        try:
            r.setex(f"{_SSO_KEY_PREFIX}{state_raw}", _SSO_STATE_TTL, "1")
            return
        except Exception as _e:
            logger.warning("Redis setex failed for SSO state: %s — using in-memory fallback", _e)
    # In-memory fallback
    with _sso_states_lock:
        now = time.time()
        expired = [k for k, v in _sso_states_fallback.items() if v < now]
        for k in expired:
            del _sso_states_fallback[k]
        _sso_states_fallback[state_raw] = now + _SSO_STATE_TTL


def _consume_sso_state(state_raw: str) -> bool:
    """Return True and atomically remove the state if it exists and has not expired."""
    r = _get_sso_redis()
    if r is not None:
        try:
            deleted = r.delete(f"{_SSO_KEY_PREFIX}{state_raw}")
            return deleted > 0
        except Exception as _e:
            logger.warning("Redis delete failed for SSO state: %s — using in-memory fallback", _e)
    # In-memory fallback
    with _sso_states_lock:
        expiry = _sso_states_fallback.pop(state_raw, None)
    return expiry is not None and time.time() < expiry


def _login_bucket(username: str, request: Request) -> str:
    ip = request.client.host if request.client and request.client.host else "unknown"
    return f"{username.strip().lower()}|{ip}"


def _login_lock_ttl(bucket: str) -> int:
    if settings.ENVIRONMENT == "development" and os.getenv("TESTING") != "1":
        return 0
    r = _get_sso_redis()
    lock_key = f"{_LOGIN_LOCK_PREFIX}{bucket}"
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


def _register_login_failure(bucket: str) -> int:
    """Register failed login and return lockout seconds if account got locked."""
    if settings.ENVIRONMENT == "development" and os.getenv("TESTING") != "1":
        return 0
    r = _get_sso_redis()
    fail_key = f"{_LOGIN_FAIL_PREFIX}{bucket}"
    lock_key = f"{_LOGIN_LOCK_PREFIX}{bucket}"
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


def _clear_login_failure(bucket: str) -> None:
    r = _get_sso_redis()
    if r is not None:
        try:
            r.delete(f"{_LOGIN_FAIL_PREFIX}{bucket}")
            r.delete(f"{_LOGIN_LOCK_PREFIX}{bucket}")
            return
        except Exception as exc:
            logger.warning("Redis clear failed for login lockout: %s", exc)
    with _sso_states_lock:
        _login_fail_fallback.pop(bucket, None)


def _password_reset_bucket(identifier: str, request: Request) -> str:
    ip = request.client.host if request.client and request.client.host else "unknown"
    return f"{identifier.strip().lower()}|{ip}"


def _register_password_reset_request(bucket: str) -> int:
    """Register password reset request and return lockout seconds if throttled."""
    now = time.time()
    with _sso_states_lock:
        st = _password_reset_req_fallback.get(bucket)
        if not st or st.get("window_until", 0) < now:
            st = {
                "count": 0,
                "window_until": now + _PASSWORD_RESET_REQUEST_WINDOW_SECONDS,
            }
        st["count"] = int(st.get("count", 0)) + 1
        _password_reset_req_fallback[bucket] = st
        if st["count"] > _PASSWORD_RESET_REQUEST_MAX_PER_WINDOW:
            return int(max(st["window_until"] - now, 1))
    return 0


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _create_ephemeral_token(token_type: str, subject: str, challenge: str, ttl_seconds: int = 300) -> str:
    expire = datetime.now(timezone.utc).timestamp() + ttl_seconds
    payload = {
        "sub": subject,
        "exp": int(expire),
        "type": token_type,
        "challenge": challenge,
    }
    kid, key = get_jwt_signing_key()
    return jose_jwt.encode(payload, key, algorithm="HS256", headers={"kid": kid})


def _read_ephemeral_token(token: str, expected_type: str) -> dict:
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


# Cookie settings — Secure=True requires HTTPS (production only)
_COOKIE_OPTS = {
    "httponly": True,
    "samesite": "lax",
    "secure": settings.ENVIRONMENT == "production",
}


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    response.set_cookie(
        "access_token",
        access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        **_COOKIE_OPTS,
    )
    response.set_cookie(
        "refresh_token",
        refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/v1/auth/refresh",  # restrict refresh cookie to the refresh endpoint
        **_COOKIE_OPTS,
    )


def _current_refresh_jti(request: Request) -> Optional[str]:
    raw_refresh = request.cookies.get("refresh_token")
    if not raw_refresh:
        return None
    token_data = decode_token(raw_refresh)
    if not token_data or token_data.get("type") != "refresh":
        return None
    return token_data.get("jti")


def _issue_password_reset_token(user: User) -> str:
    challenge = uuid.uuid4().hex
    return _create_ephemeral_token(
        token_type="password_reset",
        subject=user.id,
        challenge=challenge,
        ttl_seconds=_PASSWORD_RESET_TTL_SECONDS,
    )


def _send_password_reset_email(recipient: str, reset_link: str) -> None:
    subject = "Clarive PSA - Restablecer contraseña"
    body = (
        "Has solicitado restablecer tu contraseña de Clarive PSA.\n\n"
        f"Enlace de restablecimiento (válido {_PASSWORD_RESET_TTL_SECONDS // 60} minutos):\n"
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

    # Dev/local fallback: keep feature usable even without SMTP.
    logger.info("Password reset link for %s: %s", recipient, reset_link)


@router.post("/login", response_model=TokenResponse, summary="Login con credenciales locales")
@limiter.limit("5/minute")
def login(request: Request, response: Response, payload: LoginRequest, db: Session = Depends(get_db)):
    bucket = _login_bucket(payload.username, request)
    lock_ttl = _login_lock_ttl(bucket)
    if lock_ttl > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos fallidos. Intenta de nuevo en {lock_ttl}s.",
        )

    user = db.query(User).filter(
        (User.username == payload.username) | (User.email == payload.username),
        User.is_active == True,
    ).first()

    if not user or not user.hashed_password:
        lock_for = _register_login_failure(bucket)
        _ip = _client_ip(request)
        try:
            # emit anonymously — we don't have an org when user lookup failed
            pass
        except Exception:  # noqa: BLE001
            pass
        if lock_for > 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Demasiados intentos fallidos. Intenta de nuevo en {lock_for}s.",
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales incorrectas")

    password_ok = False
    try:
        password_ok = verify_password(payload.password, user.hashed_password)
    except Exception:  # noqa: BLE001
        # Legacy/invalid hashes should not crash login; treat as bad credentials.
        password_ok = False

    # Local recovery path: allow superadmin login with configured env password
    # in non-production environments when DB hash is out-of-sync.
    if (
        not password_ok
        and settings.ENVIRONMENT == "development"
        and os.getenv("TESTING") != "1"
        and bool(getattr(user, "is_superadmin", False))
        and payload.password == settings.SUPERADMIN_PASSWORD
    ):
        password_ok = True

    if not password_ok:
        lock_for = _register_login_failure(bucket)
        try:
            soc = _soc_svc(db, user)
            if soc:
                soc.login_failed(user_id=user.id, ip=_client_ip(request),
                                 ua=request.headers.get("User-Agent", ""),
                                 reason="bad_credentials")
        except Exception:  # noqa: BLE001
            pass
        if lock_for > 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Demasiados intentos fallidos. Intenta de nuevo en {lock_for}s.",
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales incorrectas")

    _clear_login_failure(bucket)

    user.last_login = datetime.now(timezone.utc)
    audit_log(db, user, "LOGIN", "users", user.id, user.full_name)
    try:
        soc = _soc_svc(db, user)
        if soc:
            soc.login_success(
                user_id=user.id,
                ip=_client_ip(request),
                ua=request.headers.get("User-Agent", ""),
            )
    except Exception:  # noqa: BLE001
        pass

    # Enforce MFA: users with TOTP or registered passkeys must complete
    # a second factor challenge before receiving auth tokens.
    has_totp = bool(user.mfa_enabled and user.mfa_secret)
    has_passkeys = (
        db.query(WebAuthnCredential.id)
        .filter(WebAuthnCredential.user_id == user.id, WebAuthnCredential.is_active == True)
        .first()
        is not None
    )
    if has_totp or has_passkeys:
        methods = []
        if has_totp:
            methods.append("totp")
        if has_passkeys:
            methods.append("webauthn")
        db.commit()
        return TokenResponse(
            user=UserPublic.model_validate(user),
            mfa_required=True,
            mfa_challenge_token=_issue_mfa_challenge(db, user),
            mfa_methods=methods,
        )

    # Refresh token rotation: issue new JTI and persist it
    access_token = create_access_token(subject=user.id, extra={"role": user.role})
    refresh_token, new_jti = create_refresh_token(subject=user.id)
    register_or_rotate_user_session(
        db=db,
        user_id=user.id,
        request=request,
        refresh_token_jti=new_jti,
        auth_method="password",
    )
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Error al iniciar sesión. Inténtalo de nuevo.")

    _set_auth_cookies(response, access_token, refresh_token)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserPublic.model_validate(user),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(request: Request, response: Response, db: Session = Depends(get_db), payload: Optional[RefreshRequest] = None):
    # Accept refresh token from cookie (preferred) or request body (legacy)
    raw_refresh = request.cookies.get("refresh_token")
    if not raw_refresh and payload:
        raw_refresh = payload.refresh_token
    if not raw_refresh:
        raise HTTPException(status_code=401, detail="Refresh token requerido")

    token_data = decode_token(raw_refresh)
    if not token_data or token_data.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Refresh token inválido")

    user = db.query(User).filter(User.id == token_data["sub"], User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")

    # Rotation validation: strict per-session JTI.
    token_jti = token_data.get("jti")
    if not token_jti:
        raise HTTPException(status_code=401, detail="Refresh token inválido")

    active_session = (
        db.query(UserSession)
        .filter(
            UserSession.user_id == user.id,
            UserSession.refresh_token_jti == token_jti,
            UserSession.revoked_at.is_(None),
        )
        .first()
    )
    if active_session is None:
        raise HTTPException(status_code=401, detail="Refresh token ya fue utilizado o es inválido. Por seguridad, debes iniciar sesión de nuevo.")

    # Issue new token pair and rotate JTI
    access_token = create_access_token(subject=user.id, extra={"role": user.role})
    new_refresh_token, new_jti = create_refresh_token(subject=user.id)
    register_or_rotate_user_session(
        db=db,
        user_id=user.id,
        request=request,
        refresh_token_jti=new_jti,
        previous_refresh_token_jti=token_jti,
        auth_method="refresh",
    )
    db.commit()

    _set_auth_cookies(response, access_token, new_refresh_token)

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        user=UserPublic.model_validate(user),
    )


@router.post("/logout", summary="Cerrar sesión — elimina cookies de autenticación")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    revoke_session_by_jti(
        db=db,
        user_id=current_user.id,
        refresh_token_jti=_current_refresh_jti(request),
        reason="logout",
    )
    db.commit()
    response.delete_cookie("access_token", **_COOKIE_OPTS)
    response.delete_cookie("refresh_token", path="/api/v1/auth/refresh", **_COOKIE_OPTS)
    return {"detail": "Sesión cerrada correctamente"}


@router.post("/password/forgot", summary="Solicitar enlace para restablecer contraseña")
@limiter.limit("5/minute")
def password_forgot(request: Request, payload: PasswordForgotRequest, db: Session = Depends(get_db)):
    identifier = (payload.email_or_username or "").strip()
    if identifier:
        ttl = _register_password_reset_request(_password_reset_bucket(identifier, request))
        if ttl > 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Demasiadas solicitudes de recuperación. Intenta de nuevo en {ttl}s.",
            )

    if identifier:
        user = db.query(User).filter(
            ((User.email == identifier) | (User.username == identifier)),
            User.is_active == True,
        ).first()
        if user and user.email and user.hashed_password:
            try:
                token = _issue_password_reset_token(user)
                reset_link = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?token={token}"
                _send_password_reset_email(user.email, reset_link)
                audit_log(db, user, "PASSWORD_RESET_REQUEST", "users", user.id, user.full_name)
                db.commit()
            except Exception as exc:
                logger.warning("Password reset email send failed for user_id=%s: %s", user.id, exc)

    # Anti-enumeration: always return a generic success response.
    return {
        "ok": True,
        "message": "Si existe una cuenta asociada, se ha enviado un enlace de restablecimiento.",
    }


@router.post("/password/reset", summary="Restablecer contraseña con token")
@limiter.limit("10/minute")
def password_reset(request: Request, payload: PasswordResetRequest, db: Session = Depends(get_db)):
    token_data = _read_ephemeral_token(payload.token, "password_reset")
    user_id = token_data.get("sub")
    if not user_id:
        raise HTTPException(401, "Token de restablecimiento inválido o expirado")

    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(401, "Token de restablecimiento inválido o expirado")

    ok, reason = validate_password_policy(payload.new_password)
    if not ok:
        raise HTTPException(400, reason or "La contraseña no cumple la política de seguridad")

    user.hashed_password = get_password_hash(payload.new_password)

    now = datetime.now(timezone.utc)
    db.query(UserSession).filter(
        UserSession.user_id == user.id,
        UserSession.revoked_at.is_(None),
    ).update(
        {
            "revoked_at": now,
            "revoke_reason": "password_reset",
        },
        synchronize_session=False,
    )
    audit_log(db, user, "PASSWORD_RESET_COMPLETE", "users", user.id, user.full_name)
    db.commit()

    return {"ok": True, "message": "Contraseña actualizada correctamente"}


@router.get("/sessions/active", response_model=list[ActiveSessionOut], summary="Panel de sesiones activas del usuario")
def list_active_sessions(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_jti = _current_refresh_jti(request)
    now = datetime.now(timezone.utc)
    sessions = (
        db.query(UserSession)
        .filter(
            UserSession.user_id == current_user.id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        )
        .order_by(UserSession.last_seen_at.desc())
        .all()
    )
    return [
        ActiveSessionOut(
            id=s.id,
            ip_address=s.ip_address,
            ip_asn=s.ip_asn,
            ip_org=s.ip_org,
            country_code=s.country_code,
            region=s.region,
            city=s.city,
            user_agent=s.user_agent,
            device_name=s.device_name,
            risk_score=s.risk_score or 0,
            risk_level=s.risk_level or "low",
            risk_reasons=parse_risk_reasons(s.risk_reasons),
            auth_method=s.auth_method,
            last_seen_at=s.last_seen_at,
            expires_at=s.expires_at,
            created_at=s.created_at,
            is_current=(current_jti is not None and s.refresh_token_jti == current_jti),
        )
        for s in sessions
    ]


@router.delete("/sessions/{session_id}", summary="Revocar dispositivo/sesión específica")
def revoke_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = (
        db.query(UserSession)
        .filter(
            UserSession.id == session_id,
            UserSession.user_id == current_user.id,
            UserSession.revoked_at.is_(None),
        )
        .first()
    )
    if not session:
        raise HTTPException(404, "Sesión no encontrada")
    session.revoked_at = datetime.now(timezone.utc)
    session.revoke_reason = "user_revoked"
    db.commit()
    return {"ok": True}


@router.post("/sessions/revoke-all", summary="Revocar todas las sesiones activas del usuario")
def revoke_all_sessions(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_jti = _current_refresh_jti(request)
    now = datetime.now(timezone.utc)
    active_sessions = (
        db.query(UserSession)
        .filter(
            UserSession.user_id == current_user.id,
            UserSession.revoked_at.is_(None),
        )
        .all()
    )
    revoked = 0
    for s in active_sessions:
        if current_jti and s.refresh_token_jti == current_jti:
            continue
        s.revoked_at = now
        s.revoke_reason = "user_revoke_all"
        revoked += 1
    db.commit()
    return {"ok": True, "revoked": revoked}


@router.get("/me", response_model=UserPublic)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/sso/providers", summary="Proveedores SSO activos (para mostrar en login)")
def list_sso_providers(db: Session = Depends(get_db)):
    """Devuelve los proveedores SSO activos para mostrar botones en el login."""
    try:
        from app.models.enterprise import SSOConfig
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
    except Exception:
        logger.warning("Failed to load SSO providers", exc_info=True)
        return []


@router.get("/saml/metadata", summary="Metadata SAML del Service Provider")
def saml_metadata():
    entity_id = f"{settings.BASE_URL}/api/v1/auth/saml/metadata"
    acs_url = f"{settings.BASE_URL}/api/v1/auth/saml/callback"
    slo_url = f"{settings.BASE_URL}/api/v1/auth/saml/logout"
    metadata_xml = f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<EntityDescriptor xmlns=\"urn:oasis:names:tc:SAML:2.0:metadata\" entityID=\"{entity_id}\">
  <SPSSODescriptor AuthnRequestsSigned=\"false\" WantAssertionsSigned=\"true\" protocolSupportEnumeration=\"urn:oasis:names:tc:SAML:2.0:protocol\">
    <NameIDFormat>urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress</NameIDFormat>
    <AssertionConsumerService Binding=\"urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST\" Location=\"{acs_url}\" index=\"1\" isDefault=\"true\"/>
    <SingleLogoutService Binding=\"urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect\" Location=\"{slo_url}\"/>
  </SPSSODescriptor>
</EntityDescriptor>
"""
    return Response(content=metadata_xml, media_type="application/samlmetadata+xml")


@router.get("/saml/health", summary="Health de configuración SAML")
def saml_health(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    from app.models.enterprise import SSOConfig

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
            domains = [d.strip().lower() for d in c.allowed_domains.split(",") if d.strip()]
            if any("*" in d for d in domains):
                issues.append("wildcard_domain_not_recommended")
        out.append({
            "id": c.id,
            "is_active": c.is_active,
            "issues": issues,
            "healthy": len(issues) == 0,
        })
    return {
        "metadata_url": f"{settings.BASE_URL}/api/v1/auth/saml/metadata",
        "configs": out,
    }


@router.get("/sso/{config_id}/authorize", summary="Iniciar flujo OAuth2 OIDC")
def sso_authorize(
    config_id: str,
    redirect_uri: str = Query(...),
    db: Session = Depends(get_db),
):
    """
    Genera la URL de autorización del proveedor OIDC.
    El frontend redirige al usuario a esta URL.
    """
    try:
        from app.models.enterprise import SSOConfig
        import secrets
        import urllib.parse
        config = db.query(SSOConfig).filter(SSOConfig.id == config_id, SSOConfig.is_active == True).first()
        if not config: raise HTTPException(404, "SSO no encontrado")

        # Security: validate redirect_uri against the allowed origins whitelist to
        # prevent open redirect attacks. The redirect_uri must start with one of the
        # configured ALLOWED_ORIGINS or the provider's registered redirect URIs.
        _allowed = list(settings.ALLOWED_ORIGINS) + [settings.FRONTEND_URL]
        if not any(redirect_uri.startswith(origin) for origin in _allowed):
            raise HTTPException(400, "redirect_uri no está en la lista de orígenes permitidos")

        state_raw = secrets.token_urlsafe(32)
        # Firmar el state con HMAC para prevenir CSRF (validado en el callback)
        import hmac
        import hashlib
        state_sig = hmac.new(
            settings.SECRET_KEY.encode(),
            state_raw.encode(),
            hashlib.sha256,
        ).hexdigest()
        state = f"{state_raw}.{state_sig}"
        _register_sso_state(state_raw)  # store for one-time use with TTL

        # Determinar authorization_endpoint según el proveedor
        if config.provider == "azure_ad":
            tenant = config.oidc_discovery_url.split("/")[3] if config.oidc_discovery_url else "common"
            auth_url = f"{settings.MICROSOFT_OAUTH_BASE}/{tenant}/oauth2/v2.0/authorize"
            scope = "openid profile email"
        elif config.provider == "okta":
            base = config.oidc_discovery_url.replace("/.well-known/openid-configuration", "") if config.oidc_discovery_url else ""
            auth_url = f"{base}/v1/authorize"
            scope = "openid profile email"
        elif config.provider == "google":
            auth_url = f"{settings.GOOGLE_OAUTH_BASE}/o/oauth2/v2/auth"
            scope = "openid profile email"
        else:
            # OIDC genérico: descubrir desde discovery_url
            if config.oidc_discovery_url:
                try:
                    import urllib.request
                    discovery_url = _validate_https_discovery_url(config.oidc_discovery_url)
                    with urllib.request.urlopen(discovery_url, timeout=5) as resp:
                        import json as _json
                        disc = _json.loads(resp.read())
                        auth_url = disc.get("authorization_endpoint", "")
                except Exception:
                    raise HTTPException(500, "No se pudo obtener el discovery document")
            else:
                raise HTTPException(400, "Falta oidc_discovery_url para proveedor OIDC genérico")
            scope = "openid profile email"

        params = {
            "client_id":     config.oidc_client_id,
            "response_type": "code",
            "scope":         scope,
            "redirect_uri":  redirect_uri,
            "state":         state,
            "nonce":         secrets.token_urlsafe(16),
        }
        url = auth_url + "?" + urllib.parse.urlencode(params)
        return {"authorization_url": url, "state": state, "provider": config.provider}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("SSO authorize error: %s", e, exc_info=True)
        raise HTTPException(500, "Error al iniciar el flujo SSO. Comprueba la configuración del proveedor.")


@router.post("/sso/{config_id}/callback", summary="Callback OIDC — intercambiar code por token")
def sso_callback(
    config_id: str,
    request: Request,
    response: Response,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    """
    Recibe el authorization code del proveedor OIDC,
    lo intercambia por tokens, extrae el email, y crea/autentica al usuario.
    """
    try:
        from app.models.enterprise import SSOConfig
        from app.models.user import User as UserModel, UserRole, UserStatus
        import urllib.request
        import urllib.parse
        import json as _json

        config = db.query(SSOConfig).filter(SSOConfig.id == config_id, SSOConfig.is_active == True).first()
        if not config: raise HTTPException(404, "SSO no encontrado")

        code         = payload.get("code")
        redirect_uri = payload.get("redirect_uri")
        state_param  = payload.get("state")
        if not code or not redirect_uri:
            raise HTTPException(400, "Faltan code o redirect_uri")

        # Validar state para prevenir CSRF
        if not state_param or "." not in state_param:
            raise HTTPException(400, "State inválido o ausente")
        import hmac as _hmac
        import hashlib as _hashlib
        state_raw, state_sig = state_param.rsplit(".", 1)
        expected_sig = _hmac.new(
            settings.SECRET_KEY.encode(),
            state_raw.encode(),
            _hashlib.sha256,
        ).hexdigest()
        if not _hmac.compare_digest(expected_sig, state_sig):
            raise HTTPException(400, "State inválido: posible ataque CSRF")
        # Consume the state (prevents replay attacks)
        if not _consume_sso_state(state_raw):
            raise HTTPException(400, "State expirado o ya utilizado")

        # Determinar token_endpoint
        if config.provider == "azure_ad":
            tenant    = config.oidc_discovery_url.split("/")[3] if config.oidc_discovery_url else "common"
            token_url = f"{settings.MICROSOFT_OAUTH_BASE}/{tenant}/oauth2/v2.0/token"
        elif config.provider == "okta":
            base      = config.oidc_discovery_url.replace("/.well-known/openid-configuration", "") if config.oidc_discovery_url else ""
            token_url = f"{base}/v1/token"
        elif config.provider == "google":
            token_url = settings.GOOGLE_TOKEN_URL
        else:
            if config.oidc_discovery_url:
                try:
                    discovery_url = _validate_https_discovery_url(config.oidc_discovery_url)
                    with urllib.request.urlopen(discovery_url, timeout=5) as resp:
                        disc = _json.loads(resp.read())
                        token_url = disc.get("token_endpoint", "")
                except Exception:
                    raise HTTPException(500, "No se pudo obtener el token_endpoint")
            else:
                raise HTTPException(400, "Falta oidc_discovery_url")

        # Intercambiar code por tokens
        token_data = urllib.parse.urlencode({
            "grant_type":    "authorization_code",
            "code":          code,
            "redirect_uri":  redirect_uri,
            "client_id":     config.oidc_client_id,
            "client_secret": decrypt_value(config.oidc_client_secret) if config.oidc_client_secret else "",
        }).encode()

        req = urllib.request.Request(token_url, data=token_data,
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                tokens = _json.loads(resp.read())
        except Exception as e:
            raise HTTPException(502, f"Error al obtener tokens del proveedor SSO: {e}")

        id_token = tokens.get("id_token", "")
        if not id_token:
            raise HTTPException(502, "El proveedor no devolvió id_token")

        # Verificar firma del id_token usando las claves públicas del proveedor (JWKS)
        try:
            import jwt as _jwt  # PyJWT
            # Obtener JWKS URI desde el discovery document para validar la firma
            jwks_uri = None
            if config.oidc_discovery_url:
                try:
                    discovery_url = _validate_https_discovery_url(config.oidc_discovery_url)
                    with urllib.request.urlopen(discovery_url, timeout=5) as resp:
                        disc = _json.loads(resp.read())
                        jwks_uri = disc.get("jwks_uri")
                except Exception:
                    pass

            if jwks_uri:
                _validate_https_discovery_url(jwks_uri)

            if jwks_uri:
                jwks_client = _jwt.PyJWKClient(jwks_uri)
                signing_key = jwks_client.get_signing_key_from_jwt(id_token)
                claims = _jwt.decode(
                    id_token,
                    signing_key.key,
                    algorithms=["RS256", "ES256"],
                    audience=config.oidc_client_id,
                    options={"verify_exp": True},
                )
            else:
                # No se puede obtener la URI de JWKS: rechazar la autenticación.
                # Aceptar tokens sin verificar la firma es una vulnerabilidad crítica.
                raise HTTPException(
                    status_code=502,
                    detail="No se pudo obtener JWKS URI del proveedor SSO. Imposible verificar la firma del id_token.",
                )
        except Exception as jwt_err:
            raise HTTPException(502, f"id_token inválido o firma incorrecta: {jwt_err}")

        # Extraer email y nombre según configuración del proveedor
        email_claim = config.saml_attribute_email or "email"
        name_claim  = config.saml_attribute_name  or "name"
        email = claims.get(email_claim) or claims.get("email") or claims.get("preferred_username")
        name  = claims.get(name_claim)  or claims.get("name") or email

        if not email:
            raise HTTPException(502, "No se pudo obtener el email del token SSO")

        # P0-4: Email verification check — reject unverified emails.
        # Google and Azure AD always verify emails; generic OIDC providers may not.
        email_verified = claims.get("email_verified")
        if email_verified is False:
            raise HTTPException(
                status_code=403,
                detail="El proveedor SSO indica que este email no está verificado. No se puede autenticar.",
            )

        # Buscar o crear usuario
        user = db.query(UserModel).filter(UserModel.email == email).first()
        if not user:
            if not config.auto_create_users:
                raise HTTPException(403, "El proveedor SSO no permite autocrear usuarios")
            # Crear usuario automáticamente desde SSO
            user = UserModel(
                id=str(uuid.uuid4()),
                email=email,
                full_name=name or email.split("@")[0],
                username=email.split("@")[0],
                role=_resolve_sso_role(config.default_role),
                status=UserStatus.active,
                is_active=True,
                organization_id=_resolve_sso_organization_id(db, config, email),
                sso_provider=config.provider,
                sso_subject=claims.get("sub"),
            )
            db.add(user); db.commit(); db.refresh(user)
        elif not user.is_active:
            raise HTTPException(403, "Usuario desactivado")

        # Enforce MFA for SSO users too (TOTP or WebAuthn passkeys).
        has_totp = bool(user.mfa_enabled and user.mfa_secret)
        has_passkeys = (
            db.query(WebAuthnCredential.id)
            .filter(WebAuthnCredential.user_id == user.id, WebAuthnCredential.is_active == True)
            .first()
            is not None
        )
        if has_totp or has_passkeys:
            methods = []
            if has_totp:
                methods.append("totp")
            if has_passkeys:
                methods.append("webauthn")
            return {
                "token_type": "bearer",
                "mfa_required": True,
                "mfa_challenge_token": _issue_mfa_challenge(db, user),
                "mfa_methods": methods,
                "user": {
                    "id": user.id, "email": user.email,
                    "full_name": user.full_name,
                    "role": user.role.value if hasattr(user.role, "value") else str(user.role),
                }
            }

        # Emitir JWT propio con rotación de refresh token
        access_token = create_access_token(subject=user.id, extra={"role": user.role})
        new_refresh_token, new_jti = create_refresh_token(subject=user.id)
        register_or_rotate_user_session(
            db=db,
            user_id=user.id,
            request=request,
            refresh_token_jti=new_jti,
            auth_method="sso",
        )
        db.commit()

        _set_auth_cookies(response, access_token, new_refresh_token)

        return {
            "access_token":  access_token,
            "refresh_token": new_refresh_token,
            "token_type":    "bearer",
            "user": {
                "id": user.id, "email": user.email,
                "full_name": user.full_name,
                "role": user.role.value if hasattr(user.role, "value") else str(user.role),
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("SSO callback error: %s", e, exc_info=True)
        raise HTTPException(500, "Error al completar el inicio de sesión SSO.")


# ── 2FA / MFA — TOTP real con pyotp ──────────────────────────────────────────

@router.post("/mfa/setup", summary="Iniciar configuración 2FA — genera secreto TOTP")
@limiter.limit("5/minute")
def mfa_setup(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Genera un secreto TOTP y devuelve:
    - secret: clave base32 para guardar en el usuario
    - qr_url: URL para generar QR con el autenticador
    - provisioning_uri: URI para apps como Google Authenticator / Authy
    """
    try:
        import pyotp
    except ImportError:
        raise HTTPException(500, "pyotp no instalado — ejecuta: pip install pyotp")

    secret = pyotp.random_base32()
    totp   = pyotp.TOTP(secret)
    uri    = totp.provisioning_uri(
        name=current_user.email,
        issuer_name="Clarive PSA",
    )
    # Generate QR locally — no data is sent to third-party services.
    try:
        import qrcode
        import io
        import base64
        qr_img = qrcode.make(uri)
        buf = io.BytesIO()
        qr_img.save(buf, format="PNG")
        qr_b64 = base64.b64encode(buf.getvalue()).decode()
        qr_url = f"data:image/png;base64,{qr_b64}"
    except ImportError:
        raise HTTPException(500, "qrcode no instalado — ejecuta: pip install 'qrcode[pil]'")

    # Guardar secreto temporal cifrado (aún no activado)
    current_user.mfa_secret = encrypt_value(secret)
    current_user.mfa_enabled = False
    db.commit()

    return {
        "secret":           secret,
        "provisioning_uri": uri,
        "qr_url":           qr_url,
        "issuer":           "Clarive PSA",
        "email":            current_user.email,
    }


@router.post("/mfa/verify-setup", summary="Verificar código TOTP y activar 2FA")
@limiter.limit("5/minute")
def mfa_verify_setup(
    request: Request,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Verifica el código de 6 dígitos del autenticador y activa 2FA.
    Si es correcto, guarda el secreto definitivamente.
    """
    try:
        import pyotp
    except ImportError:
        raise HTTPException(500, "pyotp no instalado")

    code   = str(payload.get("code", "")).strip()
    raw_secret = current_user.mfa_secret
    secret = decrypt_value(raw_secret) if raw_secret else None

    if not secret:
        raise HTTPException(400, "Primero inicia la configuración con /mfa/setup")
    if not code:
        raise HTTPException(400, "Código requerido")

    totp  = pyotp.TOTP(secret)
    valid = totp.verify(code, valid_window=1)  # permite ±30s

    if not valid:
        raise HTTPException(400, "Código incorrecto o expirado. Asegúrate de que la hora del dispositivo es correcta.")

    current_user.mfa_enabled = True
    db.commit()

    return {"ok": True, "message": "Autenticación de dos factores activada correctamente"}


@router.post("/mfa/validate", summary="Validar código TOTP durante el login")
@limiter.limit("10/minute")
def mfa_validate(
    request: Request,
    response: Response,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    """
    Valida el código TOTP durante el proceso de login.
    Recibe user_id + code. Si es correcto, emite los tokens JWT.
    """
    try:
        import pyotp
    except ImportError:
        raise HTTPException(500, "pyotp no instalado")

    challenge_token = payload.get("mfa_challenge_token")
    code    = str(payload.get("code", "")).strip()

    if not challenge_token:
        raise HTTPException(400, "mfa_challenge_token requerido")
    challenge_data, challenge_row = _read_mfa_challenge(db, challenge_token)
    user_id = challenge_data.get("sub")

    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(404, "Usuario no encontrado")
    if not user.mfa_enabled or not user.mfa_secret:
        raise HTTPException(400, "Este usuario no tiene TOTP activo. Usa autenticación WebAuthn/passkey.")

    totp  = pyotp.TOTP(decrypt_value(user.mfa_secret) or "")
    valid = totp.verify(code, valid_window=1)

    if not valid:
        try:
            soc = _soc_svc(db, user)
            if soc:
                soc.mfa_failed(user_id=user.id, ip=_client_ip(request), method="totp")
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(401, "Código 2FA incorrecto")

    access_token = create_access_token(subject=user.id, extra={"role": user.role})
    new_refresh_token, new_jti = create_refresh_token(subject=user.id)
    _consume_mfa_challenge(challenge_row)
    register_or_rotate_user_session(
        db=db,
        user_id=user.id,
        request=request,
        refresh_token_jti=new_jti,
        auth_method="totp",
    )
    try:
        soc = _soc_svc(db, user)
        if soc:
            soc.login_success(
                user_id=user.id,
                ip=_client_ip(request),
                ua=request.headers.get("User-Agent", ""),
            )
    except Exception:  # noqa: BLE001
        pass
    db.commit()

    _set_auth_cookies(response, access_token, new_refresh_token)

    return {
        "access_token":  access_token,
        "refresh_token": new_refresh_token,
        "token_type":    "bearer",
        "user": {
            "id": user.id, "email": user.email,
            "full_name": user.full_name,
            "role": user.role.value if hasattr(user.role, "value") else str(user.role),
        }
    }


@router.post("/mfa/webauthn/register/start", summary="Iniciar registro de passkey (WebAuthn)")
@limiter.limit("10/minute")
def webauthn_register_start(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        from webauthn import generate_registration_options, options_to_json
        from webauthn.helpers.structs import PublicKeyCredentialDescriptor, UserVerificationRequirement
    except ImportError:
        raise HTTPException(503, "webauthn no instalado — ejecuta: pip install webauthn")

    existing = db.query(WebAuthnCredential).filter(
        WebAuthnCredential.user_id == current_user.id,
        WebAuthnCredential.is_active == True,
    ).all()
    exclude_credentials = [
        PublicKeyCredentialDescriptor(id=_b64url_decode(c.credential_id)) for c in existing
    ]
    options = generate_registration_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        rp_name=settings.WEBAUTHN_RP_NAME,
        user_id=current_user.id.encode(),
        user_name=current_user.email,
        user_display_name=current_user.full_name,
        exclude_credentials=exclude_credentials,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    challenge = _b64url_encode(options.challenge)
    challenge_token = _create_ephemeral_token(
        token_type="webauthn_register_challenge",
        subject=current_user.id,
        challenge=challenge,
    )
    return {
        "options": json.loads(options_to_json(options)),
        "webauthn_challenge_token": challenge_token,
    }


@router.post("/mfa/webauthn/register/finish", summary="Finalizar registro de passkey (WebAuthn)")
@limiter.limit("10/minute")
def webauthn_register_finish(
    request: Request,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        from webauthn import verify_registration_response
    except ImportError:
        raise HTTPException(503, "webauthn no instalado — ejecuta: pip install webauthn")

    challenge_token = payload.get("webauthn_challenge_token")
    credential = payload.get("credential")
    nickname = payload.get("name")
    if not challenge_token or not credential:
        raise HTTPException(400, "webauthn_challenge_token y credential son obligatorios")

    token_data = _read_ephemeral_token(challenge_token, "webauthn_register_challenge")
    if token_data.get("sub") != current_user.id:
        raise HTTPException(403, "El challenge no pertenece al usuario autenticado")

    try:
        verification = verify_registration_response(
            credential=credential,
            expected_challenge=token_data.get("challenge", ""),
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            expected_origin=settings.WEBAUTHN_ORIGIN,
            require_user_verification=True,
        )
    except Exception as exc:
        raise HTTPException(400, f"Registro WebAuthn inválido: {exc}")

    credential_id = _b64url_encode(verification.credential_id)
    existing = db.query(WebAuthnCredential).filter(
        WebAuthnCredential.credential_id == credential_id
    ).first()
    if existing and existing.user_id != current_user.id:
        raise HTTPException(409, "La passkey ya está registrada para otro usuario")
    if existing:
        existing.public_key = _b64url_encode(verification.credential_public_key)
        existing.sign_count = int(verification.sign_count)
        existing.is_active = True
        existing.name = nickname or existing.name
    else:
        db.add(WebAuthnCredential(
            user_id=current_user.id,
            credential_id=credential_id,
            public_key=_b64url_encode(verification.credential_public_key),
            sign_count=int(verification.sign_count),
            transports=json.dumps(credential.get("response", {}).get("transports", [])),
            name=nickname,
            is_active=True,
        ))
    current_user.mfa_enabled = True
    db.commit()
    return {"ok": True, "message": "Passkey registrada correctamente"}


@router.get("/mfa/webauthn/credentials", summary="Listar passkeys registradas")
def webauthn_list_credentials(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    creds = db.query(WebAuthnCredential).filter(
        WebAuthnCredential.user_id == current_user.id,
        WebAuthnCredential.is_active == True,
    ).order_by(WebAuthnCredential.created_at.desc()).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "created_at": c.created_at,
            "last_used_at": c.last_used_at,
        }
        for c in creds
    ]


@router.delete("/mfa/webauthn/credentials/{credential_id}", summary="Eliminar passkey")
def webauthn_delete_credential(
    credential_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cred = db.query(WebAuthnCredential).filter(
        WebAuthnCredential.id == credential_id,
        WebAuthnCredential.user_id == current_user.id,
        WebAuthnCredential.is_active == True,
    ).first()
    if not cred:
        raise HTTPException(404, "Passkey no encontrada")
    cred.is_active = False
    remaining = db.query(WebAuthnCredential.id).filter(
        WebAuthnCredential.user_id == current_user.id,
        WebAuthnCredential.is_active == True,
        WebAuthnCredential.id != credential_id,
    ).first()
    if not remaining and not current_user.mfa_secret:
        current_user.mfa_enabled = False
    db.commit()
    return {"ok": True}


@router.post("/mfa/webauthn/authenticate/start", summary="Iniciar login con passkey")
@limiter.limit("15/minute")
def webauthn_auth_start(
    request: Request,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    try:
        from webauthn import generate_authentication_options, options_to_json
        from webauthn.helpers.structs import PublicKeyCredentialDescriptor, UserVerificationRequirement
    except ImportError:
        raise HTTPException(503, "webauthn no instalado — ejecuta: pip install webauthn")

    mfa_challenge_token = payload.get("mfa_challenge_token")
    if not mfa_challenge_token:
        raise HTTPException(400, "mfa_challenge_token requerido")
    mfa_data, _ = _read_mfa_challenge(db, mfa_challenge_token)
    user_id = mfa_data.get("sub")
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(404, "Usuario no encontrado")

    creds = db.query(WebAuthnCredential).filter(
        WebAuthnCredential.user_id == user.id,
        WebAuthnCredential.is_active == True,
    ).all()
    if not creds:
        raise HTTPException(400, "El usuario no tiene passkeys registradas")

    allow_credentials = [
        PublicKeyCredentialDescriptor(id=_b64url_decode(c.credential_id))
        for c in creds
    ]
    options = generate_authentication_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        allow_credentials=allow_credentials,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    challenge = _b64url_encode(options.challenge)
    webauthn_challenge_token = _create_ephemeral_token(
        token_type="webauthn_auth_challenge",
        subject=user.id,
        challenge=challenge,
    )

    return {
        "options": json.loads(options_to_json(options)),
        "webauthn_challenge_token": webauthn_challenge_token,
    }


@router.post("/mfa/webauthn/authenticate/finish", summary="Finalizar login con passkey")
@limiter.limit("15/minute")
def webauthn_auth_finish(
    request: Request,
    response: Response,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    try:
        from webauthn import verify_authentication_response
    except ImportError:
        raise HTTPException(503, "webauthn no instalado — ejecuta: pip install webauthn")

    mfa_challenge_token = payload.get("mfa_challenge_token")
    webauthn_challenge_token = payload.get("webauthn_challenge_token")
    credential = payload.get("credential")
    if not mfa_challenge_token or not webauthn_challenge_token or not credential:
        raise HTTPException(400, "mfa_challenge_token, webauthn_challenge_token y credential son obligatorios")

    mfa_data, challenge_row = _read_mfa_challenge(db, mfa_challenge_token)
    user_id = mfa_data.get("sub")

    webauthn_data = _read_ephemeral_token(webauthn_challenge_token, "webauthn_auth_challenge")
    if webauthn_data.get("sub") != user_id:
        raise HTTPException(401, "webauthn_challenge_token inválido")

    credential_id = credential.get("id")
    if not credential_id:
        raise HTTPException(400, "Credential inválida")

    cred = db.query(WebAuthnCredential).filter(
        WebAuthnCredential.user_id == user_id,
        WebAuthnCredential.credential_id == credential_id,
        WebAuthnCredential.is_active == True,
    ).first()
    if not cred:
        raise HTTPException(401, "Passkey no reconocida")

    try:
        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=webauthn_data.get("challenge", ""),
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            expected_origin=settings.WEBAUTHN_ORIGIN,
            credential_public_key=_b64url_decode(cred.public_key),
            credential_current_sign_count=cred.sign_count,
            require_user_verification=True,
        )
    except Exception as exc:
        raise HTTPException(401, f"Autenticación WebAuthn inválida: {exc}")

    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(404, "Usuario no encontrado")

    cred.sign_count = int(getattr(verification, "new_sign_count", cred.sign_count))
    cred.last_used_at = datetime.now(timezone.utc)

    access_token = create_access_token(subject=user.id, extra={"role": user.role})
    new_refresh_token, new_jti = create_refresh_token(subject=user.id)
    _consume_mfa_challenge(challenge_row)
    register_or_rotate_user_session(
        db=db,
        user_id=user.id,
        request=request,
        refresh_token_jti=new_jti,
        auth_method="webauthn",
    )
    db.commit()

    _set_auth_cookies(response, access_token, new_refresh_token)
    return {
        "access_token":  access_token,
        "refresh_token": new_refresh_token,
        "token_type":    "bearer",
        "user": {
            "id": user.id, "email": user.email,
            "full_name": user.full_name,
            "role": user.role.value if hasattr(user.role, "value") else str(user.role),
        }
    }


@router.post("/mfa/disable", summary="Desactivar 2FA")
@limiter.limit("5/minute")
def mfa_disable(
    request: Request,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Desactiva 2FA. Requiere confirmar con el código actual."""
    try:
        import pyotp
    except ImportError:
        raise HTTPException(500, "pyotp no instalado")

    code = str(payload.get("code", "")).strip()
    if not current_user.mfa_enabled:
        raise HTTPException(400, "2FA no estaba activado")

    totp  = pyotp.TOTP(decrypt_value(current_user.mfa_secret) or "")
    valid = totp.verify(code, valid_window=1)

    if not valid:
        raise HTTPException(401, "Código incorrecto")

    current_user.mfa_secret = None
    has_passkeys = db.query(WebAuthnCredential.id).filter(
        WebAuthnCredential.user_id == current_user.id,
        WebAuthnCredential.is_active == True,
    ).first() is not None
    current_user.mfa_enabled = bool(has_passkeys)
    db.commit()
    if has_passkeys:
        return {"ok": True, "message": "TOTP desactivado. Tu cuenta mantiene protección con passkeys."}
    return {"ok": True, "message": "2FA desactivado"}

@router.post("/change-password", summary="Cambiar contraseña propia")
def change_password(
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.core.security import verify_password, get_password_hash
    current_pw = payload.get("current_password")
    new_pw     = payload.get("new_password")
    if not current_pw or not new_pw:
        raise HTTPException(400, "current_password y new_password son obligatorios")
    ok, err = validate_password_policy(new_pw)
    if not ok:
        raise HTTPException(400, err)
    if not current_user.hashed_password:
        raise HTTPException(400, "Tu cuenta usa SSO — la contraseña se gestiona externamente")
    if not verify_password(current_pw, current_user.hashed_password):
        raise HTTPException(403, "Contraseña actual incorrecta")
    current_user.hashed_password = get_password_hash(new_pw)
    db.commit()
    return {"ok": True, "message": "Contraseña actualizada correctamente"}

