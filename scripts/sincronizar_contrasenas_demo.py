"""Alinea las contraseñas de los usuarios demo con el .env (23-11-2026).

Lo llaman setup.bat y setup.sh en cada arranque local.

Cada usuario recibe la MISMA contraseña que le da la semilla
(`app/db/seed_parts/core.py`) y `scripts/reset_to_admin_only.py`:

* el superadmin (`admin`): `SUPERADMIN_PASSWORD`;
* el resto (`ana.torres`, `luis.vega`, `rrhh`): `DEFAULT_USER_PASSWORD`.

Antes (hasta el 23-11-2026) ponía `DEFAULT_USER_PASSWORD` a todos, también al
admin, mientras la semilla le ponía `SUPERADMIN_PASSWORD`: según qué se hubiera
ejecutado el último, el admin entraba con una o con otra, y el banner del setup
anunciaba siempre la primera. Además la contraseña llegaba por la variable
`DEMO_PWD` leída por `cmd` con expansión retardada, que se comía los `!` (las
contraseñas generadas acaban en `!`). Ahora se leen de `Settings`, sin pasar por
la consola.

Puerta de entorno (auditoría 2026-08, P0-4): solo en development o test (con
sus alias, normalizados por `Settings`). En otro entorno no toca nada.

`--centinela <fichero>`: guarda el SHA-256 de las dos contraseñas y no rehace
nada si no han cambiado (nunca las guarda en claro).

Imprime una línea: `ok:<n>`, `sin-cambios`, `omitido:<motivo>` o `error: ...`.
Sale con 1 solo si falla.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

USUARIOS_DEMO = ("admin", "ana.torres", "luis.vega", "rrhh")
ENTORNOS_PERMITIDOS = {"development", "test"}


def huella(contrasena_usuarios: str, contrasena_superadmin: str) -> str:
    return hashlib.sha256(f"{contrasena_usuarios}\0{contrasena_superadmin}".encode()).hexdigest()


def contrasena_para(usuario, contrasena_usuarios: str, contrasena_superadmin: str) -> str:
    """La que le da la semilla: superadmin → SUPERADMIN_PASSWORD; resto → DEFAULT_USER_PASSWORD."""
    return contrasena_superadmin if getattr(usuario, "is_superadmin", False) else contrasena_usuarios


def main(argv: list[str] | None = None) -> int:
    args = argparse.ArgumentParser()
    args.add_argument("--centinela", default="")
    opciones = args.parse_args(argv)

    from app.core.config import settings

    if settings.ENVIRONMENT not in ENTORNOS_PERMITIDOS:
        print(f"omitido:ENVIRONMENT={settings.ENVIRONMENT}")
        return 0
    pwd_usuarios = settings.DEFAULT_USER_PASSWORD or ""
    pwd_superadmin = settings.SUPERADMIN_PASSWORD or ""
    if not pwd_usuarios or not pwd_superadmin:
        print("omitido:faltan DEFAULT_USER_PASSWORD o SUPERADMIN_PASSWORD en .env")
        return 0

    actual = huella(pwd_usuarios, pwd_superadmin)
    if opciones.centinela and os.path.exists(opciones.centinela):
        with open(opciones.centinela, encoding="utf-8", errors="replace") as f:
            if f.read().strip() == actual:
                print("sin-cambios")
                return 0

    from app.core.security import get_password_hash
    from app.db.session import SessionLocal, declarar_sistema
    from app.models.user import User

    db = declarar_sistema(SessionLocal(), "setup: contraseñas demo")
    try:
        actualizados = 0
        for u in db.query(User).filter(User.username.in_(USUARIOS_DEMO)).all():
            u.hashed_password = get_password_hash(contrasena_para(u, pwd_usuarios, pwd_superadmin))
            actualizados += 1
        db.commit()
    except Exception as exc:  # noqa: BLE001 - el setup solo necesita saber que falló
        db.rollback()
        print(f"error: {exc}")
        return 1
    finally:
        db.close()
    if opciones.centinela:
        with open(opciones.centinela, "w", encoding="utf-8") as f:
            f.write(actual + "\n")
    print(f"ok:{actualizados}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
