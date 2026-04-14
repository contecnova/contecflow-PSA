from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, select
from typing import Optional
from datetime import date
from pydantic import BaseModel

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager
from app.models.user import User, UserRole
from app.models.pipeline import Risk
from app.services.numbering import next_numbered_code

router = APIRouter()

PROB_SCORE = {"very_low": 0.05, "low": 0.2, "medium": 0.5, "high": 0.7, "very_high": 0.9}
IMPACT_SCORE = {"negligible": 1, "minor": 2, "moderate": 3, "major": 4, "critical": 5}
PROB_LABELS = {"very_low": "Muy baja (<10%)", "low": "Baja (10-30%)", "medium": "Media (30-60%)", "high": "Alta (60-80%)", "very_high": "Muy alta (>80%)"}
IMPACT_LABELS = {"negligible": "Insignificante", "minor": "Menor", "moderate": "Moderado", "major": "Mayor", "critical": "Crítico"}
STATUS_LABELS = {"identified": "Identificado", "analyzing": "Analizando", "mitigating": "Mitigando", "monitoring": "Monitorizando", "closed": "Cerrado", "materialized": "Materializado"}
CATEGORY_LABELS = {"technical": "Técnico", "financial": "Financiero", "schedule": "Planificación", "resource": "Recursos", "external": "Externo", "quality": "Calidad"}


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


def _next_code(project_id: str, db: Session) -> str:
    return next_numbered_code(db, "risk", prefix="RSK", padding=3)


def _risk_score(probability: str, impact: str) -> float:
    return round(PROB_SCORE.get(probability, 0.5) * IMPACT_SCORE.get(impact, 3), 2)


def _risk_level(score: float) -> str:
    if score >= 3.0: return "critical"
    if score >= 2.0: return "high"
    if score >= 1.0: return "medium"
    return "low"


def _risk_out(r: Risk) -> dict:
    score = r.risk_score or _risk_score(r.probability, r.impact)
    return {
        "id": r.id, "code": r.code, "project_id": r.project_id,
        "title": r.title, "description": r.description,
        "category": r.category,
        "category_label": CATEGORY_LABELS.get(r.category, r.category),
        "probability": r.probability,
        "probability_label": PROB_LABELS.get(r.probability, r.probability),
        "impact": r.impact,
        "impact_label": IMPACT_LABELS.get(r.impact, r.impact),
        "risk_score": score,
        "risk_level": _risk_level(score),
        "status": r.status,
        "status_label": STATUS_LABELS.get(r.status, r.status),
        "mitigation_plan": r.mitigation_plan,
        "contingency_plan": r.contingency_plan,
        "response_type": r.response_type,
        "owner_id": r.owner_id,
        "owner_name": r.owner.full_name if r.owner else None,
        "review_date": str(r.review_date) if r.review_date else None,
        "closed_date": str(r.closed_date) if r.closed_date else None,
        "identified_date": str(r.identified_date) if r.identified_date else None,
        "cost_impact_min": r.cost_impact_min,
        "cost_impact_max": r.cost_impact_max,
        "schedule_impact_days": r.schedule_impact_days,
        "notes": r.notes,
    }


@router.get("/all/portfolio", summary="Riesgos de toda la cartera")
def get_portfolio_risks(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    risks = db.query(Risk).options(
        joinedload(Risk.owner),
        joinedload(Risk.project),
    ).filter(Risk.status.notin_(["closed"])).order_by(Risk.risk_score.desc().nullslast()).limit(50).all()

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
    q = db.query(Risk).options(joinedload(Risk.owner)).filter(Risk.project_id == project_id)
    if status:
        q = q.filter(Risk.status == status)
    risks = q.order_by(Risk.risk_score.desc().nullslast()).all()
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
    score = _risk_score(payload.probability, payload.impact)
    risk = Risk(
        project_id=project_id,
        code=_next_code(project_id, db),
        risk_score=score,
        identified_by=current_user.id,
        **payload.model_dump(),
    )
    db.add(risk); db.commit(); db.refresh(risk)
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
    risk = db.query(Risk).filter(Risk.id == risk_id, Risk.project_id == project_id).first()
    if not risk:
        raise HTTPException(404, "Riesgo no encontrado")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(risk, k, v)
    risk.risk_score = _risk_score(risk.probability, risk.impact)
    db.commit(); db.refresh(risk)
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
    risk = db.query(Risk).filter(Risk.id == risk_id, Risk.project_id == project_id).first()
    if not risk:
        raise HTTPException(404, "Riesgo no encontrado")
    db.delete(risk); db.commit()
    return {"ok": True}
