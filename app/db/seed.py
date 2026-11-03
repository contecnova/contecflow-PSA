"""
Seed script – populates the DB with complete realistic data for ALL modules.
Run: python -m app.db.seed
All field names verified against actual SQLAlchemy models.

NOTE: este módulo actúa como *barrel*: el contenido real vive en el
subpaquete ``app.db.seed_parts`` (troceado por dominios). Aquí se re-exporta
la API pública EXACTA para no romper ningún import existente.
"""
import sys
import os
import random  # noqa: F401  re-export (API pública histórica)
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from datetime import date, timedelta, datetime, timezone  # noqa: F401  re-export
import bcrypt  # noqa: F401  re-export

from app.db.session import SessionLocal
from app.db.session import engine  # noqa: F401  re-export
from app.db.base import Base  # noqa: F401  re-export
from app.core.config import settings  # noqa: F401  re-export

# ── API pública re-exportada desde los submódulos ───────────────────────────
from app.db.seed_parts.core import seed, get_password_hash, _risk_score  # noqa: F401
from app.db.seed_parts.service_desk import seed_service_desk
from app.db.seed_parts.v10 import seed_v10
from app.db.seed_parts.enterprise import seed_enterprise
from app.db.seed_parts.v12 import seed_v12
from app.db.seed_parts.v13 import seed_v13
from app.db.seed_parts.config_versions import seed_v14, seed_v15, seed_v16
from app.db.seed_parts.itsm import seed_itsm_v2
from app.db.seed_parts.alm import seed_alm

if __name__ == "__main__":
    # ── La consola de Windows no habla UTF-8, y el sembrado sí ───────────────
    #
    # Auditoría 2026-09. `python -m app.db.seed` reventaba en Windows con
    # `UnicodeEncodeError: 'charmap' codec can't encode character '⚠'`: la
    # consola arranca en la página de códigos 850 —o 1252—, y el sembrado tiene
    # **81 `print` con caracteres fuera de ASCII** repartidos en 14 ficheros
    # (los «✓» de cada paso, el «⚠️» de la contraseña).
    #
    # No es un adorno que se rompe: el proceso muere a medias y la transacción
    # se deshace, así que la base se queda **con cero usuarios** y sin forma de
    # entrar en la aplicación. Era el camino de instalación documentado.
    #
    # El arreglo va en la SALIDA y no en los 81 `print`: el problema no es el
    # texto, es el descriptor. `setup.bat` fija además `PYTHONUTF8=1` para todo
    # lo que lanza; esto cubre a quien ejecute el módulo a mano.
    #
    # `errors="replace"` a propósito: si algún día aparece un carácter que la
    # consola no pueda pintar, se ve un interrogante — nunca se pierde el
    # sembrado por un símbolo.
    for _flujo in (sys.stdout, sys.stderr):
        if hasattr(_flujo, "reconfigure"):
            _flujo.reconfigure(encoding="utf-8", errors="replace")

    seed()
    seed_service_desk()
    seed_v10()
    seed_itsm_v2()
    seed_alm()
    seed_enterprise()
    seed_v12()
    seed_v13()
    db_main = SessionLocal()
    seed_v14(db_main)
    seed_v15(db_main)
    seed_v16(db_main)
    db_main.close()
