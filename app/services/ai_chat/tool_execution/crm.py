"""Herramientas de CRM/pipeline y clientes."""
from __future__ import annotations

from sqlalchemy import or_

from app.models.clients import Client
from app.models.pipeline import Opportunity
from app.models.project import Project


def _get_pipeline(tool_input, db, user, now, is_financial_role):
    q = db.query(Opportunity)
    stage = tool_input.get("stage", "")
    if stage and stage != "all":
        q = q.filter(Opportunity.stage == stage)
    else:
        q = q.filter(Opportunity.stage.notin_(["won","lost"]))
    opps = q.order_by(Opportunity.expected_close_date.asc().nullslast()).limit(tool_input.get("limit", 20)).all()
    weighted_total = sum((o.expected_revenue or 0) * (o.probability or 0) / 100 for o in opps)
    return {
        "total_opportunities": len(opps),
        "weighted_pipeline": round(weighted_total, 2),
        "opportunities": [{
            "id": o.id, "code": o.code, "name": o.name,
            "client": o.client_name, "stage": str(o.stage),
            "probability": o.probability,
            "expected_revenue": o.expected_revenue,
            "weighted_value": round((o.expected_revenue or 0) * (o.probability or 0) / 100, 2),
            "expected_close_date": str(o.expected_close_date) if o.expected_close_date else None,
        } for o in opps]
    }


def _get_clients(tool_input, db, user, now, is_financial_role):
    q = db.query(Client)
    status = tool_input.get("status", "")
    if status and status != "all": q = q.filter(Client.status == status)
    if tool_input.get("query"):
        term = f"%{tool_input['query']}%"
        q = q.filter(or_(Client.name.ilike(term)))
    clients = q.order_by(Client.name).limit(tool_input.get("limit", 20)).all()
    result = []
    for c in clients:
        projects = db.query(Project).filter(Project.client_id == c.id).all()
        total_revenue = sum(p.contract_amount or 0 for p in projects)
        result.append({
            "id": c.id, "name": c.name,
            "industry": str(c.industry) if c.industry else None,
            "status": str(c.status) if c.status else None,
            "projects_count": len(projects),
            "total_contract_value": round(total_revenue, 2),
            "email": c.contact_email, "phone": c.contact_phone,
        })
    return {"clients": result}


HANDLERS = {
    "get_pipeline": _get_pipeline,
    "get_clients": _get_clients,
}
