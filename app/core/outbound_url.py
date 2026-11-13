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

import http.client
import ipaddress
import socket
import urllib.request
from urllib.parse import urlparse

from app.core.errores import ErrorDeDominio

ALLOWED_SCHEMES = frozenset({"http", "https"})

_LOCAL_HOSTNAMES = frozenset({"localhost", "localhost.localdomain"})


def validate_outbound_url(url: str, field: str = "url", *, require_https: bool = False) -> str:
    """Devuelve la URL si es segura para una petición saliente; si no, lanza 400.

    Rechaza:
    - esquemas distintos de http/https (mata `file://`, `ftp://`, `data:`)
    - URLs sin host
    - localhost y dominios `.local`
    - literales IP en rangos privados, loopback, link-local, multicast o reservados

    Auditoria 2026-11: tambien resuelve el nombre y rechaza si alguna IP cae en
    esos rangos (antes `jira.miempresa.com -> 10.0.0.5` pasaba). Los hosts
    internos legitimos (p. ej. un Jira on-premise) se declaran en
    `OUTBOUND_PRIVATE_HOSTS_ALLOWED`.

    Esto valida la URL; para la peticion usa `abrir()` (urllib) o
    `cliente_httpx()` (httpx), que ademas validan cada redireccion y la IP a la
    que de verdad se conecta (cierra el DNS rebinding: el nombre puede resolver
    distinto entre la validacion y la conexion).
    """
    parsed = urlparse(url or "")
    scheme = parsed.scheme.lower()

    if require_https:
        if scheme != "https":
            raise ErrorDeDominio(400, f"{field} debe ser una URL HTTPS")
    elif scheme not in ALLOWED_SCHEMES:
        raise ErrorDeDominio(400, f"{field} debe usar http o https, no {scheme or 'ningún esquema'}")

    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        raise ErrorDeDominio(400, f"{field} debe incluir hostname")

    if hostname in _LOCAL_HOSTNAMES or hostname.endswith(".local"):
        raise ErrorDeDominio(400, f"{field} no puede apuntar a hosts locales")

    if hostname in _hosts_privados_permitidos():
        return url

    try:
        ip_obj = ipaddress.ip_address(hostname)
    except ValueError:
        ip_obj = None

    if ip_obj is not None:
        if _es_red_prohibida(ip_obj):
            raise ErrorDeDominio(400, f"{field} apunta a una red no permitida")
        return url

    if any(_es_red_prohibida(ip) for ip in _resolver(hostname)):
        raise ErrorDeDominio(400, f"{field} apunta a una red no permitida")

    return url


def _es_red_prohibida(ip_obj) -> bool:
    return (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    )


def _resolver(hostname: str) -> list:
    """Las IPs del nombre. Si no resuelve, ninguna: la peticion fallara sola."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except (socket.gaierror, UnicodeError, OSError):
        return []
    ips = []
    for info in infos:
        try:
            ips.append(ipaddress.ip_address(info[4][0].split("%", 1)[0]))
        except ValueError:
            continue
    return ips


def _hosts_privados_permitidos() -> set[str]:
    from app.core.config import settings

    crudo = getattr(settings, "OUTBOUND_PRIVATE_HOSTS_ALLOWED", "") or ""
    return {h.strip().lower() for h in crudo.split(",") if h.strip()}


# ── Peticiones: redirecciones y DNS rebinding (auditoria 2026-11) ────────────

def _hosts_de_proxy() -> set[str]:
    """Los proxies de salida configurados: conectar con ellos es legitimo."""
    hosts = set()
    for valor in urllib.request.getproxies().values():
        h = urlparse(valor if "://" in valor else f"http://{valor}").hostname
        if h:
            hosts.add(h.lower())
    return hosts


def comprobar_conexion(host: str, peer_ip: str) -> None:
    """Tras conectar: la IP real no puede ser interna salvo host permitido o proxy."""
    host = (host or "").lower()
    if host in _hosts_privados_permitidos() or host in _hosts_de_proxy():
        return
    try:
        ip = ipaddress.ip_address(peer_ip.split("%", 1)[0])
    except ValueError:
        return
    if _es_red_prohibida(ip):
        raise PermissionError(f"Conexion saliente bloqueada: {host} resolvio a una red no permitida ({ip})")


class _ConexionHTTP(http.client.HTTPConnection):
    def connect(self):
        super().connect()
        comprobar_conexion(self.host, self.sock.getpeername()[0])


class _ConexionHTTPS(http.client.HTTPSConnection):
    def connect(self):
        super().connect()
        comprobar_conexion(self.host, self.sock.getpeername()[0])


class _ManejadorHTTP(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(_ConexionHTTP, req)


class _ManejadorHTTPS(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_ConexionHTTPS, req, context=self._context)


class _RedireccionValidada(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_outbound_url(newurl, field="redireccion")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def abrir(req, timeout: float = 15):
    """`urllib.request.urlopen` con la URL, cada redireccion y la IP final validadas."""
    url = req.full_url if isinstance(req, urllib.request.Request) else req
    validate_outbound_url(url)
    opener = urllib.request.build_opener(_ManejadorHTTP(), _ManejadorHTTPS(), _RedireccionValidada())
    return opener.open(req, timeout=timeout)


def cliente_httpx(**kwargs):
    """`httpx.Client` con cada redireccion y la IP final validadas."""
    import httpx

    def _redireccion(response):
        if response.next_request is not None:
            validate_outbound_url(str(response.next_request.url), field="redireccion")

    import httpcore

    class _Red(httpcore.SyncBackend):
        # Se comprueba al abrir el socket, antes de mandar un solo byte.
        def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
            flujo = super().connect_tcp(host, port, timeout=timeout, local_address=local_address,
                                        socket_options=socket_options)
            peer = flujo.get_extra_info("server_addr")
            if peer:
                try:
                    comprobar_conexion(host, peer[0])
                except PermissionError:
                    flujo.close()
                    raise
            return flujo

    class _Transporte(httpx.HTTPTransport):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._pool._network_backend = _Red()  # httpcore 1.x

    hooks = kwargs.pop("event_hooks", {}) or {}
    hooks = {**hooks, "response": [*hooks.get("response", []), _redireccion]}
    kwargs.setdefault("transport", _Transporte(verify=kwargs.pop("verify", True)))
    return httpx.Client(event_hooks=hooks, **kwargs)
