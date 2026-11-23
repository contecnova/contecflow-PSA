"""Rol de aplicación sin privilegios para RLS: lo usan setup.sh y setup.bat (22-11-2026).

Auditoría 22-11-2026 (informe 01, A1): solo `setup.sh` creaba el rol
`APP_DB_USER`; `setup.bat` y el modo Docker conectaban como el dueño del
esquema (superusuario), que se salta RLS. Esta es la lógica única para los dos
lanzadores (antes vivía dentro de `setup.sh`):

1. Si `DATABASE_URL` es Postgres, toma el dueño (`DATABASE_MIGRATIONS_URL` o la
   propia `DATABASE_URL`) y crea o actualiza el rol con `python -m app.db.rls`
   (sin superusuario ni BYPASSRLS) y las políticas.
2. Guarda en `.env` `APP_DB_USER`, `APP_DB_PASSWORD` (generada una vez),
   `DATABASE_MIGRATIONS_URL` (dueño) y `DATABASE_URL` con el rol de aplicación.

Conserva los finales de línea del `.env`. `CONTECFLOW_DB_APP_ROLE=0` lo omite.
Imprime una línea `OK …`, `SKIP …` o `FAIL …` y sale siempre con 0: quien llama
avisa y sigue (la app sigue con el dueño y el arranque lo avisa o, en
staging/production, se niega: `RLS_REQUIRED`).

    python scripts/rol_de_aplicacion.py
"""
from __future__ import annotations

import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ENV = RAIZ / ".env"
ROL_POR_DEFECTO = "contecflow_app"


def _leer(texto: str, clave: str) -> str:
    valor = ""
    for linea in texto.splitlines():
        if linea.startswith(clave + "="):
            valor = linea.split("=", 1)[1].strip()
    return valor


def _poner(texto: str, clave: str, valor: str, salto: str) -> str:
    lineas = texto.splitlines()
    for i, linea in enumerate(lineas):
        if linea.startswith(clave + "="):
            lineas[i] = f"{clave}={valor}"
            break
    else:
        lineas.append(f"{clave}={valor}")
    return salto.join(lineas) + salto


def main() -> int:
    if os.environ.get("CONTECFLOW_DB_APP_ROLE", "1").strip() == "0":
        print("SKIP CONTECFLOW_DB_APP_ROLE=0: RLS no actúa")
        return 0
    if not ENV.exists():
        print("SKIP no hay .env")
        return 0
    with open(ENV, encoding="utf-8", newline="") as f:
        texto = f.read()
    salto = "\r\n" if "\r\n" in texto else "\n"
    url = _leer(texto, "DATABASE_URL")
    if not url.startswith("postgresql"):
        print("SKIP no es Postgres")
        return 0
    dueno = _leer(texto, "DATABASE_MIGRATIONS_URL") or url
    m = re.match(r"(postgresql[^:]*://)([^:@]+):([^@]*)@(.+)$", dueno)
    if not m:
        print("SKIP URL no reconocida")
        return 0
    usuario = _leer(texto, "APP_DB_USER") or ROL_POR_DEFECTO
    clave = _leer(texto, "APP_DB_PASSWORD") or secrets.token_urlsafe(24)
    if m.group(2) == usuario:
        print("SKIP DATABASE_MIGRATIONS_URL debe ser el dueño del esquema")
        return 0
    entorno = dict(os.environ, DATABASE_URL=dueno, DATABASE_MIGRATIONS_URL=dueno,
                   APP_DB_USER=usuario, APP_DB_PASSWORD=clave)
    r = subprocess.run([sys.executable, "-m", "app.db.rls"], env=entorno, cwd=str(RAIZ),
                       capture_output=True, text=True)
    if r.returncode != 0:
        ultima = ((r.stderr or r.stdout).strip().splitlines() or ["sin salida"])[-1]
        print("FAIL " + ultima[:200])
        return 0
    for k, v in (("APP_DB_USER", usuario), ("APP_DB_PASSWORD", clave), ("DATABASE_MIGRATIONS_URL", dueno),
                 ("DATABASE_URL", f"{m.group(1)}{usuario}:{clave}@{m.group(4)}")):
        texto = _poner(texto, k, v, salto)
    with open(ENV, "w", encoding="utf-8", newline="") as f:
        f.write(texto)
    print("OK " + r.stdout.strip().replace("\n", " · "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
