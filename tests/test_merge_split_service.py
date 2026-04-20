import pytest
from sqlalchemy.orm import Session
from app.services.service_desk.merge_split_service import get_ticket_or_404, ensure_distinct_tickets, derive_split_title, derive_split_description
from fastapi import HTTPException

@pytest.fixture
def db_session(db) -> Session:
    return db

def test_get_ticket_or_404_not_found(db_session):
    with pytest.raises(HTTPException) as exc:
        get_ticket_or_404(db_session, "nonexistent", "No existe")
    assert exc.value.status_code == 404

def test_ensure_distinct_tickets_same_id():
    class DummyTicket:
        id = "t1"
    with pytest.raises(HTTPException) as exc:
        ensure_distinct_tickets(DummyTicket(), DummyTicket())
    assert exc.value.status_code == 400

def test_derive_split_title_and_description():
    class DummyTicket:
        title = "Titulo"
        description = "Desc"
    assert derive_split_title(DummyTicket(), None).startswith("Titulo")
    assert derive_split_description(DummyTicket(), None) == "Desc"
