"""
Comprehensive tests for Time Tracking enhancements (Timer, Lockout, Alerts).
"""
import pytest
from sqlalchemy.orm import Session
from datetime import datetime, date

from app.models.imputation import ImputationAlert
from app.models.user import User


@pytest.fixture
def timer_client(client, dev_token):
    """Fixture for API client with dev auth headers."""
    return (client, dev_token)


# ── Timer Tests ────────────────────────────────────────────────────────────

def test_start_timer(db: Session, timer_client):
    """Test starting a timer."""
    client, token = timer_client
    headers = {"Authorization": f"Bearer {token}"}

    # Get a project to timer on
    from app.models.project import Project
    project = db.query(Project).first()
    if not project:
        pytest.skip("No project found")

    # Get a task
    from app.models.task import Task
    task = db.query(Task).filter(Task.project_id == project.id).first()

    payload = {
        "project_id": project.id,
        "task_id": task.id if task else None,
    }

    response = client.post("/api/v1/imputations/timer/start", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] is not None
    assert data["project_id"] == project.id
    assert data["started_at"] is not None


def test_start_timer_duplicate(db: Session, timer_client):
    """Test that only one timer can be active per user."""
    client, token = timer_client
    headers = {"Authorization": f"Bearer {token}"}

    from app.models.project import Project
    project = db.query(Project).first()
    if not project:
        pytest.skip("No project found")

    payload = {"project_id": project.id}

    # Start first timer
    response1 = client.post("/api/v1/imputations/timer/start", json=payload, headers=headers)
    assert response1.status_code == 200

    # Try to start second timer
    response2 = client.post("/api/v1/imputations/timer/start", json=payload, headers=headers)
    assert response2.status_code == 409
    assert "already has an active timer" in response2.json()["detail"]


def test_pause_resume_timer(db: Session, timer_client):
    """Test pausing and resuming a timer."""
    client, token = timer_client
    headers = {"Authorization": f"Bearer {token}"}

    from app.models.project import Project
    project = db.query(Project).first()
    if not project:
        pytest.skip("No project found")

    # Start timer
    payload = {"project_id": project.id}
    client.post("/api/v1/imputations/timer/start", json=payload, headers=headers)

    # Pause
    response = client.post("/api/v1/imputations/timer/pause", headers=headers)
    assert response.status_code == 200
    assert response.json()["paused_at"] is not None

    # Resume
    response = client.post("/api/v1/imputations/timer/resume", headers=headers)
    assert response.status_code == 200
    assert response.json()["paused_at"] is None


def test_stop_timer_creates_imputation(db: Session, timer_client):
    """Test that stopping timer creates an imputation."""
    client, token = timer_client
    headers = {"Authorization": f"Bearer {token}"}

    from app.models.project import Project
    project = db.query(Project).first()
    if not project:
        pytest.skip("No project found")

    # Start timer
    payload = {"project_id": project.id}
    start_response = client.post("/api/v1/imputations/timer/start", json=payload, headers=headers)
    start_time = datetime.fromisoformat(start_response.json()["started_at"].replace("Z", "+00:00"))

    # Wait a bit (simulating work)
    import time
    time.sleep(1)

    # Stop timer
    stop_payload = {"description": "Worked on task", "is_billable": True}
    response = client.post("/api/v1/imputations/timer/stop", json=stop_payload, headers=headers)
    assert response.status_code == 200

    data = response.json()
    assert data["hours"] >= 0.01  # At least a few seconds
    assert data["is_billable"] == True
    assert data["description"] == "Worked on task"


def test_get_current_timer(db: Session, timer_client):
    """Test getting the current active timer."""
    client, token = timer_client
    headers = {"Authorization": f"Bearer {token}"}

    from app.models.project import Project
    project = db.query(Project).first()
    if not project:
        pytest.skip("No project found")

    # No timer yet
    response = client.get("/api/v1/imputations/timer/current", headers=headers)
    assert response.status_code == 200
    assert response.json() is None

    # Start timer
    payload = {"project_id": project.id}
    client.post("/api/v1/imputations/timer/start", json=payload, headers=headers)

    # Get current timer
    response = client.get("/api/v1/imputations/timer/current", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data is not None
    assert data["user_id"] is not None


# ── Lockout Status Tests ───────────────────────────────────────────────────

def test_lockout_status(db: Session, timer_client):
    """Test getting lockout status."""
    client, token = timer_client
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/v1/imputations/lockout-status", headers=headers)
    assert response.status_code == 200

    data = response.json()
    assert data["lockout_days"] > 0
    assert data["current_date"] is not None
    assert data["lockout_cutoff_date"] is not None


# ── Alert Tests ────────────────────────────────────────────────────────────

def test_get_imputation_alerts(db: Session, timer_client):
    """Test getting imputation alerts."""
    client, token = timer_client
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/v1/imputations/alerts", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_dismiss_alert(db: Session, timer_client):
    """Test dismissing an imputation alert."""
    client, token = timer_client
    headers = {"Authorization": f"Bearer {token}"}

    # Create an alert manually for the authenticated user (dev_test)
    user = db.query(User).filter(User.username == "dev_test").first()
    if not user:
        pytest.skip("No active user found")

    alert = ImputationAlert(
        user_id=user.id,
        alert_date=date.today(),
        alert_type="missing_hours",
    )
    db.add(alert)
    db.commit()

    # Dismiss the alert
    response = client.post(f"/api/v1/imputations/alerts/{alert.id}/dismiss", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "dismissed"

    # Verify it's dismissed
    db.refresh(alert)
    assert alert.dismissed_at is not None


def test_imputation_cost_calculation_with_none_rate(db: Session, timer_client):
    """Test that cost is calculated correctly even if hourly_rate is None."""
    client, token = timer_client
    headers = {"Authorization": f"Bearer {token}"}

    from app.models.project import Project

    # Get current user
    user = db.query(User).filter(User.is_active == True).first()
    if not user:
        pytest.skip("No active user found")

    # Temporarily set hourly_rate to None
    original_rate = user.hourly_rate
    user.hourly_rate = None
    db.commit()

    try:
        project = db.query(Project).first()
        if not project:
            pytest.skip("No project found")

        # Start timer
        payload = {"project_id": project.id}
        client.post("/api/v1/imputations/timer/start", json=payload, headers=headers)

        # Stop timer - should handle None hourly_rate gracefully
        import time
        time.sleep(1)
        stop_payload = {"description": "Test with no rate", "is_billable": False}
        response = client.post("/api/v1/imputations/timer/stop", json=stop_payload, headers=headers)

        # Should succeed and cost should be 0
        assert response.status_code == 200
        data = response.json()
        assert data["cost_amount"] == 0.0  # Cost should be 0, not None

    finally:
        # Restore original rate
        user.hourly_rate = original_rate
        db.commit()


def test_weekly_capacity_validation(db: Session, timer_client):
    """Test that weekly capacity validation prevents excessive hours."""
    client, token = timer_client
    headers = {"Authorization": f"Bearer {token}"}

    from app.models.project import Project

    user = db.query(User).filter(User.is_active == True).first()
    if not user:
        pytest.skip("No active user found")

    # Ensure user has hourly_rate
    if not user.hourly_rate:
        user.hourly_rate = 50.0
        db.commit()

    project = db.query(Project).first()
    if not project:
        pytest.skip("No project found")

    # Try to impute 70 hours (exceeds default 40h capacity * 1.5 = 60h)
    today = date.today()
    payload = {
        "project_id": project.id,
        "date": today.isoformat(),
        "hours": 70.0,
        "description": "Over capacity",
        "is_billable": True,
    }

    response = client.post("/api/v1/imputations", json=payload, headers=headers)

    # Should be rejected due to weekly capacity validation
    assert response.status_code == 400
    assert "Excederías la capacidad semanal" in response.json()["detail"]


def test_timer_with_multiple_pauses(db: Session, timer_client):
    """Test that timer correctly accumulates pause durations."""
    client, token = timer_client
    headers = {"Authorization": f"Bearer {token}"}

    from app.models.project import Project
    project = db.query(Project).first()
    if not project:
        pytest.skip("No project found")

    # Start timer
    payload = {"project_id": project.id}
    start_response = client.post("/api/v1/imputations/timer/start", json=payload, headers=headers)
    assert start_response.status_code == 200

    # Pause, resume, pause, resume pattern
    import time

    # First pause
    pause_response = client.post("/api/v1/imputations/timer/pause", headers=headers)
    assert pause_response.status_code == 200
    time.sleep(0.5)

    # Resume
    resume_response = client.post("/api/v1/imputations/timer/resume", headers=headers)
    assert resume_response.status_code == 200
    time.sleep(0.5)

    # Second pause
    pause_response = client.post("/api/v1/imputations/timer/pause", headers=headers)
    assert pause_response.status_code == 200
    time.sleep(0.5)

    # Resume again
    resume_response = client.post("/api/v1/imputations/timer/resume", headers=headers)
    assert resume_response.status_code == 200
    time.sleep(0.5)

    # Stop timer
    stop_payload = {"description": "Test multiple pauses", "is_billable": True}
    stop_response = client.post("/api/v1/imputations/timer/stop", json=stop_payload, headers=headers)
    assert stop_response.status_code == 200

    # Hours should be calculated correctly (pause times subtracted from elapsed)
    data = stop_response.json()
    assert data["hours"] > 0
    assert data["hours"] < 1  # Should be less than 1 hour for this test


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
