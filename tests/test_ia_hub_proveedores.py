"""Hub de IA: proveedor y modelo por función, respaldo ordenado, pausa tras error
y probar/descubrir sin guardar (revisión 2026-11, lo que contecmind tenía)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.ai_providers import AIProvider
from app.services import ai_provider_service as ia
from tests.conftest import auth


@pytest.fixture
def llamadas(monkeypatch):
    vistas = []

    def _falso(p, messages, system=None, model=None, max_tokens=None, temperature=None):
        vistas.append((p.name, model))
        if getattr(p, "_falla", False) or p.name.startswith("Roto"):
            raise ConnectionError("caído")
        return {"text": "ok", "model": model or p.default_model, "tokens_in": 1, "tokens_out": 1}
    monkeypatch.setattr(ia, "call_provider", _falso)
    return vistas


def _proveedor(db, nombre, **extra):
    p = AIProvider(name=nombre, provider="openai", default_model="gpt-4o-mini", organization_id="1",
                   status="active", is_active=True, **extra)
    db.add(p)
    db.commit()
    return p


def _llamar(db, module="general"):
    return ia.call_ai(db, [{"role": "user", "content": "hola"}], module=module,
                      is_superadmin=False, organization_id="1", skip_guardrails=True)


def test_EL_HALLAZGO_cada_funcion_usa_su_proveedor_y_modelo(client, admin_token, db, llamadas):
    _proveedor(db, "General", is_default=True)
    barato = _proveedor(db, "Barato")
    r = client.put("/api/v1/ai-providers/routing", headers=auth(admin_token),
                   json={"routes": {"ask_the_data": {"provider_id": barato.id, "model": "gpt-4.1-nano"}}})
    assert r.status_code == 200, r.text
    _llamar(db, "ask_the_data")
    _llamar(db, "nexusassist")
    assert llamadas == [("Barato", "gpt-4.1-nano"), ("General", "gpt-4o-mini")]


def test_la_ruta_no_acepta_un_proveedor_de_otra_empresa(client, admin_token, db):
    otro = AIProvider(name="Ajeno", provider="openai", organization_id="org-otra", status="active", is_active=True)
    db.add(otro)
    db.commit()
    r = client.put("/api/v1/ai-providers/routing", headers=auth(admin_token),
                   json={"routes": {"ask_the_data": {"provider_id": otro.id}}})
    assert r.status_code == 400


def test_EL_HALLAZGO_el_respaldo_sigue_la_prioridad(db, llamadas):
    _proveedor(db, "Roto principal", is_default=True)
    _proveedor(db, "Segundo", priority=50)
    _proveedor(db, "Primero", priority=10)
    _llamar(db)
    assert [n for n, _ in llamadas] == ["Roto principal", "Primero"]


def test_EL_HALLAZGO_un_proveedor_en_error_vuelve_tras_la_pausa(db, llamadas):
    p = _proveedor(db, "Principal", is_default=True)
    p.status, p.last_error_at = "error", datetime.now(timezone.utc) - timedelta(seconds=10)
    _proveedor(db, "Respaldo")
    db.commit()
    _llamar(db)
    assert llamadas[0][0] == "Respaldo", "dentro de la pausa no se usa"
    p.last_error_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()
    llamadas.clear()
    _llamar(db)
    assert llamadas[0][0] == "Principal", "pasada la pausa se reintenta"
    db.expire_all()
    assert db.get(AIProvider, p.id).status == "active"


def test_probar_y_descubrir_sin_guardar(client, admin_token, db, llamadas, monkeypatch):
    monkeypatch.setattr(ia, "list_models_for_provider", lambda p: ["m1", "m2"] if p.api_key else [])
    antes = db.query(AIProvider).count()
    datos = {"provider": "openai", "api_key": "sk-escrita", "default_model": "gpt-4o-mini"}
    r = client.post("/api/v1/ai-providers/test-config", headers=auth(admin_token), json=datos)
    assert r.status_code == 200 and r.json()["data"]["ok"], r.text
    r = client.post("/api/v1/ai-providers/discover-models", headers=auth(admin_token), json=datos)
    assert r.json()["data"]["models"] == ["m1", "m2"]
    assert db.query(AIProvider).count() == antes, "nada se guarda"


@pytest.fixture
def gemini_en_env(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "AI_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "AI_API_KEY", "clave-del-env")
    monkeypatch.setattr(settings, "AI_MODEL", "gemini-2.0-flash")


def test_EL_HALLAZGO_el_proveedor_del_env_aparece_como_activo(client, admin_token, db, gemini_en_env):
    items = client.get("/api/v1/ai-providers", headers=auth(admin_token)).json()["items"]
    env = [i for i in items if i.get("source") == "env"]
    assert len(env) == 1 and env[0]["provider"] == "gemini" and env[0]["is_default"] is True
    assert env[0]["has_api_key"] is True and "clave-del-env" not in str(env)


def test_el_proveedor_del_env_se_importa_una_vez_con_la_clave_cifrada(client, admin_token, db, gemini_en_env):
    from app.core.encryption import decrypt_value
    r = client.post("/api/v1/ai-providers/env/import", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    fila = db.query(AIProvider).filter(AIProvider.provider == "gemini").one()
    assert fila.api_key != "clave-del-env" and decrypt_value(fila.api_key) == "clave-del-env"
    assert fila.default_model == "gemini-2.0-flash" and fila.organization_id == "1"
    assert client.post("/api/v1/ai-providers/env/import", headers=auth(admin_token)).status_code == 409


def _gemini(monkeypatch, *respuestas):
    from types import SimpleNamespace
    cola, topes = iter(respuestas), []

    def post(url, json=None, **k):
        topes.append(json["generationConfig"]["maxOutputTokens"])
        return SimpleNamespace(status_code=200, json=lambda: next(cola))
    monkeypatch.setattr(ia.httpx, "post", post)
    return topes


_MENSAJE = [{"role": "user", "content": "hola"}]


def test_EL_HALLAZGO_gemini_que_razona_sin_texto_reintenta_y_si_no_da_un_error_claro(monkeypatch):
    """Forma medida con la API real (gemini-2.5-flash, maxOutputTokens=10)."""
    sin_texto = {"candidates": [{"content": {"role": "model"}, "finishReason": "MAX_TOKENS"}],
                 "usageMetadata": {"promptTokenCount": 4, "thoughtsTokenCount": 7}}
    con_texto = {"candidates": [{"content": {"role": "model", "parts": [{"text": "OK"}]}, "finishReason": "STOP"}],
                 "usageMetadata": {"promptTokenCount": 4, "candidatesTokenCount": 1, "thoughtsTokenCount": 20}}
    topes = _gemini(monkeypatch, sin_texto, con_texto)
    r = ia._call_gemini("k", "gemini-2.5-flash", _MENSAJE, None, 10, 0.2)
    assert r["text"] == "OK" and topes == [10, 17]
    assert r["tokens_out"] == 7 + 21, "se factura el razonamiento de los dos intentos"
    _gemini(monkeypatch, sin_texto, sin_texto)
    with pytest.raises(ValueError, match="razonamiento"):
        ia._call_gemini("k", "gemini-2.5-flash", _MENSAJE, None, 10, 0.2)


def test_EL_HALLAZGO_gemini_cortado_a_media_frase_se_completa(monkeypatch):
    """Medido 2026-11-09: el resumen ejecutivo acababa en «una falta crítica de»."""
    cortado = {"candidates": [{"content": {"parts": [{"text": "El portfolio presenta una falta crítica de"}]},
                               "finishReason": "MAX_TOKENS"}],
               "usageMetadata": {"candidatesTokenCount": 9, "thoughtsTokenCount": 790}}
    entero = {"candidates": [{"content": {"parts": [{"text": "El portfolio presenta una falta crítica de datos."}]},
                              "finishReason": "STOP"}],
              "usageMetadata": {"candidatesTokenCount": 11, "thoughtsTokenCount": 700}}
    topes = _gemini(monkeypatch, cortado, entero)
    r = ia._call_gemini("k", "gemini-2.5-flash", _MENSAJE, None, 800, 0.2)
    assert r["text"].endswith("datos.") and not r["truncado"] and topes == [800, 1590]


def test_EL_HALLAZGO_la_pausa_tras_error_se_ajusta_desde_admin(db, llamadas):
    """Medido 2026-11-05: el ajuste estaba en Admin y se leía solo de `.env`."""
    from app.services import settings_service
    p = _proveedor(db, "Principal", is_default=True)
    p.status, p.last_error_at = "error", datetime.now(timezone.utc) - timedelta(seconds=30)
    _proveedor(db, "Respaldo")
    db.commit()
    _llamar(db)
    assert llamadas[0][0] == "Respaldo", "con la pausa por defecto (300 s) sigue apartado"
    settings_service.set_runtime_value(db, "ai", "AI_PROVIDER_ERROR_COOLDOWN_SECONDS", 10, None)
    db.commit()
    settings_service.invalidate_cache()
    llamadas.clear()
    _llamar(db)
    assert llamadas[0][0] == "Principal", "con 10 s desde Admin, ya vuelve"
