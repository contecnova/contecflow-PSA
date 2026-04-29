"""tests/test_voice_agent.py — Tests for Voice Agent IVR endpoints."""
import pytest
from tests.conftest import auth


def test_get_ivr_config(client, admin_token):
    r = client.get("/api/v1/sd/voice/config", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()
    assert "greeting" in data
    assert "dtmf_menu" in data


def test_update_ivr_config(client, admin_token):
    payload = {"greeting": "Bienvenido. Pulse 1 para soporte.", "language": "es-ES"}
    r = client.put("/api/v1/sd/voice/config", json=payload, headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()
    assert data["greeting"] == "Bienvenido. Pulse 1 para soporte."


def test_create_voice_session(client, admin_token):
    payload = {"caller_id": "+34600000001", "channel": "phone"}
    r = client.post("/api/v1/sd/voice/sessions", json=payload, headers=auth(admin_token))
    assert r.status_code == 201
    data = r.json()
    assert "session" in data
    assert data["session"]["caller_id"] == "+34600000001"
    assert "greeting" in data


def test_add_transcript_turn(client, admin_token):
    res = client.post("/api/v1/sd/voice/sessions", json={"caller_id": "+34600000002"}, headers=auth(admin_token))
    session_id = res.json()["session"]["id"]

    r = client.post(
        f"/api/v1/sd/voice/sessions/{session_id}/turn",
        json={"speaker": "user", "text": "tengo un error urgente en producción"},
        headers=auth(admin_token),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["intent"] in ("incident", "urgent", "unknown")


def test_list_sessions(client, admin_token):
    client.post("/api/v1/sd/voice/sessions", json={"caller_id": "+34600000003"}, headers=auth(admin_token))
    r = client.get("/api/v1/sd/voice/sessions", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()
    assert "sessions" in data
    assert data["count"] >= 1


def test_close_session(client, admin_token):
    res = client.post("/api/v1/sd/voice/sessions", json={"caller_id": "+34600000004"}, headers=auth(admin_token))
    session_id = res.json()["session"]["id"]

    r = client.post(
        f"/api/v1/sd/voice/sessions/{session_id}/close",
        json={"resolution": "resolved"},
        headers=auth(admin_token),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "closed"


def test_create_ticket_from_session(client, admin_token):
    res = client.post("/api/v1/sd/voice/sessions", json={"caller_id": "+34600000005"}, headers=auth(admin_token))
    session_id = res.json()["session"]["id"]
    # Add some context
    client.post(f"/api/v1/sd/voice/sessions/{session_id}/turn", json={"speaker": "user", "text": "problema urgente servidor"}, headers=auth(admin_token))

    r = client.post(f"/api/v1/sd/voice/sessions/{session_id}/ticket", headers=auth(admin_token))
    assert r.status_code == 201
    data = r.json()
    assert "id" in data
    assert data["source"] == "voice_agent"


def test_voice_agent_requires_auth(client):
    r = client.get("/api/v1/sd/voice/sessions")
    assert r.status_code == 401
