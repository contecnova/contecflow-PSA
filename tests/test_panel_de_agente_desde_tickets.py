"""Panel de agente: se calcula sobre los tickets, no sobre fotos vacias.

Auditoria 2026-11: leia `agent_metric_snapshots`, que solo llenaba un boton con
ceros; resueltos, tiempo medio, SLA y CSAT salian siempre a 0. Y cualquier
usuario podia leer el rendimiento de cualquier agente.
"""
from datetime import datetime, timedelta, timezone

from app.models.service_desk import Ticket
from tests.conftest import auth


def _ticket(client, token):
    r = client.post("/api/v1/sd/tickets", headers=auth(token), json={
        "title": "Caso", "description": "x", "priority": "p3_medium", "ticket_type": "incident"})
    return r.json()["data"]["id"]


def test_resueltos_tiempo_sla_y_csat_salen_de_los_tickets(client, admin_token, db):
    ahora = datetime.now(timezone.utc)
    ids = [_ticket(client, admin_token) for _ in range(3)]
    datos = [
        {"status": "resolved", "resolved_at": ahora - timedelta(hours=2), "resolution_minutes": 120,
         "sla_resolution_breached": False, "csat_score": 5},
        {"status": "closed", "resolved_at": ahora - timedelta(days=1), "resolution_minutes": 240,
         "sla_resolution_breached": True, "csat_score": 3},
        {"status": "in_progress"},
    ]
    for tid, d in zip(ids, datos):
        db.query(Ticket).filter(Ticket.id == tid).update({"assigned_to_user_id": "dev-test-id", **d})
    db.commit()

    r = client.get("/api/v1/cmdb/agent-dashboard/dev-test-id?days=7", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["current"]["open_tickets"] == 1
    assert d["kpis"] == {"total_resolved": 2, "avg_resolution_hours": 3.0,
                         "sla_compliance_pct": 50, "avg_csat": 4.0}
    assert len(d["trend"]) == 7 and sum(p["resolved"] for p in d["trend"]) == 2


def test_un_empleado_no_lee_el_panel_de_otro(client, dev_token):
    r = client.get("/api/v1/cmdb/agent-dashboard/admin-test-id", headers=auth(dev_token))
    assert r.status_code == 403
