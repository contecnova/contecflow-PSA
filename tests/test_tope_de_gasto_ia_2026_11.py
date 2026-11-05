"""Tope diario de gasto en IA por empresa (revisión 2026-11, lo que contecintelligence tenía).

Antes solo había un aviso en el log, que además sumaba el gasto de TODAS las
empresas. Ahora cada empresa decide un tope (AI_DAILY_BUDGET_USD, 0 = sin tope)
y al alcanzarlo sus llamadas se cortan hasta las 00:00 UTC.
"""
from __future__ import annotations

import pytest

from app.models.ai_providers import AIProvider, AIUsageLog
from app.services import ai_provider_service as ia
from app.services import settings_service
from tests.conftest import auth


@pytest.fixture
def proveedor(db, monkeypatch):
    db.add(AIProvider(name="P", provider="openai", default_model="m", organization_id="1", status="active",
                      is_active=True, is_default=True))
    db.commit()
    monkeypatch.setattr(ia, "call_provider", lambda p, messages, **k: {"text": "ok", "model": "m", "tokens_in": 1,
                                                                       "tokens_out": 1, "cost_usd": 0.4})


def _tope(db, valor, org="1"):
    settings_service.set_runtime_value(db, "ai", "AI_DAILY_BUDGET_USD", valor, org)
    db.commit()
    settings_service.invalidate_cache()


def _llamar(db, org="1"):
    return ia.call_ai(db, [{"role": "user", "content": "hola"}], module="general", is_superadmin=False,
                      organization_id=org, skip_guardrails=True)


def test_sin_tope_no_se_corta_y_el_uso_lleva_la_empresa(db, proveedor):
    db.info.clear()   # como un trabajo de fondo: sin contexto de empresa en la sesión
    for _ in range(3):
        assert _llamar(db) == "ok"
    from app.db.session import sin_filtro_de_tenant
    with sin_filtro_de_tenant(db):
        assert {u.organization_id for u in db.query(AIUsageLog)} == {"1"}
    assert abs(ia.gasto_de_hoy(db, "1") - 1.2) < 1e-6


def test_EL_HALLAZGO_al_alcanzar_el_tope_la_empresa_queda_cortada(db, proveedor):
    _tope(db, 1.0)
    _llamar(db)
    _llamar(db)
    _llamar(db)   # 1.2 USD: pasa porque al empezar llevaba 0.8
    with pytest.raises(ia.PresupuestoDeIAAgotado, match="límite diario"):
        _llamar(db)


def test_el_tope_es_de_cada_empresa(db, proveedor):
    from app.models.mfa import Organization
    db.add(Organization(id="org-ia", name="Otra", slug="org-ia"))
    db.commit()
    _tope(db, 0.4)
    _llamar(db)                      # 0.4 gastado: el tope se alcanza
    with pytest.raises(ia.PresupuestoDeIAAgotado):
        _llamar(db)
    assert ia.gasto_de_hoy(db, "org-ia") == 0
    # La otra empresa (sin tope propio ni gasto) sigue.
    db.add(AIProvider(name="P2", provider="openai", default_model="m", organization_id="org-ia", status="active",
                      is_active=True, is_default=True))
    db.commit()
    assert _llamar(db, "org-ia") == "ok"


def test_el_chat_dice_429_con_el_motivo_y_el_hub_lo_enseña(client, admin_token, pm_token, db, proveedor):
    _tope(db, 0.3)
    _llamar(db)
    r = client.post("/api/v1/ai/chat", headers=auth(pm_token), json={"message": "hola"})
    assert r.status_code == 429 and "límite diario" in r.json()["detail"]
    datos = client.get("/api/v1/ai-providers/spend-today", headers=auth(admin_token)).json()["data"]
    assert datos["blocked"] is True and datos["budget_usd"] == 0.3 and datos["used_pct"] >= 100
