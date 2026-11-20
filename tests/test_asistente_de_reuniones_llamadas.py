"""Asistente de reuniones en las llamadas del chat interno (cuarta vía, 19-11-2026).

Cada navegador sube su propio audio (subtítulos en vivo): el hablante es la
persona autenticada. STT e IA simulados.
"""
from __future__ import annotations

import json

import pytest

from app.models.user import User
from app.services import settings_service
from tests.conftest import auth


@pytest.fixture(autouse=True)
def _limpio(tmp_path, monkeypatch):
    from app.services.reuniones import almacen
    settings_service.invalidate_cache()
    monkeypatch.setattr(almacen, "RAIZ", tmp_path / "reuniones")
    yield
    settings_service.invalidate_cache()


@pytest.fixture
def simulados(monkeypatch):
    from app.services.reuniones import transcripcion
    from app.services.stt import STTResult
    monkeypatch.setattr(transcripcion, "transcribir",
                        lambda *a, **k: STTResult(text="Propongo cerrar el sprint el viernes", provider="whisper_local"))
    monkeypatch.setattr("app.services.ai_modules._base.map_reduce_analysis", lambda texto, **k: json.dumps({
        "summary": "Se cierra el sprint.", "decisions": ["Cerrar el viernes"], "risks": [], "open_questions": [],
        "actions": [{"description": "Preparar la demo", "assignee_name": None}]}))
    encolados = []
    from app.services.collaboration import _queue
    monkeypatch.setattr(_queue.task_queue, "enqueue", lambda fn, *a, **k: encolados.append((fn.__name__, a)))
    return encolados


def _llamada(client, h):
    client.get("/api/v1/collaboration/workspace", headers=h)
    canales = client.get("/api/v1/collaboration/channels", headers=h).json()
    canales = canales.get("items") if isinstance(canales, dict) else canales
    r = client.post("/api/v1/collaboration/calls/start",
                    json={"conversation_id": canales[0]["conversation_id"], "kind": "video"}, headers=h)
    return r.json()["data"]["call_id"]


def test_activar_exige_el_aviso_y_luego_graba_con_el_hablante_real(client, db, admin_token, simulados):
    h = auth(admin_token)
    call_id = _llamada(client, h)
    r = client.post(f"/api/v1/meeting-assistant/calls/{call_id}/activate", json={}, headers=h)
    assert r.status_code == 422
    r = client.post(f"/api/v1/meeting-assistant/calls/{call_id}/activate", json={"notice_confirmed": True}, headers=h)
    assert r.status_code == 200, r.text
    estado = r.json()["data"]
    assert estado["active"] and estado["meeting_id"]
    r = client.post(f"/api/v1/collaboration/calls/{call_id}/transcribe-chunk", headers=h,
                    files={"audio": ("trozo.webm", b"\x1aE\xdf\xa3voz", "audio/webm")})
    assert r.json()["text"] == "Propongo cerrar el sprint el viernes"
    from app.models.ai_chat import AIMeeting
    m = db.query(AIMeeting).filter(AIMeeting.id == estado["meeting_id"]).one()
    assert m.origin == "chat_call" and m.call_id == call_id and m.conversation_id
    (s,) = m.segmentos
    assert s.user_id == "admin-test-id" and s.speaker and len(m.audios) == 1
    # Colgar encola el cierre del asistente.
    client.post(f"/api/v1/collaboration/calls/{call_id}/end", headers=h)
    assert ("cerrar", (call_id, "1")) in simulados


def test_al_colgar_se_analiza_y_se_publica_el_enlace(client, db, admin_token, simulados, monkeypatch):
    from app.models.ai_chat import AIMeeting
    from app.models.collaboration import CollaborationMessage
    from app.services import s3_service
    from app.services.reuniones import llamadas
    monkeypatch.setattr(s3_service.file_storage, "upload_file", lambda **k: ("documents/x/v1/acta.html", 9))
    h = auth(admin_token)
    call_id = _llamada(client, h)
    client.post(f"/api/v1/meeting-assistant/calls/{call_id}/activate", json={"notice_confirmed": True}, headers=h)
    client.post(f"/api/v1/collaboration/calls/{call_id}/transcribe-chunk", headers=h,
                files={"audio": ("t.webm", b"voz", "audio/webm")})
    m = llamadas.reunion_de(db, call_id)
    llamadas._terminar(db, m, None)
    db.commit()
    m = db.query(AIMeeting).filter(AIMeeting.id == m.id).one()
    assert m.status == "lista" and m.summary == "Se cierra el sprint." and m.minutes_document_id
    cuerpos = [x.body for x in db.query(CollaborationMessage).filter(
        CollaborationMessage.conversation_id == m.conversation_id).all()]
    assert any(f"/meetings-ai?meeting={m.id}" in (b or "") for b in cuerpos)
    assert any("graba" in (b or "").lower() for b in cuerpos)   # aviso al activar


def test_quien_dice_no_no_queda_grabado(client, db, admin_token, simulados):
    from app.services.reuniones import llamadas, servicio
    h = auth(admin_token)
    call_id = _llamada(client, h)
    client.post(f"/api/v1/meeting-assistant/calls/{call_id}/activate", json={"notice_confirmed": True}, headers=h)
    m = llamadas.reunion_de(db, call_id)
    admin = db.query(User).filter(User.id == "admin-test-id").one()
    servicio.consentir(db, admin, m, None, False)
    db.commit()
    assert llamadas.transcribir_si_graba(db, admin, call_id, b"x", "t.webm", "audio/webm") is None
    assert llamadas.registrar_fragmento(db, admin, call_id, "no debe guardarse", b"x") is False
    assert not m.segmentos and not m.audios


def test_sin_asistente_la_llamada_sigue_como_siempre(client, db, admin_token, monkeypatch):
    from app.services.reuniones import llamadas
    h = auth(admin_token)
    call_id = _llamada(client, h)
    admin = db.query(User).filter(User.id == "admin-test-id").one()
    assert llamadas.transcribir_si_graba(db, admin, call_id, b"x", "t.webm", "audio/webm") is None
    assert llamadas.registrar_fragmento(db, admin, call_id, "hola") is False
    r = client.get(f"/api/v1/meeting-assistant/calls/{call_id}", headers=h).json()["data"]
    assert r["active"] is False and r["meeting_id"] is None and r["notice_text"]
