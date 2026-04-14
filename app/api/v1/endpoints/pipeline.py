from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from typing import Optional
from datetime import date
from pydantic import BaseModel

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager, require_admin
from app.models.user import User
from app.models.pipeline import Opportunity, OpportunityActivity, OpportunityStage, PipelineStageConfig
from app.models.project import Project

router = APIRouter()


def _scope_opportunity_query(q, db: Session, current_user: User):
    if current_user.is_superadmin or not current_user.organization_id:
        return q
    org_user_ids = db.query(User.id).filter(
        User.organization_id == current_user.organization_id
    ).scalar_subquery()
    return q.filter(Opportunity.owner_id.in_(org_user_ids))

STAGE_ORDER = ["lead", "qualification", "proposal", "negotiation", "won", "lost", "cancelled"]
STAGE_LABELS = {
    "lead": "Lead", "qualification": "Cualificación", "proposal": "Propuesta",
    "negotiation": "Negociación", "won": "Ganada", "lost": "Perdida", "cancelled": "Cancelada"
}
STAGE_PROB = {"lead": 10, "qualification": 25, "proposal": 50, "negotiation": 75, "won": 100, "lost": 0, "cancelled": 0}

# Allowed stage transitions
_STAGE_VALID_TRANSITIONS: dict = {
    "lead":          {"qualification", "proposal", "lost", "cancelled"},
    "qualification": {"proposal", "lost", "cancelled", "lead"},
    "proposal":      {"negotiation", "lost", "cancelled", "qualification"},
    "negotiation":   {"won", "lost", "cancelled", "proposal"},
    "won":           set(),          # Terminal
    "lost":          {"lead"},       # Allow re-opening a lost deal
    "cancelled":     set(),          # Terminal
}


class OpportunityIn(BaseModel):
    name: str
    client_name: str
    stage: str = "lead"
    probability: float = 50
    expected_revenue: Optional[float] = None
    expected_margin_pct: Optional[float] = None
    expected_hours: Optional[float] = None
    expected_close_date: Optional[date] = None
    expected_start_date: Optional[date] = None
    expected_duration_weeks: Optional[int] = None
    description: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    owner_id: Optional[str] = None
    notes: Optional[str] = None

class OpportunityUpdate(OpportunityIn):
    name: Optional[str] = None
    client_name: Optional[str] = None
    lost_reason: Optional[str] = None
    project_id: Optional[str] = None

class ActivityIn(BaseModel):
    type: str = "note"
    content: str

class StageConfigIn(BaseModel):
    stage_key: str
    label: str
    description: Optional[str] = None
    color: str = "#6B7280"
    order: int = 0
    probability_default: float = 50
    is_terminal: bool = False
    is_won: bool = False


def _next_code(db: Session) -> str:
    import re
    max_code = db.query(func.max(Opportunity.code)).scalar()
    if max_code:
        m = re.search(r"(\d+)$", max_code)
        next_num = (int(m.group(1)) + 1) if m else 1
    else:
        next_num = 1
    return f"OPP-{next_num:04d}"


def _opp_out(opp: Opportunity) -> dict:
    weighted = (opp.expected_revenue or 0) * (opp.probability / 100)
    return {
        "id": opp.id, "code": opp.code, "name": opp.name,
        "client_id": opp.client_id, "client_name": opp.client_name, "contact_name": opp.contact_name,
        "stage": opp.stage, "stage_label": STAGE_LABELS.get(opp.stage, opp.stage),
        "probability": opp.probability,
        "expected_revenue": opp.expected_revenue,
        "expected_margin_pct": opp.expected_margin_pct,
        "expected_hours": opp.expected_hours,
        "weighted_revenue": round(weighted, 0),
        "expected_close_date": str(opp.expected_close_date) if opp.expected_close_date else None,
        "expected_start_date": str(opp.expected_start_date) if opp.expected_start_date else None,
        "expected_duration_weeks": opp.expected_duration_weeks,
        "owner_id": opp.owner_id,
        "owner_name": opp.owner.full_name if opp.owner else None,
        "project_id": opp.project_id,
        "notes": opp.notes, "lost_reason": opp.lost_reason,
        "description": opp.description,
        "created_at": str(opp.created_at)[:10] if opp.created_at else None,
    }


@router.get("", summary="Listar oportunidades")
def list_opportunities(
    stage: Optional[str] = None,
    owner_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Opportunity).options(joinedload(Opportunity.owner))
    q = _scope_opportunity_query(q, db, current_user)
    if stage:
        q = q.filter(Opportunity.stage == stage)
    if owner_id:
        q = q.filter(Opportunity.owner_id == owner_id)
    opps = q.order_by(Opportunity.created_at.desc()).all()
    return [_opp_out(o) for o in opps]


@router.get("/pipeline", summary="Vista kanban del pipeline")
def get_pipeline(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Opportunity).options(joinedload(Opportunity.owner))
    q = _scope_opportunity_query(q, db, current_user)
    opps = q.all()
    stages = {}
    for s in STAGE_ORDER:
        stage_opps = [_opp_out(o) for o in opps if o.stage == s]
        stages[s] = {
            "label": STAGE_LABELS[s],
            "opportunities": stage_opps,
            "count": len(stage_opps),
            "total_revenue": sum(o["expected_revenue"] or 0 for o in stage_opps),
            "weighted_revenue": sum(o["weighted_revenue"] for o in stage_opps),
        }
    total_pipeline = sum(o["weighted_revenue"] for o in [_opp_out(op) for op in opps] if o["stage"] not in ["won", "lost", "cancelled"])
    return {
        "stages": stages,
        "summary": {
            "total_opportunities": len(opps),
            "open_opportunities": sum(1 for o in opps if o.stage not in ["won", "lost", "cancelled"]),
            "total_pipeline_weighted": round(total_pipeline, 0),
            "won_ytd": sum((o.expected_revenue or 0) for o in opps if o.stage == "won"),
            "win_rate": round(sum(1 for o in opps if o.stage == "won") / max(sum(1 for o in opps if o.stage in ["won", "lost"]), 1) * 100, 1),
        }
    }


@router.post("", summary="Crear oportunidad")
def create_opportunity(
    payload: OpportunityIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    opp = Opportunity(code=_next_code(db), **payload.model_dump())
    if not opp.owner_id:
        opp.owner_id = current_user.id
    db.add(opp); db.commit(); db.refresh(opp)

    # Auto-add activity
    act = OpportunityActivity(opportunity_id=opp.id, user_id=current_user.id, type="note", content=f"Oportunidad creada en etapa {STAGE_LABELS.get(opp.stage, opp.stage)}")
    db.add(act); db.commit()
    return _opp_out(opp)


@router.patch("/{opp_id}", summary="Actualizar oportunidad")
def update_opportunity(
    opp_id: str,
    payload: OpportunityUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    opp = _scope_opportunity_query(db.query(Opportunity), db, current_user).filter(Opportunity.id == opp_id).first()
    if not opp:
        raise HTTPException(404, "Oportunidad no encontrada")

    old_stage = opp.stage
    new_stage = payload.stage if "stage" in payload.model_fields_set else None

    # Validate stage transition before applying any changes
    if new_stage and new_stage != old_stage:
        allowed = _STAGE_VALID_TRANSITIONS.get(old_stage, set())
        if new_stage not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"Transición de etapa no permitida: '{STAGE_LABELS.get(old_stage, old_stage)}' → '{STAGE_LABELS.get(new_stage, new_stage)}'",
            )

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(opp, k, v)

    # Log stage change after applying it
    if new_stage and new_stage != old_stage:
        act = OpportunityActivity(
            opportunity_id=opp.id, user_id=current_user.id, type="stage_change",
            content=f"Etapa cambiada: {STAGE_LABELS.get(old_stage, old_stage)} → {STAGE_LABELS.get(new_stage, new_stage)}"
        )
        db.add(act)
        # Auto-update probability if not explicitly provided
        if new_stage in STAGE_PROB and not payload.probability:
            opp.probability = STAGE_PROB[new_stage]

    db.commit(); db.refresh(opp)
    return _opp_out(opp)


@router.delete("/{opp_id}", summary="Eliminar oportunidad")
def delete_opportunity(
    opp_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    opp = _scope_opportunity_query(db.query(Opportunity), db, current_user).filter(Opportunity.id == opp_id).first()
    if not opp:
        raise HTTPException(404, "Oportunidad no encontrada")
    db.delete(opp); db.commit()
    return {"ok": True}


@router.get("/{opp_id}/activities", summary="Actividades de una oportunidad")
def get_activities(
    opp_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    acts = db.query(OpportunityActivity).options(
        joinedload(OpportunityActivity.user)
    ).filter(OpportunityActivity.opportunity_id == opp_id).order_by(OpportunityActivity.created_at.desc()).all()
    return [{
        "id": a.id, "type": a.type, "content": a.content,
        "user_name": a.user.full_name if a.user else "Sistema",
        "created_at": str(a.created_at)[:16],
    } for a in acts]


@router.post("/{opp_id}/activities", summary="Añadir actividad")
def add_activity(
    opp_id: str,
    payload: ActivityIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    act = OpportunityActivity(opportunity_id=opp_id, user_id=current_user.id, **payload.model_dump())
    db.add(act); db.commit(); db.refresh(act)
    return {"id": act.id, "message": "Actividad añadida"}

@router.post("/{opp_id}/convert", summary="Convertir oportunidad ganada a proyecto")
def convert_opportunity_to_project(
    opp_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """Crea un proyecto a partir de los datos de la oportunidad y vincula ambos."""
    import uuid as _uuid
    from app.models.project import ProjectStatus, ProjectType

    opp = _scope_opportunity_query(db.query(Opportunity), db, current_user).filter(Opportunity.id == opp_id).first()
    if not opp:
        raise HTTPException(404, "Oportunidad no encontrada")
    if opp.project_id:
        raise HTTPException(400, f"Esta oportunidad ya está vinculada al proyecto {opp.project_id}")

    # Generar código de proyecto
    import re as _re
    max_prj_code = db.query(func.max(Project.code)).scalar()
    if max_prj_code:
        _m = _re.search(r"(\d+)$", max_prj_code)
        next_prj_num = (int(_m.group(1)) + 1) if _m else 1
    else:
        next_prj_num = 1
    code = f"PRJ-{next_prj_num:04d}"

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
        billing_rate=opp.hourly_rate if hasattr(opp, 'hourly_rate') else None,
    )
    db.add(project)

    # Marcar oportunidad como ganada y vincular proyecto
    opp.stage = OpportunityStage.won
    opp.project_id = project.id

    # Registrar actividad
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


# ── Weighted Forecast ─────────────────────────────────────────────────────────

@router.get("/forecast", summary="Previsión de ingresos ponderada por mes")
def get_weighted_forecast(
    months: int = 6,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns expected revenue weighted by win probability, aggregated by expected close month.
    Only includes active opportunities (not won/lost/cancelled).
    """
    from calendar import month_abbr
    from datetime import date as _date, timedelta

    today = _date.today()
    opps = db.query(Opportunity).filter(
        Opportunity.stage.notin_(["won", "lost", "cancelled"]),
    ).all()

    # Build month buckets
    buckets: dict = {}
    for i in range(months):
        month_offset = (today.month - 1 + i) % 12 + 1
        year_offset = today.year + (today.month - 1 + i) // 12
        key = f"{year_offset}-{month_offset:02d}"
        buckets[key] = {
            "month": key,
            "label": f"{month_abbr[month_offset]} {year_offset}",
            "expected_revenue": 0.0,
            "weighted_revenue": 0.0,
            "count": 0,
        }

    unscheduled = {"expected_revenue": 0.0, "weighted_revenue": 0.0, "count": 0}

    for opp in opps:
        weighted = (opp.expected_revenue or 0) * (opp.probability or 0) / 100
        if opp.expected_close_date:
            key = f"{opp.expected_close_date.year}-{opp.expected_close_date.month:02d}"
            if key in buckets:
                buckets[key]["expected_revenue"] += opp.expected_revenue or 0
                buckets[key]["weighted_revenue"] += weighted
                buckets[key]["count"] += 1
            else:
                unscheduled["expected_revenue"] += opp.expected_revenue or 0
                unscheduled["weighted_revenue"] += weighted
                unscheduled["count"] += 1
        else:
            unscheduled["expected_revenue"] += opp.expected_revenue or 0
            unscheduled["weighted_revenue"] += weighted
            unscheduled["count"] += 1

    forecast_list = [
        {**v, "expected_revenue": round(v["expected_revenue"], 2), "weighted_revenue": round(v["weighted_revenue"], 2)}
        for v in buckets.values()
    ]
    total_weighted = sum(f["weighted_revenue"] for f in forecast_list)

    return {
        "forecast": forecast_list,
        "unscheduled": {k: round(v, 2) if isinstance(v, float) else v for k, v in unscheduled.items()},
        "total_weighted_pipeline": round(total_weighted, 2),
    }


# ── Configurable Stage Management ─────────────────────────────────────────────

@router.get("/stages", summary="Listar configuración de etapas del pipeline")
def list_stage_configs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    configs = db.query(PipelineStageConfig).filter(
        PipelineStageConfig.is_active == True
    ).order_by(PipelineStageConfig.order).all()
    return [{
        "id": c.id, "stage_key": c.stage_key, "label": c.label,
        "description": c.description, "color": c.color, "order": c.order,
        "probability_default": c.probability_default,
        "is_terminal": c.is_terminal, "is_won": c.is_won,
    } for c in configs]


@router.post("/stages", summary="Crear etapa personalizada")
def create_stage_config(
    payload: StageConfigIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    existing = db.query(PipelineStageConfig).filter(
        PipelineStageConfig.stage_key == payload.stage_key
    ).first()
    if existing:
        raise HTTPException(400, f"La etapa '{payload.stage_key}' ya existe")
    stage = PipelineStageConfig(**payload.model_dump())
    db.add(stage); db.commit(); db.refresh(stage)
    return {"ok": True, "id": stage.id, "stage_key": stage.stage_key}


@router.patch("/stages/{stage_id}", summary="Actualizar etapa del pipeline")
def update_stage_config(
    stage_id: str,
    payload: StageConfigIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    stage = db.query(PipelineStageConfig).filter(PipelineStageConfig.id == stage_id).first()
    if not stage:
        raise HTTPException(404, "Etapa no encontrada")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(stage, k, v)
    db.commit()
    return {"ok": True, "id": stage.id}


@router.delete("/stages/{stage_id}", summary="Desactivar etapa del pipeline")
def delete_stage_config(
    stage_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    stage = db.query(PipelineStageConfig).filter(PipelineStageConfig.id == stage_id).first()
    if not stage:
        raise HTTPException(404, "Etapa no encontrada")
    stage.is_active = False  # Soft delete
    db.commit()
    return {"ok": True}
