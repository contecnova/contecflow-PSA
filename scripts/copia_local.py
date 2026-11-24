"""Copias de seguridad locales: SQLite o PostgreSQL + `uploads/` (23-11-2026).

`scripts/backup.sh` y `scripts/restore.sh` solo cubren el despliegue Docker
(PostgreSQL del contenedor y volumen S3). La instalación local, la que dejan
setup.bat y setup.sh (SQLite y ficheros en `uploads/`), no tenía copia: en
Windows, ninguna forma de hacerla. Este script es la vía común:

    python scripts/copia_local.py backup                 # copia en backups/
    python scripts/copia_local.py verificar <carpeta>    # solo comprueba
    python scripts/copia_local.py restore <carpeta> [--si]

Lo llaman `setup.bat backup|restore <carpeta>` y `./setup.sh backup|restore <carpeta>`.

Qué copia
  * Base SQLite: con la API de backup de sqlite3 (copia consistente aunque la
    app esté arrancada y con WAL), y `PRAGMA integrity_check` sobre la copia.
  * Base PostgreSQL (local, no Docker): `pg_dump -Fc` (contraseña por
    `PGPASSWORD`, nunca en la línea de órdenes) y `pg_restore --list` para
    comprobarla. Para el stack Docker siguen siendo backup.sh/restore.sh.
  * `UPLOAD_DIR` (por defecto `uploads/`) en `uploads.zip`, comprobado con
    `testzip`. Si los ficheros van a S3 se avisa: eso lo copia backup.sh.
  * `MANIFIESTO` con fecha, motor, revisión de Alembic y el SHA-256 de cada
    pieza, en el mismo formato que backup.sh (`sha256sum -c` lo valida).

Restaurar
  1. Verifica la copia entera (huellas, integridad de la base y del zip). Si
     algo falla, no toca nada.
  2. Pide confirmación (escribir RESTAURAR) salvo `--si`.
  3. Hace antes una copia de lo actual (`backups/contecflow-local-...-antes-de-restaurar`).
  4. Sustituye la base (SQLite con la API de backup sobre el fichero; PostgreSQL
     con `pg_restore --clean --if-exists --no-owner`) y el contenido de
     `uploads/` (rechaza rutas que salgan de la carpeta).
  5. Vuelve a comprobar la integridad de la base restaurada.

Como restore.sh, no mira ENVIRONMENT (se restaura tras un desastre, también
en producción) pero exige confirmación explícita. Las copias contienen datos
personales: misma protección y retención que la base (BACKUP_KEEP, 14 por
defecto; `backups/` está en .gitignore). Ver README, «Copias de seguridad».
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from datetime import datetime
from typing import Optional

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIJO = "contecflow-local-"
BASE_SQLITE = "base.sqlite3"
BASE_PG = "base.dump"
FICHEROS = "uploads.zip"


class ErrorDeCopia(Exception):
    """Fallo con mensaje para el operador."""


# ── Configuración (sin importar la app: debe funcionar aunque no arranque) ───

def leer_env(ruta: str) -> dict[str, str]:
    valores: dict[str, str] = {}
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8", errors="replace") as f:
            for linea in f.read().splitlines():
                if not linea or linea.lstrip().startswith("#") or "=" not in linea:
                    continue
                clave, valor = linea.split("=", 1)
                valores[clave.strip()] = valor.strip().strip('"').strip("'")
    return valores


def ajuste(nombre: str, defecto: str = "", raiz: str = RAIZ) -> str:
    return os.environ.get(nombre) or leer_env(os.path.join(raiz, ".env")).get(nombre) or defecto


def ruta_sqlite(url: str, raiz: str = RAIZ) -> str:
    """Fichero de una URL `sqlite:///...` (relativa a la raíz del proyecto)."""
    resto = url.split("///", 1)[1] if "///" in url else ""
    resto = resto.split("?", 1)[0]
    if not resto or resto == ":memory:":
        raise ErrorDeCopia("DATABASE_URL apunta a SQLite en memoria: no hay fichero que copiar")
    return resto if os.path.isabs(resto) else os.path.normpath(os.path.join(raiz, resto))


def motor_de(url: str) -> str:
    if url.startswith("sqlite"):
        return "sqlite"
    if url.startswith("postgres"):
        return "postgresql"
    raise ErrorDeCopia(f"Motor no soportado para copia local: {url.split(':', 1)[0]}")


# ── Utilidades ───────────────────────────────────────────────────────────────

def sha256(ruta: str) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def revision_sqlite(ruta: str) -> str:
    try:
        con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
        try:
            filas = con.execute("SELECT version_num FROM alembic_version").fetchall()
        finally:
            con.close()
        return " ".join(f[0] for f in filas) or "desconocida"
    except sqlite3.Error:
        return "desconocida"


def integridad_sqlite(ruta: str) -> None:
    con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    try:
        resultado = [f[0] for f in con.execute("PRAGMA integrity_check").fetchall()]
    finally:
        con.close()
    if resultado != ["ok"]:
        raise ErrorDeCopia(f"integrity_check de {os.path.basename(ruta)}: {'; '.join(resultado[:5])}")


def copiar_sqlite(origen: str, destino: str) -> None:
    """Copia consistente con la API de backup (vale con la app arrancada y WAL)."""
    fuente = sqlite3.connect(origen)
    try:
        copia = sqlite3.connect(destino)
        try:
            fuente.backup(copia)
        finally:
            copia.close()
    finally:
        fuente.close()


def _pg_partes(url: str):
    from sqlalchemy.engine import make_url  # requirements.txt
    u = make_url(url)
    entorno = dict(os.environ)
    if u.password:
        entorno["PGPASSWORD"] = str(u.password)
    conexion = ["-h", u.host or "localhost", "-p", str(u.port or 5432)]
    if u.username:
        conexion += ["-U", u.username]
    return u, entorno, conexion


def _herramienta(nombre: str) -> str:
    ruta = shutil.which(nombre)
    if not ruta:
        raise ErrorDeCopia(f"No se encuentra `{nombre}` en el PATH (cliente de PostgreSQL). "
                           "Para el stack Docker usa scripts/backup.sh y scripts/restore.sh.")
    return ruta


def _ejecutar(orden: list[str], entorno: dict, que: str) -> None:
    r = subprocess.run(orden, env=entorno, capture_output=True, text=True, timeout=3600)  # noqa: S603
    if r.returncode != 0:
        raise ErrorDeCopia(f"{que} terminó con {r.returncode}: {(r.stderr or '').strip()[:500]}")


def zip_de_carpeta(carpeta: str, destino: str) -> int:
    n = 0
    with zipfile.ZipFile(destino, "w", compression=zipfile.ZIP_DEFLATED) as z:
        if os.path.isdir(carpeta):
            for actual, _dirs, ficheros in os.walk(carpeta):
                for nombre in sorted(ficheros):
                    completo = os.path.join(actual, nombre)
                    z.write(completo, os.path.relpath(completo, carpeta).replace(os.sep, "/"))
                    n += 1
    return n


def comprobar_zip(ruta: str) -> list[str]:
    with zipfile.ZipFile(ruta) as z:
        malo = z.testzip()
        if malo:
            raise ErrorDeCopia(f"{FICHEROS} dañado: {malo}")
        nombres = z.namelist()
    for nombre in nombres:
        limpio = os.path.normpath(nombre)
        if os.path.isabs(nombre) or limpio.startswith("..") or ":" in nombre:
            raise ErrorDeCopia(f"{FICHEROS} contiene una ruta fuera de la carpeta: {nombre}")
    return nombres


# ── Manifiesto ───────────────────────────────────────────────────────────────

def escribir_manifiesto(carpeta: str, sello: str, motor: str, revision: str, piezas: list[str]) -> None:
    lineas = [f"fecha: {sello}", f"motor: {motor}", f"alembic: {revision}"]
    lineas += [f"{sha256(os.path.join(carpeta, p))}  {p}" for p in piezas]
    with open(os.path.join(carpeta, "MANIFIESTO"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lineas) + "\n")


def leer_manifiesto(carpeta: str) -> tuple[dict[str, str], dict[str, str]]:
    ruta = os.path.join(carpeta, "MANIFIESTO")
    if not os.path.exists(ruta):
        raise ErrorDeCopia(f"No hay MANIFIESTO en {carpeta}: no es una copia de copia_local.py")
    datos: dict[str, str] = {}
    huellas: dict[str, str] = {}
    with open(ruta, encoding="utf-8") as f:
        for linea in f.read().splitlines():
            if ": " in linea and not linea[:64].isalnum():
                clave, valor = linea.split(": ", 1)
                datos[clave] = valor
            elif len(linea) > 66 and linea[64:66] == "  ":
                huellas[linea[66:]] = linea[:64]
    return datos, huellas


def resolver_carpeta(ruta: str) -> str:
    """Acepta la carpeta de la copia o su MANIFIESTO."""
    ruta = os.path.abspath(ruta)
    if os.path.isfile(ruta) and os.path.basename(ruta) == "MANIFIESTO":
        ruta = os.path.dirname(ruta)
    if not os.path.isdir(ruta):
        raise ErrorDeCopia(f"No existe la copia {ruta}")
    return ruta


# ── Órdenes ──────────────────────────────────────────────────────────────────

def hacer_copia(raiz: str = RAIZ, destino_base: Optional[str] = None, etiqueta: str = "") -> str:
    url = ajuste("DATABASE_URL", "", raiz)
    if not url:
        raise ErrorDeCopia("DATABASE_URL no está definida (.env)")
    motor = motor_de(url)
    destino_base = destino_base or ajuste("BACKUP_DIR", os.path.join(raiz, "backups"), raiz)
    if not os.path.isabs(destino_base):
        destino_base = os.path.join(raiz, destino_base)
    sello = datetime.now().strftime("%Y%m%d-%H%M%S")
    carpeta = os.path.join(destino_base, f"{PREFIJO}{sello}{etiqueta}")
    os.makedirs(carpeta, exist_ok=False)
    try:
        if motor == "sqlite":
            origen = ruta_sqlite(url, raiz)
            if not os.path.exists(origen):
                raise ErrorDeCopia(f"No existe la base {origen}")
            base = os.path.join(carpeta, BASE_SQLITE)
            copiar_sqlite(origen, base)
            integridad_sqlite(base)
            revision = revision_sqlite(base)
            pieza_base = BASE_SQLITE
        else:
            u, entorno, conexion = _pg_partes(url)
            base = os.path.join(carpeta, BASE_PG)
            _ejecutar([_herramienta("pg_dump"), "-Fc", "-f", base, *conexion, u.database or ""], entorno, "pg_dump")
            _ejecutar([_herramienta("pg_restore"), "--list", base], entorno, "pg_restore --list")
            revision = "desconocida"
            pieza_base = BASE_PG
        uploads = ajuste("UPLOAD_DIR", "uploads", raiz)
        uploads = uploads if os.path.isabs(uploads) else os.path.join(raiz, uploads)
        n = zip_de_carpeta(uploads, os.path.join(carpeta, FICHEROS))
        comprobar_zip(os.path.join(carpeta, FICHEROS))
        escribir_manifiesto(carpeta, sello, motor, revision, [pieza_base, FICHEROS])
    except BaseException:
        shutil.rmtree(carpeta, ignore_errors=True)
        raise
    if ajuste("AWS_S3_ENDPOINT_URL", "", raiz) or ajuste("AWS_S3_BUCKET", "", raiz):
        print("[AVISO] Hay almacenamiento S3 configurado: sus ficheros NO entran en esta copia "
              "(scripts/backup.sh copia el volumen S3 del stack Docker).")
    print(f"[OK] Copia en {carpeta} ({motor}, alembic {revision}, {n} ficheros de {os.path.basename(uploads)})")
    podar(destino_base, int(ajuste("BACKUP_KEEP", "14", raiz) or 14))
    return carpeta


def podar(directorio: str, conservar: int) -> None:
    if conservar <= 0 or not os.path.isdir(directorio):
        return
    copias = sorted((d for d in os.listdir(directorio)
                     if d.startswith(PREFIJO) and "antes-de-restaurar" not in d), reverse=True)
    for vieja in copias[conservar:]:
        shutil.rmtree(os.path.join(directorio, vieja), ignore_errors=True)
        print(f"  borrada la copia antigua {vieja}")


def verificar(ruta: str) -> tuple[str, dict[str, str]]:
    carpeta = resolver_carpeta(ruta)
    datos, huellas = leer_manifiesto(carpeta)
    motor = datos.get("motor", "")
    pieza_base = BASE_SQLITE if motor == "sqlite" else BASE_PG if motor == "postgresql" else ""
    if not pieza_base:
        raise ErrorDeCopia(f"MANIFIESTO sin motor conocido ({motor!r})")
    for pieza in (pieza_base, FICHEROS):
        if pieza not in huellas:
            raise ErrorDeCopia(f"MANIFIESTO sin huella de {pieza}")
        completa = os.path.join(carpeta, pieza)
        if not os.path.exists(completa):
            raise ErrorDeCopia(f"Falta {pieza} en la copia")
        if sha256(completa) != huellas[pieza]:
            raise ErrorDeCopia(f"La huella de {pieza} no coincide: la copia está dañada o alterada")
    if motor == "sqlite":
        integridad_sqlite(os.path.join(carpeta, BASE_SQLITE))
    comprobar_zip(os.path.join(carpeta, FICHEROS))
    print(f"[OK] Copia íntegra: {carpeta} ({motor}, alembic {datos.get('alembic', '?')})")
    return carpeta, datos


def restaurar(ruta: str, confirmado: bool, raiz: str = RAIZ) -> None:
    carpeta, datos = verificar(ruta)
    url = ajuste("DATABASE_URL", "", raiz)
    motor = motor_de(url) if url else ""
    if motor != datos.get("motor"):
        raise ErrorDeCopia(f"La copia es de {datos.get('motor')} y DATABASE_URL es de {motor or '(vacía)'}")
    uploads = ajuste("UPLOAD_DIR", "uploads", raiz)
    uploads = uploads if os.path.isabs(uploads) else os.path.join(raiz, uploads)
    if not confirmado:
        print(f"Se SUSTITUIRÁN la base ({motor}) y el contenido de {uploads} por los de la copia.")
        print("Antes se guardará una copia de lo actual en backups/.")
        try:
            respuesta = input("Escribe RESTAURAR para seguir: ")
        except EOFError:
            respuesta = ""
        if respuesta.strip() != "RESTAURAR":
            raise ErrorDeCopia("Cancelado: no se ha tocado nada")
    previa = hacer_copia(raiz, etiqueta="-antes-de-restaurar")
    print(f"[INFO] Copia de lo actual en {previa}")

    if motor == "sqlite":
        destino = ruta_sqlite(url, raiz)
        copiar_sqlite(os.path.join(carpeta, BASE_SQLITE), destino)
        integridad_sqlite(destino)
    else:
        u, entorno, conexion = _pg_partes(url)
        _ejecutar([_herramienta("pg_restore"), "--clean", "--if-exists", "--no-owner", *conexion,
                   "-d", u.database or "", os.path.join(carpeta, BASE_PG)], entorno, "pg_restore")

    os.makedirs(uploads, exist_ok=True)
    for nombre in os.listdir(uploads):
        if nombre == ".gitkeep":
            continue
        completo = os.path.join(uploads, nombre)
        if os.path.isdir(completo) and not os.path.islink(completo):
            shutil.rmtree(completo)
        else:
            os.remove(completo)
    with zipfile.ZipFile(os.path.join(carpeta, FICHEROS)) as z:
        z.extractall(uploads)
    print(f"[OK] Restaurada {os.path.basename(carpeta)} (alembic {datos.get('alembic', '?')}). "
          "Al arrancar, setup aplica las migraciones que falten.")


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Copias locales de Contecflow (base + uploads)")
    sub = p.add_subparsers(dest="orden", required=True)
    sub.add_parser("backup")
    v = sub.add_parser("verificar")
    v.add_argument("copia")
    r = sub.add_parser("restore")
    r.add_argument("copia")
    r.add_argument("--si", action="store_true", help="no pedir confirmación")
    a = p.parse_args(argv)
    try:
        if a.orden == "backup":
            hacer_copia()
        elif a.orden == "verificar":
            verificar(a.copia)
        else:
            restaurar(a.copia, a.si)
    except ErrorDeCopia as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1
    except (OSError, sqlite3.Error, zipfile.BadZipFile) as e:
        print(f"[ERROR] {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
