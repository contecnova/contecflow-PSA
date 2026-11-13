from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest


def test_ready_endpoint_exposes_orchestration_checks(client, db):
    res = client.get("/ready")
    assert res.status_code in (200, 503)
    payload = res.json()
    assert payload["status"] in {"ok", "error"}
    assert "checks" in payload
    assert payload["checks"]["db"]["status"] in {"ok", "error"}
    assert "scheduler" in payload["checks"]
    assert payload["checks"]["scheduler"]["mode"] in {
        "apscheduler",
        "celery_beat",
        "none",
        "dual",
    }


def test_enforce_scheduler_mode_safety_raises_on_dual_in_production(monkeypatch):
    from app import main as main_mod

    monkeypatch.setattr(main_mod.settings, "ENVIRONMENT", "production", raising=False)
    monkeypatch.setattr(main_mod.settings, "ENABLE_APSCHEDULER", True)
    monkeypatch.setattr(main_mod.settings, "ENABLE_CELERY_BEAT", True)
    monkeypatch.setattr(main_mod.settings, "FAIL_ON_DUAL_SCHEDULER", True)

    with pytest.raises(RuntimeError):
        main_mod._enforce_scheduler_mode_safety()


def test_deliver_webhook_task_retries_on_transient_network_error(db, monkeypatch):
    from app.models.enterprise import WebhookDelivery
    from app.worker import deliver_webhook_task
    from unittest.mock import MagicMock

    hook = SimpleNamespace(
        id="hook-transient",
        name="Transient Hook",
        url="https://example.com/hook",
        is_active=True,
        secret=None,
        total_deliveries=0,
        failed_deliveries=0,
        consecutive_failures=0,
        last_triggered_at=None,
    )

    fake_db = MagicMock()
    fake_db.query.return_value.filter.return_value.first.return_value = hook
    added_rows = []
    fake_db.add.side_effect = lambda row: added_rows.append(row)

    retry_called = {}

    def _fake_retry(*args, **kwargs):
        retry_called["countdown"] = kwargs.get("countdown")
        raise RuntimeError("retry-called")

    monkeypatch.setattr(deliver_webhook_task, "retry", _fake_retry)

    class _FailingClient:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, *args, **kwargs):
            raise httpx.ConnectError("network down")

    with patch("app.db.session.SessionLocal", return_value=fake_db):
        with patch("httpx.Client", return_value=_FailingClient()):
            with pytest.raises(RuntimeError, match="retry-called"):
                deliver_webhook_task.run("hook-transient", '{"event":"task.created"}', "task.created")

    assert retry_called.get("countdown") == 60
    assert hook.is_active is True
    assert any(isinstance(row, WebhookDelivery) for row in added_rows)


def test_deliver_webhook_task_suspends_on_threshold_without_retry(db, monkeypatch):
    from app.models.enterprise import WebhookDelivery
    from app.worker import deliver_webhook_task
    from unittest.mock import MagicMock

    hook = SimpleNamespace(
        id="hook-cb",
        name="CB Hook",
        url="https://example.com/fails",
        is_active=True,
        secret=None,
        total_deliveries=0,
        failed_deliveries=0,
        consecutive_failures=0,
        suspended_at=None,
        last_triggered_at=None,
    )

    # Segunda auditoria 2026-11 (#37): la entrega vive en `entrega_de_webhooks`.
    monkeypatch.setattr("app.services.entrega_de_webhooks.settings", SimpleNamespace(WEBHOOK_CB_THRESHOLD=1))

    fake_db = MagicMock()
    fake_db.query.return_value.filter.return_value.first.return_value = hook
    added_rows = []
    fake_db.add.side_effect = lambda row: added_rows.append(row)

    class _Resp:
        status_code = 500
        text = "server error"

    class _Client500:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, *args, **kwargs):
            return _Resp()

    with patch("app.db.session.SessionLocal", return_value=fake_db):
        with patch("httpx.Client", return_value=_Client500()):
            result = deliver_webhook_task.run("hook-cb", '{"event":"task.created"}', "task.created")

    deliveries = [row for row in added_rows if isinstance(row, WebhookDelivery)]
    assert deliveries
    latest_delivery = deliveries[-1]

    assert result["success"] is False
    assert result["suspended"] is True
    assert hook.is_active is False
    assert hook.consecutive_failures >= 1
    assert latest_delivery is not None
    assert latest_delivery.status_code == 500
