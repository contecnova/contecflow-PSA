"""Tests contra un PostgreSQL efímero en Docker (24-11-2026).

La suite corre sobre SQLite en memoria (`tests/conftest.py`), y las pruebas que
solo tienen sentido en Postgres se saltan si no se les da una base:

    tests/test_rls_postgres.py            RLS_TEST_OWNER_URL + RLS_TEST_APP_URL
    tests/test_kb_vectores_pgvector.py    KB_PGVECTOR_URL
    tests/test_alembic_schema_parity.py   PARITY_POSTGRES_URL

Este script les da una de usar y tirar, sin tocar nada del usuario:

1. Comprueba que Docker responde; si no, lo dice y sale con 2.
2. Arranca `pgvector/pgvector:pg16` con un nombre único
   (`contecflow-test-pg-<hex>`), publicado solo en 127.0.0.1 en un puerto libre
   y con los datos en un tmpfs: no crea ni usa volúmenes con nombre, y nunca los
   `contecflow_*` (ni `docker compose`, ni `down -v`).
3. Crea dos bases:
   - `contecflow_rls`: `alembic upgrade head` (que aplica las políticas RLS) y
     el rol de aplicación `contecflow_app_test` con `python -m app.db.rls`
     (NOSUPERUSER NOBYPASSRLS, el mismo camino que `scripts/rol_de_aplicacion.py`),
     para que RLS actúe de verdad;
   - `contecflow_kb`: vacía; la prueba de pgvector la rehace entera
     (`DROP SCHEMA public CASCADE`), por eso va aparte.
   La paridad de Alembic crea y borra su propia base en el servidor.
4. Ejecuta pytest con esas variables. Sin argumentos, la suite entera
   (`tests/ -n auto --dist loadfile`); con argumentos, se pasan tal cual a pytest:

       python scripts/test_postgres.py tests/test_rls_postgres.py -x

   `--dist loadfile`: las pruebas de un mismo fichero van al mismo worker. Las
   de RLS siembran ids fijos y las de pgvector rehacen el esquema de su base;
   repartidas entre workers se pisarían.
5. Para y borra el contenedor al terminar, también si algo falla o con Ctrl+C.

`--sin-migrar` se salta el paso de Alembic (unos 2 min) cuando no se van a
correr las pruebas de RLS. `--imagen` cambia la imagen (debe traer pgvector).

Sale con el código de pytest (o 2 si no hay Docker, 3 si la base no arranca).
"""
from __future__ import annotations

import argparse
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
IMAGEN = "pgvector/pgvector:pg16"
ROL_APP = "contecflow_app_test"
BASE_RLS = "contecflow_rls"
BASE_KB = "contecflow_kb"
PYTEST_POR_DEFECTO = ["tests/", "-n", "auto", "--dist", "loadfile", "--tb=short"]


def _docker(*args: str, check: bool = True, capturar: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], check=check, capture_output=capturar, text=True)


def docker_disponible() -> str | None:
    """None si Docker responde; si no, el motivo."""
    try:
        r = _docker("info", "--format", "{{.ServerVersion}}", check=False)
    except FileNotFoundError:
        return "no se encuentra el comando `docker` en el PATH"
    if r.returncode != 0:
        return "el demonio de Docker no responde (¿Docker Desktop arrancado?): " + (r.stderr or r.stdout).strip()[:300]
    return None


def puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def esperar_postgres(url: str, segundos: int = 90) -> None:
    """Espera a que acepte conexiones TCP. El servidor provisional de `initdb`
    de la imagen solo escucha en el socket local, así que una conexión por TCP
    que funciona es ya la del servidor definitivo."""
    from sqlalchemy import create_engine, text

    motor = create_engine(url, pool_pre_ping=True)
    limite = time.monotonic() + segundos
    ultimo = None
    try:
        while time.monotonic() < limite:
            try:
                with motor.connect() as c:
                    c.execute(text("SELECT 1"))
                return
            except Exception as exc:  # noqa: BLE001 — aún arrancando
                ultimo = exc
                time.sleep(1)
    finally:
        motor.dispose()
    raise RuntimeError(f"PostgreSQL no responde tras {segundos} s: {ultimo}")


def _entorno_app(url_dueno: str, **extra: str) -> dict:
    env = dict(os.environ)
    env.update(
        DATABASE_URL=url_dueno,
        DATABASE_MIGRATIONS_URL=url_dueno,
        TESTING="1",
        PYTHONUTF8="1",
    )
    env.setdefault("SECRET_KEY", "test-postgres-secret-" + secrets.token_hex(16))
    env.setdefault("CLIENT_PORTAL_SECRET", "test-postgres-portal-" + secrets.token_hex(16))
    env.update(extra)
    return env


def preparar_bases(servidor: str, *, migrar: bool) -> dict[str, str]:
    """Crea las bases y el rol; devuelve las variables para pytest."""
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url

    base = make_url(servidor)
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        for nombre in (BASE_RLS, BASE_KB):
            c.exec_driver_sql(f'CREATE DATABASE "{nombre}"')
    admin.dispose()

    url_rls = base.set(database=BASE_RLS).render_as_string(hide_password=False)
    url_kb = base.set(database=BASE_KB).render_as_string(hide_password=False)
    clave_app = secrets.token_urlsafe(18)
    url_app = base.set(database=BASE_RLS, username=ROL_APP, password=clave_app).render_as_string(hide_password=False)

    variables = {
        "PARITY_POSTGRES_URL": servidor,
        "KB_PGVECTOR_URL": url_kb,
    }
    if not migrar:
        print("[test-postgres] --sin-migrar: las pruebas de RLS se saltarán")
        return variables

    print("[test-postgres] alembic upgrade head sobre la base de RLS (unos 2 min)...", flush=True)
    t0 = time.monotonic()
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=RAIZ,
                       env=_entorno_app(url_rls), capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"alembic upgrade head falló:\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")
    print(f"[test-postgres] migrada en {time.monotonic() - t0:.0f} s")

    # Rol de aplicación sin superusuario ni BYPASSRLS, y políticas (idempotente).
    r = subprocess.run([sys.executable, "-m", "app.db.rls"], cwd=RAIZ,
                       env=_entorno_app(url_rls, APP_DB_USER=ROL_APP, APP_DB_PASSWORD=clave_app),
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"python -m app.db.rls falló:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    print("[test-postgres] " + " | ".join(l for l in r.stdout.splitlines() if l.strip()))

    variables.update(RLS_TEST_OWNER_URL=url_rls, RLS_TEST_APP_URL=url_app)
    return variables


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        allow_abbrev=False,  # que una opción de pytest no se tome por abreviatura de las nuestras
        description="Ejecuta pytest contra un PostgreSQL efímero en Docker.",
        epilog="Lo que no reconoce se pasa a pytest. Sin nada: " + " ".join(PYTEST_POR_DEFECTO),
    )
    p.add_argument("--sin-migrar", action="store_true", help="no migra la base de RLS (sus pruebas se saltan)")
    p.add_argument("--imagen", default=os.environ.get("CONTECFLOW_TEST_PG_IMAGE", IMAGEN),
                   help=f"imagen de PostgreSQL con pgvector (por defecto {IMAGEN})")
    a, resto = p.parse_known_args(argv)
    args_pytest = resto or PYTEST_POR_DEFECTO

    motivo = docker_disponible()
    if motivo:
        print(f"[test-postgres] ERROR: Docker no está disponible: {motivo}", file=sys.stderr)
        print("[test-postgres] Arranca Docker y vuelve a lanzarlo. No se ha ejecutado ningún test.", file=sys.stderr)
        return 2

    nombre = "contecflow-test-pg-" + secrets.token_hex(4)
    clave = secrets.token_urlsafe(18)
    puerto = puerto_libre()
    print(f"[test-postgres] contenedor {nombre} ({a.imagen}) en 127.0.0.1:{puerto}, datos en tmpfs", flush=True)
    try:
        _docker("run", "-d", "--rm", "--name", nombre,
                "--label", "contecflow.test-postgres=1",
                "-e", "POSTGRES_USER=postgres", "-e", f"POSTGRES_PASSWORD={clave}",
                "-e", "POSTGRES_DB=postgres",
                "-p", f"127.0.0.1:{puerto}:5432",
                "--tmpfs", "/var/lib/postgresql/data:rw",
                a.imagen,
                capturar=False)
    except subprocess.CalledProcessError as exc:
        print(f"[test-postgres] ERROR: no se pudo arrancar el contenedor ({exc})", file=sys.stderr)
        _docker("rm", "-f", "-v", nombre, check=False)
        return 3

    try:
        servidor = f"postgresql://postgres:{clave}@127.0.0.1:{puerto}/postgres"
        try:
            esperar_postgres(servidor)
            variables = preparar_bases(servidor, migrar=not a.sin_migrar)
        except Exception as exc:  # noqa: BLE001
            print(f"[test-postgres] ERROR preparando la base: {exc}", file=sys.stderr)
            return 3

        env = dict(os.environ)
        env.update(variables)
        env["PYTHONUTF8"] = "1"
        # La suite usa su propio SQLite (tests/conftest.py): un DATABASE_URL de
        # fuera no debe llegarle.
        env.pop("DATABASE_URL", None)
        env.pop("DATABASE_MIGRATIONS_URL", None)
        print("[test-postgres] variables: " + ", ".join(sorted(variables)), flush=True)
        print("[test-postgres] pytest " + " ".join(args_pytest), flush=True)
        return subprocess.run([sys.executable, "-m", "pytest", *args_pytest], cwd=RAIZ, env=env).returncode
    except KeyboardInterrupt:
        print("\n[test-postgres] interrumpido", file=sys.stderr)
        return 130
    finally:
        # Solo el contenedor de esta ejecución, por su nombre único; -v borra
        # sus volúmenes anónimos (con tmpfs no debería haberlos).
        r = _docker("rm", "-f", "-v", nombre, check=False)
        estado = "borrado" if r.returncode == 0 else f"no se pudo borrar: {(r.stderr or '').strip()}"
        print(f"[test-postgres] contenedor {nombre} {estado}")


if __name__ == "__main__":
    sys.exit(main())
