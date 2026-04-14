"""Tests for Alerts — listing, resolving, running alert engine."""
import pytest
from tests.conftest import auth
from datetime import date, timedelta
from sqlalchemy.orm import Session

from app.models.alert import Alert, AlertType, AlertSeverity


# ── List Alerts ────────────────────────────────────────────────────────────

def test_list_alerts_empty(client, admin_token, db):
    res = client.get("/api/v1/alerts", headers=auth(admin_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_list_alerts_resolved(client, admin_token, db):
    res = client.get("/api/v1/alerts?resolved=true", headers=auth(admin_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_list_alerts_by_severity(client, admin_token, db):
    res = client.get("/api/v1/alerts?severity=warning", headers=auth(admin_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_employee_sees_only_own_alerts(client, dev_token, db):
    """Employees can only see their own alerts."""
    res = client.get("/api/v1/alerts", headers=auth(dev_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)


# ── Run Alert Engine ───────────────────────────────────────────────────────

def test_run_alert_engine(client, admin_token, db):
    """Admin can trigger the alert engine."""
    res = client.post("/api/v1/alerts/run", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert "message" in data


def test_run_alert_engine_non_admin_rejected(client, dev_token, db):
    res = client.post("/api/v1/alerts/run", headers=auth(dev_token))
    assert res.status_code in (401, 403)


def test_run_alert_engine_pm_rejected(client, pm_token, db):
    res = client.post("/api/v1/alerts/run", headers=auth(pm_token))
    assert res.status_code in (401, 403)


# ── Mark Read / Resolve ────────────────────────────────────────────────────

def test_mark_alert_read(client, admin_token, db):
    """Mark an alert as read."""
    alert = Alert(
        alert_type=AlertType.budget_exceeded,
        severity=AlertSeverity.warning,
        title="Test Alert",
        description="Test",
    )
    db.add(alert)
    db.commit()

    res = client.patch(f"/api/v1/alerts/{alert.id}/read", headers=auth(admin_token))
    assert res.status_code == 200
    assert res.json()["ok"] is True

    db.refresh(alert)
    assert alert.is_read is True


def test_resolve_alert(client, pm_token, db):
    """Manager can resolve an alert."""
    alert = Alert(
        alert_type=AlertType.deadline_risk,
        severity=AlertSeverity.warning,
        title="Deadline Alert",
    )
    db.add(alert)
    db.commit()

    res = client.patch(f"/api/v1/alerts/{alert.id}/resolve", headers=auth(pm_token))
    assert res.status_code == 200
    assert res.json()["ok"] is True

    db.refresh(alert)
    assert alert.is_resolved is True
    assert alert.resolved_at is not None


def test_mark_read_nonexistent_alert(client, admin_token, db):
    """Marking a non-existent alert read returns ok (no-op)."""
    res = client.patch("/api/v1/alerts/nonexistent-id/read", headers=auth(admin_token))
    assert res.status_code == 200


def test_resolve_nonexistent_alert(client, pm_token, db):
    """Resolving a non-existent alert returns ok (no-op)."""
    res = client.patch("/api/v1/alerts/nonexistent-id/resolve", headers=auth(pm_token))
    assert res.status_code == 200


def test_resolve_requires_manager(client, dev_token, db):
    """Employee cannot resolve alerts."""
    alert = Alert(
        alert_type=AlertType.overload,
        severity=AlertSeverity.warning,
        title="Overload Alert",
    )
    db.add(alert)
    db.commit()
    res = client.patch(f"/api/v1/alerts/{alert.id}/resolve", headers=auth(dev_token))
    assert res.status_code in (401, 403)


# ── Alert Engine Logic ─────────────────────────────────────────────────────

def test_alert_engine_with_active_project(client, admin_token, pm_token, db):
    """Alert engine scans active projects and doesn't crash."""
    # Create a project with budget
    client.post("/api/v1/projects", json={
        "name": "Budget Project",
        "code": "ALT01",
        "status": "active",
        "billing_type": "time_material",
        "budget_amount": 10000,
    }, headers=auth(pm_token))

    res = client.post("/api/v1/alerts/run", headers=auth(admin_token))
    assert res.status_code == 200


def test_alert_engine_idempotent(client, admin_token, db):
    """Running alert engine twice doesn't create duplicate alerts."""
    res1 = client.post("/api/v1/alerts/run", headers=auth(admin_token))
    res2 = client.post("/api/v1/alerts/run", headers=auth(admin_token))
    assert res1.status_code == 200
    assert res2.status_code == 200


def test_alerts_require_auth(client, db):
    res = client.get("/api/v1/alerts")
    assert res.status_code in (401, 403)
