"""Registro de auditoría inmutable en la base (migración 199, 23-11-2026).

Hallazgo B.1 del informe 05 de la auditoría del 22-11-2026: la cadena HMAC +
Ed25519 (`cadena_auditoria.py`) DETECTA una fila cambiada o borrada, pero nada lo
IMPEDÍA: cualquiera con la cadena de conexión podía hacer UPDATE o DELETE sobre
`audit_logs`. Estos triggers lo niegan en Postgres (`plpgsql`) y en SQLite
(`RAISE(ABORT)`), con tres excepciones medidas:

1. `user_id` puede pasar a NULL: la clave ajena es `ON DELETE SET NULL` (borrar
   un usuario no puede fallar por su rastro) y `user_id` no entra en la huella.
2. Las filas sin `seq` se pueden encadenar (`encadenar_existentes`, migración
   137): solo una vez, porque una fila con `seq` ya no se toca.
3. La purga de una empresa tras su cuarentena (`baja_de_empresa_service.purgar`)
   borra su registro con un permiso de `audit_log_purge_permits` abierto en la
   misma transacción (`abrir_permiso_de_purga` / `cerrar_permiso_de_purga`).

Los triggers se instalan con la migración (`instalar(conexion)`), no con
`create_all`: la suite de pruebas vacía las tablas entre pruebas y la prueba de
la inmutabilidad los instala en su propia base.
"""
from __future__ import annotations

from sqlalchemy import text

#: Columnas que no pueden cambiar en una fila ya encadenada (todas menos `user_id`).
COLUMNAS_PROTEGIDAS = (
    "id", "organization_id", "user_name", "ip_address", "user_agent", "action", "resource",
    "resource_id", "resource_name", "old_values", "new_values", "metadata", "created_at",
    "seq", "prev_hash", "entry_hash", "chain_key_id",
)

_ERROR = "audit_logs es de solo anadir: UPDATE y DELETE no estan permitidos (docs/seguridad/politicas_de_cuenta.md)"


def _sqlite(conexion) -> list[str]:
    cambia = " OR ".join(f'NEW."{c}" IS NOT OLD."{c}"' for c in COLUMNAS_PROTEGIDAS)
    return [
        "DROP TRIGGER IF EXISTS audit_logs_no_update",
        "DROP TRIGGER IF EXISTS audit_logs_no_delete",
        f"""CREATE TRIGGER audit_logs_no_update BEFORE UPDATE ON audit_logs
            FOR EACH ROW WHEN OLD.seq IS NOT NULL AND ({cambia})
            BEGIN SELECT RAISE(ABORT, '{_ERROR}'); END""",
        f"""CREATE TRIGGER audit_logs_no_delete BEFORE DELETE ON audit_logs
            FOR EACH ROW WHEN NOT EXISTS (
                SELECT 1 FROM audit_log_purge_permits p
                WHERE p.active = 1 AND p.organization_id = COALESCE(OLD.organization_id, ''))
            BEGIN SELECT RAISE(ABORT, '{_ERROR}'); END""",
    ]


def _postgres(conexion) -> list[str]:
    cambia = " OR ".join(f'NEW."{c}" IS DISTINCT FROM OLD."{c}"' for c in COLUMNAS_PROTEGIDAS)
    return [
        f"""CREATE OR REPLACE FUNCTION audit_logs_inmutable() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'TRUNCATE' THEN
                RAISE EXCEPTION '{_ERROR}' USING ERRCODE = 'insufficient_privilege';
            END IF;
            IF TG_OP = 'DELETE' THEN
                IF EXISTS (SELECT 1 FROM audit_log_purge_permits p
                           WHERE p.active AND p.organization_id = COALESCE(OLD.organization_id, '')) THEN
                    RETURN OLD;
                END IF;
                RAISE EXCEPTION '{_ERROR}' USING ERRCODE = 'insufficient_privilege';
            END IF;
            IF OLD.seq IS NOT NULL AND ({cambia}) THEN
                RAISE EXCEPTION '{_ERROR}' USING ERRCODE = 'insufficient_privilege';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql""",
        "DROP TRIGGER IF EXISTS audit_logs_no_update ON audit_logs",
        "DROP TRIGGER IF EXISTS audit_logs_no_delete ON audit_logs",
        "CREATE TRIGGER audit_logs_no_update BEFORE UPDATE ON audit_logs FOR EACH ROW EXECUTE FUNCTION audit_logs_inmutable()",
        "CREATE TRIGGER audit_logs_no_delete BEFORE DELETE ON audit_logs FOR EACH ROW EXECUTE FUNCTION audit_logs_inmutable()",
        # TRUNCATE no dispara triggers de fila: se niega con uno de sentencia.
        "DROP TRIGGER IF EXISTS audit_logs_no_truncate ON audit_logs",
        "CREATE TRIGGER audit_logs_no_truncate BEFORE TRUNCATE ON audit_logs FOR EACH STATEMENT EXECUTE FUNCTION audit_logs_inmutable()",
    ]


def instalar(conexion) -> None:
    """Instala (o reinstala) los triggers en la base de `conexion`."""
    sentencias = _postgres(conexion) if conexion.dialect.name == "postgresql" else _sqlite(conexion)
    for sql in sentencias:
        conexion.execute(text(sql))


def desinstalar(conexion) -> None:
    if conexion.dialect.name == "postgresql":
        for sql in ("DROP TRIGGER IF EXISTS audit_logs_no_truncate ON audit_logs",
                    "DROP TRIGGER IF EXISTS audit_logs_no_update ON audit_logs",
                    "DROP TRIGGER IF EXISTS audit_logs_no_delete ON audit_logs",
                    "DROP FUNCTION IF EXISTS audit_logs_inmutable()"):
            conexion.execute(text(sql))
    else:
        conexion.execute(text("DROP TRIGGER IF EXISTS audit_logs_no_update"))
        conexion.execute(text("DROP TRIGGER IF EXISTS audit_logs_no_delete"))


def instalados(conexion) -> bool:
    """¿Están los triggers? (para el informe de cumplimiento)."""
    try:
        if conexion.dialect.name == "postgresql":
            n = conexion.execute(text(
                "SELECT count(*) FROM pg_trigger WHERE tgname IN ('audit_logs_no_update','audit_logs_no_delete') "
                "AND NOT tgisinternal")).scalar()
        else:
            n = conexion.execute(text(
                "SELECT count(*) FROM sqlite_master WHERE type = 'trigger' "
                "AND name IN ('audit_logs_no_update','audit_logs_no_delete')")).scalar()
        return int(n or 0) == 2
    except Exception:
        return False


def abrir_permiso_de_purga(db, org_id: str, motivo: str = "tenant_purge") -> None:
    """Permite borrar el registro de `org_id` en ESTA transacción (purga de empresa)."""
    db.execute(text("DELETE FROM audit_log_purge_permits WHERE organization_id = :o"), {"o": org_id})
    db.execute(text("INSERT INTO audit_log_purge_permits (organization_id, reason, created_at, uses, active) "
                    "VALUES (:o, :r, CURRENT_TIMESTAMP, 0, :a)"), {"o": org_id, "r": motivo[:200], "a": True})


def cerrar_permiso_de_purga(db, org_id: str) -> None:
    db.execute(text("DELETE FROM audit_log_purge_permits WHERE organization_id = :o"), {"o": org_id})
