"""Rotar SECRET_KEY no deja ilegible lo cifrado.

Auditoria 2026-11: `scripts/rotate_keys.sh` cambiaba la clave sin re-cifrar
nada (y la imprimia). Ahora la aplicacion descifra tambien con
SECRET_KEY_PREVIOUS y `scripts/reencrypt_secrets.py` re-cifra con la actual.
"""
import importlib.util
from pathlib import Path

import pytest

from app.core import encryption
from app.core.config import settings
from app.models.user import User

VIEJA = "vieja-clave-de-prueba-0123456789abcdefghijklmnop"
NUEVA = "nueva-clave-de-prueba-9876543210zyxwvutsrqponmlk"


@pytest.fixture
def con_clave(monkeypatch):
    def poner(actual, anteriores=""):
        monkeypatch.setattr(settings, "SECRET_KEY", actual)
        monkeypatch.setattr(settings, "SECRET_KEY_PREVIOUS", anteriores)
        monkeypatch.setattr(encryption, "_KEY", None)
    return poner


def _script():
    ruta = Path(__file__).resolve().parent.parent / "scripts" / "reencrypt_secrets.py"
    spec = importlib.util.spec_from_file_location("reencrypt_secrets", ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_lo_cifrado_con_la_anterior_se_lee_si_esta_en_previous(con_clave):
    con_clave(VIEJA)
    v2 = encryption.encrypt_value("secreto-totp")
    con_clave(NUEVA)
    assert encryption.decrypt_value(v2) is None
    con_clave(NUEVA, VIEJA)
    assert encryption.decrypt_value(v2) == "secreto-totp"


def test_integraciones_y_modelos_tambien(con_clave):
    from app.services.collaboration import _integrations as colab
    from app.services import ml_trainer
    con_clave(VIEJA)
    token = colab.encrypt("token-slack")
    firmado = ml_trainer._serialize_model({"a": 1})
    con_clave(NUEVA, VIEJA)
    assert colab.decrypt(token) == "token-slack"
    assert ml_trainer._deserialize_model(firmado) == {"a": 1}


def test_el_script_recifra_y_deja_de_depender_de_la_anterior(con_clave, db, monkeypatch, capsys):
    from tests.conftest import engine as motor_de_pruebas
    con_clave(VIEJA)
    db.query(User).filter(User.id == "admin-test-id").update(
        {"mfa_secret": encryption.encrypt_value("JBSWY3DPEHPK3PXP")})
    db.commit()

    con_clave(NUEVA, VIEJA)
    script = _script()
    monkeypatch.setattr(script, "engine", motor_de_pruebas)
    monkeypatch.setattr("sys.argv", ["reencrypt_secrets.py", "--check"])
    assert script.main() == 1
    monkeypatch.setattr("sys.argv", ["reencrypt_secrets.py"])
    assert script.main() == 0
    salida = capsys.readouterr().out
    assert "users.mfa_secret: 1 cifrados" in salida and "Re-cifrados: 1." in salida

    con_clave(NUEVA)  # sin la anterior
    db.expire_all()
    valor = db.query(User).filter(User.id == "admin-test-id").one().mfa_secret
    assert encryption.decrypt_value(valor) == "JBSWY3DPEHPK3PXP"
