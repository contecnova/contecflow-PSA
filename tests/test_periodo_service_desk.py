"""Periodo libre (16-11-2026) en service desk, proyectos ágiles, ALM, aprobaciones y NPS.

Cada informe migrado acepta `desde`/`hasta`/`granularidad`/`tz` (app/core/periodo.py)
y sigue aceptando su parámetro histórico (`days`, `date_from`/`date_to`,
`from`/`to`). Se comprueba: el alias sigue funcionando, `desde`/`hasta` filtra,
la hora se rechaza donde el dato es de calendario, y los horizontes de ALM
miran hacia delante.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.models.service_desk import Ticket
from tests.conftest import auth

UTC = timezone.utc


def _ticket(client, token, titulo="Caso"):
    r = client.post("/api/v1/sd/tickets", headers=auth(token), json={
        "title": titulo, "description": "x", "priority": "p3_medium", "ticket_type": "incident"})
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


def _iso(d: datetime) -> str:
    return d.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")


# ── Service desk: /sd/metrics/itil y /sd/metrics/agent-performance ───────────
def test_itil_alias_days_y_fechas_historicas_inclusivas(client, admin_token):
    r = client.get("/api/v1/sd/metrics/itil", params={"days": 7}, headers=auth(admin_token))
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["periodo"]["origen"] == "days"
    assert "period" in d and "volume" in d

    # date_from/date_to: la fecha final es inclusiva (hasta = día siguiente).
    r = client.get("/api/v1/sd/metrics/itil", params={"date_from": "2026-11-01", "date_to": "2026-11-10", "tz": "UTC"},
                   headers=auth(admin_token))
    assert r.status_code == 200, r.text
    p = r.json()["data"]["periodo"]
    assert p["origen"] == "rango"
    assert p["desde"].startswith("2026-11-01T00:00") and p["hasta"].startswith("2026-11-11T00:00")


def test_itil_desde_hasta_filtra_por_creacion(client, admin_token, db):
    dentro, fuera = _ticket(client, admin_token, "dentro"), _ticket(client, admin_token, "fuera")
    base = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
    db.query(Ticket).filter(Ticket.id == dentro).update({"created_at": base})
    db.query(Ticket).filter(Ticket.id == fuera).update({"created_at": base - timedelta(days=20)})
    db.commit()

    r = client.get("/api/v1/sd/metrics/itil", params={
        "desde": "2026-03-10T00:00", "hasta": "2026-03-11T00:00", "tz": "UTC"}, headers=auth(admin_token))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["volume"]["total"] == 1

    # Por hora también se admite (los tickets tienen instante).
    r = client.get("/api/v1/sd/metrics/itil", params={
        "desde": "2026-03-10T12:00", "hasta": "2026-03-10T13:00", "tz": "UTC", "granularidad": "hour"},
        headers=auth(admin_token))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["volume"]["total"] == 1


def test_itil_desde_mayor_que_hasta_es_422_traducible(client, admin_token):
    r = client.get("/api/v1/sd/metrics/itil", params={"desde": "2026-03-10", "hasta": "2026-03-01"},
                   headers=auth(admin_token))
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "periodo.desde_mayor_que_hasta"


def test_rendimiento_de_agentes_filtra_por_periodo(client, admin_token, db):
    tid = _ticket(client, admin_token)
    db.query(Ticket).filter(Ticket.id == tid).update({
        "assigned_to_user_id": "dev-test-id", "created_at": datetime(2026, 2, 5, 9, 0, tzinfo=UTC)})
    db.commit()
    dentro = client.get("/api/v1/sd/metrics/agent-performance",
                        params={"desde": "2026-02-01", "hasta": "2026-02-10", "tz": "UTC"}, headers=auth(admin_token))
    fuera = client.get("/api/v1/sd/metrics/agent-performance",
                       params={"desde": "2026-01-01", "hasta": "2026-01-10", "tz": "UTC"}, headers=auth(admin_token))
    assert dentro.status_code == 200 and fuera.status_code == 200
    assert any(a["agent_id"] == "dev-test-id" for a in dentro.json()["data"])
    assert not any(a["agent_id"] == "dev-test-id" for a in fuera.json()["data"])
    assert client.get("/api/v1/sd/metrics/agent-performance", params={"days": 30},
                      headers=auth(admin_token)).status_code == 200


# ── Panel de agente: /cmdb/agent-dashboard/{id} ──────────────────────────────
def test_panel_de_agente_por_hora_y_rango(client, admin_token, db):
    tid = _ticket(client, admin_token)
    db.query(Ticket).filter(Ticket.id == tid).update({
        "assigned_to_user_id": "dev-test-id", "status": "resolved",
        "resolved_at": datetime(2026, 4, 2, 10, 30, tzinfo=UTC), "resolution_minutes": 60})
    db.commit()
    r = client.get("/api/v1/cmdb/agent-dashboard/dev-test-id", params={
        "desde": "2026-04-02T08:00", "hasta": "2026-04-02T14:00", "tz": "UTC", "granularidad": "hour"},
        headers=auth(admin_token))
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["periodo"]["granularidad"] == "hour" and len(d["trend"]) == 6
    assert d["kpis"]["total_resolved"] == 1
    assert [p["resolved"] for p in d["trend"]] == [0, 0, 1, 0, 0, 0]


# ── Flujo acumulado: /epics/cfd ──────────────────────────────────────────────
def _proyecto(client, token):
    r = client.post("/api/v1/projects", json={"name": "CFD periodo", "code": "CFDP1", "status": "active",
                                              "billing_type": "time_material"}, headers=auth(token))
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


def test_cfd_alias_days_rango_y_ultima_foto_por_semana(client, admin_token, db):
    from app.models.epics import TaskStateSnapshot
    pid = _proyecto(client, admin_token)
    for dia, n in (("2026-06-01", 1), ("2026-06-03", 3), ("2026-06-09", 5), ("2026-05-01", 9)):
        db.add(TaskStateSnapshot(project_id=pid, snap_date=dia, status="done", count=n))
    db.commit()

    r = client.get("/api/v1/epics/cfd", params={"project_id": pid, "days": 30}, headers=auth(admin_token))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["periodo"]["origen"] == "days"

    # Lunes 1 y lunes 8 de junio de 2026: dos semanas; cada una toma su última foto.
    r = client.get("/api/v1/epics/cfd", params={"project_id": pid, "desde": "2026-06-01", "hasta": "2026-06-15",
                                                "tz": "UTC", "granularidad": "week"}, headers=auth(admin_token))
    assert r.status_code == 200, r.text
    data = r.json()["data"]["data"]
    assert [(p["date"], p["done"]) for p in data] == [("2026-06-03", 3), ("2026-06-09", 5)]
    assert all("t" in p for p in data)


def test_cfd_rechaza_hora(client, admin_token):
    r = client.get("/api/v1/epics/cfd", params={"project_id": "x", "days": 7, "granularidad": "hour"},
                   headers=auth(admin_token))
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "periodo.hora_no_admitida"


# ── NPS: /nps/{id}/summary y /nps/health/trend ───────────────────────────────
def _cliente(client, token):
    r = client.post("/api/v1/clients", json={"name": "NPS periodo", "industry": "technology", "country": "ES"},
                    headers=auth(token))
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


def test_nps_alias_days_y_desde_hasta(client, admin_token, db):
    from app.models.nps import ClientNPS
    cid = _cliente(client, admin_token)
    for score in (10, 9):
        assert client.post(f"/api/v1/nps/{cid}/responses", json={"score": score, "source": "survey"},
                           headers=auth(admin_token)).status_code in (200, 201)
    viejo = db.query(ClientNPS).filter(ClientNPS.client_id == cid).first()
    viejo.created_at = datetime(2026, 1, 15, 10, 0, tzinfo=UTC)
    db.commit()

    r = client.get(f"/api/v1/nps/{cid}/summary", params={"days": 30}, headers=auth(admin_token))
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["total"] == 1 and d["days"] == 30 and d["periodo"]["origen"] == "days"

    r = client.get(f"/api/v1/nps/{cid}/summary", params={"desde": "2026-01-01", "hasta": "2026-02-01",
                                                         "tz": "UTC", "granularidad": "week"}, headers=auth(admin_token))
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["total"] == 1 and d["nps"] == 100.0
    assert all("t" in p for p in d["trend"]) and sum(p["count"] for p in d["trend"]) == 1
    assert any(p["nps"] is None for p in d["trend"])  # tramos sin respuestas: sin NPS, no 0


def test_nps_tendencia_de_salud_es_serie_del_periodo(client, admin_token):
    r = client.get("/api/v1/nps/health/trend", params={"days": 14, "granularidad": "day"}, headers=auth(admin_token))
    assert r.status_code == 200, r.text
    serie = r.json()["data"]
    assert len(serie) in (14, 15) and all("t" in p and "avg_health" in p for p in serie)


# ── Aprobaciones: /approvals/analytics/* ─────────────────────────────────────
def test_aprobaciones_alias_days_y_serie(client, admin_token):
    r = client.get("/api/v1/approvals/analytics/bottlenecks", params={"days": 30}, headers=auth(admin_token))
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["periodo"]["origen"] == "days" and d["days"] == 30
    assert isinstance(d["trend"], list) and all("t" in p for p in d["trend"])

    r = client.get("/api/v1/approvals/analytics/approver-load",
                   params={"desde": "2026-01-01", "hasta": "2026-02-01", "tz": "UTC"}, headers=auth(admin_token))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["periodo"]["origen"] == "rango"


def test_aprobaciones_days_fuera_de_rango_historico(client, admin_token):
    r = client.get("/api/v1/approvals/analytics/approver-load", params={"days": 400}, headers=auth(admin_token))
    assert r.status_code == 422


# ── ALM: horizontes hacia delante y costes ───────────────────────────────────
def _activo_que_vence(client, db, token, en_dias: int):
    from app.models.alm import ALMAsset
    r = client.post("/api/v1/alm/assets", json={"name": f"Equipo vence {en_dias}", "type": "laptop"},
                    headers=auth(token))
    assert r.status_code == 200, r.text
    aid = r.json()["data"]["id"]
    db.query(ALMAsset).filter(ALMAsset.id == aid).update(
        {"warranty_expiry": date.today() + timedelta(days=en_dias)})
    db.commit()
    return aid


def test_alm_vencimientos_miran_hacia_delante(client, admin_token, db):
    cerca = _activo_que_vence(client, db, admin_token, 10)
    lejos = _activo_que_vence(client, db, admin_token, 200)

    r = client.get("/api/v1/alm/assets/expiring", params={"days": 30}, headers=auth(admin_token))
    assert r.status_code == 200, r.text
    ids = {f["asset_id"] for f in r.json()["data"]}
    assert cerca in ids and lejos not in ids

    desde = (date.today() + timedelta(days=150)).isoformat()
    hasta = (date.today() + timedelta(days=250)).isoformat()
    r = client.get("/api/v1/alm/assets/expiring", params={"desde": desde, "hasta": hasta}, headers=auth(admin_token))
    assert r.status_code == 200, r.text
    ids = {f["asset_id"] for f in r.json()["data"]}
    assert lejos in ids and cerca not in ids


def test_alm_horizontes_rechazan_hora(client, admin_token):
    for ruta in ("/api/v1/alm/assets/expiring", "/api/v1/alm/renewals"):
        r = client.get(ruta, params={"days": 30, "granularidad": "hour"}, headers=auth(admin_token))
        assert r.status_code == 422, ruta
        assert r.json()["detail"]["code"] == "periodo.hora_no_admitida"
    assert client.get("/api/v1/alm/renewals", params={"days": 120}, headers=auth(admin_token)).status_code == 200


def test_alm_costes_desde_hasta_y_from_to(client, admin_token):
    viejo = client.get("/api/v1/alm/costs", params={"from": "2026-11-01", "to": "2026-11-30"}, headers=auth(admin_token))
    nuevo = client.get("/api/v1/alm/costs", params={"desde": "2026-11-01", "hasta": "2026-12-01", "tz": "UTC"},
                       headers=auth(admin_token))
    assert viejo.status_code == 200, viejo.text
    assert nuevo.status_code == 200, nuevo.text
    assert viejo.json()["data"] == nuevo.json()["data"]
    r = client.get("/api/v1/alm/costs", params={"days": 7, "granularidad": "hour"}, headers=auth(admin_token))
    assert r.status_code == 422
