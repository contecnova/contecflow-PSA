import ipaddress
import socket
from typing import Optional
from urllib.parse import urlparse

from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


def _parse_ip(value: Optional[str]) -> Optional[str]:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return str(ipaddress.ip_address(raw))
    # intentional: best-effort fallback, log noise outweighs diagnostic value
    except ValueError:
        return None


_PROXY_CACHE = {"expires_at": 0.0, "trust": None, "cidrs_raw": None}
_PROXY_CACHE_TTL = 300.0  # 5 minutes — proxy settings change rarely; hot path


def _effective_proxy_config() -> tuple[bool, str]:
    """Return (TRUST_PROXY_HEADERS, TRUSTED_PROXY_CIDRS) with UI override applied.

    Cached for 5 minutes so the request-path doesn't open a DB session every
    time. Admin changes via Settings → Red / Proxy take effect within 5 min.
    """
    import time as _t
    now = _t.time()
    if _PROXY_CACHE["expires_at"] > now and _PROXY_CACHE["trust"] is not None:
        return bool(_PROXY_CACHE["trust"]), str(_PROXY_CACHE["cidrs_raw"] or "")
    trust = settings.TRUST_PROXY_HEADERS
    cidrs_raw = settings.TRUSTED_PROXY_CIDRS or ""
    try:
        from app.db.session import SessionLocal
        from app.services.settings_service import get_runtime_bool, get_runtime_str
        db = SessionLocal()
        try:
            ui_trust = get_runtime_bool(db, "TRUST_PROXY_HEADERS")
            ui_cidrs = get_runtime_str(db, "TRUSTED_PROXY_CIDRS")
            if ui_trust is not None:
                trust = ui_trust
            if ui_cidrs:
                cidrs_raw = ui_cidrs
        finally:
            db.close()
    except Exception:
        logger.debug("_effective_proxy_config: fallo best-effort ignorado", exc_info=True)
    _PROXY_CACHE["expires_at"] = now + _PROXY_CACHE_TTL
    _PROXY_CACHE["trust"] = trust
    _PROXY_CACHE["cidrs_raw"] = cidrs_raw
    return bool(trust), cidrs_raw


def _trusted_proxy_networks() -> list[ipaddress._BaseNetwork]:
    _, cidrs_raw = _effective_proxy_config()
    cidrs = []
    for raw in cidrs_raw.split(","):
        item = raw.strip()
        if not item:
            continue
        try:
            cidrs.append(ipaddress.ip_network(item, strict=False))
        # intentional: best-effort fallback, log noise outweighs diagnostic value
        except ValueError:
            continue
    return cidrs


def _is_trusted_proxy(ip_raw: Optional[str]) -> bool:
    proxy_ip = _parse_ip(ip_raw)
    if not proxy_ip:
        return False
    ip_obj = ipaddress.ip_address(proxy_ip)
    return any(ip_obj in network for network in _trusted_proxy_networks())


def extract_client_ip(request) -> str:
    direct_ip = _parse_ip(request.client.host if request and request.client else None)
    if not direct_ip:
        return "unknown"

    trust, _ = _effective_proxy_config()
    if not trust or not _is_trusted_proxy(direct_ip):
        return direct_ip

    # Segunda auditoría 2026-11 (#23): se recorre de derecha a izquierda y se
    # devuelve el primer salto que NO es un proxy de confianza. Antes se tomaba
    # el primero de la lista, que lo escribe el cliente: nginx AÑADE la IP
    # (`$proxy_add_x_forwarded_for`), no la sustituye, así que con
    # `X-Forwarded-For: 1.2.3.4` cualquiera elegía su IP ante el rate limiting.
    forwarded_for = request.headers.get("x-forwarded-for", "") if request else ""
    if forwarded_for:
        saltos = [_parse_ip(s) for s in forwarded_for.split(",")]
        saltos = [s for s in saltos if s]
        for salto in reversed(saltos):
            if not _is_trusted_proxy(salto):
                return salto
        if saltos:
            return saltos[0]

    real_ip = _parse_ip(request.headers.get("x-real-ip", "") if request else "")
    if real_ip:
        return real_ip

    return direct_ip


def extract_host(request) -> str:
    """El host pedido, sin puerto. `X-Forwarded-Host` solo si viene de un proxy de confianza."""
    if request is None:
        return ""
    host = request.headers.get("host", "")
    direct_ip = _parse_ip(request.client.host if request.client else None)
    trust, _ = _effective_proxy_config()
    if trust and direct_ip and _is_trusted_proxy(direct_ip):
        host = request.headers.get("x-forwarded-host", "") or host
    return host.split(",")[0].strip().split(":")[0].lower()


class EsquemaDelProxyMiddleware:
    """Aplica `X-Forwarded-Proto` al esquema de la petición si viene de un proxy de confianza.

    Segunda auditoría 2026-11 (#23). Detrás de nginx (que no termina TLS: el
    TLS acaba delante) la API veía `http://` aunque el cliente usara `https://`.
    `request.url` y `request.base_url` salían con el esquema equivocado: la firma
    de Twilio, que se calcula sobre la URL https, no cuadraba, y el `Location`
    de las subidas tus apuntaba a http (contenido mixto).

    No se usa el `--proxy-headers` de uvicorn. Desde la 0.31 admite redes en
    `FORWARDED_ALLOW_IPS` (#30, uvicorn 0.54), pero sustituye el cliente por la
    IP reenviada antes de que la app lo vea: `extract_host` dejaría de
    reconocer a nginx como proxy de confianza y el `X-Forwarded-Host` no se
    aplicaría nunca, y habría dos políticas de confianza que mantener a la par.
    Aquí manda una sola, la que ya decide `X-Forwarded-For` y
    `X-Forwarded-Host` (`TRUST_PROXY_HEADERS` + `TRUSTED_PROXY_CIDRS`, con
    redes), ajustable en caliente desde Settings y válida con cualquier
    servidor ASGI. Solo toca el esquema: la IP del cliente la resuelve
    `extract_client_ip`.
    """

    _ESQUEMAS = {"http": "http", "https": "https"}

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            proto = next((v for k, v in scope.get("headers") or [] if k == b"x-forwarded-proto"), None)
            if proto is not None:
                esquema = self._ESQUEMAS.get(proto.decode("latin1").split(",")[0].strip().lower())
                cliente = scope.get("client")
                if esquema and cliente and _effective_proxy_config()[0] and _is_trusted_proxy(cliente[0]):
                    if scope["type"] == "websocket":
                        esquema = "wss" if esquema == "https" else "ws"
                    scope = dict(scope, scheme=esquema)
        await self.app(scope, receive, send)


def url_publica(request) -> str:
    """La URL de la petición con la base pública configurada (`BACKEND_URL`).

    Para firmas que cubren la URL (Twilio): el remitente firma la URL que tiene
    configurada, y `BACKEND_URL` es esa base —la misma con la que se construyen
    las vueltas de OAuth— sin depender de cómo reescriban los proxies el
    esquema o el host.
    """
    base = (settings.BACKEND_URL or "").rstrip("/")
    consulta = request.url.query
    return f"{base}{request.url.path}" + (f"?{consulta}" if consulta else "")


# ── Outbound SSRF guard ──────────────────────────────────────────────────────
# Single policy shared by every outbound integration (Slack/Teams webhooks,
# automations, etc.). Mirrors the OIDC discovery guard in auth_service
# (validate_https_discovery_url) so private/internal/metadata targets such as
# 169.254.169.254 can never be reached from a user-supplied URL.

class UnsafeURLError(ValueError):
    """Raised when a URL targets a private/internal/disallowed network."""


def _ip_is_disallowed(ip_obj: "ipaddress._BaseAddress") -> bool:
    return (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    )


def assert_safe_outbound_url(url: str, *, require_https: bool = True) -> str:
    """Validate an outbound URL against SSRF before fetching it.

    Raises ``UnsafeURLError`` if the scheme is disallowed, the host is a local
    name, or the literal/resolved IP falls in a private/reserved range. Returns
    the URL unchanged when it is safe so callers can use it inline.
    """
    parsed = urlparse(url or "")
    scheme = parsed.scheme.lower()
    allowed_schemes = {"https"} if require_https else {"http", "https"}
    if scheme not in allowed_schemes or not parsed.netloc:
        raise UnsafeURLError(
            f"URL must use {'/'.join(sorted(allowed_schemes))} and include a host"
        )

    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        raise UnsafeURLError("URL must include a hostname")
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        raise UnsafeURLError("URL must not point to a local host")

    # Literal IP embedded in the host (e.g. http://169.254.169.254/...)
    try:
        literal_ip = ipaddress.ip_address(hostname)
    except ValueError:
        literal_ip = None
    if literal_ip is not None and _ip_is_disallowed(literal_ip):
        raise UnsafeURLError("URL points to a disallowed (private/internal) network")

    # DNS resolution — block hostnames that resolve into private ranges
    default_port = 443 if scheme == "https" else 80
    try:
        addrinfo = socket.getaddrinfo(hostname, parsed.port or default_port, proto=socket.IPPROTO_TCP)
    except Exception:
        logger.debug("assert_safe_outbound_url: excepcion ignorada", exc_info=True)
        addrinfo = []
    for entry in addrinfo:
        try:
            resolved = ipaddress.ip_address(entry[4][0])
        except ValueError:
            continue
        if _ip_is_disallowed(resolved):
            raise UnsafeURLError("URL resolves to a disallowed (private/internal) network")

    return url
