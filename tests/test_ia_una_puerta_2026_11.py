"""Toda la IA pasa por `call_ai` (revisión 2026-11).

Medido antes: el OCR de recibos, el chat con streaming y el respaldo de los
módulos de IA llamaban a Anthropic directamente, con `ANTHROPIC_API_KEY` o con
la credencial de interfaz, sin gobernanza ni tope de gasto; con un proveedor
configurado como Gemini, esas funciones no iban.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.services import ai_provider_service as s

ADJ = [{"media": "image/png", "datos": "QUJD"}]
MSG = [{"role": "user", "content": "lee esto", "adjuntos": ADJ}]


def test_cada_familia_traduce_los_adjuntos():
    a = s._con_adjuntos(MSG, "anthropic")[0]["content"]
    assert a[0] == {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "QUJD"}} and a[-1]["text"] == "lee esto"
    o = s._con_adjuntos(MSG, "openai")[0]["content"]
    assert o[1] == {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}}
    pdf = [{"role": "user", "content": "x", "adjuntos": [{"media": "application/pdf", "datos": "UERG"}]}]
    assert s._con_adjuntos(pdf, "anthropic")[0]["content"][0]["type"] == "document"
    assert s._con_adjuntos(pdf, "openai")[0]["content"][1]["type"] == "file"
    g = s._con_adjuntos(MSG, "gemini")[0]
    assert g["_partes"] == [{"inline_data": {"mime_type": "image/png", "data": "QUJD"}}]
    assert s._con_adjuntos(MSG, "ollama")[0]["images"] == ["QUJD"]
    with pytest.raises(ValueError, match="PDF"):
        s._con_adjuntos(pdf, "ollama")
    assert "adjuntos" not in s._con_adjuntos([{"role": "user", "content": "hola"}], "anthropic")[0]


def test_EL_HALLAZGO_el_ocr_funciona_con_gemini(db, monkeypatch):
    """Sin clave de Anthropic y con Gemini como proveedor: lo que llega a Gemini es la imagen."""
    from app.services import expense_service
    from app.core.config import settings
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "", raising=False)
    prov = s.ProveedorDeEntorno(proveedor="gemini", api_key="g", modelo="gemini-2.5-flash", base_url="")
    monkeypatch.setattr(s, "_seleccionar_proveedor", lambda *a, **k: prov)
    enviado = {}

    class R:
        status_code = 200
        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": json.dumps({"amount": 9, "category": "meals"})}]}}]}
    monkeypatch.setattr(s.httpx, "post", lambda url, json=None, **k: enviado.update(url=url, cuerpo=json) or R())
    r = (expense_service.ocr_receipt(db, None, b"\x89PNG", "image/png"))
    assert "generativelanguage" in enviado["url"] or ":generateContent" in enviado["url"]
    assert enviado["cuerpo"]["contents"][-1]["parts"][0]["inline_data"]["mime_type"] == "image/png"
    assert (r["amount"], r["category"]) == (9, "meals")


def test_la_credencial_de_interfaz_entra_por_la_puerta_comun(db, monkeypatch):
    from app.services import integration_credentials_service as ic
    from app.core.config import settings
    monkeypatch.setattr(settings, "AI_PROVIDER", "", raising=False)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "", raising=False)
    monkeypatch.setattr(ic, "get_credential", lambda db_, g, k, org_id=None: "sk-ui" if k == "anthropic_api_key" else None)
    p = s.get_default_provider(db, is_superadmin=False, organization_id="org-sin-proveedor")
    from app.core.encryption import decrypt_value
    assert (p.provider, decrypt_value(p.api_key)) == ("anthropic", "sk-ui")


def test_los_modulos_no_caen_a_anthropic_directo(db, monkeypatch):
    from app.services.ai_modules import _base
    monkeypatch.setattr(_base, "call_ai", lambda *a, **k: s.AVISO_SIN_PROVEEDOR)
    with pytest.raises(RuntimeError):
        _base.call_ai_unified(db, [{"role": "user", "content": "hola"}])
    assert not hasattr(_base, "call_claude")


def test_EL_HALLAZGO_nadie_llama_a_anthropic_por_su_cuenta():
    """Sólo la capa común y la de herramientas del agente (multiproveedor) hablan con su API."""
    raiz = Path(__file__).resolve().parents[1] / "app"
    permitidos = {"services/ai_provider_service/catalogo.py", "services/ai_provider_service/clientes.py",
                  "services/ai_tools.py", "services/integration_test_service.py"}
    fuera = []
    for f in raiz.rglob("*.py"):
        rel = f.relative_to(raiz).as_posix()
        if rel in permitidos or "config" in rel:
            continue
        if re.search(r"ANTHROPIC_API_URL|anthropic-version", f.read_text()):
            fuera.append(rel)
    assert fuera == []
