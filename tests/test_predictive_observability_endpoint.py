from tests.conftest import auth

from app.models.settings import AppSetting
from app.services.predictive_retraining_service import (
    ITSM_META_KEY,
    BI_META_KEY,
    LAST_EVAL_KEY,
)


def test_status_endpoint_returns_structure(client, admin_token, db):
    res = client.get(
        "/api/v1/bi/predictive/observability/status",
        headers=auth(admin_token),
    )
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert "last_eval" in data
    assert "itsm_meta" in data
    assert "bi_meta" in data
    assert "organization_id" in data


def test_status_endpoint_returns_persisted_meta(client, admin_token, db):
    db.add(AppSetting(
        key=ITSM_META_KEY,
        organization_id="1",
        value='{"last_retrained_at":"2026-04-01T00:00:00+00:00","reason":"attention_or_stale"}',
        description="test",
    ))
    db.add(AppSetting(
        key=BI_META_KEY,
        organization_id="1",
        value='{"last_retrained_at":"2026-04-02T00:00:00+00:00","forecast_engine":"prophet"}',
        description="test",
    ))
    db.commit()

    res = client.get(
        "/api/v1/bi/predictive/observability/status",
        headers=auth(admin_token),
    )
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["itsm_meta"].get("reason") == "attention_or_stale"
    assert data["bi_meta"].get("forecast_engine") == "prophet"


def test_health_endpoint_returns_scores(client, admin_token, db):
    res = client.get(
        "/api/v1/bi/predictive/observability/health",
        headers=auth(admin_token),
    )
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert "overall_score" in data
    assert "overall_status" in data
    assert "itsm" in data
    assert "bi" in data
    assert 0.0 <= data["overall_score"] <= 1.0
    assert data["overall_status"] in ("healthy", "attention", "insufficient_data")


def test_health_endpoint_respects_lookback_days(client, admin_token, db):
    res = client.get(
        "/api/v1/bi/predictive/observability/health?lookback_days=7",
        headers=auth(admin_token),
    )
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["itsm"]["lookback_days"] == 7


def test_health_endpoint_prioritizes_insufficient_data_status(client, admin_token, db, monkeypatch):
    import app.api.v1.endpoints.predictive_observability as ep_module

    def _itsm_eval(_db, *, organization_id, lookback_days=30):
        _ = lookback_days
        return {
            "organization_id": organization_id,
            "status": "attention",
            "score": 0.6,
        }

    def _bi_eval(_db, *, organization_id):
        return {
            "organization_id": organization_id,
            "status": "insufficient_data",
            "score": 0.9,
        }

    monkeypatch.setattr(ep_module, "evaluate_itsm_model_health", _itsm_eval)
    monkeypatch.setattr(ep_module, "evaluate_bi_model_health", _bi_eval)

    res = client.get(
        "/api/v1/bi/predictive/observability/health",
        headers=auth(admin_token),
    )
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["overall_status"] == "insufficient_data"


def test_trigger_retrain_endpoint_executes_cycle(client, admin_token, db, monkeypatch):
    import app.api.v1.endpoints.predictive_observability as ep_module

    calls = {"n": 0}

    def _fake_run(db_):
        calls["n"] += 1
        return {
            "evaluated_at": "2026-04-29T00:00:00+00:00",
            "organizations": 1,
            "itsm_retrained": 1,
            "bi_retrained": 0,
            "results": [],
        }

    monkeypatch.setattr(ep_module, "run_periodic_evaluation_and_retraining", _fake_run)

    res = client.post(
        "/api/v1/bi/predictive/observability/trigger-retrain",
        headers=auth(admin_token),
    )
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["organizations"] == 1
    assert data["itsm_retrained"] == 1
    assert calls["n"] == 1


def test_non_admin_is_rejected(client, pm_token, db):
    for method, path in [
        ("get", "/api/v1/bi/predictive/observability/status"),
        ("get", "/api/v1/bi/predictive/observability/health"),
        ("post", "/api/v1/bi/predictive/observability/trigger-retrain"),
    ]:
        fn = getattr(client, method)
        res = fn(path, headers=auth(pm_token))
        assert res.status_code == 403, f"{method.upper()} {path} should return 403, got {res.status_code}: {res.text}"
