"""Planes de cambio guardados antes de las claves, traducidos con la IA (20-11-2026).

Si la empresa no tiene la traducción activa en el canal `ticket` pero sí IA
(proveedor configurado y módulo `change_management` permitido), un plan sin
`_textos` se traduce al leer con la IA (`call_ai`, simulada aquí):

- una vez por plan e idioma (cache en `translation_cache` de la empresa);
- el tope diario de gasto agotado deja el plan tal cual con su código
  (`ia_presupuesto_diario_agotado` y `params`);
- el módulo apagado o sin proveedor: tal cual, con el aviso y «Regenerar».
"""
from __future__ import annotations

import json

import pytest

PLAN = {
    "change_id": "c", "rollback_steps": [
        {"step": 1, "action": "Detener el despliegue si está en curso", "responsible": "Gestor del cambio",
         "estimated_minutes": 5},
    ],
}
CLAVE = "sd.change.rollback.chg-ia"


def _plan():
    return json.loads(json.dumps(PLAN))


@pytest.fixture
def sin_traduccion(monkeypatch):
    """Canal `ticket` del servicio de traducción desactivado."""
    from app.services.traduccion import servicio
    monkeypatch.setattr(servicio, "traducir", lambda db_, org, textos, destino, **k: [
        servicio.Resultado(servicio.DESACTIVADA, destino, motivo="disabled") for _ in textos])


@pytest.fixture
def ia(monkeypatch):
    """IA simulada: proveedor presente y `call_ai` que traduce con prefijo."""
    from app.services import ai_provider_service
    from app.services.service_desk.change_impact_service import textos as mod

    llamadas = []

    def falsa(db_, mensajes, system=None, module=None, user_id=None, organization_id=None, **_):
        items = json.loads(mensajes[-1]["content"])["items"]
        llamadas.append({"module": module, "org": organization_id, "user": user_id, "items": items,
                         "system": system})
        destino = "zh" if "(language code zh)" in system else "en"
        return json.dumps({"items": [{"lang": "es", "text": f"[{destino}] {t}"} for t in items]})

    monkeypatch.setattr(mod, "_hay_proveedor", lambda db_, org: True)
    monkeypatch.setattr(ai_provider_service, "call_ai", falsa)
    return llamadas


def test_sin_traduccion_pero_con_ia_se_traduce_con_la_ia(db, sin_traduccion, ia):
    from app.services.service_desk.change_impact_service.textos import traducir_anterior
    plan = traducir_anterior(db, _plan(), "en", "1", "admin-test-id", clave_del_plan=CLAVE)
    paso = plan["rollback_steps"][0]
    assert paso["action"] == "[en] Detener el despliegue si está en curso"
    assert paso["responsible"] == "[en] Gestor del cambio"
    assert paso["estimated_minutes"] == 5  # números y códigos no se tocan
    assert plan["textos_anteriores"] == {"status": "translated", "reason": None, "regenerable": True,
                                         "via": "ai", "cached": False}
    assert len(ia) == 1 and ia[0]["module"] == "change_management" and ia[0]["org"] == "1"
    # La acción cuenta para el tope diario del módulo.
    from app.models.ai_chat import AIActionLog
    assert db.query(AIActionLog).filter(AIActionLog.module == "change_management",
                                        AIActionLog.action_type == "translate_old_change_plan").count() == 1


def test_cache_por_plan_e_idioma_no_repite_la_llamada(db, sin_traduccion, ia):
    from app.services.service_desk.change_impact_service.textos import traducir_anterior
    traducir_anterior(db, _plan(), "en", "1", "admin-test-id", clave_del_plan=CLAVE)
    otra = traducir_anterior(db, _plan(), "en", "1", "admin-test-id", clave_del_plan=CLAVE)
    assert len(ia) == 1
    assert otra["rollback_steps"][0]["action"] == "[en] Detener el despliegue si está en curso"
    assert otra["textos_anteriores"]["cached"] is True
    # Otro idioma u otro plan: otra entrada.
    zh = traducir_anterior(db, _plan(), "zh", "1", "admin-test-id", clave_del_plan=CLAVE)
    assert zh["rollback_steps"][0]["action"].startswith("[zh] ")
    traducir_anterior(db, _plan(), "en", "1", "admin-test-id", clave_del_plan="sd.change.testing.chg-ia")
    assert len(ia) == 3


def test_tope_de_gasto_agotado_sale_tal_cual_con_su_codigo(db, sin_traduccion, monkeypatch):
    from app.services import ai_provider_service
    from app.services.service_desk.change_impact_service import textos as mod

    def agotado(*a, **k):
        raise ai_provider_service.PresupuestoDeIAAgotado("tope", tope=5.0)

    monkeypatch.setattr(mod, "_hay_proveedor", lambda db_, org: True)
    monkeypatch.setattr(ai_provider_service, "call_ai", agotado)
    plan = mod.traducir_anterior(db, _plan(), "en", "1", "admin-test-id", clave_del_plan=CLAVE)
    assert plan["rollback_steps"][0]["action"] == "Detener el despliegue si está en curso"
    anteriores = plan["textos_anteriores"]
    assert anteriores["status"] == "unavailable" and anteriores["reason"] == "budget_exhausted"
    assert anteriores["code"] == "ia_presupuesto_diario_agotado"
    assert anteriores["params"] == {"tope": "5.00"}
    assert anteriores["regenerable"] is True


def test_modulo_de_ia_apagado_no_llama_y_sale_tal_cual(db, sin_traduccion, ia):
    from app.models.ai_chat import AIGovernanceConfig
    from app.services.service_desk.change_impact_service.textos import traducir_anterior
    db.add(AIGovernanceConfig(organization_id="1", module="change_management", is_enabled=False))
    db.commit()
    plan = traducir_anterior(db, _plan(), "en", "1", "admin-test-id", clave_del_plan=CLAVE)
    assert ia == []
    assert plan["rollback_steps"][0]["action"] == "Detener el despliegue si está en curso"
    assert plan["textos_anteriores"]["status"] == "disabled"
    assert plan["textos_anteriores"]["ai_reason"] == "ai_module_disabled"
    assert plan["textos_anteriores"]["regenerable"] is True


def test_tope_diario_del_modulo_con_su_codigo(db, sin_traduccion, ia):
    from app.models.ai_chat import AIActionLog, AIGovernanceConfig
    from app.services.service_desk.change_impact_service.textos import traducir_anterior
    db.add(AIGovernanceConfig(organization_id="1", module="change_management", is_enabled=True,
                              max_actions_per_day=1))
    db.add(AIActionLog(user_id="admin-test-id", module="change_management", action_type="x"))
    db.commit()
    plan = traducir_anterior(db, _plan(), "en", "1", "admin-test-id", clave_del_plan=CLAVE)
    assert ia == []
    assert plan["textos_anteriores"]["status"] == "unavailable"
    assert plan["textos_anteriores"]["code"] == "modulo_ia_limite_diario"


def test_sin_proveedor_sale_tal_cual_sin_llamar(db, sin_traduccion, monkeypatch):
    from app.services import ai_provider_service
    from app.services.service_desk.change_impact_service.textos import traducir_anterior

    def no_debe(*a, **k):
        raise AssertionError("sin proveedor no se llama a la IA")

    monkeypatch.setattr(ai_provider_service, "call_ai", no_debe)
    plan = traducir_anterior(db, _plan(), "en", "1", "admin-test-id", clave_del_plan=CLAVE)
    assert plan["rollback_steps"][0]["action"] == "Detener el despliegue si está en curso"
    assert plan["textos_anteriores"]["status"] == "disabled"
    assert plan["textos_anteriores"]["ai_reason"] == "provider_not_configured"


def test_con_la_traduccion_activa_no_se_usa_la_ia(db, monkeypatch, ia):
    from app.services.traduccion import servicio
    from app.services.service_desk.change_impact_service.textos import traducir_anterior
    monkeypatch.setattr(servicio, "traducir", lambda db_, org, textos, destino, **k: [
        servicio.Resultado(servicio.TRADUCIDO, destino, f"<{destino}> {t}") for t in textos])
    plan = traducir_anterior(db, _plan(), "en", "1", "admin-test-id", clave_del_plan=CLAVE)
    assert ia == []
    assert plan["rollback_steps"][0]["action"] == "<en> Detener el despliegue si está en curso"
    assert "via" not in plan["textos_anteriores"]
