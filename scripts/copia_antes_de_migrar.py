"""Copia de seguridad automática antes de migraciones destructivas (auditoría 22-11-2026, 01 M10).

Hay revisiones que borran datos sin vuelta atrás (`135_filas_sin_empresa`:
`DELETE ... WHERE organization_id IS NULL` con `downgrade: pass`; 110, 111, 146,
156, 160, 166, 173 y 185 con `drop_table` tras copiar). `setup update` las
aplicaba sobre una base real sin copia previa.

`scripts/migrar.py` (lo usan setup.bat y setup.sh) llama a `copia_si_hace_falta`
antes de `alembic upgrade head`:

- calcula las revisiones pendientes (de la actual de la base a la cabeza);
- con `MIGRATION_BACKUP_MODE=destructive` (por defecto) solo copia si alguna
  pendiente es destructiva (`drop_table`, `drop_column`, `DELETE FROM`,
  `TRUNCATE`, `DROP ...` en su `upgrade`); `always` copia siempre que haya
  pendientes; `off` nunca (decisión consciente del operador);
- SQLite: copia consistente con la API de backup de sqlite3 (sirve con la app
  arrancada y el WAL activo);
- PostgreSQL: `pg_dump -Fc` si está en el PATH (contraseña por `PGPASSWORD`, no
  en la línea de órdenes); si no está, AVISA y sigue (no se puede copiar);
- una base nueva (sin revisión) no se copia: no hay nada que perder.

Las copias van a `MIGRATION_BACKUP_DIR` (por defecto `backups/`, ignorado por
git) con fecha y revisión de origen. Contienen datos personales: mismo control
de acceso y retención que la base (docs/seguridad/entrada_y_salida.md).
Si la copia falla, la migración NO se aplica (salida 1) salvo
`MIGRATION_BACKUP_MODE=off`.
"""
from __future__ import annotations

import os
import re
import shutil
import sqlite3
import subprocess
from datetime import datetime
from typing import Optional

_DESTRUCTIVA = re.compile(
    r"\bop\.drop_table\b|\bop\.drop_column\b|\bbatch_op\.drop_column\b|DELETE\s+FROM|\bTRUNCATE\b"
    r"|\bDROP\s+(TABLE|COLUMN)\b",
    re.IGNORECASE,
)


def _upgrade_de(ruta: str) -> str:
    """El texto de `upgrade()` de una revisión (sin `downgrade`, que sí borra)."""
    with open(ruta, encoding="utf-8") as f:
        texto = f.read()
    inicio = texto.find("def upgrade")
    if inicio < 0:
        return texto
    fin = texto.find("def downgrade", inicio)
    return texto[inicio:fin if fin > 0 else None]


def revisiones_pendientes(cfg, url: str) -> tuple[Optional[str], list]:
    """(revisión actual de la base, scripts pendientes hasta la cabeza)."""
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from sqlalchemy import create_engine

    motor = create_engine(url)
    try:
        with motor.connect() as conexion:
            actual = MigrationContext.configure(conexion).get_current_revision()
    finally:
        motor.dispose()
    guion = ScriptDirectory.from_config(cfg)
    if actual is None:
        return None, []
    pendientes = list(guion.walk_revisions(base=actual, head="heads"))
    return actual, [r for r in pendientes if r.revision != actual]


def destructivas(pendientes: list) -> list:
    return [r.revision for r in pendientes if r.path and _DESTRUCTIVA.search(_upgrade_de(r.path))]


def _destino(directorio: str, actual: str, extension: str) -> str:
    os.makedirs(directorio, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d-%H%M%S")
    return os.path.join(directorio, f"antes_de_migrar_{marca}_{actual}{extension}")


def _copia_sqlite(url, directorio: str, actual: str) -> str:
    ruta = url.database
    if not ruta or ruta == ":memory:":
        raise RuntimeError("SQLite en memoria: no hay fichero que copiar")
    destino = _destino(directorio, actual, ".db")
    origen = sqlite3.connect(ruta)
    try:
        copia = sqlite3.connect(destino)
        try:
            origen.backup(copia)
        finally:
            copia.close()
    finally:
        origen.close()
    return destino


def _copia_postgres(url, directorio: str, actual: str) -> Optional[str]:
    pg_dump = shutil.which("pg_dump")
    if not pg_dump:
        print("[AVISO] Hay migraciones destructivas pendientes y no se encuentra `pg_dump` en el PATH:")
        print("[AVISO] NO se ha hecho copia de la base. Hazla a mano (scripts/backup.sh) antes de seguir")
        print("[AVISO] si la base tiene datos que importan.")
        return None
    destino = _destino(directorio, actual, ".dump")
    entorno = dict(os.environ)
    if url.password:
        entorno["PGPASSWORD"] = str(url.password)
    orden = [pg_dump, "-Fc", "-f", destino, "-h", url.host or "localhost", "-p", str(url.port or 5432)]
    if url.username:
        orden += ["-U", url.username]
    orden.append(url.database or "")
    resultado = subprocess.run(orden, env=entorno, capture_output=True, text=True, timeout=3600)  # noqa: S603
    if resultado.returncode != 0:
        try:
            os.remove(destino)
        except OSError:
            pass
        raise RuntimeError(f"pg_dump terminó con {resultado.returncode}: {(resultado.stderr or '').strip()[:500]}")
    return destino


def copia_si_hace_falta(cfg, url_texto: str, modo: str, directorio: str) -> bool:
    """Hace la copia si toca. Devuelve False si la copia era necesaria y ha fallado."""
    from sqlalchemy.engine import make_url

    modo = (modo or "destructive").strip().lower()
    if modo == "off":
        return True
    try:
        actual, pendientes = revisiones_pendientes(cfg, url_texto)
    except Exception as e:  # noqa: BLE001 — sin conexión o revisión desconocida: lo dirá Alembic
        print(f"[AVISO] No se pudo calcular qué migraciones faltan ({type(e).__name__}); sin copia previa.")
        return True
    if actual is None or not pendientes:
        return True
    peligrosas = destructivas(pendientes)
    if modo != "always" and not peligrosas:
        return True
    if peligrosas:
        print(f"[INFO] Migraciones destructivas pendientes: {', '.join(peligrosas)}")
    url = make_url(url_texto)
    try:
        if url.get_backend_name() == "sqlite":
            destino = _copia_sqlite(url, directorio, actual)
        elif url.get_backend_name() == "postgresql":
            destino = _copia_postgres(url, directorio, actual)
        else:
            print(f"[AVISO] Sin copia automática para {url.get_backend_name()}: hazla a mano antes de seguir.")
            return True
    except Exception as e:  # noqa: BLE001 — se informa y se para
        print(f"[ERROR] No se ha podido hacer la copia previa a las migraciones: {type(e).__name__}: {e}")
        print("[ERROR] No se aplica ninguna migración. Arregla la copia o, sabiendo lo que haces,")
        print("[ERROR] fija MIGRATION_BACKUP_MODE=off en .env y repite.")
        return False
    if destino:
        print(f"[OK] Copia de seguridad previa a migrar: {destino}")
    return True
