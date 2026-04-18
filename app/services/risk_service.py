from sqlalchemy.orm import Session, joinedload
from typing import Optional
from datetime import date

from app.models.pipeline import Risk
from app.services.numbering import next_numbered_code
from app.services.risk_scoring import risk_score
from app.services.risk_scoring import risk_score, risk_level


def get_portfolio_risks(db: Session) -> list:
    return (
        db.query(Risk)
        .options(joinedload(Risk.owner), joinedload(Risk.project))
        .filter(Risk.status.notin_(["closed"]))
        .order_by(Risk.risk_score.desc().nullslast())
        .limit(50)
        .all()
    )


def get_risks_by_project(db: Session, project_id: str, status: Optional[str] = None) -> list:
    q = db.query(Risk).options(joinedload(Risk.owner)).filter(Risk.project_id == project_id)
    if status:
        q = q.filter(Risk.status == status)
    return q.order_by(Risk.risk_score.desc().nullslast()).all()


def create_risk(db: Session, project_id: str, identified_by: str, **fields) -> Risk:
    score = risk_score(fields["probability"], fields["impact"])
    code = next_numbered_code(db, "risk", prefix="RSK", padding=3)
    risk = Risk(
        project_id=project_id,
        code=code,
        risk_score=score,
        identified_by=identified_by,
        **fields,
    )
    db.add(risk)
    db.commit()
    db.refresh(risk)
    from app.core.events import emit, EventType
    emit(db, EventType.RISK_CREATED,
         {"risk_id": risk.id, "code": risk.code, "title": risk.title,
          "project_id": project_id, "risk_score": score},
         resource_type="risk", resource_id=risk.id, project_id=project_id)
    return risk


def get_risk(db: Session, risk_id: str, project_id: str) -> Optional[Risk]:
    return (
        db.query(Risk)
        .filter(Risk.id == risk_id, Risk.project_id == project_id)
        .first()
    )


def update_risk(db: Session, risk: Risk, updates: dict) -> Risk:
    allowed_fields = {
        "title", "description", "category", "probability", "impact", "status", "mitigation_plan",
        "contingency_plan", "response_type", "owner_id", "review_date", "cost_impact_min",
        "cost_impact_max", "schedule_impact_days", "notes", "closed_date"
    }
    allowed_status_transitions = {
        "identified":    ["analyzing", "mitigating", "monitoring", "closed", "materialized"],
        "analyzing":     ["mitigating", "monitoring", "closed", "materialized"],
        "mitigating":    ["monitoring", "closed", "materialized"],
        "monitoring":    ["closed", "materialized"],
        "closed":        [],
        "materialized":  [],
    }
    old_status = str(risk.status)
    for k, v in updates.items():
        if k not in allowed_fields:
            continue
        if k == "status":
            new_status = str(v)
            if new_status == old_status:
                continue
            if new_status not in allowed_status_transitions.get(old_status, []):
                raise ValueError(f"Transición de estado no permitida: {old_status} → {new_status}")
        setattr(risk, k, v)
    risk.risk_score = risk_score(risk.probability, risk.impact)
    db.commit()
    db.refresh(risk)
    new_status = str(risk.status)
    from app.core.events import emit, EventType
    event_type = EventType.RISK_MITIGATED if new_status in ("mitigating", "monitoring", "closed") else EventType.RISK_UPDATED
    emit(db, event_type,
         {"risk_id": risk.id, "code": risk.code, "title": risk.title,
          "status": new_status, "risk_score": risk.risk_score},
         resource_type="risk", resource_id=risk.id, project_id=risk.project_id)
    return risk


def delete_risk(db: Session, risk: Risk) -> None:
    risk_id, project_id, code = risk.id, risk.project_id, risk.code
    db.delete(risk)
    db.commit()
    from app.core.events import emit, EventType
    emit(db, EventType.RISK_CLOSED,
         {"risk_id": risk_id, "code": code, "project_id": project_id},
         resource_type="risk", resource_id=risk_id, project_id=project_id)


# ── Label constants ────────────────────────────────────────────────────────────

PROB_LABELS = {"very_low": "Muy baja (<10%)", "low": "Baja (10-30%)", "medium": "Media (30-60%)", "high": "Alta (60-80%)", "very_high": "Muy alta (>80%)"}
IMPACT_LABELS = {"negligible": "Insignificante", "minor": "Menor", "moderate": "Moderado", "major": "Mayor", "critical": "Crítico"}
STATUS_LABELS = {"identified": "Identificado", "analyzing": "Analizando", "mitigating": "Mitigando", "monitoring": "Monitorizando", "closed": "Cerrado", "materialized": "Materializado"}
CATEGORY_LABELS = {"technical": "Técnico", "financial": "Financiero", "schedule": "Planificación", "resource": "Recursos", "external": "Externo", "quality": "Calidad"}


# ── Serialization helper ──────────────────────────────────────────────────

def serialize_risk(r) -> dict:
    score = r.risk_score or risk_score(r.probability, r.impact)
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
        "risk_level": risk_level(score),
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
