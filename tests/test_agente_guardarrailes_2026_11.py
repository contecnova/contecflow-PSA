"""NexusAgent pasa por las políticas de gobernanza de entrada y salida (revisión 2026-11).

Los turnos del agente no usan `call_ai`, así que sus guardarraíles no se le
aplicaban. Con un doble del motor de políticas: una palabra se bloquea y un
dato se redacta, en la instrucción y en la respuesta, por las dos vías.
"""
from __future__ import annotations

import json
from contextlib import contextmanager

import pytest

from app.models.ai_chat import AIAgentExecution
from app.models.user import User
from app.services import ai_tools as herr
from app.services.ai_governance import GuardrailResult

TERMINA = {"content": [{"type": "text", "text": "El IBAN del cliente es ES12 3456."}], "stop_reason": "end_turn"}


@pytest.fixture
def politicas(monkeypatch):
    vistas = {"modelo": []}

    def entrada(texto, user, module, db, request_id=None):
        if "prohibido" in texto:
            return GuardrailResult(allowed=False, redacted_text=None, action_taken="block", blocked_by="lista negra")
        return GuardrailResult(allowed=True, redacted_text=texto.replace("4111", "[TARJETA]"), action_taken="redact")

    def salida(texto, user, module, db, request_id=None):
        return GuardrailResult(allowed=True, redacted_text=texto.replace("ES12 3456", "[IBAN]"), action_taken="redact")
    monkeypatch.setattr("app.services.ai_governance.check_prompt", entrada)
    monkeypatch.setattr("app.services.ai_governance.check_output", salida)

    def modelo(url, cuerpo, cabeceras, nombre):
        vistas["modelo"].append(json.dumps(cuerpo, ensure_ascii=False))
        return TERMINA
    monkeypatch.setattr(herr, "_post", modelo)
    return vistas


def _pm(db):
    return db.query(User).filter(User.username == "pm_test").one()


def _por_streaming(db, monkeypatch, instruccion):
    from app.api.v1.endpoints import ai_chat
    monkeypatch.setattr("app.db.session.SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    eventos = ai_chat._emitir_eventos_de_agente(
        instruccion=instruccion, auto_approve=False, usuario=_pm(db), system="s", hay_herramientas=True,
        api_key="k", modelo="claude-sonnet-4-5", proveedor="anthropic")
    return [json.loads(e.decode().split("data:", 1)[1]) if isinstance(e, bytes) else json.loads(str(e).split("data:", 1)[1])
            for e in eventos]


def test_EL_HALLAZGO_streaming_bloquea_redacta_la_entrada_y_la_salida(db, monkeypatch, politicas):
    eventos = _por_streaming(db, monkeypatch, "cobra a la tarjeta 4111")
    assert "[TARJETA]" in politicas["modelo"][0] and "4111" not in politicas["modelo"][0]
    final = [e for e in eventos if e["type"] == "done"][0]
    assert final["result"] == "El IBAN del cliente es [IBAN]."
    politicas["modelo"].clear()
    eventos = _por_streaming(db, monkeypatch, "algo prohibido")
    assert eventos == [{"type": "error", "message": "[Mensaje bloqueado por política de gobernanza: lista negra]"}]
    assert politicas["modelo"] == []


def test_en_segundo_plano_tambien(db, monkeypatch, politicas):
    pm = _pm(db)
    monkeypatch.setattr("app.services.ai_provider_service.get_default_provider", lambda db_, **k: None)
    monkeypatch.setattr("app.services.ai_client.get_api_key", lambda: "k")

    @contextmanager
    def sesion():
        yield db
    monkeypatch.setattr("app.db.session.worker_db_session", sesion)
    from app.worker import run_agent_task
    for instruccion in ("cobra a la tarjeta 4111", "algo prohibido"):
        e = AIAgentExecution(user_id=pm.id, instruction=instruccion, status="pending", organization_id=pm.organization_id)
        db.add(e)
        db.commit()
        run_agent_task.run(e.id, instruccion, pm.id)
        db.refresh(e)
        if "prohibido" in instruccion:
            assert e.status == "failed" and "lista negra" in e.error
        else:
            assert e.status == "done" and e.result == "El IBAN del cliente es [IBAN]."
    assert len(politicas["modelo"]) == 1 and "[TARJETA]" in politicas["modelo"][0]
