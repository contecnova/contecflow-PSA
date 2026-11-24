"""Contenedor efímero por ejecución (TICKET_A_PR.md §Aislamiento). Sin Docker, NADA se ejecuta.

Por qué así: el agente ejecuta órdenes de shell con los permisos de quien lo
arranca y su análisis de órdenes es aproximado; el código del repositorio del
cliente tampoco es de fiar (los tests lo ejecutan). Por eso cada fase corre en su
propio contenedor, que se destruye al terminar, con:

- **red interna** (`docker network create --internal`): sin salida directa ni
  acceso a la red de la plataforma. La única salida es un **proxy** (squid) en
  otro contenedor, unido a esa red y a la de salida, que solo deja pasar
  `CONNECT` a los hosts de la lista blanca (API del modelo y, si la empresa lo
  pide, registros de paquetes). El host Git NO está en la lista: el código se
  baja y el PR se abre desde el servidor por API, así que el contenedor nunca
  ve una credencial de Git;
- **sin secretos de la plataforma**: nada se monta del host; el espacio de
  trabajo es un volumen propio que se rellena por la entrada estándar (tar) y
  se vacía por la salida estándar. Las variables del modelo van en un fichero
  `--env-file` temporal (0600) que se borra en cuanto se crea el contenedor;
- **usuario sin privilegios** (1000:1000), `--cap-drop ALL`,
  `no-new-privileges`, raíz de **solo lectura** (`--read-only`, `/tmp` y `HOME`
  en tmpfs) y el espacio de trabajo de solo lectura en la fase PLAN;
- **límites** de CPU, memoria (sin swap), procesos y **tiempo** (al pasarlo,
  `docker kill`);
- **destrucción**: contenedores, red y volumen se borran siempre (`finally`).

Se habla con Docker por su CLI (`TICKET_PR_DOCKER_BIN`), con argumentos en lista
(nunca `shell=True`). `ordenes_*` construyen las órdenes sin ejecutarlas: los
tests las comprueban sin Docker.
"""
from __future__ import annotations

import base64
import logging
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

USUARIO = "1000:1000"
ETIQUETA = "contecflow.ticket_pr=1"
ALIAS_DEL_PROXY = "egress"
PUERTO_DEL_PROXY = 3128


class DockerNoDisponible(RuntimeError):
    """No hay Docker (o no responde): el módulo lo dice y no ejecuta nada."""
    codigo = "ticket_pr_docker_no_disponible"


@dataclass(frozen=True)
class Limites:
    cpus: float = 2.0
    memoria_mb: int = 4096
    procesos: int = 512
    segundos: int = 900


@dataclass
class Pedido:
    imagen: str
    argumentos: list[str]
    espacio: bytes                                   # tar con el espacio de trabajo
    limites: Limites
    hosts_permitidos: list[tuple[str, int]] = field(default_factory=list)   # (host, puerto)
    entorno: dict[str, str] = field(default_factory=dict)                  # va por --env-file (0600)
    entrypoint: Optional[str] = None
    solo_lectura: bool = False                       # espacio de trabajo de solo lectura (PLAN)
    devolver_espacio: bool = False


@dataclass
class Resultado:
    codigo_salida: int
    salida: str
    errores: str
    segundos: int
    espacio: Optional[bytes] = None
    agotado: bool = False


def _settings():
    from app.core.config import settings
    return settings


def _docker() -> str:
    return str(getattr(_settings(), "TICKET_PR_DOCKER_BIN", "docker") or "docker")


def _correr(args: list[str], *, entrada: Optional[bytes] = None, timeout: float = 120,
            binario: bool = False) -> subprocess.CompletedProcess:
    if binario or entrada is not None:
        return subprocess.run([_docker(), *args], input=entrada, capture_output=True, timeout=timeout, check=False)
    return subprocess.run([_docker(), *args], capture_output=True, timeout=timeout, check=False,
                          encoding="utf-8", errors="replace")


#: Última comprobación (instante, resultado): la pantalla pregunta a menudo y
#: `docker version` cuesta un proceso; 30 s bastan para decir «no hay Docker».
_ULTIMA: list = [0.0, (False, None)]
_VIGENCIA_S = 30.0


def disponible() -> tuple[bool, Optional[str]]:
    """(¿hay Docker y responde el demonio?, versión del servidor)."""
    ahora = time.monotonic()
    if ahora - _ULTIMA[0] < _VIGENCIA_S:
        return _ULTIMA[1]
    resultado: tuple[bool, Optional[str]] = (False, None)
    if shutil.which(_docker()):
        try:
            r = _correr(["version", "--format", "{{.Server.Version}}"], timeout=15)
            if r.returncode == 0:
                resultado = (True, (r.stdout or "").strip()[:40] or None)
        except (OSError, subprocess.SubprocessError):
            logger.info("ticket_pr: docker no responde", exc_info=True)
    _ULTIMA[0], _ULTIMA[1] = ahora, resultado
    return resultado


def exigir_docker() -> None:
    ok, _ = disponible()
    if not ok:
        raise DockerNoDisponible("docker no disponible")


def descargar_imagen(imagen: str, timeout: float = 600) -> bool:
    """`docker pull` de la imagen fijada (prueba de conexión). True si se descarga o ya está."""
    try:
        r = _correr(["pull", "--quiet", imagen], timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        logger.info("ticket_pr: no se pudo descargar %s", imagen, exc_info=True)
        return False
    return r.returncode == 0


# ── Órdenes (puras: se prueban sin Docker) ───────────────────────────────────

def configuracion_del_proxy(hosts: list[tuple[str, int]]) -> str:
    """squid.conf: solo esos hosts y puertos; nada de caché; nada más."""
    dominios = sorted({h.lower() for h, _ in hosts})
    puertos = sorted({int(p) for _, p in hosts} | {443})
    lineas = [
        f"http_port {PUERTO_DEL_PROXY}",
        "acl CONNECT method CONNECT",
        f"acl puertos port {' '.join(str(p) for p in puertos)}",
        f"acl permitidos dstdomain {' '.join(dominios)}" if dominios else "acl permitidos dstdomain .invalid",
        "http_access deny !puertos",
        "http_access allow permitidos",
        "http_access deny all",
        "cache deny all",
        "via off",
        "forwarded_for delete",
        "access_log stdio:/dev/stdout",
        "cache_log /dev/stderr",
        "pid_filename none",
        "coredump_dir /tmp",
    ]
    return "\n".join(lineas) + "\n"


def ordenes_de_preparacion(nombres: dict, helper: str) -> list[list[str]]:
    """Red interna, volumen y relleno del volumen (tar por la entrada estándar)."""
    return [
        ["network", "create", "--internal", "--label", ETIQUETA, nombres["red"]],
        ["volume", "create", "--label", ETIQUETA, nombres["volumen"]],
        ["run", "--rm", "-i", "--network", "none", "--label", ETIQUETA, "--user", "0:0", "--cap-drop", "ALL",
         "--cap-add", "CHOWN", "--cap-add", "DAC_OVERRIDE", "--cap-add", "FOWNER",
         "--security-opt", "no-new-privileges", "-v", f"{nombres['volumen']}:/workspace",
         "--entrypoint", "sh", helper, "-c", "tar -x -C /workspace && chown -R 1000:1000 /workspace"],
    ]


def orden_del_proxy(nombres: dict, imagen: str, hosts: list[tuple[str, int]]) -> list[str]:
    conf = base64.b64encode(configuracion_del_proxy(hosts).encode()).decode()
    return ["run", "-d", "--name", nombres["proxy"], "--label", ETIQUETA, "--network", "bridge",
            "--cap-drop", "ALL", "--cap-add", "SETUID", "--cap-add", "SETGID",
            "--security-opt", "no-new-privileges", "--memory", "256m", "--pids-limit", "128",
            "-e", f"SQUID_CONF_B64={conf}", "--entrypoint", "sh", imagen, "-c",
            'echo "$SQUID_CONF_B64" | base64 -d > /tmp/squid.conf && exec squid -N -f /tmp/squid.conf']


def orden_del_agente(nombres: dict, pedido: Pedido, fichero_de_entorno: Optional[str]) -> list[str]:
    lim = pedido.limites
    montaje = f"{nombres['volumen']}:/workspace" + (":ro" if pedido.solo_lectura else "")
    args = ["create", "--name", nombres["agente"], "--label", ETIQUETA,
            "--network", nombres["red"] if pedido.hosts_permitidos else "none",
            "--read-only", "--tmpfs", "/tmp:rw,nosuid,size=512m", "--tmpfs", "/home/agent:rw,nosuid,size=1024m",
            "--user", USUARIO, "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--pids-limit", str(lim.procesos), "--cpus", str(lim.cpus),
            "--memory", f"{lim.memoria_mb}m", "--memory-swap", f"{lim.memoria_mb}m",
            "-e", "HOME=/home/agent", "-v", montaje, "-w", "/workspace"]
    if pedido.hosts_permitidos:
        proxy = f"http://{ALIAS_DEL_PROXY}:{PUERTO_DEL_PROXY}"
        for var in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
            args += ["-e", f"{var}={proxy}"]
        args += ["-e", "NO_PROXY=", "-e", "no_proxy="]
    if fichero_de_entorno:
        args += ["--env-file", fichero_de_entorno]
    if pedido.entrypoint:
        args += ["--entrypoint", pedido.entrypoint]
    return args + [pedido.imagen, *pedido.argumentos]


def orden_de_exportacion(nombres: dict, helper: str) -> list[str]:
    return ["run", "--rm", "--network", "none", "--label", ETIQUETA, "--user", "0:0", "--cap-drop", "ALL",
            "--cap-add", "DAC_READ_SEARCH", "--security-opt", "no-new-privileges",
            "-v", f"{nombres['volumen']}:/workspace:ro", "--entrypoint", "tar", helper, "-c", "-C", "/workspace", "."]


def ordenes_de_limpieza(nombres: dict) -> list[list[str]]:
    return [["rm", "-f", nombres["agente"]], ["rm", "-f", nombres["proxy"]],
            ["network", "rm", nombres["red"]], ["volume", "rm", "-f", nombres["volumen"]]]


def nombres_para(sufijo: Optional[str] = None) -> dict:
    s = sufijo or uuid.uuid4().hex[:12]
    return {"red": f"cf-tpr-net-{s}", "volumen": f"cf-tpr-vol-{s}", "proxy": f"cf-tpr-proxy-{s}",
            "agente": f"cf-tpr-agent-{s}"}


# ── Ejecución ────────────────────────────────────────────────────────────────

def _fichero_de_entorno(entorno: dict[str, str]) -> Optional[str]:
    if not entorno:
        return None
    fd, ruta = tempfile.mkstemp(prefix="cf-tpr-", suffix=".env")
    try:
        os.chmod(ruta, 0o600)
    except OSError:
        logger.debug("ticket_pr: chmod del fichero de entorno", exc_info=True)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        for k, v in entorno.items():
            f.write(f"{k}={str(v).replace(chr(10), ' ')}\n")
    return ruta


def _borrar(ruta: Optional[str]) -> None:
    if ruta:
        try:
            os.remove(ruta)
        except OSError:
            logger.debug("ticket_pr: no se pudo borrar %s", ruta, exc_info=True)


def _exigir(r: subprocess.CompletedProcess, paso: str) -> None:
    if r.returncode != 0:
        err = r.stderr if isinstance(r.stderr, str) else (r.stderr or b"").decode("utf-8", "replace")
        raise RuntimeError(f"docker {paso}: {err.strip()[:300]}")


def ejecutar(pedido: Pedido) -> Resultado:
    """Prepara, ejecuta y destruye. Lanza `DockerNoDisponible` si no hay Docker."""
    exigir_docker()
    s = _settings()
    helper = s.TICKET_PR_HELPER_IMAGE
    nombres = nombres_para()
    entorno_en_disco: Optional[str] = None
    inicio = time.monotonic()
    try:
        red, volumen, relleno = ordenes_de_preparacion(nombres, helper)
        if pedido.hosts_permitidos:
            _exigir(_correr(red), "network create")
        _exigir(_correr(volumen), "volume create")
        _exigir(_correr(relleno, entrada=pedido.espacio, timeout=300, binario=True), "preparar espacio")
        if pedido.hosts_permitidos:
            _exigir(_correr(orden_del_proxy(nombres, s.TICKET_PR_EGRESS_PROXY_IMAGE, pedido.hosts_permitidos),
                            timeout=120), "proxy")
            _exigir(_correr(["network", "connect", "--alias", ALIAS_DEL_PROXY, nombres["red"], nombres["proxy"]]),
                    "network connect")
        entorno_en_disco = _fichero_de_entorno(pedido.entorno)
        _exigir(_correr(orden_del_agente(nombres, pedido, entorno_en_disco), timeout=120), "create")
        _borrar(entorno_en_disco)           # Docker ya lo ha leído: no queda en disco
        entorno_en_disco = None
        agotado = False
        try:
            r = _correr(["start", "-a", nombres["agente"]], timeout=pedido.limites.segundos)
            codigo, salida, errores = r.returncode, r.stdout or "", r.stderr or ""
        except subprocess.TimeoutExpired as exc:
            agotado = True
            _correr(["kill", nombres["agente"]], timeout=30)
            codigo = 124
            salida = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            errores = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        espacio = None
        if pedido.devolver_espacio and not agotado:
            r = _correr(orden_de_exportacion(nombres, helper), timeout=300, binario=True)
            _exigir(r, "exportar espacio")
            espacio = r.stdout
        return Resultado(codigo, salida, errores, int(time.monotonic() - inicio), espacio, agotado)
    finally:
        _borrar(entorno_en_disco)
        for orden in ordenes_de_limpieza(nombres):
            try:
                _correr(orden, timeout=60)
            except (OSError, subprocess.SubprocessError):
                logger.warning("ticket_pr: limpieza «docker %s» fallida", " ".join(orden), exc_info=True)
