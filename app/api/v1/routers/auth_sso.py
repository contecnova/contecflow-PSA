"""
Auth SSO Router — OAuth2 / OIDC single sign-on providers (Google, Azure AD, Okta, generic OIDC).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, Body, Request, Query
from sqlalchemy.orm import Session

from app.schemas.auth_payloads import SSOCallbackIn
import logging
import secrets
import urllib.parse
import urllib.request

from app.core.outbound_url import abrir, validate_outbound_url
from app.core.ratelimit import limiter
import json as _json
import hmac as _hmac
import hashlib as _hashlib
import base64 as _b64
from urllib.parse import urlparse

from app.db.session import get_db
from app.core.config import settings
from app.core.encryption import decrypt_value
from app.services.session_security import register_or_rotate_user_session

import app.services.auth_service as _svc
from app.services.auth_service import (
    issue_mfa_challenge as _issue_mfa_challenge,
    register_sso_state as _register_sso_state,
    consume_sso_state_payload as _consume_sso_state_payload,
    validate_https_discovery_url as _validate_https_discovery_url,
)
from app.api.cookies_de_sesion import set_auth_cookies as _set_auth_cookies
from app.core.errores import ErrorDeDominio

logger = logging.getLogger(__name__)
router = APIRouter()


def _holgura_sso() -> int:
    from app.services.auth_service import sso_holgura_de_reloj
    return sso_holgura_de_reloj()


def _timeout() -> float:
    """Auditoria 2026-11: antes 5 y 10 s escritos aqui."""
    from app.services.auth_service import sso_timeout_http
    return sso_timeout_http()


def _descubrimiento(config) -> dict:
    """El documento OIDC del proveedor (authorization, token, jwks, issuer)."""
    if not config.oidc_discovery_url:
        raise HTTPException(400, "Falta oidc_discovery_url")
    url = _validate_https_discovery_url(config.oidc_discovery_url)
    try:
        with abrir(url, timeout=_timeout()) as resp:  # noqa: S310
            return _json.loads(resp.read())
    except _json.JSONDecodeError as exc:
        logger.warning("SSO: discovery JSON inválido url=%r: %s", _safe_url(config.oidc_discovery_url), exc)
        raise HTTPException(502, "El discovery document del proveedor no es JSON válido")
    except OSError as exc:
        logger.warning("SSO: error de red al obtener discovery url=%r: %s", _safe_url(config.oidc_discovery_url), exc)
        raise HTTPException(502, "No se pudo obtener el discovery document")


_CLIENTES_JWKS: dict = {}


def _cliente_jwks(jwks_uri: str):
    """PyJWKClient guarda las claves; antes se creaba uno por inicio de sesion."""
    import jwt as _jwt
    if jwks_uri not in _CLIENTES_JWKS:
        _CLIENTES_JWKS[jwks_uri] = _jwt.PyJWKClient(jwks_uri, cache_keys=True)
    return _CLIENTES_JWKS[jwks_uri]


_ALGORITMOS = ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "PS256", "PS384", "PS512"]


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
def list_sso_providers(
    request: Request,
    email: Optional[str] = Query(None, max_length=320),
    domain: Optional[str] = Query(None, max_length=255),
    db: Session = Depends(get_db),
):
    """Devuelve los proveedores SSO activos para mostrar botones en el login.

    Segunda auditoría 2026-11 (#11): en modo `email_selector` hace falta
    `email` o `domain` y solo salen los proveedores de ese dominio; sin él,
    ninguno (la lista completa enumeraba los proveedores de todas las empresas).
    """
    try:
        return _svc.get_active_sso_providers(db, request, dominio=domain or email)
    except Exception:
        logger.warning("Failed to load SSO providers", exc_info=True)
        return []


@router.get("/sso/{config_id}/authorize", summary="Iniciar flujo OAuth2 OIDC")
@limiter.limit(settings.SSO_RATE_LIMIT)
def sso_authorize(
    request: Request,
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

        # PKCE S256 (auditoría 2026-08, P2-13). Sin él, un `code` interceptado
        # —en el historial del navegador, en un log de proxy, por una app
        # maliciosa que registre el esquema de redirección— es canjeable por
        # tokens sin más. Con PKCE hay que presentar además el verificador, que
        # nunca sale de este servidor.
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = (
            _b64.urlsafe_b64encode(_hashlib.sha256(code_verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )

        # El nonce ya se generaba pero NO se verificaba en el callback, así que no
        # protegía de nada. Se guarda para poder compararlo.
        nonce = secrets.token_urlsafe(16)

        _register_sso_state(state_raw, {"code_verifier": code_verifier, "nonce": nonce})

        # Determine authorization endpoint via OIDC discovery document
        auth_url = _descubrimiento(config).get("authorization_endpoint", "")
        if not auth_url:
            raise HTTPException(502, "El discovery document no trae authorization_endpoint")

        # Auditoria 2026-11: los scopes guardados se ignoraban.
        scope = config.oidc_scopes or "openid profile email"
        if "openid" not in scope.split():
            scope = "openid " + scope
        params = {
            "client_id":             config.oidc_client_id,
            "response_type":        "code",
            "scope":                 scope,
            "redirect_uri":          redirect_uri,
            "state":                 state,
            "nonce":                 nonce,
            "code_challenge":        code_challenge,
            "code_challenge_method": "S256",
        }
        url = auth_url + "?" + urllib.parse.urlencode(params)
        return {"authorization_url": url, "state": state, "provider": config.provider}
    except (HTTPException, ErrorDeDominio):
        raise
    except Exception as e:
        logger.error("SSO authorize error: %s", e, exc_info=True)
        raise HTTPException(500, "Error al iniciar el flujo SSO. Comprueba la configuración del proveedor.")



# ── Fases del callback de SSO ────────────────────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 18). `sso_callback` eran 212 lineas de complejidad
# 32 en el camino de AUTENTICACION, con cuatro fases encadenadas dentro de un
# unico `try`. Las tres primeras son controles de seguridad —el `state` firmado
# contra CSRF, el intercambio del codigo, la verificacion del `nonce` contra
# replay del id_token— y solo se podian ejercitar levantando el callback entero
# con la red simulada.
#
# Ahora cada fase es una funcion, con el cuerpo movido verbatim, y cada rechazo
# se puede probar por separado. El `try/except` sigue en el endpoint, donde
# estaba: envolver cada fase por separado cambiaria como se traducen los errores
# a respuestas HTTP, y eso no es parte de esta reorganizacion.


def _validar_peticion_y_consumir_estado(payload) -> dict:
    """Valida `code`, `redirect_uri` y el `state` firmado; consume el estado.

    Devuelve lo que se guardo con el estado: el verificador de PKCE y el `nonce`
    esperado. Cada `raise` de aqui es un control:

      · sin `code` o `redirect_uri`  -> peticion incompleta
      · `redirect_uri` no permitido  -> impide redirigir el token a un tercero
      · `state` ausente o sin firma  -> falta la proteccion contra CSRF
      · firma HMAC que no cuadra     -> `state` manipulado
      · estado ya consumido          -> replay del propio callback

    El estado es de un solo uso a proposito: `_consume_sso_state_payload` lo
    borra al leerlo.
    """
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
    # Consume el estado (evita replay) Y recupera lo que se guardó con él:
    # el verificador de PKCE y el nonce esperado.
    sso_payload = _consume_sso_state_payload(state_raw)
    if sso_payload is None:
        raise HTTPException(400, "State expirado o ya utilizado")
    # El verificador de PKCE y el nonce los lee quien llama del propio payload.
    return sso_payload


def _resolver_token_endpoint(config) -> str:
    """URL del endpoint de token del proveedor.

    Tres proveedores la tienen fija por construccion —Azure AD, Okta y Google— y
    el resto hay que descubrirla en su documento OIDC. Ese descubrimiento es una
    llamada de red y por eso trae su propio manejo de errores: una respuesta que
    no es JSON y un fallo de red se traducen a 502 distintos, porque son
    problemas distintos para quien lee el registro.
    """
    if config.provider == "azure_ad":
        tenant    = config.oidc_discovery_url.split("/")[3] if config.oidc_discovery_url else "common"
        token_url = f"{settings.MICROSOFT_OAUTH_BASE}/{tenant}/oauth2/v2.0/token"
    elif config.provider == "okta":
        base      = config.oidc_discovery_url.replace("/.well-known/openid-configuration", "") if config.oidc_discovery_url else ""
        token_url = f"{base}/v1/token"
    elif config.provider == "google":
        token_url = settings.GOOGLE_TOKEN_URL
    else:
        token_url = _descubrimiento(config).get("token_endpoint", "")
        if not token_url:
            raise HTTPException(502, "No se pudo obtener el token_endpoint")
    return token_url


def _intercambiar_codigo_por_tokens(config, code: str, redirect_uri: str, code_verifier):
    """Canjea el authorization code por los tokens en el proveedor.

    `code_verifier` es el de PKCE: sin el, un `code` interceptado seria
    canjeable por quien lo capturase.
    """
    token_url = _resolver_token_endpoint(config)

    # Intercambiar code por tokens
    _token_params = {
        "grant_type":    "authorization_code",
        "code":          code,
        "redirect_uri":  redirect_uri,
        "client_id":     config.oidc_client_id,
        "client_secret": decrypt_value(config.oidc_client_secret) if config.oidc_client_secret else "",
    }
    # PKCE: el proveedor comprueba que el verificador corresponde al
    # challenge que se envió en /authorize. Sólo se manda si el estado lo
    # traía, para no romper una transacción iniciada antes de este cambio.
    if code_verifier:
        _token_params["code_verifier"] = code_verifier
    token_data = urllib.parse.urlencode(_token_params).encode()

    req = urllib.request.Request(validate_outbound_url(token_url, field="token_url"), data=token_data,  # noqa: S310
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with abrir(req, timeout=_timeout()) as resp:  # noqa: S310
            tokens = _json.loads(resp.read())
    except _json.JSONDecodeError as exc:
        logger.warning("SSO callback: token response JSON inválido url=%r: %s", _safe_url(token_url), exc)
        raise HTTPException(502, "El proveedor devolvió una respuesta de token no válida")
    except OSError as exc:
        logger.warning("SSO callback: error de red al obtener tokens url=%r: %s", _safe_url(token_url), exc)
        raise HTTPException(502, f"Error de red al obtener tokens del proveedor SSO: {exc}")
    return tokens


def _extraer_identidad(config, claims: dict) -> tuple:
    """Correo y nombre del usuario segun como los mapee el proveedor.

    Los dos rechazos de aqui son controles de identidad, no validaciones de
    forma:

      · sin correo no hay a quien identificar, asi que no se puede crear cuenta;
      · `email_verified` a False se rechaza (P0-4). Un proveedor que NO ha
        verificado el correo no acredita nada: aceptarlo permitiria suplantar a
        cualquiera registrando su direccion en ese proveedor.
    """
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
    return email, name


def _validar_id_token_y_extraer_identidad(
    config, tokens: dict, expected_nonce, config_id: str
):
    """Verifica el id_token y devuelve (claims, email, name).

    Dos controles que no son opcionales:

      · el `nonce` del id_token tiene que ser el que se emitio, o un id_token
        capturado antes seria reutilizable (replay);
      · `email_verified` a False se rechaza: un proveedor que no ha verificado
        el correo no acredita la identidad, y aceptarlo permitiria suplantar a
        cualquiera registrando su direccion.
    """
    id_token = tokens.get("id_token", "")
    if not id_token:
        raise HTTPException(502, "El proveedor no devolvió id_token")

    # Verificar firma del id_token usando las claves públicas del proveedor (JWKS)
    try:
        import jwt as _jwt
        # Obtener JWKS URI desde el discovery document para validar la firma
        disc = _descubrimiento(config) if config.oidc_discovery_url else {}
        jwks_uri = disc.get("jwks_uri")
        if not jwks_uri:
            raise HTTPException(
                status_code=502,
                detail="No se pudo obtener JWKS URI del proveedor SSO. Imposible verificar la firma del id_token.",
            )
        _validate_https_discovery_url(jwks_uri)
        signing_key = _cliente_jwks(jwks_uri).get_signing_key_from_jwt(id_token)
        # Auditoria 2026-11 (como contecintelligence, `security/sso.py`): se
        # comprueba el emisor del discovery, se aceptan RS/ES/PS 256-512 y hay
        # tolerancia de reloj. Antes no se miraba `iss`.
        issuer = disc.get("issuer")
        # Azure AD multi-tenant publica un issuer con {tenantid}: no se puede comparar literal.
        verificar_iss = bool(issuer) and "{tenantid}" not in issuer
        claims = _jwt.decode(
            id_token,
            signing_key.key,
            algorithms=_ALGORITMOS,
            audience=config.oidc_client_id,
            issuer=issuer if verificar_iss else None,
            leeway=_holgura_sso(),
            options={"verify_exp": True, "verify_iss": verificar_iss, "require": ["exp", "iat"]},
        )
    # intentional: chained re-raise preserves context
    except (HTTPException, ErrorDeDominio):
        raise
    except Exception as jwt_err:
        logger.warning("SSO callback id_token verification failed for config=%s", config_id, exc_info=True)
        raise HTTPException(502, f"id_token inválido o firma incorrecta: {jwt_err}")

    # Verificación del NONCE (auditoría 2026-08, P2-13). Se generaba en
    # /authorize y no se comprobaba aquí, así que no protegía de replay del
    # id_token: un id_token capturado podía reutilizarse en otra sesión.
    if expected_nonce:
        token_nonce = claims.get("nonce")
        if not token_nonce or not _hmac.compare_digest(str(token_nonce), str(expected_nonce)):
            logger.warning(
                "SSO callback: nonce del id_token no coincide para config=%s", config_id
            )
            raise HTTPException(400, "Nonce inválido: posible reutilización del id_token")

    email, name = _extraer_identidad(config, claims)
    return claims, email, name


@router.post("/sso/{config_id}/callback", summary="Callback OIDC — intercambiar code por token")
@limiter.limit(settings.SSO_RATE_LIMIT)
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

        sso_payload = _validar_peticion_y_consumir_estado(payload)
        code = payload.code
        redirect_uri = payload.redirect_uri
        code_verifier = sso_payload.get("code_verifier")
        expected_nonce = sso_payload.get("nonce")

        tokens = _intercambiar_codigo_por_tokens(
            config, code, redirect_uri, code_verifier
        )
        claims, email, name = _validar_id_token_y_extraer_identidad(
            config, tokens, expected_nonce, config_id
        )

        # Buscar o crear usuario
        user = _svc.create_or_update_sso_user(db, config, email, name, claims)
        # La empresa es la del proveedor SSO (revision multitenant 2026-11).
        from app.services import entrada_service as _entrada
        org = _entrada.confirmar(db, user, request, config.organization_id)

        # Enforce MFA for SSO users too (TOTP or WebAuthn passkeys).
        has_totp    = bool(user.mfa_enabled and user.mfa_secret)
        has_passkeys = _svc.user_has_passkeys(db, user.id)
        # Auditoria 2026-11 (#45): la organizacion que exige MFA tambien lo
        # exige por SSO; antes el login por contrasena bloqueaba y el SSO no.
        if not (has_totp or has_passkeys) and _svc.organizacion_exige_mfa(db, user, org):
            _svc.commit_db(db)
            raise HTTPException(
                status_code=403,
                detail=("Tu organización requiere MFA. Configura un autenticador "
                        "(TOTP o passkey) antes de poder iniciar sesión."),
            )
        if has_totp or has_passkeys:
            methods = []
            if has_totp:
                methods.append("totp")
            if has_passkeys:
                methods.append("webauthn")
            return {
                "token_type":         "bearer",
                "mfa_required":       True,
                "mfa_challenge_token": _issue_mfa_challenge(db, user, org),
                "mfa_methods":        methods,
                "user": {
                    "id": user.id, "email": user.email,
                    "full_name": user.full_name,
                    "role": user.role.value if hasattr(user.role, "value") else str(user.role),
                },
            }

        access_token, new_refresh_token, new_jti = _entrada.emitir_tokens(user, org)
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

    except (HTTPException, ErrorDeDominio):
        raise
    except Exception as e:
        logger.error("SSO callback error: %s", e, exc_info=True)
        raise HTTPException(500, "Error al completar el inicio de sesión SSO.")
