"""Paridad columna a columna entre un PostgreSQL migrado y los modelos.

Segunda auditoria 2026-11 (#5). Compara con
`alembic.autogenerate.compare_metadata` (tablas, columnas, tipos, nulabilidad,
valores por defecto del servidor, indices, unicos y claves ajenas) y comprueba
aparte los enums nativos, que Alembic no compara por valores.

Cada diferencia se clasifica en **real** o **ruido**. El ruido no se admite por
tipo de diferencia (eso tapaba cualquier indice que faltase), sino uno a uno y
con su motivo:

* `remove_index` de los indices que solo existen en PostgreSQL y no se pueden
  declarar en el modelo de forma portable: trigramas GIN (083), unicos
  parciales `WHERE is_active` (2f165b37fe82) y el unico de expresion de la
  cadena de auditoria (137). Ver `INDICES_SOLO_POSTGRES`.
* `modify_default` cuando la base tiene un `server_default` que el modelo no
  declara y su valor es **el mismo** que el `default=` de Python del modelo: la
  revision lo puso para rellenar las filas que ya existian al anadir una
  columna NOT NULL. El ORM siempre envia el valor, asi que no cambia nada. Si
  el valor no coincide, es real.
* `remove_column` de `sd_kb_articles.embedding_vec` (pgvector, fuera del modelo
  a proposito: ver app/services/service_desk/kb_vectores.py).
* Tablas de modelos de test (prefijo `_test_`).

Uso (lo rapido es comparar una base ya migrada, ~35 s; migrar desde cero son
~2 min mas):

    python scripts/paridad_postgres.py --url postgresql://u:p@host:5432/base
    python scripts/paridad_postgres.py --servidor postgresql://u:p@host:5432/postgres --migrar

Sale con 1 si hay diferencias reales. El test
`tests/test_alembic_schema_parity.py::test_alembic_upgrade_head_sobre_postgres_coincide_con_los_modelos`
usa este mismo modulo.
"""
from __future__ import annotations

import argparse
import enum
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

PREFIJO_MODELOS_DE_TEST = "_test_"

#: Indices que crean las revisiones solo en PostgreSQL y que el modelo no puede
#: declarar sin romper SQLite (operador GIN, predicado parcial o expresion).
INDICES_SOLO_POSTGRES = {
    # 083: busqueda por trigramas (gin_trgm_ops)
    "idx_clients_contact_email_trgm": "083 trigramas",
    "idx_clients_name_trgm": "083 trigramas",
    "idx_clients_short_name_trgm": "083 trigramas",
    "idx_projects_name_trgm": "083 trigramas",
    "idx_tasks_title_trgm": "083 trigramas",
    "idx_tickets_number_trgm": "083 trigramas",
    "idx_tickets_title_trgm": "083 trigramas",
    "idx_users_email_trgm": "083 trigramas",
    "idx_users_full_name_trgm": "083 trigramas",
    "idx_users_username_trgm": "083 trigramas",
    # 2f165b37fe82 / 125: unicos parciales sobre las filas activas
    "uq_department_name_active": "unico parcial WHERE is_active",
    "uq_project_status_value_active": "unico parcial WHERE is_active",
    "uq_project_type_value_active": "unico parcial WHERE is_active",
    "uq_task_status_value_active": "unico parcial WHERE is_active",
    # 137: unico de expresion COALESCE(organization_id, ''), seq
    "ux_audit_logs_cadena": "137 cadena de auditoria",
}

#: Columnas que existen en la base y no en el modelo, a proposito.
COLUMNAS_FUERA_DEL_MODELO = {("sd_kb_articles", "embedding_vec")}

#: `'pending'::character varying`, `'draft'::review360campaignstatus`, `'0'::double precision`
_CAST = re.compile(r"^\(?(.*?)\)?::[\w ]+(\[\])?$")


def _texto_default(clausula) -> str | None:
    if clausula is None:
        return None
    arg = getattr(clausula, "arg", clausula)
    return str(getattr(arg, "text", arg))


def _normaliza_bd(texto: str) -> str:
    m = _CAST.match(texto.strip())
    valor = m.group(1) if m else texto.strip()
    if len(valor) >= 2 and valor[0] == valor[-1] == "'":
        valor = valor[1:-1].replace("''", "'")
    return valor


def _normaliza_python(valor) -> str | None:
    if isinstance(valor, enum.Enum):
        valor = valor.value
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, (int, float, str)):
        return str(valor)
    return None


def _mismo_valor(bd: str, py: str) -> bool:
    if bd == py:
        return True
    try:
        return float(bd) == float(py)
    except ValueError:
        return False


def _es_ruido(d, metadata) -> str | None:
    """Motivo por el que la diferencia no cambia ningun resultado, o None."""
    x = d[0] if isinstance(d, list) else d
    tipo = x[0]
    if tipo in ("add_table", "remove_table") and x[1].name.startswith(PREFIJO_MODELOS_DE_TEST):
        return "modelo de test"
    if tipo == "remove_index" and x[1].name in INDICES_SOLO_POSTGRES:
        return INDICES_SOLO_POSTGRES[x[1].name]
    if tipo == "remove_column" and (x[2], x[3].name) in COLUMNAS_FUERA_DEL_MODELO:
        return "columna fuera del modelo a proposito"
    if tipo == "modify_default":
        _, _schema, tabla, columna, _info, en_bd, en_modelo = x
        if en_modelo is not None or en_bd is None:
            return None
        col = metadata.tables[tabla].c[columna]
        if col.default is None or not getattr(col.default, "is_scalar", False):
            return None
        py = _normaliza_python(col.default.arg)
        bd = _normaliza_bd(_texto_default(en_bd))
        if py is not None and _mismo_valor(bd, py):
            return "server_default de relleno igual al default del modelo"
    return None


def _diferencias_de_enum(conn, metadata) -> list[str]:
    from sqlalchemy import Enum, text

    tipo_de = {
        (t, c): u for t, c, u in conn.execute(text(
            "SELECT table_name, column_name, udt_name FROM information_schema.columns "
            "WHERE table_schema = current_schema()"
        ))
    }
    valores: dict[str, set[str]] = {}
    for nombre, valor in conn.execute(text(
        "SELECT t.typname, e.enumlabel FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid"
    )):
        valores.setdefault(nombre, set()).add(valor)

    malas, recorridas = [], 0
    for tabla in metadata.sorted_tables:
        if tabla.name.startswith(PREFIJO_MODELOS_DE_TEST):
            continue
        for col in tabla.columns:
            if not (isinstance(col.type, Enum) and col.type.native_enum):
                continue
            recorridas += 1
            tipo = tipo_de.get((tabla.name, col.name))
            faltan = set(col.type.enums) - valores.get(tipo, set())
            if tipo != col.type.name or faltan:
                malas.append(f"{tabla.name}.{col.name}: base={tipo} modelo={col.type.name} faltan={sorted(faltan)}")
    if recorridas <= 100:
        malas.append(f"solo se recorrieron {recorridas} columnas enum: la comprobacion no esta mirando")
    return malas


def comparar(url: str) -> dict:
    """Compara una base PostgreSQL ya migrada con `Base.metadata`."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from sqlalchemy import create_engine

    from app.db.base import Base
    import app.models  # noqa: F401 — registra todos los modelos

    eng = create_engine(url)
    try:
        with eng.connect() as conn:
            ctx = MigrationContext.configure(
                conn, opts={"compare_type": True, "compare_server_default": True})
            diffs = compare_metadata(ctx, Base.metadata)
            enums = _diferencias_de_enum(conn, Base.metadata)
    finally:
        eng.dispose()

    reales, ruido = [], {}
    for d in diffs:
        motivo = _es_ruido(d, Base.metadata)
        if motivo is None:
            reales.append(d)
        else:
            ruido[motivo] = ruido.get(motivo, 0) + 1
    return {"total": len(diffs), "reales": reales, "ruido": ruido, "enums": enums}


def _entorno(url: str) -> dict:
    env = dict(os.environ)
    env["DATABASE_URL"] = url
    env["DATABASE_MIGRATIONS_URL"] = url
    env.setdefault("SECRET_KEY", "parity-test-secret-2f9c41ab7de6035849bc12ef")
    env.setdefault("CLIENT_PORTAL_SECRET", "parity-test-portal-8a13cd52be97640f2e1b")
    env["TESTING"] = "1"
    return env


def migrar_base_nueva(servidor: str):
    """Crea una base vacia en `servidor`, corre `alembic upgrade head` y devuelve
    (url, borrar). `borrar()` elimina la base."""
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url

    nombre = f"parity_{uuid.uuid4().hex[:12]}"
    admin = create_engine(make_url(servidor).set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.exec_driver_sql(f'CREATE DATABASE "{nombre}"')

    def borrar() -> None:
        with admin.connect() as c:
            c.exec_driver_sql(f'DROP DATABASE IF EXISTS "{nombre}" WITH (FORCE)')
        admin.dispose()

    url = make_url(servidor).set(database=nombre).render_as_string(hide_password=False)
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO, env=_entorno(url), capture_output=True, text=True, timeout=900,
    )
    if proc.returncode != 0:
        borrar()
        raise RuntimeError(
            "`alembic upgrade head` fallo sobre un PostgreSQL vacio.\n"
            f"stdout:\n{proc.stdout[-3000:]}\nstderr:\n{proc.stderr[-3000:]}")
    return url, borrar


def informe(resultado: dict) -> str:
    lineas = [f"{resultado['total']} diferencias: {len(resultado['reales'])} reales, "
              f"{sum(resultado['ruido'].values())} ruido"]
    for motivo, n in sorted(resultado["ruido"].items()):
        lineas.append(f"  ruido  {n:4d}  {motivo}")
    for d in resultado["reales"]:
        lineas.append(f"  REAL   {str(d)[:300]}")
    for e in resultado["enums"]:
        lineas.append(f"  ENUM   {e}")
    return "\n".join(lineas)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--url", help="base PostgreSQL ya migrada a head")
    g.add_argument("--servidor", help="servidor PostgreSQL donde crear una base nueva (con --migrar)")
    p.add_argument("--migrar", action="store_true", help="crear base vacia y correr alembic upgrade head")
    a = p.parse_args()
    # Antes de importar app: la configuracion valida SECRET_KEY al cargarse.
    for k, v in _entorno(a.url or a.servidor).items():
        os.environ.setdefault(k, v)

    t0 = time.monotonic()
    borrar = None
    url = a.url
    if a.servidor:
        if not a.migrar:
            p.error("--servidor requiere --migrar")
        url, borrar = migrar_base_nueva(a.servidor)
        print(f"migrada en {time.monotonic() - t0:.0f} s")
    try:
        t1 = time.monotonic()
        r = comparar(url)
        print(f"comparada en {time.monotonic() - t1:.0f} s")
    finally:
        if borrar:
            borrar()
    print(informe(r))
    return 1 if r["reales"] or r["enums"] else 0


if __name__ == "__main__":
    sys.exit(main())
