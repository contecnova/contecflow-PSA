"""Página de indicadores para un iframe (revisión 2026-11).

Medido el 09-11-2026: la pestaña de Teams y la parte web de SharePoint enlazaban
a `/embed/bi`, que no existía, y toda la web sale con `X-Frame-Options: DENY`;
había además una segunda API de incrustación (`/bi/platform/embed/*`) cuyo token
no abría nada. Ahora la página la sirve la API, valida el token y dice quién puede
incrustarla.
"""
import pytest

from app.services import m365_bi_embed_service as m365
from tests.conftest import auth

FOTO = {"dashboard_id": "executive", "generated_at": "2026-11-09T10:00:00", "latest_month": "2026-10",
        "latest_revenue": 12345.0, "latest_cost": 6789.0, "latest_hours": 321.0, "anomaly_count": 2,
        "forecast_3m": [{"month": "2026-11", "predicted": 13000.0}], "anomalies": [],
        "overrun_predictions": [{"project_name": "ERP <Acme>", "risk_level": "high"}]}


@pytest.fixture(autouse=True)
def foto(monkeypatch):
    monkeypatch.setattr(m365, "get_dashboard_snapshot", lambda db, **k: FOTO)


def _token(client, token, dashboard="executive"):
    r = client.post("/api/v1/bi/embed/token", headers=auth(token), json={"dashboard_id": dashboard})
    assert r.status_code == 200, r.text
    return r.json()


def test_EL_HALLAZGO_el_token_abre_la_pagina_y_dice_quien_puede_incrustarla(client, admin_token):
    t = _token(client, admin_token)["token"]
    r = client.get("/api/v1/bi/embed/view", params={"dashboard_id": "executive", "token": t, "org": "1"})
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "12,345" in r.text and "ERP &lt;Acme&gt;" in r.text            # escapado
    csp = r.headers["content-security-policy"]
    assert "frame-ancestors 'self' https://teams.microsoft.com" in csp and "https://*.sharepoint.com" in csp
    assert "x-frame-options" not in {k.lower() for k in r.headers}


def test_otro_panel_otra_empresa_o_revocado_no_abren_nada(client, admin_token):
    datos = _token(client, admin_token)
    t = datos["token"]
    assert client.get("/api/v1/bi/embed/view", params={"dashboard_id": "otro", "token": t, "org": "1"}).status_code == 401
    assert client.get("/api/v1/bi/embed/view", params={"dashboard_id": "executive", "token": t, "org": "2"}).status_code == 401
    from jose import jwt
    jti = jwt.get_unverified_claims(t)["jti"]
    client.delete(f"/api/v1/bi/embed/token/{jti}", headers=auth(admin_token))
    assert client.get("/api/v1/bi/embed/view", params={"dashboard_id": "executive", "token": t, "org": "1"}).status_code == 401


def test_teams_y_sharepoint_enlazan_a_la_pagina_que_existe(db):
    tab = m365.generate_teams_tab_config(db, dashboard_id="executive", org_id="1", user_id="u")
    parte = m365.get_sharepoint_webpart_config(db, dashboard_id="executive", org_id="1", user_id="u")
    for url in (tab["content_url"], parte["embed_url"]):
        assert "/api/v1/bi/embed/view?dashboard_id=executive&token=" in url and "&org=1" in url


def test_la_api_duplicada_ya_no_esta(client, admin_token):
    assert client.post("/api/v1/bi/platform/embed/token", headers=auth(admin_token), json={"dashboard_key": "x"}).status_code in (404, 405)


def test_la_empresa_anade_sus_dominios(client, admin_token):
    client.put("/api/v1/bi/embed/config", headers=auth(admin_token), json={"csp_frame_ancestors": ["https://intranet.acme.com"]})
    t = _token(client, admin_token)["token"]
    r = client.get("/api/v1/bi/embed/view", params={"dashboard_id": "executive", "token": t, "org": "1"})
    assert "https://intranet.acme.com" in r.headers["content-security-policy"]
