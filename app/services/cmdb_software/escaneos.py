"""Conectores de escaneo reales: SSH (Linux), WinRM (Windows) y API de EDR/RMM.

Cada **conexión de escaneo** se guarda como un proveedor de descubrimiento de
la CMDB (`cmdb_discovery_providers`, tipos ``sw_ssh``, ``sw_winrm`` y
``sw_api``): así hereda, sin tablas nuevas,

- la configuración **cifrada** por empresa (`cifrar_config` / `load_config`;
  nunca se devuelve un secreto: `config_sin_secretos`),
- la **programación** (`scan_interval_minutes`, `next_run_at`; la pasa el
  trabajo `cmdb_discovery_run` cada 15 min por `run_discovery_for_provider`,
  que para estos tipos llama a `ejecutar`),
- el **historial de ejecuciones** (`cmdb_discovery_jobs`).

Se configuran en *Configuración → Software y vulnerabilidades → Conexiones de
escaneo* (`software.config`) y se lanzan bajo demanda desde la CMDB
(`software.gestionar`). Cada ejecución deja auditoría (`sw_scan`) con lo
encontrado por máquina, sin credenciales.

Qué se recoge:

- **SSH (Linux)**: sistema (``/etc/os-release``), paquetes (dpkg, rpm o apk;
  por defecto solo librerías y herramientas de seguridad relevantes, o todos
  con ``all_packages``), puertos a la escucha y su proceso (``ss``/``netstat``),
  versiones de nginx, Apache, PHP, Java, Node.js, Python, MySQL/MariaDB,
  PostgreSQL, Redis, OpenSSL, OpenSSH, HAProxy y Docker, y (``read_configs``)
  su configuración (``nginx -T``, ``apache2.conf``/``httpd.conf``,
  ``php.ini``), que se parsea y se enmascara con `configuracion`. Con
  ``sudo`` usa ``sudo -n`` (sin contraseña interactiva). La clave del
  servidor se verifica contra ``known_hosts``; sin él solo se acepta una
  clave desconocida si se marca ``accept_unknown_host_keys``.
- **WinRM (Windows)**: sistema, programas instalados (registro Uninstall, 64 y
  32 bits), servicios, IIS (versión, sitios, enlaces y puertos) y puertos a
  la escucha.
- **API (EDR/RMM)**: GET a una URL con token; la respuesta es el formato del
  inventario (`[{host, instances}]`) o se mapea con rutas de campos
  configurables (lista de equipos, nombre, IP, lista de software, nombre,
  versión, fabricante, ruta) y paginación por ``next``.

Las librerías de red (`paramiko`, `pywinrm`) se importan al usarlas; sin
ellas el escaneo falla con un código claro. Los tests sustituyen
`EJECUTORES` por ejecutores simulados.
"""
from __future__ import annotations

import io
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import ErrorConCodigo, error
from app.models.cmdb import CMDBDiscoveryJob, CMDBDiscoveryProvider
from app.services.audit import audit_log

logger = logging.getLogger(__name__)

#: Rev. 194: conexiones de terceros (Trend Vision One, Defender VM, Qualys, Tenable, Rapid7) y
#: SIEM genérico (intentos de explotación); su lógica está en `riesgo/terceros.py`.
TIPOS_TERCEROS = ("sw_vm_trendmicro", "sw_vm_defender", "sw_vm_qualys", "sw_vm_tenable", "sw_vm_rapid7", "sw_siem")
TIPOS = ("sw_ssh", "sw_winrm", "sw_api") + TIPOS_TERCEROS
#: Claves de configuración por tipo (las secretas, marcadas): las lee la pantalla.
CAMPOS = {
    "sw_ssh": ("hosts", "port", "username", "password*", "private_key*", "passphrase*", "known_hosts",
               "accept_unknown_host_keys", "sudo", "read_configs", "all_packages", "environment", "exposure",
               "create_cis", "timeout"),
    "sw_winrm": ("hosts", "port", "username", "password*", "transport", "use_ssl", "verify_ssl", "environment",
                 "exposure", "create_cis", "include_services", "timeout"),
    "sw_api": ("url", "token*", "auth_header", "list_path", "host_field", "ip_field", "software_field",
               "name_field", "version_field", "vendor_field", "path_field", "next_path", "max_pages",
               "environment", "create_cis", "timeout"),
}
from app.services.cmdb_software.riesgo.terceros import CAMPOS as _CAMPOS_TERCEROS  # noqa: E402
CAMPOS.update(_CAMPOS_TERCEROS)
SECRETOS ={k.rstrip("*") for campos in CAMPOS.values() for k in campos if k.endswith("*")}

Ejecutor = Callable[[str], tuple[int, str]]


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


# ── Utilidades de texto ──────────────────────────────────────────────────────

def _primero(patron: str, texto: str) -> Optional[str]:
    m = re.search(patron, texto or "")
    return m.group(1) if m else None


# `_ruta` vive en `riesgo/terceros.py` (`ruta_json`), que la usa con el SIEM: así
# `terceros` no importa `escaneos` de vuelta (ciclo escondido, 23-11-2026).
from app.services.cmdb_software.riesgo.terceros import ruta_json as _ruta  # noqa: E402
# ── Linux por SSH ────────────────────────────────────────────────────────────

#: Sondas de versión: clave conocida → (orden, regex de versión, categoría, (orden de config, formato, ruta)).
SONDAS_LINUX: dict[str, tuple] = {
    "nginx": ("nginx -v 2>&1", r"nginx/([\w.\-]+)", "web_server", ("nginx -T 2>/dev/null", "nginx", "/etc/nginx/nginx.conf")),
    "apache": ("(apache2 -v || httpd -v) 2>&1", r"Apache/([\d.]+)", "web_server",
               ("cat /etc/apache2/apache2.conf 2>/dev/null || cat /etc/httpd/conf/httpd.conf 2>/dev/null", "apache",
                "/etc/apache2/apache2.conf")),
    "php": ("php -v 2>&1", r"PHP ([\d.]+)", "language",
            ("cat \"$(php -r 'echo php_ini_loaded_file();' 2>/dev/null)\" 2>/dev/null", "php_ini", None)),
    "java": ("java -version 2>&1", r'version "([\d._]+)', "runtime", None),
    "nodejs": ("node -v 2>&1", r"v([\d.]+)", "runtime", None),
    "python": ("python3 --version 2>&1", r"Python ([\d.]+)", "language", None),
    "mysql": ("(mysqld --version || mysql --version) 2>&1", r"Ver ([\d.]+)", "database",
              ("cat /etc/mysql/my.cnf 2>/dev/null || cat /etc/my.cnf 2>/dev/null", "ini", "/etc/mysql/my.cnf")),
    "postgresql": ("(postgres --version || psql --version) 2>&1", r"\)\s*([\d.]+)", "database", None),
    "redis": ("redis-server --version 2>&1", r"v=([\d.]+)", "database", None),
    "openssl": ("openssl version 2>&1", r"OpenSSL ([\d.]+[a-z]?)", "library", None),
    "openssh": ("ssh -V 2>&1", r"OpenSSH_([\w.]+)", "tool", None),
    "haproxy": ("haproxy -v 2>&1", r"version ([\d.]+)", "middleware", None),
    "docker": ("docker --version 2>&1", r"version ([\d.]+)", "tool", None),
}
#: Proceso a la escucha → clave de sonda.
PROCESOS = {"nginx": "nginx", "apache2": "apache", "httpd": "apache", "php-fpm": "php", "java": "java",
            "node": "nodejs", "python": "python", "python3": "python", "mysqld": "mysql", "mariadbd": "mysql",
            "postgres": "postgresql", "redis-server": "redis", "sshd": "openssh", "haproxy": "haproxy",
            "dockerd": "docker"}
#: Paquetes que se guardan siempre (librerías y herramientas con historial de vulnerabilidades).
PAQUETES_RELEVANTES = ("openssl", "libssl", "glibc", "libc6", "libc-bin", "sudo", "bash", "curl", "libcurl", "polkit",
                       "policykit", "systemd", "xz-utils", "xz", "liblzma", "zlib", "git", "linux-image", "kernel",
                       "containerd", "log4j", "openssh-client", "libxml2", "expat", "libexpat", "gnutls", "nss",
                       "krb5", "libkrb5", "ca-certificates", "tzdata", "busybox", "musl", "apk-tools", "rpm",
                       "dpkg", "apt", "yum", "dnf")
#: ID de os-release → (nombre, fabricante CPE, producto CPE).
SISTEMAS = {"ubuntu": ("Ubuntu", "canonical", "ubuntu_linux"), "debian": ("Debian", "debian", "debian_linux"),
            "rhel": ("Red Hat Enterprise Linux", "redhat", "enterprise_linux"), "centos": ("CentOS", "centos", "centos"),
            "rocky": ("Rocky Linux", "rockylinux", "rocky_linux"), "almalinux": ("AlmaLinux", "almalinux", "almalinux"),
            "alpine": ("Alpine Linux", "alpinelinux", "alpine_linux"), "amzn": ("Amazon Linux", "amazon", "linux"),
            "sles": ("SUSE Linux Enterprise Server", "suse", "linux_enterprise_server"),
            "ol": ("Oracle Linux", "oracle", "linux"), "fedora": ("Fedora", "fedoraproject", "fedora")}
_PURL_DE_PAQUETE = {"dpkg": "deb", "rpm": "rpm", "apk": "apk"}


def _os_release(texto: str) -> dict:
    d = {}
    for linea in (texto or "").splitlines():
        if "=" in linea:
            k, v = linea.split("=", 1)
            d[k.strip()] = v.strip().strip('"')
    return d


def _paquetes(ejecutar: Ejecutor) -> tuple[Optional[str], list[tuple[str, str]]]:
    for gestor, orden in (("dpkg", "command -v dpkg-query >/dev/null 2>&1 && dpkg-query -W -f='${Package}\\t${Version}\\n'"),
                          ("rpm", "command -v rpm >/dev/null 2>&1 && rpm -qa --qf '%{NAME}\\t%{VERSION}-%{RELEASE}\\n'"),
                          ("apk", "command -v apk >/dev/null 2>&1 && apk info -v")):
        rc, salida = ejecutar(orden)
        if rc != 0 or not salida.strip():
            continue
        lista = []
        for linea in salida.splitlines():
            linea = linea.strip()
            if not linea:
                continue
            if gestor == "apk":
                m = re.match(r"^(.+?)-(\d[^-]*-r\d+)$", linea)
                if m:
                    lista.append((m.group(1), m.group(2)))
            elif "\t" in linea:
                n, v = linea.split("\t", 1)
                lista.append((n.strip(), v.strip()))
        return gestor, lista
    return None, []


def _escuchando(ejecutar: Ejecutor) -> dict[str, list[int]]:
    """Proceso → puertos a la escucha (``ss -ltnpH``, o ``netstat -ltnp``)."""
    rc, salida = ejecutar("ss -ltnpH 2>/dev/null || netstat -ltnp 2>/dev/null")
    puertos: dict[str, set] = {}
    for linea in (salida or "").splitlines():
        campos = linea.split()
        # ss -ltnpH: estado, recv-q, send-q, LOCAL, remota, proceso; netstat -ltnp: proto, recv-q, send-q, LOCAL...
        if len(campos) < 5 or ":" not in campos[3]:
            continue
        puerto = campos[3].rsplit(":", 1)[1]
        if not puerto.isdigit():
            continue
        procesos = re.findall(r'"([^"]+)",pid=', linea) or re.findall(r"\d+/([\w.\-]+)", linea)
        for p in procesos:
            puertos.setdefault(p, set()).add(int(puerto))
    return {k: sorted(v) for k, v in puertos.items()}


def recoger_linux(ejecutar: Ejecutor, opciones: Optional[dict] = None) -> dict:
    """Inventario de un Linux con el formato de `importacion.aplicar_inventario` (+ ``host``)."""
    from app.services.cmdb_software.configuracion import interpretar
    opciones = opciones or {}
    sudo = "sudo -n " if opciones.get("sudo") else ""
    _, os_txt = ejecutar("cat /etc/os-release 2>/dev/null")
    osr = _os_release(os_txt)
    _, nombre_host = ejecutar("hostname -f 2>/dev/null || hostname")
    _, ips = ejecutar("hostname -I 2>/dev/null")
    _, kernel = ejecutar("uname -r 2>/dev/null")
    host = {"hostname": (nombre_host or "").strip().splitlines()[0] if (nombre_host or "").strip() else None,
            "ip_address": (ips or "").split()[0] if (ips or "").split() else None, "os_type": "linux",
            "os_version": osr.get("PRETTY_NAME"), "kernel_version": (kernel or "").strip() or None}
    instancias: list[dict] = []
    sistema = osr.get("ID", "").lower()
    if sistema:
        nombre, cv, cp = SISTEMAS.get(sistema, (osr.get("NAME") or sistema, None, None))
        instancias.append({"name": nombre, "version": osr.get("VERSION_ID"), "category": "os", "origin": "open_source",
                           "cpe": f"cpe:2.3:o:{cv}:{cp}:{osr.get('VERSION_ID') or '*'}:*:*:*:*:*:*:*" if cv else None,
                           "instance_name": f"{nombre} {osr.get('VERSION_ID') or ''}".strip(),
                           "config": {"kernel": host["kernel_version"], "pretty_name": osr.get("PRETTY_NAME")}})
    escuchando = _escuchando(ejecutar)
    puertos_por_sonda: dict[str, list[int]] = {}
    for proceso, puertos in escuchando.items():
        clave = PROCESOS.get(proceso) or next((v for k, v in PROCESOS.items() if proceso.startswith(k)), None)
        if clave:
            puertos_por_sonda.setdefault(clave, [])
            puertos_por_sonda[clave] = sorted(set(puertos_por_sonda[clave]) | set(puertos))
    for clave, (orden, patron, categoria, conf) in SONDAS_LINUX.items():
        rc, salida = ejecutar(orden)
        version = _primero(patron, salida)
        if not version:
            continue
        nombre = clave
        if clave == "mysql" and "mariadb" in (salida or "").lower():
            nombre = "mariadb"
            version = _primero(r"Distrib ([\d.]+)", salida) or _primero(r"([\d.]+)-MariaDB", salida) or version
        d = {"name": nombre, "version": version, "category": categoria,
             "ports": puertos_por_sonda.get(clave, []), "instance_name": nombre}
        if conf and opciones.get("read_configs", True):
            orden_conf, formato, ruta = conf
            rc2, texto = ejecutar(sudo + orden_conf if sudo and not orden_conf.startswith("cat \"$(") else orden_conf)
            if rc2 == 0 and (texto or "").strip():
                config, fmt = interpretar(texto=texto, formato=formato, producto=nombre, ruta=ruta)
                d.update(config=config, config_format=fmt, config_path=ruta)
        instancias.append(d)
    gestor, paquetes = _paquetes(ejecutar)
    if gestor:
        tipo = _PURL_DE_PAQUETE[gestor]
        todos = bool(opciones.get("all_packages"))
        from app.services.cmdb_software.identificadores import construir_purl
        for nombre, version in paquetes:
            if not todos and not nombre.lower().startswith(PAQUETES_RELEVANTES):
                continue
            instancias.append({"name": nombre, "version": version, "category": "library", "origin": "open_source",
                               "purl": construir_purl(tipo, sistema or None, nombre, version),
                               "instance_name": nombre, "key": f"pkg:{tipo}:{nombre}"})
    return {"host": host, "instances": instancias, "complete": True}


# ── Windows por WinRM ────────────────────────────────────────────────────────

SCRIPT_WINDOWS = r"""
$ErrorActionPreference='SilentlyContinue'
$os = Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version
$ips = @(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -ne '127.0.0.1' } | ForEach-Object { $_.IPAddress })
$rutas = 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
$apps = @(Get-ItemProperty $rutas | Where-Object { $_.DisplayName -and -not $_.SystemComponent } | Select-Object DisplayName,DisplayVersion,Publisher,InstallLocation)
$svcs = @(Get-CimInstance Win32_Service | Select-Object Name,DisplayName,State,StartMode)
$iis = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\InetStp' | Select-Object VersionString,MajorVersion,MinorVersion,PathWWWRoot
$sites = @()
if (Get-Module -ListAvailable WebAdministration) { Import-Module WebAdministration; $sites = @(Get-Website | ForEach-Object { [pscustomobject]@{name=$_.name; state=$_.state; path=$_.physicalPath; bindings=@($_.bindings.Collection | ForEach-Object { $_.protocol + ' ' + $_.bindingInformation })} }) }
$procs = @{}; Get-Process | ForEach-Object { $procs[$_.Id] = $_.ProcessName }
$ports = @(Get-NetTCPConnection -State Listen | ForEach-Object { [pscustomobject]@{port=$_.LocalPort; process=$procs[[int]$_.OwningProcess]} })
[pscustomobject]@{hostname=$env:COMPUTERNAME; fqdn=([System.Net.Dns]::GetHostEntry('').HostName); os=$os; ips=$ips; apps=$apps; services=$svcs; iis=$iis; sites=$sites; ports=$ports} | ConvertTo-Json -Depth 5 -Compress
"""


def _lista(v) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def interpretar_windows(datos: dict, opciones: Optional[dict] = None) -> dict:
    opciones = opciones or {}
    os_ = datos.get("os") or {}
    host = {"hostname": datos.get("fqdn") or datos.get("hostname"), "ip_address": (_lista(datos.get("ips")) or [None])[0],
            "os_type": "windows", "os_version": os_.get("Caption")}
    puertos_por_proceso: dict[str, set] = {}
    for p in _lista(datos.get("ports")):
        if p and p.get("process"):
            puertos_por_proceso.setdefault(str(p["process"]).lower(), set()).add(int(p.get("port") or 0))
    instancias = []
    if os_.get("Caption"):
        servicios = [s.get("Name") for s in _lista(datos.get("services")) if s and s.get("State") == "Running"]
        instancias.append({"name": re.sub(r"^Microsoft\s+", "", os_["Caption"]).strip(), "version": os_.get("Version"),
                           "category": "os", "origin": "purchased", "vendor": "Microsoft",
                           "instance_name": os_["Caption"],
                           "config": {"running_services": sorted(servicios)[:300]}
                           if opciones.get("include_services", True) else None})
    for a in _lista(datos.get("apps")):
        if not a or not a.get("DisplayName"):
            continue
        nombre = str(a["DisplayName"]).strip()
        proceso = re.sub(r"[^a-z0-9]", "", nombre.lower())[:12]
        puertos = sorted({p for k, v in puertos_por_proceso.items() for p in v if k and k in proceso})
        instancias.append({"name": nombre, "version": a.get("DisplayVersion"), "category": "application",
                           "origin": "purchased", "vendor": a.get("Publisher"),
                           "install_path": a.get("InstallLocation") or None, "instance_name": nombre,
                           "ports": puertos})
    iis = datos.get("iis") or {}
    if iis.get("VersionString") or iis.get("MajorVersion"):
        version = _primero(r"([\d.]+)", str(iis.get("VersionString") or "")) or \
            f"{iis.get('MajorVersion')}.{iis.get('MinorVersion') or 0}"
        sitios = _lista(datos.get("sites"))
        puertos = sorted({int(m) for s in sitios for b in _lista(s.get("bindings"))
                          for m in re.findall(r":(\d+):", str(b))})
        instancias.append({"name": "Microsoft IIS", "version": version, "category": "web_server", "origin": "purchased",
                           "vendor": "Microsoft", "instance_name": "IIS", "ports": puertos,
                           "config_path": r"C:\Windows\System32\inetsrv\config\applicationHost.config",
                           "config": {"sites": [{"name": s.get("name"), "state": s.get("state"),
                                                 "path": s.get("path"), "bindings": _lista(s.get("bindings"))}
                                                for s in sitios], "ports": puertos,
                                      "tls": any("https" in str(b) for s in sitios for b in _lista(s.get("bindings")))},
                           "config_format": "json"})
    return {"host": host, "instances": instancias, "complete": True}


def recoger_windows(ejecutar: Ejecutor, opciones: Optional[dict] = None) -> dict:
    rc, salida = ejecutar(SCRIPT_WINDOWS)
    if rc != 0 or not (salida or "").strip():
        raise ErrorConCodigo("sw_escaneo_fallido", host="?", detalle=f"rc={rc}")
    # M72: PowerShell 5 escribe UTF-8 con BOM; `json.loads` lo rechazaba.
    return interpretar_windows(json.loads(salida.lstrip("\ufeff")), opciones)


# ── API de EDR/RMM ───────────────────────────────────────────────────────────

def _http_get(url: str, headers: Optional[dict] = None, timeout: float = 30):
    # SSRF: la URL es de la conexión (empresa); `peticion` valida URL, redirecciones e IP conectada.
    # Con credenciales (cabeceras que no sean Accept) no se siguen redirecciones.
    from app.core.outbound_url import peticion
    con_credenciales = any(k.lower() != "accept" for k in (headers or {}))
    r = peticion("GET", url, field="url", headers=headers, timeout=timeout, follow_redirects=not con_credenciales)
    r.raise_for_status()
    return r.json()


def recoger_api(conf: dict) -> list[dict]:
    """Equipos del EDR/RMM en el formato del inventario."""
    cabeceras = {"Accept": "application/json"}
    if conf.get("token"):
        nombre = conf.get("auth_header") or "Authorization"
        cabeceras[nombre] = conf["token"] if nombre.lower() != "authorization" or " " in conf["token"] \
            else f"Bearer {conf['token']}"
    url = conf.get("url")
    if not url:
        raise ErrorConCodigo("sw_conexion_incompleta", campo="url")
    equipos, paginas = [], 0
    while url and paginas < int(conf.get("max_pages") or 10):
        datos = _http_get(url, cabeceras, float(conf.get("timeout") or 30))
        paginas += 1
        lista = _ruta(datos, conf.get("list_path"))
        equipos += lista if isinstance(lista, list) else []
        siguiente = _ruta(datos, conf.get("next_path")) if conf.get("next_path") else None
        url = None
        if isinstance(siguiente, str) and siguiente.startswith(("http://", "https://")):
            from app.core.outbound_url import mismo_origen
            if mismo_origen(conf.get("url"), siguiente):
                url = siguiente
            else:  # el `next` de la respuesta no decide a qué host va el token
                logger.warning("paginación de la API de EDR/RMM: la página siguiente es de otro origen; se detiene")
    salida = []
    for e in equipos:
        if not isinstance(e, dict):
            continue
        if "instances" in e and not conf.get("software_field"):
            host = e.get("host") or e.get("ci") or {}
            salida.append({"host": host, "instances": e.get("instances") or [], "complete": e.get("complete", True)})
            continue
        host = {"hostname": _ruta(e, conf.get("host_field") or "hostname"), "ip_address": _ruta(e, conf.get("ip_field") or "ip")}
        programas = _ruta(e, conf.get("software_field") or "software") or []
        instancias = []
        for s in programas if isinstance(programas, list) else []:
            if not isinstance(s, dict):
                continue
            nombre = _ruta(s, conf.get("name_field") or "name")
            if not nombre:
                continue
            instancias.append({"name": str(nombre), "version": _ruta(s, conf.get("version_field") or "version"),
                               "vendor": _ruta(s, conf.get("vendor_field") or "vendor"),
                               "install_path": _ruta(s, conf.get("path_field") or "path"),
                               "category": "application", "origin": "purchased", "instance_name": str(nombre)})
        salida.append({"host": host, "instances": instancias, "complete": True})
    return salida


# ── Conexiones remotas (sustituibles en tests) ──────────────────────────────

def _ssh(host: str, conf: dict):
    try:
        import paramiko
    except ImportError:
        raise ErrorConCodigo("sw_dependencia_no_instalada", paquete="paramiko")
    cliente = paramiko.SSHClient()
    if conf.get("known_hosts"):
        for linea in str(conf["known_hosts"]).splitlines():
            partes = linea.split()
            if len(partes) >= 3:
                try:
                    import base64
                    clave = paramiko.PKey.from_type_string(partes[1], base64.b64decode(partes[2]))
                    for nombre in partes[0].split(","):
                        cliente.get_host_keys().add(nombre, partes[1], clave)
                except Exception:  # noqa: BLE001 - una línea mala no invalida las demás
                    logger.debug("_ssh: excepcion ignorada", exc_info=True)
                    continue
        cliente.set_missing_host_key_policy(paramiko.RejectPolicy())
    elif conf.get("accept_unknown_host_keys"):
        cliente.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    else:
        cliente.set_missing_host_key_policy(paramiko.RejectPolicy())
    pkey = None
    if conf.get("private_key"):
        for tipo in (paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.RSAKey):
            try:
                pkey = tipo.from_private_key(io.StringIO(conf["private_key"]), password=conf.get("passphrase") or None)
                break
            except Exception:  # noqa: BLE001 - se prueba el siguiente tipo de clave
                logger.warning("_ssh: excepcion ignorada", exc_info=True)
                continue
    nombre, _, puerto = host.partition(":")
    cliente.connect(nombre, port=int(puerto or conf.get("port") or 22), username=conf.get("username"),
                    password=conf.get("password") or None, pkey=pkey, timeout=float(conf.get("timeout") or 20),
                    allow_agent=False, look_for_keys=False)
    limite = float(conf.get("timeout") or 20)

    def ejecutar(orden: str) -> tuple[int, str]:
        _in, out, _err = cliente.exec_command(orden, timeout=limite)
        texto = out.read(2_000_000).decode("utf-8", errors="replace")
        return out.channel.recv_exit_status(), texto
    return ejecutar, cliente.close


def _winrm(host: str, conf: dict):
    try:
        import winrm
    except ImportError:
        raise ErrorConCodigo("sw_dependencia_no_instalada", paquete="pywinrm")
    ssl = conf.get("use_ssl", True)
    nombre, _, puerto = host.partition(":")
    sesion = winrm.Session(f"{'https' if ssl else 'http'}://{nombre}:{puerto or conf.get('port') or (5986 if ssl else 5985)}/wsman",
                           auth=(conf.get("username"), conf.get("password")), transport=conf.get("transport") or "ntlm",
                           server_cert_validation="validate" if conf.get("verify_ssl", True) else "ignore",
                           operation_timeout_sec=int(conf.get("timeout") or 30),
                           read_timeout_sec=int(conf.get("timeout") or 30) + 10)

    def ejecutar(script: str) -> tuple[int, str]:
        r = sesion.run_ps(script)
        return r.status_code, r.std_out.decode("utf-8", errors="replace")
    return ejecutar, (lambda: None)


#: tipo → función (host, conf) → (ejecutor, cerrar). Los tests los sustituyen.
EJECUTORES: dict[str, Callable] = {"sw_ssh": _ssh, "sw_winrm": _winrm}


def recoger(tipo: str, conf: dict, hosts: Optional[list[str]] = None) -> list[dict]:
    """Inventarios de todos los equipos de una conexión (los fallos van como ``{host, error}``)."""
    if tipo == "sw_api":
        return recoger_api(conf)
    configurados = [h.strip() for h in re.split(r"[\s,;]+", str(conf.get("hosts") or "")) if h.strip()]
    # A21: las credenciales guardadas SOLO se usan contra hosts que el admin configuró (si no, quien pudiera
    # lanzar un escaneo las enviaría a cualquier host: relé de credenciales). Comparación normalizada.
    # Decisión SSRF: como todo destino es un host configurado por el admin, NO se aplica `validar_host_saliente`
    # (los escaneos internos de la red de la empresa son legítimos y bloquearía IP privadas); el guardia solo
    # ocurre sobre lo que viene de la petición, y eso ya se rechaza aquí.
    permitidos = {h.lower() for h in configurados}
    if hosts:
        for h in hosts:
            if str(h or "").strip().lower() not in permitidos:
                raise ErrorConCodigo("cmdb_host_no_configurado", host=str(h)[:100])
        destinos = [str(h).strip() for h in hosts]
    else:
        destinos = configurados
    if not destinos:
        raise ErrorConCodigo("sw_conexion_incompleta", campo="hosts")
    salida = []
    for destino in destinos[:500]:
        cerrar = None
        try:
            ejecutar, cerrar = EJECUTORES[tipo](destino, conf)
            inv = recoger_linux(ejecutar, conf) if tipo == "sw_ssh" else recoger_windows(ejecutar, conf)
            inv["host"] = {**{"hostname": destino.partition(":")[0]}, **{k: v for k, v in inv["host"].items() if v}}
            inv["target"] = destino
            salida.append(inv)
        except Exception as e:  # noqa: BLE001 - un equipo caído no para el resto
            logger.debug("recoger: excepcion ignorada", exc_info=True)
            salida.append({"target": destino, "error": getattr(e, "code", None) or type(e).__name__,
                           "detail": str(e)[:300]})
        finally:
            if cerrar:
                try:
                    cerrar()
                except Exception:  # noqa: BLE001
                    logger.debug("recoger: excepcion ignorada", exc_info=True)
    return salida


# ── Conexiones guardadas ─────────────────────────────────────────────────────

def _q(db, org):
    q = db.query(CMDBDiscoveryProvider).filter(CMDBDiscoveryProvider.provider_type.in_(TIPOS))
    return q.filter(CMDBDiscoveryProvider.organization_id == org) if org else q


def ultimas_ejecuciones(db: Session, conexion_, limite: int) -> list:
    """Últimas ejecuciones de descubrimiento de una conexión de escaneo."""
    return (db.query(CMDBDiscoveryJob).filter(CMDBDiscoveryJob.provider_id == conexion_.id)
            .order_by(CMDBDiscoveryJob.started_at.desc()).limit(limite).all())


def conexion(db, org, id_) -> CMDBDiscoveryProvider:
    c = _q(db, org).filter(CMDBDiscoveryProvider.id == id_).first() if id_ else None
    if c is None:
        raise error(404, "sw_conexion_no_encontrada")
    return c


def serializar(c: CMDBDiscoveryProvider) -> dict:
    from app.services.cmdb.parser import load_config
    conf = load_config(c)
    return {"id": c.id, "name": c.name, "type": c.provider_type, "is_active": c.is_active,
            "scan_interval_minutes": c.scan_interval_minutes,
            "config": {k: v for k, v in conf.items() if k not in SECRETOS},
            "secrets_set": sorted(k for k in SECRETOS if conf.get(k)),
            "last_run_at": c.last_run_at.isoformat() if c.last_run_at else None, "last_run_status": c.last_run_status,
            "next_run_at": c.next_run_at.isoformat() if c.next_run_at else None}


def listar(db, org) -> list[dict]:
    return [serializar(c) for c in _q(db, org).order_by(CMDBDiscoveryProvider.name)]


def guardar(db: Session, org, datos: dict, usuario, c: Optional[CMDBDiscoveryProvider] = None) -> CMDBDiscoveryProvider:
    """Alta o cambio. Los secretos vacíos no cambian; ``'__borrar__'`` los quita. Audita sin secretos."""
    from app.services.cmdb.parser import cifrar_config, load_config
    tipo = datos.get("type") or (c.provider_type if c else None)
    if tipo not in TIPOS:
        raise error(422, "sw_tipo_de_conexion_no_valido", tipo=tipo)
    nombre = (datos.get("name") or (c.name if c else "") or "").strip()
    if len(nombre) < 2:
        raise error(422, "sw_nombre_obligatorio")
    actual = load_config(c) if c else {}
    nueva = dict(actual)
    permitidas = {k.rstrip("*") for k in CAMPOS[tipo]}
    cambiados = []
    for k, v in (datos.get("config") or {}).items():
        if k not in permitidas:
            continue
        if k in SECRETOS:
            if v in (None, ""):
                continue
            if v == "__borrar__":
                nueva.pop(k, None)
            else:
                nueva[k] = str(v)
            cambiados.append(k)
        else:
            nueva[k] = v
    intervalo = int(datos.get("scan_interval_minutes") or (c.scan_interval_minutes if c else 1440) or 1440)
    if not 15 <= intervalo <= 60 * 24 * 31:
        raise error(422, "sw_ajuste_fuera_de_rango", campo="scan_interval_minutes", minimo=15, maximo=60 * 24 * 31)
    antes = serializar(c) if c else None
    if c is None:
        c = CMDBDiscoveryProvider(organization_id=org, provider_type=tipo, created_by=getattr(usuario, "id", None),
                                  next_run_at=_ahora() + timedelta(minutes=intervalo))
        db.add(c)
    c.name = nombre[:100]
    c.config_json = cifrar_config(nueva)
    c.scan_interval_minutes = intervalo
    if "is_active" in datos:
        c.is_active = bool(datos["is_active"])
    db.flush()
    audit_log(db, usuario, "UPDATE" if antes else "CREATE", "sw_scan_connection", c.id, c.name, old_values=antes,
              new_values=serializar(c), metadata={"secrets_changed": cambiados})
    return c


def borrar(db: Session, c: CMDBDiscoveryProvider, usuario) -> None:
    audit_log(db, usuario, "DELETE", "sw_scan_connection", c.id, c.name, old_values=serializar(c))
    db.delete(c)
    db.flush()


def _unico_por_nombre_corto(db: Session, org, corto: str):
    from sqlalchemy import func, or_
    from app.models.service_desk.cmdb import ConfigurationItem
    from app.services.cmdb_software import catalogo as cat
    t = (corto or "").strip().lower()
    if not t:
        return None
    candidatos = cat._q(db, ConfigurationItem, org).filter(
        ConfigurationItem.is_active.is_(True),
        or_(func.lower(ConfigurationItem.name) == t, func.lower(ConfigurationItem.hostname) == t,
            func.lower(ConfigurationItem.hostname).like(t + ".%"))).limit(2).all()
    return candidatos[0] if len(candidatos) == 1 else None


def _ci_para(db: Session, org, host: dict, c: CMDBDiscoveryProvider, crear: bool):
    from app.services.cmdb.models import reconcile_cis
    from app.services.cmdb.parser import normalize_agent_payload
    from app.services.cmdb_software.importacion import buscar_ci
    for clave in ("hostname", "fqdn", "ip_address"):
        encontrado = buscar_ci(db, org, host.get(clave))
        if encontrado is None and clave == "hostname" and host.get(clave) and "." in host[clave]:
            # M72 (auditoría 22-11-2026): por nombre corto solo si es INEQUÍVOCO
            # (antes `web01.prod` casaba con el CI `web01` de desarrollo).
            encontrado = _unico_por_nombre_corto(db, org, host[clave].split(".")[0])
        if encontrado is not None:
            return encontrado
    if not crear or not (host.get("hostname") or host.get("ip_address")):
        return None
    ci_dict = normalize_agent_payload(host, f"{c.id}:{host.get('hostname') or host.get('ip_address')}")
    reconcile_cis(db, [ci_dict], c.provider_type, provider=c, organization_id=org, retirar_ausentes=False)
    db.flush()
    return buscar_ci(db, org, host.get("hostname") or host.get("ip_address"))


def ejecutar(db: Session, c: CMDBDiscoveryProvider, usuario=None, hosts: Optional[list[str]] = None,
             job: Optional[CMDBDiscoveryJob] = None, disparo: str = "manual") -> dict:
    """Escanea, aplica el inventario en cada CI y reevalúa. No confirma (salvo el job, que ya viene creado)."""
    from app.services.cmdb.parser import load_config
    from app.services.cmdb_software.correlacion import reevaluar
    from app.services.cmdb_software.importacion import aplicar_inventario
    if c.provider_type in TIPOS_TERCEROS:
        from app.services.cmdb_software.riesgo.terceros import ejecutar_conexion
        r = ejecutar_conexion(db, c, usuario, disparo)
        audit_log(db, usuario, "SCAN", "sw_scan", c.id, c.name,
                  metadata={"type": c.provider_type, "hosts": r.get("hosts"), "errors": len(r.get("errors") or []),
                            "findings_new": r.get("findings_new"), "trigger": disparo})
        return r
    org = c.organization_id
    conf = load_config(c)
    resumen = {"hosts": 0, "errors": [], "cis_created": 0, "created": 0, "updated": 0, "stopped": 0, "components": 0,
               "without_ci": []}
    for inv in recoger(c.provider_type, conf, hosts):
        if inv.get("error"):
            resumen["errors"].append({"target": inv.get("target"), "error": inv["error"]})
            continue
        host = inv.get("host") or {}
        from app.services.cmdb_software.importacion import buscar_ci
        buscar_existente = buscar_ci(db, org, host.get("hostname")) or buscar_ci(db, org, host.get("ip_address"))
        ci = _ci_para(db, org, host, c, conf.get("create_cis", True))
        if ci is None:
            resumen["without_ci"].append(host.get("hostname") or inv.get("target"))
            continue
        resumen["cis_created"] += int(buscar_existente is None)
        for d in inv.get("instances") or []:
            for k in ("environment", "exposure"):
                if conf.get(k) and not d.get(k):
                    d[k] = conf[k]
        r = aplicar_inventario(db, org, ci.id, inv, origen="scan", usuario=usuario)
        resumen["hosts"] += 1
        for k in ("created", "updated", "stopped", "components"):
            resumen[k] += r.get(k, 0)
    res = reevaluar(db, org, usuario)
    resumen["findings_new"] = res["findings_new"]
    resumen["findings_resolved"] = res["findings_resolved"]
    audit_log(db, usuario, "SCAN", "sw_scan", c.id, c.name,
              metadata={k: v for k, v in resumen.items() if k != "errors"} | {"errors": len(resumen["errors"]),
                                                                            "trigger": disparo})
    return resumen


def ejecutar_con_registro(db: Session, c: CMDBDiscoveryProvider, usuario=None, hosts: Optional[list[str]] = None) -> dict:
    """Bajo demanda: deja su ejecución en `cmdb_discovery_jobs` como el resto del descubrimiento."""
    job = CMDBDiscoveryJob(organization_id=c.organization_id, provider_id=c.id, status="running", started_at=_ahora(),
                           triggered_by="manual")
    db.add(job)
    db.flush()
    try:
        with db.begin_nested():
            r = ejecutar(db, c, usuario, hosts, job, "manual")
        job.status = "partial" if r["errors"] else "ok"
        job.cis_created, job.cis_updated = r["cis_created"], r["hosts"]
        job.summary_json = json.dumps(r, default=str)[:20000]
    except Exception as e:  # noqa: BLE001 - el error queda en la ejecución
        logger.debug("ejecutar_con_registro: excepcion ignorada", exc_info=True)
        job.status, job.error_message = "error", f"{getattr(e, 'code', None) or type(e).__name__}: {e}"[:2000]
        r = {"error": job.error_message}
    job.finished_at = _ahora()
    c.last_run_at, c.last_run_status = job.finished_at, job.status
    c.next_run_at = job.finished_at + timedelta(minutes=max(15, c.scan_interval_minutes or 1440))
    db.flush()
    return {"job_id": job.id, "status": job.status, **r}


def para_el_descubrimiento(db: Session, c: CMDBDiscoveryProvider) -> dict:
    """Lo que llama `run_discovery_for_provider` (programado): devuelve las cifras del job."""
    r = ejecutar(db, c, None, None, None, "scheduler")
    return {"created": r["cis_created"], "updated": r["hosts"], "deactivated": 0, "software": r}


def probar(db: Session, c: CMDBDiscoveryProvider) -> dict:
    """Prueba de conexión con el primer equipo (o la primera página de la API), sin guardar nada."""
    from app.services.cmdb.parser import load_config
    if c.provider_type in TIPOS_TERCEROS:
        from app.services.cmdb_software.riesgo.terceros import probar_conexion
        return probar_conexion(c)
    conf = load_config(c)
    try:
        if c.provider_type == "sw_api":
            n = len(recoger_api({**conf, "max_pages": 1}))
            return {"ok": True, "devices": n}
        primero = [h.strip() for h in re.split(r"[\s,;]+", str(conf.get("hosts") or "")) if h.strip()][:1]
        if not primero:
            return {"ok": False, "error": "sw_conexion_incompleta"}
        ejecutar_, cerrar = EJECUTORES[c.provider_type](primero[0], conf)
        try:
            rc, salida = ejecutar_("uname -sr" if c.provider_type == "sw_ssh" else "$PSVersionTable.PSVersion.ToString()")
        finally:
            cerrar()
        return {"ok": rc == 0, "host": primero[0], "output": (salida or "").strip()[:200]}
    except Exception as e:  # noqa: BLE001
        logger.warning("probar: excepcion ignorada", exc_info=True)
        return {"ok": False, "error": getattr(e, "code", None) or type(e).__name__}
