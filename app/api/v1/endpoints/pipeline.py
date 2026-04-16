from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date
from pydantic import BaseModel

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager, require_admin
from app.models.user import User
from app.services import pipeline_service
from app.services.pipeline_service import STAGE_LABELS, STAGE_PROB, serialize_opportunity as _opp_out

router = APIRouter()

STAGE_ORDER = ["lead", "qualification", "proposal", "negotiation", "won", "lost", "cancelled"]


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


# _opp_out delegated to pipeline_service.serialize_opportunity (see imports above)


@router.get("", summary="Listar oportunidades")
def list_opportunities(
    stage: Optional[str] = None,
    owner_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    opps = pipeline_service.get_opportunities(db, current_user, stage=stage, owner_id=owner_id)
    return [_opp_out(o) for o in opps]


@router.get("/pipeline", summary="Vista kanban del pipeline")
def get_pipeline(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    opps = pipeline_service.get_pipeline_opps(db, current_user)
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
    opp = pipeline_service.create_opportunity(db, current_user, payload.model_dump())
    return _opp_out(opp)


@router.patch("/{opp_id}", summary="Actualizar oportunidad")
def update_opportunity(
    opp_id: str,
    payload: OpportunityUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    new_stage = payload.stage if "stage" in payload.model_fields_set else None
    opp = pipeline_service.update_opportunity(
        db, current_user, opp_id,
        data=payload.model_dump(exclude_unset=True),
        new_stage=new_stage,
        explicit_probability=payload.probability,
    )
    return _opp_out(opp)


@router.delete("/{opp_id}", summary="Eliminar oportunidad")
def delete_opportunity(
    opp_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return pipeline_service.delete_opportunity(db, current_user, opp_id)


@router.get("/{opp_id}/activities", summary="Actividades de una oportunidad")
def get_activities(
    opp_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    acts = pipeline_service.list_activities(db, opp_id)
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
    act = pipeline_service.add_activity(db, current_user, opp_id, payload.type, payload.content)
    return {"id": act.id, "message": "Actividad añadida"}

@router.post("/{opp_id}/convert", summary="Convertir oportunidad ganada a proyecto")
def convert_opportunity_to_project(
    opp_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """Crea un proyecto a partir de los datos de la oportunidad y vincula ambos."""
    return pipeline_service.convert_opportunity_to_project(db, current_user, opp_id)


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
    opps = pipeline_service.get_active_opportunities_for_forecast(db)

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
    configs = pipeline_service.list_stage_configs(db)
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
    stage = pipeline_service.create_stage_config(db, payload.model_dump())
    return {"ok": True, "id": stage.id, "stage_key": stage.stage_key}


@router.patch("/stages/{stage_id}", summary="Actualizar etapa del pipeline")
def update_stage_config(
    stage_id: str,
    payload: StageConfigIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    stage = pipeline_service.update_stage_config(db, stage_id, payload.model_dump(exclude_unset=True))
    return {"ok": True, "id": stage.id}


@router.delete("/stages/{stage_id}", summary="Desactivar etapa del pipeline")
def delete_stage_config(
    stage_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    pipeline_service.delete_stage_config(db, stage_id)
    return {"ok": True}
