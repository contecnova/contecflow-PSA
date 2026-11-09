"""Tests for Office 365 BI integration endpoints."""
from tests.conftest import auth


def test_get_o365_config_default(client, admin_token):
    r = client.get("/api/v1/bi/o365/config", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "enabled" in data
    assert "tenant_id" in data


def test_save_o365_config(client, admin_token):
    payload = {
        "enabled": True,
        "tenant_id": "test-tenant-123",
        "client_id": "app-client-abc",
        "client_secret": "super-secret",
        "sync_schedule": "0 2 * * *",
        "reports": ["teams_activity", "email_activity"],
    }
    r = client.put("/api/v1/bi/o365/config", json=payload, headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["tenant_id"] == "test-tenant-123"
    # client_secret must NOT be stored/returned
    assert "client_secret" not in data or data.get("client_secret") in (None, "", "***")






def test_get_o365_report_teams(client, admin_token):
    r = client.get("/api/v1/bi/o365/reports/teams_activity", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "report" in data or "rows" in data


def test_get_o365_report_unknown(client, admin_token):
    r = client.get("/api/v1/bi/o365/reports/nonexistent_report_xyz", headers=auth(admin_token))
    assert r.status_code in (404, 400)


def test_get_o365_adoption(client, admin_token):
    r = client.get("/api/v1/bi/o365/adoption", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert isinstance(data, dict)


def test_get_o365_sync_log(client, admin_token):
    r = client.get("/api/v1/bi/o365/sync-log", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "log" in data or "entries" in data


def test_o365_auth_required(client):
    r = client.get("/api/v1/bi/o365/config")
    assert r.status_code == 401


# ── Revisión 2026-11 ──────────────────────────────────────────────────────────
# El test anterior de sincronización parcheaba `requests`, pero el servicio usa
# `httpx`: llamaba a Microsoft de verdad y aceptaba cualquier respuesta.

class _Resp:
    def __init__(self, status, json_=None, text=""):
        self.status_code, self._json, self.text = status, json_, text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"{self.status_code} de Graph")

    def json(self):
        return self._json


class _Graph:
    """Microsoft de mentira: token bueno y un informe que falla."""
    falla = "getEmailActivityUserDetail"
    secretos: list = []

    def __init__(self, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def post(self, url, data=None, **kw):
        _Graph.secretos.append(data["client_secret"])
        return _Resp(200, {"access_token": "tok"})

    def get(self, url, **kw):
        if self.falla in url:
            return _Resp(403)
        return _Resp(200, text="User Principal Name,Has Any Product,Is Licensed For Teams,Is Licensed For Viva\nu1,True,True,False\nu2,False,False,True\n")


def test_EL_HALLAZGO_el_secreto_se_guarda_y_un_informe_que_falla_no_es_ok(client, db, admin_token, monkeypatch):
    import httpx
    from app.models.settings import AppSetting
    monkeypatch.setattr(httpx, "Client", _Graph)
    _Graph.secretos = []
    r = client.put("/api/v1/bi/o365/config", headers=auth(admin_token),
                   json={"enabled": True, "tenant_id": "t1", "client_id": "c1", "client_secret": "secreto-claro"})
    assert r.json()["data"]["secret_puesto"] is True and "client_secret" not in r.json()["data"]
    assert "secreto-claro" not in db.query(AppSetting).filter(AppSetting.key == "bi.o365.config").one().value
    d = client.post("/api/v1/bi/o365/sync", headers=auth(admin_token)).json()["data"]
    assert _Graph.secretos == ["secreto-claro"]                 # descifrado al usarlo, sin teclearlo otra vez
    assert d["ok"] is False and "email_activity" in d["error"] and "403" in d["error"]
    por = {x["report"]: x for x in d["synced"]}
    assert por["teams_activity"]["ok"] and por["teams_activity"]["records"] == 2
    a = client.get("/api/v1/bi/o365/adoption", headers=auth(admin_token)).json()["data"]
    assert a["by_product"] == {"Teams": 1, "Viva": 1}            # de las columnas, no de una lista fija
    log = client.get("/api/v1/bi/o365/sync-log", headers=auth(admin_token)).json()["data"]["entries"]
    assert log[-1]["ok"] is False


def test_sin_secreto_lo_dice(client, admin_token):
    client.put("/api/v1/bi/o365/config", headers=auth(admin_token), json={"enabled": True, "tenant_id": "t1", "client_id": "c1"})
    d = client.post("/api/v1/bi/o365/sync", headers=auth(admin_token)).json()["data"]
    assert d["ok"] is False and "secret" in d["error"]


def test_informe_desconocido_en_la_config_se_rechaza(client, admin_token):
    r = client.put("/api/v1/bi/o365/config", headers=auth(admin_token), json={"enabled_reports": ["inventado"]})
    assert r.status_code == 400
