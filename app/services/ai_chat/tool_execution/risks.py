"""Herramientas de riesgos: consulta por proyecto, global y creación."""
from __future__ import annotations

import uuid as _uuid

from sqlalchemy import func, or_

from app.models.pipeline import Risk
from app.models.project import Project


def _get_project_risks(tool_input, db, user, now, is_financial_role):
    pid = tool_input.get("project_id", "")
    p = db.query(Project).filter(
        or_(Project.id == pid, Project.name.ilike(f"%{pid}%"), Project.code.ilike(f"%{pid}%"))
    ).first()
    if not p: return {"error": f"Proyecto no encontrado: {pid}"}
    q = db.query(Risk).filter(Risk.project_id == p.id)
    status_filter = tool_input.get("status", "")
    if status_filter and status_filter != "all":
        q = q.filter(Risk.status == status_filter)
    elif not status_filter:
        q = q.filter(Risk.status.notin_(["closed"]))
    risks = q.order_by(Risk.risk_score.desc().nullslast()).all()
    return {
        "project": {"id": p.id, "code": p.code, "name": p.name},
        "risks": [{
            "id": r.id, "code": r.code, "title": r.title, "description": r.description,
            "category": r.category, "probability": str(r.probability),
            "impact": str(r.impact), "risk_score": r.risk_score,
            "status": str(r.status), "mitigation_plan": r.mitigation_plan,
            "contingency_plan": r.contingency_plan,
            "cost_impact_min": r.cost_impact_min, "cost_impact_max": r.cost_impact_max,
            "schedule_impact_days": r.schedule_impact_days,
        } for r in risks]
    }


def _get_all_risks(tool_input, db, user, now, is_financial_role):
    q = db.query(Risk).join(Project, Risk.project_id == Project.id)
    status_filter = tool_input.get("status", "")
    if status_filter and status_filter != "all":
        q = q.filter(Risk.status == status_filter)
    else:
        q = q.filter(Risk.status.notin_(["closed"]))
    if tool_input.get("impact"):
        q = q.filter(Risk.impact == tool_input["impact"])
    if tool_input.get("probability"):
        q = q.filter(Risk.probability == tool_input["probability"])
    risks = q.order_by(Risk.risk_score.desc().nullslast()).limit(tool_input.get("limit", 50)).all()
    proj_ids = {r.project_id for r in risks}
    proj_map = {p.id: p for p in db.query(Project).filter(Project.id.in_(proj_ids)).all()}
    return {
        "total_risks": len(risks),
        "risks": [{
            "id": r.id, "code": r.code, "title": r.title,
            "project_id": r.project_id,
            "project_name": proj_map[r.project_id].name if r.project_id in proj_map else "?",
            "project_code": proj_map[r.project_id].code if r.project_id in proj_map else "?",
            "category": r.category, "probability": str(r.probability),
            "impact": str(r.impact), "risk_score": r.risk_score,
            "status": str(r.status), "mitigation_plan": r.mitigation_plan,
            "cost_impact_min": r.cost_impact_min, "cost_impact_max": r.cost_impact_max,
            "schedule_impact_days": r.schedule_impact_days,
        } for r in risks]
    }


def _create_risk(tool_input, db, user, now, is_financial_role):
    pid = tool_input.get("project_id", "")
    p = db.query(Project).filter(
        or_(Project.id == pid, Project.name.ilike(f"%{pid}%"), Project.code.ilike(f"%{pid}%"))
    ).first()
    if not p: return {"error": "Proyecto no encontrado"}
    count = db.query(func.count(Risk.id)).filter(Risk.project_id == p.id).scalar() or 0
    code = f"RSK-{count + 1:03d}"
    _prob_score = {"very_low": 0.05, "low": 0.2, "medium": 0.45, "high": 0.7, "very_high": 0.9}
    _imp_score  = {"negligible": 0.05, "minor": 0.1, "moderate": 0.3, "major": 0.6, "critical": 0.9}
    prob = tool_input.get("probability", "medium")
    imp  = tool_input.get("impact", "moderate")
    score = _prob_score.get(prob, 0.45) * _imp_score.get(imp, 0.3) * 100
    risk = Risk(
        id=str(_uuid.uuid4()), code=code, project_id=p.id,
        title=tool_input["title"],
        description=tool_input.get("description"),
        category=tool_input.get("category"),
        probability=prob, impact=imp, risk_score=round(score, 1),
        mitigation_plan=tool_input.get("mitigation_plan"),
        identified_by=user.id,
    )
    db.add(risk); db.flush()
    return {"ok": True, "risk_id": risk.id, "code": code, "risk_score": risk.risk_score,
            "project": p.name}


HANDLERS = {
    "get_project_risks": _get_project_risks,
    "get_all_risks": _get_all_risks,
    "create_risk": _create_risk,
}
