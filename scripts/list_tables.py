from app.db.session import SessionLocal
from sqlalchemy import text
s = SessionLocal()
from app.db.contexto_de_tenant import declarar_sistema as _declarar_sistema
_declarar_sistema(s, "script: listar tablas")  # auditoría 22-11-2026: TENANT_SESION_SIN_CONTEXTO=cerrar
print(s.execute(text('SELECT name FROM sqlite_master WHERE type=\'table\';')).fetchall())
