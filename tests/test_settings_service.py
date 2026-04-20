import pytest
from sqlalchemy.orm import Session
from app.services.settings_service import (
    get_general_settings, update_setting, get_project_types, create_project_type, update_project_type, delete_project_type,
    get_project_statuses, create_project_status, update_project_status, delete_project_status,
    get_task_statuses, create_task_status, update_task_status, delete_task_status
)
from app.models.settings import AppSetting, CustomProjectType, CustomProjectStatus, CustomTaskStatus

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
