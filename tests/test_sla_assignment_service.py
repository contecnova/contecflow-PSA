import pytest
from sqlalchemy.orm import Session
from app.services.service_desk.sla_assignment_service import (
    assign_sla_policy_to_client, assign_sla_policy_to_contract, assign_sla_policy_target, _ensure_sla_policy_exists_if_provided
)
from fastapi import HTTPException

@pytest.fixture
def db_session(db) -> Session:
    return db

def test_assign_sla_policy_to_client_not_found(db_session):
    with pytest.raises(HTTPException) as exc:
        assign_sla_policy_to_client(db_session, "nonexistent", "sla-1")
    assert exc.value.status_code == 404

def test_assign_sla_policy_to_contract_not_found(db_session):
    with pytest.raises(HTTPException) as exc:
        assign_sla_policy_to_contract(db_session, "nonexistent", "sla-1")
    assert exc.value.status_code == 404

def test_assign_sla_policy_target_invalid_type(db_session):
    with pytest.raises(HTTPException) as exc:
        assign_sla_policy_target(db_session, "invalid", "id", "sla-1")
    assert exc.value.status_code == 400

def test_ensure_sla_policy_exists_if_provided_not_found(db_session):
    with pytest.raises(HTTPException) as exc:
        _ensure_sla_policy_exists_if_provided(db_session, "nonexistent")
    assert exc.value.status_code == 404
