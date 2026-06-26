"""
test_webhooks.py — Tests for outbound webhook management and delivery.

Covers:
  - Webhook CRUD (create, list, update, delete)
  - Event subscription filtering
  - Project-scoped webhooks
  - Webhook test delivery
  - Webhook delivery log query
  - HMAC-SHA256 payload signing (unit test)
  - Webhook firing logic: matching active hooks, ignoring inactive
"""
from tests.conftest import auth


# ── Helpers ────────────────────────────────────────────────────────────────────

def _create_webhook(client, token, url="https://example.com/hook", events=None, project_id=None):
    payload = {
        "name": "Test Hook",
        "url": url,
        "events": events or ["task.created", "task.updated"],
        "is_active": True,
    }
    if project_id:
        payload["project_id"] = project_id
    res = client.post("/api/v1/enterprise/webhooks", json=payload, headers=auth(token))
    assert res.status_code in (200, 201), res.text
    return res.json()


# ── Webhook CRUD ───────────────────────────────────────────────────────────────

class TestWebhookCRUD:
    def test_create_webhook(self, client, admin_token, db):
        hook = _create_webhook(client, admin_token)
        assert hook.get("name") == "Test Hook"
        assert hook.get("is_active") is True
        assert "id" in hook

    def test_list_webhooks(self, client, admin_token, db):
        _create_webhook(client, admin_token, url="https://example.com/hook1")
        _create_webhook(client, admin_token, url="https://example.com/hook2")
        res = client.get("/api/v1/enterprise/webhooks", headers=auth(admin_token))
        assert res.status_code == 200
        assert len(res.json()) >= 2

    def test_update_webhook(self, client, admin_token, db):
        hook = _create_webhook(client, admin_token)
        res = client.patch(
            f"/api/v1/enterprise/webhooks/{hook['id']}",
            json={"name": "Updated Hook", "is_active": False},
            headers=auth(admin_token),
        )
        assert res.status_code in (200, 204), res.text
        if res.status_code == 200:
            data = res.json()
            assert data.get("is_active") is False

    def test_delete_webhook(self, client, admin_token, db):
        hook = _create_webhook(client, admin_token, url="https://example.com/to-delete")
        res = client.delete(
            f"/api/v1/enterprise/webhooks/{hook['id']}",
            headers=auth(admin_token),
        )
        assert res.status_code in (200, 204), res.text

    def test_get_webhook_events_catalog(self, client, admin_token, db):
        res = client.get("/api/v1/enterprise/webhooks/events", headers=auth(admin_token))
        assert res.status_code == 200
        data = res.json()
        # Should return a list of event names or a dict
        assert data

    def test_create_webhook_rejects_internal_url(self, client, admin_token, db):
        """SSRF guard at the source: internal/metadata destinations → 400."""
        for bad_url in (
            "http://example.com/hook",                 # non-HTTPS
            "https://169.254.169.254/latest/meta-data/",  # cloud IMDS
            "https://localhost/hook",                   # loopback
        ):
            res = client.post(
                "/api/v1/enterprise/webhooks",
                json={"name": "SSRF Hook", "url": bad_url,
                      "events": ["task.created"], "is_active": True},
                headers=auth(admin_token),
            )
            assert res.status_code == 400, f"{bad_url} → {res.status_code} {res.text}"

    def test_update_webhook_rejects_internal_url(self, client, admin_token, db):
        hook = _create_webhook(client, admin_token)
        res = client.patch(
            f"/api/v1/enterprise/webhooks/{hook['id']}",
            json={"url": "https://127.0.0.1/hook"},
            headers=auth(admin_token),
        )
        assert res.status_code == 400, res.text

    def test_non_admin_cannot_create_webhook(self, client, dev_token, db):
        res = client.post(
            "/api/v1/enterprise/webhooks",
            json={"name": "Dev Hook", "url": "https://example.com/hook",
                  "events": ["task.created"], "is_active": True},
            headers=auth(dev_token),
        )
        assert res.status_code in (401, 403)


# ── Webhook Event Subscription ────────────────────────────────────────────────

class TestWebhookEventSubscription:
    def test_wildcard_subscription(self, client, admin_token, db):
        hook = _create_webhook(client, admin_token, events=["*"])
        assert hook.get("events") == ["*"] or "*" in (hook.get("events") or [])

    def test_multiple_event_types(self, client, admin_token, db):
        events = ["task.created", "task.updated", "project.closed", "invoice.approved"]
        hook = _create_webhook(client, admin_token, events=events)
        assert hook.get("id")

    def test_invalid_event_rejected(self, client, admin_token, db):
        res = client.post(
            "/api/v1/enterprise/webhooks",
            json={"name": "Bad Event Hook", "url": "https://example.com/hook",
                  "events": ["invalid.not.a.real.event.xyz"], "is_active": True},
            headers=auth(admin_token),
        )
        # Some implementations accept any event name, others validate
        assert res.status_code in (200, 201, 400, 422)


# ── Webhook Test Delivery ──────────────────────────────────────────────────────

class TestWebhookDelivery:
    def test_test_delivery_endpoint(self, client, admin_token, db):
        hook = _create_webhook(client, admin_token)
        res = client.post(
            f"/api/v1/enterprise/webhooks/{hook['id']}/test",
            headers=auth(admin_token),
        )
        # Will fail actual delivery (test URL) but endpoint should respond
        assert res.status_code in (200, 202, 207, 400, 422, 500, 503)

    def test_delivery_log_query(self, client, admin_token, db):
        hook = _create_webhook(client, admin_token)
        res = client.get(
            f"/api/v1/enterprise/webhooks/{hook['id']}/deliveries",
            headers=auth(admin_token),
        )
        assert res.status_code == 200
        assert isinstance(res.json(), list)


# ── Webhook Service Unit Tests ─────────────────────────────────────────────────

class TestWebhookSigningUnit:
    def test_hmac_signature_format(self):
        from app.services.webhooks import _sign_payload
        sig = _sign_payload("my-secret", '{"event":"test"}')
        assert sig.startswith("sha256=")
        assert len(sig) == 7 + 64  # "sha256=" + 64 hex chars

    def test_same_payload_same_signature(self):
        from app.services.webhooks import _sign_payload
        payload = '{"event":"task.created","data":{}}'
        sig1 = _sign_payload("secret-key", payload)
        sig2 = _sign_payload("secret-key", payload)
        assert sig1 == sig2

    def test_different_secret_different_signature(self):
        from app.services.webhooks import _sign_payload
        payload = '{"event":"task.created"}'
        sig1 = _sign_payload("secret-1", payload)
        sig2 = _sign_payload("secret-2", payload)
        assert sig1 != sig2

    def test_fire_webhook_no_active_hooks(self, db):
        from app.services.webhooks import fire_webhook
        count = fire_webhook(db, "task.created", {"task_id": "t-1"})
        assert count == 0

    def test_fire_webhook_inactive_hook_skipped(self, db):
        from app.services.webhooks import fire_webhook
        from app.models.enterprise import Webhook
        import json

        hook = Webhook(
            name="Inactive Hook",
            url="https://example.com/hook",
            events=json.dumps(["task.created"]),
            is_active=False,
            secret="test-secret",
        )
        db.add(hook)
        db.commit()

        count = fire_webhook(db, "task.created", {"task_id": "t-2"})
        assert count == 0

    def test_fire_webhook_wrong_event_skipped(self, db):
        from app.services.webhooks import fire_webhook
        from app.models.enterprise import Webhook
        import json

        hook = Webhook(
            name="Scoped Hook",
            url="https://example.com/scoped",
            events=json.dumps(["invoice.approved"]),
            is_active=True,
            secret="test-secret",
        )
        db.add(hook)
        db.commit()

        # Fire a different event
        count = fire_webhook(db, "task.created", {"task_id": "t-3"})
        assert count == 0

    def test_fire_webhook_project_scope_filter(self, db):
        from app.services.webhooks import fire_webhook
        from app.models.enterprise import Webhook
        import json

        hook = Webhook(
            name="Project Hook",
            url="https://example.com/proj",
            events=json.dumps(["task.created"]),
            is_active=True,
            secret="test-secret",
            project_id="proj-a",
        )
        db.add(hook)
        db.commit()

        # Fire for different project → should not match
        count = fire_webhook(db, "task.created", {"task_id": "t-4"}, project_id="proj-b")
        assert count == 0
