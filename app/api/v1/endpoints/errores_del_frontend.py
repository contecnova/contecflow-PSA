"""Informes de error del frontend (auditoria 2026-11).

`RouteBoundary` mandaba los fallos de render a `/api/logs/frontend-error`, una
ruta que no existia: el 404 se perdia y ningun crash quedaba registrado. Esto
solo escribe en el log (nada en BD), con limite de tamaño y de frecuencia; es
publico porque el fallo puede ocurrir antes de iniciar sesion.
"""
import logging

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from app.core.ratelimit import limiter

router = APIRouter()
logger = logging.getLogger("contecflow.frontend")


class ErrorDelFrontend(BaseModel):
    section: str = Field("", max_length=100)
    message: str = Field("", max_length=2000)
    stack: str = Field("", max_length=8000)
    component_stack: str = Field("", max_length=8000)
    url: str = Field("", max_length=1000)
    ua: str = Field("", max_length=500)
    ts: str = Field("", max_length=40)


@router.post("", status_code=204, summary="Registrar un error de render del frontend")
@limiter.limit("30/minute")
def registrar_error_del_frontend(payload: ErrorDelFrontend, request: Request, response: Response):
    logger.error("frontend [%s] %s | %s\n%s\n%s", payload.section, payload.message,
                 payload.url, payload.stack, payload.component_stack)
    return Response(status_code=204)
