"""
Auth Core Router — Login, logout, refresh, password reset, get_me.
Core authentication flows separated from MFA/SSO/Sessions for maintainability.
"""
from fastapi import APIRouter, Depends, HTTPException, Response, status, Body, Request
from sqlalchemy.orm import Session
from typing import Optional

from pydantic import BaseModel
from datetime import datetime, timezone
import logging
import secrets

from app.db.session import get_db
from app.services.audit import audit_log
from app.core.security import (
    verify_password,
    get_password_hash,
    decode_token,
    validate_password_policy,
)
from app.core.deps import get_current_user
from app.core.config import settings
from app.core.entorno import en_pruebas
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
    issue_mfa_challenge as _issue_mfa_challenge,
    COOKIE_OPTS as _COOKIE_OPTS,
    register_login_failure as _register_login_failure,
    login_lock_ttl as _login_lock_ttl,
    clear_login_failure as _clear_login_failure,
    login_bucket as _login_bucket,
    password_reset_bucket as _password_reset_bucket,
    register_password_reset_request as _register_password_reset_request,
    read_ephemeral_token as _read_ephemeral_token,
    issue_password_reset_token as _issue_password_reset_token,
    consume_password_reset_token as _consume_password_reset_token,
    send_password_reset_email as _send_password_reset_email,
)
from app.api.cookies_de_sesion import current_refresh_jti as _current_refresh_jti, set_auth_cookies as _set_auth_cookies
from app.core.network import extract_client_ip as _client_ip

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Login con credenciales locales ───────────────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 18). `login` era complejidad 18 y es la puerta de
# entrada de la aplicacion. Se ha partido en las fases que ya tenia, y ninguna
# decision ha cambiado. Lo que se ha conservado con especial cuidado:
#
#   · el MISMO mensaje 401 para «no existe el usuario» y «contrasena incorrecta»
#     («Credenciales incorrectas»). Cambiar uno de los dos convertiria el login
#     en un oraculo de usuarios existentes;
#   · el orden de las condiciones del bypass de superadmin, con
#     `compare_digest` al final: es un cortocircuito deliberado para no comparar
#     la contrasena mas que cuando todo lo demas ya se cumple;
#   · que `_register_login_failure` se llame exactamente UNA vez por intento
#     fallido — dos llamadas gastarian el doble de cupo y bloquearian antes de
#     los cinco intentos;
#   · que la auditoria SOC vaya en su propio `try`: un fallo del registro de
#     seguridad no puede convertirse en un fallo de login.

# Marcadores en la URL de la base que delatan un entorno de verdad. El bypass de
# superadmin se niega a funcionar si aparece cualquiera, ademas de las otras
# siete condiciones.
_MARCADORES_DE_BASE_REAL = (
    "prod", "production", "rds.amazonaws.com", "database.windows.net", "cloudsql",
)

_MENSAJE_CREDENCIALES = "Credenciales incorrectas"


def _mensaje_de_bloqueo(segundos: int) -> str:
    return f"Demasiados intentos fallidos. Intenta de nuevo en {segundos}s."


def _auditar_en_soc(db: Session, user, request: Request, *, exito: bool) -> None:
    """Registra el intento en el SOC. Nunca propaga: es auditoria, no control.

    Si esto lanzara, un SOC caido impediria iniciar sesion a todo el mundo.
    """
    try:
        soc = _soc_svc(db, user)
        if not soc:
            return
        ua = request.headers.get("User-Agent", "")
        if exito:
            soc.login_success(user_id=user.id, ip=_client_ip(request), ua=ua)
        else:
            soc.login_failed(user_id=user.id, ip=_client_ip(request), ua=ua,
                             reason="bad_credentials")
    except Exception:
        cual = "login_success" if exito else "login_failed"
        logger.warning("SOC %s audit failed for user=%s", cual, user.id, exc_info=True)


_HASH_FICTICIO: list = []


def _gastar_tiempo_de_hash(password: Optional[str]) -> None:
    """Un bcrypt de mas cuando no hay hash que comprobar.

    Auditoria 2026-11 (#45): un usuario inexistente respondia en ~1 ms y uno
    existente en lo que tarda bcrypt (~100-300 ms). El mensaje era el mismo,
    pero el tiempo delataba que cuentas existen.
    """
    if not _HASH_FICTICIO:
        _HASH_FICTICIO.append(get_password_hash(secrets.token_urlsafe(16)))
    try:
        verify_password(password or "", _HASH_FICTICIO[0])
    except Exception:
        logger.debug("hash ficticio: excepcion ignorada", exc_info=True)


def _rechazar_credenciales(bucket, *, cuenta=None, db=None, user=None, request=None):
    """Apunta el intento fallido y rechaza. No vuelve nunca.

    Se usa en los dos caminos de fallo —usuario inexistente y contrasena
    incorrecta— para que el mensaje y el consumo de cupo sean identicos. Que los
    dos respondan lo mismo es lo que impide averiguar por el login si un usuario
    existe.

    `cuenta`: el contador por cuenta (todas las IPs), con umbral mas alto.
    """
    lock_for = _register_login_failure(bucket)
    if cuenta is not None:
        lock_for = max(lock_for, _register_login_failure(cuenta, _svc.LOGIN_ACCOUNT_MULTIPLIER))
    if user is not None:
        _auditar_en_soc(db, user, request, exito=False)
    if lock_for > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=_mensaje_de_bloqueo(lock_for),
        )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail=_MENSAJE_CREDENCIALES
    )


def _contrasena_correcta(payload: LoginRequest, user) -> bool:
    """Verifica la contrasena. Un error del verificador cuenta como fallo.

    El `except` amplio es a proposito: un hash corrupto en base debe rechazar el
    acceso, no devolver un 500 que revelaria que ese usuario existe.
    """
    try:
        return verify_password(payload.password, user.hashed_password)
    except Exception:
        logger.warning(
            "verify_password raised unexpectedly for user=%s", user.id, exc_info=True
        )
        return False


def _bypass_de_superadmin_aplicable(user, payload: LoginRequest) -> bool:
    """El camino de recuperacion local. Ocho condiciones, todas obligatorias.

    Solo en desarrollo, solo con la variable puesta a mano, solo sobre SQLite,
    solo si la URL de la base no parece de un entorno real, solo para un
    superadministrador, y fuera de la suite de pruebas.

    `compare_digest` va al final del `and` a proposito: asi la contrasena solo se
    compara cuando todo lo demas ya se cumple, y la comparacion es en tiempo
    constante para no filtrar su longitud ni su prefijo por canal lateral.
    """
    _db_url = (settings.DATABASE_URL or "").lower()
    base_real = any(m in _db_url for m in _MARCADORES_DE_BASE_REAL)
    return (
        settings.ENVIRONMENT == "development"
        and settings.ENVIRONMENT not in {"staging", "production"}
        and not en_pruebas()
        and settings.ENABLE_SUPERADMIN_BYPASS
        and settings.DATABASE_URL.startswith("sqlite")
        and not base_real
        and bool(getattr(user, "is_superadmin", False))
        and secrets.compare_digest(
            (payload.password or "").encode("utf-8"),
            (settings.SUPERADMIN_PASSWORD or "").encode("utf-8"),
        )
    )


def _exigir_mfa_de_la_organizacion(db: Session, user, tiene_factor: bool, org=None) -> None:
    """Bloquea el login si la organizacion exige MFA y el usuario no tiene ninguno.

    Se bloquea en vez de dejar entrar y avisar: la politica de la organizacion
    dice que sin segundo factor no se entra, y un aviso ignorable no es una
    politica. `org`: la empresa en la que se entra (si no, la del usuario). La
    usa tambien el callback SSO (auditoria 2026-11 #45).
    """
    if tiene_factor or not (org or user.organization_id):
        return
    if _svc.organizacion_exige_mfa(db, user, org):
        raise HTTPException(
            status_code=403,
            detail=(
                "Tu organización requiere MFA. Configura un autenticador "
                "(TOTP o passkey) antes de poder iniciar sesión."
            ),
        )


def _reto_de_segundo_factor(db: Session, user, has_totp: bool, has_passkeys: bool, org=None):
    """Devuelve el reto de MFA en vez de los tokens de sesion.

    Aqui NO se emiten cookies de autenticacion: la sesion no existe hasta que se
    supere el segundo factor.
    """
    methods = []
    if has_totp:
        methods.append("totp")
    if has_passkeys:
        methods.append("webauthn")
    _svc.commit_db(db)
    return TokenResponse(
        user=UserPublic.model_validate(user),
        mfa_required=True,
        mfa_challenge_token=_issue_mfa_challenge(db, user, org),
        mfa_methods=methods,
    )


def _abrir_sesion(db: Session, user, request: Request, response: Response, org=None):
    """Emite el par de tokens (de la empresa `org`), registra la sesion y pone las cookies."""
    from app.services.entrada_service import emitir_tokens
    access_token, refresh_token, new_jti = emitir_tokens(user, org)
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
        logger.exception("commit_db failed during login finalization for user=%s", user.id)
        db.rollback()
        raise HTTPException(
            status_code=500, detail="Error al iniciar sesión. Inténtalo de nuevo."
        )

    _set_auth_cookies(response, access_token, refresh_token)
    from app.core.modulos import con_rutas_cerradas
    return TokenResponse(user=UserPublic.model_validate(con_rutas_cerradas(db, user)))


@router.post("/login", response_model=TokenResponse, summary="Login con credenciales locales")
@limiter.limit("5/minute")
def login(request: Request, response: Response, payload: LoginRequest, db: Session = Depends(get_db)):
    bucket = _login_bucket(payload.username, request.client.host if request.client else None)
    cuenta = _svc.login_account_bucket(payload.username)
    lock_ttl = max(_login_lock_ttl(bucket), _login_lock_ttl(cuenta))
    if lock_ttl > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=_mensaje_de_bloqueo(lock_ttl),
        )

    user = _svc.lookup_user_by_credentials(db, payload.username)
    if not user or not user.hashed_password:
        _gastar_tiempo_de_hash(payload.password)
        _rechazar_credenciales(bucket, cuenta=cuenta)

    password_ok = _contrasena_correcta(payload, user)
    if not password_ok and _bypass_de_superadmin_aplicable(user, payload):
        password_ok = True
        logger.warning(
            "Superadmin bypass used for user=%s ip=%s — review ENABLE_SUPERADMIN_BYPASS",
            user.id, _client_ip(request),
        )

    if not password_ok:
        _rechazar_credenciales(bucket, cuenta=cuenta, db=db, user=user, request=request)

    _clear_login_failure(bucket)
    _clear_login_failure(cuenta)
    # En que empresa entra (revision multitenant 2026-11): segun el modo del
    # despliegue, la del host, la del codigo, la unica o la que elija. Un
    # rechazo por empresa responde como una contrasena mala.
    from app.services import entrada_service as _entrada
    try:
        org = _entrada.decidir(db, user, request, codigo=payload.organization)
    except _entrada.EleccionPendiente as pendiente:
        org, eleccion = None, pendiente.organizaciones
    else:
        eleccion = None

    user.last_login = datetime.now(timezone.utc)
    audit_log(db, user, "LOGIN", "users", user.id, user.full_name)
    _auditar_en_soc(db, user, request, exito=True)
    if eleccion is not None:
        return _pedir_eleccion(db, user, eleccion)

    # Segundo factor: quien tenga TOTP o passkeys registradas no recibe tokens
    # hasta superar el reto.
    return _segundo_factor_o_sesion(db, user, request, response, org)


def _segundo_factor_o_sesion(db: Session, user, request: Request, response: Response, org):
    has_totp = bool(user.mfa_enabled and user.mfa_secret)
    has_passkeys = _svc.user_has_passkeys(db, user.id)
    _exigir_mfa_de_la_organizacion(db, user, has_totp or has_passkeys, org)
    if has_totp or has_passkeys:
        return _reto_de_segundo_factor(db, user, has_totp, has_passkeys, org)
    return _abrir_sesion(db, user, request, response, org)


def _pedir_eleccion(db: Session, user, organizaciones: list):
    """Pertenece a varias empresas: aun no hay sesion, solo un token para elegir."""
    from app.services import entrada_service as _entrada
    _svc.commit_db(db)
    return TokenResponse(
        user=UserPublic.model_validate(user),
        organization_selection_required=True,
        organizations=[_entrada.resumen(o) for o in organizaciones],
        selection_token=_entrada.token_de_eleccion(user),
    )


class EleccionIn(BaseModel):
    selection_token: str
    organization_id: str


@router.post("/select-organization", response_model=TokenResponse,
             summary="Elegir empresa tras la contraseña (usuarios de varias empresas)")
@limiter.limit("10/minute")
def select_organization(request: Request, response: Response, payload: EleccionIn, db: Session = Depends(get_db)):
    from app.services import entrada_service as _entrada
    user = _svc.lookup_user_by_id_active(db, _entrada.leer_token_de_eleccion(payload.selection_token))
    if not user:
        raise HTTPException(401, "Usuario no encontrado o desactivado")
    org = _entrada.decidir(db, user, request, elegida=payload.organization_id)
    return _segundo_factor_o_sesion(db, user, request, response, org)


class CambioIn(BaseModel):
    organization_id: str


@router.get("/organizations", summary="Mis empresas y la activa")
def my_organizations(request: Request, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    from app.services import entrada_service as _entrada
    activas = _entrada.organizaciones_del_usuario(db, current_user)
    return {"current": current_user.organization_id,
            "items": [_entrada.resumen(o) for o in activas]}


@router.post("/switch-organization", response_model=TokenResponse, summary="Cambiar de empresa en la sesión")
@limiter.limit("20/minute")
def switch_organization(request: Request, response: Response, payload: CambioIn,
                        db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.services import entrada_service as _entrada
    if _entrada.modo() != "email_selector":
        raise HTTPException(409, "En este despliegue la empresa la fija el acceso, no se cambia en la sesión")
    org = _entrada.decidir(db, current_user, request, elegida=payload.organization_id)
    jti = _current_refresh_jti(request)
    if jti:
        revoke_session_by_jti(db=db, user_id=current_user.id, refresh_token_jti=jti, reason="switch_organization")
    # Revisión GRC 2026-11b: cambiar de empresa en la sesión no dejaba rastro.
    # Va a la empresa de destino; lo confirma `_abrir_sesion`.
    from app.services.audit import audit_log
    destino = getattr(org, "id", org)
    entrada = audit_log(db, current_user, "ORG_SWITCH", "users", current_user.id, current_user.email,
                        new_values={"organization_id": destino})
    if destino:
        entrada.organization_id = destino
    return _abrir_sesion(db, current_user, request, response, org)


@router.get("/entry-config", summary="Cómo se entra en este despliegue (público)")
def entry_config(request: Request, db: Session = Depends(get_db)):
    """El modo de entrada y, en modo subdominio, la empresa del host (para su marca)."""
    from app.services import entrada_service as _entrada
    org = _entrada.organizacion_por_host(db, request) if _entrada.modo() == "subdomain" else None
    return {"mode": _entrada.modo(),
            "organization": _entrada.resumen(org) if org and org.is_active else None}


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

    # Issue new token pair and rotate JTI. La empresa activa se conserva, y se
    # vuelve a validar: pertenencia vigente y empresa activa.
    from app.services import entrada_service as _entrada
    org = token_data.get("org")
    if org and not user.is_superadmin:
        if not _entrada.pertenece(db, user, org):
            raise HTTPException(status_code=401, detail="Ya no perteneces a esa organización: vuelve a entrar")
        from app.db.session import exigir_organizacion_activa
        exigir_organizacion_activa(db, org)
    access_token, new_refresh_token, new_jti = _entrada.emitir_tokens(user, org)
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
    # Auditoria 2026-11 (#22): la cookie de refresco ahora llega aqui (ruta
    # `/api/v1/auth`), asi que su sesion se revoca de verdad.
    revoke_session_by_jti(
        db=db,
        user_id=current_user.id,
        refresh_token_jti=_current_refresh_jti(request),
        reason="logout",
    )
    _svc.commit_db(db)
    response.delete_cookie("access_token", **_COOKIE_OPTS)
    response.delete_cookie("refresh_token", path=_svc.REFRESH_COOKIE_PATH, **_COOKIE_OPTS)
    response.delete_cookie("refresh_token", path=_svc.REFRESH_COOKIE_PATH_ANTIGUA, **_COOKIE_OPTS)
    return {"detail": "Sesión cerrada correctamente"}


@router.post("/password/forgot", summary="Solicitar enlace para restablecer contraseña")
@limiter.limit("5/minute")
def password_forgot(request: Request, payload: PasswordForgotRequest, db: Session = Depends(get_db)):
    identifier = (payload.email_or_username or "").strip()
    if identifier:
        ttl = _register_password_reset_request(_password_reset_bucket(identifier, request.client.host if request.client else None))
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
                # Segunda auditoria 2026-11 (n.º 20): el SMTP sale de la peticion.
                # Ademas cierra un oraculo de tiempos: la respuesta tardaba lo
                # que el SMTP solo si la cuenta existia. El worker abre su sesion
                # (`db`) en la empresa del usuario para leer su servidor SMTP.
                from app.core.segundo_plano import encolar
                org_del_usuario = getattr(user, "organization_id", None)
                encolar(_send_password_reset_email, user.email, reset_link,
                        org_id=org_del_usuario, _organizacion=org_del_usuario, _sesion=db)
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

    ok, reason = validate_password_policy(payload.new_password, db=db, org_id=getattr(user, "organization_id", None))
    if not ok:
        raise HTTPException(400, reason or "La contraseña no cumple la política de seguridad")

    audit_log(db, user, "PASSWORD_RESET_COMPLETE", "users", user.id, user.full_name)
    _consume_password_reset_token(user.id, token_data.get("jti"))
    _svc.complete_password_reset(db, user, get_password_hash(payload.new_password))

    return {"ok": True, "message": "Contraseña actualizada correctamente"}


@router.get("/me", response_model=UserPublic)
def get_me(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.core.modulos import con_rutas_cerradas
    usuario = con_rutas_cerradas(db, current_user)
    actor = getattr(request.state, "suplantado_por", None)
    if actor:
        usuario.impersonated_by = _svc.correo_de_usuario(db, actor)
    return usuario


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
            logger.info("MFA challenge read failed during change-password for user=%s", current_user.id, exc_info=True)
            raise HTTPException(401, f"MFA inválido: {str(e)}")

    if not current_pw or not new_pw:
        raise HTTPException(400, "current_password y new_password son obligatorios")

    ok, err = validate_password_policy(new_pw, db=db, org_id=getattr(current_user, "organization_id", None))
    if not ok:
        raise HTTPException(400, err)

    if not current_user.hashed_password:
        raise HTTPException(400, "Tu cuenta usa SSO — la contraseña se gestiona externamente")

    if not verify_password(current_pw, current_user.hashed_password):
        raise HTTPException(403, "Contraseña actual incorrecta")

    current_user.hashed_password = get_password_hash(new_pw)
    # Auditoria 2026-11 (#22): las demas sesiones se cierran; la actual sigue.
    revocadas = _svc.revocar_sesiones_del_usuario(
        db, current_user.id, "password_change", salvo_jti=_current_refresh_jti(request))
    _svc.commit_db(db)

    return {"ok": True, "message": "Contraseña actualizada correctamente", "sessions_revoked": revocadas}
