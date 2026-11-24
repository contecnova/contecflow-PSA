"""Decide cómo corren las tareas en segundo plano en local (23-11-2026).

Lo llaman setup.bat y setup.sh antes de arrancar. Antes los dos lanzaban SIEMPRE
el worker y el beat de Celery y la API con `ENABLE_APSCHEDULER=0`; setup.bat
además no escribía `REDIS_URL`. Sin Redis, worker y beat morían al arrancar y
ninguna tarea programada corría (SLA, buzón, avisos...), sin que nada lo dijera.

Ahora:

* Si hay un Redis que responde (el de `REDIS_URL` del .env, uno local en 6379 o
  el de Docker en `CF_REDIS_PORT`, 6381 por defecto, con `REDIS_PASSWORD`), se
  usa Celery. Si el .env no tenía `REDIS_URL`, se escribe el que respondió.
* Si no, modo integrado: sin worker ni beat; la API arranca con APScheduler
  (`ENABLE_APSCHEDULER=1`, `ENABLE_CELERY_BEAT=0`), que replica entero el
  calendario de beat y ejecuta las tareas en su propio proceso.

`CONTECFLOW_TAREAS=celery|integrado|auto` (auto por defecto) fuerza el modo.

Salida (una línea): `celery <url sin contraseña>` o `integrado <motivo>`.
Nunca imprime contraseñas. Sale siempre con 0: el modo integrado no es un error.
"""
from __future__ import annotations

import os
import sys
from urllib.parse import urlsplit, urlunsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def leer_env(ruta: str) -> dict[str, str]:
    valores: dict[str, str] = {}
    if not os.path.exists(ruta):
        return valores
    with open(ruta, encoding="utf-8", errors="replace") as f:
        for linea in f.read().splitlines():
            if not linea or linea.lstrip().startswith("#") or "=" not in linea:
                continue
            clave, valor = linea.split("=", 1)
            valores[clave.strip()] = valor.strip().strip('"').strip("'")
    return valores


def poner_en_env(ruta: str, clave: str, valor: str) -> None:
    """Añade o reemplaza `clave=valor` conservando los finales de línea del fichero."""
    if os.path.exists(ruta):
        with open(ruta, "rb") as f:
            datos = f.read().decode("utf-8", errors="replace")
    else:
        datos = ""
    fin = "\r\n" if "\r\n" in datos else "\n"
    lineas = datos.splitlines()
    for i, linea in enumerate(lineas):
        if linea.startswith(f"{clave}="):
            lineas[i] = f"{clave}={valor}"
            break
    else:
        lineas.append(f"{clave}={valor}")
    with open(ruta, "wb") as f:
        f.write((fin.join(lineas) + fin).encode("utf-8"))


def sin_contrasena(url: str) -> str:
    p = urlsplit(url)
    if not p.password:
        return url
    host = p.hostname or ""
    if p.port:
        host = f"{host}:{p.port}"
    return urlunsplit((p.scheme, f"{p.username or ''}:***@{host}", p.path, p.query, p.fragment))


def responde(url: str, contrasena: str) -> bool:
    try:
        import redis  # requirements.txt
    except ImportError:
        return False
    try:
        kwargs = {"socket_connect_timeout": 1, "socket_timeout": 1}
        if contrasena and not urlsplit(url).password:
            kwargs["password"] = contrasena
        return bool(redis.Redis.from_url(url, **kwargs).ping())
    except Exception:  # noqa: BLE001 - cualquier fallo es «no hay Redis»
        return False


def candidatos(env: dict[str, str]) -> list[str]:
    propios = [env["REDIS_URL"]] if env.get("REDIS_URL") else []
    puerto_docker = os.environ.get("CF_REDIS_PORT") or "6381"
    resto = ["redis://127.0.0.1:6379/0", f"redis://127.0.0.1:{puerto_docker}/0"]
    return propios + [u for u in resto if u not in propios]


def decidir(ruta_env: str = ".env") -> str:
    forzado = (os.environ.get("CONTECFLOW_TAREAS") or "auto").strip().lower()
    if forzado == "integrado":
        return "integrado forzado con CONTECFLOW_TAREAS=integrado"
    env = leer_env(ruta_env)
    contrasena = env.get("REDIS_PASSWORD", "")
    for url in candidatos(env):
        if responde(url, contrasena):
            if not env.get("REDIS_URL"):
                poner_en_env(ruta_env, "REDIS_URL", url)
            return f"celery {sin_contrasena(url)}"
    if forzado == "celery":
        return "integrado CONTECFLOW_TAREAS=celery pero ningun Redis responde"
    if env.get("REDIS_URL"):
        return f"integrado REDIS_URL={sin_contrasena(env['REDIS_URL'])} no responde"
    return "integrado no hay Redis en 6379 ni en Docker"


if __name__ == "__main__":
    print(decidir(sys.argv[1] if len(sys.argv) > 1 else ".env"))
