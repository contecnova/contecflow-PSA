"""Modo Docker completo de Contecflow: `setup.sh docker` y `setup.bat docker` (22-11-2026).

Un único script para los dos lanzadores, para que hagan exactamente lo mismo en
Windows, macOS y Linux. Solo usa la biblioteca estándar: corre con cualquier
Python 3.8+ (el del sistema o el de .venv), sin instalar dependencias.

    python scripts/docker_stack.py arrancar [demo|clean]
    python scripts/docker_stack.py parar
    python scripts/docker_stack.py estado

`arrancar`:
  1. Comprueba Docker y, si el daemon está parado, intenta encenderlo.
  2. Completa el .env con lo que el compose exige y falta (credenciales de
     Postgres/S3, METRICS_AUTH_TOKEN, usuario y contraseña de Grafana, el origen
     de la web en ALLOWED_ORIGINS). Los secretos se GENERAN una vez y se guardan
     en .env; nunca se escriben en el repositorio. Lo que ya tiene valor no se toca.
  3. Crea los volúmenes persistentes si faltan (contecflow_postgres_data,
     contecflow_s3_data). NUNCA los borra ni los recrea.
  4. Construye y levanta infraestructura + perfil `app` + perfil
     `observability` (el servicio `migrate` aplica las migraciones antes de la
     API; si fallan, la API no arranca y se enseña su log).
  5. Intenta el perfil `host-metrics` (node-exporter, cAdvisor) aparte: si en
     Docker Desktop no arrancan, avisa y sigue.
  6. Espera a que la API esté sana, alinea la contraseña de Grafana con el .env
     y, si se pide (`demo`/`clean`), siembra los datos dentro del contenedor.
  7. Enseña las URLs.

`parar`: `docker compose down` de todos los perfiles, SIN `-v`: los datos se
conservan. Documentación: docs/OBSERVABILIDAD.md.
"""
from __future__ import annotations

import json
import os
import platform
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ENV = RAIZ / ".env"
PERFILES = ["--profile", "app", "--profile", "observability"]
TODOS_LOS_PERFILES = PERFILES + ["--profile", "s3", "--profile", "host-metrics"]
VOLUMENES_PERSISTENTES = ("contecflow_postgres_data", "contecflow_s3_data")
_MARCADORES = ("CHANGE_ME", "REPLACE_ME", "TODO", "PLACEHOLDER", "YOUR_")


def info(msg: str) -> None:
    print(f"[INFO] {msg}", flush=True)


def ok(msg: str) -> None:
    print(f"[OK] {msg}", flush=True)


def aviso(msg: str) -> None:
    print(f"[WARN] {msg}", flush=True)


def fallo(msg: str) -> None:
    print(f"[ERROR] {msg}", flush=True)


# ── Docker ────────────────────────────────────────────────────────────────────

def _compose_base() -> list:
    if subprocess.run(["docker", "compose", "version"], capture_output=True).returncode == 0:
        return ["docker", "compose"]
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    return []


def compose(*args, capturar=False, comprobar=False):
    base = _compose_base()
    r = subprocess.run(base + list(args), cwd=RAIZ, capture_output=capturar, text=True)
    if comprobar and r.returncode != 0:
        raise SystemExit(r.returncode)
    return r


def _daemon_vivo() -> bool:
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


def asegurar_docker() -> None:
    if not shutil.which("docker"):
        fallo("Docker no está instalado. Instala Docker Desktop (Windows/macOS) o Docker Engine (Linux).")
        raise SystemExit(1)
    if not _daemon_vivo():
        aviso("El daemon de Docker no responde; intentando arrancarlo (hasta 3 min)...")
        sistema = platform.system()
        try:
            if sistema == "Windows":
                for exe in (Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Docker" / "Docker"
                            / "Docker Desktop.exe",):
                    if exe.exists():
                        subprocess.Popen([str(exe)], close_fds=True)
            elif sistema == "Darwin":
                subprocess.run(["open", "-ga", "Docker"], capture_output=True)
            elif shutil.which("systemctl"):
                subprocess.run(["systemctl", "start", "docker"], capture_output=True)
        except OSError:
            pass
        limite = time.time() + 180
        while not _daemon_vivo():
            if time.time() > limite:
                fallo("Docker no arrancó en 3 min. Ábrelo a mano y repite.")
                raise SystemExit(1)
            time.sleep(3)
    if not _compose_base():
        fallo("No se encuentra `docker compose` ni `docker-compose`.")
        raise SystemExit(1)
    ok("Docker disponible")


def _volumen_existe(nombre: str) -> bool:
    return subprocess.run(["docker", "volume", "inspect", nombre], capture_output=True).returncode == 0


def asegurar_volumenes_persistentes() -> None:
    """Equivale a `ensure_persistent_volumes` de setup.sh: crea, nunca borra."""
    creados = []
    for v in VOLUMENES_PERSISTENTES:
        if not _volumen_existe(v):
            subprocess.run(["docker", "volume", "create", v], capture_output=True, check=False)
            creados.append(v)
    if creados:
        info("Volúmenes persistentes creados: " + ", ".join(creados))
    else:
        ok("Volúmenes persistentes ya presentes (protegidos de 'down -v')")


# ── .env ──────────────────────────────────────────────────────────────────────

class Env:
    """Lectura y alta de claves en .env conservando todo lo demás (y sus finales de línea)."""

    def __init__(self, ruta: Path):
        self.ruta = ruta
        # Sin traducir los saltos (newline=""): `read_text` convierte CRLF en LF y
        # el .env de Windows se reescribía con LF.
        self.texto = ""
        if ruta.exists():
            with open(ruta, encoding="utf-8", newline="") as f:
                self.texto = f.read()
        self.salto = "\r\n" if "\r\n" in self.texto else "\n"

    def leer(self, clave: str) -> str:
        valor = ""
        for linea in self.texto.splitlines():
            if linea.startswith(clave + "="):
                valor = linea.split("=", 1)[1].strip()
        if valor.upper().startswith(_MARCADORES):
            return ""
        return valor

    def poner(self, clave: str, valor: str) -> None:
        lineas = self.texto.splitlines()
        for i, linea in enumerate(lineas):
            if linea.startswith(clave + "="):
                lineas[i] = f"{clave}={valor}"
                break
        else:
            lineas.append(f"{clave}={valor}")
        self.texto = self.salto.join(lineas) + self.salto
        self.ruta.write_text(self.texto, encoding="utf-8", newline="")


def _secreto(n: int = 24) -> str:
    return secrets.token_urlsafe(n)


def _contrasena() -> str:
    return secrets.token_urlsafe(15).replace("-", "x").replace("_", "y") + "Aa1!"


def _puerto(valor: str, defecto: str) -> tuple:
    """`127.0.0.1:8080` | `8080` → ('localhost', '8080')."""
    valor = (valor or defecto).strip()
    if ":" in valor:
        host, puerto = valor.rsplit(":", 1)
    else:
        host, puerto = "", valor
    if host in ("", "127.0.0.1", "0.0.0.0"):
        host = "localhost"
    return host, puerto


def asegurar_env() -> Env:
    nuevo = not ENV.exists()
    env = Env(ENV)
    if nuevo:
        info("No hay .env: se crea uno mínimo con secretos aleatorios.")
        for clave, valor in (("SECRET_KEY", secrets.token_hex(32)), ("CLIENT_PORTAL_SECRET", secrets.token_hex(32)),
                             ("ENVIRONMENT", "development"), ("SUPERADMIN_EMAIL", "admin@company.com"),
                             ("SUPERADMIN_PASSWORD", _contrasena()), ("DEFAULT_USER_PASSWORD", _contrasena())):
            env.poner(clave, valor)

    for clave in ("POSTGRES_USER", "POSTGRES_DB", "MINIO_ROOT_USER"):
        if not env.leer(clave):
            env.poner(clave, "contecflow")
            aviso(f"{clave} no estaba definida; se fijó 'contecflow' en .env")

    # Igual que setup.sh: con el volumen ya inicializado, un secreto nuevo no
    # coincidiría con el que se usó al crearlo.
    for clave, volumen in (("POSTGRES_PASSWORD", "contecflow_postgres_data"),
                           ("MINIO_ROOT_PASSWORD", "contecflow_s3_data")):
        if not env.leer(clave):
            if _volumen_existe(volumen):
                env.poner(clave, "contecflow_dev")
                aviso(f"{clave} faltaba con el volumen {volumen} ya creado; se aplicó el valor local histórico")
            else:
                env.poner(clave, _secreto())
                aviso(f"{clave} no estaba definida; se generó y se guardó en .env")

    if not env.leer("ENVIRONMENT"):
        env.poner("ENVIRONMENT", "development")
    if not env.leer("METRICS_AUTH_TOKEN"):
        env.poner("METRICS_AUTH_TOKEN", _secreto(32))
        aviso("METRICS_AUTH_TOKEN no estaba definido; se generó y se guardó en .env (Prometheus lo usa)")
    if not env.leer("GRAFANA_ADMIN_USER"):
        env.poner("GRAFANA_ADMIN_USER", "admin")
    if not env.leer("GRAFANA_ADMIN_PASSWORD") or env.leer("GRAFANA_ADMIN_PASSWORD") == "admin":
        env.poner("GRAFANA_ADMIN_PASSWORD", _contrasena())
        aviso("GRAFANA_ADMIN_PASSWORD no estaba definida; se generó y se guardó en .env")

    # La web en Docker sale por WEB_PORT: su origen tiene que estar en
    # ALLOWED_ORIGINS o el middleware CSRF rechaza el login (403).
    host, puerto = _puerto(env.leer("WEB_PORT"), "127.0.0.1:8080")
    origenes_web = [f"http://{host}:{puerto}"] + ([f"http://127.0.0.1:{puerto}"] if host == "localhost" else [])
    crudo = env.leer("ALLOWED_ORIGINS")
    try:
        actuales = json.loads(crudo) if crudo else []
        if not isinstance(actuales, list):
            raise ValueError
    except ValueError:
        actuales = [o.strip() for o in crudo.split(",") if o.strip()]
    faltan = [o for o in origenes_web if o not in actuales]
    if faltan:
        env.poner("ALLOWED_ORIGINS", json.dumps(actuales + faltan, separators=(",", ":")))
        info("ALLOWED_ORIGINS: añadido " + ", ".join(faltan))
    return env


# ── Arranque ──────────────────────────────────────────────────────────────────

def _estado_contenedor(nombre: str) -> tuple:
    r = subprocess.run(["docker", "inspect", "-f",
                        "{{.State.Status}}|{{.State.ExitCode}}|{{if .State.Health}}{{.State.Health.Status}}{{end}}",
                        nombre], capture_output=True, text=True)
    if r.returncode != 0:
        return ("ausente", "", "")
    partes = (r.stdout.strip().split("|") + ["", "", ""])[:3]
    return tuple(partes)


def esperar_sano(nombre: str, segundos: int) -> bool:
    limite = time.time() + segundos
    while time.time() < limite:
        estado, _, salud = _estado_contenedor(nombre)
        if salud == "healthy" or (estado == "running" and salud == ""):
            return True
        if estado in ("exited", "dead"):
            return False
        time.sleep(3)
    return False


def _migraciones_ok() -> bool:
    estado, codigo, _ = _estado_contenedor("contecflow-migrate")
    return estado == "exited" and codigo == "0"


def _sincronizar_grafana(env: Env) -> None:
    """Grafana solo aplica GF_SECURITY_ADMIN_PASSWORD al crear su base: si el
    volumen ya existía, se alinea la contraseña con la del .env."""
    if not esperar_sano("contecflow-grafana", 120):
        aviso("Grafana no está sana todavía: docker compose logs grafana")
        return
    r = compose("exec", "-T", "grafana", "grafana", "cli", "admin", "reset-admin-password",
                env.leer("GRAFANA_ADMIN_PASSWORD"), capturar=True)
    if r.returncode != 0:
        aviso("No se pudo alinear la contraseña de Grafana con el .env (la del primer arranque sigue valiendo).")


def _sembrar(modo: str) -> None:
    if modo == "demo":
        info("Cargando datos demo en la base del contenedor...")
        r = compose("exec", "-T", "api", "python", "-m", "app.db.seed")
    else:
        info("Dejando la base con solo el administrador...")
        r = compose("exec", "-T", "api", "python", "scripts/reset_to_admin_only.py")
    if r.returncode != 0:
        fallo(f"El sembrado ({modo}) ha fallado: revisa el mensaje de arriba.")
        raise SystemExit(1)
    ok(f"Datos {modo} cargados")


def _hay_usuarios() -> bool:
    r = compose("exec", "-T", "api", "python", "-c",
                "from app.db.session import SessionLocal\n"
                "from app.models.user import User\n"
                "db=SessionLocal()\n"
                "print(db.query(User).filter(User.hashed_password.isnot(None)).count())\n"
                "db.close()", capturar=True)
    try:
        return int((r.stdout or "0").strip().splitlines()[-1]) > 0
    except (ValueError, IndexError):
        return True  # si no se sabe, no se asusta a nadie


def urls(env: Env) -> None:
    web = _puerto(env.leer("WEB_PORT"), "127.0.0.1:8080")
    graf = _puerto(env.leer("GRAFANA_PORT"), "127.0.0.1:3001")
    prom = _puerto(env.leer("PROMETHEUS_PORT"), "127.0.0.1:9090")
    alm = _puerto(env.leer("ALERTMANAGER_PORT"), "127.0.0.1:9093")
    print("")
    print("============================================")
    print("  Contecflow en Docker")
    print("============================================")
    print(f"  App:           http://{web[0]}:{web[1]}")
    print(f"  API (docs):    http://{web[0]}:{web[1]}/api/v1/docs")
    print(f"  Grafana:       http://{graf[0]}:{graf[1]}   (usuario: {env.leer('GRAFANA_ADMIN_USER') or 'admin'};"
          " contraseña: GRAFANA_ADMIN_PASSWORD en .env)")
    print(f"  Prometheus:    http://{prom[0]}:{prom[1]}")
    print(f"  Alertmanager:  http://{alm[0]}:{alm[1]}")
    print("")
    print("  Logs:  docker compose logs -f api worker beat")
    print("  Parar: setup docker-stop   (conserva los datos)")
    print("")


def arrancar(modo: str = "") -> None:
    asegurar_docker()
    env = asegurar_env()
    asegurar_volumenes_persistentes()

    info("Construyendo imágenes y levantando todo (infraestructura + app + observabilidad)...")
    info("La primera vez tarda varios minutos (imagen de la API y build del frontend).")
    r = compose(*PERFILES, "up", "-d", "--build")
    if r.returncode != 0:
        if not _migraciones_ok():
            fallo("Las migraciones (servicio migrate) han fallado; la API no arranca con un esquema a medias:")
            compose("logs", "--tail", "60", "migrate")
        else:
            fallo("docker compose up ha fallado; revisa el mensaje de arriba.")
        raise SystemExit(1)
    if _migraciones_ok():
        ok("Migraciones aplicadas (alembic upgrade head + políticas RLS)")

    info("Métricas de máquina y contenedores (node-exporter, cAdvisor)...")
    r = compose("--profile", "host-metrics", "up", "-d", "node-exporter", "cadvisor", capturar=True)
    if r.returncode != 0:
        aviso("node-exporter/cAdvisor no arrancaron (habitual en algunas versiones de Docker Desktop). "
              "El resto funciona; esos paneles quedan vacíos. docs/OBSERVABILIDAD.md §Docker Desktop.")

    info("Esperando a que la API esté sana (hasta 5 min)...")
    if not esperar_sano("contecflow-api", 300):
        fallo("La API no está sana. Últimas líneas de su log:")
        compose("logs", "--tail", "60", "api")
        raise SystemExit(1)
    ok("API sana")
    for nombre in ("contecflow-worker", "contecflow-beat", "contecflow-web", "contecflow-prometheus",
                   "contecflow-alertmanager"):
        if not esperar_sano(nombre, 90):
            aviso(f"{nombre} no está en marcha: docker compose logs {nombre.split('-', 1)[1]}")
    _sincronizar_grafana(env)

    if modo in ("demo", "clean"):
        _sembrar(modo)
    elif not _hay_usuarios():
        aviso("La base no tiene usuarios todavía. Siembra con:  setup docker demo   o   setup docker clean")
    urls(env)


def parar() -> None:
    asegurar_docker()
    info("Parando todos los contenedores de Contecflow (los datos se conservan en los volúmenes)...")
    r = compose(*TODOS_LOS_PERFILES, "down")
    if r.returncode != 0:
        raise SystemExit(r.returncode)
    ok("Docker detenido (datos conservados en volúmenes)")


def estado() -> None:
    asegurar_docker()
    compose(*TODOS_LOS_PERFILES, "ps")
    if ENV.exists():
        urls(Env(ENV))


def main(argv: list) -> int:
    orden = argv[1] if len(argv) > 1 else ""
    if orden == "arrancar":
        modo = (argv[2] if len(argv) > 2 else "").lower()
        modo = {"seed": "demo", "zero": "clean", "cero": "clean", "admin-only": "clean",
                "admin_only": "clean"}.get(modo, modo)
        if modo not in ("", "demo", "clean"):
            fallo(f"Modo de datos inválido: {modo} (usa demo|clean)")
            return 1
        arrancar(modo)
    elif orden == "parar":
        parar()
    elif orden == "estado":
        estado()
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
