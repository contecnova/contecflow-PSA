import httpx

from tests.conftest import auth


def _graph_http_error(status_code: int, body_text: str) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "https://graph.microsoft.com/v1.0/test")
    resp = httpx.Response(status_code, text=body_text, request=req)
    return httpx.HTTPStatusError("boom", request=req, response=resp)


def test_m365_calendar_sync_does_not_leak_graph_response(monkeypatch, client, admin_token):
    import app.api.v1.endpoints.m365 as m365_ep

    monkeypatch.setattr(m365_ep, "_require_m365", lambda: None)

    async def _raise_graph_error(_path):
        raise _graph_http_error(400, '{"error":"secret-graph-token"}')

    monkeypatch.setattr(m365_ep, "_graph_get", _raise_graph_error)

    res = client.post(
        "/api/v1/m365/calendar/sync",
        params={"user_upn": "alice@example.com"},
        headers=auth(admin_token),
    )

    assert res.status_code == 400
    detail = res.json().get("detail") or ""
    assert detail == "Graph API request failed"
    assert "secret-graph-token" not in detail


def test_m365_teams_notify_does_not_leak_webhook_response(monkeypatch, client, admin_token):
    import app.api.v1.endpoints.m365 as m365_ep

    class _Resp:
        status_code = 400
        text = "upstream secret: teams-hook-token"

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            return _Resp()

    monkeypatch.setattr(m365_ep.httpx, "AsyncClient", lambda **kwargs: _Client())

    res = client.post(
        "/api/v1/m365/teams/notify",
        json={
            "title": "Alert",
            "text": "Body",
            "webhook_url": "https://example.com/hook",
        },
        headers=auth(admin_token),
    )

    assert res.status_code == 502
    detail = res.json().get("detail") or ""
    assert detail == "Teams webhook delivery failed"
    assert "teams-hook-token" not in detail
