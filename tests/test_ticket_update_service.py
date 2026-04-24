import pytest
from sqlalchemy.orm import Session
from app.services.service_desk.ticket_update_service import get_scoped_ticket_or_404
from fastapi import HTTPException

@pytest.fixture
def db_session(db) -> Session:
    return db

def test_get_scoped_ticket_or_404_not_found(db_session):
    class DummyUser:
        is_superadmin = True
        organization_id = None
    with pytest.raises(HTTPException) as exc:
        get_scoped_ticket_or_404(db_session, DummyUser(), "nonexistent")
    assert exc.value.status_code == 404
