"""
Auth SSO Router — OAuth2 / OIDC single sign-on providers (Google, Azure AD, Okta, generic OIDC).
"""
from fastapi import APIRouter, Depends, HTTPException, Response, Body, Request, Query
from sqlalchemy.orm import Session

from app.schemas.auth_payloads import SSOCallbackIn
import logging
import secrets
import urllib.parse
import urllib.request

from app.core.outbound_url import validate_outbound_url
import json as _json
import hmac as _hmac
import hashlib as _hashlib
from urllib.parse import urlparse

from app.db.session import get_db
from app.core.config import settings
from app.core.encryption import decrypt_value
from app.core.security import create_access_token, create_refresh_token
from app.services.session_security import register_or_rotate_user_session

import app.services.auth_service as _svc
from app.services.auth_service import (
    issue_mfa_challenge as _issue_mfa_challenge,
    register_sso_state as _register_sso_state,
    consume_sso_state as _consume_sso_state,
    validate_https_discovery_url as _validate_https_discovery_url,
    set_auth_cookies as _set_auth_cookies,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _safe_url(url: str) -> str:
    """Devuelve la URL sin querystring para que no se filtren a logs
    tokens/codes que algunos IdPs incluyen accidentalmente como query params.
    """
    try:
        p = urllib.parse.urlsplit(url)
        return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, "", ""))
    except Exception:
        logger.debug("_safe_url could not parse URL=%r", url, exc_info=True)
        return "<unparseable-url>"


def _normalized_origin(uri: str) -> tuple[str, str, int] | None:
    """Return normalized (scheme, host, port) for origin-style comparisons."""
    try:
        parsed = urlparse(uri.strip())
    except Exception:
        logger.debug("_normalized_origin urlparse failed for uri=%r", uri, exc_info=True)
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


@router.get("/sso/providers", summary="Proveedores SSO activos (para mostrar en login)")
def list_sso_providers(db: Session = Depends(get_db)):
    """Devuelve los proveedores SSO activos para mostrar botones en el login."""
    try:
        return _svc.get_active_sso_providers(db)
    except Exception:
        logger.warning("Failed to load SSO providers", exc_info=True)
        return []


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
        config = _svc.get_sso_config_or_404(db, config_id)

        _allowed = list(settings.ALLOWED_ORIGINS) + [settings.FRONTEND_URL]
        if not _is_allowed_redirect_uri(redirect_uri, _allowed):
            raise HTTPException(400, "redirect_uri no está en la lista de orígenes permitidos")

        state_raw = secrets.token_urlsafe(32)
        sig = _hmac.new(settings.SECRET_KEY.encode(), state_raw.encode(), _hashlib.sha256).hexdigest()
        state = f"{state_raw}.{sig}"
        _register_sso_state(state_raw)

        # Determine authorization endpoint via OIDC discovery document
        if config.oidc_discovery_url:
            try:
                discovery_url = _validate_https_discovery_url(config.oidc_discovery_url)
                with urllib.request.urlopen(discovery_url, timeout=5) as resp:  # noqa: S310
                    disc = _json.loads(resp.read())
                    auth_url = disc.get("authorization_endpoint", "")
            except HTTPException:
                raise
            except _json.JSONDecodeError as exc:
                logger.warning("SSO authorize: discovery document JSON inválido url=%r: %s", _safe_url(config.oidc_discovery_url), exc)
                raise HTTPException(502, "El discovery document del proveedor no es JSON válido")
            except OSError as exc:
                logger.warning("SSO authorize: error de red al obtener discovery url=%r: %s", _safe_url(config.oidc_discovery_url), exc)
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
    payload: SSOCallbackIn = Body(...),
    db: Session = Depends(get_db),
):
    """
    Recibe el authorization code del proveedor OIDC,
    lo intercambia por tokens, extrae el email, y crea/autentica al usuario.
    """
    try:
        config = _svc.get_sso_config_or_404(db, config_id)

        code         = payload.code
        redirect_uri = payload.redirect_uri
        state_param  = payload.state
        if not code or not redirect_uri:
            raise HTTPException(400, "Faltan code o redirect_uri")
        _allowed = list(settings.ALLOWED_ORIGINS) + [settings.FRONTEND_URL]
        if not _is_allowed_redirect_uri(redirect_uri, _allowed):
            raise HTTPException(400, "redirect_uri no está en la lista de orígenes permitidos")

        # Validar state para prevenir CSRF
        if not state_param or "." not in state_param:
            raise HTTPException(400, "State inválido o ausente")
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
                    with urllib.request.urlopen(discovery_url, timeout=5) as resp:  # noqa: S310
                        disc = _json.loads(resp.read())
                        token_url = disc.get("token_endpoint", "")
                except HTTPException:
                    raise
                except _json.JSONDecodeError as exc:
                    logger.warning("SSO callback: discovery JSON inválido url=%r: %s", _safe_url(config.oidc_discovery_url), exc)
                    raise HTTPException(502, "El discovery document del proveedor no es JSON válido")
                except OSError as exc:
                    logger.warning("SSO callback: error de red al obtener discovery url=%r: %s", _safe_url(config.oidc_discovery_url), exc)
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

        req = urllib.request.Request(validate_outbound_url(token_url, field="token_url"), data=token_data,  # noqa: S310
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
                tokens = _json.loads(resp.read())
        except _json.JSONDecodeError as exc:
            logger.warning("SSO callback: token response JSON inválido url=%r: %s", _safe_url(token_url), exc)
            raise HTTPException(502, "El proveedor devolvió una respuesta de token no válida")
        except OSError as exc:
            logger.warning("SSO callback: error de red al obtener tokens url=%r: %s", _safe_url(token_url), exc)
            raise HTTPException(502, f"Error de red al obtener tokens del proveedor SSO: {exc}")

        id_token = tokens.get("id_token", "")
        if not id_token:
            raise HTTPException(502, "El proveedor no devolvió id_token")

        # Verificar firma del id_token usando las claves públicas del proveedor (JWKS)
        try:
            import jwt as _jwt
            # Obtener JWKS URI desde el discovery document para validar la firma
            jwks_uri = None
            if config.oidc_discovery_url:
                try:
                    discovery_url = _validate_https_discovery_url(config.oidc_discovery_url)
                    with urllib.request.urlopen(discovery_url, timeout=5) as resp:  # noqa: S310
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
                raise HTTPException(
                    status_code=502,
                    detail="No se pudo obtener JWKS URI del proveedor SSO. Imposible verificar la firma del id_token.",
                )
        # intentional: chained re-raise preserves context
        except HTTPException:
            raise
        except Exception as jwt_err:
            logger.warning("SSO callback id_token verification failed for config=%s", config_id, exc_info=True)
            raise HTTPException(502, f"id_token inválido o firma incorrecta: {jwt_err}")

        # Extraer email y nombre según configuración del proveedor
        email_claim = config.saml_attribute_email or "email"
        name_claim  = config.saml_attribute_name  or "name"
        email = claims.get(email_claim) or claims.get("email") or claims.get("preferred_username")
        name  = claims.get(name_claim)  or claims.get("name") or email

        if not email:
            raise HTTPException(502, "No se pudo obtener el email del token SSO")

        # P0-4: Email verification check — reject unverified emails.
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
