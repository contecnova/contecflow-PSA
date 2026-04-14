from sqlalchemy.orm import Session, joinedload

from app.models.resources import UserSkill
from app.models.user import User


def run_skills_report(db: Session, filters: dict, org_id=None) -> dict:
    skills_q = db.query(UserSkill).options(
        joinedload(UserSkill.user), joinedload(UserSkill.skill)
    )
    if org_id:
        skills_user_ids = [
            r.id for r in db.query(User.id).filter(User.organization_id == org_id).all()
        ]
        skills_q = skills_q.filter(UserSkill.user_id.in_(skills_user_ids))
    skills = skills_q.all()
    rows = [
        {
            "user_name": s.user.full_name if s.user else "—",
            "skill_name": s.skill.name if s.skill else "—",
            "skill_category": s.skill.category if s.skill else "—",
            "level": s.level,
            "years_experience": s.years_experience,
            "is_primary": s.is_primary,
        }
        for s in skills
    ]
    return {
        "rows": rows,
        "totals": {
            "users": len(set(r["user_name"] for r in rows)),
            "skills": len(rows),
        },
    }


def run_pipeline_report(db: Session, filters: dict, org_id=None) -> dict:
    from app.models.pipeline import Opportunity

    opps_q = db.query(Opportunity)
    if org_id:
        pipeline_user_ids = [
            r.id for r in db.query(User.id).filter(User.organization_id == org_id).all()
        ]
        opps_q = opps_q.filter(Opportunity.owner_id.in_(pipeline_user_ids))
    opps = opps_q.all()
    rows = [
        {
            "name": o.name,
            "client_name": o.client_name or "—",
            "stage": o.stage,
            "amount": o.expected_revenue or 0,
            "probability_pct": o.probability or 0,
            "weighted_amount": round(
                (o.expected_revenue or 0) * (o.probability or 0) / 100,
                0,
            ),
            "expected_close": str(o.expected_close_date) if o.expected_close_date else None,
            "assigned_to": o.owner.full_name if o.owner else "—",
        }
        for o in opps
    ]
    by_stage = {}
    for r in rows:
        stage = r["stage"]
        if stage not in by_stage:
            by_stage[stage] = {"stage": stage, "count": 0, "amount": 0, "weighted": 0}
        by_stage[stage]["count"] += 1
        by_stage[stage]["amount"] += r["amount"]
        by_stage[stage]["weighted"] += r["weighted_amount"]
    return {
        "rows": rows,
        "by_stage": list(by_stage.values()),
        "totals": {
            "total_amount": round(sum(r["amount"] for r in rows), 2),
            "weighted_amount": round(sum(r["weighted_amount"] for r in rows), 2),
            "count": len(rows),
        },
    }
