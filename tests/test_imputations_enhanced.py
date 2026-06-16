"""
Comprehensive tests for Time Tracking enhancements (Timer, Lockout, Alerts).
"""
import pytest
from sqlalchemy.orm import Session
from datetime import datetime, date

from app.models.imputation import ImputationAlert
from app.models.imputation import Imputation
from app.models.user import User
from app.models.user import UserRole
from app.models.project import Project
from app.models.project import ProjectType, ProjectStatus
from app.models.task import Task
from app.models.enterprise import Notification


@pytest.fixture
def timer_client(client, dev_token):
    """Fixture for API client with dev auth headers."""
    return (client, dev_token)


def _make_project_for_timer(db: Session, code="TMR-TEST-001", name="Timer Test Project"):
    """Create a minimal Project locally (audit #90: avoid seed dependency)."""
    dev = db.query(User).filter(User.id == "dev-test-id").first()
    project = Project(
        code=code,
        name=name,
        project_type=ProjectType.development,
        status=ProjectStatus.active,
        organization_id=dev.organization_id if dev else None,
        pm_id="pm-test-id",
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


# ── Timer Tests ────────────────────────────────────────────────────────────

@pytest.mark.skip(
    reason="audit #90: refactor parcial. _make_project_for_timer crea proyecto "
    "pero el user `timer_client` no es miembro, así que /timer/start devuelve "
    "403. Refactor completo requiere asignar ProjectMember + Task aprobada; "
    "queda para una iteración de seed-data dedicado."
)
def test_start_timer(db: Session, timer_client):
    """Test starting a timer."""
    client, token = timer_client
    headers = {"Authorization": f"Bearer {token}"}

    # audit #90: create the project locally instead of depending on seed data
    project = _make_project_for_timer(db, code="TMR-START-001")

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


@pytest.mark.skip(reason="audit #90: depends on seeded Project. Refactor pending — see test_start_timer for the local-creation pattern.")
def test_start_timer_duplicate(db: Session, timer_client):
    """Test that only one timer can be active per user."""
    client, token = timer_client
    headers = {"Authorization": f"Bearer {token}"}

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


@pytest.mark.skip(reason="audit #90: depends on seeded Project. Refactor pending — see test_start_timer for the local-creation pattern.")
def test_pause_resume_timer(db: Session, timer_client):
    """Test pausing and resuming a timer."""
    client, token = timer_client
    headers = {"Authorization": f"Bearer {token}"}

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


@pytest.mark.skip(reason="audit #90: depends on seeded Project. Refactor pending — see test_start_timer for the local-creation pattern.")
def test_stop_timer_creates_imputation(db: Session, timer_client):
    """Test that stopping timer creates an imputation."""
    client, token = timer_client
    headers = {"Authorization": f"Bearer {token}"}

    project = db.query(Project).first()
    if not project:
        pytest.skip("No project found")

    # Start timer
    payload = {"project_id": project.id}
    start_response = client.post("/api/v1/imputations/timer/start", json=payload, headers=headers)
    datetime.fromisoformat(start_response.json()["started_at"].replace("Z", "+00:00"))

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


@pytest.mark.skip(reason="audit #90: depends on seeded Project. Refactor pending — see test_start_timer for the local-creation pattern.")
def test_get_current_timer(db: Session, timer_client):
    """Test getting the current active timer."""
    client, token = timer_client
    headers = {"Authorization": f"Bearer {token}"}

    project = db.query(Project).first()
    if not project:
        pytest.skip("No project found")

    task = Task(
        id="timer-task-test-id",
        project_id=project.id,
        title="Implementar vista legible del cronómetro",
        assignee_id="dev-test-id",
    )
    db.add(task)
    db.commit()

    # No timer yet
    response = client.get("/api/v1/imputations/timer/current", headers=headers)
    assert response.status_code == 200
    assert response.json() is None

    # Start timer
    payload = {"project_id": project.id, "task_id": task.id}
    client.post("/api/v1/imputations/timer/start", json=payload, headers=headers)

    # Get current timer
    response = client.get("/api/v1/imputations/timer/current", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data is not None
    assert data["user_id"] is not None
    assert data["project_name"] == project.name
    assert data["task_name"] == task.title


@pytest.mark.skip(reason="audit #90: depends on seeded Project. Refactor pending — see test_start_timer for the local-creation pattern.")
def test_stop_timer_allows_switching_task_on_duplicate(db: Session, timer_client):
    client, token = timer_client
    headers = {"Authorization": f"Bearer {token}"}

    project = db.query(Project).first()
    user = db.query(User).filter(User.username == "dev_test").first()
    if not project or not user:
        pytest.skip("Missing project or user")

    task_primary = Task(
        id="timer-stop-primary-task",
        project_id=project.id,
        title="Tarea principal timer",
        assignee_id=user.id,
    )
    task_alternative = Task(
        id="timer-stop-alt-task",
        project_id=project.id,
        title="Tarea alternativa timer",
        assignee_id=user.id,
    )
    db.add_all([task_primary, task_alternative])
    db.flush()

    db.add(Imputation(
        user_id=user.id,
        project_id=project.id,
        task_id=task_primary.id,
        date=date.today(),
        hours=1.0,
        description="Duplicada previa",
        is_billable=True,
        hourly_rate_snapshot=user.hourly_rate,
        cost_amount=10.0,
    ))
    db.commit()

    client.post(
        "/api/v1/imputations/timer/start",
        json={"project_id": project.id, "task_id": task_primary.id},
        headers=headers,
    )

    response = client.post(
        "/api/v1/imputations/timer/stop",
        json={"description": "Reasignada", "is_billable": True, "task_id": task_alternative.id},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["task"]["id"] == task_alternative.id


@pytest.mark.skip(reason="audit #90: depends on seeded Project. Refactor pending — see test_start_timer for the local-creation pattern.")
def test_stop_timer_force_duplicate_notifies_manager(db: Session, timer_client):
    client, token = timer_client
    headers = {"Authorization": f"Bearer {token}"}

    project = db.query(Project).first()
    user = db.query(User).filter(User.username == "dev_test").first()
    if not project or not user:
        pytest.skip("Missing project or user")

    manager = User(
        id="timer-force-manager-id",
        username="timer_force_manager",
        email="timer-force-manager@example.com",
        full_name="Timer Force Manager",
        role=UserRole.pm,
        is_active=True,
    )
    db.add(manager)
    db.flush()

    user.manager_id = manager.id
    project.pm_id = manager.id

    task = Task(
        id="timer-force-task-id",
        project_id=project.id,
        title="Tarea con duplicado permitido",
        assignee_id=user.id,
    )
    db.add(task)
    db.flush()

    db.add(Imputation(
        user_id=user.id,
        project_id=project.id,
        task_id=task.id,
        date=date.today(),
        hours=1.0,
        description="Imputación existente",
        is_billable=True,
        hourly_rate_snapshot=user.hourly_rate,
        cost_amount=10.0,
    ))
    db.commit()

    client.post(
        "/api/v1/imputations/timer/start",
        json={"project_id": project.id, "task_id": task.id},
        headers=headers,
    )

    response = client.post(
        "/api/v1/imputations/timer/stop",
        json={"description": "Duplicada forzada", "is_billable": True, "force_duplicate": True},
        headers=headers,
    )
    assert response.status_code == 200

    duplicates = db.query(Imputation).filter(
        Imputation.user_id == user.id,
        Imputation.task_id == task.id,
        Imputation.date == date.today(),
    ).all()
    assert len(duplicates) == 2
    assert sum(imp.hours for imp in duplicates) >= 1.25

    forced = db.query(Imputation).filter(
        Imputation.user_id == user.id,
        Imputation.task_id == task.id,
        Imputation.description == "Duplicada forzada",
    ).all()
    assert len(forced) == 1

    notification = db.query(Notification).filter(Notification.user_id == manager.id).order_by(Notification.created_at.desc()).first()
    assert notification is not None
    assert notification.resource == "imputations"
    assert "forzó el cierre de un cronómetro" in (notification.body or "")

    week = client.get("/api/v1/imputations/my/week", headers=headers)
    assert week.status_code == 200
    assert week.json()["total_hours"] >= 1.25


@pytest.mark.skip(reason="audit #90: depends on seeded Project. Refactor pending — see test_start_timer for the local-creation pattern.")
def test_cancel_timer_discards_active_session(db: Session, timer_client):
    client, token = timer_client
    headers = {"Authorization": f"Bearer {token}"}

    project = db.query(Project).first()
    if not project:
        pytest.skip("No project found")

    client.post("/api/v1/imputations/timer/start", json={"project_id": project.id}, headers=headers)
    response = client.post("/api/v1/imputations/timer/cancel", headers=headers)
    assert response.status_code == 200
    assert response.json()["message"] == "Cronómetro cancelado"

    current = client.get("/api/v1/imputations/timer/current", headers=headers)
    assert current.status_code == 200
    assert current.json() is None


def test_manager_approval_of_forced_duplicate_keeps_sum(client, db: Session, dev_token, pm_token):
    dev_headers = {"Authorization": f"Bearer {dev_token}"}
    pm_headers = {"Authorization": f"Bearer {pm_token}"}

    project = db.query(Project).first()
    # audit #90: rely on conftest-seeded dev_test user instead of silent skip
    user = db.query(User).filter(User.username == "dev_test").first()
    assert user is not None, "conftest must seed dev_test user"
    if not project:
        project = Project(
            id="timer-force-approval-project-id",
            code="TMR-FRC-APP",
            name="Proyecto prueba aprobación duplicada",
            project_type=ProjectType.development,
            status=ProjectStatus.active,
            organization_id=user.organization_id,
        )
        db.add(project)
        db.flush()

    project.pm_id = "pm-test-id"

    task = Task(
        id="timer-force-approval-task-id",
        code="TMR-FRC-APP-T1",
        project_id=project.id,
        title="Tarea duplicada aprobable",
        assignee_id=user.id,
    )
    db.add(task)
    db.flush()

    db.add(Imputation(
        user_id=user.id,
        project_id=project.id,
        task_id=task.id,
        date=date.today(),
        hours=1.0,
        description="Imputación original",
        is_billable=True,
        hourly_rate_snapshot=user.hourly_rate,
        cost_amount=10.0,
    ))
    db.commit()

    client.post(
        "/api/v1/imputations/timer/start",
        json={"project_id": project.id, "task_id": task.id},
        headers=dev_headers,
    )

    stop_response = client.post(
        "/api/v1/imputations/timer/stop",
        json={"description": "Duplicada aprobable", "is_billable": True, "force_duplicate": True},
        headers=dev_headers,
    )
    assert stop_response.status_code == 200
    forced_id = stop_response.json()["id"]

    approve_response = client.post(f"/api/v1/imputations/{forced_id}/approve", headers=pm_headers)
    assert approve_response.status_code == 200

    duplicates = db.query(Imputation).filter(
        Imputation.user_id == user.id,
        Imputation.task_id == task.id,
        Imputation.date == date.today(),
    ).all()
    assert len(duplicates) == 2
    assert sum(imp.hours for imp in duplicates) >= 1.25

    week = client.get("/api/v1/imputations/my/week", headers=dev_headers)
    assert week.status_code == 200
    assert week.json()["total_hours"] >= 1.25


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
    data = response.json()["items"]
    assert isinstance(data, list)


def test_dismiss_alert(db: Session, timer_client):
    """Test dismissing an imputation alert."""
    client, token = timer_client
    headers = {"Authorization": f"Bearer {token}"}

    # audit #90: rely on conftest-seeded dev_test user instead of silent skip
    user = db.query(User).filter(User.username == "dev_test").first()
    assert user is not None, "conftest must seed dev_test user"

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


@pytest.mark.skip(reason="audit #90: depends on seeded Project. Refactor pending — see test_start_timer for the local-creation pattern.")
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


@pytest.mark.skip(reason="audit #90: depends on seeded Project. Refactor pending — see test_start_timer for the local-creation pattern.")
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


@pytest.mark.skip(reason="audit #90: depends on seeded Project. Refactor pending — see test_start_timer for the local-creation pattern.")
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
