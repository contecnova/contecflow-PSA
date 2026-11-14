"""Voz de Twilio con varias organizaciones (segunda auditoría 2026-11, #19).

La organización sale del número llamado (`To`, ajuste `TWILIO_PHONE_NUMBERS`),
la firma se verifica con el token de esa organización y la llamada se atiende
en su contexto. Un número desconocido se rechaza sin caer en ninguna.
"""
import base64
import hashlib
import hmac
import json

import pytest

from app.core.config import settings

ORG_A = "org-a-test"
ORG_B = "org-b-test"
URL = "http://testserver/api/v1/sd/voice/webhook/twilio"


def _firma(token, params):
    datos = URL + "".join(f"{k}{params[k]}" for k in sorted(params))
    return base64.b64encode(hmac.new(token.encode(), datos.encode(), hashlib.sha1).digest()).decode()


def _llamar(client, to, token):
    params = {"To": to, "From": "+34611111111", "CallSid": "CA1"}
    return client.post(URL, data=params, headers={"X-Twilio-Signature": _firma(token, params)})


def _sesiones(db, org):
    from app.models.settings import AppSetting
    db.expire_all()
    q = db.query(AppSetting).filter(AppSetting.key == "sd.voice_agent.sessions")
    q = q.filter(AppSetting.organization_id == org) if org else q.filter(AppSetting.organization_id.is_(None))
    fila = q.first()
    return json.loads(fila.value) if fila and fila.value else {}


@pytest.fixture
def dos_numeros(db, seed_multitenant, monkeypatch):
    from app.models.settings import AppSetting
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "tok-global", raising=False)
    for org, numeros, token in ((ORG_A, "+34 600 000 001, +34600000009", "tok-a"),
                                (ORG_B, "+34600000002", "tok-b")):
        db.add(AppSetting(organization_id=org, key="TWILIO_PHONE_NUMBERS", value=numeros))
        db.add(AppSetting(organization_id=org, key="TWILIO_AUTH_TOKEN", value=token))
    db.query(AppSetting).filter(AppSetting.key == "sd.voice_agent.sessions").delete()
    db.commit()


def test_el_numero_de_a_se_atiende_en_a(client, db, dos_numeros):
    r = _llamar(client, "+34600000001", "tok-a")
    assert r.status_code == 200, r.text
    assert "<Gather" in r.text
    sesiones = _sesiones(db, ORG_A)
    assert len(sesiones) == 1
    assert _sesiones(db, ORG_B) == {} and _sesiones(db, None) == {}
    # La opción DTMF vuelve con la firma de A y se anota en la sesión de A.
    (sid,) = sesiones
    url = f"http://testserver/api/v1/sd/voice/webhook/twilio/gather?session_id={sid}"
    params = {"To": "+34600000001", "From": "+34611111111", "CallSid": "CA1", "Digits": "1"}
    datos = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    firma = base64.b64encode(hmac.new(b"tok-a", datos.encode(), hashlib.sha1).digest()).decode()
    r = client.post(url, data=params, headers={"X-Twilio-Signature": firma})
    assert r.status_code == 200 and "<Dial>" in r.text, r.text
    assert len(_sesiones(db, ORG_A)[sid]["transcript"]) == 2


def test_numero_desconocido_se_rechaza_sin_caer_en_ninguna(client, db, dos_numeros):
    r = _llamar(client, "+34999999999", "tok-global")
    assert r.status_code == 200 and "<Reject" in r.text and "<Gather" not in r.text
    assert _sesiones(db, ORG_A) == {} and _sesiones(db, ORG_B) == {} and _sesiones(db, None) == {}


def test_firma_invalida_403(client, db, dos_numeros):
    r = _llamar(client, "+34600000001", "tok-falso")
    assert r.status_code == 403
    assert _sesiones(db, ORG_A) == {}


def test_el_token_de_una_organizacion_no_vale_para_el_numero_de_otra(client, db, dos_numeros):
    assert _llamar(client, "+34600000002", "tok-a").status_code == 403
    assert _llamar(client, "+34600000001", "tok-b").status_code == 403
    assert _sesiones(db, ORG_A) == {} and _sesiones(db, ORG_B) == {}
