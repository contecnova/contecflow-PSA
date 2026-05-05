#!/usr/bin/env python3
"""
Reset all application data while preserving schema and keep only the admin user.

Designed for local testing flows where you want to boot Contecflow from a clean
state but keep login access with the configured superadmin credentials.
"""

from __future__ import annotations

import os
import sys

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


def _ensure_admin_user(db):
    email = settings.SUPERADMIN_EMAIL
    password = settings.SUPERADMIN_PASSWORD

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


def main() -> int:
    db = SessionLocal()
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
