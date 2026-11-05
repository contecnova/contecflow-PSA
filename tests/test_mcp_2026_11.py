"""Servidor MCP (revisión 2026-11, lo que contecintelligence ya tenía).

Las herramientas de NexusAgent para agentes externos, con el gobierno que ya
existía: módulo de Gobernanza IA (apagado sin configurar), solo lectura salvo
MCP_WRITE_MODE (off / approval / direct), alcance de la clave de API y registro de auditoría de IA.
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


def _escritura(db, valor):
    from app.services import settings_service
    modo = {True: "direct", False: "off"}.get(valor, valor)
    settings_service.set_runtime_value(db, "ai", "MCP_WRITE_MODE", modo, "1")
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



# ── Escritura con aprobación humana (revisión 2026-11) ──────────────────────

def _flujo_mcp(client, admin_token):
    from tests.test_approvals import add_step, create_workflow
    wf = create_workflow(client, admin_token, entity_type="mcp_action")
    add_step(client, admin_token, wf["id"], approver_type="role", approver_role="admin")


def _proyecto_mcp(db):
    from app.models.project import Project, ProjectStatus, ProjectType
    p = Project(code="MCP2", name="Por MCP", status=ProjectStatus.active, project_type=ProjectType.development,
                organization_id="1")
    db.add(p)
    db.commit()
    return p


def _pedir_tarea(client, token, proyecto_id, titulo):
    r = _rpc(client, "tools/call", {"name": "create_task", "arguments": {"project_id": proyecto_id, "title": titulo}},
             auth(token))
    return r.json()["result"]


def test_en_modo_aprobacion_se_anuncia_y_aparece_el_estado(client, admin_token, pm_token, db):
    _encender(client, admin_token)
    _escritura(db, "approval")
    herramientas = {t["name"]: t for t in _rpc(client, "tools/list", cabeceras=auth(pm_token)).json()["result"]["tools"]}
    assert "REQUIERE APROBACIÓN" in herramientas["create_task"]["description"]
    assert "mcp_action_status" in herramientas


def test_sin_flujo_para_mcp_action_no_se_hace_nada(client, admin_token, pm_token, db):
    from app.models.ai_chat import MCPPendingAction
    from app.models.task import Task
    _encender(client, admin_token)
    _escritura(db, "approval")
    p = _proyecto_mcp(db)
    r = _pedir_tarea(client, pm_token, p.id, "Sin flujo")
    assert r["isError"] is True and "mcp_action" in r["content"][0]["text"]
    db.expire_all()
    assert db.query(MCPPendingAction).count() == 0 and db.query(Task).filter(Task.title == "Sin flujo").count() == 0


def test_EL_HALLAZGO_la_escritura_espera_a_la_persona_y_se_ejecuta_al_aprobar(client, admin_token, pm_token, db):
    from app.models.task import Task
    _encender(client, admin_token)
    _escritura(db, "approval")
    _flujo_mcp(client, admin_token)
    p = _proyecto_mcp(db)
    r = _pedir_tarea(client, pm_token, p.id, "Aprobada por una persona")
    datos = r["structuredContent"]
    assert r["isError"] is False and datos["status"] == "pending_approval", r
    db.expire_all()
    assert db.query(Task).filter(Task.title == "Aprobada por una persona").count() == 0, "no se ejecuta al llamar"
    estado = _rpc(client, "tools/call", {"name": "mcp_action_status", "arguments": {"action_id": datos["action_id"]}},
                  auth(pm_token)).json()["result"]["structuredContent"]
    assert estado["status"] == "pending"
    d = client.post(f"/api/v1/approvals/requests/{datos['approval_request_id']}/decide", headers=auth(admin_token),
                    json={"decision": "approved"})
    assert d.status_code == 200, d.text
    db.expire_all()
    assert db.query(Task).filter(Task.title == "Aprobada por una persona").count() == 1
    estado = _rpc(client, "tools/call", {"name": "mcp_action_status", "arguments": {"action_id": datos["action_id"]}},
                  auth(pm_token)).json()["result"]["structuredContent"]
    assert estado["status"] == "executed" and estado["result"]


def test_rechazada_no_se_ejecuta_y_otro_no_ve_la_accion(client, admin_token, pm_token, dev_token, db):
    from app.models.task import Task
    _encender(client, admin_token)
    _escritura(db, "approval")
    _flujo_mcp(client, admin_token)
    p = _proyecto_mcp(db)
    datos = _pedir_tarea(client, pm_token, p.id, "Rechazada")["structuredContent"]
    d = client.post(f"/api/v1/approvals/requests/{datos['approval_request_id']}/decide", headers=auth(admin_token),
                    json={"decision": "rejected", "note": "no"})
    assert d.status_code == 200, d.text
    db.expire_all()
    assert db.query(Task).filter(Task.title == "Rechazada").count() == 0
    estado = _rpc(client, "tools/call", {"name": "mcp_action_status", "arguments": {"action_id": datos["action_id"]}},
                  auth(pm_token)).json()["result"]["structuredContent"]
    assert estado["status"] == "rejected"
    ajeno = _rpc(client, "tools/call", {"name": "mcp_action_status", "arguments": {"action_id": datos["action_id"]}},
                 auth(dev_token)).json()["result"]
    assert ajeno["isError"] is True


def test_un_modo_desconocido_no_abre_la_escritura(client, admin_token, db):
    _encender(client, admin_token)
    _escritura(db, "todo")
    assert "create_task" not in _nombres(_rpc(client, "tools/list", cabeceras=auth(admin_token)))


# ── Gobernanza por empresa (revisión 2026-11, medido en la copia) ───────────

def test_EL_HALLAZGO_lo_que_enciende_un_superadmin_vale_para_su_empresa(client, superadmin_token, pm_token, db):
    """Medido: el interruptor de un superadmin se guardaba sin empresa (fila global
    que el filtro esconde) y MCP seguía apagado para los PM de su empresa."""
    r = client.patch("/api/v1/governance/config/mcp", headers=auth(superadmin_token), json={"is_enabled": True})
    assert r.status_code == 200, r.text
    assert _rpc(client, "initialize", cabeceras=auth(pm_token)).status_code == 200


def test_el_interruptor_no_toca_la_fila_de_otra_empresa(client, superadmin_token, db):
    from app.models.ai_chat import AIGovernanceConfig
    from app.models.mfa import Organization
    db.add(Organization(id="org-gob", name="Otra", slug="org-gob"))
    db.flush()
    db.add(AIGovernanceConfig(module="voice", is_enabled=True, organization_id="org-gob"))
    db.commit()
    client.patch("/api/v1/governance/config/voice", headers=auth(superadmin_token), json={"is_enabled": False})
    from app.db.session import sin_filtro_de_tenant
    db.expire_all()
    with sin_filtro_de_tenant(db):
        assert db.query(AIGovernanceConfig).filter(AIGovernanceConfig.organization_id == "org-gob").one().is_enabled is True


def test_EL_HALLAZGO_lo_que_crea_un_superadmin_queda_en_su_empresa(client, superadmin_token, pm_token, db):
    """Medido en la copia: el flujo creado por el admin (superadmin) quedaba sin
    empresa y el agente de un PM respondía «no hay flujo para mcp_action»."""
    from app.models.billing_reports import ApprovalWorkflow
    from tests.test_approvals import create_workflow
    wf = create_workflow(client, superadmin_token, entity_type="mcp_action")
    from app.db.session import sin_filtro_de_tenant
    with sin_filtro_de_tenant(db):
        assert db.get(ApprovalWorkflow, wf["id"]).organization_id == "1"
