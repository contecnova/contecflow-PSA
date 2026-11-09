"""Editor de IA en línea: no pierde el texto ni llena el historial (revisión 2026-11).

Medido antes: usaba /ai/chat, cada uso abría una conversación, y si no había
proveedor ponía el aviso en lugar del texto del usuario.
"""
from __future__ import annotations

from app.models.ai_chat import AIConversation
from app.services import ai_provider_service as s
from tests.conftest import auth


def test_EL_HALLAZGO_sin_proveedor_es_un_error_y_no_un_texto(client, db, pm_token, monkeypatch):
    import app.api.v1.endpoints.ai_chat as ep
    monkeypatch.setattr(ep, "call_ai", lambda *a, **k: s.AVISO_SIN_PROVEEDOR)
    antes = db.query(AIConversation).count()
    r = client.post("/api/v1/ai/texto", headers=auth(pm_token), json={"mensaje": "Mejora: hola"})
    assert r.status_code == 503 and db.query(AIConversation).count() == antes


def test_con_proveedor_devuelve_el_texto_sin_guardar_conversacion(client, db, pm_token, monkeypatch):
    import app.api.v1.endpoints.ai_chat as ep
    visto = {}
    monkeypatch.setattr(ep, "call_ai", lambda db_, msgs, **k: visto.update(k) or "Hola, buenos días.")
    antes = db.query(AIConversation).count()
    r = client.post("/api/v1/ai/texto", headers=auth(pm_token), json={"mensaje": "Mejora: hola"})
    assert r.json()["data"]["texto"] == "Hola, buenos días." and visto["module"] == "inline_editor"
    assert db.query(AIConversation).count() == antes
