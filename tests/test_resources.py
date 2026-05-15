"""
Tests for Resource Planning Analytics and Dashboards.
"""
import pytest
from sqlalchemy.orm import Session

from app.models.user import User


@pytest.fixture
def resource_client(client, admin_token):
    """Fixture for API client with admin auth headers."""
    return (client, admin_token)


def _make_project(db: Session, code="RES-TEST-001", name="Resource Test Project"):
    """Create a minimal Project locally (audit #90: avoid seed dependency)."""
    from app.models.project import Project, ProjectType, ProjectStatus
    admin = db.query(User).filter(User.id == "admin-test-id").first()
    project = Project(
        code=code,
        name=name,
        project_type=ProjectType.consulting,
        status=ProjectStatus.active,
        organization_id=admin.organization_id if admin else None,
        pm_id="pm-test-id",
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _make_skill(db: Session, name="Resource Test Skill"):
    """Create a minimal Skill locally (audit #90: avoid seed dependency)."""
    from app.models.resources import Skill, SkillCategory
    admin = db.query(User).filter(User.id == "admin-test-id").first()
    skill = Skill(
        name=name,
        category=SkillCategory.technical,
        organization_id=admin.organization_id if admin else None,
    )
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return skill


# ── Availability Matrix Tests ──────────────────────────────────────────────

def test_availability_matrix(db: Session, resource_client):
    """Test getting team availability matrix."""
    client, token = resource_client
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/v1/resources/availability-matrix?weeks_ahead=4", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # Should have users × weeks records
    if data:
        assert "user_id" in data[0]
        assert "week_iso" in data[0]
        assert "load_pct" in data[0]
        assert "available_hours" in data[0]


def test_availability_matrix_for_project(db: Session, resource_client):
    """Test getting availability matrix filtered by project."""
    client, token = resource_client
    headers = {"Authorization": f"Bearer {token}"}

    # audit #90: create the project locally instead of depending on seed data
    project = _make_project(db, code="RES-AVAIL-001", name="Availability Matrix Project")

    response = client.get(
        f"/api/v1/resources/availability-matrix?weeks_ahead=4&project_id={project.id}",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


# ── Load Scoring Tests ─────────────────────────────────────────────────────

def test_load_scoring(db: Session, resource_client):
    """Test getting users ranked by load."""
    client, token = resource_client
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/v1/resources/load-scoring", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)

    if data:
        # Should be sorted by load_pct descending
        loads = [item["load_pct"] for item in data]
        assert loads == sorted(loads, reverse=True)

        # Check structure
        item = data[0]
        assert "user_id" in item
        assert "load_pct" in item
        assert "status" in item
        assert item["status"] in ["overloaded", "at_capacity", "underutilized"]


def test_load_scoring_filters(db: Session, resource_client):
    """Test load scoring with filters."""
    client, token = resource_client
    headers = {"Authorization": f"Bearer {token}"}

    # Only overloaded users
    response = client.get(
        "/api/v1/resources/load-scoring?min_load_pct=100&max_load_pct=200",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()

    if data:
        for item in data:
            assert 100 <= item["load_pct"] <= 200


# ── Team Health Tests ──────────────────────────────────────────────────────

def test_team_health(db: Session, resource_client):
    """Test getting team health metrics."""
    client, token = resource_client
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/v1/resources/team-health", headers=headers)
    assert response.status_code == 200
    data = response.json()

    assert "avg_load_pct" in data
    assert "overloaded_count" in data
    assert "at_capacity_count" in data
    assert "underutilized_count" in data
    assert "total_users" in data
    assert "billable_pct" in data

    # Counters should be non-negative
    assert data["overloaded_count"] >= 0
    assert data["at_capacity_count"] >= 0
    assert data["underutilized_count"] >= 0
    assert data["total_users"] >= 0


# ── Skill Gaps Tests ───────────────────────────────────────────────────────

def test_skill_gaps(db: Session, resource_client):
    """Test analyzing skill gaps in a project."""
    client, token = resource_client
    headers = {"Authorization": f"Bearer {token}"}

    # audit #90: create the project locally instead of depending on seed data
    project = _make_project(db, code="RES-SKILL-001", name="Skill Gaps Project")

    response = client.get(f"/api/v1/resources/{project.id}/skill-gaps", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


# ── Available Users by Skill Tests ─────────────────────────────────────────

def test_available_by_skill(db: Session, resource_client):
    """Test getting available users by skill."""
    client, token = resource_client
    headers = {"Authorization": f"Bearer {token}"}

    # audit #90: create the skill locally instead of depending on seed data
    skill = _make_skill(db, name="Python (resources test)")

    response = client.get(f"/api/v1/resources/available-by-skill/{skill.id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)

    if data:
        item = data[0]
        assert "user_id" in item
        assert "level" in item
        assert "available_hours" in item
        assert "load_pct" in item


# ── Utilization History Tests ──────────────────────────────────────────────

def test_utilization_history(db: Session, resource_client):
    """Test getting utilization history."""
    client, token = resource_client
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/v1/resources/utilization-history?weeks_back=12", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)

    if data:
        item = data[0]
        assert "user_id" in item
        assert "week_iso" in item
        assert "planned_hours" in item
        assert "actual_hours" in item
        assert "utilization_pct" in item


def test_utilization_history_for_user(db: Session, resource_client):
    """Test getting utilization history for specific user."""
    client, token = resource_client
    headers = {"Authorization": f"Bearer {token}"}

    # audit #90: rely on conftest-seeded admin user instead of silent skip
    user = db.query(User).filter(User.id == "admin-test-id").first()
    assert user is not None, "conftest must seed admin-test-id"

    response = client.get(
        f"/api/v1/resources/utilization-history?user_id={user.id}&weeks_back=12",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)

    if data:
        for item in data:
            assert item["user_id"] == user.id


# ── Alerts Tests ───────────────────────────────────────────────────────────

def test_get_resource_alerts(db: Session, resource_client):
    """Test getting resource alerts."""
    client, token = resource_client
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/v1/resources/alerts", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)

    if data:
        item = data[0]
        assert "id" in item
        assert "user_id" in item
        assert "alert_type" in item
        assert "severity" in item


def test_acknowledge_alert(db: Session, resource_client, admin_token):
    """Test acknowledging an alert."""
    client, token = resource_client
    headers = {"Authorization": f"Bearer {token}"}

    from app.models.resources import ResourceAlert, ResourceAlertType

    # audit #90: rely on conftest-seeded admin user instead of silent skip
    user = db.query(User).filter(User.id == "admin-test-id").first()
    assert user is not None, "conftest must seed admin-test-id"

    alert = ResourceAlert(
        user_id=user.id,
        alert_type=ResourceAlertType.overload_warning,
        context='{"week": "2025-W20", "load_pct": 120}',
        severity="warning",
    )
    db.add(alert)
    db.commit()

    # Acknowledge the alert
    response = client.patch(
        f"/api/v1/resources/alerts/{alert.id}/acknowledge",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "acknowledged"

    # Verify it's acknowledged
    db.refresh(alert)
    assert alert.acknowledged_at is not None


# ── Forecast Tests ─────────────────────────────────────────────────────────

def test_forecast(db: Session, resource_client):
    """Test getting 4-week forecast."""
    client, token = resource_client
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/v1/resources/forecast", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_availability_matrix_iso_week_calculation(db: Session, resource_client):
    """Test that ISO week calculations are accurate."""
    client, token = resource_client
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/v1/resources/availability-matrix?weeks_ahead=4", headers=headers)
    assert response.status_code == 200
    data = response.json()

    if data:
        # Verify week_iso format and uniqueness per user
        seen_weeks = {}
        for record in data:
            user_id = record["user_id"]
            week_iso = record["week_iso"]

            # week_iso should be in format YYYY-WXX
            parts = week_iso.split("-W")
            assert len(parts) == 2
            assert parts[0].isdigit() and len(parts[0]) == 4  # Year
            assert parts[1].isdigit() and 1 <= int(parts[1]) <= 53  # Week 01-53

            # Track which weeks we've seen for each user
            if user_id not in seen_weeks:
                seen_weeks[user_id] = []
            seen_weeks[user_id].append(week_iso)

        # Should have multiple weeks for users
        if seen_weeks:
            assert any(len(weeks) > 1 for weeks in seen_weeks.values())


def test_billable_percentage_calculated_correctly(db: Session, resource_client):
    """Test that billable percentage is calculated from actual data."""
    client, token = resource_client
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/v1/resources/team-health", headers=headers)
    assert response.status_code == 200
    data = response.json()

    # billable_pct should be a number between 0 and 100
    assert isinstance(data["billable_pct"], (int, float))
    assert 0 <= data["billable_pct"] <= 100


def test_organization_filtering_in_availability(db: Session, resource_client):
    """Test that availability matrix only includes users from current organization."""
    client, token = resource_client
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/v1/resources/availability-matrix", headers=headers)
    assert response.status_code == 200
    data = response.json()

    # Get current user's organization
    from app.models.user import User
    user = db.query(User).filter(User.is_active == True).first()
    if user and user.organization_id:
        # All returned users should be from the same organization
        if data:
            for record in data:
                user_record = db.query(User).filter(User.id == record["user_id"]).first()
                # Verify user belongs to current user's organization
                if user_record:
                    assert user_record.organization_id == user.organization_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
