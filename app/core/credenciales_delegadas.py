"""Claves de API y tokens del portal de desarrolladores como credencial de la API.

Auditoria 2026-11. Las dos existian y no autenticaban nada:

- las claves de API (`api_keys`, prefijo `nxpm_`) solo las miraba el
  `POST /bookings/api-keys/verify`, sin autenticar, que decia si una clave era
  valida;
- los tokens del portal (`oauth_tokens`) se guardaban con PBKDF2 y sal
  aleatoria y luego se buscaban **por ese hash**, que no coincide nunca: ni
  `/developer/userinfo` ni la revocacion podian funcionar.

Ahora `get_current_user` acepta, ademas de la sesion:

- `X-API-Key: nxpm_…` o `Authorization: Bearer nxpm_…`;
- `Authorization: Bearer <token del portal>`.

La credencial actua **como su dueño** (su rol y su organizacion) y sus
alcances la recortan:

- `read`: solo lectura (GET, HEAD, OPTIONS);
- `write` o `admin`: tambien escritura;
- `projects`, `tasks`, `timesheets`, `billing`, `expenses` (solo tokens del
  portal): lectura y escritura dentro de su area y nada fuera.

Nunca sirve para gestionar credenciales: sesion, contraseña, MFA, SSO, claves
de API ni aplicaciones del portal piden iniciar sesion.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

PREFIJO_CLAVE = "nxpm_"
_LECTURA = {"GET", "HEAD", "OPTIONS"}

#: Rutas que una credencial delegada no puede tocar: gestionan credenciales.
RUTAS_VEDADAS = (
    "/api/v1/auth/", "/api/v1/mfa", "/api/v1/bookings/api-keys", "/api/v1/developer/apps",
    "/api/v1/enterprise/sso", "/api/v1/bookings/sso", "/api/v1/users/me/password",
)
#: Excepciones de solo lectura dentro de las vedadas.
_LECTURAS_PERMITIDAS = ("/api/v1/auth/me",)

#: Alcance de area -> prefijos que abre.
AREAS = {
    "projects": ("/api/v1/projects",),
    "tasks": ("/api/v1/tasks",),
    "timesheets": ("/api/v1/timesheets", "/api/v1/imputations"),
    "billing": ("/api/v1/invoices", "/api/v1/billing-reports"),
    "expenses": ("/api/v1/expenses",),
}
ALCANCES_GENERALES = ("read", "write", "admin")
ALCANCES_VALIDOS = ALCANCES_GENERALES + tuple(AREAS)


def huella(secreto: str) -> str:
    """SHA-256: los secretos son aleatorios de 192+ bits, y asi se pueden buscar."""
    return hashlib.sha256(secreto.encode()).hexdigest()


def _no(detalle: str, codigo: int = status.HTTP_401_UNAUTHORIZED) -> HTTPException:
    return HTTPException(status_code=codigo, detail=detalle, headers={"WWW-Authenticate": "Bearer"})


def comprobar_alcance(metodo: str, ruta: str, alcances: list[str]) -> None:
    """403 si la credencial no cubre esta peticion."""
    vedada = any(ruta.startswith(p) for p in RUTAS_VEDADAS)
    if vedada and not (metodo in _LECTURA and ruta in _LECTURAS_PERMITIDAS):
        raise _no("Una clave de API o un token de aplicación no pueden gestionar credenciales", 403)
    generales = set(alcances) & set(ALCANCES_GENERALES)
    if ruta == "/api/v1/mcp":
        # MCP va siempre por POST: la escritura se decide por herramienta
        # (`mcp_service.permite_escribir`). Un token de área no abre MCP.
        if not generales:
            raise _no("MCP necesita una credencial de alcance read, write o admin", 403)
        return
    if generales:
        if metodo not in _LECTURA and not generales & {"write", "admin"}:
            raise _no("La credencial solo tiene alcance de lectura (read)", 403)
        return
    prefijos = [p for a in alcances for p in AREAS.get(a, ())]
    if not any(ruta == p or ruta.startswith(p + "/") or ruta.startswith(p + "?") for p in prefijos):
        raise _no(f"La credencial no tiene alcance para {ruta} (alcances: {', '.join(alcances) or 'ninguno'})", 403)


def _ventanas(clave, ahora: datetime) -> None:
    """Pone a cero los contadores de la hora y del dia cuando cambian."""
    ultima = clave.last_reset_at
    if ultima is not None and ultima.tzinfo is None:
        ultima = ultima.replace(tzinfo=timezone.utc)
    if ultima is None or ultima.date() != ahora.date():
        clave.requests_today = 0
        clave.requests_this_hour = 0
    elif ultima.hour != ahora.hour:
        clave.requests_this_hour = 0
    clave.last_reset_at = ahora


def _clave_de_api(db: Session, crudo: str):
    from app.models.bookings import ApiKey
    from app.services.bookings_service import _verify_api_key

    clave = db.query(ApiKey).filter(ApiKey.key_digest == huella(crudo)).first()
    if clave is None:
        # Claves anteriores a la huella: bcrypt por prefijo, y se les pone.
        for c in db.query(ApiKey).filter(ApiKey.key_prefix == crudo[:12], ApiKey.key_digest.is_(None)):
            if _verify_api_key(crudo, c.key_hash):
                c.key_digest = huella(crudo)
                clave = c
                break
    if clave is None or not clave.is_active:
        raise _no("API key inválida o revocada")
    ahora = datetime.now(timezone.utc)
    vence = clave.expires_at
    if vence is not None and (vence if vence.tzinfo else vence.replace(tzinfo=timezone.utc)) < ahora:
        raise _no("API key expirada")
    _ventanas(clave, ahora)
    if clave.rate_limit_per_day and (clave.requests_today or 0) >= clave.rate_limit_per_day:
        raise _no("Límite diario de peticiones de la API key alcanzado", 429)
    if clave.rate_limit_per_hour and (clave.requests_this_hour or 0) >= clave.rate_limit_per_hour:
        raise _no("Límite por hora de peticiones de la API key alcanzado", 429)
    clave.requests_today = (clave.requests_today or 0) + 1
    clave.requests_this_hour = (clave.requests_this_hour or 0) + 1
    clave.last_used_at = ahora
    return clave.user_id, json.loads(clave.scopes or '["read"]'), "api_key"


def _token_de_aplicacion(db: Session, crudo: str):
    from app.models.oauth_apps import OAuthApp, OAuthToken

    token = db.query(OAuthToken).filter(OAuthToken.access_token_hash == huella(crudo),
                                        OAuthToken.revoked.is_(False)).first()
    if token is None:
        return None
    vence = token.expires_at
    if vence is not None and (vence if vence.tzinfo else vence.replace(tzinfo=timezone.utc)) < datetime.now(timezone.utc):
        raise _no("Token de aplicación expirado")
    app = db.query(OAuthApp).filter(OAuthApp.id == token.app_id).first()
    if app is None or not app.is_active:
        raise _no("La aplicación del token está desactivada")
    return token.user_id, json.loads(token.scopes or '["read"]'), "oauth"


def resolver(db: Session, request: Request, crudo: Optional[str]):
    """(user_id, alcances, tipo) si `crudo` (o `X-API-Key`) es una credencial delegada; None si no."""
    cabecera = request.headers.get("x-api-key")
    if cabecera:
        return _clave_de_api(db, cabecera.strip())
    if not crudo:
        return None
    if crudo.startswith(PREFIJO_CLAVE):
        return _clave_de_api(db, crudo)
    if crudo.count(".") == 2:
        return None  # un JWT: lo resuelve la sesion
    return _token_de_aplicacion(db, crudo)


def ttl_de_token(db: Session) -> timedelta:
    from app.services.settings_service import get_runtime_int
    minutos = get_runtime_int(db, "DEVELOPER_TOKEN_TTL_MINUTES")
    return timedelta(minutes=minutos or 60)
