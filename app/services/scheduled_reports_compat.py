"""Compatibility helpers for scheduled_reports reads.

Some local SQLite databases can be behind migrations and miss newer columns
(e.g. report_type). ORM entity loads would then fail with OperationalError.
This module reads only columns that actually exist in the table.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


#: Lo que devuelve esta función cuando no puede leer nada. Ceros y no `None`:
#: un panel que pinta un contador prefiere un cero honesto a un hueco.
_RESUMEN_VACIO = {"total": 0, "active": 0, "errored": 0, "with_slack": 0, "by_frequency": {}}


def _columnas_de_tabla(db: Session, tabla: str) -> set[str]:
    """Las columnas que la tabla tiene **ahora mismo**, o un conjunto vacío.

    Se pregunta al motor en vez de confiar en el modelo porque esta función
    existe para tolerar desfases de esquema: una instalación con migraciones a
    medias tiene la tabla sin algunas columnas, y seleccionarlas sería un error
    de SQL en vez de un resumen incompleto.

    SQLite y PostgreSQL no comparten forma de preguntarlo: `PRAGMA` no existe
    en Postgres y `information_schema` es incompleto en SQLite.
    """
    try:
        if db.get_bind().dialect.name == "sqlite":
            filas = db.execute(text(f"PRAGMA table_info('{tabla}')")).fetchall()  # noqa: S608
            return {fila[1] for fila in filas}
        filas = db.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = :tabla AND table_schema = 'public'"
        ), {"tabla": tabla}).fetchall()
        return {fila[0] for fila in filas}
    except Exception:
        db.rollback()
        return set()


def summarize_scheduled_reports(db: Session) -> dict[str, Any]:
    """Agregados de `scheduled_reports`, tolerando desfases de esquema."""
    columnas = _columnas_de_tabla(db, "scheduled_reports")
    interesantes = [
        c for c in ("is_active", "last_status", "slack_webhook", "frequency")
        if c in columnas
    ]
    if not interesantes:
        # O la tabla no existe, o no tiene ninguna columna de las que se leen.
        return dict(_RESUMEN_VACIO)

    # Sólo las columnas disponibles: `SELECT *` traería las que no se usan y
    # un nombre fijo fallaría en las instalaciones que no lo tienen.
    # Revision multitenant 2026-11: el SQL a mano no pasa por el filtro de
    # tenant y contaba los informes de todas las empresas.
    sql, params = f"SELECT {', '.join(interesantes)} FROM scheduled_reports", {}  # noqa: S608
    if "organization_id" in columnas and not db.info.get("is_superadmin", True):
        sql += " WHERE organization_id = :org"
        params["org"] = db.info.get("organization_id")
    filas = db.execute(text(sql), params).fetchall()

    por_frecuencia: dict[str, int] = defaultdict(int)
    activos = con_error = con_slack = 0
    for fila in filas:
        datos = dict(fila._mapping)
        # Sin columna `is_active` se cuentan todos como activos: es lo que
        # significaba antes de que esa columna existiera.
        if bool(datos.get("is_active", 1)):
            activos += 1
        if datos.get("last_status") == "error":
            con_error += 1
        if datos.get("slack_webhook"):
            con_slack += 1
        por_frecuencia[str(datos.get("frequency") or "unknown")] += 1

    return {
        "total": len(filas),
        "active": activos,
        "errored": con_error,
        "with_slack": con_slack,
        "by_frequency": dict(por_frecuencia),
    }
