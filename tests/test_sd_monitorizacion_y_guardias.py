"""Alertas de monitorizacion e incidencias; guardias que avisan.

Auditoria 2026-11: no entraba ninguna alerta (la «correlacion» agrupaba tickets
ya abiertos) y las guardias se definian sin que nada las consultase.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

TOKEN = "token-de-monitorizacion"
URL = "/api/v1/sd/events/prometheus"


@pytest.fixture()
def token(db):
    from app.services.integration_credentials_service import invalidate_cache, set_credential
    set_credential(db, "monitoring", "ingest_token", TOKEN, org_id="1")
    db.commit()
    invalidate_cache("monitoring")
    return TOKEN


def _alertmanager(status="firing", fingerprint="abc", severity="critical", instance="srv-web-01"):
    return {"alerts": [{"status": status, "fingerprint": fingerprint,
                        "labels": {"alertname": "HostDown", "severity": severity, "instance": f"{instance}:9100"},
                        "annotations": {"summary": "srv-web-01 no responde", "description": "Ping perdido"}}]}


def _tickets(db):
    from app.db.session import sin_filtro_de_tenant
    from app.models.service_desk import Ticket
    with sin_filtro_de_tenant(db):
        return db.query(Ticket).all()


def test_sin_token_o_con_token_falso_no_entra(client, db, token):
    assert client.post(URL, json=_alertmanager()).status_code == 403
    assert client.post(URL, json=_alertmanager(), headers={"X-Contecflow-Event-Token": "otro"}).status_code == 403
    assert _tickets(db) == []


def test_una_alerta_abre_una_incidencia_con_su_prioridad_y_su_ci(client, db, token):
    from app.models.service_desk import ConfigurationItem
    db.add(ConfigurationItem(code="srv-web-01", name="Web 1", ci_type="server", organization_id="1"))
    db.commit()
    r = client.post(URL, json=_alertmanager(), headers={"X-Contecflow-Event-Token": token})
    assert r.status_code == 200 and r.json()["data"]["created"] == 1, r.text
    [t] = _tickets(db)
    assert (t.organization_id, t.priority.value, t.source, t.ticket_type.value) == ("1", "p1_critical", "monitoring", "incident")
    assert t.ci_id is not None, "el CI srv-web-01 tenia que quedar enlazado"


def test_la_misma_alerta_no_abre_otra_y_al_recuperarse_la_resuelve(client, db, token):
    from app.models.service_desk import MonitoringAlert
    h = {"X-Contecflow-Event-Token": token}
    client.post(URL, json=_alertmanager(), headers=h)
    r = client.post(URL, json=_alertmanager(), headers=h)
    assert r.json()["data"]["repeated"] == 1 and len(_tickets(db)) == 1
    assert db.query(MonitoringAlert).one().occurrences == 2
    client.post(URL, json=_alertmanager(status="resolved"), headers=h)
    [t] = _tickets(db)
    db.refresh(t)
    assert t.status.value == "resolved" and "Recuperado" in t.resolution


def test_si_un_agente_ya_la_trabaja_no_se_resuelve_sola(client, db, token):
    from app.models.service_desk import TicketComment
    h = {"X-Contecflow-Event-Token": token}
    client.post(URL, json=_alertmanager(), headers=h)
    [t] = _tickets(db)
    db.add(TicketComment(ticket_id=t.id, body="Mirando el balanceador", author_user_id="admin-test-id", organization_id="1"))
    db.commit()
    client.post(URL, json=_alertmanager(status="resolved"), headers=h)
    db.refresh(t)
    assert t.status.value != "resolved"


def test_el_formato_generico_y_sus_errores(client, db, token):
    h = {"X-Contecflow-Event-Token": token}
    assert client.post("/api/v1/sd/events/zabbix", headers=h, json={"title": "sin clave"}).status_code == 422
    r = client.post("/api/v1/sd/events/zabbix", headers=h,
                    json=[{"key": "z-1", "title": "Disco lleno", "severity": "warning"}])
    assert r.json()["data"]["created"] == 1
    assert _tickets(db)[0].priority.value == "p3_medium"


def test_un_p1_avisa_a_quien_esta_de_guardia_tambien_por_sms(db, monkeypatch):
    from app.models.service_desk import AgentGroup, OnCallEntry, OnCallSchedule, SupportLevel, Ticket
    from app.models.user import User, UserRole, UserStatus
    from app.services.service_desk import correo, sms_service
    from app.services.service_desk.ticket_event_processor import procesar_pendientes

    sms, mails = [], []
    monkeypatch.setattr(sms_service, "send_sms", lambda to, body: sms.append(to) or True)
    monkeypatch.setattr(correo, "enviar", lambda *a, **k: mails.append(a[2]) or correo.ResultadoEnvio(True))
    db.add(User(id="guardia-1", username="guardia", email="guardia@x.com", full_name="De Guardia", phone="+34600999888",
                role=UserRole.employee, status=UserStatus.active, is_active=True, hashed_password="x", organization_id="1"))
    g = AgentGroup(id="cola-n2", name="N2", support_level=SupportLevel.l2, organization_id="1")
    db.add(g)
    db.flush()
    s = OnCallSchedule(name="Noches", group_id=g.id, organization_id="1")
    db.add(s)
    db.flush()
    ahora = datetime.now(timezone.utc)
    db.add(OnCallEntry(schedule_id=s.id, user_id="guardia-1", start_dt=ahora - timedelta(hours=1),
                       end_dt=ahora + timedelta(hours=7), organization_id="1"))
    for numero, prioridad in (("INC-0001", "p1_critical"), ("INC-0002", "p4_low")):
        db.add(Ticket(number=numero, ticket_type="incident", title="Caida", description="d", priority=prioridad,
                      organization_id="1", assigned_group_id=g.id, requester_email="c@x.com"))
    db.commit()
    procesar_pendientes(db)
    assert sms == ["+34600999888"], "solo el P1 pagina, y por SMS"
    assert mails.count("guardia@x.com") == 1
