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

if __name__ == "__main__":
    seed()
    seed_service_desk()
    seed_v10()
    seed_itsm_v2()
    seed_enterprise()
    seed_v12()
    seed_v13()
    db_main = SessionLocal()
    seed_v14(db_main)
    seed_v15(db_main)
    seed_v16(db_main)
    db_main.close()
