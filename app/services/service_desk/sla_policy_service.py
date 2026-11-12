from sqlalchemy.orm import Session

from app.models.service_desk import SLAPolicy
import logging
from app.core.errores import ErrorDeDominio

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
        "calendar_id": policy.calendar_id,
    }


def list_sla_policies_payload(db: Session) -> list[dict]:
    """Las politicas activas, cada una con los clientes y contratos que la usan.

    Sin eso la asignacion por cliente o contrato (que manda sobre la politica
    por defecto) no se veia en ninguna pantalla.
    """
    from app.models.clients import Client
    from app.models.pipeline import Contract

    policies = db.query(SLAPolicy).filter(SLAPolicy.is_active == True).all()
    ids = [p.id for p in policies]
    clientes: dict = {}
    for c in db.query(Client.id, Client.name, Client.sla_policy_id).filter(Client.sla_policy_id.in_(ids)).all():
        clientes.setdefault(c.sla_policy_id, []).append({"id": c.id, "name": c.name})
    contratos: dict = {}
    for c in db.query(Contract).filter(Contract.sla_policy_id.in_(ids)).all():
        contratos.setdefault(c.sla_policy_id, []).append(
            {"id": c.id, "name": getattr(c, "title", None) or getattr(c, "name", None) or c.id})
    return [{**serialize_sla_policy(p), "clients": clientes.get(p.id, []), "contracts": contratos.get(p.id, [])}
            for p in policies]


def _exigir_calendario(db: Session, calendar_id) -> None:
    if not calendar_id:
        return
    from app.models.cmdb import SLACalendar
    cal = db.get(SLACalendar, calendar_id)
    if cal is None or not cal.is_active:
        raise ErrorDeDominio(422, "El calendario elegido no existe")


def create_sla_policy_record(db: Session, payload) -> SLAPolicy:
    _exigir_calendario(db, payload.calendar_id)
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
        raise ErrorDeDominio(404, "Politica SLA no encontrada")
    return policy


def update_sla_policy_record(db: Session, policy_id: str, payload) -> SLAPolicy:
    policy = get_sla_policy_or_404(db, policy_id)
    _exigir_calendario(db, payload.calendar_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(policy, key, value)
    if payload.is_default:
        _quitar_otros_por_defecto(db, policy)
    return policy


def deactivate_sla_policy_record(db: Session, policy_id: str) -> None:
    policy = get_sla_policy_or_404(db, policy_id)
    policy.is_active = False
