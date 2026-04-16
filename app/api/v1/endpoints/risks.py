from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date
from pydantic import BaseModel

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager
from app.models.user import User, UserRole
from app.services import risk_service
from app.services.risk_scoring import risk_level, risk_score
from app.services.risk_service import (
    PROB_LABELS, IMPACT_LABELS, STATUS_LABELS, CATEGORY_LABELS, serialize_risk as _risk_out,
)

router = APIRouter()

# Label constants delegated to risk_service (see imports above)


class RiskIn(BaseModel):
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    probability: str
    impact: str
    status: str = "identified"
    mitigation_plan: Optional[str] = None
    contingency_plan: Optional[str] = None
    response_type: Optional[str] = None
    owner_id: Optional[str] = None
    review_date: Optional[date] = None
    cost_impact_min: Optional[float] = None
    cost_impact_max: Optional[float] = None
    schedule_impact_days: Optional[int] = None
    notes: Optional[str] = None

class RiskUpdate(RiskIn):
    title: Optional[str] = None
    probability: Optional[str] = None
    impact: Optional[str] = None
    closed_date: Optional[date] = None


# _risk_out delegated to risk_service.serialize_risk (see imports above)


@router.get("/all/portfolio", summary="Riesgos de toda la cartera")
def get_portfolio_risks(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    risks = risk_service.get_portfolio_risks(db)
    result = []
    for r in risks:
        d = _risk_out(r)
        d["project_name"] = r.project.name if r.project else "—"
        d["project_code"] = r.project.code if r.project else "—"
        result.append(d)
    return result



@router.get("/{project_id}", summary="Registro de riesgos de un proyecto")
def get_risks(
    project_id: str,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    risks = risk_service.get_risks_by_project(db, project_id, status=status)
    result = [_risk_out(r) for r in risks]

    # Summary
    by_level = {}
    for r in result:
        lvl = r["risk_level"]
        by_level[lvl] = by_level.get(lvl, 0) + 1

    return {
        "risks": result,
        "summary": {
            "total": len(result),
            "open": sum(1 for r in result if r["status"] not in ["closed", "materialized"]),
            "by_level": by_level,
            "critical_count": by_level.get("critical", 0),
            "high_count": by_level.get("high", 0),
        }
    }


@router.post("/{project_id}", summary="Crear riesgo")
def create_risk(
    project_id: str,
    payload: RiskIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.admin, UserRole.pm]:
        raise HTTPException(403, "Acceso denegado")
    risk = risk_service.create_risk(
        db,
        project_id=project_id,
        identified_by=current_user.id,
        **payload.model_dump(),
    )
    return _risk_out(risk)


@router.patch("/{project_id}/{risk_id}", summary="Actualizar riesgo")
def update_risk(
    project_id: str,
    risk_id: str,
    payload: RiskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.admin, UserRole.pm]:
        raise HTTPException(403, "Acceso denegado")
    risk = risk_service.get_risk(db, risk_id, project_id)
    if not risk:
        raise HTTPException(404, "Riesgo no encontrado")
    risk = risk_service.update_risk(db, risk, payload.model_dump(exclude_unset=True))
    return _risk_out(risk)


@router.delete("/{project_id}/{risk_id}", summary="Eliminar riesgo")
def delete_risk(
    project_id: str,
    risk_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [UserRole.admin, UserRole.pm]:
        raise HTTPException(403, "Acceso denegado")
    risk = risk_service.get_risk(db, risk_id, project_id)
    if not risk:
        raise HTTPException(404, "Riesgo no encontrado")
    risk_service.delete_risk(db, risk)
    return {"ok": True}
