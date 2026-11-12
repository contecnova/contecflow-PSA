import pytest
from sqlalchemy.orm import Session
from app.services.user_service import (
    get_load_map_payload, get_org_chart_payload, approval_chain_for_user, create_user_record
)
from app.models.user import User, UserRole, UserStatus
from fastapi import HTTPException
from app.core.errores import ErrorDeDominio

@pytest.fixture
def db_session(db) -> Session:
    return db

def test_get_load_map_payload(db_session):
    class DummyUser:
        id = "dummy"
        organization_id = 1
        is_active = True
        status = UserStatus.active
    dummy = DummyUser()
    result = get_load_map_payload(db_session, dummy)
    assert isinstance(result, list)

def test_get_org_chart_payload(db_session):
    class DummyUser:
        id = "dummy"
        organization_id = 1
        is_active = True
        status = UserStatus.active
    dummy = DummyUser()
    result = get_org_chart_payload(db_session, dummy)
    assert "nodes" in result

def test_approval_chain_for_user(db_session):
    user = db_session.query(User).filter(User.role == UserRole.admin).first()
    chain = approval_chain_for_user(user, db_session, user)
    assert isinstance(chain, list)

def test_create_user_record_duplicate(db_session):
    user = db_session.query(User).first()
    class Payload:
        username = user.username
        email = user.email
        password = "testpass123"
        def model_dump(self, exclude=None):
            return {"username": self.username, "email": self.email, "password": self.password}
    with pytest.raises((HTTPException, ErrorDeDominio)):
        create_user_record(Payload(), user, db_session)
