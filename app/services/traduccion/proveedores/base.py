"""Interfaz comun de los proveedores de traduccion y su salida HTTP.

Un proveedor recibe una lista de textos, el idioma destino, el de origen (o
None: que lo detecte) y, por texto, los terminos del glosario que aparecen en
el con lo que debe salir. Devuelve, en el mismo orden, el texto traducido y el
idioma de origen que ha detectado. Nunca devuelve una lista mas corta: o todo o
`ErrorDeTraduccion` (nunca parcial).

Salida HTTP (`publicar_json`): https obligatorio, URL y redirecciones validadas
contra SSRF (`app.core.outbound_url.cliente_httpx`), tiempo de espera del ajuste
`OUTBOUND_HTTP_TIMEOUT_SECONDS` y metrica por proveedor. En un error nunca se
escribe la clave: solo el estado HTTP.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session


@dataclass
class Traducido:
    texto: str
    origen: Optional[str]


class ErrorDeTraduccion(Exception):
    """Fallo del proveedor con un codigo estable (la interfaz lo traduce: `trad.motivo.<codigo>`)."""

    def __init__(self, codigo: str, detalle: str = ""):
        self.codigo = codigo
        self.detalle = detalle
        super().__init__(f"{codigo}: {detalle}" if detalle else codigo)


class ProveedorDeTraduccion:
    nombre = "base"

    def admite(self, destino: str) -> bool:  # pragma: no cover - interfaz
        raise NotImplementedError

    def traducir(self, textos: list[str], destino: str, origen: Optional[str],
                 glosarios: list[list]) -> list[Traducido]:  # pragma: no cover - interfaz
        raise NotImplementedError


_CODIGOS_HTTP = {401: "auth_failed", 403: "auth_failed", 429: "rate_limited", 456: "quota_exceeded"}


def publicar_json(db: Session, url: str, *, metrica: str, headers: dict, json=None, params=None):
    """POST con la salida protegida. Devuelve el JSON de la respuesta."""
    import httpx

    from app.core.errores import ErrorDeDominio
    from app.core.metrics import track_external_call
    from app.core.outbound_url import cliente_httpx, validate_outbound_url
    from app.services.settings_service import outbound_http_timeout

    try:
        validate_outbound_url(url, field=metrica, require_https=True)
    except (ErrorDeDominio, ValueError, PermissionError) as exc:
        raise ErrorDeTraduccion("url_not_allowed") from exc
    espera = outbound_http_timeout(db)
    try:
        with track_external_call(metrica):
            with cliente_httpx(timeout=espera, follow_redirects=False) as c:
                resp = c.post(url, headers=headers, json=json, params=params)
    except httpx.TimeoutException as exc:
        raise ErrorDeTraduccion("timeout", f"{espera:g} s") from exc
    except httpx.HTTPError as exc:
        raise ErrorDeTraduccion("network", type(exc).__name__) from exc
    except PermissionError as exc:
        raise ErrorDeTraduccion("url_not_allowed") from exc
    if resp.status_code >= 400:
        raise ErrorDeTraduccion(_CODIGOS_HTTP.get(resp.status_code, "provider_error"), f"HTTP {resp.status_code}")
    try:
        return resp.json()
    except ValueError as exc:
        raise ErrorDeTraduccion("bad_response") from exc


def credenciales_de_la_empresa(db: Session, clave: str, org_id: Optional[str]) -> dict:
    """Las credenciales de ESA empresa, descifradas. Sin respaldo global ni del entorno:
    los textos de una empresa nunca salen con las claves de otra."""
    from app.core.encryption import decrypt_value
    from app.db.session import sin_filtro_de_tenant
    from app.models.settings import IntegrationCredential
    from app.services.integration_credentials_service import PROVIDER_REGISTRY

    campos = {f[0]: f for f in PROVIDER_REGISTRY[clave]["fields"]}
    salida = {k: None for k in campos}
    if not org_id:
        return salida
    with sin_filtro_de_tenant(db):
        filas = db.query(IntegrationCredential).filter(IntegrationCredential.provider == clave,
                                                       IntegrationCredential.organization_id == org_id).all()
    for f in filas:
        if f.key not in campos:
            continue
        secreto = campos[f.key][2]
        salida[f.key] = (decrypt_value(f.value_encrypted) if f.value_encrypted else None) if secreto else f.value
    return salida
