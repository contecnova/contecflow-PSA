from tests.conftest import auth


def test_run_job_async_returns_queued(client, admin_token, monkeypatch):
    def _fake_run(_db, *, limit=100):
        return {"processed": 0, "auto_resolved": 0, "suggested": 0, "failed": 0, "limit": limit}

    monkeypatch.setattr(
        "app.api.v1.endpoints.service_desk.ai_auto_resolution.run_daily_auto_resolution_job",
        _fake_run,
    )

    r = client.post(
        "/api/v1/sd/auto-resolution/run-job?run_async=true&limit=9",
        headers=auth(admin_token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "queued"
    assert body["limit"] == 9
    assert "job_id" in body


def test_run_job_sync_uses_limit(client, admin_token, monkeypatch):
    seen = {"limit": None}

    def _fake_run(_db, *, limit=100):
        seen["limit"] = limit
        return {"processed": 3, "auto_resolved": 1, "suggested": 1, "failed": 0}

    monkeypatch.setattr(
        "app.api.v1.endpoints.service_desk.ai_auto_resolution.run_daily_auto_resolution_job",
        _fake_run,
    )

    r = client.post(
        "/api/v1/sd/auto-resolution/run-job?run_async=false&limit=7",
        headers=auth(admin_token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "completed"
    assert body["processed"] == 3
    assert seen["limit"] == 7


def test_auto_resolution_config_get_returns_defaults(client, admin_token):
    r = client.get("/api/v1/sd/auto-resolution/config", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert "threshold_auto" in body
    assert "threshold_suggest" in body
    assert "default_job_limit" in body


def test_auto_resolution_config_patch_persists_and_normalizes(client, admin_token):
    r = client.patch(
        "/api/v1/sd/auto-resolution/config",
        headers=auth(admin_token),
        json={
            "threshold_auto": 0.82,
            "threshold_suggest": 0.90,
            "auto_close_hours_after_resolution": 60,
            "validation_window_hours": 36,
            "default_job_limit": 30,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["threshold_auto"] == 0.82
    # Suggest threshold is clamped to not exceed threshold_auto.
    assert body["threshold_suggest"] == 0.82
    assert body["auto_close_hours_after_resolution"] == 60
    assert body["validation_window_hours"] == 36
    assert body["default_job_limit"] == 30

    r2 = client.get("/api/v1/sd/auto-resolution/config", headers=auth(admin_token))
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2["threshold_auto"] == 0.82
    assert body2["default_job_limit"] == 30


def test_auto_resolution_stats_includes_runtime_health(client, admin_token):
    r = client.get("/api/v1/sd/auto-resolution/stats", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert "runtime" in body
    assert "running" in body["runtime"]
    assert "status" in body["runtime"]


def test_stats_includes_job_history_after_sync_run(client, admin_token, monkeypatch):
    def _fake_run(_db, *, limit=100):
        return {"processed": 5, "auto_resolved": 2, "suggested": 1, "failed": 0}

    monkeypatch.setattr(
        "app.api.v1.endpoints.service_desk.ai_auto_resolution.run_daily_auto_resolution_job",
        _fake_run,
    )

    # Run a sync job to generate history
    r = client.post(
        "/api/v1/sd/auto-resolution/run-job?run_async=false&limit=5",
        headers=auth(admin_token),
    )
    assert r.status_code == 200, r.text

    # Verify stats includes job_history with at least one entry
    r2 = client.get("/api/v1/sd/auto-resolution/stats", headers=auth(admin_token))
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert "job_history" in body
    assert isinstance(body["job_history"], list)
    assert len(body["job_history"]) >= 1
    latest = body["job_history"][0]
    assert latest["status"] == "completed"
    assert latest["stats"]["processed"] == 5
    assert latest["duration_ms"] is not None
