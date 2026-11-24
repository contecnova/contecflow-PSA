#!/usr/bin/env python3
"""
Reset all application data while preserving schema and keep only the admin user.

Designed for local testing flows where you want to boot Contecflow from a clean
state but keep login access with the configured superadmin credentials.
"""

from __future__ import annotations

import os
import sys
import uuid

from sqlalchemy import text

# Ensure project root is importable when running as: python scripts/reset_to_admin_only.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.models.user import User, UserRole, UserStatus


def _wipe_all_data(db):
    bind = db.get_bind()
    metadata = User.metadata
    metadata.reflect(bind=bind)

    # Never wipe Alembic migration marker table.
    data_tables = [t for t in metadata.sorted_tables if t.name != "alembic_version"]
    dialect = bind.dialect.name

    # 23-11-2026: desde la 199, `audit_logs` es de solo añadir (triggers que niegan
    # UPDATE/DELETE/TRUNCATE) y `setup clean` fallaba. Este reseteo total solo corre
    # fuera de producción (`exigir_entorno_no_productivo` en `main`): se retiran los
    # triggers, se vacía todo y se reinstalan en la MISMA transacción. Fuera de este
    # script la protección no cambia.
    from app.db import auditoria_inmutable
    auditoria_inmutable.desinstalar(db.connection())

    if dialect == "sqlite":
        db.execute(text("PRAGMA foreign_keys=OFF"))
        for table in reversed(data_tables):
            db.execute(table.delete())
        # Best-effort reset for autoincrement counters in sqlite.
        try:
            db.execute(text("DELETE FROM sqlite_sequence"))
        except Exception:
            pass
        db.execute(text("PRAGMA foreign_keys=ON"))
    elif dialect == "postgresql":
        table_names = ", ".join(f'"{t.name}"' for t in data_tables)
        if table_names:
            db.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))
    else:
        for table in reversed(data_tables):
            db.execute(table.delete())

    auditoria_inmutable.instalar(db.connection())


def _get_available_columns(db, table_name: str) -> set[str]:
    """Return set of column names for the given table. Works on SQLite and PostgreSQL."""
    bind = db.get_bind()
    dialect = bind.dialect.name
    if dialect == "sqlite":
        result = db.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
        return {row[1] for row in result}
    else:
        result = db.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = :t AND table_schema = 'public'"
            ),
            {"t": table_name},
        ).fetchall()
        return {row[0] for row in result}


def _ensure_default_organization(db):
    columns = _get_available_columns(db, "organizations")
    existing = db.execute(
        text("SELECT id FROM organizations WHERE slug = :slug LIMIT 1"),
        {"slug": "default"},
    ).fetchone()
    if existing:
        return existing[0]

    org_id = str(uuid.uuid4())
    insert_columns = ["id", "name", "slug", "plan", "is_active", "max_users", "max_projects", "admin_email"]
    insert_columns = [col for col in insert_columns if col in columns]

    values = {
        "id": org_id,
        "name": "Default Organization",
        "slug": "default",
        "plan": "starter",
        "is_active": True,
        "max_users": 25,
        "max_projects": 100,
        "admin_email": settings.SUPERADMIN_EMAIL,
    }

    if not insert_columns:
        raise RuntimeError("No se pudo crear la organización base: la tabla organizations no está disponible")

    cols_sql = ", ".join(insert_columns)
    placeholders = ", ".join(f":{col}" for col in insert_columns)
    db.execute(text(f"INSERT INTO organizations ({cols_sql}) VALUES ({placeholders})"), values)
    return org_id


def _ensure_admin_user(db):
    email = settings.SUPERADMIN_EMAIL
    password = settings.SUPERADMIN_PASSWORD
    org_id = _ensure_default_organization(db)

    admin = db.query(User).filter(User.username == "admin").first()
    if admin is None:
        admin = User(
            username="admin",
            email=email,
            full_name="Administrador",
            role=UserRole.admin,
            status=UserStatus.active,
            is_active=True,
            is_superadmin=True,
            hashed_password=get_password_hash(password),
            organization_id=org_id,
        )
        db.add(admin)
    else:
        admin.email = email
        admin.full_name = admin.full_name or "Administrador"
        admin.role = UserRole.admin
        admin.status = UserStatus.active
        admin.is_active = True
        admin.is_superadmin = True
        admin.hashed_password = get_password_hash(password)
        if not admin.organization_id:
            admin.organization_id = org_id


def _solo_admin() -> int:
    """Crea o restablece el admin desde el .env SIN borrar nada (23-11-2026).

    Es lo que hace `make init-admin` (antes llamaba a un `init_admin.sh` que no
    existía). Toma SUPERADMIN_EMAIL y SUPERADMIN_PASSWORD, que `Settings` ya
    exige fuertes fuera de desarrollo, igual que la semilla, que re-afirma esa
    contraseña en cada pasada como vía de recuperación de un superadmin
    bloqueado. Por eso vale en cualquier entorno: no borra datos. Queda en
    audit_log (sin la contraseña) y, si el admin ya existía, se cierran sus
    sesiones (como al restablecer una contraseña).
    """
    from app.db.contexto_de_tenant import declarar_sistema as _declarar_sistema
    from app.services.audit import audit_log

    db = SessionLocal()
    _declarar_sistema(db, "script: crear o restablecer admin")
    try:
        existia = db.query(User).filter(User.username == "admin").first() is not None
        _ensure_admin_user(db)
        admin = db.query(User).filter(User.username == "admin").first()
        cerradas = 0
        if existia:
            from app.services.auth_service.tokens_y_cookies import revocar_sesiones_del_usuario
            cerradas = revocar_sesiones_del_usuario(db, admin.id, "admin restablecido desde .env")
        db.flush()
        audit_log(db, None, "UPDATE" if existia else "CREATE", "users", admin.id, "admin",
                  new_values={"is_active": True, "is_superadmin": True, "password": "(restablecida desde .env)"},
                  metadata={"origen": "scripts/reset_to_admin_only.py --solo-admin", "sesiones_cerradas": cerradas})
        db.commit()
        print(f"OK: admin {'restablecido' if existia else 'creado'} con SUPERADMIN_EMAIL/SUPERADMIN_PASSWORD del .env.")
        return 0
    except Exception as exc:
        db.rollback()
        print(f"ERROR: no se pudo crear o restablecer el admin: {exc}")
        return 1
    finally:
        db.close()


def main() -> int:
    if "--solo-admin" in sys.argv[1:]:
        return _solo_admin()
    from app.core.entorno import exigir_entorno_no_productivo
    exigir_entorno_no_productivo("Dejar la base sólo con el administrador")
    db = SessionLocal()
    from app.db.contexto_de_tenant import declarar_sistema as _declarar_sistema
    _declarar_sistema(db, "script: reset a solo admin")  # auditoría 22-11-2026: TENANT_SESION_SIN_CONTEXTO=cerrar
    try:
        _wipe_all_data(db)
        _ensure_admin_user(db)
        db.commit()
        print("OK: base de datos reseteada. Solo existe el usuario admin.")
        return 0
    except Exception as exc:
        db.rollback()
        print(f"ERROR: no se pudo resetear la base de datos: {exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
