"""Auditoria 2026-11: los modelos no importan servicios y el webhook de Stripe exige firma."""
import hashlib
import hmac
import json
import re
import time
from pathlib import Path

import pytest

from app.services import payments_service

RAIZ = Path(__file__).resolve().parents[1] / "app"


def test_ningun_modelo_importa_servicios():
    fuera = [
        str(f.relative_to(RAIZ)) for f in (RAIZ / "models").rglob("*.py")
        if re.search(r"^\s*(from app\.services|import app\.services)", f.read_text(encoding="utf-8"), re.M)
    ]
    assert fuera == []


def _firma(cuerpo: bytes, secreto: str, t: int) -> str:
    return f"t={t},v1=" + hmac.new(secreto.encode(), f"{t}.".encode() + cuerpo, hashlib.sha256).hexdigest()


def test_firma_de_stripe():
    cuerpo, ahora = b'{"type":"x"}', int(time.time())
    assert payments_service.verificar_firma(cuerpo, _firma(cuerpo, "s", ahora), "s")
    assert not payments_service.verificar_firma(cuerpo, _firma(cuerpo, "otro", ahora), "s")
    assert not payments_service.verificar_firma(cuerpo, _firma(cuerpo, "s", ahora - 3600), "s")  # reenvio viejo
    assert not payments_service.verificar_firma(cuerpo, None, "s")


def test_webhook_sin_secreto_o_sin_firma_no_toca_nada(monkeypatch):
    from app.core.errores import ErrorDeDominio
    cuerpo = json.dumps({"type": "checkout.session.completed"}).encode()
    monkeypatch.setattr(payments_service, "_secreto", lambda db: None)
    with pytest.raises(ErrorDeDominio) as e:
        payments_service.handle_stripe_webhook(cuerpo, None, db=None)
    assert e.value.status_code == 503
    monkeypatch.setattr(payments_service, "_secreto", lambda db: "s")
    with pytest.raises(ErrorDeDominio) as e:
        payments_service.handle_stripe_webhook(cuerpo, "t=1,v1=00", db=None)
    assert e.value.status_code == 400


def test_la_ruta_del_webhook_esta_montada(client):
    r = client.post("/api/v1/invoices/stripe/webhook", content=b"{}")
    assert r.status_code in (400, 503)  # rechazado por firma/secreto, no 404/401


def test_conexion_a_ip_interna_bloqueada_tras_resolver(monkeypatch):
    """DNS rebinding: el nombre valido acaba conectando a una IP interna."""
    from app.core import outbound_url as ou
    monkeypatch.setattr(ou, "_hosts_de_proxy", lambda: set())
    with pytest.raises(PermissionError):
        ou.comprobar_conexion("api.ejemplo.com", "10.0.0.5")
    ou.comprobar_conexion("api.ejemplo.com", "93.184.216.34")


def test_redireccion_a_red_interna_bloqueada():
    import urllib.request
    from fastapi import HTTPException
    from app.core import outbound_url as ou
    req = urllib.request.Request("https://api.ejemplo.com/x")
    with pytest.raises(HTTPException):
        ou._RedireccionValidada().redirect_request(req, None, 302, "Found", {}, "http://169.254.169.254/latest/meta-data")


def test_subida_sin_extension_de_tipo_desconocido():
    from fastapi import HTTPException
    from app.core.uploads import validate_upload
    with pytest.raises(HTTPException) as e:
        validate_upload("informe", "application/octet-stream", b"<html><script>alert(1)</script>")
    assert e.value.status_code == 415
    validate_upload("informe", "application/octet-stream", b"%PDF-1.7\n...")  # PDF reconocido: pasa
