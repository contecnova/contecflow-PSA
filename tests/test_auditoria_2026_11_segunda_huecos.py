"""Segunda auditoría 2026-11: #22 (entregas de webhooks), #23 (Jira del hub) y #26 (huecos de tests).

#26: comportamientos ya arreglados en la revisión GRC/multitenant 2026-11b que
no tenían test: auditoría de rotaciones de secretos, ORG_SWITCH, evidencia de
cumplimiento, y que los trabajos de fondo corren en la empresa de cada fila.
"""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db.session import sin_filtro_de_tenant
from app.models.enterprise import AuditLog
from app.models.mfa import Organization
from tests.conftest import auth

RAIZ = Path(__file__).resolve().parents[1]
JIRA_URL = "https://93.184.216.34"   # IP pública literal: la validación SSRF no resuelve DNS


def _auditado(db, accion, recurso):
    with sin_filtro_de_tenant(db):
        return db.query(AuditLog).filter(AuditLog.action == accion, AuditLog.resource == recurso).all()


def _org(db, oid):
    if not db.get(Organization, oid):
        db.add(Organization(id=oid, name=oid, slug=oid))
        db.flush()


# ── #22 Entregas de todos los webhooks en una consulta ───────────────────────

def test_entregas_de_todos_los_webhooks_paginadas_y_filtradas(client, db, admin_token):
    from app.models.enterprise import Webhook, WebhookDelivery
    _org(db, "org-otra")
    a = Webhook(name="A", url="https://a.example", events="[]", organization_id="1")
    b = Webhook(name="B", url="https://b.example", events="[]", organization_id="1")
    ajeno = Webhook(name="X", url="https://x.example", events="[]", organization_id="org-otra")
    db.add_all([a, b, ajeno])
    db.flush()
    base = datetime(2026, 11, 1, tzinfo=timezone.utc)
    for i, (h, ev, ok) in enumerate([(a, "task.created", True), (a, "task.updated", False),
                                     (b, "task.created", True), (ajeno, "task.created", True)]):
        db.add(WebhookDelivery(webhook_id=h.id, event=ev, success=ok, status_code=200 if ok else 500,
                               organization_id=h.organization_id, created_at=base + timedelta(minutes=i)))
    db.commit()

    url = "/api/v1/enterprise/webhooks/deliveries"
    r = client.get(url, headers=auth(admin_token))
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["meta"]["total"] == 3, "la otra empresa no se ve"
    assert [d["webhook_name"] for d in cuerpo["items"]] == ["B", "A", "A"], "más reciente primero"
    assert cuerpo["items"][0]["webhook_url"] == "https://b.example"

    def total(**params):
        return client.get(url, headers=auth(admin_token), params=params).json()["meta"]["total"]
    assert total(webhook_id=a.id) == 2
    assert total(event="task.created") == 2
    assert total(success="false") == 1
    pag = client.get(url, headers=auth(admin_token), params={"page": 2, "page_size": 2}).json()
    assert len(pag["items"]) == 1 and pag["meta"]["total"] == 3
    # el endpoint por webhook se mantiene
    assert client.get(f"/api/v1/enterprise/webhooks/{a.id}/deliveries", headers=auth(admin_token)).status_code == 200


# ── #23 Jira del hub = JiraConfig de la organización ─────────────────────────

def test_el_hub_guarda_y_lee_la_jira_config_de_la_organizacion(client, db, admin_token, monkeypatch):
    from app.models.jira_integration import JiraConfig
    from app.services import integrations, jira_service

    r = client.put("/api/v1/integrations-hub/jira/config", headers=auth(admin_token), json={
        "name": "Jira", "base_url": JIRA_URL, "email": "a@b.c", "api_token": "tok-1", "project_key": "PRJ"})
    assert r.status_code == 200, r.text
    assert "tok-1" not in r.text and r.json()["data"]["has_token"] is True
    with sin_filtro_de_tenant(db):
        filas = db.query(JiraConfig).filter(JiraConfig.organization_id == "1").all()
    assert len(filas) == 1 and filas[0].usar_para_tareas is True
    assert jira_service.get_jira_config(db, "1")["jira_api_token"] == "tok-1", "la ven las tareas"

    # sin token se conserva el guardado
    r = client.put("/api/v1/integrations-hub/jira/config", headers=auth(admin_token),
                   json={"base_url": JIRA_URL, "email": "otro@b.c"})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert jira_service.get_jira_config(db, "1") == {
        "jira_url": JIRA_URL, "jira_email": "otro@b.c", "jira_api_token": "tok-1", "jira_project_key": "PRJ"}

    usada = {}
    def buscar(cfg, jql, n):
        usada.update(cfg)
        return {"ok": True, "data": {"issues": [], "total": 0}}
    monkeypatch.setattr(integrations, "search_jira_issues", buscar)
    r = client.get("/api/v1/integrations-hub/jira/search", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    assert usada["api_token"] == "tok-1" and usada["base_url"] == JIRA_URL

    assert client.delete("/api/v1/integrations-hub/jira/config", headers=auth(admin_token)).status_code == 200
    assert client.get("/api/v1/integrations-hub/jira/search", headers=auth(admin_token)).status_code == 404


def test_oauth_integrations_jira_va_a_la_jira_config(client, db, admin_token):
    from app.models.cab import IntegrationConfig
    r = client.post("/api/v1/oauth-integrations", headers=auth(admin_token), json={
        "integration_type": "jira", "name": "Jira",
        "config": {"base_url": JIRA_URL, "email": "a@b.c", "api_token": "tok-2"}})
    assert r.status_code == 200, r.text
    with sin_filtro_de_tenant(db):
        assert db.query(IntegrationConfig).filter(IntegrationConfig.integration_type == "jira").count() == 0
    cfg = client.get("/api/v1/integrations-hub/jira/config", headers=auth(admin_token)).json()["data"]
    assert cfg["configured"] and cfg["base_url"] == JIRA_URL and "api_token" not in cfg


def _revision_161():
    ruta = RAIZ / "alembic" / "versions" / "161_jira_hub_a_jira_config.py"
    spec = importlib.util.spec_from_file_location("rev161", ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_la_migracion_161_lleva_las_filas_de_integration_configs_a_jira_config():
    rev = _revision_161()
    motor = sa.create_engine("sqlite://")
    with motor.begin() as con:
        for sql in (
            "CREATE TABLE organizations (id VARCHAR(36) PRIMARY KEY)",
            "CREATE TABLE integration_configs (id VARCHAR(36) PRIMARY KEY, organization_id VARCHAR(36), "
            "integration_type VARCHAR(20), name VARCHAR(255), is_active BOOLEAN, access_token TEXT, "
            "refresh_token TEXT, config TEXT)",
            "CREATE TABLE sd_jira_configs (id VARCHAR(36) PRIMARY KEY, organization_id VARCHAR(36), "
            "name VARCHAR(100) NOT NULL, jira_base_url VARCHAR(500) NOT NULL, jira_email VARCHAR(255) NOT NULL, "
            "jira_api_token_enc TEXT NOT NULL, jira_project_key VARCHAR(50) NOT NULL, "
            "jira_issue_type_incident VARCHAR(100), jira_issue_type_service_request VARCHAR(100), "
            "jira_issue_type_change VARCHAR(100), jira_issue_type_problem VARCHAR(100), sync_direction VARCHAR(20), "
            "sync_comments BOOLEAN, sync_status_changes BOOLEAN, sync_priority_changes BOOLEAN, "
            "sync_assignments BOOLEAN, sync_interval_minutes INTEGER, is_active BOOLEAN, "
            "usar_para_tareas BOOLEAN NOT NULL DEFAULT 0, created_at DATETIME)",
        ):
            con.execute(sa.text(sql))
        con.execute(sa.text("INSERT INTO organizations VALUES ('o1'), ('o2')"))
        cfg = json.dumps({"base_url": "https://j.example/", "email": "e@x", "api_token": "v2:cifrado"})
        con.execute(sa.text(
            "INSERT INTO integration_configs VALUES ('i1', 'o1', 'jira', 'Jira uno', 1, NULL, NULL, :c), "
            "('i2', 'o2', 'jira', 'Jira dos', 1, NULL, NULL, :c), "
            "('i3', 'o1', 'slack', 'Slack', 1, 'tok', NULL, '{}')"), {"c": cfg})
        con.execute(sa.text(   # o2 ya tenía conexión de tareas: gana la existente
            "INSERT INTO sd_jira_configs (id, organization_id, name, jira_base_url, jira_email, "
            "jira_api_token_enc, jira_project_key, usar_para_tareas) "
            "VALUES ('j2', 'o2', 'Previa', 'https://previa', 'p@x', 'v2:previo', 'P', 1)"))
        for _ in range(2):   # idempotente
            with Operations.context(MigrationContext.configure(con)):
                rev.upgrade()
        filas = con.execute(sa.text(
            "SELECT organization_id, jira_base_url, jira_api_token_enc, name FROM sd_jira_configs "
            "WHERE usar_para_tareas = 1 ORDER BY organization_id")).fetchall()
        assert [tuple(f) for f in filas] == [("o1", "https://j.example", "v2:cifrado", "Jira uno"),
                                             ("o2", "https://previa", "v2:previo", "Previa")]
        viejas = con.execute(sa.text(
            "SELECT id, is_active, config FROM integration_configs ORDER BY id")).fetchall()
        assert [tuple(f) for f in viejas] == [("i1", 0, None), ("i2", 0, None), ("i3", 1, "{}")]


# ── #26 Rotaciones de secretos auditadas ─────────────────────────────────────

def test_rotar_el_slug_del_webhook_cab_se_audita(client, db, admin_token):
    r = client.post("/api/v1/webhooks", headers=auth(admin_token), json={"name": "Entrante", "slug": "slug-hueco-1"})
    assert r.status_code == 200, r.text
    tid = r.json()["data"]["id"]
    r = client.post(f"/api/v1/webhooks/{tid}/rotate", headers=auth(admin_token), params={"expires_in_days": 7})
    assert r.status_code == 200, r.text
    filas = [f for f in _auditado(db, "SECRET_ROTATED", "webhook_trigger") if f.resource_id == tid]
    assert len(filas) == 1 and json.loads(filas[0].new_values) == {"expires_in_days": 7}
    assert r.json()["data"]["slug"] not in (filas[0].new_values or "")


def test_rotar_el_secreto_de_una_app_oauth_se_audita(client, db, pm_token):
    app = client.post("/api/v1/developer/apps", headers=auth(pm_token),
                      json={"name": "Integra", "scopes": ["read"]}).json()["data"]
    r = client.post(f"/api/v1/developer/apps/{app['id']}/rotate-secret", headers=auth(pm_token))
    assert r.status_code == 200, r.text
    filas = [f for f in _auditado(db, "SECRET_ROTATED", "oauth_app") if f.resource_id == app["id"]]
    assert len(filas) == 1 and filas[0].user_id == "pm-test-id"
    secreto = r.json()["data"]["client_secret"]
    assert secreto not in json.dumps([filas[0].new_values, filas[0].old_values, filas[0].resource_name])


def test_rotar_el_token_de_un_agente_cmdb_se_audita(client, db, admin_token):
    alta = client.post("/api/v1/sd/cmdb/agents/register", headers=auth(admin_token), json={"name": "srv-01"})
    assert alta.status_code == 201, alta.text
    agente = alta.json()["data"]["agent_id"]
    r = client.post(f"/api/v1/sd/cmdb/agents/{agente}/rotate-token", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    filas = [f for f in _auditado(db, "SECRET_ROTATED", "cmdb_agent") if f.resource_id == agente]
    assert len(filas) == 1
    assert r.json()["data"]["token"] not in (filas[0].new_values or "")


# ── #26 ORG_SWITCH ───────────────────────────────────────────────────────────

def test_cambiar_de_empresa_en_la_sesion_se_audita_en_la_de_destino(client, db, pm_token, monkeypatch):
    from app.core.config import settings
    from app.models.user import UserOrganizationMembership
    monkeypatch.setattr(settings, "TENANT_ENTRY_MODE", "email_selector")
    _org(db, "1")
    _org(db, "org-dest")
    db.add(UserOrganizationMembership(user_id="pm-test-id", organization_id="org-dest"))
    db.commit()
    r = client.post("/api/v1/auth/switch-organization", headers=auth(pm_token), json={"organization_id": "org-dest"})
    assert r.status_code == 200, r.text
    filas = [f for f in _auditado(db, "ORG_SWITCH", "users") if f.user_id == "pm-test-id"]
    assert len(filas) == 1
    assert filas[0].organization_id == "org-dest"
    assert json.loads(filas[0].new_values) == {"organization_id": "org-dest"}


# ── #26 Evidencia de cumplimiento ────────────────────────────────────────────

def test_crear_evidencia_de_cumplimiento_se_audita(client, db, admin_token):
    r = client.post("/api/v1/governance/compliance/evidence", headers=auth(admin_token), json={
        "framework": "soc2", "control_id": "SOC2-CC6.1", "evidence_type": "policy", "title": "Revisión"})
    assert r.status_code == 200, r.text
    eid = r.json()["data"]["id"]
    filas = [f for f in _auditado(db, "CREATE", "compliance_evidence") if f.resource_id == eid]
    assert len(filas) == 1 and filas[0].resource_name == "SOC2-CC6.1"
    assert json.loads(filas[0].new_values) == {"framework": "SOC2", "type": "policy"}


# ── #26 Trabajos de fondo en la empresa de cada fila ─────────────────────────

def test_el_run_que_despierta_de_una_espera_sigue_en_su_empresa(db):
    from app.models.workflow_designer import (
        WorkflowBlueprint, WorkflowBlueprintStatus, WorkflowBlueprintVersion, WorkflowRunStep,
    )
    from app.services.service_desk.workflow_engine import start_run, tick_waiting
    org = "org-wf"
    _org(db, org)
    bp = WorkflowBlueprint(name="Espera", process_type="ticket",
                           status=WorkflowBlueprintStatus.published, organization_id=org)
    db.add(bp)
    db.flush()
    grafo = {"nodes": [{"id": "s", "type": "start"},
                       {"id": "w", "type": "wait", "config": {"wait_minutes": 5}},
                       {"id": "f", "type": "end"}],
             "edges": [{"source": "s", "target": "w"}, {"source": "w", "target": "f"}]}
    db.add(WorkflowBlueprintVersion(blueprint_id=bp.id, version=1, graph_json=json.dumps(grafo),
                                    is_published=True, organization_id=org))
    db.flush()
    run = start_run(db, blueprint_id=bp.id, organization_id=org)
    assert run.status.value == "waiting", run.last_error
    run.wake_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()

    # La sesión del worker es la del operador (superadmin, organización 1 en `info`).
    assert tick_waiting(db) == 1
    db.refresh(run)
    assert run.status.value == "completed", run.last_error
    fin = db.query(WorkflowRunStep).filter(WorkflowRunStep.run_id == run.id, WorkflowRunStep.node_id == "f").one()
    assert fin.organization_id == org, "el paso nuevo se sellaba con la organización de la sesión"
    assert db.info["organization_id"] == 1, "el contexto de la sesión se restaura"


def test_la_cola_de_flujos_procesa_cada_elemento_en_su_empresa(db):
    from app.models.billing_reports import AutomationWorkflow, WorkflowExecution
    from app.models.bookings import WorkflowQueueItem
    from app.services.bookings_service.cola_de_flujos import process_workflow_queue_record
    _org(db, "1")
    _org(db, "org-q")
    ahora = datetime.now(timezone.utc) - timedelta(minutes=1)
    flujos = {}
    for org in ("1", "org-q"):
        wf = AutomationWorkflow(name=f"F {org}", status="active", trigger_type="manual", organization_id=org)
        db.add(wf)
        db.flush()
        flujos[org] = wf.id
        db.add(WorkflowQueueItem(workflow_id=wf.id, trigger_data="{}", execute_at=ahora,
                                 status="pending", organization_id=org))
    db.commit()

    res = process_workflow_queue_record(db)
    assert res["processed"] == 2, res
    for org, wid in flujos.items():
        ejecucion = db.query(WorkflowExecution).filter(WorkflowExecution.workflow_id == wid).one()
        assert ejecucion.organization_id == org
        assert db.get(AutomationWorkflow, wid).run_count == 1
