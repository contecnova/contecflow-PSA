"""Cliente HTTP de los conectores de uso.

Una sola puerta de salida para todos: tiempo de espera del ajuste
`OUTBOUND_HTTP_TIMEOUT_SECONDS` (de la empresa), URLs y redirecciones
validadas contra SSRF (`app.core.outbound_url.cliente_httpx`: Okta y Jamf
llevan una URL que escribe el cliente), métricas por proveedor y errores
traducidos a `ErrorDeConector` con un código estable. Nunca se escribe en un
error la cabecera de autorización ni un secreto: solo el estado HTTP y el
mensaje de la fuente, recortado.

Los tests sustituyen esta clase por un doble con la misma interfaz
(`obtener_json`, `obtener_texto`, `enviar_formulario`).
"""
from __future__ import annotations

import logging
from typing import Optional

from app.services.alm_uso.proveedores.base import ErrorDeConector

logger = logging.getLogger(__name__)

_CODIGOS = {401: "AUTH_FAILED", 403: "FORBIDDEN", 404: "NOT_FOUND", 429: "RATE_LIMITED"}


def _mensaje_de_fuente(resp) -> str:
    try:
        cuerpo = resp.json()
    except ValueError:
        return (resp.text or "")[:300]
    if isinstance(cuerpo, dict):
        err = cuerpo.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or err.get("code") or "")[:300]
        return str(cuerpo.get("error_description") or err or cuerpo.get("errorSummary")
                   or cuerpo.get("message") or "")[:300]
    return ""


class ClienteHttp:
    def __init__(self, timeout: float, metrica: str):
        self.timeout = timeout
        self.metrica = metrica

    def _peticion(self, metodo: str, url: str, **kw):
        import httpx
        from app.core.metrics import track_external_call
        from app.core.outbound_url import cliente_httpx, validate_outbound_url

        validate_outbound_url(url, field="alm_uso", require_https=True)
        try:
            with track_external_call(self.metrica):
                with cliente_httpx(timeout=self.timeout, follow_redirects=True) as c:
                    resp = c.request(metodo, url, **kw)
        except httpx.TimeoutException as exc:
            raise ErrorDeConector("TIMEOUT", f"La fuente no respondió en {self.timeout:g} s") from exc
        except httpx.HTTPError as exc:
            raise ErrorDeConector("NETWORK", f"No se pudo conectar con la fuente: {type(exc).__name__}") from exc
        except PermissionError as exc:
            raise ErrorDeConector("URL_NOT_ALLOWED", "La dirección de la fuente no está permitida") from exc
        if resp.status_code >= 400:
            codigo = _CODIGOS.get(resp.status_code, "SERVER_ERROR" if resp.status_code >= 500 else "BAD_REQUEST")
            raise ErrorDeConector(codigo, f"HTTP {resp.status_code}: {_mensaje_de_fuente(resp)}",
                                  estado_http=resp.status_code)
        return resp

    def obtener_json(self, url: str, *, headers: Optional[dict] = None, params: Optional[dict] = None) -> tuple:
        """(cuerpo JSON, cabeceras de respuesta)."""
        resp = self._peticion("GET", url, headers=headers or {}, params=params)
        try:
            return resp.json(), dict(resp.headers)
        except ValueError as exc:
            raise ErrorDeConector("BAD_RESPONSE", "La fuente no devolvió JSON") from exc

    def obtener_texto(self, url: str, *, headers: Optional[dict] = None, params: Optional[dict] = None) -> str:
        return self._peticion("GET", url, headers=headers or {}, params=params).text

    def enviar_formulario(self, url: str, datos: dict, *, headers: Optional[dict] = None) -> dict:
        resp = self._peticion("POST", url, data=datos, headers=headers or {})
        try:
            return resp.json()
        except ValueError as exc:
            raise ErrorDeConector("BAD_RESPONSE", "La fuente no devolvió JSON") from exc


def cliente_para(db, metrica: str) -> ClienteHttp:
    """El cliente con la espera de las llamadas salientes (`OUTBOUND_HTTP_TIMEOUT_SECONDS`).

    Los informes de uso son descargas más grandes que una llamada corriente: 30 s
    mientras el operador no fije el ajuste; fijado, manda el ajuste.
    """
    from app.services.settings_service import outbound_http_timeout
    return ClienteHttp(outbound_http_timeout(db, default=30), metrica)


def siguiente_de_link(cabeceras: dict) -> Optional[str]:
    """La URL `rel="next"` de una cabecera Link (Okta)."""
    link = cabeceras.get("link") or cabeceras.get("Link") or ""
    for parte in link.split(","):
        trozos = parte.split(";")
        if len(trozos) >= 2 and 'rel="next"' in trozos[1].replace(" ", ""):
            return trozos[0].strip().strip("<>")
    return None
