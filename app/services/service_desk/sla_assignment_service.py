from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.clients import Client
from app.models.pipeline import Contract
from app.models.service_desk import SLAPolicy


def _ensure_sla_policy_exists_if_provided(db: Session, sla_policy_id: str) -> None:
    if not sla_policy_id:
        return
    policy = db.query(SLAPolicy).filter(
        SLAPolicy.id == sla_policy_id,
        SLAPolicy.is_active == True,
    ).first()
    if not policy:
        raise HTTPException(404, "Política SLA no encontrada")


def assign_sla_policy_to_client(db: Session, client_id: str, sla_policy_id: str) -> None:
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(404, "Cliente no encontrado")
    _ensure_sla_policy_exists_if_provided(db, sla_policy_id)
    client.sla_policy_id = sla_policy_id


def assign_sla_policy_to_contract(db: Session, contract_id: str, sla_policy_id: str) -> None:
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        raise HTTPException(404, "Contrato no encontrado")
    _ensure_sla_policy_exists_if_provided(db, sla_policy_id)
    contract.sla_policy_id = sla_policy_id


def assign_sla_policy_target(db: Session, target_type: str, target_id: str, sla_policy_id: str) -> dict:
    if target_type == "client":
        assign_sla_policy_to_client(db, target_id, sla_policy_id)
        return {"ok": True, "client_id": target_id, "sla_policy_id": sla_policy_id}
    if target_type == "contract":
        assign_sla_policy_to_contract(db, target_id, sla_policy_id)
        return {"ok": True, "contract_id": target_id, "sla_policy_id": sla_policy_id}
    raise HTTPException(400, "target_type inválido")


def sla_policy_id_from_payload(payload: dict):
    return payload.get("sla_policy_id")
