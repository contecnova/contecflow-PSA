"""Aislamiento entre empresas en la propia base de datos (Postgres RLS).

Revisión 2026-11. Medido en la base de un despliegue: la aplicación conectaba
como `contecflow`, superusuario con BYPASSRLS, y había 0 políticas. Todo el
aislamiento descansaba en el filtro del ORM (`TenantSession`): lo que no pasara
por él —SQL a mano, operaciones masivas— no tenía nada debajo.

Tres piezas:

1. **Políticas** (`aplicar`): una por tabla con `organization_id` (u `org_id`),
   generadas desde los modelos con la MISMA semántica que el filtro del ORM:
   estricta; con las filas globales (NULL) para los que declaran
   `_tenant_filter_include_global`; y por ficha o pertenencia para los usuarios
   (`_tenant_filter_members`). Las aplica cada `alembic upgrade` (env.py), así
   que una tabla nueva no se queda sin política.
2. **Contexto** (`sincronizar`): antes de cada sentencia y de cada flush, la
   sesión pone `app.tenant` (local a la transacción) con su empresa, o vacío
   cuando el ORM tampoco filtra (superadmin, trabajos de fondo,
   `sin_filtro_de_tenant`). Vacío = sin restricción: la base no esconde nada
   que el ORM enseñe, solo lo que se le escape.
3. **Rol de aplicación** (`crear_rol`): sin superusuario ni BYPASSRLS. Sin él,
   las políticas existen pero no actúan (el dueño de la tabla se las salta), y
   el arranque lo avisa: `estado()` lo dice y Admin lo enseña.

Las inserciones con `organization_id` vacío se admiten (WITH CHECK): una fila
sin empresa no filtra datos de nadie, y hay registros globales legítimos.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

POLITICA = "aislamiento_por_empresa"
GUC = "app.tenant"
_TENANT = f"NULLIF(current_setting('{GUC}', true), '')"


def _modelos_por_tabla() -> dict:
    from app.db.base import Base
    salida = {}
    for mapper in Base.registry.mappers:
        tabla = getattr(mapper.class_, "__table__", None)
        if tabla is not None and tabla.name not in salida:
            salida[tabla.name] = mapper.class_
    return salida


def politicas() -> dict[str, tuple[str, str]]:
    """{tabla: (USING, WITH CHECK)} para cada tabla con columna de empresa."""
    from app.db.base import Base
    modelos = _modelos_por_tabla()
    salida = {}
    for tabla in Base.metadata.sorted_tables:
        col = "organization_id" if "organization_id" in tabla.c else ("org_id" if "org_id" in tabla.c else None)
        if col is None:
            continue
        modelo = modelos.get(tabla.name)
        libre = f"{_TENANT} IS NULL"
        propio = f"{col}::text = {_TENANT}"
        usar = f"{libre} OR {propio}"
        if modelo is not None and getattr(modelo, "_tenant_filter_include_global", False):
            usar += f" OR {col} IS NULL"
        if modelo is not None and getattr(modelo, "_tenant_filter_members", False):
            usar += (f" OR id IN (SELECT user_id FROM user_organization_memberships "
                     f"WHERE organization_id::text = {_TENANT})")
        salida[tabla.name] = (usar, f"{libre} OR {col} IS NULL OR {propio}")
    return salida


def aplicar(conexion) -> int:
    """Crea o rehace las políticas. Idempotente; solo en Postgres. Devuelve cuántas."""
    if conexion.dialect.name != "postgresql":
        return 0
    # Lo que hay de verdad en la base (tras un downgrade una tabla puede no
    # tener aún la columna de empresa).
    columnas: dict[str, set] = {}
    for t, c in conexion.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND column_name IN ('organization_id', 'org_id', 'id')")):
        columnas.setdefault(t, set()).add(c)
    n = 0
    for tabla, (usar, comprobar) in politicas().items():
        if not columnas.get(tabla, set()) & {"organization_id", "org_id"}:
            continue
        conexion.execute(text(f'ALTER TABLE "{tabla}" ENABLE ROW LEVEL SECURITY'))
        conexion.execute(text(f'DROP POLICY IF EXISTS {POLITICA} ON "{tabla}"'))
        conexion.execute(text(f'CREATE POLICY {POLITICA} ON "{tabla}" USING ({usar}) WITH CHECK ({comprobar})'))
        n += 1
    return n


def crear_rol(conexion, nombre: str, clave: str) -> None:
    """Rol de la aplicación: puede leer y escribir datos, no saltarse RLS ni cambiar el esquema."""
    import re
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", nombre):
        raise ValueError("nombre de rol no válido")
    existe = conexion.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :n"), {"n": nombre}).first()
    accion = "ALTER" if existe else "CREATE"
    conexion.execute(text(f"{accion} ROLE {nombre} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE "
                          f"PASSWORD :clave"), {"clave": clave})
    base = conexion.execute(text("SELECT current_database()")).scalar()
    dueno = conexion.execute(text("SELECT current_user")).scalar()
    conexion.execute(text(f'GRANT CONNECT ON DATABASE "{base}" TO {nombre}'))
    conexion.execute(text(f"GRANT USAGE ON SCHEMA public TO {nombre}"))
    conexion.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {nombre}"))
    conexion.execute(text(f"GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO {nombre}"))
    # Lo que creen las migraciones futuras (como el dueño) también le llega.
    conexion.execute(text(f'ALTER DEFAULT PRIVILEGES FOR ROLE "{dueno}" IN SCHEMA public '
                          f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {nombre}"))
    conexion.execute(text(f'ALTER DEFAULT PRIVILEGES FOR ROLE "{dueno}" IN SCHEMA public '
                          f"GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {nombre}"))


def estado(conexion) -> dict:
    """¿Está armada la red? Se mide el rol, no solo las políticas."""
    if conexion.dialect.name != "postgresql":
        return {"armed": False, "reason": "no es Postgres"}
    rol, superusuario, salta = conexion.execute(text(
        "SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")).first()
    con_rls = conexion.execute(text(
        "SELECT count(*) FROM pg_class WHERE relkind = 'r' AND relrowsecurity "
        "AND relnamespace = current_schema()::regnamespace")).scalar()
    esperadas = len(politicas())
    armada = not superusuario and not salta and con_rls >= esperadas
    motivo = None
    if superusuario or salta:
        motivo = f"la aplicación conecta como {rol}, que se salta RLS (superusuario o BYPASSRLS)"
    elif con_rls < esperadas:
        motivo = f"{con_rls} tablas con RLS de {esperadas}: falta `alembic upgrade head`"
    return {"armed": armada, "role": rol, "tables_with_rls": int(con_rls), "tables_expected": esperadas,
            "reason": motivo}


# ── Contexto por transacción ────────────────────────────────────────────────

def tenant_de(info: dict) -> str:
    """Lo mismo que decide el filtro del ORM: empresa, o vacío si no filtra."""
    if info.get("bypass_tenant_filter") or info.get("is_superadmin") is not False:
        return ""
    return str(info.get("organization_id") or "")


def sincronizar(session, *, libre: bool = False) -> None:
    """Pone `app.tenant` en la conexión de la transacción actual si ha cambiado.

    `libre`: esta sentencia no se filtra (la recarga de un objeto que ya está en
    la sesión: el ORM tampoco la filtra, y es lo que deja releer una fila que
    uno mismo acaba de mover a otra empresa).
    """
    try:
        if session.get_bind().dialect.name != "postgresql":
            return
    except Exception:
        return
    deseado = "" if libre else tenant_de(session.info)
    conexion = session.connection()
    marca = (id(conexion.connection.dbapi_connection), id(session.get_transaction()))
    if session.info.get("_rls_marca") == (marca, deseado):
        return
    conexion.exec_driver_sql(f"SELECT set_config('{GUC}', %(t)s, true)", {"t": deseado})
    session.info["_rls_marca"] = (marca, deseado)


def main() -> int:
    """`python -m app.db.rls`: crea o actualiza el rol de aplicación y aplica las políticas.

    Lee `APP_DB_USER` y `APP_DB_PASSWORD`; conecta con `DATABASE_MIGRATIONS_URL`
    (el dueño del esquema) o, si no está, con `DATABASE_URL`. Sin rol definido
    solo aplica las políticas.
    """
    import os
    from sqlalchemy import create_engine
    from app.core.config import settings
    import app.models  # noqa: F401  (registra los modelos para `politicas`)
    url = settings.DATABASE_MIGRATIONS_URL or settings.DATABASE_URL
    if not url.startswith("postgresql"):
        print("rls: no es Postgres; nada que hacer")
        return 0
    motor = create_engine(url)
    with motor.begin() as conexion:
        usuario, clave = os.getenv("APP_DB_USER", "").strip(), os.getenv("APP_DB_PASSWORD", "").strip()
        if usuario and clave:
            crear_rol(conexion, usuario, clave)
            print(f"rls: rol {usuario} listo (sin superusuario ni BYPASSRLS)")
        print(f"rls: {aplicar(conexion)} tablas con política")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
