"""Aplicar las migraciones desde setup.bat y setup.sh (19-11-2026).

Por qué no `python -m alembic upgrade head` a pelo:

1. Si la cadena tiene DOS cabezas (dos migraciones nuevas colgando de la misma
   anterior, p. ej. dos ramas de trabajo en paralelo), Alembic responde
   «Multiple head revisions» y no aplica nada. Aquí se detecta antes y se dice
   cuáles son y cómo arreglarlo.
2. Alembic termina con código -1 cuando falla; en Windows `if errorlevel 1` no
   detecta los negativos y setup.bat seguía como si nada (y la comprobación de
   esquema daba un diagnóstico engañoso). Este script siempre sale con 0 o 1.

Uso: python scripts/migrar.py
"""
from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)


def main() -> int:
    from alembic import command
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(os.path.join(RAIZ, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(RAIZ, "alembic"))
    cabezas = ScriptDirectory.from_config(cfg).get_heads()
    if len(cabezas) != 1:
        print("[ERROR] La cadena de migraciones tiene %d cabezas: %s" % (len(cabezas), ", ".join(sorted(cabezas))))
        print("[ERROR] Dos migraciones cuelgan de la misma anterior. Encadena una tras otra")
        print("[ERROR] (cambia su down_revision) o crea una de merge: python -m alembic merge heads")
        return 1
    try:
        command.upgrade(cfg, "head")
    except Exception as e:  # noqa: BLE001 — cualquier fallo de migración para el setup
        print(f"[ERROR] Las migraciones han fallado: {type(e).__name__}: {e}")
        return 1
    print(f"[OK] Migraciones aplicadas hasta {cabezas[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
