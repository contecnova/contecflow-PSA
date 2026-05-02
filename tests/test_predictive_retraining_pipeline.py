from datetime import datetime, timedelta, timezone

from app.models.service_desk import Ticket, TicketPriority, TicketStatus, TicketType
from app.models.settings import AppSetting
from app.services import predictive_retraining_service as retraining_service
from app.services.service_desk.predictive_analytics_service import (
    PREDICTIVE_BASELINES_KEY,
    recompute_predictive_baselines,
)


def _mk_ticket(idx: int, *, predicted: int, actual: int, priority: TicketPriority = TicketPriority.p2_high) -> Ticket:
    now = datetime.now(tz=timezone.utc)
    return Ticket(
        id=f"t-{idx}",
        number=f"TCK-{idx:05d}",
        ticket_type=TicketType.incident,
        title=f"Ticket {idx}",
        description="predictive test",
        status=TicketStatus.resolved,
        priority=priority,
        requester_user_id="admin-test-id",
        created_by_user_id="admin-test-id",
        predicted_severity="high",
        predicted_resolution_minutes=predicted,
        prediction_generated_at=now,
        resolution_minutes=actual,
        resolved_at=now,
    )


def test_recompute_predictive_baselines_persists_in_app_settings(db):
    db.add_all(
        [
            _mk_ticket(1, predicted=60, actual=45, priority=TicketPriority.p2_high),
            _mk_ticket(2, predicted=40, actual=50, priority=TicketPriority.p2_high),
            _mk_ticket(3, predicted=200, actual=220, priority=TicketPriority.p3_medium),
        ]
    )
    db.commit()

    payload = recompute_predictive_baselines(db, organization_id="1")

    assert payload["samples"] >= 3
    assert isinstance(payload.get("by_bucket"), dict)

    row = (
        db.query(AppSetting)
        .filter(AppSetting.key == PREDICTIVE_BASELINES_KEY, AppSetting.organization_id == "1")
        .first()
    )
    assert row is not None
    assert row.value


def test_periodic_pipeline_triggers_retraining_when_models_are_stale(db, monkeypatch):
    counters = {"itsm": 0, "bi_anomaly": 0, "bi_overrun": 0}

    def _itsm_eval(_db, *, organization_id, lookback_days=30):
        _ = lookback_days
        return {
            "organization_id": organization_id,
            "status": "attention",
            "score": 0.42,
        }

    def _bi_eval(_db, *, organization_id):
        return {
            "organization_id": organization_id,
            "status": "attention",
            "score": 0.39,
            "forecast_engine": "linear_regression_fallback",
            "overrun_engine": "heuristic_fallback",
        }

    def _recompute(_db, *, organization_id):
        counters["itsm"] += 1
        return {"samples": 12, "organization_id": organization_id}

    def _anomaly(_db, *, organization_id, contamination=0.1):
        _ = contamination
        counters["bi_anomaly"] += 1
        return {"organization_id": organization_id}

    def _overrun(_db, *, organization_id):
        counters["bi_overrun"] += 1
        return {"organization_id": organization_id}

    monkeypatch.setattr(retraining_service, "evaluate_itsm_model_health", _itsm_eval)
    monkeypatch.setattr(retraining_service, "evaluate_bi_model_health", _bi_eval)
    monkeypatch.setattr(retraining_service.predictive_analytics_service, "recompute_predictive_baselines", _recompute)
    monkeypatch.setattr(retraining_service.bi_intelligence_service, "ml_detect_anomalies_multivariate", _anomaly)
    monkeypatch.setattr(retraining_service.bi_intelligence_service, "ml_predict_project_overrun_lgbm", _overrun)

    stale_at = (datetime.now(tz=timezone.utc) - timedelta(days=30)).isoformat()
    db.add(
        AppSetting(
            key=retraining_service.ITSM_META_KEY,
            organization_id="1",
            value=f'{{"last_retrained_at":"{stale_at}"}}',
        )
    )
    db.add(
        AppSetting(
            key=retraining_service.BI_META_KEY,
            organization_id="1",
            value=f'{{"last_retrained_at":"{stale_at}"}}',
        )
    )
    db.commit()

    result = retraining_service.run_periodic_evaluation_and_retraining(db)

    assert result["organizations"] >= 1
    assert result["itsm_retrained"] >= 1
    assert result["bi_retrained"] >= 1
    assert counters["itsm"] >= 1
    assert counters["bi_anomaly"] >= 1
    assert counters["bi_overrun"] >= 1


def test_periodic_pipeline_skips_retraining_when_models_healthy_and_fresh(db, monkeypatch):
    def _itsm_eval(_db, *, organization_id, lookback_days=30):
        _ = lookback_days
        return {
            "organization_id": organization_id,
            "status": "healthy",
            "score": 0.91,
        }

    def _bi_eval(_db, *, organization_id):
        return {
            "organization_id": organization_id,
            "status": "healthy",
            "score": 0.87,
            "forecast_engine": "prophet",
            "overrun_engine": "lightgbm",
        }

    monkeypatch.setattr(retraining_service, "evaluate_itsm_model_health", _itsm_eval)
    monkeypatch.setattr(retraining_service, "evaluate_bi_model_health", _bi_eval)

    recent_at = (datetime.now(tz=timezone.utc) - timedelta(days=1)).isoformat()
    db.add(
        AppSetting(
            key=retraining_service.ITSM_META_KEY,
            organization_id="1",
            value=f'{{"last_retrained_at":"{recent_at}"}}',
        )
    )
    db.add(
        AppSetting(
            key=retraining_service.BI_META_KEY,
            organization_id="1",
            value=f'{{"last_retrained_at":"{recent_at}"}}',
        )
    )
    db.commit()

    result = retraining_service.run_periodic_evaluation_and_retraining(db)

    assert result["itsm_retrained"] == 0
    assert result["bi_retrained"] == 0


def test_bi_health_reports_insufficient_data_when_history_is_too_short(db, monkeypatch):
    def _forecast(_db, *, organization_id, metric_key="revenue", periods=2, frequency="MS"):
        _ = (organization_id, metric_key, periods, frequency)
        return {
            "engine": "prophet",
            "history_months": 3,
            "forecast": [],
        }

    def _overrun(_db, *, organization_id):
        _ = organization_id
        return {"engine": "lightgbm", "predictions": []}

    monkeypatch.setattr(retraining_service.bi_intelligence_service, "ml_forecast_prophet", _forecast)
    monkeypatch.setattr(retraining_service.bi_intelligence_service, "ml_predict_project_overrun_lgbm", _overrun)

    result = retraining_service.evaluate_bi_model_health(db, organization_id="1")

    assert result["history_months"] == 3
    assert result["status"] == "insufficient_data"
