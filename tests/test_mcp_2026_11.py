"""Servidor MCP (revisión 2026-11, lo que contecintelligence ya tenía).

Las herramientas de NexusAgent para agentes externos, con el gobierno que ya
existía: módulo de Gobernanza IA (apagado sin configurar), solo lectura salvo
MCP_ALLOW_WRITE, alcance de la clave de API y registro de auditoría de IA.
"""
from __future__ import annotations

import pytest

from app.models.ai_chat import AIActionLog
from tests.conftest import auth
from tests.test_claves_de_api_autentican import _clave, _sin_sesion

URL = "/api/v1/mcp"


def _rpc(client, metodo, params=None, cabeceras=None, rid=1):
    cuerpo = {"jsonrpc": "2.0", "id": rid, "method": metodo}
    if params is not None:
        cuerpo["params"] = params
    return client.post(URL, json=cuerpo, headers=cabeceras or {})


def _encender(client, admin_token):
    r = client.patch("/api/v1/governance/config/mcp", headers=auth(admin_token), json={"is_enabled": True})
    assert r.status_code == 200, r.text


def _escritura(db, valor: bool):
    from app.services import settings_service
    settings_service.set_runtime_value(db, "ai", "MCP_ALLOW_WRITE", valor, "1")
    db.commit()
    settings_service.invalidate_cache()


def _nombres(r):
    return {t["name"] for t in r.json()["result"]["tools"]}


def test_EL_HALLAZGO_apagado_hasta_que_la_empresa_lo_enciende(client, admin_token):
    assert _rpc(client, "initialize", cabeceras=auth(admin_token)).status_code == 403
    estado = client.get("/api/v1/governance/config", headers=auth(admin_token)).json()["items"]
    assert {m["module"]: m["is_enabled"] for m in estado}["mcp"] is False


def test_protocolo_basico(client, admin_token):
    _encender(client, admin_token)
    h = auth(admin_token)
    r = _rpc(client, "initialize", {"protocolVersion": "2025-03-26"}, h)
    assert r.json()["result"]["protocolVersion"] == "2025-03-26"
    assert _rpc(client, "ping", cabeceras=h).json()["result"] == {}
    assert client.post(URL, json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=h).status_code == 202
    assert client.post(URL, json=[{"jsonrpc": "2.0", "id": 1, "method": "ping"}], headers=h).status_code == 400
    assert _rpc(client, "nada", cabeceras=h).json()["error"]["code"] == -32601


def test_EL_HALLAZGO_solo_lectura_por_defecto_y_queda_auditado(client, admin_token, db):
    _encender(client, admin_token)
    h = auth(admin_token)
    nombres = _nombres(_rpc(client, "tools/list", cabeceras=h))
    assert "get_dashboard_summary" in nombres and "create_task" not in nombres
    r = _rpc(client, "tools/call", {"name": "get_dashboard_summary", "arguments": {}}, h)
    assert r.json()["result"]["isError"] is False, r.text
    r = _rpc(client, "tools/call", {"name": "create_task", "arguments": {"title": "x"}}, h)
    assert r.json()["result"]["isError"] is True
    acciones = {(a.action_type, a.status) for a in db.query(AIActionLog).filter(AIActionLog.module == "mcp")}
    assert acciones == {("get_dashboard_summary", "success"), ("create_task", "blocked")}


def test_con_escritura_permitida_la_clave_read_sigue_sin_escribir(client, admin_token, db):
    _encender(client, admin_token)
    _escritura(db, True)
    assert "create_task" in _nombres(_rpc(client, "tools/list", cabeceras=auth(admin_token)))
    lectura, escritura = _clave(client, admin_token, ("read",)), _clave(client, admin_token, ("write",))
    c = _sin_sesion(client)
    assert "create_task" not in _nombres(_rpc(c, "tools/list", cabeceras={"X-API-Key": lectura}))
    assert "create_task" in _nombres(_rpc(c, "tools/list", cabeceras={"X-API-Key": escritura}))


def test_un_token_de_area_no_abre_mcp(client, admin_token, db):
    _encender(client, admin_token)
    clave = _clave(client, admin_token, ("projects",))
    c = _sin_sesion(client)
    assert _rpc(c, "tools/list", cabeceras={"X-API-Key": clave}).status_code == 403


def test_el_limite_diario_de_la_gobernanza_se_aplica(client, admin_token, db):
    from app.models.ai_chat import AIGovernanceConfig
    _encender(client, admin_token)
    db.query(AIGovernanceConfig).filter(AIGovernanceConfig.module == "mcp").update({"max_actions_per_day": 1})
    db.commit()
    h = auth(admin_token)
    assert _rpc(client, "tools/call", {"name": "get_alerts", "arguments": {}}, h).json()["result"]["isError"] is False
    r = _rpc(client, "tools/call", {"name": "get_alerts", "arguments": {}}, h).json()["result"]
    assert r["isError"] is True and "límite diario" in r["content"][0]["text"]


def test_toda_herramienta_esta_clasificada():
    from app.services import mcp_service
    mcp_service._clasificar()
    nombres = {h["name"] for h in mcp_service._herramientas()}
    assert mcp_service.ESCRITURA <= nombres


def test_con_escritura_la_tarea_creada_queda_guardada(client, admin_token, db):
    from app.models.project import Project, ProjectStatus, ProjectType
    from app.models.task import Task
    p = Project(code="MCP1", name="Por MCP", status=ProjectStatus.active, project_type=ProjectType.development,
                organization_id="1")
    db.add(p)
    db.commit()
    _encender(client, admin_token)
    _escritura(db, True)
    r = _rpc(client, "tools/call", {"name": "create_task", "arguments": {"project_id": p.id, "title": "Desde un agente"}},
             auth(admin_token))
    assert r.json()["result"]["isError"] is False, r.text
    db.expire_all()
    assert db.query(Task).filter(Task.title == "Desde un agente").count() == 1
