"""👍/👎 de las respuestas de IA (revisión 2026-11, lo que contecmind tenía).

Antes no se podía valorar ninguna respuesta; las preguntas internas nunca
llegaban a «Preguntas sin respuesta». Ahora un 👎 las lleva.
"""
from __future__ import annotations

import pytest

from app.models.ai_chat import AIAnswerFeedback
from app.models.service_desk.kb_calidad import KBGap
from tests.conftest import auth
from tests.test_kb_calidad_2026_11 import _cliente_del_portal, _portal_chat


@pytest.fixture
def ia(monkeypatch):
    monkeypatch.setattr("app.api.v1.endpoints.ai_chat.call_ai", lambda db, messages, system=None, **k: "respuesta")
    monkeypatch.setattr("app.services.ai_modules.client_portal.call_ai_unified", lambda db, messages, system=None, **k: "respuesta")


def _preguntar(client, token, texto):
    r = client.post("/api/v1/ai/chat", headers=auth(token), json={"message": texto})
    assert r.status_code == 200, r.text
    return r.json()["data"]["message_id"]


def test_EL_HALLAZGO_un_no_me_ha_servido_abre_una_pregunta_sin_respuesta(client, pm_token, db, ia):
    mid = _preguntar(client, pm_token, "¿Cómo se pide una licencia de Visio para un proyecto?")
    r = client.post(f"/api/v1/ai/messages/{mid}/feedback", headers=auth(pm_token), json={"helpful": False})
    assert r.status_code == 200, r.text
    hueco = db.query(KBGap).one()
    assert hueco.source == "assistant_feedback" and "Visio" in hueco.question
    fila = db.query(AIAnswerFeedback).one()
    assert fila.helpful is False and fila.user_id == "pm-test-id"


def test_un_me_ha_servido_no_abre_nada_y_votar_otra_vez_cambia_el_voto(client, pm_token, db, ia):
    mid = _preguntar(client, pm_token, "¿Cuántas horas tiene la jornada estándar?")
    client.post(f"/api/v1/ai/messages/{mid}/feedback", headers=auth(pm_token), json={"helpful": True})
    assert db.query(KBGap).count() == 0
    client.post(f"/api/v1/ai/messages/{mid}/feedback", headers=auth(pm_token), json={"helpful": False})
    db.expire_all()
    assert db.query(AIAnswerFeedback).count() == 1 and db.query(AIAnswerFeedback).one().helpful is False


def test_nadie_valora_la_respuesta_de_otro(client, pm_token, dev_token, db, ia):
    mid = _preguntar(client, pm_token, "¿Dónde está la plantilla de acta de reunión?")
    assert client.post(f"/api/v1/ai/messages/{mid}/feedback", headers=auth(dev_token),
                       json={"helpful": False}).status_code == 404


def test_EL_HALLAZGO_el_cliente_del_portal_valora_y_avisa_al_equipo(client, admin_token, db, ia):
    _cliente_del_portal(client, admin_token)
    datos = _portal_chat(client, "¿Puedo ampliar el alcance del soporte a fines de semana?")
    r = client.post(f"/api/v1/portal/ai-chat/messages/{datos['message_id']}/feedback", json={"helpful": False})
    assert r.status_code == 200, r.text
    # Sin artículo ya quedó apuntada al preguntar; el 👎 suma sobre la misma pregunta.
    db.expire_all()
    hueco = db.query(KBGap).one()
    assert hueco.times_asked == 2
    historial = client.get(f"/api/v1/portal/ai-chat/{datos['session_id']}/messages").json()["items"]
    assert all("id" in m for m in historial)
