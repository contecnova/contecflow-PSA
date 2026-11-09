"""Motor semántico: vectores comparables y backend real (revisión 2026-11).

Medido en el código: con TF-IDF el vocabulario se fija en cada asignador, pero
los vectores de perfiles y correcciones se guardaron con uno anterior; con otra
longitud el coseno daba 0 y el ranking dependía sólo de la carga.
"""
from __future__ import annotations

import json

from app.models.semantic_engine import SemProfile
from app.services import semantic_engine_service
from app.services.semantic_classifier import SemanticAssigner, _cosine


def test_EL_HALLAZGO_un_vector_guardado_con_otro_vocabulario_se_recalcula(db):
    a = SemanticAssigner(db)
    actual = a._encode_single("redes vpn cortafuegos")
    viejo = json.dumps([0.5, 0.5])  # otra longitud: el vocabulario de antes
    v = a._vector_comparable(viejo, "redes vpn cortafuegos", len(actual))
    assert len(v) == len(actual) and _cosine(actual, v) > 0.99


def test_el_backend_en_uso_dice_tfidf_si_no_hay_transformer(db, monkeypatch):
    import importlib.util
    cfg = semantic_engine_service.get_or_create_config(db)
    cfg.local_model_name = "all-MiniLM-L6-v2"
    monkeypatch.setattr(importlib.util, "find_spec", lambda n: None)
    from app.services import semantic_classifier as sc
    monkeypatch.setattr(sc, "_MODEL_INSTANCE", None)
    datos = semantic_engine_service.serialize_config(cfg)
    assert datos["embeddings_backend"] == "transformer" and datos["backend_en_uso"] == "tfidf"
