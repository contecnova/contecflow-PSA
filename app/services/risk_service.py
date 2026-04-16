from sqlalchemy.orm import Session, joinedload
from typing import Optional
from datetime import date

from app.models.pipeline import Risk
from app.services.numbering import next_numbered_code
from app.services.risk_scoring import risk_score


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
    return risk


def get_risk(db: Session, risk_id: str, project_id: str) -> Optional[Risk]:
    return (
        db.query(Risk)
        .filter(Risk.id == risk_id, Risk.project_id == project_id)
        .first()
    )


def update_risk(db: Session, risk: Risk, updates: dict) -> Risk:
    for k, v in updates.items():
        setattr(risk, k, v)
    risk.risk_score = risk_score(risk.probability, risk.impact)
    db.commit()
    db.refresh(risk)
    return risk


def delete_risk(db: Session, risk: Risk) -> None:
    db.delete(risk)
    db.commit()
