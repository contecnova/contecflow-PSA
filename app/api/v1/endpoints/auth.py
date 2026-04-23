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


logger = logging.getLogger(__name__)

router = APIRouter()
import app.services.auth_service as _svc
from app.services.auth_service import (
    soc_svc as _soc_svc,
    client_ip as _client_ip,
    mfa_challenge_query as _mfa_challenge_query,
    issue_mfa_challenge as _issue_mfa_challenge,
    read_mfa_challenge as _read_mfa_challenge,
    consume_mfa_challenge as _consume_mfa_challenge,
    resolve_sso_role as _resolve_sso_role,
    resolve_sso_organization_id as _resolve_sso_organization_id,
    validate_https_discovery_url as _validate_https_discovery_url,
    get_sso_redis as _get_sso_redis,
    register_sso_state as _register_sso_state,
    consume_sso_state as _consume_sso_state,
    login_bucket as _login_bucket,
    login_lock_ttl as _login_lock_ttl,
    register_login_failure as _register_login_failure,
    clear_login_failure as _clear_login_failure,
    password_reset_bucket as _password_reset_bucket,
    register_password_reset_request as _register_password_reset_request,
    b64url_encode as _b64url_encode,
    b64url_decode as _b64url_decode,
    create_ephemeral_token as _create_ephemeral_token,
    read_ephemeral_token as _read_ephemeral_token,
    set_auth_cookies as _set_auth_cookies,
    current_refresh_jti as _current_refresh_jti,
    issue_password_reset_token as _issue_password_reset_token,
    send_password_reset_email as _send_password_reset_email,
    SSO_STATE_TTL as _SSO_STATE_TTL,
    SSO_KEY_PREFIX as _SSO_KEY_PREFIX,
    LOGIN_FAIL_PREFIX as _LOGIN_FAIL_PREFIX,
    LOGIN_LOCK_PREFIX as _LOGIN_LOCK_PREFIX,
    PASSWORD_RESET_TTL_SECONDS as _PASSWORD_RESET_TTL_SECONDS,
    PASSWORD_RESET_REQUEST_WINDOW_SECONDS as _PASSWORD_RESET_REQUEST_WINDOW_SECONDS,
    PASSWORD_RESET_REQUEST_MAX_PER_WINDOW as _PASSWORD_RESET_REQUEST_MAX_PER_WINDOW,
    COOKIE_OPTS as _COOKIE_OPTS,
)


def _normalized_origin(uri: str) -> tuple[str, str, int] | None:
    """Return normalized (scheme, host, port) for origin-style comparisons."""
    try:
        parsed = urlparse(uri.strip())
    except Exception:
        return None
    if parsed.scheme not in {"http", "https"}:
        return None
    if not parsed.hostname:
        return None
    if parsed.username or parsed.password:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    return (parsed.scheme, parsed.hostname.lower(), port)


def _is_allowed_redirect_uri(redirect_uri: str, allowed_origins: list[str]) -> bool:
    target_origin = _normalized_origin(redirect_uri)
    if not target_origin:
        return False
    allowed = {
        origin
        for origin in (_normalized_origin(item) for item in allowed_origins if item)
        if origin is not None
    }
    return target_origin in allowed


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
    has_passkeys = _svc.user_has_passkeys(db, user.id)
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
    _svc.complete_password_reset(db, user, get_password_hash(payload.new_password))

    return {"ok": True, "message": "Contraseña actualizada correctamente"}


@router.get("/sessions/active", response_model=list[ActiveSessionOut], summary="Panel de sesiones activas del usuario")
def list_active_sessions(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_jti = _current_refresh_jti(request)
    now = datetime.now(timezone.utc)
    sessions = _svc.get_active_user_sessions(db, current_user.id, now)
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
    return _svc.revoke_one_session(db, session_id, current_user.id)


@router.post("/sessions/revoke-all", summary="Revocar todas las sesiones activas del usuario")
def revoke_all_sessions(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_jti = _current_refresh_jti(request)
    revoked = _svc.revoke_all_user_sessions_except_current(db, current_user.id, current_jti)
    return {"ok": True, "revoked": revoked}


@router.get("/me", response_model=UserPublic)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/sso/providers", summary="Proveedores SSO activos (para mostrar en login)")
def list_sso_providers(db: Session = Depends(get_db)):
    """Devuelve los proveedores SSO activos para mostrar botones en el login."""
    try:
        return _svc.get_active_sso_providers(db)
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
    saml_configs = _svc.get_saml_health(db)
    return {
        "metadata_url": f"{settings.BASE_URL}/api/v1/auth/saml/metadata",
        "configs": saml_configs,
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
        import secrets
        import urllib.parse

        config = _svc.get_sso_config_or_404(db, config_id)

        _allowed = list(settings.ALLOWED_ORIGINS) + [settings.FRONTEND_URL]
        if not _is_allowed_redirect_uri(redirect_uri, _allowed):
            raise HTTPException(400, "redirect_uri no está en la lista de orígenes permitidos")

        state_raw = secrets.token_urlsafe(32)
        import hmac as _hmac
        import hashlib as _hashlib
        sig = _hmac.new(settings.SECRET_KEY.encode(), state_raw.encode(), _hashlib.sha256).hexdigest()
        state = f"{state_raw}.{sig}"
        _register_sso_state(state_raw)

        # Determine authorization endpoint via OIDC discovery document
        if config.oidc_discovery_url:
            try:
                import urllib.request
                import json as _json
                discovery_url = _validate_https_discovery_url(config.oidc_discovery_url)
                with urllib.request.urlopen(discovery_url, timeout=5) as resp:
                    disc = _json.loads(resp.read())
                    auth_url = disc.get("authorization_endpoint", "")
            except HTTPException:
                raise
            except _json.JSONDecodeError as exc:
                logger.warning("SSO authorize: discovery document JSON inválido url=%r: %s", config.oidc_discovery_url, exc)
                raise HTTPException(502, "El discovery document del proveedor no es JSON válido")
            except OSError as exc:
                logger.warning("SSO authorize: error de red al obtener discovery url=%r: %s", config.oidc_discovery_url, exc)
                raise HTTPException(502, "No se pudo obtener el discovery document")
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
        import urllib.request
        import urllib.parse
        import json as _json

        config = _svc.get_sso_config_or_404(db, config_id)

        code         = payload.get("code")
        redirect_uri = payload.get("redirect_uri")
        state_param  = payload.get("state")
        if not code or not redirect_uri:
            raise HTTPException(400, "Faltan code o redirect_uri")
        _allowed = list(settings.ALLOWED_ORIGINS) + [settings.FRONTEND_URL]
        if not _is_allowed_redirect_uri(redirect_uri, _allowed):
            raise HTTPException(400, "redirect_uri no está en la lista de orígenes permitidos")

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
                except HTTPException:
                    raise
                except _json.JSONDecodeError as exc:
                    logger.warning("SSO callback: discovery JSON inválido url=%r: %s", config.oidc_discovery_url, exc)
                    raise HTTPException(502, "El discovery document del proveedor no es JSON válido")
                except OSError as exc:
                    logger.warning("SSO callback: error de red al obtener discovery url=%r: %s", config.oidc_discovery_url, exc)
                    raise HTTPException(502, "No se pudo obtener el token_endpoint")
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
        except _json.JSONDecodeError as exc:
            logger.warning("SSO callback: token response JSON inválido url=%r: %s", token_url, exc)
            raise HTTPException(502, "El proveedor devolvió una respuesta de token no válida")
        except OSError as exc:
            logger.warning("SSO callback: error de red al obtener tokens url=%r: %s", token_url, exc)
            raise HTTPException(502, f"Error de red al obtener tokens del proveedor SSO: {exc}")

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
                except (OSError, _json.JSONDecodeError) as exc:
                    logger.warning(
                        "SSO callback: no se pudo obtener JWKS URI url=%r: %s",
                        config.oidc_discovery_url,
                        exc,
                    )

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
        except HTTPException:
            raise
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
        user = _svc.create_or_update_sso_user(db, config, email, name, claims)

        # Enforce MFA for SSO users too (TOTP or WebAuthn passkeys).
        has_totp    = bool(user.mfa_enabled and user.mfa_secret)
        has_passkeys = _svc.user_has_passkeys(db, user.id)
        if has_totp or has_passkeys:
            methods = []
            if has_totp:
                methods.append("totp")
            if has_passkeys:
                methods.append("webauthn")
            return {
                "token_type":         "bearer",
                "mfa_required":       True,
                "mfa_challenge_token": _issue_mfa_challenge(db, user),
                "mfa_methods":        methods,
                "user": {
                    "id": user.id, "email": user.email,
                    "full_name": user.full_name,
                    "role": user.role.value if hasattr(user.role, "value") else str(user.role),
                },
            }

        access_token = create_access_token(subject=user.id, extra={"role": user.role})
        new_refresh_token, new_jti = create_refresh_token(subject=user.id)
        register_or_rotate_user_session(
            db=db,
            user_id=user.id,
            request=request,
            refresh_token_jti=new_jti,
            auth_method="sso",
        )
        _svc.commit_db(db)
        _set_auth_cookies(response, access_token, new_refresh_token)
        return {
            "access_token":  access_token,
            "refresh_token": new_refresh_token,
            "token_type":    "bearer",
            "user": {
                "id": user.id, "email": user.email,
                "full_name": user.full_name,
                "role": user.role.value if hasattr(user.role, "value") else str(user.role),
            },
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

    try:
        import io
        import base64
        import qrcode
        secret = pyotp.random_base32()
        totp   = pyotp.TOTP(secret)
        uri    = totp.provisioning_uri(
            name=current_user.email,
            issuer_name=settings.PROJECT_NAME,
        )
        qr_img = qrcode.make(uri)
        buf = io.BytesIO()
        qr_img.save(buf, format="PNG")
        qr_b64 = base64.b64encode(buf.getvalue()).decode()
        qr_url = f"data:image/png;base64,{qr_b64}"
        enc_secret = encrypt_value(secret)
        current_user.mfa_secret = enc_secret
        current_user.mfa_enabled = False
        db.add(current_user)
        _svc.commit_db(db)
        return {
            "secret":           secret,
            "provisioning_uri": uri,
            "qr_url":           qr_url,
            "issuer":           settings.PROJECT_NAME,
            "email":            current_user.email,
        }
    except ImportError as ie:
        logger.error("ImportError en MFA setup: %s", ie, exc_info=True)
        raise HTTPException(500, f"Dependencia faltante en 2FA: {ie}")
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error("MFA setup error: %s\nTraceback:\n%s", e, tb)
        # Devuelve el mensaje real del error en modo debug, genérico en prod
        msg = str(e) if settings.DEBUG or os.environ.get("DEBUG") else "Error al configurar 2FA"
        raise HTTPException(500, msg)


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
    _svc.commit_db(db)

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

    user = _svc.lookup_user_by_id_active(db, user_id)
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
    _svc.commit_db(db)

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

    existing = _svc.get_active_user_credentials(db, current_user.id)
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
    _svc.upsert_webauthn_credential(
        db=db,
        current_user_id=current_user.id,
        credential_id=credential_id,
        public_key=_b64url_encode(verification.credential_public_key),
        sign_count=int(verification.sign_count),
        transports=json.dumps(credential.get("response", {}).get("transports", [])),
        nickname=nickname,
    )
    current_user.mfa_enabled = True
    _svc.commit_db(db)
    return {"ok": True, "message": "Passkey registrada correctamente"}


@router.get("/mfa/webauthn/credentials", summary="Listar passkeys registradas")
def webauthn_list_credentials(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    creds = _svc.get_active_user_credentials(db, current_user.id)
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
    cred = _svc.get_active_webauthn_credential(db, credential_id, current_user.id)
    if not cred:
        raise HTTPException(404, "Passkey no encontrada")
    cred.is_active = False
    remaining = _svc.has_remaining_active_credentials(db, current_user.id, credential_id)
    if not remaining and not current_user.mfa_secret:
        current_user.mfa_enabled = False
    _svc.commit_db(db)
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
    user = _svc.lookup_user_by_id_active(db, user_id)
    if not user:
        raise HTTPException(404, "Usuario no encontrado")

    creds = _svc.get_active_user_credentials(db, user.id)
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

    cred = _svc.get_webauthn_credential_for_auth(db, user_id, credential_id)
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

    user = _svc.lookup_user_by_id_active(db, user_id)
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
    _svc.commit_db(db)

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
    has_passkeys = _svc.user_has_passkeys(db, current_user.id)
    current_user.mfa_enabled = bool(has_passkeys)
    _svc.commit_db(db)
    if has_passkeys:
        return {"ok": True, "message": "TOTP desactivado. Tu cuenta mantiene protección con passkeys."}
    return {"ok": True, "message": "2FA desactivado"}


from fastapi import Request
from app.services.auth_service import read_mfa_challenge

@router.post("/change-password", summary="Cambiar contraseña propia")
@limiter.limit("5/minute")
def change_password(
    request: Request,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.core.security import verify_password, get_password_hash
    current_pw = payload.get("current_password")
    new_pw     = payload.get("new_password")
    mfa_token  = payload.get("mfa_challenge_token")
    # Si el usuario tiene MFA activo, requerimos challenge reciente
    if current_user.mfa_enabled:
        if not mfa_token:
            raise HTTPException(401, "Debes completar un challenge MFA para cambiar la contraseña")
        try:
            challenge_data, challenge_row = read_mfa_challenge(db, mfa_token)
        except Exception as e:
            raise HTTPException(401, f"MFA inválido: {str(e)}")
        # Consumo challenge (ya lo hace read_mfa_challenge)
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

