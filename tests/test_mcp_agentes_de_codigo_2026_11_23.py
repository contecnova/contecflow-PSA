"""MCP para agentes de código (OpenCode, Claude Code), 23-11-2026.

Ver `docs/integraciones/MCP.md`. Lo crítico:

- autenticación: credencial MCP (`mcp:read` / `mcp:write`) que solo abre el
  servidor MCP, nunca el resto de la API ni la configuración de credenciales;
- cada herramienta pide la MISMA capacidad que su ruta REST;
- aislamiento por empresa (un ticket de otra empresa no existe para el agente);
- auditoría de cada escritura en `audit_log` (canal mcp, credencial, empresa,
  IP) sin datos personales (ni el texto del comentario);
- límite de uso por credencial y minuto (429 con Retry-After y código);
- protocolo Streamable HTTP (versiones, GET 405, Origin, respuestas 202);
- Mi cuaderno privado salvo que su dueño lo comparta con sus agentes.
"""
from __future__ import annotations

import json

import pytest

from app.models.ai_chat import AIActionLog
from app.models.enterprise import AuditLog
from tests.conftest import auth
from tests.test_claves_de_api_autentican import _sin_sesion

URL = "/api/v1/mcp"


@pytest.fixture(autouse=True)
def _limites_limpios():
    from app.services import mcp_service
    mcp_service.reiniciar_limites()
    yield
    mcp_service.reiniciar_limites()


def _rpc(client, metodo, params=None, cabeceras=None, rid=1):
    cuerpo = {"jsonrpc": "2.0", "id": rid, "method": metodo}
    if params is not None:
        cuerpo["params"] = params
    return client.post(URL, json=cuerpo, headers=cabeceras or {})


def _llamar(client, nombre, argumentos=None, cabeceras=None):
    return _rpc(client, "tools/call", {"name": nombre, "arguments": argumentos or {}}, cabeceras)


def _encender(client, admin_token, **ajustes):
    r = client.patch("/api/v1/mcp/estado", headers=auth(admin_token), json={"enabled": True, **ajustes})
    assert r.status_code == 200, r.text
    from app.services import settings_service
    settings_service.invalidate_cache()


def _credencial(client, token, scope="read") -> str:
    r = client.post("/api/v1/mcp/credenciales", headers=auth(token), json={"name": "portátil", "scope": scope})
    assert r.status_code == 200, r.text
    datos = r.json()["data"]
    assert datos["key"].startswith("nxpm_") and datos["scopes"] == [f"mcp:{scope}"]
    return datos["key"]


def _bearer(clave: str) -> dict:
    return {"Authorization": f"Bearer {clave}"}


def _nombres(r) -> set:
    return {t["name"] for t in r.json()["result"]["tools"]}


def _proyecto_y_tarea(db, asignado="admin-test-id"):
    from app.models.project import Project, ProjectStatus, ProjectType
    from app.models.task import Task
    p = Project(code="MCPA", name="Agentes", status=ProjectStatus.active, project_type=ProjectType.development,
                organization_id="1")
    db.add(p)
    db.flush()
    t = Task(code="TSK-901", title="Cache de sesiones", project_id=p.id, assignee_id=asignado,
             reporter_id="admin-test-id", organization_id="1")
    db.add(t)
    db.commit()
    return p, t


# ── Autenticación y alcance de la credencial ────────────────────────────────

def test_sin_credencial_401(client, admin_token):
    _encender(client, admin_token)
    c = _sin_sesion(client)
    assert _rpc(c, "initialize").status_code == 401


def test_EL_HALLAZGO_la_credencial_mcp_solo_abre_mcp(client, admin_token):
    _encender(client, admin_token)
    lectura = _credencial(client, admin_token, "read")
    escritura = _credencial(client, admin_token, "write")
    c = _sin_sesion(client)
    assert _rpc(c, "initialize", {"protocolVersion": "2025-06-18"}, _bearer(lectura)).status_code == 200
    # Ni el resto de la API...
    assert c.get("/api/v1/projects", headers=_bearer(lectura)).status_code == 403
    assert c.get("/api/v1/projects", headers=_bearer(escritura)).status_code == 403
    # ...ni su propia configuración ni sus credenciales (vedadas a toda credencial delegada).
    assert c.get("/api/v1/mcp/credenciales", headers=_bearer(escritura)).status_code == 403
    assert c.post("/api/v1/mcp/credenciales", headers=_bearer(escritura),
                  json={"name": "x", "scope": "write"}).status_code == 403


def test_una_credencial_revocada_deja_de_conectar(client, admin_token):
    _encender(client, admin_token)
    clave = _credencial(client, admin_token)
    lista = client.get("/api/v1/mcp/credenciales", headers=auth(admin_token)).json()["items"]
    assert len(lista) == 1 and lista[0]["scopes"] == ["mcp:read"]
    assert client.delete(f"/api/v1/mcp/credenciales/{lista[0]['id']}", headers=auth(admin_token)).status_code == 200
    c = _sin_sesion(client)
    assert _rpc(c, "ping", cabeceras=_bearer(clave)).status_code == 401


def test_alcance_de_credencial_no_valido(client, admin_token):
    r = client.post("/api/v1/mcp/credenciales", headers=auth(admin_token), json={"name": "x", "scope": "admin"})
    assert r.status_code == 422 and r.json().get("code") == "mcp_credencial_alcance_no_valido"


def test_solo_lectura_no_ve_ni_ejecuta_escrituras_y_queda_auditado(client, admin_token, db):
    _encender(client, admin_token, write_mode="direct")
    _, t = _proyecto_y_tarea(db)
    clave = _credencial(client, admin_token, "read")
    c = _sin_sesion(client)
    nombres = _nombres(_rpc(c, "tools/list", cabeceras=_bearer(clave)))
    assert "get_task" in nombres and "add_task_comment" not in nombres
    r = _llamar(c, "add_task_comment", {"task": t.code, "content": "nota"}, _bearer(clave)).json()["result"]
    assert r["isError"] is True and r["structuredContent"]["error"]["code"] == "mcp_escritura_no_permitida"
    bloqueada = db.query(AuditLog).filter(AuditLog.action == "MCP_TOOL_CALL").one()
    assert json.loads(bloqueada.metadata_)["estado"] == "blocked"


# ── Capacidad por herramienta (la de su ruta REST) ──────────────────────────

def test_EL_HALLAZGO_cada_herramienta_pide_la_capacidad_de_su_ruta(client, admin_token, dev_token, db):
    """`open_change` es `POST /sd/changes` (sd.administrar): un empleado no lo ve ni lo ejecuta."""
    _encender(client, admin_token, write_mode="direct")
    clave = _credencial(client, dev_token, "write")
    c = _sin_sesion(client)
    nombres = _nombres(_rpc(c, "tools/list", cabeceras=_bearer(clave)))
    assert "list_my_tasks" in nombres and "open_change" not in nombres
    r = _llamar(c, "open_change", {"title": "Desplegar", "description": "v2"}, _bearer(clave)).json()["result"]
    assert r["isError"] is True
    assert r["structuredContent"]["error"]["code"] == "mcp_herramienta_sin_capacidad"
    assert r["structuredContent"]["error"]["params"]["capacidad"] == "sd.administrar"


def test_el_catalogo_declara_rutas_reales_y_capacidades_del_catalogo():
    from app.core.capacidades import CAPACIDADES
    from app.main import app
    from app.services.mcp_herramientas import HERRAMIENTAS, _comprobar_catalogo
    _comprobar_catalogo()
    rutas = {(m, r.path) for r in app.routes for m in (getattr(r, "methods", None) or set())}
    sin_ruta = [h.nombre for h in HERRAMIENTAS if (h.politica.metodo, "/api/v1" + h.politica.ruta) not in rutas]
    assert not sin_ruta, sin_ruta
    assert all(h.politica.capacidad is None or h.politica.capacidad in CAPACIDADES for h in HERRAMIENTAS)


def test_las_del_asistente_piden_ademas_ia_usar(client, admin_token, sub_token):
    _encender(client, admin_token)
    nombres = _nombres(_rpc(client, "tools/list", cabeceras=auth(sub_token)))
    assert "get_dashboard_summary" not in nombres and "search_all" not in nombres
    r = _llamar(client, "search_all", {"query": "x"}, auth(sub_token)).json()["result"]
    assert r["isError"] is True and r["structuredContent"]["error"]["code"] == "mcp_herramienta_ia"


# ── Aislamiento por empresa ─────────────────────────────────────────────────

def test_EL_HALLAZGO_un_ticket_de_otra_empresa_no_existe_para_el_agente(client, admin_token, db):
    from app.db.session import sin_filtro_de_tenant
    from app.models.mfa import Organization
    from app.models.service_desk import Ticket
    with sin_filtro_de_tenant(db):
        db.add(Organization(id="org-mcp", name="Otra", slug="org-mcp"))
        db.flush()
        db.add(Ticket(id="tk-otra", number="INC-7001", ticket_type="incident", title="Ajeno", description="secreto",
                      organization_id="org-mcp"))
        db.add(Ticket(id="tk-mia", number="INC-7002", ticket_type="incident", title="Propio", description="visible",
                      organization_id="1", requester_user_id="admin-test-id"))
        db.commit()
    _encender(client, admin_token)
    clave = _credencial(client, admin_token)
    c = _sin_sesion(client)
    ajeno = _llamar(c, "get_ticket", {"ticket": "INC-7001"}, _bearer(clave)).json()["result"]
    assert ajeno["isError"] is True and ajeno["structuredContent"]["error"]["code"] == "no_encontrado"
    propio = _llamar(c, "get_ticket", {"ticket": "INC-7002"}, _bearer(clave)).json()["result"]
    assert propio["isError"] is False and propio["structuredContent"]["number"] == "INC-7002"
    encontrados = _llamar(c, "search_tickets", {"query": "INC-700"}, _bearer(clave)).json()["result"]
    assert {t["number"] for t in encontrados["structuredContent"]["items"]} == {"INC-7002"}


# ── Auditoría de las escrituras (sin datos personales) ──────────────────────

def test_EL_HALLAZGO_cada_escritura_queda_en_audit_log_con_canal_credencial_empresa_e_ip(client, admin_token, db):
    _encender(client, admin_token, write_mode="direct")
    _, t = _proyecto_y_tarea(db)
    clave = _credencial(client, admin_token, "write")
    c = _sin_sesion(client)
    secreto = "El cliente Pérez llamó desde el 600123456"
    r = _llamar(c, "add_task_comment", {"task": t.code, "content": secreto}, _bearer(clave)).json()["result"]
    assert r["isError"] is False, r
    fila = db.query(AuditLog).filter(AuditLog.action == "MCP_TOOL_CALL").one()
    meta = json.loads(fila.metadata_)
    assert meta["canal"] == "mcp" and meta["herramienta"] == "add_task_comment" and meta["estado"] == "success"
    assert meta["credencial"]["tipo"] == "api_key" and meta["credencial"]["id"]
    assert meta["empresa"] == "1" and fila.ip_address
    # Ni el texto del comentario en la auditoría ni en el registro de uso.
    assert secreto not in (fila.metadata_ or "") and "Pérez" not in (fila.new_values or "")
    uso = db.query(AIActionLog).filter(AIActionLog.module == "mcp", AIActionLog.action_type == "add_task_comment").one()
    assert secreto not in (uso.input_summary or "") and uso.ip_address


def test_la_conexion_queda_auditada(client, admin_token, db):
    _encender(client, admin_token)
    clave = _credencial(client, admin_token)
    c = _sin_sesion(client)
    _rpc(c, "initialize", {"protocolVersion": "2025-11-25", "clientInfo": {"name": "opencode", "version": "1"}},
         _bearer(clave))
    fila = db.query(AuditLog).filter(AuditLog.action == "MCP_CONNECT").one()
    assert json.loads(fila.metadata_)["cliente"]["name"] == "opencode"


def test_log_time_entra_por_la_puerta_validada(client, admin_token, db, monkeypatch):
    from types import SimpleNamespace
    from app.services.imputation_service import alta
    _encender(client, admin_token, write_mode="direct")
    p, _ = _proyecto_y_tarea(db)
    llamadas = []

    def espia(usuario, db_, **kw):
        llamadas.append(kw)
        return SimpleNamespace(id="imp-1", date=kw["fecha"], hours=kw["horas"], project_id=kw["project_id"],
                               task_id=kw["task_id"], is_billable=kw["is_billable"])
    monkeypatch.setattr(alta, "crear_imputacion_validada", espia)
    r = _llamar(client, "log_time", {"project": p.code, "hours": 2, "date": "2026-11-20"}, auth(admin_token)).json()
    assert r["result"]["isError"] is False, r
    assert llamadas and llamadas[0]["project_id"] == p.id and llamadas[0]["horas"] == 2


# ── Límite de uso por credencial ────────────────────────────────────────────

def test_EL_HALLAZGO_limite_por_credencial_429_con_retry_after(client, admin_token):
    _encender(client, admin_token, rate_limit_per_minute=2)
    clave, otra = _credencial(client, admin_token), _credencial(client, admin_token)
    c = _sin_sesion(client)
    assert _rpc(c, "ping", cabeceras=_bearer(clave)).status_code == 200
    assert _rpc(c, "ping", cabeceras=_bearer(clave)).status_code == 200
    r = _rpc(c, "ping", cabeceras=_bearer(clave))
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
    assert r.json()["error"]["data"]["code"] == "mcp_limite_de_uso"
    # Es por credencial: otra del mismo dueño sigue.
    assert _rpc(c, "ping", cabeceras=_bearer(otra)).status_code == 200


# ── Protocolo (Streamable HTTP) ─────────────────────────────────────────────

def test_protocolo_streamable_http(client, admin_token):
    _encender(client, admin_token)
    h = auth(admin_token)
    r = _rpc(client, "initialize", {"protocolVersion": "2025-11-25"}, h)
    assert r.json()["result"]["protocolVersion"] == "2025-11-25"
    assert _rpc(client, "initialize", {"protocolVersion": "1999-01-01"}, h).json()["result"]["protocolVersion"] == "2025-11-25"
    g = client.get(URL, headers=h)
    assert g.status_code == 405 and g.headers["Allow"] == "POST"
    assert client.delete(URL, headers=h).status_code == 405
    v = client.post(URL, json={"jsonrpc": "2.0", "id": 1, "method": "ping"}, headers={**h, "MCP-Protocol-Version": "1999-01-01"})
    assert v.status_code == 400 and v.json()["error"]["data"]["code"] == "mcp_version_no_soportada"
    o = client.post(URL, json={"jsonrpc": "2.0", "id": 1, "method": "ping"}, headers={**h, "Origin": "https://malo.example"})
    assert o.status_code == 403 and o.json()["error"]["data"]["code"] == "mcp_origen_no_permitido"
    # Una respuesta del cliente (sin method) y una notificación: 202 sin cuerpo.
    assert client.post(URL, json={"jsonrpc": "2.0", "id": 9, "result": {}}, headers=h).status_code == 202
    assert client.post(URL, json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=h).status_code == 202
    herramientas = {t["name"]: t for t in _rpc(client, "tools/list", cabeceras=h).json()["result"]["tools"]}
    t = herramientas["search_tickets"]
    assert t["inputSchema"]["type"] == "object" and "page_size" in t["inputSchema"]["properties"]
    assert t["annotations"]["readOnlyHint"] is True
    desconocida = _llamar(client, "no_existe", {}, h).json()
    assert desconocida["error"]["code"] == -32602 and desconocida["error"]["data"]["code"] == "mcp_herramienta_desconocida"


def test_argumentos_no_validos_con_codigo(client, admin_token):
    _encender(client, admin_token)
    r = _llamar(client, "search_tasks", {"page_size": 1000}, auth(admin_token)).json()["result"]
    assert r["isError"] is True and r["structuredContent"]["error"]["code"] == "mcp_argumentos_no_validos"


def test_apagado_403_con_codigo(client, admin_token):
    r = _rpc(client, "initialize", cabeceras=auth(admin_token))
    assert r.status_code == 403 and r.json()["error"]["data"]["code"] == "mcp_apagado"


def test_listas_paginadas(client, admin_token, db):
    from app.models.task import Task
    p, _ = _proyecto_y_tarea(db)
    for i in range(3):
        db.add(Task(code=f"TSK-95{i}", title=f"Más {i}", project_id=p.id, assignee_id="admin-test-id",
                    organization_id="1"))
    db.commit()
    _encender(client, admin_token)
    r = _llamar(client, "list_my_tasks", {"page": 1, "page_size": 2}, auth(admin_token)).json()["result"]
    datos = r["structuredContent"]
    assert len(datos["items"]) == 2 and datos["total"] == 4 and datos["has_more"] is True and datos["next_page"] == 2


# ── Configuración ───────────────────────────────────────────────────────────

def test_solo_gobierno_cambia_el_estado(client, admin_token, pm_token):
    assert client.get("/api/v1/mcp/estado", headers=auth(pm_token)).status_code == 200
    assert client.patch("/api/v1/mcp/estado", headers=auth(pm_token), json={"enabled": True}).status_code == 403
    r = client.patch("/api/v1/mcp/estado", headers=auth(admin_token), json={"enabled": True, "write_mode": "approval"})
    assert r.status_code == 200 and r.json()["data"]["enabled"] is True and r.json()["data"]["write_mode"] == "approval"
    herramientas = client.get("/api/v1/mcp/herramientas", headers=auth(pm_token)).json()["items"]
    assert {h["name"] for h in herramientas} >= {"list_my_tasks", "open_change", "search_notebook"}


# ── Mi cuaderno: privado salvo que su dueño lo comparta con sus agentes ─────

def _cuaderno_con_pagina(client, token, titulo="Diseño de la caché"):
    nb = client.post("/api/v1/notebook/notebooks", headers=auth(token), json={"title": "Trabajo"}).json()["data"]
    arbol = client.get("/api/v1/notebook/tree", headers=auth(token)).json()["data"]
    seccion = next(n for n in arbol["notebooks"] if n["id"] == nb["id"])["sections"][0]["id"]
    r = client.post(f"/api/v1/notebook/sections/{seccion}/pages", headers=auth(token), json={"title": titulo})
    assert r.status_code == 200, r.text
    return nb["id"]


def test_EL_HALLAZGO_el_cuaderno_es_privado_hasta_que_su_dueno_lo_comparte(client, admin_token, pm_token):
    _encender(client, admin_token, notebook_enabled=True)
    nb = _cuaderno_con_pagina(client, pm_token)
    h = auth(pm_token)
    vacio = _llamar(client, "search_notebook", {"query": "caché"}, h).json()["result"]["structuredContent"]
    assert vacio["items"] == []
    r = client.post(f"/api/v1/notebook/notebooks/{nb}/shares", headers=h,
                    json={"target_type": "agents", "target_id": "me", "permission": "edit"})
    assert r.status_code == 200 and r.json()["data"]["permission"] == "read"
    hallado = _llamar(client, "search_notebook", {"query": "caché"}, h).json()["result"]["structuredContent"]
    assert [p["title"] for p in hallado["items"]] == ["Diseño de la caché"]
    # Otra persona (aunque admin) no lo ve por MCP: solo los cuadernos propios.
    ajeno = _llamar(client, "search_notebook", {"query": "caché"}, auth(admin_token)).json()["result"]
    assert ajeno["structuredContent"]["items"] == []


def test_sin_el_interruptor_de_la_empresa_no_hay_cuaderno_por_mcp(client, admin_token, pm_token):
    _encender(client, admin_token)
    nb = _cuaderno_con_pagina(client, pm_token)
    assert "search_notebook" not in _nombres(_rpc(client, "tools/list", cabeceras=auth(pm_token)))
    r = client.post(f"/api/v1/notebook/notebooks/{nb}/shares", headers=auth(pm_token),
                    json={"target_type": "agents", "target_id": "me"})
    assert r.status_code == 403 and r.json().get("code") == "mcp_cuaderno_apagado"
