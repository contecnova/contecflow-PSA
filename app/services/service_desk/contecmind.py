"""Documentos de contecmind en la sugerencia al agente.

Decision medida el 2026-11-01: la base de conocimiento del Service Desk sigue
en contecflow (articulos cortos, publicos en el portal, que contecmind no puede
servir a un visitante del portal) y los DOCUMENTOS —manuales, procedimientos,
contratos— se buscan en contecmind, que ya los indexa con sus permisos.

Mismo protocolo que el cliente de contecrm (`crmcore/documental/cliente.py`):
1. la credencial de aplicacion se cambia por un token de aplicacion
   (`/api/v1/oauth/token`), que se guarda hasta que caduca;
2. ese token se canjea por uno del USUARIO (`/api/v1/tokens/exchange`): se
   busca con su identidad, y contecmind aplica sus permisos;
3. `/api/v1/documents/search` devuelve `{items: [{document_id, title,
   snippet, score}]}`.

La organizacion que se manda es la de contecflow; en contecmind tiene que
estar dada de alta como tenant de esta aplicacion (si no, 403 y aqui un
aviso). Se configura en Credenciales > «contecmind».
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.services.integration_credentials_service import get_provider_config

logger = logging.getLogger(__name__)

_cache: dict[tuple, tuple[float, str]] = {}
_lock = threading.Lock()


@dataclass
class Resultado:
    documentos: list[dict] = field(default_factory=list)
    configurado: bool = False
    error: Optional[str] = None


def _token_de_aplicacion(cfg: dict) -> str:
    clave = (cfg["base_url"], cfg["client_id"])
    with _lock:
        guardado = _cache.get(clave)
        if guardado and guardado[0] > time.monotonic() + 30:
            return guardado[1]
    r = httpx.post(cfg["base_url"].rstrip("/") + "/api/v1/oauth/token", timeout=10, json={
        "client_id": cfg["client_id"], "client_secret": cfg["client_secret"], "grant_type": "client_credentials"})
    r.raise_for_status()
    datos = r.json()
    token = str(datos.get("access_token") or "")
    if not token:
        raise RuntimeError("contecmind no ha devuelto token de aplicación")
    with _lock:
        _cache[clave] = (time.monotonic() + float(datos.get("expires_in") or 300), token)
    return token


def buscar_documentos(db: Session, org_id: Optional[str], email_usuario: str, texto: str,
                      limite: int = 5) -> Resultado:
    """Documentos de contecmind sobre `texto`, con los permisos del usuario."""
    cfg = get_provider_config(db, "contecmind", org_id=org_id)
    if not (cfg.get("base_url") and cfg.get("client_id") and cfg.get("client_secret")):
        return Resultado()
    if not org_id or not email_usuario or len((texto or "").strip()) < 2:
        return Resultado(configurado=True)
    base = cfg["base_url"].rstrip("/")
    try:
        app = _token_de_aplicacion(cfg)
        canje = httpx.post(base + "/api/v1/tokens/exchange", timeout=10,
                           headers={"Authorization": f"Bearer {app}"},
                           json={"tenant": org_id, "subject": email_usuario, "role": "reader",
                                 "scopes": ["documents:search", "documents:read"], "ttl_s": 300})
        if canje.status_code == 403:
            return Resultado(configurado=True, error="Esta organización no está dada de alta en contecmind")
        canje.raise_for_status()
        token = canje.json().get("token") or canje.json().get("access_token")
        r = httpx.get(base + "/api/v1/documents/search", timeout=15,
                      headers={"Authorization": f"Bearer {token}"},
                      params={"q": texto[:500], "limit": limite})
        r.raise_for_status()
        items = r.json().get("items") or []
    except (httpx.HTTPError, ValueError, RuntimeError) as exc:
        logger.warning("contecmind no disponible: %s", exc)
        return Resultado(configurado=True, error="contecmind no responde")
    return Resultado(configurado=True, documentos=[{
        "document_id": str(i.get("document_id")), "title": i.get("title") or "(sin título)",
        "snippet": i.get("snippet") or "", "score": i.get("score"),
    } for i in items if isinstance(i, dict)][:limite])
