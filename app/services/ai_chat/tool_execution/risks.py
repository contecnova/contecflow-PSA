"""Herramientas de riesgos: consulta por proyecto, global y creación."""
from __future__ import annotations

from app.models.pipeline import Risk
from app.models.project import Project
from app.services.ai_chat.tool_execution.politica import buscar_proyecto, proyectos_visibles


def _get_project_risks(tool_input, db, user, now, is_financial_role):
    pid = tool_input.get("project_id", "")
    p = buscar_proyecto(db, user, pid)
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
    q = db.query(Risk).join(Project, Risk.project_id == Project.id).filter(
        Risk.project_id.in_(proyectos_visibles(db, user)))
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
    # Segunda auditoría 2026-11: como `POST /risks/{project_id}` (admin o PM, en
    # un proyecto que ve) y por el mismo servicio (`risk_service.create_risk`).
    from app.schemas.risks import RiskIn
    from app.services import risk_service
    p = buscar_proyecto(db, user, tool_input.get("project_id", ""))
    if not p: return {"error": "Proyecto no encontrado"}
    datos = RiskIn(**{
        "probability": "medium", "impact": "moderate",
        **{k: v for k, v in tool_input.items() if k in RiskIn.model_fields and k != "project_id"},
    })
    risk = risk_service.create_risk(db, project_id=p.id, identified_by=user.id, **datos.model_dump())
    return {"ok": True, "risk_id": risk.id, "code": risk.code, "risk_score": risk.risk_score,
            "project": p.name}


HANDLERS = {
    "get_project_risks": _get_project_risks,
    "get_all_risks": _get_all_risks,
    "create_risk": _create_risk,
}
