"""Herramientas de OKRs."""
from __future__ import annotations

from app.models.okrs import Objective, KeyResult


def _get_okrs(tool_input, db, user, now, is_financial_role):
    q = db.query(Objective)
    status = tool_input.get("status", "")
    if status and status != "all": q = q.filter(Objective.status == status)
    else: q = q.filter(Objective.status.in_(["draft","active"]))
    year = tool_input.get("year") or now.year
    q = q.filter(Objective.year == year)
    objectives = q.order_by(Objective.progress.desc()).limit(20).all()
    result = []
    for obj in objectives:
        krs = db.query(KeyResult).filter(KeyResult.objective_id == obj.id).all()
        result.append({
            "id": obj.id, "title": obj.title, "status": str(obj.status),
            "period": str(obj.period), "year": obj.year, "progress": obj.progress,
            "key_results": [{
                "title": kr.title, "progress": kr.progress,
                "current_value": kr.current_value, "target_value": kr.target_value,
                "unit": kr.unit,
            } for kr in krs]
        })
    return {"objectives": result}


HANDLERS = {
    "get_okrs": _get_okrs,
}
