import uuid as _uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.models.pipeline import Opportunity, OpportunityActivity, OpportunityStage, PipelineStageConfig
from app.models.project import Project, ProjectStatus, ProjectType
from app.models.user import User
from app.services.numbering import next_numbered_code

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
    q = db.query(Opportunity).options(joinedload(Opportunity.owner))
    q = scope_opportunity_query(q, db, current_user)
    if stage:
        q = q.filter(Opportunity.stage == stage)
    if owner_id:
        q = q.filter(Opportunity.owner_id == owner_id)
    return q.order_by(Opportunity.created_at.desc()).all()


def get_pipeline_opps(db: Session, current_user: User):
    q = db.query(Opportunity).options(joinedload(Opportunity.owner))
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


def update_opportunity(
    db: Session,
    current_user: User,
    opp_id: str,
    data: dict,
    new_stage=None,
    explicit_probability=None,
) -> Opportunity:
    opp = scope_opportunity_query(
        db.query(Opportunity), db, current_user
    ).filter(Opportunity.id == opp_id).first()
    if not opp:
        raise HTTPException(404, "Oportunidad no encontrada")

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
    opp = scope_opportunity_query(
        db.query(Opportunity), db, current_user
    ).filter(Opportunity.id == opp_id).first()
    if not opp:
        raise HTTPException(404, "Oportunidad no encontrada")
    db.delete(opp)
    db.commit()
    return {"ok": True}


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
    opp = scope_opportunity_query(
        db.query(Opportunity), db, current_user
    ).filter(Opportunity.id == opp_id).first()
    if not opp:
        raise HTTPException(404, "Oportunidad no encontrada")
    if opp.project_id:
        raise HTTPException(400, f"Esta oportunidad ya está vinculada al proyecto {opp.project_id}")

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
        billing_rate=opp.hourly_rate if hasattr(opp, "hourly_rate") else None,
    )
    db.add(project)

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
    db.commit()
    db.refresh(project)

    return {
        "project_id":   project.id,
        "project_code": project.code,
        "project_name": project.name,
        "message":      f"Proyecto {code} creado correctamente",
    }


def get_active_opportunities_for_forecast(db: Session):
    return db.query(Opportunity).filter(
        Opportunity.stage.notin_(["won", "lost", "cancelled"])
    ).all()


def list_stage_configs(db: Session):
    return (
        db.query(PipelineStageConfig)
        .filter(PipelineStageConfig.is_active == True)  # noqa: E712
        .order_by(PipelineStageConfig.order)
        .all()
    )


def create_stage_config(db: Session, payload_dict: dict) -> PipelineStageConfig:
    existing = db.query(PipelineStageConfig).filter(
        PipelineStageConfig.stage_key == payload_dict["stage_key"]
    ).first()
    if existing:
        raise HTTPException(400, f"La etapa '{payload_dict['stage_key']}' ya existe")
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
    if not stage:
        raise HTTPException(404, "Etapa no encontrada")
    stage.is_active = False
    db.commit()
