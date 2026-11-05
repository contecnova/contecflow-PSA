"""El tope diario de gasto en IA también frena a NexusAgent (revisión 2026-11).

El agente con herramientas pedía sus turnos directamente al proveedor
(`ai_tools.pedir_turno`), sin pasar por `call_ai`: el tope de la empresa no lo
frenaba y su gasto no se apuntaba. Ahora cada turno pasa por
`ai_provider_service.turno_de_agente`.
"""
from __future__ import annotations

import pytest

from app.models.ai_providers import AIUsageLog
from app.models.user import User
from app.services import ai_provider_service as ia
from app.services import ai_tools as herr
from app.services import settings_service
from app.services.ai_chat.agent_loop import run_tool_use_loop

# Un turno que pide una herramienta y otro que termina, con el uso que declara Anthropic.
PIDE = {"content": [{"type": "tool_use", "id": "t1", "name": "buscar", "input": {}}],
        "stop_reason": "tool_use", "usage": {"input_tokens": 1_000_000, "output_tokens": 0}}
TERMINA = {"content": [{"type": "text", "text": "Hecho."}], "stop_reason": "end_turn",
           "usage": {"input_tokens": 0, "output_tokens": 100_000}}
HERRAMIENTAS = [{"name": "buscar", "description": "b", "input_schema": {"type": "object", "properties": {}}}]


def _usuario(db):
    return db.query(User).filter(User.organization_id == "1").first()


def _bucle(db, usuario):
    return run_tool_use_loop(execute_tool=lambda *a: {"ok": True}, instruction="busca", system="s",
                             tools=HERRAMIENTAS, db=db, current_user=usuario, model="claude-sonnet-4-5",
                             api_key="k", auto_approve=True, provider="anthropic")


def _uso(db):
    from app.db.session import sin_filtro_de_tenant
    with sin_filtro_de_tenant(db):
        return db.query(AIUsageLog).filter(AIUsageLog.module == "nexusagent").all()


def test_cada_turno_apunta_tokens_y_coste_de_la_empresa(db, monkeypatch):
    respuestas = iter([PIDE, TERMINA])
    monkeypatch.setattr(herr, "_post", lambda *a, **k: next(respuestas))
    db.info.clear()   # como el worker: sin contexto de empresa en la sesión
    texto, _pasos, _n = _bucle(db, _usuario(db))
    assert texto == "Hecho."
    filas = _uso(db)
    assert len(filas) == 2 and {f.organization_id for f in filas} == {"1"}
    # claude-sonnet-4-5: 3 USD por millón de entrada, 15 por millón de salida.
    assert abs(sum(f.cost_usd for f in filas) - (3.0 + 1.5)) < 1e-9
    assert abs(ia.gasto_de_hoy(db, "1") - 4.5) < 1e-9


def test_EL_HALLAZGO_con_el_tope_alcanzado_el_agente_no_llama_al_proveedor(db, monkeypatch):
    settings_service.set_runtime_value(db, "ai", "AI_DAILY_BUDGET_USD", 2.0, "1")
    db.commit()
    settings_service.invalidate_cache()
    respuestas = iter([PIDE, TERMINA])
    llamadas = []
    monkeypatch.setattr(herr, "_post", lambda *a, **k: llamadas.append(1) or next(respuestas))
    # El tope se mira antes de CADA turno: el primero (con 0 gastado) pasa y
    # cuesta 3 USD; el segundo ya no sale, aunque sea la misma ejecución.
    with pytest.raises(ia.PresupuestoDeIAAgotado):
        _bucle(db, _usuario(db))
    assert len(llamadas) == 1
    with pytest.raises(ia.PresupuestoDeIAAgotado):
        _bucle(db, _usuario(db))
    assert len(llamadas) == 1          # una ejecución nueva tampoco llega al proveedor


def test_un_turno_que_falla_queda_apuntado_como_fallo(db, monkeypatch):
    def _cae(*a, **k):
        raise ConnectionError("sin red")
    monkeypatch.setattr(herr, "_post", _cae)
    with pytest.raises(ConnectionError):
        _bucle(db, _usuario(db))
    (fila,) = _uso(db)
    assert fila.success is False and "sin red" in fila.error_msg and fila.organization_id == "1"


@pytest.mark.parametrize("proveedor,crudo,esperado", [
    ("anthropic", {"usage": {"input_tokens": 7, "output_tokens": 3}}, (7, 3)),
    ("openai", {"usage": {"prompt_tokens": 7, "completion_tokens": 3}}, (7, 3)),
    ("groq", {"usage": {"prompt_tokens": 7, "completion_tokens": 3}}, (7, 3)),
    ("gemini", {"usageMetadata": {"promptTokenCount": 7, "candidatesTokenCount": 3}}, (7, 3)),
    ("gemini", {}, (0, 0)),
])
def test_el_uso_se_lee_del_campo_de_cada_proveedor(proveedor, crudo, esperado):
    assert herr.uso_del_turno(proveedor, crudo) == esperado


def test_la_via_en_streaming_tambien_esta_gobernada(db, monkeypatch):
    """La pantalla usa el streaming, que tiene su propio bucle (ai_chat.py)."""
    from app.api.v1.endpoints.ai_chat import _emitir_bucle_del_agente
    settings_service.set_runtime_value(db, "ai", "AI_DAILY_BUDGET_USD", 0.5, "1")
    db.commit()
    settings_service.invalidate_cache()
    db.add(AIUsageLog(organization_id="1", module="general", tokens_in=0, tokens_out=0, cost_usd=0.6, success=True))
    db.commit()
    llamadas = []
    monkeypatch.setattr(herr, "_post", lambda *a, **k: llamadas.append(1) or TERMINA)
    with pytest.raises(ia.PresupuestoDeIAAgotado):
        list(_emitir_bucle_del_agente(db, "busca", "s", True, _usuario(db), "k", "claude-sonnet-4-5",
                                      proveedor="anthropic", base_url=""))
    assert llamadas == []
