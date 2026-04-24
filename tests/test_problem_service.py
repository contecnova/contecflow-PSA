import pytest
from sqlalchemy.orm import Session
from app.services.service_desk.problem_service import list_problems_payload, _validate_problem_org_constraints
from fastapi import HTTPException

@pytest.fixture
def db_session(db) -> Session:
    return db

def test_list_problems_payload_empty(db_session):
    class DummyUser:
        is_superadmin = True
        organization_id = None
    result = list_problems_payload(db_session, DummyUser(), 1, 10)
    assert isinstance(result, list)

def test_validate_problem_org_constraints_superadmin(db_session):
    class DummyUser:
        is_superadmin = True
        organization_id = None
    # Should not raise
    _validate_problem_org_constraints(db_session, DummyUser())

def test_validate_problem_org_constraints_invalid_project(db_session):
    class DummyUser:
        is_superadmin = False
        organization_id = "org-1"
    with pytest.raises(HTTPException):
        _validate_problem_org_constraints(db_session, DummyUser(), project_id="nonexistent")
