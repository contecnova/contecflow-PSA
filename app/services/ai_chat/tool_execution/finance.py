"""Herramientas financieras: gastos, facturas, rentabilidad y aprobaciones."""
from __future__ import annotations

from sqlalchemy import func, or_

from app.models.billing_reports import Invoice, ApprovalRequest
from app.models.expenses import Expense
from app.models.imputation import Imputation
from app.models.project import Project


def _get_expenses(tool_input, db, user, now, is_financial_role):
    q = db.query(Expense)
    pid = tool_input.get("project_id", "")
    if pid:
        p = db.query(Project).filter(
            or_(Project.id == pid, Project.name.ilike(f"%{pid}%"), Project.code.ilike(f"%{pid}%"))
        ).first()
        if p: q = q.filter(Expense.project_id == p.id)
    status = tool_input.get("status", "")
    if status and status != "all": q = q.filter(Expense.status == status)
    expenses = q.order_by(Expense.expense_date.desc()).limit(tool_input.get("limit", 30)).all()
    proj_ids = {e.project_id for e in expenses if e.project_id}
    proj_map = {p.id: p for p in db.query(Project).filter(Project.id.in_(proj_ids)).all()}
    total = sum(e.amount or 0 for e in expenses)
    return {
        "total_amount": round(total, 2),
        "expenses": [{
            "id": e.id, "description": e.description,
            "amount": e.amount, "category": str(e.category) if e.category else None,
            "status": str(e.status) if e.status else None,
            "date": str(e.date) if e.date else None,
            "project_name": proj_map[e.project_id].name if e.project_id and e.project_id in proj_map else None,
        } for e in expenses]
    }


def _get_invoices(tool_input, db, user, now, is_financial_role):
    if not is_financial_role:
        return {"error": "Acceso denegado: solo administradores o RRHH pueden ver facturas."}
    q = db.query(Invoice)
    status = tool_input.get("status", "")
    if status and status != "all": q = q.filter(Invoice.status == status)
    if tool_input.get("project_id"):
        pid = tool_input["project_id"]
        p = db.query(Project).filter(
            or_(Project.id == pid, Project.name.ilike(f"%{pid}%"))
        ).first()
        if p: q = q.filter(Invoice.project_id == p.id)
    if tool_input.get("client_name"):
        q = q.filter(Invoice.client_name.ilike(f"%{tool_input['client_name']}%"))
    invoices = q.order_by(Invoice.issue_date.desc()).limit(tool_input.get("limit", 30)).all()
    total_paid = sum(inv.total or 0 for inv in invoices if inv.status == "paid")
    total_pending = sum(inv.total or 0 for inv in invoices if inv.status in ("sent", "overdue"))
    return {
        "total_paid": round(total_paid, 2),
        "total_pending": round(total_pending, 2),
        "invoices": [{
            "id": inv.id, "number": inv.number,
            "client_name": inv.client_name, "status": str(inv.status),
            "total": inv.total, "currency": inv.currency,
            "issue_date": str(inv.issue_date) if inv.issue_date else None,
            "due_date": str(inv.due_date) if inv.due_date else None,
            "paid_date": str(inv.paid_date) if inv.paid_date else None,
        } for inv in invoices]
    }


def _get_profitability(tool_input, db, user, now, is_financial_role):
    if not is_financial_role:
        return {"error": "Acceso denegado: solo administradores o RRHH pueden ver rentabilidad."}
    pid = tool_input.get("project_id", "")
    if pid:
        projects = db.query(Project).filter(
            or_(Project.id == pid, Project.name.ilike(f"%{pid}%"), Project.code.ilike(f"%{pid}%"))
        ).limit(5).all()
    else:
        projects = db.query(Project).filter(Project.status.in_(["active","planning","completed"])).limit(20).all()
    result = []
    for p in projects:
        hours = db.query(func.sum(Imputation.hours)).filter(Imputation.project_id == p.id).scalar() or 0
        cost = db.query(func.sum(Imputation.cost_amount)).filter(Imputation.project_id == p.id).scalar() or 0
        from app.services.gastos_avanzados import totales_por_proyecto
        expenses_total = totales_por_proyecto(db, [p.id]).get(p.id, 0)
        invoiced = db.query(func.sum(Invoice.total)).filter(
            Invoice.project_id == p.id, Invoice.status.in_(["sent","paid"])
        ).scalar() or 0
        revenue = p.contract_amount or invoiced or 0
        total_cost = cost + expenses_total
        margin = revenue - total_cost
        margin_pct = round(margin / revenue * 100, 1) if revenue else None
        result.append({
            "id": p.id, "code": p.code, "name": p.name, "client": p.client_name,
            "status": p.status, "contract_amount": p.contract_amount,
            "hours_logged": round(hours, 1), "cost_labour": round(cost, 2),
            "expenses": round(expenses_total, 2), "total_cost": round(total_cost, 2),
            "revenue": round(revenue, 2), "invoiced": round(invoiced, 2),
            "gross_margin": round(margin, 2), "margin_pct": margin_pct,
        })
    result.sort(key=lambda x: (x["margin_pct"] or 0))
    return {"profitability": result}


def _get_approvals(tool_input, db, user, now, is_financial_role):
    q = db.query(ApprovalRequest)
    status = tool_input.get("status", "")
    if status and status != "all": q = q.filter(ApprovalRequest.status == status)
    else: q = q.filter(ApprovalRequest.status == "pending")
    approvals = q.order_by(ApprovalRequest.created_at.desc()).limit(tool_input.get("limit", 20)).all()
    return {"approvals": [{
        "id": a.id, "entity_type": a.entity_type, "entity_summary": a.entity_summary,
        "status": a.status, "requested_by": a.requested_by,
        "current_step": a.current_step,
        "created_at": str(a.created_at)[:10] if a.created_at else None,
    } for a in approvals]}


HANDLERS = {
    "get_expenses": _get_expenses,
    "get_invoices": _get_invoices,
    "get_profitability": _get_profitability,
    "get_approvals": _get_approvals,
}
