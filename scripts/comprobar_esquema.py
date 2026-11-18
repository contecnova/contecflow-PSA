"""Comprueba que la base de datos tiene el esquema de los modelos (18-11-2026).

Lo ejecutan setup.bat y setup.sh después de `alembic upgrade head`.

Por qué: `alembic_version` puede decir «head» sin que las revisiones se hayan
ejecutado (un `alembic stamp` a mano o sobre otra base, una copia de la base
de otra máquina…). Entonces `upgrade head` no hace nada y la aplicación
arranca y falla con 500 («no such column») al primer uso. Pasó con la 183:
la base marcaba 183 y no tenía `clients.phone` ni `client_contacts.portal_user_id`.

Compara tablas y columnas de `Base.metadata` con las de la base. Si falta
algo, lo lista, dice qué hacer y sale con código 1 para que el setup se pare.
No repara nada por su cuenta: añadir columnas a mano se saltaría los datos
que preparan las migraciones (rellenos, correlaciones), que es lo que ocultaba
el antiguo `app.db.migrate`.

Uso: python scripts/comprobar_esquema.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def faltantes() -> tuple[list[str], dict[str, list[str]]]:
    import sqlalchemy as sa

    import app.models  # noqa: F401  registra todos los modelos
    from app.db.base import Base
    from app.db.session import engine

    insp = sa.inspect(engine)
    en_bd = set(insp.get_table_names())
    tablas, columnas = [], {}
    for nombre, tabla in sorted(Base.metadata.tables.items()):
        if nombre not in en_bd:
            tablas.append(nombre)
            continue
        hay = {c["name"] for c in insp.get_columns(nombre)}
        sin = [c.name for c in tabla.columns if c.name not in hay]
        if sin:
            columnas[nombre] = sin
    return tablas, columnas


def main() -> int:
    tablas, columnas = faltantes()
    if not tablas and not columnas:
        print("[OK] Esquema completo: la base tiene todas las tablas y columnas de los modelos")
        return 0
    print("[ERROR] La base NO tiene el esquema de los modelos aunque Alembic diga que esta al dia.")
    for t in tablas:
        print(f"[ERROR]   falta la tabla {t}")
    for t, cs in columnas.items():
        print(f"[ERROR]   faltan columnas en {t}: {', '.join(cs)}")
    print("[ERROR] La version de Alembic se marco sin ejecutar las migraciones.")
    print("[ERROR] Haz copia de la base, vuelve a la ultima revision que si se aplico")
    print("[ERROR] (python -m alembic stamp <revision>) y ejecuta python -m alembic upgrade head.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
