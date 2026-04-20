import pytest
from sqlalchemy.orm import Session
from app.services.service_desk.customer_context_service import get_customer_context_payload

@pytest.fixture
def db_session(db) -> Session:
    return db

def test_get_customer_context_payload_empty(db_session):
    result = get_customer_context_payload(db_session, "nonexistent")
    assert isinstance(result, dict)
    assert result["open_tickets"] == 0
