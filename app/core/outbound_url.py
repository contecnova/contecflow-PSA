"""Validación de URLs salientes antes de hacer peticiones desde el servidor.

Motivo (auditoría 2026-08, docs/AUDIT_2026_08_SECOND_PASS.md §1.9): había 45 sitios
haciendo `urllib.request.urlopen(...)` sin restringir el esquema. `urlopen` acepta
`file://`, `ftp://` y `data:`, así que una URL de configuración manipulada puede
convertirse en lectura de ficheros locales, y un host interno en SSRF.

`app/services/auth_service.py` ya tenía la comprobación correcta, pero solo para la
URL de discovery de OIDC. Este módulo la generaliza para poder aplicarla en los
puntos por donde pasan las llamadas salientes.

Uso:

    from app.core.outbound_url import validate_outbound_url
    url = validate_outbound_url(url, field="webhook_url")
"""
from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from fastapi import HTTPException

ALLOWED_SCHEMES = frozenset({"http", "https"})

_LOCAL_HOSTNAMES = frozenset({"localhost", "localhost.localdomain"})


def validate_outbound_url(url: str, field: str = "url", *, require_https: bool = False) -> str:
    """Devuelve la URL si es segura para una petición saliente; si no, lanza 400.

    Rechaza:
    - esquemas distintos de http/https (mata `file://`, `ftp://`, `data:`)
    - URLs sin host
    - localhost y dominios `.local`
    - literales IP en rangos privados, loopback, link-local, multicast o reservados

    No resuelve DNS a propósito: hacerlo abriría una ventana TOCTOU (el nombre podría
    resolver a otra IP en el momento de la petición) y añadiría latencia y un fallo
    externo a una ruta de validación. Para defensa completa frente a SSRF por DNS
    rebinding hace falta control a nivel de red o egreso, no validación de cadena.
    """
    parsed = urlparse(url or "")
    scheme = parsed.scheme.lower()

    if require_https:
        if scheme != "https":
            raise HTTPException(400, f"{field} debe ser una URL HTTPS")
    elif scheme not in ALLOWED_SCHEMES:
        raise HTTPException(400, f"{field} debe usar http o https, no {scheme or 'ningún esquema'}")

    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        raise HTTPException(400, f"{field} debe incluir hostname")

    if hostname in _LOCAL_HOSTNAMES or hostname.endswith(".local"):
        raise HTTPException(400, f"{field} no puede apuntar a hosts locales")

    try:
        ip_obj = ipaddress.ip_address(hostname)
    except ValueError:
        ip_obj = None

    if ip_obj is not None and (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    ):
        raise HTTPException(400, f"{field} apunta a una red no permitida")

    return url
