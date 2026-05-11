import hashlib
import hmac
import json
import time

from app.core.config import settings


def _slack_signature(secret: str, body: bytes, ts: str) -> str:
    base = f"v0:{ts}:{body.decode()}"
    digest = hmac.new(secret.encode(), base.encode(), hashlib.sha256).hexdigest()
    return f"v0={digest}"


def _jwt_with_payload(payload: dict) -> str:
    encoded = json.dumps(payload).encode()
    b64 = __import__("base64").urlsafe_b64encode(encoded).decode().rstrip("=")
    return f"x.{b64}.y"


def test_slack_commands_fail_closed_when_secret_missing(monkeypatch, client, db):
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setattr(settings, "SLACK_SIGNING_SECRET", "", raising=False)

    body = b"text=ayuda&user_name=admin"
    ts = str(int(time.time()))

    res = client.post(
        "/api/v1/integrations-hub/slack/commands",
        data=body.decode(),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Slack-Request-Timestamp": ts,
            "X-Slack-Signature": "v0=invalid",
        },
    )

    assert res.status_code == 503
    assert "not configured" in (res.json().get("detail") or "").lower()


def test_slack_commands_reject_invalid_signature(monkeypatch, client, db):
    monkeypatch.setattr(settings, "SLACK_SIGNING_SECRET", "sec-test", raising=False)

    body = b"text=ayuda&user_name=admin"
    ts = str(int(time.time()))
    bad_sig = _slack_signature("wrong-secret", body, ts)

    res = client.post(
        "/api/v1/integrations-hub/slack/commands",
        data=body.decode(),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Slack-Request-Timestamp": ts,
            "X-Slack-Signature": bad_sig,
        },
    )

    assert res.status_code == 403
    assert "signature" in (res.json().get("detail") or "").lower()


def test_teams_commands_fail_closed_when_app_id_missing(monkeypatch, client, db):
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setattr(settings, "TEAMS_BOT_APP_ID", "", raising=False)

    res = client.post(
        "/api/v1/integrations-hub/teams/commands",
        json={"text": "ayuda", "from": {"name": "admin"}},
    )

    assert res.status_code == 503
    assert "not configured" in (res.json().get("detail") or "").lower()


def test_teams_commands_reject_wrong_audience(monkeypatch, client, db):
    monkeypatch.setattr(settings, "TEAMS_BOT_APP_ID", "expected-app", raising=False)

    token = _jwt_with_payload({"aud": "other-app"})
    res = client.post(
        "/api/v1/integrations-hub/teams/commands",
        json={"text": "ayuda", "from": {"name": "admin"}},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert res.status_code == 403
    assert "audience" in (res.json().get("detail") or "").lower()
