"""
Auth MFA Router — Two-factor authentication: TOTP setup/verify and WebAuthn (passkeys).
"""
from fastapi import APIRouter, Depends, HTTPException, Response, Body, Request
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import json
import logging

from app.db.session import get_db
from app.core.deps import get_current_user
from app.core.config import settings
from app.core.ratelimit import limiter
from app.core.encryption import encrypt_value, decrypt_value
from app.models.user import User
from app.schemas.auth_payloads import (
    MfaCodeIn, MfaValidateIn,
    WebAuthnRegisterFinishIn, WebAuthnAuthStartIn, WebAuthnAuthFinishIn,
)
from app.services.session_security import register_or_rotate_user_session

import app.services.auth_service as _svc
from app.services.auth_service import (
    client_ip as _client_ip,
    soc_svc as _soc_svc,
    read_mfa_challenge as _read_mfa_challenge,
    consume_mfa_challenge as _consume_mfa_challenge,
    b64url_encode as _b64url_encode,
    b64url_decode as _b64url_decode,
    create_ephemeral_token as _create_ephemeral_token,
    read_ephemeral_token as _read_ephemeral_token,
    set_auth_cookies as _set_auth_cookies,
)
from app.core.security import create_access_token, create_refresh_token

logger = logging.getLogger(__name__)
router = APIRouter()


# ── TOTP Setup and Verification ───────────────────────────────────────────────

@router.post("/mfa/setup", summary="Iniciar configuración 2FA — genera secreto TOTP")
@limiter.limit("5/minute")
def mfa_setup(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Genera un secreto TOTP y devuelve QR para el autenticador."""
    try:
        import pyotp
    except ImportError:
        raise HTTPException(500, "pyotp no instalado — ejecuta: pip install pyotp")

    try:
        import qrcode
    except ImportError:
        raise HTTPException(500, "qrcode no instalado — ejecuta: pip install qrcode[pil]")

    try:
        import io
        import base64
        import qrcode
        from app.services.settings_service import get_runtime_str
        _project_name = get_runtime_str(db, "PROJECT_NAME", getattr(current_user, "organization_id", None)) or settings.PROJECT_NAME
        secret = pyotp.random_base32()
        totp   = pyotp.TOTP(secret)
        uri    = totp.provisioning_uri(
            name=current_user.email,
            issuer_name=_project_name,
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
            "issuer":           _project_name,
            "email":            current_user.email,
        }
    except ImportError as ie:
        logger.error("ImportError en MFA setup: %s", ie, exc_info=True)
        raise HTTPException(500, f"Dependencia faltante en 2FA: {ie}")
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error("MFA setup error: %s\nTraceback:\n%s", e, tb)
        msg = str(e) if settings.ENVIRONMENT == "development" else "Error al configurar 2FA"
        raise HTTPException(500, msg)


@router.post("/mfa/verify-setup", summary="Verificar código TOTP y activar 2FA")
@limiter.limit("5/minute")
def mfa_verify_setup(
    request: Request,
    payload: MfaCodeIn = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Verifica el código de 6 dígitos del autenticador y activa 2FA."""
    try:
        import pyotp
    except ImportError:
        raise HTTPException(500, "pyotp no instalado")

    code   = (payload.code or "").strip()
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
    payload: MfaValidateIn = Body(...),
    db: Session = Depends(get_db),
):
    """Valida el código TOTP durante el proceso de login."""
    try:
        import pyotp
    except ImportError:
        raise HTTPException(500, "pyotp no instalado")

    challenge_token = payload.mfa_challenge_token
    code    = (payload.code or "").strip()

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
        except Exception:
            logger.warning("SOC mfa_failed audit raised for user=%s", user.id, exc_info=True)
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
    except Exception:
        logger.warning("SOC login_success audit raised for user=%s during MFA validate", user.id, exc_info=True)
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
    payload: MfaCodeIn = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Desactiva 2FA. Requiere confirmar con el código actual."""
    try:
        import pyotp
    except ImportError:
        raise HTTPException(500, "pyotp no instalado")

    code = payload.code.strip()
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


# ── WebAuthn / Passkey Registration ───────────────────────────────────────────

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
    from app.services.settings_service import get_runtime_str
    _rp_name = get_runtime_str(db, "WEBAUTHN_RP_NAME", getattr(current_user, "organization_id", None)) or settings.WEBAUTHN_RP_NAME
    options = generate_registration_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        rp_name=_rp_name,
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
    payload: WebAuthnRegisterFinishIn = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        from webauthn import verify_registration_response
    except ImportError:
        raise HTTPException(503, "webauthn no instalado — ejecuta: pip install webauthn")

    challenge_token = payload.webauthn_challenge_token
    credential = payload.credential
    nickname = payload.name
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


# ── WebAuthn / Passkey Authentication ─────────────────────────────────────────

@router.post("/mfa/webauthn/authenticate/start", summary="Iniciar login con passkey")
@limiter.limit("15/minute")
def webauthn_auth_start(
    request: Request,
    payload: WebAuthnAuthStartIn = Body(...),
    db: Session = Depends(get_db),
):
    try:
        from webauthn import generate_authentication_options, options_to_json
        from webauthn.helpers.structs import PublicKeyCredentialDescriptor, UserVerificationRequirement
    except ImportError:
        raise HTTPException(503, "webauthn no instalado — ejecuta: pip install webauthn")

    mfa_challenge_token = payload.mfa_challenge_token
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
    payload: WebAuthnAuthFinishIn = Body(...),
    db: Session = Depends(get_db),
):
    try:
        from webauthn import verify_authentication_response
    except ImportError:
        raise HTTPException(503, "webauthn no instalado — ejecuta: pip install webauthn")

    mfa_challenge_token = payload.mfa_challenge_token
    webauthn_challenge_token = payload.webauthn_challenge_token
    credential = payload.credential
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
