import pytest
from sqlalchemy.orm import Session
from app.services.task_service import validate_task_transition, apply_status_side_effects, cascade_reschedule, bulk_update_tasks
from app.models.task import TaskStatus, Task
from app.models.user import User, UserRole
from fastapi import HTTPException
from datetime import date
from app.core.errores import ErrorDeDominio

@pytest.fixture
def db_session(db) -> Session:
    return db

def test_validate_task_transition_valid():
    validate_task_transition(TaskStatus.todo, TaskStatus.in_progress)
    validate_task_transition(TaskStatus.in_progress, TaskStatus.done)

def test_validate_task_transition_invalid():
    with pytest.raises((HTTPException, ErrorDeDominio)):
        validate_task_transition(TaskStatus.done, TaskStatus.todo)

def test_apply_status_side_effects_sets_timestamps():
    class DummyTask:
        started_at = None
        completed_at = None
        project_id = None
        assignee_id = None
    t = DummyTask()
    apply_status_side_effects(t, TaskStatus.in_progress)
    assert t.started_at is not None
    apply_status_side_effects(t, TaskStatus.done)
    assert t.completed_at is not None

def test_cascade_reschedule_no_task(db_session):
    with pytest.raises((HTTPException, ErrorDeDominio)):
        cascade_reschedule("nonexistent", date.today(), db_session)

# bulk_update_tasks edge case: forbidden for employee

def test_bulk_update_tasks_forbidden(db_session):
    user = db_session.query(User).filter(User.role == UserRole.employee).first()
    task = db_session.query(Task).first()
    if not user or not task:
        pytest.skip("No hay datos de usuario o tarea")
    result = bulk_update_tasks([task.id], {"status": TaskStatus.done}, user, db_session)
    assert any(x["reason"] == "forbidden" for x in result.get("skipped", []))
