"""Service desk — mejoras de mercado (16-11-2026).

Agente autonomo (modo sugerir/ejecutar, aislamiento), candidatos a duplicado,
SLA condicionales, ciclos de vida, tareas de catalogo por etapas, aprobacion
del catalogo en el motor comun, clases de CI, panel personal y asistente del
portal. Las integraciones (Slack, WhatsApp) van en
`test_sd_mercado_canales_2026_11.py`, con dobles.
"""
import json
from datetime import datetime, timedelta, timezone

from app.models.service_desk import (
    AgentGroup, AutonomousPlaybook, AutonomousPlaybookExecution, ServiceCategory, ServiceItem, SLARule, Ticket,
    TicketComment,
)
from app.services.settings_service import update_setting
from tests.conftest import auth


def _ticket(client, token, titulo="La impresora hace un zumbido", **extra):
    r = client.post("/api/v1/sd/tickets", headers=auth(token), json={
        "title": titulo, "description": titulo, "priority": "p4_low", "ticket_type": "incident", **extra})
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


def _org(db, tid):
    db.expire_all()
    return db.query(Ticket).filter(Ticket.id == tid).one().organization_id


def _playbook(db, org):
    db.add(AutonomousPlaybook(organization_id=org, name="Zumbidos", playbook_type="zumbido",
                              steps_json=json.dumps([{"type": "comment", "content": "Apaga y enciende"}]),
                              conditions_json=json.dumps({"trigger_keywords": ["zumbido"], "max_priority": "p3_medium"})))
    update_setting("SD_AUTONOMOUS_AGENT_ENABLED", "true", org, db)
    update_setting("SD_AUTONOMY_SUGGEST_THRESHOLD", "0.1", org, db)
    db.commit()


# ── Agente autonomo ───────────────────────────────────────────────────────────

def test_modo_sugerir_no_escribe_y_aplicar_si(client, admin_token, db):
    tid = _ticket(client, admin_token)
    org = _org(db, tid)
    _playbook(db, org)  # sin SD_AUTONOMOUS_AGENT_MODE: sugerir
    from app.services.service_desk.autonomous_agent_service import run_autonomous_scan
    run_autonomous_scan(db, org_id=org)
    assert db.query(TicketComment).filter(TicketComment.ticket_id == tid).count() == 0
    fila = db.query(AutonomousPlaybookExecution).filter(AutonomousPlaybookExecution.ticket_id == tid).one()
    assert fila.status == "suggested" and fila.mode == "suggest"
    assert json.loads(fila.actions_json)[0]["type"] == "comment"

    r = client.post(f"/api/v1/sd/autonomous/executions/{fila.id}/apply", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    db.expire_all()
    assert [c.body for c in db.query(TicketComment).filter(TicketComment.ticket_id == tid)] == ["Apaga y enciende"]
    assert client.post(f"/api/v1/sd/autonomous/executions/{fila.id}/apply", headers=auth(admin_token)).status_code == 409


def test_config_del_agente_y_playbooks_de_otra_empresa_no_se_ven(client, admin_token, db):
    r = client.put("/api/v1/sd/autonomous/config", headers=auth(admin_token),
                   json={"enabled": True, "mode": "execute", "disabled_playbooks": ["pw-reset", "inventado"]})
    assert r.status_code == 200, r.text
    datos = r.json()["data"]
    assert datos["mode"] == "execute" and datos["disabled_playbooks"] == ["pw-reset"]
    db.add(AutonomousPlaybook(organization_id=None, name="De nadie", playbook_type="x", steps_json="[]"))
    db.commit()
    nombres = {p["name"] for p in client.get("/api/v1/sd/autonomous/playbooks", headers=auth(admin_token)).json()["items"]}
    assert "De nadie" not in nombres
    pw = next(p for p in client.get("/api/v1/sd/autonomous/playbooks", headers=auth(admin_token)).json()["items"]
              if p["id"] == "pw-reset")
    assert pw["enabled"] is False


# ── Duplicados ────────────────────────────────────────────────────────────────

def test_candidatos_a_duplicado_por_texto(client, admin_token, db):
    a = _ticket(client, admin_token, "No funciona la VPN de la oficina de Madrid")
    b = _ticket(client, admin_token, "La VPN de la oficina de Madrid no funciona desde esta mañana")
    _ticket(client, admin_token, "Pedir una silla nueva")
    r = client.get(f"/api/v1/sd/tickets/{b}/duplicate-candidates", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    ids = [c["id"] for c in r.json()["data"]["candidates"]]
    assert ids and ids[0] == a
    assert "similar_text" in r.json()["data"]["candidates"][0]["reasons"]


# ── SLA condicionales ─────────────────────────────────────────────────────────

def test_regla_de_sla_por_prioridad_fija_los_plazos(client, admin_token, db):
    tid = _ticket(client, admin_token, "Primero, para saber la empresa")
    org = _org(db, tid)
    db.add(SLARule(organization_id=org, name="P4 en 100 h", priority="p4_low", response_hours=50, resolution_hours=100))
    db.commit()
    nuevo = _ticket(client, admin_token, "Con regla")
    db.expire_all()
    t = db.query(Ticket).filter(Ticket.id == nuevo).one()
    sin = db.query(Ticket).filter(Ticket.id == tid).one()
    assert t.sla_resolution_due > sin.sla_resolution_due


# ── Ciclos de vida ────────────────────────────────────────────────────────────

def test_ciclo_de_vida_propio_cae_en_su_estado_base(client, admin_token, db):
    r = client.put("/api/v1/sd/lifecycles", headers=auth(admin_token), json={
        "ticket_type": "incident", "name": "Incidencias", "restrict_transitions": True,
        "states": [
            {"key": "abierta", "label": "Abierta", "base_status": "new", "is_initial": True},
            {"key": "esperando_pieza", "label": "Esperando pieza", "base_status": "pending_third"},
            {"key": "arreglada", "label": "Arreglada", "base_status": "resolved"},
        ],
        "transitions": [{"from_key": "abierta", "to_key": "esperando_pieza"}],
    })
    assert r.status_code == 200, r.text
    tid = _ticket(client, admin_token, "Ciclo")
    db.expire_all()
    assert db.query(Ticket).filter(Ticket.id == tid).one().lifecycle_state == "abierta"
    r = client.patch(f"/api/v1/sd/tickets/{tid}", headers=auth(admin_token), json={"lifecycle_state": "esperando_pieza"})
    assert r.status_code == 200, r.text
    db.expire_all()
    t = db.query(Ticket).filter(Ticket.id == tid).one()
    assert t.lifecycle_state == "esperando_pieza" and getattr(t.status, "value", t.status) == "pending_third"
    # No hay paso «esperando_pieza → arreglada».
    r = client.patch(f"/api/v1/sd/tickets/{tid}", headers=auth(admin_token), json={"lifecycle_state": "arreglada"})
    assert r.status_code == 409


# ── Catalogo: tareas por etapas ───────────────────────────────────────────────

def _servicio(db, org, **extra):
    cat = ServiceCategory(organization_id=org, name="IT")
    db.add(cat)
    db.flush()
    grupo = AgentGroup(organization_id=org, name="Puesto", support_level="l1")
    db.add(grupo)
    db.flush()
    item = ServiceItem(organization_id=org, category_id=cat.id, name="Alta de empleado", **extra)
    db.add(item)
    db.commit()
    return item, grupo


def test_tareas_estructuradas_por_etapas(client, admin_token, db):
    org = _org(db, _ticket(client, admin_token, "empresa"))
    item, grupo = _servicio(db, org)
    r = client.patch(f"/api/v1/sd/catalog/services/{item.id}", headers=auth(admin_token), json={"fulfillment_tasks": [
        {"title": "Crear cuenta", "group_id": grupo.id, "stage": 1, "sla_hours": 4},
        {"title": "Entregar portátil", "group_id": grupo.id, "stage": 2},
    ]})
    assert r.status_code == 200, r.text
    peticion = _ticket(client, admin_token, "Alta de Ana", service_item_id=item.id, ticket_type="service_request")
    db.expire_all()
    hijos = db.query(Ticket).filter(Ticket.parent_ticket_id == peticion).all()
    assert [h.title.split(" · ")[-1] for h in hijos] == ["Crear cuenta"]
    from app.services.service_desk.fulfillment_service import al_terminar_una_tarea
    from app.models.service_desk import TicketStatus
    hijos[0].status = TicketStatus.resolved
    db.flush()
    assert al_terminar_una_tarea(db, hijos[0]) is False
    db.commit()
    titulos = sorted(h.title.split(" · ")[-1] for h in db.query(Ticket).filter(Ticket.parent_ticket_id == peticion))
    assert titulos == ["Crear cuenta", "Entregar portátil"]


def test_modo_engine_sin_flujo_se_rechaza_al_guardar(client, admin_token, db):
    org = _org(db, _ticket(client, admin_token, "empresa"))
    item, _ = _servicio(db, org)
    r = client.patch(f"/api/v1/sd/catalog/services/{item.id}", headers=auth(admin_token),
                     json={"requires_approval": True, "approval_mode": "engine"})
    assert r.status_code == 422


def test_decision_del_motor_libera_o_cancela_la_peticion(client, admin_token, db):
    from app.services.service_desk.catalog_approval_service import aplicar_decision_del_motor
    tid = _ticket(client, admin_token, "Pedir software")
    t = db.query(Ticket).filter(Ticket.id == tid).one()
    t.approval_status = "pending"
    db.commit()
    aplicar_decision_del_motor(db, tid, "rejected", None, "No hay presupuesto")
    db.expire_all()
    t = db.query(Ticket).filter(Ticket.id == tid).one()
    assert t.approval_status == "rejected" and getattr(t.status, "value", t.status) == "cancelled"


# ── Clases de CI ──────────────────────────────────────────────────────────────

def test_clase_de_ci_propia_fija_la_clase_base(client, admin_token, db):
    r = client.post("/api/v1/sd/cmdb/ci-classes", headers=auth(admin_token),
                    json={"key": "firewall", "label": "Firewall", "base_type": "network"})
    assert r.status_code in (200, 201), r.text
    r = client.post("/api/v1/sd/cmdb", headers=auth(admin_token),
                    json={"name": "fw-01", "ci_type": "server", "ci_class": "firewall"})
    assert r.status_code in (200, 201), r.text
    lista = client.get("/api/v1/sd/cmdb", params={"q": "fw-01"}, headers=auth(admin_token)).json()["items"]
    assert lista[0]["ci_class"] == "firewall" and lista[0]["ci_type"] == "network"
    assert client.post("/api/v1/sd/cmdb", headers=auth(admin_token),
                       json={"name": "x", "ci_type": "server", "ci_class": "no_existe"}).status_code == 422


# ── Panel personal ────────────────────────────────────────────────────────────

def test_panel_personal_y_widgets_validados(client, admin_token, dev_token):
    r = client.put("/api/v1/sd/dashboard/layout", params={"role": "operation"}, headers=auth(dev_token),
                   json={"widgets": ["sla_risk", "my_queue_prioritized"]})
    assert r.status_code == 200, r.text
    assert client.get("/api/v1/sd/dashboard/layout", headers=auth(dev_token)).json()["data"]["layout"]["origin"] == "user"
    assert client.get("/api/v1/sd/dashboard/layout", headers=auth(admin_token)).json()["data"]["layout"]["origin"] != "user"
    assert client.put("/api/v1/sd/dashboard/layout", params={"scope": "org"}, headers=auth(dev_token),
                      json={"widgets": ["sla_risk"]}).status_code == 403
    assert client.put("/api/v1/sd/dashboard/layout", headers=auth(dev_token),
                      json={"widgets": ["inventado"]}).status_code == 422


# ── Asistente del portal ──────────────────────────────────────────────────────

def _cliente_del_portal(db, org):
    from app.models.client_portal import ClientUser
    c = ClientUser(organization_id=org, full_name="Cliente Uno", email="cliente.uno@example.com", is_active=True)
    db.add(c)
    db.commit()
    return c


def test_asistente_del_portal_propone_y_solo_crea_al_confirmar(client, admin_token, db):
    from app.services.service_desk import asistente_del_portal as asistente
    org = _org(db, _ticket(client, admin_token, "empresa"))
    item, _ = _servicio(db, org, is_visible_to_clients=True, description="portatil nuevo para empleado")
    cliente = _cliente_del_portal(db, org)
    antes = db.query(Ticket).count()
    r = asistente.interpretar(db, cliente, "Necesito un portatil nuevo para un empleado")
    assert r["intent"] == "catalog_request" and r["action"]["params"]["service_item_id"] == item.id
    assert db.query(Ticket).count() == antes
    hecho = asistente.confirmar(db, cliente, r["action"]["id"])
    assert hecho["status"] == "executed" and db.query(Ticket).count() == antes + 1
    t = db.query(Ticket).filter(Ticket.id == hecho["ticket_id"]).one()
    assert t.requester_client_id == cliente.id and t.service_item_id == item.id


def test_asistente_sin_integracion_de_contrasena_no_inventa(client, admin_token, db):
    from app.services.service_desk import asistente_del_portal as asistente
    org = _org(db, _ticket(client, admin_token, "empresa"))
    cliente = _cliente_del_portal(db, org)
    assert asistente.interpretar(db, cliente, "He olvidado mi contraseña")["intent"] == "password_reset_unavailable"
    estado = asistente.interpretar(db, cliente, "¿Cómo va INC-9999?")
    assert estado["intent"] == "ticket_status" and estado["result"]["tickets"] == []


def test_politica_del_portal_falla_cerrada():
    from app.services.ai_chat.tool_execution.politica import denegacion_del_portal

    class Cliente:
        is_active, organization_id = True, "1"
    assert denegacion_del_portal(None, Cliente(), "portal_catalog_request") is None
    assert denegacion_del_portal(None, Cliente(), "borrar_todo") is not None
    assert denegacion_del_portal(None, None, "portal_ticket_status") is not None


def test_prediccion_y_triaje_acotados_a_la_empresa(client, admin_token, db):
    tid = _ticket(client, admin_token, "Triaje")
    assert client.post(f"/api/v1/ai-planning/triage/{tid}", headers=auth(admin_token)).status_code == 200
    assert client.post("/api/v1/ai-planning/triage/no-existe", headers=auth(admin_token)).status_code == 404


def test_presencia_caduca_sin_latido():
    import asyncio
    from app.services.service_desk import presencia
    presencia._memoria.clear()
    vivos = asyncio.run(presencia.anotar("t1", "u1", "Ana", "view", 45))
    assert [v["user_id"] for v in vivos] == ["u1"]
    presencia._memoria["t1"]["u1"]["ts"] = (datetime.now(timezone.utc) - timedelta(seconds=100)).timestamp()
    assert asyncio.run(presencia.anotar("t1", "u2", "Luis", "edit", 45))[0]["user_id"] == "u2"
    assert asyncio.run(presencia.anotar("t1", "u2", "Luis", "leave", 45)) == []
