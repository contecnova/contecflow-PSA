"""Los secretos de e-firma se guardan cifrados.

Auditoria 2026-11: `app_settings` guardaba en claro el secreto de DocuSign y el
de Adobe Sign.
"""
import importlib.util
from pathlib import Path

from app.models.settings import AppSetting
from app.models.user import User
from app.services import esign_service
from tests.conftest import auth


def test_guardar_por_la_api_cifra_y_leer_descifra(client, admin_token, db):
    r = client.patch("/api/v1/esign/config", headers=auth(admin_token), json={
        "docusign_secret_key": "ds-secreto-123", "docusign_account_id": "cuenta-1"})
    assert r.status_code == 200, r.text
    fila = db.query(AppSetting).filter(AppSetting.key == "esign.docusign_secret_key").one()
    assert fila.value.startswith("v2:") and "ds-secreto-123" not in fila.value
    cuenta = db.query(AppSetting).filter(AppSetting.key == "esign.docusign_account_id").one()
    assert cuenta.value == "cuenta-1"  # no es secreto: en claro
    admin = db.query(User).filter(User.id == "admin-test-id").one()
    assert esign_service.ajuste_de_firma(db, admin, "esign.docusign_secret_key") == "ds-secreto-123"


def test_la_migracion_cifra_lo_que_estaba_en_claro(db, monkeypatch):
    db.add(AppSetting(key="esign.adobe_sign_client_secret", value="adobe-en-claro"))
    db.commit()
    ruta = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "117_esign_secretos_cifrados.py"
    spec = importlib.util.spec_from_file_location("m117", ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    conexion = db.connection()
    monkeypatch.setattr(m.op, "get_bind", lambda: conexion, raising=False)
    m.upgrade()
    db.commit()
    db.expire_all()
    fila = db.query(AppSetting).filter(AppSetting.key == "esign.adobe_sign_client_secret").one()
    assert fila.value.startswith("v2:")
    assert esign_service.descifrar_si_es_secreto(fila.key, fila.value) == "adobe-en-claro"
    # Un valor antiguo en claro se sigue leyendo.
    assert esign_service.descifrar_si_es_secreto("esign.docusign_secret_key", "viejo") == "viejo"
