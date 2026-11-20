"""Identificadores normalizados de software: purl, CPE 2.3 y clave de conciliación.

- purl (https://github.com/package-url/purl-spec):
  ``pkg:type/namespace/name@version?qualifiers#subpath``.
- CPE 2.3 (NISTIR 7695): ``cpe:2.3:part:vendor:product:version:update:...``.

La **clave de conciliación** de un producto (`clave_de_producto`) es la que
une lo que llega por SBOM, por agente, por CSV o a mano:

1. purl: ``purl:<tipo>/<espacio>/<nombre>`` (minúsculas; pypi normaliza
   ``_`` y ``.`` a ``-``);
2. si no, CPE: ``cpe:<fabricante>:<producto>``;
3. si no, nombre normalizado: ``name:<letras y números>``, resolviendo los
   alias conocidos (``php-fpm`` → php, ``httpd`` → apache…).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote, unquote


@dataclass
class Purl:
    type: str
    name: str
    namespace: Optional[str] = None
    version: Optional[str] = None
    qualifiers: dict = field(default_factory=dict)
    subpath: Optional[str] = None

    def clave(self) -> str:
        """`tipo/espacio/nombre` normalizado (sin versión): identifica el paquete."""
        return clave_de_paquete(self.type, self.namespace, self.name)

    def texto(self, con_version: bool = True) -> str:
        return construir_purl(self.type, self.namespace, self.name, self.version if con_version else None,
                              self.qualifiers)


def _normalizar_nombre(tipo: str, nombre: str) -> str:
    nombre = (nombre or "").strip()
    tipo = (tipo or "").lower()
    if tipo == "pypi":
        return re.sub(r"[-_.]+", "-", nombre).lower()
    if tipo in ("npm", "composer", "github", "gitlab", "bitbucket", "golang", "deb", "rpm", "apk", "generic",
                "docker", "oci", "gem", "cargo", "nuget", "hex", "pub", "swift", "cocoapods", "conan", "hackage"):
        return nombre.lower()
    return nombre.lower()


def clave_de_paquete(tipo: Optional[str], espacio: Optional[str], nombre: Optional[str]) -> str:
    tipo = (tipo or "generic").lower().strip()
    espacio = (espacio or "").strip().strip("/")
    if tipo == "golang":
        espacio = espacio.lower()
    elif espacio:
        espacio = espacio.lower()
    return f"{tipo}/{espacio}/{_normalizar_nombre(tipo, nombre or '')}"


def parsear_purl(texto: Optional[str]) -> Optional[Purl]:
    """`Purl` o None si no es un purl."""
    if not texto or not isinstance(texto, str):
        return None
    t = texto.strip()
    if not t.lower().startswith("pkg:"):
        return None
    t = t[4:].lstrip("/")
    subpath = None
    if "#" in t:
        t, subpath = t.split("#", 1)
    qualifiers: dict = {}
    if "?" in t:
        t, q = t.split("?", 1)
        for parte in q.split("&"):
            if "=" in parte:
                k, v = parte.split("=", 1)
                qualifiers[k.lower()] = unquote(v)
    version = None
    # La versión va tras la última «@» del último segmento (el espacio de npm empieza por «@»).
    if "@" in t.rsplit("/", 1)[-1]:
        t, version = t.rsplit("@", 1)
        version = unquote(version)
    partes = [unquote(p) for p in t.split("/") if p]
    if len(partes) < 2:
        return None
    tipo = partes[0].lower()
    nombre = partes[-1]
    espacio = "/".join(partes[1:-1]) or None
    return Purl(type=tipo, namespace=espacio, name=nombre, version=version or None, qualifiers=qualifiers,
                subpath=subpath)


def construir_purl(tipo: Optional[str], espacio: Optional[str], nombre: Optional[str],
                   version: Optional[str] = None, qualifiers: Optional[dict] = None) -> Optional[str]:
    if not nombre:
        return None
    tipo = (tipo or "generic").lower()
    partes = [tipo]
    if espacio:
        partes.extend(quote(p, safe="@") for p in espacio.split("/") if p)
    partes.append(quote(nombre, safe=""))
    s = "pkg:" + "/".join(partes)
    if version:
        s += "@" + quote(str(version), safe="+:~")
    if qualifiers:
        s += "?" + "&".join(f"{k}={quote(str(v), safe='')}" for k, v in sorted(qualifiers.items()) if v)
    return s


# ── CPE 2.3 ──────────────────────────────────────────────────────────────────

@dataclass
class Cpe:
    part: str
    vendor: str
    product: str
    version: Optional[str] = None

    def clave(self) -> str:
        return f"cpe:{self.vendor}:{self.product}"


def _cpe_valor(v: str) -> Optional[str]:
    v = (v or "").replace("\\", "")
    return None if v in ("*", "-", "") else v.lower()


def parsear_cpe(texto: Optional[str]) -> Optional[Cpe]:
    """CPE 2.3 formateado (o URI 2.2 ``cpe:/a:vendor:product:version``)."""
    if not texto or not isinstance(texto, str):
        return None
    t = texto.strip()
    if t.lower().startswith("cpe:2.3:"):
        partes = re.split(r"(?<!\\):", t)
        if len(partes) < 5:
            return None
        vendor, product = _cpe_valor(partes[3]), _cpe_valor(partes[4])
        if not vendor or not product:
            return None
        return Cpe(part=(partes[2] or "a").lower(), vendor=vendor, product=product,
                   version=_cpe_valor(partes[5]) if len(partes) > 5 else None)
    if t.lower().startswith("cpe:/"):
        partes = t[5:].split(":")
        if len(partes) < 3:
            return None
        return Cpe(part=partes[0].lower() or "a", vendor=partes[1].lower(), product=partes[2].lower(),
                   version=partes[3].lower() if len(partes) > 3 and partes[3] else None)
    return None


def construir_cpe(vendor: Optional[str], product: Optional[str], version: Optional[str] = None,
                  part: str = "a") -> Optional[str]:
    if not vendor or not product:
        return None
    def esc(x):
        return re.sub(r"([^A-Za-z0-9_.\-~])", r"\\\1", x.lower().replace(" ", "_"))
    v = esc(version) if version else "*"
    return f"cpe:2.3:{part}:{esc(vendor)}:{esc(product)}:{v}:*:*:*:*:*:*:*"


# ── Nombres y productos conocidos ────────────────────────────────────────────

def normalizar_texto(nombre: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]+", "", (nombre or "").lower())


#: Productos base que llegan con nombres distintos. clave → (nombre, categoría,
#: cpe_vendor, cpe_product, tipo purl, espacio purl, nombre purl, alias).
CONOCIDOS: dict[str, dict] = {
    "php": dict(name="PHP", category="language", cpe=("php", "php"), purl=("generic", None, "php"),
                aliases=("php", "phpfpm", "php-fpm", "php-cli", "phpcli", "php8", "php7")),
    "nginx": dict(name="nginx", category="web_server", cpe=("f5", "nginx"), purl=("generic", None, "nginx"),
                  aliases=("nginx", "nginxplus", "openresty")),
    "apache": dict(name="Apache HTTP Server", category="web_server", cpe=("apache", "http_server"),
                   purl=("generic", None, "httpd"), aliases=("apache", "apache2", "httpd", "apachehttpserver",
                                                              "apachehttpd")),
    "tomcat": dict(name="Apache Tomcat", category="app_server", cpe=("apache", "tomcat"),
                   purl=("generic", None, "tomcat"), aliases=("tomcat", "apachetomcat", "tomcat9", "tomcat10")),
    "iis": dict(name="Microsoft IIS", category="web_server", cpe=("microsoft", "internet_information_services"),
                purl=("generic", None, "iis"), aliases=("iis", "microsoftiis", "internetinformationservices")),
    "mysql": dict(name="MySQL", category="database", cpe=("oracle", "mysql"), purl=("generic", None, "mysql"),
                  aliases=("mysql", "mysqld", "mysqlserver")),
    "mariadb": dict(name="MariaDB", category="database", cpe=("mariadb", "mariadb"),
                    purl=("generic", None, "mariadb"), aliases=("mariadb", "mariadbserver")),
    "postgresql": dict(name="PostgreSQL", category="database", cpe=("postgresql", "postgresql"),
                       purl=("generic", None, "postgresql"), aliases=("postgresql", "postgres", "psql", "pgsql")),
    "mssql": dict(name="Microsoft SQL Server", category="database", cpe=("microsoft", "sql_server"),
                  purl=("generic", None, "mssql"), aliases=("mssql", "sqlserver", "microsoftsqlserver")),
    "oracle_db": dict(name="Oracle Database", category="database", cpe=("oracle", "database_server"),
                      purl=("generic", None, "oracle-database"), aliases=("oracle", "oracledatabase", "oracledb")),
    "mongodb": dict(name="MongoDB", category="database", cpe=("mongodb", "mongodb"),
                    purl=("generic", None, "mongodb"), aliases=("mongodb", "mongod")),
    "redis": dict(name="Redis", category="database", cpe=("redis", "redis"), purl=("generic", None, "redis"),
                  aliases=("redis", "redisserver")),
    "openssl": dict(name="OpenSSL", category="library", cpe=("openssl", "openssl"),
                    purl=("generic", None, "openssl"), aliases=("openssl", "libssl")),
    "nodejs": dict(name="Node.js", category="runtime", cpe=("nodejs", "node.js"), purl=("generic", None, "node"),
                   aliases=("node", "nodejs")),
    "python": dict(name="Python", category="language", cpe=("python", "python"), purl=("generic", None, "python"),
                   aliases=("python", "python3", "cpython")),
    "java": dict(name="Java (OpenJDK)", category="runtime", cpe=("oracle", "openjdk"),
                 purl=("generic", None, "openjdk"), aliases=("java", "openjdk", "jdk", "jre", "temurin")),
    "dotnet": dict(name=".NET", category="runtime", cpe=("microsoft", ".net"), purl=("generic", None, "dotnet"),
                   aliases=("dotnet", "net", "netcore", "aspnetcore")),
    "openssh": dict(name="OpenSSH", category="tool", cpe=("openbsd", "openssh"), purl=("generic", None, "openssh"),
                    aliases=("openssh", "sshd")),
    "haproxy": dict(name="HAProxy", category="middleware", cpe=("haproxy", "haproxy"),
                    purl=("generic", None, "haproxy"), aliases=("haproxy",)),
    "rabbitmq": dict(name="RabbitMQ", category="middleware", cpe=("vmware", "rabbitmq"),
                     purl=("generic", None, "rabbitmq"), aliases=("rabbitmq", "rabbitmqserver")),
    "elasticsearch": dict(name="Elasticsearch", category="database", cpe=("elastic", "elasticsearch"),
                          purl=("generic", None, "elasticsearch"), aliases=("elasticsearch",)),
    "docker": dict(name="Docker Engine", category="tool", cpe=("docker", "docker"),
                   purl=("generic", None, "docker"), aliases=("docker", "dockerengine", "dockerd")),
    "kubernetes": dict(name="Kubernetes", category="middleware", cpe=("kubernetes", "kubernetes"),
                       purl=("generic", None, "kubernetes"), aliases=("kubernetes", "k8s", "kubelet")),
    "wordpress": dict(name="WordPress", category="application", cpe=("wordpress", "wordpress"),
                      purl=("generic", None, "wordpress"), aliases=("wordpress",)),
}

_ALIAS: dict[str, str] = {a: k for k, d in CONOCIDOS.items() for a in d["aliases"]}


def conocido(nombre: Optional[str]) -> Optional[str]:
    """Clave de `CONOCIDOS` para un nombre (o None)."""
    return _ALIAS.get(normalizar_texto(nombre))


def clave_de_producto(nombre: Optional[str] = None, purl: Optional[str | Purl] = None,
                      purl_type: Optional[str] = None, purl_namespace: Optional[str] = None,
                      purl_name: Optional[str] = None, cpe_vendor: Optional[str] = None,
                      cpe_product: Optional[str] = None) -> str:
    """La clave de conciliación de un producto (ver la cabecera)."""
    p = purl if isinstance(purl, Purl) else parsear_purl(purl) if purl else None
    if p is None and purl_name:
        p = Purl(type=purl_type or "generic", namespace=purl_namespace, name=purl_name)
    if p is not None and not (p.type == "generic" and conocido(p.name)):
        return "purl:" + p.clave()
    if cpe_vendor and cpe_product:
        return f"cpe:{cpe_vendor.lower()}:{cpe_product.lower()}"
    base = conocido(nombre) or conocido(p.name if p else None)
    if base:
        d = CONOCIDOS[base]
        return f"cpe:{d['cpe'][0]}:{d['cpe'][1]}"
    return "name:" + normalizar_texto(nombre or (p.name if p else ""))


#: CPE con los que NVD ha publicado el mismo producto a lo largo del tiempo.
CPE_ALTERNATIVOS: dict[str, tuple[tuple[str, str], ...]] = {
    "nginx": (("nginx", "nginx"),),
    "mysql": (("mysql", "mysql"),),
    "java": (("oracle", "jdk"), ("oracle", "jre"), ("eclipse", "temurin")),
    "dotnet": (("microsoft", ".net_core"), ("microsoft", "asp.net_core")),
    "redis": (("redislabs", "redis"),),
    "rabbitmq": (("pivotal_software", "rabbitmq"),),
    "kubernetes": (("linuxfoundation", "kubernetes"),),
}


def cpes_de(nombre: Optional[str], cpe_vendor: Optional[str], cpe_product: Optional[str]) -> list[tuple[str, str]]:
    """El CPE del producto y los alternativos conocidos."""
    salida = [(cpe_vendor, cpe_product)] if cpe_vendor and cpe_product else []
    clave = conocido(nombre)
    if clave:
        base = CONOCIDOS[clave]["cpe"]
        for c in (base, *CPE_ALTERNATIVOS.get(clave, ())):
            if c not in salida:
                salida.append(c)
    return salida


def datos_de_conocido(nombre: Optional[str]) -> Optional[dict]:
    """Nombre, categoría, CPE y purl del producto base al que se refiere `nombre`."""
    clave = conocido(nombre)
    if not clave:
        return None
    d = CONOCIDOS[clave]
    return {"name": d["name"], "category": d["category"], "cpe_vendor": d["cpe"][0], "cpe_product": d["cpe"][1],
            "purl_type": d["purl"][0], "purl_namespace": d["purl"][1], "purl_name": d["purl"][2]}
