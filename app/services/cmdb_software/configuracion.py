"""Configuración de una instancia: parsear lo relevante y enmascarar secretos.

**Los secretos nunca se guardan.** `enmascarar` sustituye por ``***``:

- el valor de toda clave cuyo nombre lleva password, passwd, pwd, secret,
  token, key (salvo ``ssl_certificate_key``/``keyfile``, que son RUTAS: se
  conserva la ruta, no hay contenido), credential, auth, private,
  community, salt, cookie, session;
- la contraseña de las cadenas de conexión (``mysql://user:clave@host``,
  ``Password=…;``);
- todo bloque PEM (``-----BEGIN … PRIVATE KEY-----``).

Parseadores (devuelven un dict plano y legible, con lo que sirve para
comparar con una línea base y para buscar):

- ``nginx``: versión si viene, ``listen`` (puertos), ``server_name``,
  ``ssl_protocols``, ``ssl_ciphers``, ``ssl_prefer_server_ciphers``,
  ``server_tokens``, ``client_max_body_size``, módulos (``load_module``),
  ``include``, ``root``, ``proxy_pass``/``fastcgi_pass`` (a qué se conecta),
  ``add_header`` (cabeceras de seguridad);
- ``apache``: ``Listen``, ``LoadModule``, ``SSLProtocol``, ``SSLCipherSuite``,
  ``ServerTokens``, ``ServerSignature``, ``TraceEnable``, ``DocumentRoot``,
  ``ProxyPass``, ``Include``;
- ``php_ini`` / ``ini`` / ``my_cnf``: secciones y claves (``expose_php``,
  ``display_errors``, ``allow_url_include``, ``disable_functions``…);
- ``keyvalue`` / ``env``: ``CLAVE=valor``;
- ``json``: un dict ya estructurado (se aplana con puntos).
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Optional

MASCARA = "***"

_SECRETAS = re.compile(r"(passw(or)?d|pwd|secret|token|credential|auth|private|community|salt|cookie|session|"
                       r"api[_-]?key|access[_-]?key|secret[_-]?key|(^|[_.-])key$|^key$)", re.I)
#: Claves con «key» o similares que son RUTAS o nombres, no secretos.
_NO_SECRETAS = re.compile(r"(ssl_certificate_key|sslcertificatekeyfile|keyfile|key_file|key_path|keystore_type|"
                          r"keepalive|monkey|hotkey|sort_key|primary_key|foreign_key|session\.save_path|"
                          r"session\.name|session\.gc_|session\.cookie_(secure|httponly|samesite|lifetime))", re.I)
_URL_CON_CLAVE = re.compile(r"(?P<pre>[a-z][a-z0-9+.\-]*://[^:/\s@]+:)(?P<clave>[^@\s/]+)(?P<post>@)", re.I)
_PARES_CLAVE = re.compile(r"(?P<pre>\b(password|pwd|passwd|secret|token|apikey|api_key)\s*[=:]\s*)"
                          r"(?P<clave>[^;,\s\"']+)", re.I)
_PEM = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)


def es_clave_secreta(clave: str) -> bool:
    c = str(clave or "")
    return bool(_SECRETAS.search(c)) and not _NO_SECRETAS.search(c)


def enmascarar_texto(valor: str) -> str:
    v = _PEM.sub(MASCARA, valor)
    v = _URL_CON_CLAVE.sub(lambda m: m.group("pre") + MASCARA + m.group("post"), v)
    v = _PARES_CLAVE.sub(lambda m: m.group("pre") + MASCARA, v)
    return v


def enmascarar(config: Any, _clave: str = "") -> Any:
    """Copia de `config` sin secretos (recursiva). Devuelve también las claves enmascaradas en `secretas`."""
    if isinstance(config, dict):
        return {k: (MASCARA if es_clave_secreta(k) and v not in (None, "", [], {}) and not isinstance(v, (dict, list))
                    else enmascarar(v, k)) for k, v in config.items()}
    if isinstance(config, list):
        return [enmascarar(v, _clave) for v in config]
    if isinstance(config, str):
        return enmascarar_texto(config)
    return config


def claves_enmascaradas(antes: Any, despues: Any, ruta: str = "") -> list[str]:
    """Rutas de las claves que `enmascarar` tapó (para la auditoría: QUÉ, nunca el valor)."""
    salida: list[str] = []
    if isinstance(antes, dict) and isinstance(despues, dict):
        for k, v in antes.items():
            salida += claves_enmascaradas(v, despues.get(k), f"{ruta}.{k}" if ruta else str(k))
    elif antes != despues and despues is not None and MASCARA in str(despues):
        salida.append(ruta or "*")
    return salida


def huella(config: Any) -> Optional[str]:
    if config in (None, {}, ""):
        return None
    return hashlib.sha256(json.dumps(config, sort_keys=True, default=str).encode()).hexdigest()


def diferencias(antes: Optional[dict], despues: Optional[dict]) -> list[str]:
    """Claves (planas) que cambian, aparecen o desaparecen."""
    a, d = aplanar(antes or {}), aplanar(despues or {})
    return sorted(k for k in set(a) | set(d) if a.get(k) != d.get(k))


def aplanar(config: Any, prefijo: str = "") -> dict:
    salida: dict = {}
    if isinstance(config, dict):
        for k, v in config.items():
            clave = f"{prefijo}.{k}" if prefijo else str(k)
            if isinstance(v, dict):
                salida.update(aplanar(v, clave))
            else:
                salida[clave] = v
    else:
        salida[prefijo or "value"] = config
    return salida


# ── Parseadores ──────────────────────────────────────────────────────────────

def _sin_comentarios(texto: str, marcas=("#",)) -> list[str]:
    lineas = []
    for linea in (texto or "").splitlines():
        s = linea.strip()
        if not s or any(s.startswith(m) for m in marcas):
            continue
        lineas.append(s)
    return lineas


def _anadir(d: dict, clave: str, valor) -> None:
    if clave in d:
        actual = d[clave]
        if not isinstance(actual, list):
            actual = [actual]
        if valor not in actual:
            actual.append(valor)
        d[clave] = actual
    else:
        d[clave] = valor


def _puertos(valores) -> list[int]:
    salida = []
    for v in valores if isinstance(valores, list) else [valores]:
        m = re.search(r"(?:^|\s|:|\])(\d{2,5})(?:\s|$)", f" {v} ".replace("[::]", "[]"))
        if m:
            salida.append(int(m.group(1)))
        elif str(v).strip().isdigit():
            salida.append(int(str(v).strip()))
    return sorted(set(salida))


_NGINX_CLAVES = ("listen", "server_name", "ssl_protocols", "ssl_ciphers", "ssl_prefer_server_ciphers",
                 "server_tokens", "client_max_body_size", "load_module", "include", "root", "proxy_pass",
                 "fastcgi_pass", "uwsgi_pass", "add_header", "ssl_certificate", "ssl_certificate_key",
                 "ssl_session_tickets", "ssl_stapling", "autoindex", "worker_processes", "keepalive_timeout",
                 "access_log", "error_log", "user", "http2", "limit_req_zone", "auth_basic", "allow", "deny")


def parsear_nginx(texto: str) -> dict:
    """Las directivas relevantes de un `nginx.conf` (o de `nginx -T`)."""
    d: dict = {}
    m = re.search(r"nginx version:\s*nginx/([\w.\-]+)", texto or "")
    if m:
        d["version"] = m.group(1)
    servidores = 0
    for linea in _sin_comentarios(texto):
        if re.match(r"^server\s*\{", linea):
            servidores += 1
        for parte in linea.split(";"):
            parte = parte.strip().lstrip("{").strip()
            if not parte:
                continue
            trozos = parte.split(None, 1)
            directiva = trozos[0]
            if directiva in _NGINX_CLAVES and len(trozos) > 1:
                _anadir(d, directiva, trozos[1].strip().rstrip("{").strip())
    if "listen" in d:
        d["ports"] = _puertos(d["listen"])
        d["tls"] = any("ssl" in str(x) or "443" in str(x) for x in (d["listen"] if isinstance(d["listen"], list)
                                                                    else [d["listen"]]))
    if "ssl_protocols" in d:
        protos = " ".join(d["ssl_protocols"] if isinstance(d["ssl_protocols"], list) else [d["ssl_protocols"]])
        d["tls_protocols"] = sorted(set(protos.split()))
    if "load_module" in d:
        d["modules"] = sorted({re.sub(r"^.*/|\.so$", "", m) for m in
                               (d["load_module"] if isinstance(d["load_module"], list) else [d["load_module"]])})
    upstreams = []
    for k in ("proxy_pass", "fastcgi_pass", "uwsgi_pass"):
        v = d.get(k)
        upstreams += v if isinstance(v, list) else ([v] if v else [])
    if upstreams:
        d["upstreams"] = sorted(set(upstreams))
    d["server_blocks"] = servidores
    return d


_APACHE_CLAVES = ("Listen", "LoadModule", "SSLProtocol", "SSLCipherSuite", "ServerTokens", "ServerSignature",
                  "TraceEnable", "DocumentRoot", "ProxyPass", "ProxyPassReverse", "Include", "IncludeOptional",
                  "ServerName", "SSLEngine", "Options", "Header", "Timeout", "KeepAlive", "User", "Group",
                  "SSLCertificateFile", "SSLCertificateKeyFile", "SSLHonorCipherOrder")


def parsear_apache(texto: str) -> dict:
    d: dict = {}
    m = re.search(r"Server version:\s*Apache/([\w.\-]+)", texto or "")
    if m:
        d["version"] = m.group(1)
    for linea in _sin_comentarios(texto):
        if linea.startswith("<"):
            continue
        trozos = linea.split(None, 1)
        if trozos[0] in _APACHE_CLAVES and len(trozos) > 1:
            _anadir(d, trozos[0], trozos[1].strip())
    if "Listen" in d:
        d["ports"] = _puertos(d["Listen"])
    if "LoadModule" in d:
        d["modules"] = sorted({str(x).split()[0] for x in
                               (d["LoadModule"] if isinstance(d["LoadModule"], list) else [d["LoadModule"]])})
    if "SSLProtocol" in d:
        protos = " ".join(d["SSLProtocol"] if isinstance(d["SSLProtocol"], list) else [d["SSLProtocol"]])
        d["tls_protocols"] = sorted(set(protos.split()))
    return d


def parsear_ini(texto: str) -> dict:
    """php.ini, my.cnf y cualquier INI: ``{seccion: {clave: valor}}``; sin sección, en la raíz."""
    d: dict = {}
    seccion: Optional[str] = None
    for linea in _sin_comentarios(texto, ("#", ";")):
        m = re.match(r"^\[(.+)\]$", linea)
        if m:
            seccion = m.group(1).strip()
            d.setdefault(seccion, {})
            continue
        if "=" in linea:
            k, v = linea.split("=", 1)
        else:
            k, v = linea, "true"
        k, v = k.strip(), v.strip().strip('"').strip("'")
        destino = d[seccion] if seccion else d
        destino[k] = v
    # PHP: las directivas viven en [PHP]; se suben a la raíz para buscarlas igual.
    if isinstance(d.get("PHP"), dict):
        for k, v in d.pop("PHP").items():
            d.setdefault(k, v)
    return d


def parsear_clave_valor(texto: str) -> dict:
    d: dict = {}
    for linea in _sin_comentarios(texto, ("#", ";", "//")):
        linea = re.sub(r"^export\s+", "", linea)
        if "=" in linea:
            k, v = linea.split("=", 1)
        elif ":" in linea:
            k, v = linea.split(":", 1)
        else:
            continue
        d[k.strip()] = v.strip().strip('"').strip("'")
    return d


PARSEADORES = {"nginx": parsear_nginx, "apache": parsear_apache, "php_ini": parsear_ini, "ini": parsear_ini,
               "my_cnf": parsear_ini, "keyvalue": parsear_clave_valor, "env": parsear_clave_valor}


def formato_por_producto(nombre: Optional[str], ruta: Optional[str] = None) -> Optional[str]:
    n = (nombre or "").lower()
    r = (ruta or "").lower()
    if "nginx" in n or r.endswith("nginx.conf"):
        return "nginx"
    if "apache" in n or "httpd" in n or r.endswith(("httpd.conf", "apache2.conf")):
        return "apache"
    if "php" in n or r.endswith("php.ini"):
        return "php_ini"
    if r.endswith((".cnf", ".ini")) or "mysql" in n or "mariadb" in n:
        return "ini"
    if r.endswith((".env", ".properties", ".conf")):
        return "keyvalue"
    return None


def interpretar(config: Any = None, texto: Optional[str] = None, formato: Optional[str] = None,
                producto: Optional[str] = None, ruta: Optional[str] = None) -> tuple[Optional[dict], Optional[str]]:
    """(configuración enmascarada, formato). `config` (dict) manda; si no, se parsea `texto`."""
    if isinstance(config, dict) and config:
        return enmascarar(config), formato or "json"
    if texto:
        formato = formato or formato_por_producto(producto, ruta) or "keyvalue"
        parseador = PARSEADORES.get(formato, parsear_clave_valor)
        return enmascarar(parseador(texto)), formato
    return None, formato


# ── Línea base ────────────────────────────────────────────────────────────────

OPERADORES = ("eq", "neq", "contains", "not_contains", "regex", "in", "not_in", "present", "absent",
              "min_version")


def _como_lista(v) -> list:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    return [str(v)]


def evaluar_regla(config: dict, regla: dict) -> Optional[dict]:
    """None si cumple; si no, {key, op, expected, actual, severity}."""
    plano = aplanar(config or {})
    clave = str(regla.get("key") or "")
    op = regla.get("op") or "eq"
    esperado = regla.get("value")
    actual = plano.get(clave, (config or {}).get(clave))
    texto = " ".join(_como_lista(actual)).lower()
    ok = True
    if op == "present":
        ok = actual not in (None, "", [])
    elif op == "absent":
        ok = actual in (None, "", [])
    elif op == "eq":
        ok = texto == str(esperado or "").lower()
    elif op == "neq":
        ok = texto != str(esperado or "").lower()
    elif op == "contains":
        ok = str(esperado or "").lower() in texto
    elif op == "not_contains":
        ok = str(esperado or "").lower() not in texto
    elif op == "regex":
        try:
            ok = re.search(str(esperado or ""), " ".join(_como_lista(actual))) is not None
        except re.error:
            ok = False
    elif op in ("in", "not_in"):
        permitidos = {x.strip().lower() for x in (esperado if isinstance(esperado, list)
                                                   else str(esperado or "").split(","))}
        valores = {x.strip().lower() for x in " ".join(_como_lista(actual)).split()} if actual not in (None, "") else set()
        ok = valores <= permitidos if op == "in" else not (valores & permitidos)
    elif op == "min_version":
        from app.services.cmdb_software.versiones import comparar, valida
        ok = valida(str(actual or "")) and comparar(str(actual), str(esperado)) >= 0
    if ok:
        return None
    return {"key": clave, "op": op, "expected": esperado, "actual": actual,
            "severity": regla.get("severity") or "medium", "description": regla.get("description")}


def evaluar_linea_base(config: dict, reglas: list[dict]) -> list[dict]:
    return [r for r in (evaluar_regla(config, x) for x in reglas or []) if r]
