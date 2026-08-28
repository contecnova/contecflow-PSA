"""Invariantes del stack Docker (auditoría 2026-08, P2-12).

El despliegue anterior no podía funcionar y nadie lo había comprobado: sus
propios autores anotaron que nunca se levantó. Estos tests fijan por escrito las
propiedades de las que depende que funcione y que sea seguro, para que un cambio
que las rompa se detecte sin necesidad de un host con Docker.

Lo que NO cubren, y hay que decirlo: esto valida la DEFINICIÓN del stack, no que
levante. Un `docker compose --profile app up` en un host con Docker sigue siendo
imprescindible antes de publicar, y no se ha podido ejecutar en el entorno de la
auditoría.
"""
from __future__ import annotations

import pathlib
import re

import pytest

yaml = pytest.importorskip("yaml")

REPO = pathlib.Path(__file__).resolve().parents[1]
COMPOSE = REPO / "docker-compose.yml"
NGINX = REPO / "frontend" / "nginx.frontend.conf"
DOCKERIGNORE = REPO / ".dockerignore"


@pytest.fixture(scope="module")
def compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


# ── Un solo fichero de compose ────────────────────────────────────────────────

def test_solo_existe_un_compose():
    """Antes había dos (docker-compose.dev.yml y deploy/docker-compose.yml).

    Dos definiciones de la misma infraestructura es la clase de divergencia que
    dejó al worker apuntando a otra base de datos que la API. Los perfiles
    resuelven dev vs producción sin duplicar.
    """
    encontrados = sorted(
        f.relative_to(REPO).as_posix()
        for f in REPO.rglob("docker-compose*.yml")
        if "node_modules" not in f.parts and ".venv" not in f.parts and "venv" not in f.parts
    )
    assert encontrados == ["docker-compose.yml"], (
        f"hay más de un fichero de compose: {encontrados}"
    )


# ── Seguridad de red ──────────────────────────────────────────────────────────

def test_ningun_puerto_se_publica_en_todas_las_interfaces(compose):
    """Con `"5432:5432"` Docker publica en 0.0.0.0.

    Este fichero se copia para levantar demos y preproducciones, y ahí eso
    significa un Postgres, un Redis sin contraseña y un MinIO accesibles desde
    toda la red con credenciales de desarrollo.
    """
    infractores = []
    for nombre, svc in compose["services"].items():
        for mapeo in svc.get("ports", []) or []:
            if not isinstance(mapeo, str):
                infractores.append(f"{nombre}: {mapeo!r} (formato no textual)")
                continue
            # Válido: "127.0.0.1:5434:5432" o "${VAR:-127.0.0.1:5434}:5432"
            if "127.0.0.1" not in mapeo and "localhost" not in mapeo:
                infractores.append(f"{nombre}: {mapeo}")
    assert not infractores, (
        "puertos publicados en todas las interfaces:\n  " + "\n  ".join(infractores)
    )


def test_la_api_no_publica_puerto_al_host(compose):
    """Quien entra es nginx, por la red interna.

    Publicar la API saltaría las cabeceras de seguridad y el tope de tamaño de
    cuerpo que aplica nginx.
    """
    api = compose["services"]["api"]
    assert not api.get("ports"), (
        "la API publica puertos al host: el acceso debe pasar por nginx"
    )
    assert api.get("expose"), "la API debe exponer su puerto a la red interna"


# ── Fallo temprano en vez de defectos silenciosos ─────────────────────────────

@pytest.mark.parametrize(
    "variable",
    ["POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB",
     "MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD"],
)
def test_las_variables_criticas_usan_fallo_temprano(variable):
    """`${VAR:?}` aborta el `up` si falta; `${VAR:-algo}` arranca con un defecto.

    Un defecto silencioso en una credencial significa levantar el stack con
    credenciales conocidas sin que nadie se entere.
    """
    texto = COMPOSE.read_text(encoding="utf-8")
    usos = re.findall(r"\$\{" + variable + r"(:[?-][^}]*)?\}", texto)
    assert usos, f"{variable} no se usa en el compose"
    con_defecto = [u for u in usos if u.startswith(":-")]
    assert not con_defecto, (
        f"{variable} tiene valor por defecto en el compose ({con_defecto}): "
        "debe usar ${VAR:?} para fallar al arrancar"
    )


# ── Protección de los datos ───────────────────────────────────────────────────

def test_los_datos_irremplazables_estan_en_volumenes_externos(compose):
    """`external: true` hace que `docker compose down -v` no los borre.

    Es la lección del incidente de contecmind: un `down -v` recreó los volúmenes
    y se perdieron los metadatos y el índice de golpe.
    """
    volumenes = compose.get("volumes", {})
    for nombre in ("postgres_data", "minio_data"):
        assert nombre in volumenes, f"falta el volumen {nombre}"
        assert volumenes[nombre].get("external") is True, (
            f"{nombre} contiene datos irremplazables y debe ser external: true"
        )


def test_setup_crea_los_volumenes_externos():
    """`external: true` impide que compose los cree, así que `up` fallaría con
    "external volume not found" en una máquina nueva. setup.sh los crea."""
    setup = (REPO / "setup.sh").read_text(encoding="utf-8")
    assert "ensure_persistent_volumes" in setup
    for v in ("contecflow_postgres_data", "contecflow_minio_data"):
        assert v in setup, f"setup.sh no crea el volumen {v}"


# ── Reproducibilidad ──────────────────────────────────────────────────────────

def test_ninguna_imagen_usa_latest(compose):
    """Con un tag móvil, dos despliegues del mismo commit pueden levantar
    imágenes distintas y un fallo deja de ser reproducible."""
    infractores = [
        f"{n}: {svc['image']}"
        for n, svc in compose["services"].items()
        if isinstance(svc.get("image"), str)
        and (svc["image"].endswith(":latest") or ":" not in svc["image"].split("/")[-1])
        and "${" not in svc["image"]
    ]
    assert not infractores, "imágenes sin versión fijada:\n  " + "\n  ".join(infractores)


# ── Lo que hacía imposible que funcionara ─────────────────────────────────────

def test_nginx_proxea_la_api():
    """El defecto que impedía que el despliegue funcionase.

    nginx servía sólo estáticos: el navegador cargaba la aplicación y ninguna
    llamada a la API llegaba a destino.
    """
    conf = NGINX.read_text(encoding="utf-8")
    assert "proxy_pass" in conf, "nginx no hace proxy a la API"
    assert re.search(r"location\s+/api/", conf), "falta el bloque location /api/"
    assert "upstream" in conf and "api:8000" in conf, (
        "el upstream debe apuntar al servicio api de la red de compose"
    )


def test_nginx_soporta_websocket():
    """Sin las cabeceras de Upgrade, el chat queda en reconexión perpetua."""
    conf = NGINX.read_text(encoding="utf-8")
    assert "$http_upgrade" in conf and '"upgrade"' in conf, (
        "falta la negociación de WebSocket en nginx"
    )


def test_nginx_acota_el_tamano_del_cuerpo():
    """Sin la directiva, nginx aplica 1 MB y rechaza subidas legítimas."""
    conf = NGINX.read_text(encoding="utf-8")
    assert re.search(r"client_max_body_size\s+\d+m", conf), (
        "falta client_max_body_size en nginx"
    )


def test_nginx_propaga_la_ip_real():
    """Sin X-Forwarded-For, el rate limiting por IP cuenta todas las peticiones
    como procedentes de nginx y un solo cliente agota la cuota de todos."""
    conf = NGINX.read_text(encoding="utf-8")
    for cabecera in ("X-Real-IP", "X-Forwarded-For", "X-Forwarded-Proto"):
        assert cabecera in conf, f"nginx no propaga {cabecera}"


def test_el_index_no_se_cachea():
    """Es el único fichero sin hash en el nombre. Si se cachea, un despliegue
    nuevo sigue sirviendo un index que referencia bundles que ya no existen."""
    conf = NGINX.read_text(encoding="utf-8")
    bloque = conf[conf.index("location = /index.html"):]
    assert "no-store" in bloque[:400] or "no-cache" in bloque[:400], (
        "index.html debe servirse sin caché"
    )


# ── El contexto de build ──────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "patron", [".env", ".git", "*.db", "uploads/", ".venv/", "node_modules/"]
)
def test_el_dockerignore_excluye_lo_sensible(patron):
    """Sin .dockerignore, el `COPY . .` metía SECRET_KEY, credenciales de base de
    datos, la clave de Anthropic, el historial de git y datos de clientes dentro
    de la imagen."""
    assert DOCKERIGNORE.exists(), "no existe .dockerignore"
    lineas = {
        l.strip() for l in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
        if l.strip() and not l.startswith("#")
    }
    assert patron in lineas, f".dockerignore no excluye {patron}"


# ── Planificador singleton ────────────────────────────────────────────────────

def test_beat_es_un_servicio_aparte(compose):
    """Antes iba como `worker --beat` en el mismo contenedor.

    Con más de una réplica del worker eso son varios planificadores disparando la
    misma tarea periódica: informes y correos duplicados.
    """
    assert "beat" in compose["services"], "beat debe ser un servicio propio"
    worker_cmd = " ".join(str(x) for x in compose["services"]["worker"]["command"])
    assert "--beat" not in worker_cmd, (
        "el worker no debe llevar --beat: beat tiene que ser singleton"
    )
    beat_cmd = " ".join(str(x) for x in compose["services"]["beat"]["command"])
    assert "beat" in beat_cmd


# ── Migraciones antes de la aplicación ────────────────────────────────────────

def test_la_api_espera_a_que_terminen_las_migraciones(compose):
    """Si la migración falla, la aplicación no debe arrancar con un esquema a
    medias."""
    api = compose["services"]["api"]
    dep = api["depends_on"]
    assert "migrate" in dep, "la API debe depender del servicio de migraciones"
    assert dep["migrate"]["condition"] == "service_completed_successfully"


def test_las_migraciones_usan_alembic(compose):
    """No `create_all`: es lo que ocultó el hueco de 19 tablas."""
    cmd = " ".join(str(x) for x in compose["services"]["migrate"]["command"])
    assert "alembic" in cmd and "upgrade" in cmd and "head" in cmd
    assert "create_all" not in cmd


# ── Coherencia de las URLs internas ───────────────────────────────────────────

def test_los_servicios_de_app_comparten_configuracion(compose):
    """El ancla YAML evita que api, worker y beat se desincronicen.

    Era el tipo de divergencia que dejó al worker apuntando a otra base de datos.
    """
    urls = {}
    for nombre in ("api", "worker", "beat", "migrate"):
        env = compose["services"][nombre]["environment"]
        urls[nombre] = (env["DATABASE_URL"], env["REDIS_URL"])
    distintos = {v for v in urls.values()}
    assert len(distintos) == 1, (
        f"los servicios de app no comparten DATABASE_URL/REDIS_URL: {urls}"
    )


def test_las_urls_internas_no_usan_localhost(compose):
    """Dentro de la red de compose los servicios se resuelven por nombre.

    Un `localhost` haría que el contenedor se conectara a sí mismo.
    """
    for nombre in ("api", "worker", "beat", "migrate"):
        env = compose["services"][nombre]["environment"]
        for clave, valor in env.items():
            if isinstance(valor, str) and ("URL" in clave or "ENDPOINT" in clave):
                assert "localhost" not in valor and "127.0.0.1" not in valor, (
                    f"{nombre}.{clave} apunta a localhost: {valor}"
                )
