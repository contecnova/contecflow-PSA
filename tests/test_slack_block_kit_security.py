import httpx

from tests.conftest import auth


def test_slack_block_kit_error_is_sanitized(monkeypatch, client, admin_token, db):
    import app.api.v1.endpoints.slack_block_kit as slack_ep

    req = httpx.Request("POST", "https://hooks.slack.com/services/test")
    resp = httpx.Response(400, text='{"error":"sensitive-slack-detail"}', request=req)

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, *args, **kwargs):
            raise httpx.HTTPStatusError("bad", request=req, response=resp)

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: _Client())

    payload = {
        "event_type": "task_overdue",
        "data": {
            "task_title": "Task",
            "project_name": "Proj",
            "due_date": "2026-05-10",
            "assignee": "Alice",
            "task_id": "t1",
        },
        "webhook_url": "https://hooks.slack.com/services/test",
    }
    res = client.post("/api/v1/notifications/slack/block-kit", json=payload, headers=auth(admin_token))

    assert res.status_code == 502
    detail = res.json().get("detail") or ""
    assert detail == "Slack delivery failed"
    assert "sensitive-slack-detail" not in detail
