"""Los 429 de la IA dicen la causa (19-11-2026).

Antes todo corte del asistente salía como `ia_uso_no_permitido` («está
desactivado o has llegado al límite diario»). Ahora:

- `ia_modulo_desactivado` (`modulo`): el módulo está apagado en Gobierno de IA;
- `ia_limite_diario` (`n`, `modulo`): la persona llegó a su tope diario;
- `ia_presupuesto_diario_agotado` (`tope`): la empresa llegó a su tope diario de
  gasto en IA (`AI_DAILY_BUDGET_USD`); antes 429 sin código.

Cada código tiene su texto en `MENSAJES_DEL_OPERADOR` y en `err_srv` de
es/en/zh (lo mide `test_errores_del_operador_turnos`).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.codigos_de_error import MENSAJES_DEL_OPERADOR
from tests.conftest import auth

CODIGOS = ("ia_modulo_desactivado", "ia_limite_diario", "ia_presupuesto_diario_agotado")


def test_los_codigos_estan_en_el_catalogo_del_operador():
    for codigo in CODIGOS:
        assert codigo in MENSAJES_DEL_OPERADOR, codigo
    assert "ia_uso_no_permitido" not in MENSAJES_DEL_OPERADOR  # el genérico ya no se usa


def test_el_generico_ya_no_se_lanza():
    import pathlib
    raiz = pathlib.Path(__file__).resolve().parents[1] / "app"
    usos = [str(f) for f in raiz.rglob("*.py") if '"ia_uso_no_permitido"' in f.read_text(encoding="utf-8")]
    assert not usos, usos


@pytest.fixture
def modulo(monkeypatch):
    """Config de Gobierno de IA simulada para el módulo."""
    estado = {"config": None}
    from app.services import governance_service
    monkeypatch.setattr(governance_service, "config_de_modulo", lambda db, org, mod: estado["config"])
    return estado


def test_modulo_desactivado(db, modulo):
    from app.services.ai_chat.rate_limit_service import limite_de_uso
    modulo["config"] = SimpleNamespace(is_enabled=False, max_actions_per_day=None)
    codigo, datos, texto = limite_de_uso(db, "pm-test-id", "nexusassist")
    assert codigo == "ia_modulo_desactivado" and datos == {"modulo": "nexusassist"}
    assert "nexusassist" in texto


def test_limite_diario(db, modulo, monkeypatch):
    from app.services.ai_chat import rate_limit_service as rl
    modulo["config"] = SimpleNamespace(is_enabled=True, max_actions_per_day=0)
    assert rl.limite_de_uso(db, "pm-test-id", "nexusassist") is None  # sin tope
    from app.models.ai_chat import AIActionLog
    db.add(AIActionLog(user_id="pm-test-id", module="nexusassist", action_type="chat", status="success"))
    db.commit()
    modulo["config"] = SimpleNamespace(is_enabled=True, max_actions_per_day=1)
    codigo, datos, _texto = rl.limite_de_uso(db, "pm-test-id", "nexusassist")
    assert codigo == "ia_limite_diario" and datos == {"n": 1, "modulo": "nexusassist"}
    # El texto suelto de siempre sigue para MCP.
    assert rl.check_rate_limit(db, "pm-test-id", "nexusassist") == _texto


def test_sin_config_no_corta(db, modulo):
    from app.services.ai_chat.rate_limit_service import check_rate_limit, limite_de_uso
    assert limite_de_uso(db, "pm-test-id", "nexusassist") is None
    assert check_rate_limit(db, "pm-test-id", "nexusassist") is None


def test_el_chat_responde_429_con_la_causa(client, pm_token, monkeypatch):
    from app.services.ai_chat import rate_limit_service as rl
    monkeypatch.setattr(rl, "limite_de_uso", lambda db, u, m: ("ia_limite_diario", {"n": 3, "modulo": m}, "x"))
    r = client.post("/api/v1/ai/chat", json={"message": "hola"}, headers=auth(pm_token))
    assert r.status_code == 429
    assert r.json()["code"] == "ia_limite_diario"
    assert r.json()["params"] == {"n": 3, "modulo": "nexusassist"}


def test_presupuesto_agotado_lleva_codigo_y_tope():
    from app.services.ai_provider_service import PresupuestoDeIAAgotado
    e = PresupuestoDeIAAgotado("texto", tope=12.5)
    assert e.codigo == "ia_presupuesto_diario_agotado"
    assert e.params == {"tope": "12.50"}
    assert str(e) == "texto"


def test_el_manejador_global_del_presupuesto_da_codigo():
    import asyncio
    import json

    from app.main import _presupuesto_de_ia_agotado
    from app.services.ai_provider_service import PresupuestoDeIAAgotado
    resp = asyncio.run(_presupuesto_de_ia_agotado(None, PresupuestoDeIAAgotado("t", tope=3)))
    cuerpo = json.loads(resp.body)
    assert resp.status_code == 429
    assert cuerpo["code"] == "ia_presupuesto_diario_agotado" and cuerpo["params"] == {"tope": "3.00"}
