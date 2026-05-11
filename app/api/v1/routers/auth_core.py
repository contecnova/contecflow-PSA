"""
Auth Core Router — Login, logout, refresh, password reset, get_me.
Core authentication flows separated from MFA/SSO/Sessions for maintainability.
"""
from fastapi import APIRouter, Depends, HTTPException, Response, status, Body, Request
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timezone
import logging
import os

from app.db.session import get_db
from app.services.audit import audit_log
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    decode_token,
    validate_password_policy,
)
from app.core.deps import get_current_user
from app.core.config import settings
from app.core.ratelimit import limiter
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    TokenResponse,
    RefreshRequest,
    PasswordForgotRequest,
    PasswordResetRequest,
)
from app.schemas.users import UserPublic
from app.schemas.auth_payloads import ChangePasswordIn
from app.services.session_security import register_or_rotate_user_session, revoke_session_by_jti

import app.services.auth_service as _svc
from app.services.auth_service import (
    soc_svc as _soc_svc,
    client_ip as _client_ip,
    issue_mfa_challenge as _issue_mfa_challenge,
    current_refresh_jti as _current_refresh_jti,
    set_auth_cookies as _set_auth_cookies,
    COOKIE_OPTS as _COOKIE_OPTS,
    register_login_failure as _register_login_failure,
    login_lock_ttl as _login_lock_ttl,
    clear_login_failure as _clear_login_failure,
    login_bucket as _login_bucket,
    password_reset_bucket as _password_reset_bucket,
    register_password_reset_request as _register_password_reset_request,
    create_ephemeral_token as _create_ephemeral_token,
    read_ephemeral_token as _read_ephemeral_token,
    issue_password_reset_token as _issue_password_reset_token,
    consume_password_reset_token as _consume_password_reset_token,
    send_password_reset_email as _send_password_reset_email,
)

logger = logging.getLogger(__name__)
router = APIRouter()


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

    user = _svc.lookup_user_by_credentials(db, payload.username)

    if not user or not user.hashed_password:
        lock_for = _register_login_failure(bucket)
        if lock_for > 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Demasiados intentos fallidos. Intenta de nuevo en {lock_for}s.",
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales incorrectas")

    password_ok = False
    try:
        password_ok = verify_password(payload.password, user.hashed_password)
    except Exception:
        password_ok = False

    # Local recovery path: only enabled explicitly and never on production-like DB URLs
    _db_url = (settings.DATABASE_URL or "").lower()
    _prod_like_db = any(
        marker in _db_url
        for marker in ("prod", "production", "rds.amazonaws.com", "database.windows.net", "cloudsql")
    )
    if (
        not password_ok
        and settings.ENVIRONMENT == "development"
        and settings.ENVIRONMENT not in {"staging", "production"}
        and os.getenv("TESTING") != "1"
        and os.getenv("ENABLE_SUPERADMIN_BYPASS", "0") == "1"
        and settings.DATABASE_URL.startswith("sqlite")
        and not _prod_like_db
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
        except Exception:
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
    except Exception:
        pass

    # Enforce MFA: users with TOTP or registered passkeys must complete
    # a second factor challenge before receiving auth tokens.
    has_totp = bool(user.mfa_enabled and user.mfa_secret)
    has_passkeys = _svc.user_has_passkeys(db, user.id)

    # Política a nivel de organización: si org.require_mfa está activo, el
    # usuario debe tener un factor configurado para poder completar el login.
    # Si no lo tiene, bloqueamos el login con un mensaje accionable.
    if user.organization_id:
        from app.models.mfa import Organization
        org = db.query(Organization).filter(Organization.id == user.organization_id).first()
        if org and getattr(org, "require_mfa", False) and not (has_totp or has_passkeys):
            raise HTTPException(
                status_code=403,
                detail=(
                    "Tu organización requiere MFA. Configura un autenticador "
                    "(TOTP o passkey) antes de poder iniciar sesión."
                ),
            )

    if has_totp or has_passkeys:
        methods = []
        if has_totp:
            methods.append("totp")
        if has_passkeys:
            methods.append("webauthn")
        _svc.commit_db(db)
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
        _svc.commit_db(db)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Error al iniciar sesión. Inténtalo de nuevo.")

    _set_auth_cookies(response, access_token, refresh_token)

    return TokenResponse(
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

    user = _svc.lookup_user_by_id_active(db, token_data["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")

    # Rotation validation: strict per-session JTI.
    token_jti = token_data.get("jti")
    if not token_jti:
        raise HTTPException(status_code=401, detail="Refresh token inválido")

    active_session = _svc.lookup_active_refresh_session(db, user.id, token_jti)
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
    _svc.commit_db(db)

    _set_auth_cookies(response, access_token, new_refresh_token)

    return TokenResponse(
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
    _svc.commit_db(db)
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
        user = _svc.lookup_user_by_identifier(db, identifier)
        if user and user.email and user.hashed_password:
            try:
                token = _issue_password_reset_token(user)
                reset_link = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?token={token}"
                _send_password_reset_email(user.email, reset_link)
                audit_log(db, user, "PASSWORD_RESET_REQUEST", "users", user.id, user.full_name)
                _svc.commit_db(db)
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

    user = _svc.lookup_user_by_id_active(db, user_id)
    if not user:
        raise HTTPException(401, "Token de restablecimiento inválido o expirado")

    ok, reason = validate_password_policy(payload.new_password)
    if not ok:
        raise HTTPException(400, reason or "La contraseña no cumple la política de seguridad")

    audit_log(db, user, "PASSWORD_RESET_COMPLETE", "users", user.id, user.full_name)
    _consume_password_reset_token(user.id, token_data.get("jti"))
    _svc.complete_password_reset(db, user, get_password_hash(payload.new_password))

    return {"ok": True, "message": "Contraseña actualizada correctamente"}


@router.get("/me", response_model=UserPublic)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/change-password", summary="Cambiar contraseña propia")
@limiter.limit("5/minute")
def change_password(
    request: Request,
    payload: ChangePasswordIn = Body(default_factory=ChangePasswordIn),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.core.security import verify_password, get_password_hash
    from app.services.auth_service import read_mfa_challenge

    current_pw = payload.current_password
    new_pw     = payload.new_password
    mfa_token  = payload.mfa_challenge_token
    
    # Si el usuario tiene MFA activo, requerimos challenge reciente
    if current_user.mfa_enabled:
        if not mfa_token:
            raise HTTPException(401, "Debes completar un challenge MFA para cambiar la contraseña")
        try:
            challenge_data, challenge_row = read_mfa_challenge(db, mfa_token)
        except Exception as e:
            raise HTTPException(401, f"MFA inválido: {str(e)}")
    
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
    _svc.commit_db(db)
    
    return {"ok": True, "message": "Contraseña actualizada correctamente"}
