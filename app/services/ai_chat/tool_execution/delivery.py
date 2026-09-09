"""Herramientas de entrega: hitos, CRs, contratos, entregables y sprints."""
from __future__ import annotations

from sqlalchemy import or_

from app.models.financial import ProjectMilestone
from app.models.pipeline import Contract
from app.models.project import Project
from app.models.resources import ChangeRequest, Deliverable
from app.models.sprints import Sprint


def _get_milestones(tool_input, db, user, now, is_financial_role):
    q = db.query(ProjectMilestone)
    pid = tool_input.get("project_id", "")
    if pid:
        p = db.query(Project).filter(
            or_(Project.id == pid, Project.name.ilike(f"%{pid}%"), Project.code.ilike(f"%{pid}%"))
        ).first()
        if p: q = q.filter(ProjectMilestone.project_id == p.id)
    if tool_input.get("only_pending"): q = q.filter(ProjectMilestone.is_completed == False)
    milestones = q.order_by(ProjectMilestone.due_date.asc().nullslast()).limit(30).all()
    proj_ids = {m.project_id for m in milestones}
    proj_map = {p.id: p for p in db.query(Project).filter(Project.id.in_(proj_ids)).all()}
    return {"milestones": [{
        "id": m.id, "name": m.name,
        "project_name": proj_map[m.project_id].name if m.project_id in proj_map else "?",
        "due_date": str(m.due_date) if m.due_date else None,
        "is_completed": m.is_completed, "billing_status": m.billing_status,
        "billing_amount": m.billing_amount, "is_billed": m.is_billed,
    } for m in milestones]}


def _get_change_requests(tool_input, db, user, now, is_financial_role):
    q = db.query(ChangeRequest)
    pid = tool_input.get("project_id", "")
    if pid:
        p = db.query(Project).filter(
            or_(Project.id == pid, Project.name.ilike(f"%{pid}%"), Project.code.ilike(f"%{pid}%"))
        ).first()
        if p: q = q.filter(ChangeRequest.project_id == p.id)
    status = tool_input.get("status", "")
    if status and status != "all": q = q.filter(ChangeRequest.status == status)
    else: q = q.filter(ChangeRequest.status.notin_(["implemented","rejected"]))
    crs = q.order_by(ChangeRequest.created_at.desc()).limit(30).all()
    proj_ids = {c.project_id for c in crs}
    proj_map = {p.id: p for p in db.query(Project).filter(Project.id.in_(proj_ids)).all()}
    return {"change_requests": [{
        "id": c.id, "code": getattr(c, "code", ""), "title": c.title,
        "status": c.status, "impact": c.impact,
        "cost_impact": c.cost_impact, "schedule_impact_days": c.schedule_impact_days,
        "project_name": proj_map[c.project_id].name if c.project_id in proj_map else "?",
    } for c in crs]}


def _get_contracts(tool_input, db, user, now, is_financial_role):
    q = db.query(Contract)
    if tool_input.get("status"): q = q.filter(Contract.status == tool_input["status"])
    contracts = q.order_by(Contract.end_date.asc().nullslast()).limit(tool_input.get("limit", 20)).all()
    return {"contracts": [{
        "id": c.id,
        "title": getattr(c, "title", None) or getattr(c, "name", None) or getattr(c, "reference", None),
        "status": getattr(c, "status", None),
        "value": getattr(c, "value", None) or getattr(c, "total_value", None),
        "start_date": str(c.start_date) if getattr(c, "start_date", None) else None,
        "end_date": str(c.end_date) if getattr(c, "end_date", None) else None,
        "client": getattr(c, "client_name", None),
    } for c in contracts]}


def _get_deliverables(tool_input, db, user, now, is_financial_role):
    q = db.query(Deliverable)
    pid = tool_input.get("project_id", "")
    if pid:
        p = db.query(Project).filter(
            or_(Project.id == pid, Project.name.ilike(f"%{pid}%"), Project.code.ilike(f"%{pid}%"))
        ).first()
        if p: q = q.filter(Deliverable.project_id == p.id)
    status = tool_input.get("status", "")
    if status and status != "all": q = q.filter(Deliverable.status == status)
    else: q = q.filter(Deliverable.status.notin_(["done"]))
    deliverables = q.order_by(Deliverable.planned_date.asc().nullslast()).limit(30).all()
    proj_ids = {d.project_id for d in deliverables if d.project_id}
    proj_map = {p.id: p for p in db.query(Project).filter(Project.id.in_(proj_ids)).all()}
    return {"deliverables": [{
        "id": d.id, "title": d.title, "status": str(d.status),
        "due_date": str(d.due_date) if getattr(d, "due_date", None) else None,
        "project_name": proj_map[d.project_id].name if d.project_id and d.project_id in proj_map else None,
    } for d in deliverables]}


def _get_sprints(tool_input, db, user, now, is_financial_role):
    q = db.query(Sprint)
    pid = tool_input.get("project_id", "")
    if pid:
        p = db.query(Project).filter(
            or_(Project.id == pid, Project.name.ilike(f"%{pid}%"), Project.code.ilike(f"%{pid}%"))
        ).first()
        if p: q = q.filter(Sprint.project_id == p.id)
    if tool_input.get("only_active"):
        q = q.filter(Sprint.status == "active")
    sprints = q.order_by(Sprint.start_date.desc().nullslast()).limit(20).all()
    proj_ids = {s.project_id for s in sprints}
    proj_map = {p.id: p for p in db.query(Project).filter(Project.id.in_(proj_ids)).all()}
    return {"sprints": [{
        "id": s.id, "name": s.name,
        "project_name": proj_map[s.project_id].name if s.project_id in proj_map else "?",
        "status": str(s.status) if s.status else None,
        "start_date": str(s.start_date) if getattr(s, "start_date", None) else None,
        "end_date": str(s.end_date) if getattr(s, "end_date", None) else None,
        "velocity": getattr(s, "velocity", None),
        "completed_points": getattr(s, "completed_points", None),
        "total_points": getattr(s, "total_points", None),
    } for s in sprints]}


HANDLERS = {
    "get_milestones": _get_milestones,
    "get_change_requests": _get_change_requests,
    "get_contracts": _get_contracts,
    "get_deliverables": _get_deliverables,
    "get_sprints": _get_sprints,
}
