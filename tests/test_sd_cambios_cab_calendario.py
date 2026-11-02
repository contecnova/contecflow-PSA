"""Cambios ITSM: comite con votos, congelaciones, choques y versiones.

Auditoria 2026-11: un PATCH con `status: approved` aprobaba un cambio sin
pasar por el CAB; el CAB era un JSON sin pantalla; y no habia calendario, ni
congelaciones, ni deteccion de choques, ni versiones.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import auth

BASE = "/api/v1/sd"


@pytest.fixture()
def cab(db):
    """La cola CAB: pm (responsable) y dev."""
    from app.models.service_desk import AgentGroup, AgentGroupMember, SupportLevel
    from app.models.settings import AppSetting
    from app.services.settings_service import invalidate_cache

    g = AgentGroup(id="cola-cab", name="CAB", support_level=SupportLevel.l3, organization_id="1")
    db.add(g)
    db.flush()
    db.add_all([AgentGroupMember(group_id=g.id, user_id="pm-test-id", is_lead=True, organization_id="1"),
                AgentGroupMember(group_id=g.id, user_id="dev-test-id", organization_id="1")])
    db.add(AppSetting(key="SD_CAB_GROUP_ID", value=g.id, organization_id="1"))
    db.commit()
    invalidate_cache("SD_CAB_GROUP_ID")
    yield g
    invalidate_cache("SD_CAB_GROUP_ID")


def _cambio(client, token, **extra):
    datos = {"title": "Parche del servidor", "description": "Actualizar kernel", "change_type": "normal", **extra}
    r = client.post(f"{BASE}/changes", headers=auth(token), json=datos)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _patch(client, token, cid, **datos):
    return client.patch(f"{BASE}/changes/{cid}", headers=auth(token), json=datos)


def test_un_patch_no_aprueba_un_cambio(client, admin_token):
    c = _cambio(client, admin_token)
    assert _patch(client, admin_token, c["id"], status="approved").status_code == 409


def test_sin_cab_configurado_un_cambio_normal_no_se_puede_enviar(client, admin_token):
    c = _cambio(client, admin_token)
    r = _patch(client, admin_token, c["id"], status="cab_review")
    assert r.status_code == 409 and "SD_CAB_GROUP_ID" in r.text


def test_el_cab_vota_y_la_mayoria_aprueba(client, admin_token, pm_token, dev_token, cab, db):
    from app.models.service_desk import ChangeApproval

    c = _cambio(client, admin_token)
    assert _patch(client, admin_token, c["id"], status="cab_review").status_code == 200
    assert sorted(a.approver_user_id for a in db.query(ChangeApproval).all()) == ["dev-test-id", "pm-test-id"]
    wf = client.post(f"{BASE}/changes/{c['id']}/cab/vote", headers=auth(pm_token), json={"approve": True}).json()
    assert wf["data"]["workflow"]["status"] == "requester", "1 de 2 no llega a la mayoria (2)"
    client.post(f"{BASE}/changes/{c['id']}/cab/vote", headers=auth(dev_token), json={"approve": True})
    assert client.get(f"{BASE}/changes/{c['id']}", headers=auth(admin_token)).json()["data"]["status"] == "approved"


def test_un_voto_en_contra_que_hace_imposible_el_quorum_rechaza(client, admin_token, pm_token, cab):
    c = _cambio(client, admin_token)
    _patch(client, admin_token, c["id"], status="cab_review")
    client.post(f"{BASE}/changes/{c['id']}/cab/vote", headers=auth(pm_token),
                json={"approve": False, "note": "Sin plan de vuelta atrás"})
    d = client.get(f"{BASE}/changes/{c['id']}", headers=auth(admin_token)).json()["data"]
    assert d["status"] == "cancelled"


def test_en_emergencia_solo_votan_los_responsables(client, admin_token, cab, db):
    from app.models.service_desk import ChangeApproval

    c = _cambio(client, admin_token, change_type="emergency")
    _patch(client, admin_token, c["id"], status="cab_review")
    assert [a.approver_user_id for a in db.query(ChangeApproval).all()] == ["pm-test-id"]


def test_un_estandar_de_bajo_riesgo_se_aprueba_solo_sin_inventar_usuario(client, admin_token, db, monkeypatch):
    from app.models.service_desk import ITSMChangeRequest
    from app.services.service_desk import change_service

    monkeypatch.setattr(change_service, "_auto_score_change",
                        lambda db, ch: setattr(ch, "auto_risk_score", 10.0))
    c = _cambio(client, admin_token, change_type="standard")
    ch = db.get(ITSMChangeRequest, c["id"])
    assert ch.status.value == "approved" and ch.approved_by is None


def test_no_se_programa_en_una_congelacion_salvo_emergencia(client, admin_token, pm_token, cab, db):
    from app.models.service_desk import ITSMChangeRequest

    ini = datetime(2026, 12, 20, tzinfo=timezone.utc)
    r = client.post(f"{BASE}/change-blackouts", headers=auth(admin_token), json={
        "name": "Cierre de año", "start_at": ini.isoformat(), "end_at": (ini + timedelta(days=15)).isoformat()})
    assert r.status_code == 201, r.text
    for tipo, esperado in (("normal", 409), ("emergency", 200)):
        c = _cambio(client, admin_token, change_type=tipo,
                    planned_start="2026-12-24T10:00:00", planned_end="2026-12-24T12:00:00")
        ch = db.get(ITSMChangeRequest, c["id"])
        ch.status = "approved"
        db.commit()
        assert _patch(client, admin_token, c["id"], status="scheduled").status_code == esperado, tipo


def test_el_calendario_marca_los_choques_sobre_el_mismo_ci(client, admin_token, db):
    from app.models.service_desk import ITSMChangeRequest

    ids = []
    for titulo, ci in (("A", ["ci-1", "ci-2"]), ("B", ["ci-2"]), ("C", ["ci-9"])):
        c = _cambio(client, admin_token, title=titulo, planned_start="2026-11-10T10:00:00",
                    planned_end="2026-11-10T12:00:00")
        _patch(client, admin_token, c["id"], affected_cis=ci)
        ch = db.get(ITSMChangeRequest, c["id"])
        ch.status = "approved"
        ids.append(c["id"])
    db.commit()
    cal = client.get(f"{BASE}/change-calendar", headers=auth(admin_token),
                     params={"desde": "2026-11-01T00:00:00Z", "hasta": "2026-12-01T00:00:00Z"}).json()["data"]
    por_titulo = {c["title"]: c for c in cal["changes"]}
    assert [x["cis"] for x in por_titulo["A"]["conflicts"]] == [["ci-2"]]
    assert por_titulo["C"]["conflicts"] == []


def test_una_version_no_se_publica_con_cambios_pendientes(client, admin_token, db):
    r = client.post(f"{BASE}/releases", headers=auth(admin_token), json={"name": "Noviembre", "version": "2026.11"})
    assert r.status_code == 201
    rel = r.json()["data"]["id"]
    c = _cambio(client, admin_token)
    _patch(client, admin_token, c["id"], release_id=rel)
    r = client.put(f"{BASE}/releases/{rel}", headers=auth(admin_token), json={"name": "Noviembre", "status": "released"})
    assert r.status_code == 409 and c["number"] in r.text
    versiones = client.get(f"{BASE}/releases", headers=auth(admin_token)).json()["items"]
    assert [x["number"] for x in versiones[0]["changes"]] == [c["number"]]
