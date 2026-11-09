import uuid as _uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.models.pipeline import Opportunity, OpportunityActivity, OpportunityStage, PipelineStageConfig
from app.models.project import Project, ProjectStatus, ProjectType
from app.models.user import User
from app.services.numbering import next_numbered_code
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

STAGE_LABELS = {
    "lead": "Lead", "qualification": "Cualificación", "proposal": "Propuesta",
    "negotiation": "Negociación", "won": "Ganada", "lost": "Perdida", "cancelled": "Cancelada"
}
STAGE_PROB = {
    "lead": 10, "qualification": 25, "proposal": 50,
    "negotiation": 75, "won": 100, "lost": 0, "cancelled": 0,
}

_STAGE_VALID_TRANSITIONS: dict = {
    "lead":          {"qualification", "proposal", "lost", "cancelled"},
    "qualification": {"proposal", "lost", "cancelled", "lead"},
    "proposal":      {"negotiation", "lost", "cancelled", "qualification"},
    "negotiation":   {"won", "lost", "cancelled", "proposal"},
    "won":           set(),
    "lost":          {"lead"},
    "cancelled":     set(),
}


def scope_opportunity_query(q, db: Session, current_user: User):
    if current_user.is_superadmin or not current_user.organization_id:
        return q
    org_user_ids = db.query(User.id).filter(
        User.organization_id == current_user.organization_id
    ).scalar_subquery()
    return q.filter(Opportunity.owner_id.in_(org_user_ids))


def get_opportunities(db: Session, current_user: User, stage=None, owner_id=None):
    q = db.query(Opportunity).options(joinedload(Opportunity.owner)).filter(Opportunity.is_active == True)
    q = scope_opportunity_query(q, db, current_user)
    if stage:
        q = q.filter(Opportunity.stage == stage)
    if owner_id:
        q = q.filter(Opportunity.owner_id == owner_id)
    return q.order_by(Opportunity.created_at.desc()).all()


def get_pipeline_opps(db: Session, current_user: User):
    q = db.query(Opportunity).options(joinedload(Opportunity.owner)).filter(Opportunity.is_active == True)
    q = scope_opportunity_query(q, db, current_user)
    return q.all()


def create_opportunity(db: Session, current_user: User, payload_dict: dict) -> Opportunity:
    code = next_numbered_code(db, "opportunity", prefix="OPP", padding=4)
    opp = Opportunity(code=code, **payload_dict)
    if not opp.owner_id:
        opp.owner_id = current_user.id
    db.add(opp)
    db.commit()
    db.refresh(opp)
    act = OpportunityActivity(
        opportunity_id=opp.id,
        user_id=current_user.id,
        type="note",
        content=f"Oportunidad creada en etapa {STAGE_LABELS.get(opp.stage, opp.stage)}",
    )
    db.add(act)
    db.commit()
    return opp


def oportunidad_propia(db: Session, current_user: User, opp_id: str) -> Opportunity:
    """La oportunidad activa, si el sujeto puede verla. 404 si no.

    Auditoria 2026-08. Esta busqueda estaba **copiada literalmente tres veces**
    —en `update_opportunity`, `delete_opportunity` y
    `convert_opportunity_to_project`— y hacia falta una cuarta para el
    `GET /pipeline/{id}` del hallazgo 37, que la interfaz llamaba y no existia.
    Tres copias de la misma consulta es donde se pierde una guarda, asi que vive
    aqui.

    El `is_active == True` no es decorativo: el borrado de una oportunidad es
    logico, y sin ese filtro una ya borrada volveria a aparecer.
    """
    opp = scope_opportunity_query(
        db.query(Opportunity), db, current_user
    ).filter(
        Opportunity.id == opp_id,
        Opportunity.is_active == True,  # noqa: E712
    ).first()
    if not opp:
        raise HTTPException(404, "Oportunidad no encontrada")
    return opp


def update_opportunity(
    db: Session,
    current_user: User,
    opp_id: str,
    data: dict,
    new_stage=None,
    explicit_probability=None,
) -> Opportunity:
    opp = oportunidad_propia(db, current_user, opp_id)

    old_stage = opp.stage

    if new_stage and new_stage != old_stage:
        allowed = _STAGE_VALID_TRANSITIONS.get(old_stage, set())
        if new_stage not in allowed:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Transición de etapa no permitida: "
                    f"'{STAGE_LABELS.get(old_stage, old_stage)}' → "
                    f"'{STAGE_LABELS.get(new_stage, new_stage)}'"
                ),
            )

    for k, v in data.items():
        setattr(opp, k, v)

    if new_stage and new_stage != old_stage:
        act = OpportunityActivity(
            opportunity_id=opp.id,
            user_id=current_user.id,
            type="stage_change",
            content=(
                f"Etapa cambiada: {STAGE_LABELS.get(old_stage, old_stage)} → "
                f"{STAGE_LABELS.get(new_stage, new_stage)}"
            ),
        )
        db.add(act)
        if new_stage in STAGE_PROB and not explicit_probability:
            opp.probability = STAGE_PROB[new_stage]

    db.commit()
    db.refresh(opp)
    return opp


def delete_opportunity(db: Session, current_user: User, opp_id: str) -> dict:
    opp = oportunidad_propia(db, current_user, opp_id)
    if opp.project_id:
        raise HTTPException(400, "No se puede eliminar: la oportunidad esta vinculada a un proyecto")
    opp.is_active = False
    db.commit()
    return {"ok": True, "message": "Oportunidad eliminada correctamente"}


def list_activities(db: Session, opp_id: str):
    return (
        db.query(OpportunityActivity)
        .options(joinedload(OpportunityActivity.user))
        .filter(OpportunityActivity.opportunity_id == opp_id)
        .order_by(OpportunityActivity.created_at.desc())
        .all()
    )


def add_activity(
    db: Session, current_user: User, opp_id: str, type_: str, content: str
) -> OpportunityActivity:
    act = OpportunityActivity(
        opportunity_id=opp_id,
        user_id=current_user.id,
        type=type_,
        content=content,
    )
    db.add(act)
    db.commit()
    db.refresh(act)
    return act


def convert_opportunity_to_project(db: Session, current_user: User, opp_id: str) -> dict:
    opp = oportunidad_propia(db, current_user, opp_id)
    if opp.project_id:
        raise HTTPException(400, f"Esta oportunidad ya está vinculada al proyecto {opp.project_id}")
    # Revisión 2026-11: convertir marca la oportunidad como ganada; una perdida
    # o cancelada no se resucita así.
    if str(getattr(opp.stage, "value", opp.stage)) in ("lost", "cancelled"):
        raise HTTPException(400, "Una oportunidad perdida o cancelada no se convierte en proyecto")

    code = next_numbered_code(db, "project", prefix="PRJ", padding=4)

    project = Project(
        id=str(_uuid.uuid4()),
        code=code,
        name=opp.name,
        description=opp.description,
        status=ProjectStatus.planning,
        project_type=ProjectType.consulting,
        billing_type="time_material",
        client_name=opp.client_name,
        client_id=opp.client_id,
        budget_amount=opp.expected_revenue,
        start_date=opp.expected_start_date,
        end_date_planned=opp.expected_close_date,
        pm_id=opp.owner_id or current_user.id,
        billing_rate=opp.hourly_rate,
    )
    db.add(project)
    db.flush()  # get project.id before creating the contract

    opp.stage = OpportunityStage.won
    opp.project_id = project.id

    act = OpportunityActivity(
        id=str(_uuid.uuid4()),
        opportunity_id=opp.id,
        user_id=current_user.id,
        type="note",
        content=f"Oportunidad convertida a proyecto {code} por {current_user.full_name}",
    )
    db.add(act)

    # ── Auto-create ASC 606 RevenueContract ────────────────────────────────────
    rev_contract_id = None
    try:
        from app.services.proposal_service import CONTRACT_TYPE_TO_ASC_METHOD
        from app.models.revenue import RevenueContract, ASCMethod

        asc_method_value = CONTRACT_TYPE_TO_ASC_METHOD.get(
            opp.contract_type or "", "over_time"
        )
        asc_method = ASCMethod(asc_method_value)
        duration_months = None
        if opp.expected_duration_weeks:
            duration_months = max(1, round(opp.expected_duration_weeks / 4))

        rev = RevenueContract(
            id=str(_uuid.uuid4()),
            organization_id=current_user.organization_id,
            project_id=project.id,
            client_id=opp.client_id,
            name=f"Contrato: {opp.name}",
            contract_value=opp.expected_revenue or 0.0,
            currency=settings.DEFAULT_CURRENCY,
            method=asc_method,
            start_date=opp.expected_start_date,
            end_date=opp.expected_close_date,
            duration_months=duration_months,
            notes=f"Generado automáticamente al convertir oportunidad {opp.code}",
        )
        db.add(rev)
        rev_contract_id = rev.id
    except Exception:
        # Non-blocking: project creation must not fail if revenue module errors
        logger.exception("Error no bloqueante creando contrato de ingresos para opp=%s", getattr(opp, "code", None))

    db.commit()
    db.refresh(project)

    return {
        "project_id":      project.id,
        "project_code":    project.code,
        "project_name":    project.name,
        "rev_contract_id": rev_contract_id,
        "message":         f"Proyecto {code} creado correctamente",
    }


def get_active_opportunities_for_forecast(db: Session):
    return db.query(Opportunity).filter(
        Opportunity.is_active == True,
        Opportunity.stage.notin_(["won", "lost", "cancelled"])
    ).all()


def list_stage_configs(db: Session):
    stages = (
        db.query(PipelineStageConfig)
        .filter(PipelineStageConfig.is_active == True)
        .order_by(PipelineStageConfig.order)
        .all()
    )
    if not stages:
        # Defaults si la base está vacía
        defaults = [
            dict(stage_key=k, label=v, order=i, probability_default=STAGE_PROB[k],
                 description=None, color=None, is_terminal=(k in ("won", "lost", "cancelled")), is_won=(k == "won"), id=k)
            for i, (k, v) in enumerate(STAGE_LABELS.items())
        ]
        # Simula objetos con atributos para compatibilidad
        class Dummy:
            def __init__(self, d):
                self.__dict__.update(d)
        return [Dummy(d) for d in defaults]
    return stages


def create_stage_config(db: Session, payload_dict: dict) -> PipelineStageConfig:
    existing = db.query(PipelineStageConfig).filter(
        PipelineStageConfig.stage_key == payload_dict["stage_key"]
    ).first()
    if existing:
        from fastapi import status
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"La etapa '{payload_dict['stage_key']}' ya existe")
    stage = PipelineStageConfig(**payload_dict)
    db.add(stage)
    db.commit()
    db.refresh(stage)
    return stage


def update_stage_config(db: Session, stage_id: str, data: dict) -> PipelineStageConfig:
    stage = db.query(PipelineStageConfig).filter(PipelineStageConfig.id == stage_id).first()
    if not stage:
        raise HTTPException(404, "Etapa no encontrada")
    for k, v in data.items():
        setattr(stage, k, v)
    db.commit()
    return stage


def delete_stage_config(db: Session, stage_id: str) -> None:
    stage = db.query(PipelineStageConfig).filter(PipelineStageConfig.id == stage_id).first()
    # Idempotente: si no existe, simplemente retorna (como DELETE de REST estándar)
    if not stage:
        return
    stage.is_active = False
    db.commit()


# ── Serialization helper ───────────────────────────────────────────────────

def serialize_opportunity(opp) -> dict:
    weighted = (opp.expected_revenue or 0) * (opp.probability / 100)
    proposal_status = "none"
    if opp.proposal_sent_at:
        proposal_status = "sent"
    elif opp.proposal_generated_at:
        proposal_status = "generated"
    return {
        "id": opp.id, "code": opp.code, "name": opp.name,
        "client_id": opp.client_id, "client_name": opp.client_name, "contact_name": opp.contact_name,
        "stage": opp.stage, "stage_label": STAGE_LABELS.get(opp.stage, opp.stage),
        "probability": opp.probability,
        "expected_revenue": opp.expected_revenue,
        "expected_margin_pct": opp.expected_margin_pct,
        "expected_hours": opp.expected_hours,
        "hourly_rate": opp.hourly_rate,
        "contract_type": opp.contract_type,
        "weighted_revenue": round(weighted, 0),
        "expected_close_date": str(opp.expected_close_date) if opp.expected_close_date else None,
        "expected_start_date": str(opp.expected_start_date) if opp.expected_start_date else None,
        "expected_duration_weeks": opp.expected_duration_weeks,
        "owner_id": opp.owner_id,
        "owner_name": opp.owner.full_name if opp.owner else None,
        "project_id": opp.project_id,
        "notes": opp.notes, "lost_reason": opp.lost_reason,
        "description": opp.description,
        "proposal_status": proposal_status,
        "proposal_template_id": opp.proposal_template_id,
        "proposal_generated_at": str(opp.proposal_generated_at)[:16] if opp.proposal_generated_at else None,
        "proposal_sent_at": str(opp.proposal_sent_at)[:16] if opp.proposal_sent_at else None,
        "created_at": str(opp.created_at)[:10] if opp.created_at else None,
    }
