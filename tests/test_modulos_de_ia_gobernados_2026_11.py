"""Gobierno de IA: cada interruptor apaga su módulo y el tope diario cuenta (revisión 2026-11).

Medido antes: sólo NexusAssist y NexusAgent comprobaban su interruptor, y los
registros se guardaban con otro nombre (`contecflowassist`…), así que el tope
diario y el uso por módulo no casaban nunca.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core.modulos_ia import comprobar_modulo
from app.models.ai_chat import AIActionLog, AIGovernanceConfig
from tests.conftest import auth


def _apagar(client, token, modulo):
    r = client.patch(f"/api/v1/governance/config/{modulo}", headers=auth(token), json={"is_enabled": False})
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("modulo,ruta,cuerpo", [
    ("voice", "/api/v1/ai-modules/voice/command", {"transcript": "crea una tarea"}),
    ("knowledge_base", "/api/v1/ai-modules/kb/search", {"query": "vpn"}),
    ("meeting_assistant", "/api/v1/ai-modules/meetings/process", {"title": "R", "transcript": "x"}),
    ("nexusoracle", "/api/v1/ai-modules/oracle/run", None),
])
def test_EL_HALLAZGO_un_modulo_apagado_no_responde(client, admin_token, modulo, ruta, cuerpo):
    _apagar(client, admin_token, modulo)
    r = client.post(ruta, headers=auth(admin_token), json=cuerpo) if cuerpo is not None else client.post(ruta, headers=auth(admin_token))
    assert r.status_code == 403, r.text
    assert "Gobierno de IA" in r.json()["detail"]


def test_EL_HALLAZGO_el_tope_diario_cuenta_con_el_nombre_de_gobierno(db):
    db.add(AIGovernanceConfig(organization_id="1", module="nexusassist", is_enabled=True, max_actions_per_day=1))
    db.add(AIActionLog(user_id="dev-test-id", module="nexusassist", action_type="chat"))
    db.commit()
    with pytest.raises(HTTPException) as e:
        comprobar_modulo(db, "1", "nexusassist", "dev-test-id")
    assert e.value.status_code == 429
