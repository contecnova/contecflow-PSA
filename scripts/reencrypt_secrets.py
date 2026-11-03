"""Re-cifra con la SECRET_KEY actual todo lo que se cifro con una anterior.

Uso (desde la raiz, con el .env ya rotado):

    venv/bin/python scripts/reencrypt_secrets.py            # re-cifra
    venv/bin/python scripts/reencrypt_secrets.py --check    # solo cuenta

Auditoria 2026-11: `rotate_keys.sh` cambiaba SECRET_KEY y lo cifrado con la
anterior quedaba ilegible para siempre (credenciales de integraciones, secretos
TOTP, buzones…). La rotacion buena es: la clave nueva en SECRET_KEY, la vieja
en SECRET_KEY_PREVIOUS (la aplicacion lee con las dos) y este script, que
recorre TODAS las columnas de texto de TODAS las tablas y re-cifra lo que solo
abre una clave anterior. Cuando dice «0 pendientes», SECRET_KEY_PREVIOUS se
puede vaciar.

Formatos que reconoce:
- `v2:<sal>.<token>` de `app.core.encryption` (el actual);
- token Fernet suelto (`gAAAAA…`): el v1 de `encryption` o el de las
  integraciones de colaboracion; se identifica por la clave que lo abre y se
  re-cifra con su mismo esquema;
- `kmsv1:` no depende de SECRET_KEY y no se toca.

Dice cuantos valores ha mirado por tabla: una comprobacion que no cuenta lo que
recorre puede estar mirando nada.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cryptography.fernet import Fernet, InvalidToken  # noqa: E402
from sqlalchemy import String, Text, select, update  # noqa: E402

import app.models  # noqa: E402,F401 — registra todas las tablas
from app.core import encryption  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import engine  # noqa: E402


def _fernet_colaboracion(secreto: str) -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secreto.encode() + b"|collab-integrations").digest()))


def _abre(fernet: Fernet, token: str) -> str | None:
    try:
        return fernet.decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def recifrar(valor: str) -> str | None:
    """El valor re-cifrado con la clave actual, o None si ya lo esta (o no es nuestro)."""
    actual, anteriores = settings.SECRET_KEY, encryption.claves_secretas()[1:]
    if valor.startswith("v2:"):
        sal_b64, token = valor[3:].split(".", 1)
        sal = base64.urlsafe_b64decode(sal_b64 + "==")
        if _abre(Fernet(encryption._derive_record_key(sal, actual)), token) is not None:
            return None
        for vieja in anteriores:
            claro = _abre(Fernet(encryption._derive_record_key(sal, vieja)), token)
            if claro is not None:
                return encryption.encrypt_value(claro)
        return None
    if valor.startswith("gAAAAA"):
        if (_abre(_fernet_colaboracion(actual), valor) is not None
                or _abre(Fernet(encryption._derive_key(actual)), valor) is not None):
            return None
        for vieja in anteriores:
            claro = _abre(_fernet_colaboracion(vieja), valor)
            if claro is not None:
                return _fernet_colaboracion(actual).encrypt(claro.encode()).decode()
            claro = _abre(Fernet(encryption._derive_key(vieja)), valor)
            if claro is not None:
                return encryption.encrypt_value(claro)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="solo cuenta, no escribe")
    args = parser.parse_args()

    if len(encryption.claves_secretas()) < 2:
        print("SECRET_KEY_PREVIOUS esta vacia: no hay clave anterior con la que leer. Nada que hacer.")
        return 0

    mirados = pendientes = escritos = columnas = 0
    with engine.begin() as conn:
        for tabla in Base.metadata.sorted_tables:
            pk = list(tabla.primary_key.columns)
            if len(pk) != 1:
                continue
            for col in tabla.columns:
                if not isinstance(col.type, (String, Text)) or col.primary_key:
                    continue
                columnas += 1
                filas = conn.execute(select(pk[0], col).where(
                    (col.like("v2:%")) | (col.like("gAAAAA%")))).all()
                vistos_tabla = 0
                for ident, valor in filas:
                    mirados += 1
                    vistos_tabla += 1
                    nuevo = recifrar(valor)
                    if nuevo is None:
                        continue
                    pendientes += 1
                    if not args.check:
                        conn.execute(update(tabla).where(pk[0] == ident).values({col.name: nuevo}))
                        escritos += 1
                if vistos_tabla:
                    print(f"  {tabla.name}.{col.name}: {vistos_tabla} cifrados")
    print(f"Columnas de texto recorridas: {columnas}. Valores cifrados mirados: {mirados}. "
          f"Con clave anterior: {pendientes}. Re-cifrados: {escritos}.")
    if args.check and pendientes:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
