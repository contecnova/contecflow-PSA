"""Tests: M365 BI Embed — Teams, SharePoint, Excel y Word export.

Cubre los 6 endpoints de /m365/bi/* con mocks de Graph API y servicios BI
para garantizar el comportamiento sin dependencias externas.
"""
import io
import pytest
from tests.conftest import auth


# ── Helpers ────────────────────────────────────────────────────────────────────

_SNAPSHOT = {
    "dashboard_id": "executive",
    "organization_id": "1",
    "generated_at": "2024-01-15T12:00:00+00:00",
    "latest_month": "2024-01",
    "latest_revenue": 120_000.0,
    "latest_cost": 80_000.0,
    "latest_hours": 2_500.0,
    "forecast_3m": [
        {"month": "2024-02", "predicted": 125_000.0},
        {"month": "2024-03", "predicted": 130_000.0},
        {"month": "2024-04", "predicted": 132_000.0},
    ],
    "anomaly_count": 1,
    "anomalies": [{"month": "2023-11", "revenue": 90_000.0, "z_score": -2.3, "direction": "low", "severity": "medium"}],
    "overrun_engine": "lgbm",
    "overrun_predictions": [{"project_name": "Proj A", "overrun_probability": 0.75, "risk_level": "high"}],
}

_TOKEN_DATA = {
    "token": "test.embed.token",
    "expires_at": "2024-01-16T12:00:00+00:00",
}


@pytest.fixture(autouse=True)
def mock_bi_deps(monkeypatch):
    """Mock BI intelligence + embed token services para todos los tests del módulo."""
    import app.services.m365_bi_embed_service as embed_svc

    monkeypatch.setattr(embed_svc, "get_dashboard_snapshot", lambda db, **kw: _SNAPSHOT)
    monkeypatch.setattr(embed_svc, "create_embed_token", lambda db, org, user, dash, scopes, ttl: _TOKEN_DATA)


# ── GET /m365/bi/status ────────────────────────────────────────────────────────

def test_m365_bi_status_unauthenticated(client):
    res = client.get("/api/v1/m365/bi/status")
    assert res.status_code in (401, 403)


def test_m365_bi_status_returns_capabilities(client, admin_token):
    res = client.get("/api/v1/m365/bi/status", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert "capabilities" in data
    assert "excel_export" in data["capabilities"]
    assert data["capabilities"]["excel_export"] is True
    assert data["capabilities"]["word_export"] is True


# ── POST /m365/bi/teams/tab ────────────────────────────────────────────────────

def test_teams_tab_config_returns_embed_url(client, admin_token):
    """Con register_via_graph=False devuelve config local sin llamar a Graph."""
    res = client.post(
        "/api/v1/m365/bi/teams/tab",
        json={"dashboard_id": "executive", "register_via_graph": False},
        headers=auth(admin_token),
    )
    assert res.status_code == 200
    data = res.json()
    assert "embed_token" in data
    assert data["embed_token"] == "test.embed.token"
    assert "content_url" in data
    assert "executive" in data["content_url"]
    assert data["graph_registered"] is False


def test_teams_tab_config_graph_register_no_m365(client, admin_token, monkeypatch):
    """register_via_graph=True pero Graph no configurado → graceful (graph_error en respuesta)."""
    import app.services.m365_bi_embed_service as embed_svc

    def _mock_graph_post(path, payload):
        raise RuntimeError("Graph not configured")

    monkeypatch.setattr(embed_svc, "require_m365", lambda: None)  # bypass require check
    monkeypatch.setattr(embed_svc, "graph_post_sync", _mock_graph_post)

    res = client.post(
        "/api/v1/m365/bi/teams/tab",
        json={
            "dashboard_id": "executive",
            "team_id": "team-abc",
            "channel_id": "chan-xyz",
            "register_via_graph": True,
        },
        headers=auth(admin_token),
    )
    assert res.status_code == 200
    data = res.json()
    # Graph failed gracefully — token still returned
    assert data["embed_token"] == "test.embed.token"
    assert data["graph_registered"] is False
    assert "graph_error" in data


# ── POST /m365/bi/teams/card ───────────────────────────────────────────────────

def test_teams_card_graph_success(client, admin_token, monkeypatch):
    """Cuando Graph está configurado, posta via Graph API."""
    import app.services.m365_bi_embed_service as embed_svc
    import httpx

    monkeypatch.setattr(embed_svc, "m365_configured", lambda: True)
    monkeypatch.setattr(embed_svc, "get_graph_token_sync", lambda: "bearer-token")

    class _MockResp:
        status_code = 201
        def raise_for_status(self): pass
        def json(self): return {"id": "msg-1", "webUrl": "https://teams.example/msg-1"}

    class _MockClient:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, *a, **kw): return _MockResp()

    monkeypatch.setattr(embed_svc.httpx, "Client", lambda **kw: _MockClient())

    res = client.post(
        "/api/v1/m365/bi/teams/card",
        json={"dashboard_id": "executive", "team_id": "team-1", "channel_id": "chan-1"},
        headers=auth(admin_token),
    )
    assert res.status_code == 200
    data = res.json()
    assert data["channel"] == "graph"
    assert data["message_id"] == "msg-1"


def test_teams_card_fallback_to_webhook(client, admin_token, monkeypatch):
    """Cuando Graph no está disponible, usa el webhook Teams."""
    import app.services.m365_bi_embed_service as embed_svc
    import app.core.config as cfg_mod

    monkeypatch.setattr(embed_svc, "m365_configured", lambda: False)
    monkeypatch.setattr(cfg_mod.settings, "TEAMS_WEBHOOK_URL", "https://webhook.example/hook", raising=False)
    monkeypatch.setattr(embed_svc.settings, "TEAMS_WEBHOOK_URL", "https://webhook.example/hook", raising=False)

    class _MockResp:
        status_code = 200
        text = "1"

    class _MockClient:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, *a, **kw): return _MockResp()

    monkeypatch.setattr(embed_svc.httpx, "Client", lambda **kw: _MockClient())

    res = client.post(
        "/api/v1/m365/bi/teams/card",
        json={"dashboard_id": "executive", "team_id": "team-1", "channel_id": "chan-1"},
        headers=auth(admin_token),
    )
    assert res.status_code == 200
    data = res.json()
    assert data["channel"] == "webhook"


def test_teams_card_no_graph_no_webhook(client, admin_token, monkeypatch):
    """Sin Graph ni webhook → 503."""
    import app.services.m365_bi_embed_service as embed_svc

    monkeypatch.setattr(embed_svc, "m365_configured", lambda: False)
    monkeypatch.setattr(embed_svc.settings, "TEAMS_WEBHOOK_URL", None, raising=False)

    res = client.post(
        "/api/v1/m365/bi/teams/card",
        json={"dashboard_id": "executive", "team_id": "team-1", "channel_id": "chan-1"},
        headers=auth(admin_token),
    )
    assert res.status_code == 503


# ── GET /m365/bi/sharepoint/webpart ───────────────────────────────────────────

def test_sharepoint_webpart_config_returns_iframe(client, admin_token):
    res = client.get(
        "/api/v1/m365/bi/sharepoint/webpart?dashboard_id=executive",
        headers=auth(admin_token),
    )
    assert res.status_code == 200
    data = res.json()
    assert "iframe_html" in data
    assert "<iframe" in data["iframe_html"]
    assert "test.embed.token" in data["iframe_html"]
    assert "embed_url" in data
    assert "expires_at" in data


# ── POST /m365/bi/sharepoint/page ─────────────────────────────────────────────

def test_sharepoint_page_no_m365_returns_503(client, admin_token):
    """Sin M365 configurado → require_m365 lanza 503."""
    res = client.post(
        "/api/v1/m365/bi/sharepoint/page",
        json={"site_id": "site-abc", "page_title": "BI Report", "dashboard_id": "executive"},
        headers=auth(admin_token),
    )
    assert res.status_code == 503


def test_sharepoint_page_graph_success(client, admin_token, monkeypatch):
    import app.services.m365_bi_embed_service as embed_svc

    monkeypatch.setattr(embed_svc, "require_m365", lambda: None)
    monkeypatch.setattr(embed_svc, "get_graph_token_sync", lambda: "bearer-token")

    class _MockResp:
        status_code = 201
        def raise_for_status(self): pass
        def json(self): return {"id": "page-1", "name": "bi.aspx", "webUrl": "https://sp.example/bi.aspx"}

    class _MockClient:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, *a, **kw): return _MockResp()

    monkeypatch.setattr(embed_svc.httpx, "Client", lambda **kw: _MockClient())

    res = client.post(
        "/api/v1/m365/bi/sharepoint/page",
        json={"site_id": "site-abc", "page_title": "BI Report", "dashboard_id": "executive"},
        headers=auth(admin_token),
    )
    assert res.status_code == 200
    data = res.json()
    assert data["created"] is True
    assert data["page_id"] == "page-1"


# ── GET /m365/bi/export/excel ─────────────────────────────────────────────────

def test_excel_export_returns_xlsx(client, admin_token, monkeypatch):
    """Exporta un xlsx real — verifica Content-Type y encabezados xlsx."""
    import app.services.m365_bi_embed_service as embed_svc

    # Provide minimal BI data so openpyxl actually runs
    def _forecast(db, **kw):
        return {
            "history": [{"month": "2024-01", "revenue": 100000, "cost": 70000, "hours": 2000}],
            "forecast": [{"month": "2024-02", "predicted_revenue": 110000, "lower_bound": 100000, "upper_bound": 120000}],
        }

    def _anomalies(db, **kw):
        return {"items": [{"month": "2023-11", "revenue": 85000, "z_score": -2.1, "direction": "low", "severity": "medium"}]}

    def _overrun(db, **kw):
        return {"engine": "lgbm", "predictions": [{"project_name": "P1", "overrun_probability": 0.6, "risk_level": "high"}]}

    monkeypatch.setattr(embed_svc.bi_svc, "ml_forecast_revenue", _forecast)
    monkeypatch.setattr(embed_svc.bi_svc, "ml_detect_revenue_anomalies", _anomalies)
    monkeypatch.setattr(embed_svc.bi_svc, "ml_predict_project_overrun_lgbm", _overrun)

    res = client.get(
        "/api/v1/m365/bi/export/excel?dashboard_id=executive",
        headers=auth(admin_token),
    )
    assert res.status_code == 200
    ct = res.headers.get("content-type", "")
    assert "spreadsheetml" in ct or "octet-stream" in ct
    # PK header — valid xlsx (ZIP format)
    assert res.content[:2] == b"PK"


def test_excel_export_upload_without_upn_returns_400(client, admin_token):
    res = client.get(
        "/api/v1/m365/bi/export/excel?dashboard_id=executive&upload_to_onedrive=true",
        headers=auth(admin_token),
    )
    assert res.status_code == 400


# ── GET /m365/bi/export/word ──────────────────────────────────────────────────

def test_word_export_returns_rtf(client, admin_token):
    """Exporta RTF — verifica Content-Type y cabecera {\rtf1."""
    res = client.get(
        "/api/v1/m365/bi/export/word?dashboard_id=executive",
        headers=auth(admin_token),
    )
    assert res.status_code == 200
    ct = res.headers.get("content-type", "")
    assert "rtf" in ct or "octet-stream" in ct
    # RTF files always start with {\rtf1
    assert res.content.startswith(b"{\\rtf1")


def test_word_export_upload_without_upn_returns_400(client, admin_token):
    res = client.get(
        "/api/v1/m365/bi/export/word?dashboard_id=executive&upload_to_onedrive=true",
        headers=auth(admin_token),
    )
    assert res.status_code == 400
