"""Herramientas de proyectos: estado, búsqueda, dashboard, presupuesto."""
from __future__ import annotations

from sqlalchemy import func, or_

from app.models.imputation import Imputation
from app.models.pipeline import Risk
from app.models.project import Project
from app.models.task import Task
from app.services.ai_chat.context_service import build_tenant_context


def _get_project_status(tool_input, db, user, now, is_financial_role):
    pid = tool_input.get("project_id", "")
    p = db.query(Project).filter(
        or_(Project.id == pid, Project.name.ilike(f"%{pid}%"), Project.code.ilike(f"%{pid}%"))
    ).first()
    if not p: return {"error": f"Proyecto no encontrado: {pid}"}
    tasks = db.query(Task).filter(Task.project_id == p.id).all()
    done = sum(1 for t in tasks if t.status == "done")
    overdue_count = sum(1 for t in tasks if t.status != "done" and t.due_date and t.due_date < now.date())
    hours = db.query(func.sum(Imputation.hours)).filter(Imputation.project_id == p.id).scalar() or 0
    risks_count = db.query(func.count(Risk.id)).filter(
        Risk.project_id == p.id, Risk.status.notin_(["closed"])
    ).scalar() or 0
    return {
        "id": p.id, "code": p.code, "name": p.name, "status": p.status,
        "risk_level": str(p.risk_level), "client": p.client_name,
        "budget_amount": p.budget_amount, "contract_amount": p.contract_amount,
        "budget_hours": p.budget_hours, "hours_logged": round(hours, 1),
        "tasks_total": len(tasks), "tasks_done": done, "tasks_overdue": overdue_count,
        "active_risks": risks_count,
        "start_date": str(p.start_date) if p.start_date else None,
        "end_date_planned": str(p.end_date_planned) if p.end_date_planned else None,
    }


def _search_projects(tool_input, db, user, now, is_financial_role):
    q = db.query(Project)
    if tool_input.get("query"):
        term = f"%{tool_input['query']}%"
        q = q.filter(or_(Project.name.ilike(term), Project.client_name.ilike(term),
                         Project.code.ilike(term)))
    status = tool_input.get("status")
    if status and status != "all":
        q = q.filter(Project.status == status)
    if tool_input.get("risk_level"):
        q = q.filter(Project.risk_level == tool_input["risk_level"])
    projects = q.order_by(Project.status).limit(30).all()
    return {"projects": [{"id": p.id, "code": p.code, "name": p.name,
                          "status": p.status, "risk_level": str(p.risk_level),
                          "client": p.client_name, "budget": p.budget_amount,
                          "start_date": str(p.start_date) if p.start_date else None,
                          "end_date_planned": str(p.end_date_planned) if p.end_date_planned else None,
                          } for p in projects]}


def _get_dashboard_summary(tool_input, db, user, now, is_financial_role):
    ctx = build_tenant_context(db, user)
    return {"ok": True, "data": ctx}


def _get_budget_status(tool_input, db, user, now, is_financial_role):
    pid = tool_input.get("project_id", "")
    if pid:
        projects = db.query(Project).filter(
            or_(Project.id == pid, Project.name.ilike(f"%{pid}%"), Project.code.ilike(f"%{pid}%"))
        ).limit(5).all()
    else:
        projects = db.query(Project).filter(Project.status.in_(["active","planning"])).limit(30).all()
    result = []
    project_ids = [p.id for p in projects]
    hours_by_project = {
        pid: hrs for pid, hrs in
        db.query(Imputation.project_id, func.sum(Imputation.hours))
          .filter(Imputation.project_id.in_(project_ids))
          .group_by(Imputation.project_id).all()
    }
    from app.services.gastos_avanzados import totales_por_proyecto
    expenses_by_project = totales_por_proyecto(db, project_ids)
    for p in projects:
        hours = hours_by_project.get(p.id) or 0
        expenses_total = expenses_by_project.get(p.id) or 0
        budget_pct = round(hours / p.budget_hours * 100, 1) if p.budget_hours else None
        result.append({
            "id": p.id, "code": p.code, "name": p.name, "client": p.client_name,
            "budget_hours": p.budget_hours, "hours_logged": round(hours, 1),
            "budget_hours_pct": budget_pct,
            "budget_amount": p.budget_amount, "contract_amount": p.contract_amount,
            "expenses_approved": round(expenses_total, 2),
            "status": p.status,
        })
    return {"budget_status": result}


def _update_project_status(tool_input, db, user, now, is_financial_role):
    pid = tool_input.get("project_id", "")
    p = db.query(Project).filter(
        or_(Project.id == pid, Project.name.ilike(f"%{pid}%"), Project.code.ilike(f"%{pid}%"))
    ).first()
    if not p: return {"error": "Proyecto no encontrado"}
    if tool_input.get("status"): p.status = tool_input["status"]
    if tool_input.get("risk_level"): p.risk_level = tool_input["risk_level"]
    db.flush()
    return {"ok": True, "project_id": p.id, "name": p.name,
            "status": str(p.status), "risk_level": str(p.risk_level)}


HANDLERS = {
    "get_project_status": _get_project_status,
    "search_projects": _search_projects,
    "get_dashboard_summary": _get_dashboard_summary,
    "get_budget_status": _get_budget_status,
    "update_project_status": _update_project_status,
}
