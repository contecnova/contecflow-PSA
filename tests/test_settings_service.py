import pytest
from sqlalchemy.orm import Session
from app.services.settings_service import (
    get_general_settings, update_setting, get_project_types, create_project_type, update_project_type, delete_project_type,
    get_project_statuses, create_project_status, update_project_status, delete_project_status,
    get_task_statuses, create_task_status, update_task_status, delete_task_status,
    get_departments, create_department, update_department, delete_department,
)

@pytest.fixture
def db_session(db) -> Session:
    return db

def test_get_and_update_general_settings(db_session):
    settings = get_general_settings(db_session)
    assert isinstance(settings, list)
    updated = update_setting("company_name", "TestCo", None, db_session)
    assert updated.value == "TestCo"

def test_project_type_crud(db_session):
    types = get_project_types(db_session)
    assert isinstance(types, list)
    payload = {"value": "testtype", "label": "Test Type", "color": "#fff", "sort_order": 99}
    item = create_project_type(payload, db_session)
    assert item.value == "testtype"
    item2 = update_project_type(item.id, {"label": "Updated"}, db_session)
    assert item2.label == "Updated"
    result = delete_project_type(item.id, db_session)
    assert result["ok"] is True

def test_project_status_crud(db_session):
    statuses = get_project_statuses(db_session)
    assert isinstance(statuses, list)
    payload = {"value": "teststatus", "label": "Test Status", "color": "#000", "is_default": False, "sort_order": 99}
    item = create_project_status(payload, db_session)
    assert item.value == "teststatus"
    item2 = update_project_status(item.id, {"label": "Updated"}, db_session)
    assert item2.label == "Updated"
    result = delete_project_status(item.id, db_session)
    assert result["ok"] is True

def test_task_status_crud(db_session):
    statuses = get_task_statuses(db_session)
    assert isinstance(statuses, list)
    payload = {"value": "testtask", "label": "Test Task", "color": "#111", "is_default": False, "sort_order": 99}
    item = create_task_status(payload, db_session)
    assert item.value == "testtask"
    item2 = update_task_status(item.id, {"label": "Updated"}, db_session)
    assert item2.label == "Updated"
    result = delete_task_status(item.id, db_session)
    assert result["ok"] is True


# ── Tests for soft-delete → recreate cycle (GH issue: department soft-delete breaks uniqueness)
def test_project_type_delete_and_recreate_same_value(db_session):
    """Verify that deleting and recreating a project type with same value works."""
    payload = {"value": "cycletype", "label": "Cycle Type", "color": "#f00", "sort_order": 50}
    
    # Create
    item1 = create_project_type(payload, db_session)
    assert item1.value == "cycletype"
    
    # Delete (soft-delete)
    result = delete_project_type(item1.id, db_session)
    assert result["ok"] is True
    
    # Recreate with same value should NOT fail
    item2 = create_project_type(payload, db_session)
    assert item2.value == "cycletype"
    assert item2.id != item1.id  # Different ID because it's a new record

def test_project_status_delete_and_recreate_same_value(db_session):
    """Verify that deleting and recreating a project status with same value works."""
    payload = {"value": "cyclestatus", "label": "Cycle Status", "color": "#0f0", "is_default": False, "sort_order": 50}
    
    item1 = create_project_status(payload, db_session)
    result = delete_project_status(item1.id, db_session)
    assert result["ok"] is True
    
    item2 = create_project_status(payload, db_session)
    assert item2.value == "cyclestatus"
    assert item2.id != item1.id

def test_task_status_delete_and_recreate_same_value(db_session):
    """Verify that deleting and recreating a task status with same value works."""
    payload = {"value": "cycletask", "label": "Cycle Task", "color": "#00f", "is_default": False, "sort_order": 50}
    
    item1 = create_task_status(payload, db_session)
    result = delete_task_status(item1.id, db_session)
    assert result["ok"] is True
    
    item2 = create_task_status(payload, db_session)
    assert item2.value == "cycletask"
    assert item2.id != item1.id

def test_department_delete_and_recreate_same_name(db_session):
    """Verify that deleting and recreating a department with same name works (GH issue fix)."""
    payload = {"name": "IT Department", "description": "Test IT"}
    
    # Create
    dept1 = create_department(payload, db_session)
    assert dept1.name == "IT Department"
    dept1_id = dept1.id
    
    # Delete (soft-delete, so row still exists but is_active=False)
    result = delete_department(dept1_id, db_session)
    assert result["ok"] is True
    
    # Recreate with same name should NOT fail (this was the bug)
    dept2 = create_department(payload, db_session)
    assert dept2.name == "IT Department"
    assert dept2.id != dept1_id  # Different record
    
    # New department should be in the active list
    active_depts = get_departments(db_session)
    names = [d.name for d in active_depts]
    assert "IT Department" in names
    # Only one "IT Department" should be active
    assert names.count("IT Department") == 1
