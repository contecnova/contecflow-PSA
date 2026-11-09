"""NexusAssist guarda el mensaje ya redactado por la política (revisión 2026-11).

Medido antes: el mensaje se guardaba tal cual antes de aplicar las políticas de
entrada; sólo se redactaba lo que iba al proveedor, así que el dato sensible
quedaba en el historial de la conversación.
"""
from __future__ import annotations

from app.models.ai_chat import AIMessage
from app.services import ai_provider_service
from app.services.ai_governance import GuardrailResult
from tests.conftest import auth


def test_EL_HALLAZGO_el_historial_guarda_lo_redactado_y_un_bloqueo_no_guarda_nada(client, pm_token, db, monkeypatch):
    def entrada(texto, user, module, db, request_id=None):
        if "prohibido" in texto:
            return GuardrailResult(allowed=False, redacted_text=None, action_taken="block", blocked_by="lista")
        return GuardrailResult(allowed=True, redacted_text=texto.replace("4111", "[TARJETA]"), action_taken="redact")
    monkeypatch.setattr("app.services.ai_governance.check_prompt", entrada)
    monkeypatch.setattr(ai_provider_service, "call_ai", lambda *a, **k: "Hecho.")
    monkeypatch.setattr("app.api.v1.endpoints.ai_chat.call_ai", lambda *a, **k: "Hecho.", raising=False)

    r = client.post("/api/v1/ai/chat", headers=auth(pm_token), json={"message": "Mi tarjeta es 4111 1111"})
    assert r.status_code == 200, r.text
    contenidos = [m.content for m in db.query(AIMessage).filter(AIMessage.role == "user").all()]
    assert contenidos and all("4111" not in c for c in contenidos)

    antes = db.query(AIMessage).count()
    r = client.post("/api/v1/ai/chat", headers=auth(pm_token), json={"message": "esto está prohibido"})
    assert r.status_code == 400
    db.expire_all()
    assert db.query(AIMessage).count() == antes
