"""La transcripción y el resumen de reuniones pasan por el control de IA de la empresa (revisión 2026-11).

El resumen llamaba a OpenAI directamente con la clave del `.env`; la
transcripción no respetaba el tope ni se apuntaba.
"""
from __future__ import annotations

import pytest

from app.models.ai_providers import AIUsageLog
from app.services import settings_service
from app.services import stt
from app.services.ai_provider_service import PresupuestoDeIAAgotado
from app.services.collaboration import _transcription as tr


class _Prov:
    name = "doble"

    def transcribe(self, data, filename, content_type, language=None):
        return stt.STTResult(text="hola", provider="doble", model="m-stt")


@pytest.fixture(autouse=True)
def _cache():
    settings_service.invalidate_cache()
    yield
    settings_service.invalidate_cache()


def _uso(db, modulo):
    from app.db.session import sin_filtro_de_tenant
    with sin_filtro_de_tenant(db):
        return db.query(AIUsageLog).filter(AIUsageLog.module == modulo).all()


def test_la_transcripcion_se_apunta_y_respeta_el_tope(db, monkeypatch):
    monkeypatch.setattr(stt, "_ordered_providers", lambda db=None, org_id=None: [_Prov()])
    assert tr.transcribe_audio_chunk(b"x", "a.webm", db=db, org_id="1") == "hola"
    (fila,) = _uso(db, "voice")
    assert fila.organization_id == "1" and fila.model == "m-stt" and fila.cost_usd == 0
    settings_service.set_runtime_value(db, "ai", "AI_DAILY_BUDGET_USD", 0.1, "1")
    db.add(AIUsageLog(organization_id="1", module="general", cost_usd=1.0, success=True, tokens_in=0, tokens_out=0))
    db.commit()
    settings_service.invalidate_cache()
    with pytest.raises(PresupuestoDeIAAgotado):
        stt.transcribe_audio(b"x", "a.webm", "audio/webm", db=db, org_id="1")


def test_EL_HALLAZGO_el_resumen_va_por_call_ai_con_la_empresa(db, monkeypatch):
    vistos = []

    def falso(db_, messages, **k):
        vistos.append(k)
        return '{"summary": "Se acordó migrar.", "actions": [{"text": "Migrar", "owner": "Ana"}]}'
    monkeypatch.setattr("app.services.ai_provider_service.call_ai", falso)
    monkeypatch.setenv("OPENAI_API_KEY", "no-debe-usarse")
    resumen, acciones = tr.summarize_text("Hablamos de la migración y Ana se encarga.", db=db, organization_id="1")
    assert resumen == "Se acordó migrar." and acciones == [{"text": "Migrar", "owner": "Ana"}]
    assert vistos[0]["module"] == "meeting_assistant" and vistos[0]["organization_id"] == "1"


def test_sin_ia_queda_el_resumen_heuristico(db, monkeypatch):
    monkeypatch.setattr("app.services.ai_provider_service.call_ai",
                        lambda *a, **k: (_ for _ in ()).throw(PresupuestoDeIAAgotado("tope")))
    resumen, _ = tr.summarize_text("Primera frase bastante larga de la reunión. Segunda frase también larga aquí.",
                                   db=db, organization_id="1")
    assert resumen.startswith("• Primera frase")
