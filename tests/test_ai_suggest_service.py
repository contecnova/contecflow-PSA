import pytest
from sqlalchemy.orm import Session
from app.services.service_desk.ai_suggest_service import _get_ticket_or_404
from fastapi import HTTPException

@pytest.fixture
def db_session(db) -> Session:
    return db

def test_get_ticket_or_404_not_found(db_session):
    with pytest.raises(HTTPException) as exc:
        _get_ticket_or_404(db_session, "nonexistent")
    assert exc.value.status_code == 404
