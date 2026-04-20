import pytest
from sqlalchemy.orm import Session
from app.services.service_desk.ticket_query_service import build_ticket_list_query
from app.models.user import User, UserRole

@pytest.fixture
def db_session(db) -> Session:
    return db

def test_build_ticket_list_query_superadmin(db_session):
    class DummyUser:
        is_superadmin = True
        role = UserRole.admin
        organization_id = None
        id = "admin"
    q = build_ticket_list_query(db_session, DummyUser())
    assert hasattr(q, "all")

def test_build_ticket_list_query_employee_scope(db_session):
    class DummyUser:
        is_superadmin = False
        role = UserRole.employee
        organization_id = "org-1"
        id = "emp-1"
    q = build_ticket_list_query(db_session, DummyUser())
    assert hasattr(q, "all")
