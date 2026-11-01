from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.service_desk import SLAPolicy
import logging

logger = logging.getLogger(__name__)


def serialize_sla_policy(policy: SLAPolicy) -> dict:
    return {
        "id": policy.id,
        "name": policy.name,
        "description": policy.description,
        "is_default": policy.is_default,
        "p1_response_hours": policy.p1_response_hours,
        "p1_resolution_hours": policy.p1_resolution_hours,
        "p2_response_hours": policy.p2_response_hours,
        "p2_resolution_hours": policy.p2_resolution_hours,
        "p3_response_hours": policy.p3_response_hours,
        "p3_resolution_hours": policy.p3_resolution_hours,
        "p4_response_hours": policy.p4_response_hours,
        "p4_resolution_hours": policy.p4_resolution_hours,
        "business_hours_only": policy.business_hours_only,
        "business_start": policy.business_start,
        "business_end": policy.business_end,
        "business_days": policy.business_days,
        "timezone": policy.timezone,
    }


def list_sla_policies_payload(db: Session) -> list[dict]:
    policies = db.query(SLAPolicy).filter(SLAPolicy.is_active == True).all()
    return [serialize_sla_policy(policy) for policy in policies]


def create_sla_policy_record(db: Session, payload) -> SLAPolicy:
    p = SLAPolicy(**payload.model_dump())
    db.add(p)
    if payload.is_default:
        db.flush()
        _quitar_otros_por_defecto(db, p)
    return p


def _quitar_otros_por_defecto(db: Session, policy: SLAPolicy) -> None:
    """Sólo una política por defecto por organización.

    El `update` iba sin filtro: para un superadministrador —sin filtro de
    tenant— quitaba la política por defecto de TODAS las organizaciones.
    """
    db.query(SLAPolicy).filter(
        SLAPolicy.id != policy.id,
        SLAPolicy.organization_id.is_(None) if policy.organization_id is None
        else SLAPolicy.organization_id == policy.organization_id,
    ).update({"is_default": False}, synchronize_session=False)


def get_sla_policy_or_404(db: Session, policy_id: str) -> SLAPolicy:
    policy = db.query(SLAPolicy).filter(SLAPolicy.id == policy_id).first()
    if not policy:
        raise HTTPException(404, "Politica SLA no encontrada")
    return policy


def update_sla_policy_record(db: Session, policy_id: str, payload) -> SLAPolicy:
    policy = get_sla_policy_or_404(db, policy_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(policy, key, value)
    if payload.is_default:
        _quitar_otros_por_defecto(db, policy)
    return policy


def deactivate_sla_policy_record(db: Session, policy_id: str) -> None:
    policy = get_sla_policy_or_404(db, policy_id)
    policy.is_active = False
