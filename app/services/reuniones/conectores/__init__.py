"""Conectores «al terminar» (Teams, Zoom, Meet): HTTP común y forma normalizada.

Cada conector devuelve reuniones con la forma de `Importable` y
`servicio.guardar_importada` las convierte en reunión (sin duplicar: única
por empresa + origen + `external_id`). Las pruebas cambian `_transporte` por
un `httpx.MockTransport` (sin red).
"""
from __future__ import annotations
import logging

from dataclasses import dataclass, field
from typing import Optional

import httpx

from app.core.codigos_de_error import ErrorConCodigo

_transporte: Optional[httpx.BaseTransport] = None


def _plazo() -> float:
    try:
        from app.services.settings_service import outbound_http_timeout
        return outbound_http_timeout(default=20)
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).debug("_plazo: excepcion ignorada", exc_info=True)
        return 20.0


def http(metodo: str, url: str, *, plataforma: str, **kw) -> httpx.Response:
    """Petición con errores con código (credencial, no encontrado, no responde)."""
    try:
        with httpx.Client(timeout=_plazo(), transport=_transporte, follow_redirects=True) as c:
            r = c.request(metodo, url, **kw)
    except httpx.HTTPError as exc:
        raise ErrorConCodigo("conector_no_responde", detail=f"{plataforma}: {exc}") from exc
    if r.status_code in (401, 403):
        raise ErrorConCodigo("credencial_rechazada", detail=f"{plataforma}: {r.text[:200]}")
    if r.status_code == 404:
        raise ErrorConCodigo("reuniones_plataforma_no_encontrada", plataforma=plataforma)
    if r.status_code >= 400:
        raise ErrorConCodigo("conector_rechazado", detail=f"{plataforma}: {r.status_code} {r.text[:200]}")
    return r


@dataclass
class Importable:
    origin: str
    external_id: str
    title: Optional[str] = None
    meeting_date: Optional[str] = None
    ends_at: Optional[str] = None
    join_url: Optional[str] = None
    organizer_email: Optional[str] = None
    participants: list = field(default_factory=list)   # [{name, email, role}]
    segments: list = field(default_factory=list)       # [{speaker, start_ms, end_ms, text, email?}]
    language: Optional[str] = None


def exigir_activo(cfg: dict, bloque: str, plataforma: str) -> None:
    if not cfg[bloque]["enabled"]:
        raise ErrorConCodigo("reuniones_conector_desactivado", plataforma=plataforma)
