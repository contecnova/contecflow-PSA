"""Restablecimiento de contraseña: «¿Olvidaste tu contraseña?» y restablecimiento forzado.

23-11-2026 (incidencia de usuario: «No hay función de restablecer contraseña»;
docs/seguridad/politicas_de_cuenta.md §«Restablecimiento»). Piezas comunes al
operador (`/auth/password/*`) y al portal de clientes (`/portal/auth/password/*`):

- **Un solo uso de verdad.** `reclamar_jti` comprueba y borra el `jti` del enlace
  en UNA operación (script Lua en Redis; bajo cerrojo en memoria). Antes el
  operador comprobaba (`is_current_password_reset_jti`) y borraba después: dos
  peticiones simultáneas con el mismo enlace pasaban las dos.
- **Sin oráculo de cuentas.** Misma respuesta exista o no la cuenta, y
  `igualar_tiempo` lleva la respuesta a un suelo con algo de azar, para que no
  se note el trabajo de más (token, auditoría, encolar el correo).
- **Minimización (RGPD).** El cubo del límite de intentos lleva el HASH del
  identificador, no el correo; si la cuenta no existe no se apunta nada.
- **Cerrar sesiones del portal.** El token del portal es un JWT sin estado; para
  echar a todas sus sesiones se anota un «corte» por cliente (Redis, con
  respaldo en memoria, hasta que caduque el último token posible) y
  `token_de_cliente_revocado` rechaza los emitidos antes. Sin esquema nuevo.
- **Enlace al portal correcto.** La base sale del dominio propio de la empresa
  (`OrgBranding.custom_domain`, si está activo) o de `FRONTEND_URL`; nunca de la
  cabecera `Host` de la petición (envenenamiento del enlace de restablecimiento).
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import threading
import time
import uuid
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

#: Tipo del token del portal: distinto del del operador para que uno no valga en el otro.
TIPO_TOKEN_DEL_PORTAL = "portal_password_reset"  # noqa: S105
#: Prefijo de la clave del `jti` del portal (el operador usa el id del usuario tal cual).
_PREFIJO_PORTAL = "portal:"
#: Suelo de tiempo de las respuestas de «olvidé mi contraseña» (segundos) y azar añadido.
SUELO_DE_RESPUESTA_S = 0.45
_AZAR_MS = 200

_LUA_RECLAMAR = ("if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) "
                 "else return 0 end")


# ── Comunes ───────────────────────────────────────────────────────────────────

def huella(identificador: str) -> str:
    """Hash del identificador para el cubo del límite de intentos (no se guarda el correo)."""
    return hashlib.sha256((identificador or "").strip().lower().encode("utf-8")).hexdigest()[:32]


def igualar_tiempo(inicio: float, suelo_s: float = SUELO_DE_RESPUESTA_S) -> None:
    """Duerme lo que falte para el suelo (más azar): la respuesta tarda lo mismo exista o no la cuenta."""
    from app.core.entorno import en_pruebas
    if en_pruebas():
        return
    resto = suelo_s + secrets.randbelow(_AZAR_MS) / 1000 - (time.monotonic() - inicio)
    if resto > 0:
        time.sleep(resto)


def reclamar_jti(clave: str, jti: Optional[str]) -> bool:
    """Consume el `jti` vigente de `clave` si coincide. True solo para UNA petición."""
    from app.services.auth_service import estado_efimero as ee
    if not clave or not jti:
        return False
    r = ee.get_sso_redis()
    if r is not None:
        try:
            return bool(r.eval(_LUA_RECLAMAR, 1, f"{ee.PASSWORD_RESET_JTI_PREFIX}{clave}", jti))
        except Exception as exc:
            logger.warning("reclamar_jti: Redis no disponible (%s); se usa la memoria", exc)
    with ee._sso_states_lock:
        actual = ee._password_reset_jti_fallback.get(clave)
        if not actual or actual[0] != jti or actual[1] <= time.time():
            return False
        ee._password_reset_jti_fallback.pop(clave, None)
        return True


def minutos_de_validez() -> int:
    from app.services.auth_service.estado_efimero import PASSWORD_RESET_TTL_SECONDS
    return PASSWORD_RESET_TTL_SECONDS // 60


def campos_de_politica(p) -> dict:
    """Lo que la pantalla de nueva contraseña enseña de la política (sin datos de nadie)."""
    return {k: getattr(p, k) for k in (
        "MIN_PASSWORD_LENGTH", "PASSWORD_MAX_LENGTH", "PASSWORD_REQUIRE_UPPERCASE", "PASSWORD_REQUIRE_LOWERCASE",
        "PASSWORD_REQUIRE_DIGIT", "PASSWORD_REQUIRE_SPECIAL", "PASSWORD_BLOCK_COMMON", "PASSWORD_BLOCK_PERSONAL",
        "PASSWORD_HISTORY_COUNT", "PASSWORD_EXPIRY_DAYS")}


def enviar_correo_de_restablecimiento(destinatario: str, enlace: str, idioma: Optional[str] = None,
                                      forzado: bool = False, db=None, org_id: Optional[str] = None) -> bool:
    """Correo con el enlace, en el idioma del destinatario. Encolable (solo valores JSON).

    No lanza: un fallo de SMTP queda en el log SIN el correo del destinatario.
    """
    from html import escape
    from app.services.notification_service import ServidorSmtp, enviar_correo
    from app.services.textos_de_salida import nombre_de_marca, texto
    marca = nombre_de_marca(db, org_id)
    asunto = texto("restablecer.asunto", idioma, marca=marca)
    cuerpo = texto("restablecer.cuerpo_forzado" if forzado else "restablecer.cuerpo", idioma,
                   marca=escape(marca), url=escape(enlace), minutos=minutos_de_validez())
    try:
        servidor = ServidorSmtp.de_organizacion(db, org_id) if db is not None else ServidorSmtp.del_entorno()
        resultado = enviar_correo(destinatario, asunto, cuerpo, servidor=servidor)
    except Exception:
        logger.warning("Correo de restablecimiento no enviado (org=%s)", org_id, exc_info=True)
        return False
    if not resultado.enviado:
        logger.info("Correo de restablecimiento no enviado (org=%s): %s", org_id, resultado.error)
    return bool(resultado.enviado)


# ── Operador ──────────────────────────────────────────────────────────────────

def enviar_enlace_al_operador(db, user, *, forzado: bool = False) -> bool:
    """Emite el token (invalida el anterior) y encola el correo. False si la cuenta no admite enlace."""
    from app.core.segundo_plano import encolar
    from app.services.auth_service.tokens_y_cookies import issue_password_reset_token
    if not getattr(user, "email", None) or not getattr(user, "hashed_password", None):
        return False
    token = issue_password_reset_token(user)
    enlace = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?token={token}"
    org = getattr(user, "organization_id", None)
    idioma = None
    try:
        from app.services.formato_regional import idioma_de_salida
        idioma = idioma_de_salida(db, user_id=user.id, org_id=org, preferido=getattr(user, "language", None))
    except Exception:
        logger.debug("idioma del correo de restablecimiento no resuelto", exc_info=True)
    encolar(enviar_correo_de_restablecimiento, user.email, enlace, idioma, forzado,
            org_id=org, _organizacion=org, _sesion=db)
    return True


# ── Portal de clientes ────────────────────────────────────────────────────────

def _clave_del_portal(client_id: str) -> str:
    return f"{_PREFIJO_PORTAL}{client_id}"


def emitir_token_del_portal(cliente) -> str:
    """Token firmado de un solo uso (el `jti` vigente se guarda: uno nuevo invalida el anterior)."""
    from app.services.auth_service.estado_efimero import PASSWORD_RESET_TTL_SECONDS, store_password_reset_jti
    from app.services.auth_service.tokens_y_cookies import create_ephemeral_token
    jti = uuid.uuid4().hex
    store_password_reset_jti(_clave_del_portal(cliente.id), jti, PASSWORD_RESET_TTL_SECONDS)
    return create_ephemeral_token(TIPO_TOKEN_DEL_PORTAL, cliente.id, uuid.uuid4().hex,
                                  ttl_seconds=PASSWORD_RESET_TTL_SECONDS, token_jti=jti)


def leer_token_del_portal(token: str) -> dict:
    """Carga útil del token del portal si es válido y sigue vigente. Si no, 401 con código del portal."""
    import jwt
    from app.core.codigos_de_error import error
    from app.services.auth_service.estado_efimero import is_current_password_reset_jti
    from app.services.key_management import get_jwt_verification_keys
    carga = None
    for clave in get_jwt_verification_keys().values():
        try:
            carga = jwt.decode(token or "", clave, algorithms=["HS256"])
            break
        except jwt.PyJWTError:
            continue
    if (not carga or carga.get("type") != TIPO_TOKEN_DEL_PORTAL or not carga.get("sub") or not carga.get("jti")
            or not is_current_password_reset_jti(_clave_del_portal(carga["sub"]), carga["jti"])):
        raise error(401, "portal_reset_token_no_valido")
    return carga


def reclamar_token_del_portal(carga: dict) -> bool:
    return reclamar_jti(_clave_del_portal(carga.get("sub") or ""), carga.get("jti"))


def base_del_portal(db, org_id: Optional[str]) -> str:
    """URL base del portal de la empresa: su dominio propio activo o `FRONTEND_URL`."""
    if org_id and db is not None:
        try:
            from app.models.white_label import OrgBranding
            b = db.query(OrgBranding).filter(OrgBranding.organization_id == org_id).first()
            dominio = (getattr(b, "custom_domain", None) or "").strip().lower() if b else ""
            if dominio and getattr(b, "is_active", True) and getattr(b, "enable_portal", True) \
                    and "/" not in dominio and " " not in dominio:
                return f"https://{dominio}"
        except Exception:
            logger.debug("dominio propio del portal no legible", exc_info=True)
    return settings.FRONTEND_URL.rstrip("/")


def enlace_del_portal(db, cliente, token: str) -> str:
    from urllib.parse import quote
    idioma = (getattr(cliente, "language", None) or "")[:5]
    sufijo = f"&lang={quote(idioma)}" if idioma else ""
    return f"{base_del_portal(db, getattr(cliente, 'organization_id', None))}/portal/reset-password?token={token}{sufijo}"


def enviar_enlace_al_cliente(db, cliente, *, forzado: bool = False) -> bool:
    """Emite el token del portal y encola el correo con el enlace a SU portal."""
    from app.core.segundo_plano import encolar
    if not getattr(cliente, "email", None):
        return False
    token = emitir_token_del_portal(cliente)
    org = getattr(cliente, "organization_id", None)
    encolar(enviar_correo_de_restablecimiento, cliente.email, enlace_del_portal(db, cliente, token),
            (getattr(cliente, "language", None) or None), forzado, org_id=org, _organizacion=org, _sesion=db)
    return True


# Cortes de sesión del portal (cliente -> instante; los tokens emitidos antes no valen).
_PREFIJO_CORTE = "contecflow:portal:cut:"
_cortes_en_memoria: dict[str, tuple[int, float]] = {}
_cerrojo = threading.Lock()


def _horas_del_token_del_portal() -> float:
    return float(getattr(settings, "CLIENT_TOKEN_EXPIRE_HOURS", 72) or 72)


def cerrar_sesiones_del_portal(client_id: str) -> None:
    """Invalida todos los tokens del portal de `client_id` emitidos hasta ahora."""
    from app.services.auth_service.estado_efimero import get_sso_redis
    if not client_id:
        return
    ahora = int(time.time())
    ttl = int(_horas_del_token_del_portal() * 3600) + 120
    r = get_sso_redis()
    if r is not None:
        try:
            r.setex(f"{_PREFIJO_CORTE}{client_id}", ttl, str(ahora))
        except Exception:
            logger.warning("No se pudo anotar en Redis el corte de sesiones del portal", exc_info=True)
    with _cerrojo:
        reloj = time.time()
        for k in [k for k, (_, hasta) in _cortes_en_memoria.items() if hasta < reloj]:
            _cortes_en_memoria.pop(k, None)
        _cortes_en_memoria[client_id] = (ahora, reloj + ttl)


def _corte_de(client_id: str) -> Optional[int]:
    from app.services.auth_service.estado_efimero import get_sso_redis
    r = get_sso_redis()
    if r is not None:
        try:
            v = r.get(f"{_PREFIJO_CORTE}{client_id}")
            if v:
                return int(v)
        except Exception:
            logger.warning("No se pudo leer en Redis el corte de sesiones del portal", exc_info=True)
    with _cerrojo:
        fila = _cortes_en_memoria.get(client_id)
    if fila and fila[1] > time.time():
        return fila[0]
    return None


def sesion_del_portal_cortada(carga: dict) -> bool:
    """Si el token del portal (ya decodificado) se emitió antes del último corte de su cliente.

    El token no lleva `iat`; se deduce de `exp` menos su vida (`CLIENT_TOKEN_EXPIRE_HOURS`).
    Un token emitido en el mismo segundo que el corte sigue valiendo (el login justo después).
    """
    sub, exp = (carga or {}).get("sub"), (carga or {}).get("exp")
    if not sub or not exp:
        return False
    corte = _corte_de(str(sub))
    if corte is None:
        return False
    try:
        emitido = int(exp) - int(_horas_del_token_del_portal() * 3600)
    except (TypeError, ValueError):
        return False
    return emitido < corte


# ── Portal: la unidad de trabajo de cada ruta (prueba global 23-11-2026) ────────
# Vivían en `app/api/v1/endpoints/client_portal_password.py`, que consultaba
# `client_users` y confirmaba la transacción en la capa API.

def pedir_en_el_portal(db, correo: str, origen) -> None:
    """«¿Olvidaste tu contraseña?» del portal: envía el enlace si la cuenta existe.

    Misma respuesta pase lo que pase (sin oráculo): un fallo se deshace y queda en
    el log sin datos. Si la cuenta no existe no se apunta nada (RGPD: minimización).
    """
    from sqlalchemy import func
    from app.db.session import exigir_organizacion_activa
    from app.models.client_portal import ClientUser
    from app.services.seguridad_de_cuentas.auditoria import auditar
    cliente = db.query(ClientUser).filter(func.lower(ClientUser.email) == correo,
                                          ClientUser.is_active == True).first()  # noqa: E712
    if cliente is None or not cliente.hashed_password:
        return
    try:
        exigir_organizacion_activa(db, cliente.organization_id)
        enviar_enlace_al_cliente(db, cliente)
        auditar(db, None, "PORTAL_PASSWORD_RESET_REQUEST", cliente, org_id=cliente.organization_id,
                origen=origen, recurso="client_user")
        db.commit()
    except Exception as exc:  # misma respuesta pase lo que pase (sin oráculo)
        db.rollback()
        logger.warning("portal: restablecimiento no enviado client_id=%s: %s", cliente.id, type(exc).__name__)


def restablecer_en_el_portal(db, cliente, carga: dict, nueva: str, minimo: int, origen) -> None:
    """Contraseña nueva con el enlace: política de la empresa, un solo uso, cierra
    TODAS las sesiones del portal y audita (`PORTAL_PASSWORD_RESET_COMPLETE`)."""
    from app.core.codigos_de_error import ErrorConCodigo, desde_valor, error
    from app.services.client_portal_service.autenticacion import hash_password, verify_password
    from app.services.seguridad_de_cuentas.auditoria import auditar
    from app.services.seguridad_de_cuentas.contrasenas import validar_del_portal
    try:
        validar_del_portal(db, cliente, nueva, minimo)
        if cliente.hashed_password and verify_password(nueva, cliente.hashed_password):
            raise ErrorConCodigo("portal_contrasena_igual_a_la_anterior")
    except ValueError as e:
        raise desde_valor(400, e)
    # Un solo uso: comprobar y borrar el `jti` en una operación.
    if not reclamar_token_del_portal(carga):
        raise error(401, "portal_reset_token_no_valido")
    cliente.hashed_password = hash_password(nueva)
    cliente.must_change_password = False
    cerrar_sesiones_del_portal(cliente.id)
    auditar(db, None, "PORTAL_PASSWORD_RESET_COMPLETE", cliente, org_id=cliente.organization_id,
            origen=origen, recurso="client_user", datos={"sessions_revoked": "all"})
    db.commit()


def forzar_en_el_portal(db, actor, org: Optional[str], client_id: str, motivo: str, enviar: bool, origen) -> bool:
    """El equipo fuerza el restablecimiento de un usuario del portal de SU empresa:
    cambio obligatorio, cierre de sesiones y enlace (`PORTAL_PASSWORD_RESET_FORCED`).
    Devuelve si se envió el enlace."""
    from app.core.codigos_de_error import error
    from app.models.client_portal import ClientUser
    from app.services.seguridad_de_cuentas.auditoria import auditar
    cliente = db.query(ClientUser).filter(ClientUser.id == client_id).first()
    if cliente is None or (not actor.is_superadmin and cliente.organization_id != org):
        raise error(404, "no_encontrado", que="cliente")
    cliente.must_change_password = True
    cerrar_sesiones_del_portal(cliente.id)
    enviado = bool(enviar and cliente.is_active and cliente.hashed_password
                   and enviar_enlace_al_cliente(db, cliente, forzado=True))
    auditar(db, actor, "PORTAL_PASSWORD_RESET_FORCED", cliente, org_id=cliente.organization_id,
            origen=origen, recurso="client_user",
            datos={"reason": motivo, "link_sent": enviado, "sessions_revoked": "all"})
    db.commit()
    return enviado
