"""Validación de URLs y hosts salientes: el ÚNICO guardia SSRF de la aplicación.

Motivo (auditoría 2026-08, docs/AUDIT_2026_08_SECOND_PASS.md §1.9): había 45 sitios
haciendo `urllib.request.urlopen(...)` sin restringir el esquema. `urlopen` acepta
`file://`, `ftp://` y `data:`, así que una URL de configuración manipulada puede
convertirse en lectura de ficheros locales, y un host interno en SSRF.

Auditoría 22-11-2026 (01 M7, 02 C4/A20/A27/A28/M59/M80/M94, 03 A-RZ4): había
**tres validadores más** (webhooks de empresa, acciones de automatizaciones y
aprovisionamiento de reservas, más el de discovery OIDC) con listas de redes
distintas, y ~30 ficheros que llamaban a `httpx` sin pasar por aquí. Desde el
23-11-2026 todos delegan en este módulo, que además:

- bloquea todo lo que no sea una IP **global** (antes pasaban CGN 100.64/10,
  NAT64 con IPv4 interna y nombres de metadatos de nube);
- valida hosts sin URL (SMTP, IMAP, SNMP, SSH: `validar_host_saliente`);
- ofrece cliente síncrono y asíncrono que comprueban la IP a la que DE VERDAD se
  conecta (cierra el DNS rebinding / TOCTOU entre validar y conectar) y cada
  redirección;
- fija el origen al paginar (`mismo_origen`): un `next` de la respuesta no
  puede llevarse el token a otro host.

Uso:

    from app.core.outbound_url import validate_outbound_url, cliente_httpx
    url = validate_outbound_url(url, field="webhook_url")      # al guardar
    with cliente_httpx(timeout=10) as c:                       # al llamar
        c.post(url, json=...)

`tests/test_ssrf_validador_unico.py` prohíbe `httpx.get/post/Client/...` fuera
de la lista de ficheros revisados (ver docs/seguridad/salidas_de_red.md).
"""
from __future__ import annotations

import http.client
import ipaddress
import socket
import urllib.request
from typing import Optional
from urllib.parse import urlparse

from app.core.codigos_de_error import error

ALLOWED_SCHEMES = frozenset({"http", "https"})

_LOCAL_HOSTNAMES = frozenset({"localhost", "localhost.localdomain"})

#: Nombres de los servicios de metadatos de nube: nunca son un destino legítimo.
_METADATA_HOSTNAMES = frozenset({
    "metadata", "metadata.google", "metadata.google.internal",
    "metadata.azure.com", "instance-data", "instance-data.ec2.internal",
})

_NAT64 = ipaddress.ip_network("64:ff9b::/96")


def validate_outbound_url(url: str, field: str = "url", *, require_https: bool = False) -> str:
    """Devuelve la URL si es segura para una petición saliente; si no, lanza 400.

    Rechaza:
    - esquemas distintos de http/https (mata `file://`, `ftp://`, `data:`)
    - URLs sin host o con credenciales en la URL (`https://user:pass@host`)
    - localhost, dominios `.local`/`.internal` y nombres de metadatos de nube
    - literales IP y nombres que resuelvan a algo que no sea IP global
      (privadas, loopback, link-local, CGN, reservadas, multicast, NAT64 interna)

    Los hosts internos legítimos (p. ej. un Jira on-premise) se declaran en
    `OUTBOUND_PRIVATE_HOSTS_ALLOWED`.

    Esto valida la URL; para la petición usa `abrir()` (urllib),
    `cliente_httpx()` o `cliente_httpx_async()`, que además validan cada
    redirección y la IP a la que de verdad se conecta.
    """
    parsed = urlparse(url or "")
    scheme = parsed.scheme.lower()

    if require_https:
        if scheme != "https":
            raise error(400, "url_debe_ser_https", detail=f"{field} debe ser una URL HTTPS", campo=field)
    elif scheme not in ALLOWED_SCHEMES:
        raise error(400, "url_esquema_no_valido", campo=field, esquema=scheme or 'ningún esquema')

    if parsed.username or parsed.password:
        raise error(400, "url_con_credenciales", campo=field)

    validar_host_saliente(parsed.hostname or "", field=field)
    return url


def validar_url_o_valueerror(url: str, field: str = "url", *, require_https: bool = False) -> str:
    """Igual que `validate_outbound_url`, pero lanza `ErrorConCodigo` (un `ValueError`).

    Para servicios cuyos llamadores ya hacen `except ValueError` (webhooks,
    flujos de reservas, automatizaciones): el código y los parámetros se
    conservan, así que la API sigue respondiendo traducible.
    """
    from app.core.codigos_de_error import ErrorConCodigo
    from app.core.errores import ErrorDeDominio

    try:
        return validate_outbound_url(url, field=field, require_https=require_https)
    except ErrorDeDominio as exc:
        raise ErrorConCodigo(exc.code or "url_no_valida", detail=str(exc.detail), **(exc.params or {})) from exc


def validar_host_saliente(host: str, field: str = "host") -> list:
    """Comprueba un host (sin URL: SMTP, IMAP, SNMP, SSH...) y devuelve sus IPs.

    Lanza 400 si es local, de metadatos o resuelve a una red no global. Devuelve
    las IPs resueltas (vacía si es un host permitido explícitamente o no
    resuelve) para que quien conecte por UDP/sockets propios use una de ellas y
    no vuelva a resolver (DNS rebinding).
    """
    hostname = (host or "").strip().lower().rstrip(".")
    if hostname.startswith("[") and hostname.endswith("]"):
        hostname = hostname[1:-1]
    if not hostname:
        raise error(400, "url_sin_host", detail=f"{field} debe incluir hostname", campo=field)

    if hostname in _hosts_privados_permitidos():
        return []

    if (hostname in _LOCAL_HOSTNAMES or hostname.endswith(".local") or hostname.endswith(".internal")
            or hostname.endswith(".localhost") or hostname in _METADATA_HOSTNAMES):
        raise error(400, "url_host_local", detail=f"{field} no puede apuntar a hosts locales", campo=field)

    try:
        ip_obj = ipaddress.ip_address(hostname.split("%", 1)[0])
    except ValueError:
        ip_obj = None

    if ip_obj is not None:
        if _es_red_prohibida(ip_obj):
            raise error(400, "url_red_no_permitida", campo=field)
        return [ip_obj]

    ips = _resolver(hostname)
    if any(_es_red_prohibida(ip) for ip in ips):
        raise error(400, "url_red_no_permitida", campo=field)
    return ips


def es_red_prohibida(ip_str: str) -> bool:
    """`True` si la IP (texto) no es un destino saliente aceptable."""
    try:
        return _es_red_prohibida(ipaddress.ip_address(str(ip_str).split("%", 1)[0]))
    except ValueError:
        return True


def _es_red_prohibida(ip_obj) -> bool:
    if isinstance(ip_obj, ipaddress.IPv6Address):
        if ip_obj.ipv4_mapped is not None:
            return _es_red_prohibida(ip_obj.ipv4_mapped)
        if ip_obj in _NAT64:
            return _es_red_prohibida(ipaddress.IPv4Address(int(ip_obj) & 0xFFFFFFFF))
    return (
        not ip_obj.is_global
        or ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    )


def _resolver(hostname: str) -> list:
    """Las IPs del nombre. Si no resuelve, ninguna: la petición fallará sola."""
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


def mismo_origen(base: str, siguiente: str) -> bool:
    """`True` si `siguiente` tiene el mismo esquema, host y puerto que `base`.

    Para paginación (`next`, `@odata.nextLink`): sin esto la respuesta remota
    decide a qué host se manda el token en la siguiente página.
    """
    a, b = urlparse(base or ""), urlparse(siguiente or "")
    return (a.scheme.lower(), (a.hostname or "").lower(), a.port) == (
        b.scheme.lower(), (b.hostname or "").lower(), b.port)


# ── Peticiones: redirecciones y DNS rebinding (auditoría 2026-11) ────────────

def _hosts_de_proxy() -> set[str]:
    """Los proxies de salida configurados: conectar con ellos es legítimo."""
    hosts = set()
    for valor in urllib.request.getproxies().values():
        h = urlparse(valor if "://" in valor else f"http://{valor}").hostname
        if h:
            hosts.add(h.lower())
    return hosts


class ConexionBloqueada(RuntimeError):
    """La IP a la que se ha conectado es interna (DNS rebinding o redirección).

    No es un `OSError` a propósito: httpcore convierte los `OSError` de la
    conexión en `ConnectError` genérico y el bloqueo se confundiría con un
    destino caído.
    """


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
        raise ConexionBloqueada(f"Conexion saliente bloqueada: {host} resolvio a una red no permitida ({ip})")


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
    """`urllib.request.urlopen` con la URL, cada redirección y la IP final validadas."""
    url = req.full_url if isinstance(req, urllib.request.Request) else req
    validate_outbound_url(url)
    opener = urllib.request.build_opener(_ManejadorHTTP(), _ManejadorHTTPS(), _RedireccionValidada())
    return opener.open(req, timeout=timeout)


def cabecera_basic(usuario: str, clave: str) -> str:
    """Valor de `Authorization` para HTTP Basic (RFC 7617): «Basic base64(usuario:clave)»."""
    import base64
    return "Basic " + base64.b64encode(f"{usuario}:{clave}".encode()).decode()


def _validar_peticion(request) -> None:
    """Hook de petición: la URL de cada petición (también la primera) se valida."""
    validate_outbound_url(str(request.url), field="url")


def _validar_redireccion(response) -> None:
    if response.next_request is not None:
        validate_outbound_url(str(response.next_request.url), field="redireccion")


def cliente_httpx(**kwargs):
    """`httpx.Client` con cada petición, cada redirección y la IP final validadas."""
    import httpcore
    import httpx

    class _Red(httpcore.SyncBackend):
        # Se comprueba al abrir el socket, antes de mandar un solo byte.
        def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
            flujo = super().connect_tcp(host, port, timeout=timeout, local_address=local_address,
                                        socket_options=socket_options)
            peer = flujo.get_extra_info("server_addr")
            if peer:
                try:
                    comprobar_conexion(host, peer[0])
                except ConexionBloqueada:
                    flujo.close()
                    raise
            return flujo

    class _Transporte(httpx.HTTPTransport):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._pool._network_backend = _Red()  # httpcore 1.x

    hooks = kwargs.pop("event_hooks", {}) or {}
    hooks = {
        **hooks,
        "request": [_validar_peticion, *hooks.get("request", [])],
        "response": [*hooks.get("response", []), _validar_redireccion],
    }
    kwargs.setdefault("transport", _Transporte(verify=kwargs.pop("verify", True)))
    return httpx.Client(event_hooks=hooks, **kwargs)


def cliente_httpx_async(**kwargs):
    """`httpx.AsyncClient` con las mismas garantías que `cliente_httpx`."""
    import httpcore
    import httpx
    from httpcore._backends.auto import AutoBackend

    class _Red(AutoBackend):
        async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
            flujo = await super().connect_tcp(host, port, timeout=timeout, local_address=local_address,
                                              socket_options=socket_options)
            peer = flujo.get_extra_info("server_addr")
            if peer:
                try:
                    comprobar_conexion(host, peer[0])
                except ConexionBloqueada:
                    await flujo.aclose()
                    raise
            return flujo

    class _Transporte(httpx.AsyncHTTPTransport):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._pool._network_backend = _Red()  # httpcore 1.x

    async def _peticion(request):
        _validar_peticion(request)

    async def _redireccion(response):
        _validar_redireccion(response)

    hooks = kwargs.pop("event_hooks", {}) or {}
    hooks = {
        **hooks,
        "request": [_peticion, *hooks.get("request", [])],
        "response": [*hooks.get("response", []), _redireccion],
    }
    kwargs.setdefault("transport", _Transporte(verify=kwargs.pop("verify", True)))
    _ = httpcore  # httpcore 1.x es requisito del transporte
    return httpx.AsyncClient(event_hooks=hooks, **kwargs)


def peticion(metodo: str, url: str, *, field: str = "url", require_https: bool = False,
             timeout: Optional[float] = None, **kwargs):
    """Petición única validada (equivale a `httpx.request` pero segura).

    Sustituye a `httpx.get/post/request(...)` sueltos: valida la URL con el
    campo de origen (para que el error diga qué configuración está mal) y la
    hace con `cliente_httpx`. `follow_redirects` se respeta y cada salto se
    valida; httpx quita `Authorization` al cambiar de origen.
    """
    validate_outbound_url(url, field=field, require_https=require_https)
    seguir = kwargs.pop("follow_redirects", False)
    with cliente_httpx(timeout=timeout if timeout is not None else 15.0, follow_redirects=seguir) as c:
        return c.request(metodo, url, **kwargs)
