"""Motor semántico: el desempate con IA no pisa a un experto ni inventa usuarios (revisión 2026-11).

Medido antes: la respuesta del modelo se guardaba como corrección de experto
(sobrescribiendo la de una persona para el mismo texto) y no se comprobaba que
el usuario devuelto fuese un candidato.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.models.semantic_engine import SemFeedback
from app.services import ai_provider_service
from app.services.semantic_classifier import SemanticAssigner, _text_hash

TEXTO = "La VPN no conecta desde casa"
CANDIDATOS = [SimpleNamespace(user_id="u-ana", profile_text="redes y VPN"),
              SimpleNamespace(user_id="u-luis", profile_text="facturación")]


def _asignador(db, respuesta, monkeypatch):
    monkeypatch.setattr(ai_provider_service, "call_ai", lambda *a, **k: respuesta)
    return SemanticAssigner(db)


def test_EL_HALLAZGO_no_pisa_la_correccion_del_experto(db, monkeypatch):
    db.add(SemFeedback(text_hash=_text_hash(TEXTO), text_snippet=TEXTO, embedding="[]", item_type="ticket",
                       correct_user_id="u-luis", corrected_by="experto"))
    db.commit()
    r = _asignador(db, '{"user_id": "u-ana", "reason": "sabe de VPN"}', monkeypatch)._llm_suggest(TEXTO, CANDIDATOS, "ticket")
    assert r and r["suggested_user_id"] == "u-ana"
    db.expire_all()
    fb = db.query(SemFeedback).filter(SemFeedback.text_hash == _text_hash(TEXTO)).one()
    assert (fb.correct_user_id, fb.corrected_by) == ("u-luis", "experto")


def test_EL_HALLAZGO_un_usuario_que_no_es_candidato_no_vale(db, monkeypatch):
    r = _asignador(db, '{"user_id": "u-inventado"}', monkeypatch)._llm_suggest(TEXTO, CANDIDATOS, "ticket")
    assert r is None


def test_sin_proveedor_no_hay_sugerencia(db, monkeypatch):
    r = _asignador(db, ai_provider_service.AVISO_SIN_PROVEEDOR, monkeypatch)._llm_suggest(TEXTO, CANDIDATOS, "ticket")
    assert r is None
