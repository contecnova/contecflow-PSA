"""Endpoint MCP (revisión 2026-11): ver `app/services/mcp_service.py`.

Transporte «Streamable HTTP» en su forma simple: un POST con un mensaje JSON-RPC
y una respuesta JSON. La autenticación es la de toda la API: sesión, token o
clave de API (`Authorization: Bearer nxpm_…`); la credencial actúa como su dueño.
"""
from __future__ import annotations
import logging

from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.async_db import run_db
from app.core.deps import get_current_user, require_internal_user
from app.db.session import get_db
from app.models.user import User
from app.services import mcp_service

router = APIRouter()


@router.post("/mcp", summary="Servidor MCP: herramientas de Contecflow para agentes externos")
async def mcp(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
              _rol: User = Depends(require_internal_user)) -> Response:
    try:
        mensaje: Any = await request.json()
    except Exception:
        logging.getLogger(__name__).debug("mcp: excepcion ignorada", exc_info=True)
        return JSONResponse(mcp_service._error(None, mcp_service.PARSE_ERROR, "cuerpo JSON no válido"), status_code=400)
    if isinstance(mensaje, list):
        return JSONResponse(mcp_service._error(None, mcp_service.INVALID_REQUEST, "no se admiten lotes JSON-RPC"),
                            status_code=400)
    # Revisión 2026-11: el trabajo con la base (y las herramientas, que pueden
    # llamar a la IA) va al threadpool; en el handler async bloqueaba el bucle.
    if not await run_db(mcp_service.encendido, db, current_user.organization_id):
        return JSONResponse(mcp_service._error(mensaje.get("id") if isinstance(mensaje, dict) else None,
                                               mcp_service.INVALID_REQUEST,
                                               "MCP está apagado para esta empresa (Gobernanza IA → Módulos)"),
                            status_code=403)
    delegada = getattr(request.state, "credencial_delegada", None)
    alcances = delegada.get("alcances") if delegada else None
    respuesta = await run_db(mcp_service.despachar, db, current_user, mensaje, alcances)
    if respuesta is None:
        return Response(status_code=202)
    return JSONResponse(respuesta)


@router.get("/mcp", summary="MCP: sin canal de servidor (405, como pide la especificación)")
async def mcp_sin_canal(current_user: User = Depends(get_current_user)) -> Response:
    return Response(status_code=405)
