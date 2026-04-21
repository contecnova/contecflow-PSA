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
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def validate_password_policy(password: str) -> tuple[bool, Optional[str]]:
    """Validate password against configured policy and return (ok, error_message)."""
    if len(password) < settings.MIN_PASSWORD_LENGTH:
        return False, f"La contraseña debe tener al menos {settings.MIN_PASSWORD_LENGTH} caracteres"
    if settings.PASSWORD_REQUIRE_UPPERCASE and not re.search(r"[A-Z]", password):
        return False, "La contraseña debe incluir al menos una letra mayúscula"
    if settings.PASSWORD_REQUIRE_LOWERCASE and not re.search(r"[a-z]", password):
        return False, "La contraseña debe incluir al menos una letra minúscula"
    if settings.PASSWORD_REQUIRE_DIGIT and not re.search(r"\d", password):
        return False, "La contraseña debe incluir al menos un número"
    if settings.PASSWORD_REQUIRE_SPECIAL and not re.search(r"[^A-Za-z0-9]", password):
        return False, "La contraseña debe incluir al menos un carácter especial"
    return True, None


def create_access_token(subject: str, extra: dict = None, expires_delta: timedelta = None) -> str:
    default_minutes = min(settings.ACCESS_TOKEN_EXPIRE_MINUTES, settings.ACCESS_TOKEN_MAX_MINUTES)
    delta = expires_delta if expires_delta is not None else timedelta(minutes=default_minutes)
    expire = datetime.now(timezone.utc) + delta
    payload = {"sub": subject, "exp": expire, "type": "access"}
    if extra:
        payload.update(extra)
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


def create_refresh_token(subject: str) -> tuple[str, str]:
    """Returns (token, jti). The jti must be stored per-user for rotation validation."""
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
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
        except Exception:
            kid = None

        if kid and kid in keys:
            return jwt.decode(token, keys[kid], algorithms=[ALGORITHM])

        # Fallback for legacy tokens without kid or stale kid values
        for key in keys.values():
            try:
                return jwt.decode(token, key, algorithms=[ALGORITHM])
            except Exception:
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
