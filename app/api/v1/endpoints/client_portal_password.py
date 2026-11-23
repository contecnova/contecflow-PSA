"""Portal de clientes: «¿Olvidaste tu contraseña?» y restablecimiento forzado (23-11-2026).

Incidencia de usuario: «No hay función de restablecer contraseña para los
usuarios». El portal no tenía nada; el patrón es el del operador
(`/auth/password/*`, `app/api/v1/routers/auth_core.py`) con las piezas comunes
de `app/services/seguridad_de_cuentas/restablecimiento.py`:

- `POST /portal/auth/password/forgot`: misma respuesta y tiempo parecido exista o
  no el correo; límite por (hash del correo, IP) y por minuto; auditado solo si la
  cuenta existe (`PORTAL_PASSWORD_RESET_REQUEST`), sin guardar lo tecleado si no.
- `POST /portal/auth/password/policy`: las reglas de la empresa para la pantalla.
- `POST /portal/auth/password/reset`: token de un solo uso (30 min), política de
  la empresa (`validar_del_portal`), cierra TODAS las sesiones del portal del
  cliente y audita (`PORTAL_PASSWORD_RESET_COMPLETE`).
- `POST /portal/clients/{id}/force-password-reset` (equipo, `clientes.gestionar`):
  cambio obligatorio, cierre de sesiones y, si se pide, enlace; con motivo y
  auditoría (`PORTAL_PASSWORD_RESET_FORCED`).

Documentado en docs/seguridad/politicas_de_cuenta.md §«Restablecimiento».
"""
from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.codigos_de_error import desde_valor, error, error_http
from app.core.config import settings
from app.core.deps import requiere_capacidad
from app.core.network import extract_client_ip
from app.core.ratelimit import limiter
from app.core.responses import APIResponse
from app.db.session import get_db, publicar_contexto_de_tenant, sesion_de_sistema
from app.models.client_portal import ClientUser
from app.models.user import User
from app.services.seguridad_de_cuentas import restablecimiento as _rest
from app.services.seguridad_de_cuentas.auditoria import Origen, auditar

router = APIRouter()
logger = logging.getLogger("contecflow.client_portal")

_RESPUESTA_GENERICA = {"ok": True, "message": "Si existe una cuenta asociada, se ha enviado un enlace de restablecimiento."}


class OlvidoIn(BaseModel):
    email: EmailStr = Field(..., max_length=254)


class TokenIn(BaseModel):
    token: str = Field(..., min_length=10, max_length=4096)


class RestablecerIn(TokenIn):
    new_password: str = Field(..., min_length=1, max_length=1024)


class ForzarIn(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500, description="Motivo (queda en la auditoría)")
    send_link: bool = Field(default=True, description="Enviar al cliente el enlace para elegir una contraseña nueva")


def _cliente_del_token(db: Session, carga: dict) -> ClientUser:
    from app.services.client_portal_service import get_active_client_by_id
    cliente = get_active_client_by_id(db, carga.get("sub") or "")
    if not cliente:
        raise error(401, "portal_reset_token_no_valido")
    publicar_contexto_de_tenant(db, cliente, es_cliente=True)
    return cliente


@router.post("/auth/password/forgot", summary="Portal: pedir el enlace para restablecer la contraseña")
@limiter.limit("5/minute")
def portal_password_forgot(request: Request, payload: OlvidoIn,
                           db: Session = Depends(sesion_de_sistema("portal: recuperar contraseña"))):
    from app.services.auth_service.estado_efimero import password_reset_bucket, register_password_reset_request
    inicio = time.monotonic()
    correo = str(payload.email).strip().lower()
    ttl = register_password_reset_request(
        password_reset_bucket("portal:" + _rest.huella(correo), extract_client_ip(request)))
    if ttl > 0:
        raise error(429, "portal_recuperacion_demasiadas_solicitudes", segundos=ttl)

    cliente = db.query(ClientUser).filter(func.lower(ClientUser.email) == correo,
                                          ClientUser.is_active == True).first()  # noqa: E712
    if cliente is not None and cliente.hashed_password:
        try:
            from app.db.session import exigir_organizacion_activa
            exigir_organizacion_activa(db, cliente.organization_id)
            _rest.enviar_enlace_al_cliente(db, cliente)
            auditar(db, None, "PORTAL_PASSWORD_RESET_REQUEST", cliente, org_id=cliente.organization_id,
                    origen=Origen.de(request), recurso="client_user")
            db.commit()
        except Exception as exc:  # misma respuesta pase lo que pase (sin oráculo)
            db.rollback()
            logger.warning("portal: restablecimiento no enviado client_id=%s: %s", cliente.id, type(exc).__name__)
    # Si la cuenta no existe no se apunta nada (RGPD: minimización).
    _rest.igualar_tiempo(inicio)
    return APIResponse.ok(data=_RESPUESTA_GENERICA)


@router.post("/auth/password/policy", summary="Portal: reglas de la contraseña para la pantalla de restablecimiento")
@limiter.limit("20/minute")
def portal_password_policy(request: Request, payload: TokenIn,
                           db: Session = Depends(sesion_de_sistema("portal: política para restablecer"))):
    from app.services.seguridad_de_cuentas.politica import leer
    cliente = _cliente_del_token(db, _rest.leer_token_del_portal(payload.token))
    campos = _rest.campos_de_politica(leer(db, cliente.organization_id))
    # Mismo mínimo que `validar_del_portal`; el portal no guarda historial.
    campos["MIN_PASSWORD_LENGTH"] = max(int(campos["MIN_PASSWORD_LENGTH"]), int(settings.MIN_PASSWORD_LENGTH))
    campos["PASSWORD_HISTORY_COUNT"] = 0
    return APIResponse.ok(data=campos)


@router.post("/auth/password/reset", summary="Portal: restablecer la contraseña con el enlace")
@limiter.limit("10/minute")
def portal_password_reset(request: Request, payload: RestablecerIn,
                          db: Session = Depends(sesion_de_sistema("portal: restablecer contraseña"))):
    from app.core.codigos_de_error import ErrorConCodigo
    from app.services.client_portal_service.autenticacion import hash_password, verify_password
    from app.services.seguridad_de_cuentas.contrasenas import validar_del_portal
    carga = _rest.leer_token_del_portal(payload.token)
    cliente = _cliente_del_token(db, carga)
    try:
        validar_del_portal(db, cliente, payload.new_password, settings.MIN_PASSWORD_LENGTH)
        if cliente.hashed_password and verify_password(payload.new_password, cliente.hashed_password):
            raise ErrorConCodigo("portal_contrasena_igual_a_la_anterior")
    except ValueError as e:
        raise desde_valor(400, e)
    # Un solo uso: comprobar y borrar el `jti` en una operación.
    if not _rest.reclamar_token_del_portal(carga):
        raise error(401, "portal_reset_token_no_valido")
    cliente.hashed_password = hash_password(payload.new_password)
    cliente.must_change_password = False
    _rest.cerrar_sesiones_del_portal(cliente.id)
    auditar(db, None, "PORTAL_PASSWORD_RESET_COMPLETE", cliente, org_id=cliente.organization_id,
            origen=Origen.de(request), recurso="client_user", datos={"sessions_revoked": "all"})
    db.commit()
    return APIResponse.ok(data={"ok": True})


@router.post("/clients/{client_id}/force-password-reset",
             summary="Forzar el restablecimiento de un usuario del portal (cambio obligatorio, cierre de sesiones y enlace)")
def portal_force_password_reset(client_id: str, request: Request, payload: ForzarIn,
                                db: Session = Depends(get_db),
                                current_user: User = Depends(requiere_capacidad("clientes.gestionar"))):
    org = (db.info or {}).get("organization_id") or current_user.organization_id
    cliente = db.query(ClientUser).filter(ClientUser.id == client_id).first()
    if cliente is None or (not current_user.is_superadmin and cliente.organization_id != org):
        raise error_http(404, "no_encontrado", que="cliente")
    cliente.must_change_password = True
    _rest.cerrar_sesiones_del_portal(cliente.id)
    enviado = bool(payload.send_link and cliente.is_active and cliente.hashed_password
                   and _rest.enviar_enlace_al_cliente(db, cliente, forzado=True))
    auditar(db, current_user, "PORTAL_PASSWORD_RESET_FORCED", cliente, org_id=cliente.organization_id,
            origen=Origen.de(request), recurso="client_user",
            datos={"reason": payload.reason, "link_sent": enviado, "sessions_revoked": "all"})
    db.commit()
    return APIResponse.ok(data={"ok": True, "link_sent": enviado})
