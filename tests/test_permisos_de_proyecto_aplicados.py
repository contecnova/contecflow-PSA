"""Los permisos por proyecto (`project_permissions`) se aplican.

Auditoria 2026-11: la pantalla /project-permissions guardaba nivel e
interruptores y ninguna comprobacion los leia.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.enterprise import ProjectPermission, ProjectPermissionLevel
from tests.conftest import auth


def _proyecto(client, pm_token, code="PERM1"):
    r = client.post("/api/v1/projects", headers=auth(pm_token),
                    json={"name": "Con permisos", "code": code, "status": "active", "billing_type": "time_material"})
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


def _permiso(db, pid, user_id, level, **kw):
    db.add(ProjectPermission(project_id=pid, user_id=user_id, level=ProjectPermissionLevel(level),
                             organization_id="1", **kw))
    db.commit()


def _ids(client, token):
    return {p["id"] for p in client.get("/api/v1/projects", headers=auth(token)).json()["items"]}


def test_EL_HALLAZGO_nivel_none_cierra_el_proyecto(client, pm_token, db):
    pid = _proyecto(client, pm_token)
    _permiso(db, pid, "pm-test-id", "none")
    assert client.get(f"/api/v1/projects/{pid}", headers=auth(pm_token)).status_code == 403
    assert pid not in _ids(client, pm_token)


def test_EL_HALLAZGO_viewer_solo_lee(client, pm_token, db):
    pid = _proyecto(client, pm_token)
    _permiso(db, pid, "pm-test-id", "viewer")
    assert client.get(f"/api/v1/projects/{pid}", headers=auth(pm_token)).status_code == 200
    r = client.patch(f"/api/v1/projects/{pid}", json={"name": "otro"}, headers=auth(pm_token))
    assert r.status_code == 403 and "lectura" in r.text


def test_sin_financieros_no_ve_el_EVM_pero_si_el_proyecto(client, pm_token, db):
    pid = _proyecto(client, pm_token)
    _permiso(db, pid, "pm-test-id", "manager", can_see_financials=False)
    assert client.get(f"/api/v1/projects/{pid}", headers=auth(pm_token)).status_code == 200
    assert client.get(f"/api/v1/projects/{pid}/evm", headers=auth(pm_token)).status_code == 403


def test_sin_exportar_no_exporta(client, pm_token, db):
    pid = _proyecto(client, pm_token)
    _permiso(db, pid, "pm-test-id", "manager", can_export=False)
    assert client.get(f"/api/v1/projects/{pid}/uat/export", headers=auth(pm_token)).status_code == 403


def test_viewer_hace_visible_el_proyecto_a_quien_no_lo_veria(client, pm_token, dev_token, db):
    pid = _proyecto(client, pm_token)
    assert pid not in _ids(client, dev_token)
    _permiso(db, pid, "dev-test-id", "viewer")
    assert pid in _ids(client, dev_token)


def test_un_permiso_caducado_no_cuenta(client, pm_token, db):
    pid = _proyecto(client, pm_token)
    _permiso(db, pid, "pm-test-id", "none", expires_at=datetime.now(timezone.utc) - timedelta(hours=1))
    assert client.get(f"/api/v1/projects/{pid}", headers=auth(pm_token)).status_code == 200


def test_el_admin_no_se_restringe(client, pm_token, admin_token, db):
    pid = _proyecto(client, pm_token)
    _permiso(db, pid, "admin-test-id", "none")
    assert client.get(f"/api/v1/projects/{pid}", headers=auth(admin_token)).status_code == 200
