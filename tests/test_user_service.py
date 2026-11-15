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

def _dummy(rol):
    class DummyUser:
        id = "dummy"
        organization_id = 1
        is_active = True
        status = UserStatus.active
        role = rol
    return DummyUser()


def test_get_org_chart_payload(db_session):
    result = get_org_chart_payload(db_session, _dummy(UserRole.admin))
    assert "nodes" in result


@pytest.mark.parametrize("rol", [UserRole.employee, UserRole.subcontractor, None])
def test_get_org_chart_payload_minimo_privilegio(db_session, rol):
    # DOCS.md, «Segunda auditoría 2026-11»: empleado y subcontratado ya no ven
    # el organigrama (403); sin rol, falla cerrada.
    with pytest.raises(ErrorDeDominio) as e:
        get_org_chart_payload(db_session, _dummy(rol))
    assert e.value.status_code == 403

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
