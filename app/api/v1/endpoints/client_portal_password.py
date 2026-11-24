"""Portal de clientes: «¿Olvidaste tu contraseña?» y restablecimiento forzado (23-11-2026).

Incidencia de usuario: «No hay función de restablecer contraseña para los
usuarios». El portal no tenía nada; el patrón es el del operador
(`/auth/password/*`, `app/api/v1/routers/auth_core.py`) con las piezas comunes
de `app/services/seguridad_de_cuentas/restablecimiento.py`:

- `POST /portal/auth/password/forgot`: misma respuesta y tiempo parecido exista o
  no el correo; 24-11-2026 (migración 208): un enlace por cada empresa en la que
  existe la cuenta, o solo el de la empresa del código de acceso o del host; límite por (hash del correo, IP) y por minuto; auditado solo si la
  cuenta existe (`PORTAL_PASSWORD_RESET_REQUEST`), sin guardar lo tecleado si no.
- `POST /portal/auth/password/policy`: las reglas de la empresa para la pantalla.
- `POST /portal/auth/password/reset`: token de un solo uso (30 min), política de
  la empresa (`validar_del_portal`), cierra TODAS las sesiones del portal del
  cliente y audita (`PORTAL_PASSWORD_RESET_COMPLETE`).
- `POST /portal/clients/{id}/force-password-reset` (equipo, `clientes.gestionar`):
  cambio obligatorio, cierre de sesiones y, si se pide, enlace; con motivo y
  auditoría (`PORTAL_PASSWORD_RESET_FORCED`).
- `POST /portal/clients/{id}/set-password` (equipo, `clientes.gestionar`,
  23-11-2026): contraseña puesta a mano con la política de la empresa, obligar a
  cambiarla en el primer acceso, envío opcional por correo al titular, cierre de
  TODAS sus sesiones y auditoría (`PORTAL_PASSWORD_SET`) sin la contraseña.

Documentado en docs/seguridad/politicas_de_cuenta.md §«Restablecimiento».
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.core.config import settings
from app.core.deps import requiere_capacidad
from app.core.network import extract_client_ip
from app.core.ratelimit import limiter
from app.core.responses import APIResponse
from app.db.session import get_db, publicar_contexto_de_tenant, sesion_de_sistema
from app.models.client_portal import ClientUser
from app.models.user import User
from app.services.seguridad_de_cuentas import restablecimiento as _rest
from app.services.seguridad_de_cuentas.auditoria import Origen

router = APIRouter()
logger = logging.getLogger("contecflow.client_portal")

_RESPUESTA_GENERICA = {"ok": True, "message": "Si existe una cuenta asociada, se ha enviado un enlace de restablecimiento."}


class OlvidoIn(BaseModel):
    email: EmailStr = Field(..., max_length=254)
    # Migración 208: código de acceso del portal (`slug` de la empresa); sin él ni
    # dominio propio, un enlace por cada empresa en la que existe la cuenta.
    organization_code: Optional[str] = Field(None, max_length=100)


class TokenIn(BaseModel):
    token: str = Field(..., min_length=10, max_length=4096)


class RestablecerIn(TokenIn):
    new_password: str = Field(..., min_length=1, max_length=1024)


class EstablecerIn(BaseModel):
    # Sin `min_length`: la longitud la decide la política de la empresa (error con código).
    password: str = Field(..., min_length=1, max_length=1024, repr=False)
    must_change_password: bool = Field(default=True, description="Obligar a cambiarla en el primer acceso")
    send_access: bool = Field(default=False, description="Enviar el acceso (con la contraseña) por correo al titular")


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

    # Si la cuenta no existe no se apunta nada (RGPD: minimización).
    from app.core.network import extract_host
    _rest.pedir_en_el_portal(db, correo, Origen.de(request), codigo=payload.organization_code,
                             host=extract_host(request))
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
    # Migración 208: el restablecimiento es de la cuenta de UNA empresa; la pantalla la nombra.
    campos["organization_name"] = _rest.nombre_de_empresa(db, cliente.organization_id)
    return APIResponse.ok(data=campos)


@router.post("/auth/password/reset", summary="Portal: restablecer la contraseña con el enlace")
@limiter.limit("10/minute")
def portal_password_reset(request: Request, payload: RestablecerIn,
                          db: Session = Depends(sesion_de_sistema("portal: restablecer contraseña"))):
    carga = _rest.leer_token_del_portal(payload.token)
    cliente = _cliente_del_token(db, carga)
    _rest.restablecer_en_el_portal(db, cliente, carga, payload.new_password, settings.MIN_PASSWORD_LENGTH,
                                   Origen.de(request))
    return APIResponse.ok(data={"ok": True})


@router.post("/clients/{client_id}/force-password-reset",
             summary="Forzar el restablecimiento de un usuario del portal (cambio obligatorio, cierre de sesiones y enlace)")
def portal_force_password_reset(client_id: str, request: Request, payload: ForzarIn,
                                db: Session = Depends(get_db),
                                current_user: User = Depends(requiere_capacidad("clientes.gestionar"))):
    org = (db.info or {}).get("organization_id") or current_user.organization_id
    enviado = _rest.forzar_en_el_portal(db, current_user, org, client_id, payload.reason, payload.send_link,
                                        Origen.de(request))
    return APIResponse.ok(data={"ok": True, "link_sent": enviado})


@router.post("/clients/{client_id}/set-password",
             summary="Establecer a mano la contraseña de un usuario del portal (política de la empresa, sesiones cerradas)")
def portal_set_password(client_id: str, request: Request, payload: EstablecerIn,
                        db: Session = Depends(get_db),
                        current_user: User = Depends(requiere_capacidad("clientes.gestionar"))):
    """23-11-2026 (portal_usuarios). La contraseña no vuelve en la respuesta ni va
    a los logs ni a la auditoría (que guarda quién, a quién, si obliga a cambiarla
    y si se envió)."""
    from app.services.client_portal_service.usuarios import establecer_contrasena
    return APIResponse.ok(data=establecer_contrasena(
        db, current_user, client_id, payload.password, obligar_cambio=payload.must_change_password,
        enviar=payload.send_access, origen=Origen.de(request)))
