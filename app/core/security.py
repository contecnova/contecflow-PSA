import bcrypt
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from app.core.config import settings
from app.services.key_management import get_jwt_signing_key, get_jwt_verification_keys

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def get_password_hash(password: str) -> str:
    # BCRYPT_ROUNDS configurable; default 12. Subir a 14+ en producción.
    rounds = getattr(settings, "BCRYPT_ROUNDS", 12)
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=rounds)).decode()


def validate_password_policy(password: str, db=None, org_id: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """Validate password against configured policy and return (ok, error_message).

    When ``db`` is provided the policy resolves through the runtime-flags
    service (UI overrides → env fallback). When called without ``db`` (legacy
    callers) it falls back to the env values directly.
    """
    if db is not None:
        from app.services.settings_service import get_runtime_namespace
        _p = get_runtime_namespace(db, {
            "MIN_PASSWORD_LENGTH": "int",
            "PASSWORD_REQUIRE_UPPERCASE": "bool",
            "PASSWORD_REQUIRE_LOWERCASE": "bool",
            "PASSWORD_REQUIRE_DIGIT": "bool",
            "PASSWORD_REQUIRE_SPECIAL": "bool",
        }, org_id=org_id)
    else:
        _p = settings
    if len(password) < _p.MIN_PASSWORD_LENGTH:
        return False, f"La contraseña debe tener al menos {_p.MIN_PASSWORD_LENGTH} caracteres"
    if _p.PASSWORD_REQUIRE_UPPERCASE and not re.search(r"[A-Z]", password):
        return False, "La contraseña debe incluir al menos una letra mayúscula"
    if _p.PASSWORD_REQUIRE_LOWERCASE and not re.search(r"[a-z]", password):
        return False, "La contraseña debe incluir al menos una letra minúscula"
    if _p.PASSWORD_REQUIRE_DIGIT and not re.search(r"\d", password):
        return False, "La contraseña debe incluir al menos un número"
    if _p.PASSWORD_REQUIRE_SPECIAL and not re.search(r"[^A-Za-z0-9]", password):
        return False, "La contraseña debe incluir al menos un carácter especial"
    return True, None


_JWT_RESERVED_CLAIMS = {"sub", "exp", "iat", "type", "jti"}


def _token_ttl_minutes(db=None, org_id: Optional[str] = None) -> int:
    if db is not None:
        from app.services.settings_service import get_runtime_int
        expire = get_runtime_int(db, "ACCESS_TOKEN_EXPIRE_MINUTES", org_id) or settings.ACCESS_TOKEN_EXPIRE_MINUTES
        max_m  = get_runtime_int(db, "ACCESS_TOKEN_MAX_MINUTES",    org_id) or settings.ACCESS_TOKEN_MAX_MINUTES
    else:
        expire = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        max_m  = settings.ACCESS_TOKEN_MAX_MINUTES
    return min(expire, max_m)


def _refresh_ttl_days(db=None, org_id: Optional[str] = None) -> int:
    if db is not None:
        from app.services.settings_service import get_runtime_int
        return get_runtime_int(db, "REFRESH_TOKEN_EXPIRE_DAYS", org_id) or settings.REFRESH_TOKEN_EXPIRE_DAYS
    return settings.REFRESH_TOKEN_EXPIRE_DAYS


def create_access_token(subject: str, extra: dict = None, expires_delta: timedelta = None, db=None, org_id: Optional[str] = None) -> str:
    delta = expires_delta if expires_delta is not None else timedelta(minutes=_token_ttl_minutes(db, org_id))
    expire = datetime.now(timezone.utc) + delta
    safe_extra = {k: v for k, v in (extra or {}).items() if k not in _JWT_RESERVED_CLAIMS}
    payload = {"sub": subject, "exp": expire, "type": "access", **safe_extra}
    kid, key = get_jwt_signing_key()
    return jwt.encode(payload, key, algorithm=ALGORITHM, headers={"kid": kid})


def create_mfa_challenge_token(subject: str) -> str:
    """Short-lived token used to complete MFA after password validation."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=5)
    jti = str(uuid.uuid4())
    payload = {
        "sub": subject,
        "exp": expire,
        "type": "mfa_challenge",
        "purpose": "login",
        "jti": jti,
    }
    kid, key = get_jwt_signing_key()
    return jwt.encode(payload, key, algorithm=ALGORITHM, headers={"kid": kid}), jti


def create_refresh_token(subject: str, db=None, org_id: Optional[str] = None) -> tuple[str, str]:
    """Returns (token, jti). The jti must be stored per-user for rotation validation."""
    expire = datetime.now(timezone.utc) + timedelta(days=_refresh_ttl_days(db, org_id))
    jti = str(uuid.uuid4())
    kid, key = get_jwt_signing_key()
    token = jwt.encode(
        {"sub": subject, "exp": expire, "type": "refresh", "jti": jti},
        key,
        algorithm=ALGORITHM,
        headers={"kid": kid},
    )
    return token, jti


def decode_token(token: str) -> Optional[dict]:
    try:
        keys = get_jwt_verification_keys()
        kid = None
        try:
            kid = jwt.get_unverified_header(token).get("kid")
        # intentional: best-effort fallback, log noise outweighs diagnostic value
        except Exception:
            kid = None

        if kid and kid in keys:
            return jwt.decode(token, keys[kid], algorithms=[ALGORITHM])

        # Fallback for legacy tokens without kid or stale kid values
        for key in keys.values():
            try:
                return jwt.decode(token, key, algorithms=[ALGORITHM])
            # intentional: best-effort fallback, log noise outweighs diagnostic value
            except Exception:  # noqa: S112
                continue
        return None
    except jwt.ExpiredSignatureError:
        logger.debug("JWT token expired")
        return None
    except JWTError as e:
        logger.warning(f"JWT decode failed: {e}")
        return None


def verify_client_token(token: str, db):
    """Verify a client portal JWT token and return the ClientUser.

    Uses the dedicated CLIENT_PORTAL_SECRET key only — never the backend
    JWT signing keys — so client tokens cannot be accepted as backend
    user tokens and vice-versa.
    """
    from app.models.client_portal import ClientUser
    try:
        from jose import jwt as jose_jwt
        payload = jose_jwt.decode(token, settings.CLIENT_PORTAL_SECRET, algorithms=["HS256"])
        if payload.get("type") != "client":
            return None
        uid = payload.get("sub")
        if not uid:
            return None
        return db.query(ClientUser).filter(ClientUser.id == uid).first()
    except Exception as e:
        logger.debug(f"Client token validation failed: {e}", exc_info=False)
        return None


def verify_admin_or_governance_role(user) -> None:
    """Verify that user has admin or governance role. Raises HTTPException if not."""
    from fastapi import HTTPException, status

    # Check if user is admin or governance
    if getattr(user, 'is_superadmin', False):
        return
    if getattr(user, 'role', None) in ('admin', 'governance'):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin or governance role required"
    )
