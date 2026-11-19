from sqlalchemy.orm import Session

from app.models.clients import Client
from app.models.pipeline import Contract
from app.models.service_desk import SLAPolicy
import logging
from app.core.codigos_de_error import error

logger = logging.getLogger(__name__)


def _ensure_sla_policy_exists_if_provided(db: Session, sla_policy_id: str) -> None:
    if not sla_policy_id:
        return
    policy = db.query(SLAPolicy).filter(
        SLAPolicy.id == sla_policy_id,
        SLAPolicy.is_active == True,
    ).first()
    if not policy:
        raise error(404, "no_encontrado", detail="Política SLA no encontrada", que="politica_sla")


def assign_sla_policy_to_client(db: Session, client_id: str, sla_policy_id: str) -> None:
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise error(404, "no_encontrado", detail="Cliente no encontrado", que="cliente")
    _ensure_sla_policy_exists_if_provided(db, sla_policy_id)
    client.sla_policy_id = sla_policy_id


def assign_sla_policy_to_contract(db: Session, contract_id: str, sla_policy_id: str) -> None:
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        raise error(404, "no_encontrado", detail="Contrato no encontrado", que="contrato")
    _ensure_sla_policy_exists_if_provided(db, sla_policy_id)
    contract.sla_policy_id = sla_policy_id


def assign_sla_policy_target(db: Session, target_type: str, target_id: str, sla_policy_id: str) -> dict:
    if target_type == "client":
        assign_sla_policy_to_client(db, target_id, sla_policy_id)
        return {"ok": True, "client_id": target_id, "sla_policy_id": sla_policy_id}
    if target_type == "contract":
        assign_sla_policy_to_contract(db, target_id, sla_policy_id)
        return {"ok": True, "contract_id": target_id, "sla_policy_id": sla_policy_id}
    raise error(400, "sla_tipo_destino_no_valido", detail="target_type inválido")


def sla_policy_id_from_payload(payload: dict):
    return payload.get("sla_policy_id")
