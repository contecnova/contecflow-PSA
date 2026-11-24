"""Endpoint MCP: ver `app/services/mcp_service.py` y `docs/integraciones/MCP.md`.

Transporte «Streamable HTTP» de la especificación MCP (2025-03-26 en adelante),
en su forma sin flujo de servidor: cada POST lleva UN mensaje JSON-RPC y recibe
una respuesta JSON (`application/json`); las notificaciones y las respuestas del
cliente, 202 sin cuerpo; GET y DELETE, 405 (no hay canal SSE ni sesión que
cerrar), como permite la especificación. Lo usan tal cual OpenCode (servidor
remoto) y Claude Code (`claude mcp add --transport http`).

Autenticación: la de toda la API. Para un agente, una clave de API
(`Authorization: Bearer nxpm_…` o `X-API-Key`) o un token OAuth del portal de
desarrolladores; la credencial actúa como su dueño y en la empresa en la que se
creó, y pasa por GRC y ABAC (`get_current_user`). Además, aquí:

- `mcp.usar` (todos los roles; cada herramienta pide luego su propia capacidad);
- la cabecera `Origin`, si viene, debe ser de la propia aplicación
  (`ALLOWED_ORIGINS`): protección frente a DNS rebinding que pide la especificación;
- la cabecera `MCP-Protocol-Version`, si viene, debe ser una versión admitida (400);
- límite de uso por credencial y minuto (`MCP_RATE_LIMIT_PER_MINUTE`): 429 con
  `Retry-After`.

Configuración (Configuración → Agentes de código (MCP), `/settings/mcp`):
`GET/PATCH /mcp/estado`, `GET /mcp/herramientas` y las credenciales propias
`GET/POST /mcp/credenciales`, `DELETE /mcp/credenciales/{id}`. Una credencial
delegada no puede tocarlas (`credenciales_delegadas.RUTAS_VEDADAS`).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.abac_enforce import enforce_abac
from app.core.async_db import run_db
from app.core.codigos_de_error import error_http
from app.core.deps import requiere_capacidad
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.user import User
from app.services.transaccion import confirmar
from app.services import mcp_service

logger = logging.getLogger(__name__)

router = APIRouter()

RUTA = "/api/v1/mcp"
_PERMITIDOS = "POST"


def _json(cuerpo: Optional[dict], status_code: int = 200, cabeceras: Optional[dict] = None) -> Response:
    if cuerpo is None:
        return Response(status_code=202)
    return JSONResponse(cuerpo, status_code=status_code, headers=cabeceras)


def _origen_permitido(request: Request) -> bool:
    origen = request.headers.get("origin")
    if not origen:
        return True               # clientes de terminal y editor no lo mandan
    from app.core.config import settings
    propio = f"{request.url.scheme}://{request.url.netloc}"
    permitidos = {o.rstrip("/") for o in (settings.ALLOWED_ORIGINS or [])} | {propio}
    if getattr(settings, "FRONTEND_URL", None):
        permitidos.add(str(settings.FRONTEND_URL).rstrip("/"))
    return origen.rstrip("/") in permitidos


def _comprobar_y_despachar(db: Session, user: User, mensaje: Any, ctx: mcp_service.Contexto):
    """En el threadpool: encendido, límite de uso y despacho. `(cuerpo, estado, cabeceras)`."""
    rid = mensaje.get("id") if isinstance(mensaje, dict) else None
    org = getattr(user, "organization_id", None)
    if not mcp_service.encendido(db, org):
        return mcp_service.error_con_codigo(rid, mcp_service.SERVER_ERROR, "mcp_apagado"), 403, None
    exceso = mcp_service.consumir_limite(db, org, mcp_service.clave_de_limite(user, ctx))
    if exceso:
        n, segundos = exceso
        return (mcp_service.error_con_codigo(rid, mcp_service.SERVER_ERROR, "mcp_limite_de_uso", n=n,
                                             segundos=segundos), 429, {"Retry-After": str(segundos)})
    return mcp_service.despachar(db, user, mensaje, contexto=ctx), 200, None


@router.post("/mcp", summary="Servidor MCP (Streamable HTTP): herramientas de Contecflow para agentes")
async def mcp(request: Request, db: Session = Depends(get_db),
              current_user: User = Depends(requiere_capacidad("mcp.usar"))) -> Response:
    if not _origen_permitido(request):
        return _json(mcp_service.error_con_codigo(None, mcp_service.SERVER_ERROR, "mcp_origen_no_permitido",
                                                  origen=request.headers.get("origin", "")[:200]), 403)
    version = request.headers.get("mcp-protocol-version")
    if version and version not in mcp_service.SUPPORTED_PROTOCOL_VERSIONS:
        return _json(mcp_service.error_con_codigo(None, mcp_service.INVALID_REQUEST, "mcp_version_no_soportada",
                                                  version=version[:40],
                                                  admitidas=", ".join(mcp_service.SUPPORTED_PROTOCOL_VERSIONS)), 400)
    try:
        mensaje: Any = json.loads(await request.body() or b"null")
    except ValueError:
        logger.debug("mcp: cuerpo JSON no válido", exc_info=True)
        return _json(mcp_service.error_con_codigo(None, mcp_service.PARSE_ERROR, "mcp_json_no_valido"), 400)
    if isinstance(mensaje, list):
        return _json(mcp_service.error_con_codigo(None, mcp_service.INVALID_REQUEST, "mcp_lotes_no_admitidos"), 400)
    ctx = mcp_service.Contexto.de_peticion(request)
    # El trabajo con la base (y las herramientas, que pueden llamar a la IA) va al threadpool.
    cuerpo, estado, cabeceras = await run_db(_comprobar_y_despachar, db, current_user, mensaje, ctx)
    return _json(cuerpo, estado, cabeceras)


@router.get("/mcp", summary="MCP: sin canal SSE del servidor (405, como permite la especificación)")
async def mcp_sin_canal(_usuario: User = Depends(requiere_capacidad("mcp.usar"))) -> Response:
    return Response(status_code=405, headers={"Allow": _PERMITIDOS})


@router.delete("/mcp", summary="MCP: sin sesión que cerrar (405, como permite la especificación)")
async def mcp_sin_sesion(_usuario: User = Depends(requiere_capacidad("mcp.usar"))) -> Response:
    return Response(status_code=405, headers={"Allow": _PERMITIDOS})


# ── Configuración (Configuración → Agentes de código (MCP)) ─────────────────

def _url_publica(request: Request) -> str:
    from app.core.config import settings
    base = (getattr(settings, "BACKEND_URL", None) or str(request.base_url)).rstrip("/")
    return f"{base}{RUTA}"


def _estado(db: Session, user: User, request: Request) -> dict:
    from app.core import capacidades as _capacidades
    from app.services.mcp_herramientas import cuaderno_por_mcp_encendido
    from app.services.settings_service import get_runtime_int
    org = getattr(user, "organization_id", None)
    return {
        "enabled": mcp_service.encendido(db, org),
        "write_mode": mcp_service.modo_de_escritura(db, org),
        "notebook_enabled": cuaderno_por_mcp_encendido(db, org),
        "rate_limit_per_minute": get_runtime_int(db, "MCP_RATE_LIMIT_PER_MINUTE", org, default=60),
        "url": _url_publica(request),
        "protocol_versions": list(mcp_service.SUPPORTED_PROTOCOL_VERSIONS),
        "server_name": "contecflow",
        "can_admin": _capacidades.tiene(db, user, "gobierno.administrar"),
    }


@router.get("/mcp/estado", summary="Estado del servidor MCP de la empresa y la URL para conectar")
def estado_mcp(request: Request, db: Session = Depends(get_db),
               current_user: User = Depends(requiere_capacidad("mcp.usar"))):
    return APIResponse.ok(data=_estado(db, current_user, request))


class EstadoMcpIn(BaseModel):
    enabled: Optional[bool] = Field(None, description="Servidor MCP encendido para la empresa")
    write_mode: Optional[str] = Field(None, pattern=r"^(off|approval|direct)$",
                                      description="Herramientas que escriben: off, approval o direct")
    notebook_enabled: Optional[bool] = Field(None, description="Herramientas de Mi cuaderno por MCP")
    rate_limit_per_minute: Optional[int] = Field(None, ge=0, le=10000,
                                                 description="Llamadas por minuto de cada credencial (0: sin límite propio)")


@router.patch("/mcp/estado", summary="Encender o apagar MCP y sus ajustes para la empresa (auditado)")
def cambiar_estado_mcp(payload: EstadoMcpIn, request: Request, db: Session = Depends(get_db),
                       current_user: User = Depends(requiere_capacidad("gobierno.administrar"))):
    from app.core.network import extract_client_ip
    from app.services import governance_service as _gsvc
    from app.services.audit import audit_log
    from app.services.settings_service import invalidate_cache, set_runtime_value
    org = _gsvc.get_org_id(current_user)
    antes = _estado(db, current_user, request)
    cambios = payload.model_dump(exclude_none=True)
    ip = extract_client_ip(request)
    if "enabled" in cambios:
        _gsvc.upsert_ai_module_config(db, org, mcp_service.MODULO, cambios["enabled"], current_user.id)
    for campo, clave in (("write_mode", "MCP_WRITE_MODE"), ("notebook_enabled", "MCP_NOTEBOOK_ENABLED"),
                         ("rate_limit_per_minute", "MCP_RATE_LIMIT_PER_MINUTE")):
        if campo in cambios:
            set_runtime_value(db, "ai", clave, cambios[campo], org, actor_id=current_user.id, actor_ip=ip,
                              actor_ua=request.headers.get("user-agent"))
    audit_log(db, current_user, "UPDATE", "mcp_config", None, "mcp",
              old_values={k: antes.get(k) for k in cambios}, new_values=cambios,
              metadata={"canal": "settings"}, ip_address=ip)
    confirmar(db)
    invalidate_cache()
    return APIResponse.ok(data=_estado(db, current_user, request))


@router.get("/mcp/herramientas", response_model=APIListResponse[dict],
            summary="Herramientas MCP de trabajo diario y si puedes usarlas (capacidad de su ruta)")
def herramientas_mcp(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("mcp.usar"))):
    items = mcp_service.catalogo_para(db, current_user)
    return APIListResponse.ok(items=items, total=len(items), page=1, page_size=max(1, len(items)))


# ── Credenciales propias para agentes de código ─────────────────────────────

_ALCANCE = {"read": ["mcp:read"], "write": ["mcp:write"]}


def _es_de_mcp(clave: dict) -> bool:
    return bool(set(clave.get("scopes") or []) & {"mcp:read", "mcp:write"})


@router.get("/mcp/credenciales", response_model=APIListResponse[dict], summary="Mis credenciales MCP")
def mis_credenciales(db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("mcp.usar"))):
    from app.services.bookings_service import list_api_keys_records
    items = [c for c in list_api_keys_records(current_user.id, False, db) if _es_de_mcp(c)]
    return APIListResponse.ok(items=items, total=len(items), page=1, page_size=max(1, len(items)))


class CredencialMcpIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120, description="Para qué es (p. ej. «OpenCode portátil»)")
    scope: str = Field("read", description="read: solo lectura; write: lectura y escritura")
    expires_in_days: int = Field(90, ge=1, le=365, description="Días hasta que caduca")


@router.post("/mcp/credenciales", summary="Generar una credencial MCP (la clave se muestra una vez; auditado)")
def crear_credencial(payload: CredencialMcpIn, db: Session = Depends(get_db),
                     current_user: User = Depends(requiere_capacidad("mcp.usar"))):
    from types import SimpleNamespace
    from app.services.bookings_service import create_api_key_record
    alcances = _ALCANCE.get(payload.scope)
    if alcances is None:
        raise error_http(422, "mcp_credencial_alcance_no_valido", alcance=payload.scope[:20])
    vence = datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days)
    datos = SimpleNamespace(name=f"MCP · {payload.name.strip()}", scopes=alcances, rate_limit_per_hour=1000,
                            rate_limit_per_day=10000, expires_at=vence)
    creada = create_api_key_record(datos, current_user.id, db)
    return APIResponse.ok(data={**creada, "scopes": alcances, "expires_at": vence.isoformat()})


@router.delete("/mcp/credenciales/{key_id}", summary="Revocar una credencial MCP propia (auditado)")
def revocar_credencial(key_id: str, db: Session = Depends(get_db),
                       current_user: User = Depends(requiere_capacidad("mcp.usar"))):
    from app.services.bookings_service import revoke_api_key_record
    enforce_abac(db, current_user, "booking_api_key", key_id, action="delete")
    return APIResponse.ok(data=revoke_api_key_record(key_id, current_user.id, db))
