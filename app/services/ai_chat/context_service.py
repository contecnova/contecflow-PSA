from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.billing_reports import ApprovalRequest, Invoice
from app.models.expenses import Expense
from app.models.imputation import Imputation
from app.models.pipeline import Opportunity
from app.models.project import Project
from app.models.resources import Absence
from app.models.service_desk import Ticket
from app.models.task import Task
from app.models.user import User, UserRole


def build_tenant_context(db: Session, user: User = None) -> dict:
    """Build a rich data context for the current tenant for AI assistants."""
    now = datetime.now(timezone.utc)
    can_see_financials = (
        user is None
        or getattr(user, "is_superadmin", False)
        or getattr(user, "role", None) in (UserRole.admin, UserRole.hr)
    )

    org_id = getattr(user, "organization_id", None) if user else None
    q_proj = db.query(Project).filter(Project.status.in_(["active", "planning"]))
    if org_id:
        q_proj = q_proj.filter(Project.organization_id == org_id)
    projects = q_proj.limit(20).all()

    q_ticket = db.query(Ticket).filter(Ticket.status.in_(["open", "in_progress"]))
    if org_id:
        q_ticket = q_ticket.filter(Ticket.organization_id == org_id)
    open_ticket_rows = q_ticket.order_by(Ticket.created_at.asc()).limit(50).all()
    ticket_assignee_ids = {t.assigned_to_user_id for t in open_ticket_rows if t.assigned_to_user_id}
    ticket_user_map = {}
    if ticket_assignee_ids:
        ticket_user_map = {
            u.id: u.full_name
            for u in db.query(User).filter(User.id.in_(ticket_assignee_ids)).all()
        }
    tickets_detail = [{
        "id": t.id,
        "number": getattr(t, "number", None),
        "title": t.title,
        "status": t.status,
        "priority": t.priority,
        "assigned_to": ticket_user_map.get(t.assigned_to_user_id, "Sin asignar"),
        "created_at": str(t.created_at)[:10] if t.created_at else None,
    } for t in open_ticket_rows]

    q_task = db.query(Task).filter(Task.status != "done", Task.due_date < now.date())
    if org_id:
        q_task = q_task.filter(Task.organization_id == org_id)
    overdue_task_rows = q_task.order_by(Task.due_date.asc()).limit(30).all()
    task_proj_ids = {t.project_id for t in overdue_task_rows}
    task_assignee_ids = {t.assignee_id for t in overdue_task_rows if t.assignee_id}
    task_proj_map = {p.id: p.name for p in db.query(Project).filter(Project.id.in_(task_proj_ids)).all()} if task_proj_ids else {}
    task_user_map = {u.id: u.full_name for u in db.query(User).filter(User.id.in_(task_assignee_ids)).all()} if task_assignee_ids else {}
    overdue_tasks_detail = [{
        "id": t.id,
        "title": t.title,
        "status": t.status,
        "priority": t.priority,
        "project": task_proj_map.get(t.project_id, "?"),
        "assigned_to": task_user_map.get(t.assignee_id, "Sin asignar"),
        "due_date": str(t.due_date) if t.due_date else None,
        "days_overdue": (now.date() - t.due_date).days if t.due_date else None,
    } for t in overdue_task_rows]

    week_start = (now - timedelta(days=now.weekday())).date()
    week_end = week_start + timedelta(days=6)
    q_imp = db.query(Imputation).filter(Imputation.date >= week_start, Imputation.date <= week_end)
    if org_id:
        q_imp = q_imp.filter(Imputation.organization_id == org_id)
    imp_rows = q_imp.all()
    imp_by_user = {}
    imp_by_project = {}
    total_hours_week = 0.0
    for i in imp_rows:
        total_hours_week += i.hours or 0
        imp_by_user[i.user_id] = imp_by_user.get(i.user_id, 0) + (i.hours or 0)
        imp_by_project[i.project_id] = imp_by_project.get(i.project_id, 0) + (i.hours or 0)
    imp_all_user_ids = set(imp_by_user.keys())
    imp_all_proj_ids = set(imp_by_project.keys())
    imp_user_names = {u.id: u.full_name for u in db.query(User).filter(User.id.in_(imp_all_user_ids)).all()} if imp_all_user_ids else {}
    imp_proj_names = {p.id: p.name for p in db.query(Project).filter(Project.id.in_(imp_all_proj_ids)).all()} if imp_all_proj_ids else {}
    hours_by_user = sorted(
        [{"user": imp_user_names.get(uid, uid), "hours": round(h, 1)} for uid, h in imp_by_user.items()],
        key=lambda x: -x["hours"],
    )
    hours_by_project = sorted(
        [{"project": imp_proj_names.get(pid, pid), "hours": round(h, 1)} for pid, h in imp_by_project.items()],
        key=lambda x: -x["hours"],
    )

    pending_invoices_count = 0
    pending_invoices_amount = 0.0
    overdue_invoices = 0
    pipeline_count = 0
    if can_see_financials:
        q_inv = db.query(func.count(Invoice.id)).filter(Invoice.status.in_(["sent", "overdue"]))
        q_inv_amt = db.query(func.sum(Invoice.total)).filter(Invoice.status.in_(["sent", "overdue"]))
        q_overdue = db.query(func.count(Invoice.id)).filter(Invoice.status == "overdue")
        q_pipe = db.query(func.count(Opportunity.id)).filter(Opportunity.stage.notin_(["won", "lost"]))
        if org_id:
            q_inv = q_inv.filter(Invoice.organization_id == org_id)
            q_inv_amt = q_inv_amt.filter(Invoice.organization_id == org_id)
            q_overdue = q_overdue.filter(Invoice.organization_id == org_id)
            q_pipe = q_pipe.filter(Opportunity.organization_id == org_id)
        pending_invoices_count = q_inv.scalar() or 0
        pending_invoices_amount = q_inv_amt.scalar() or 0
        overdue_invoices = q_overdue.scalar() or 0
        pipeline_count = q_pipe.scalar() or 0
    q_approvals = db.query(func.count(ApprovalRequest.id)).filter(ApprovalRequest.status == "pending")
    q_absences = db.query(func.count(Absence.id)).filter(
        Absence.status == "approved",
        Absence.start_date <= now.date(),
        Absence.end_date >= now.date(),
    )
    if org_id:
        q_approvals = q_approvals.filter(ApprovalRequest.organization_id == org_id)
        q_absences = q_absences.filter(Absence.organization_id == org_id)
    pending_approvals = q_approvals.scalar() or 0
    active_absences = q_absences.scalar() or 0

    q_team = db.query(User).filter(User.is_active == True)
    if org_id:
        q_team = q_team.filter(User.organization_id == org_id)
    team_members = q_team.limit(50).all()

    all_active_proj_ids = [p.id for p in projects]
    prof_items = []
    if can_see_financials and all_active_proj_ids:
        q_rates = db.query(User).filter(User.is_active == True)
        if org_id:
            q_rates = q_rates.filter(User.organization_id == org_id)
        all_user_rates = {u.id: (getattr(u, "hourly_rate", None) or 0) for u in q_rates.all()}
        q_imp_user = db.query(
            Imputation.project_id, Imputation.user_id,
            func.sum(Imputation.hours).label("hours"),
        ).filter(Imputation.project_id.in_(all_active_proj_ids))
        if org_id:
            q_imp_user = q_imp_user.filter(Imputation.organization_id == org_id)
        imp_user_rows = q_imp_user.group_by(
            Imputation.project_id, Imputation.user_id
        ).all()
        # Expenses
        q_exp = db.query(
            Expense.project_id, func.sum(Expense.amount).label("total_exp")
        ).filter(
            Expense.project_id.in_(all_active_proj_ids),
            Expense.status == "approved",
        )
        if org_id:
            q_exp = q_exp.filter(Expense.organization_id == org_id)
        exp_rows = q_exp.group_by(Expense.project_id).all()
        # Invoices
        q_inv = db.query(
            Invoice.project_id, func.sum(Invoice.total).label("invoiced")
        ).filter(
            Invoice.project_id.in_(all_active_proj_ids),
            Invoice.status.in_(["sent", "paid", "overdue"]),
        )
        if org_id:
            q_inv = q_inv.filter(Invoice.organization_id == org_id)
        inv_rows = q_inv.group_by(Invoice.project_id).all()
        proj_labor_cost = {}
        proj_hours_total = {}
        for row in imp_user_rows:
            rate = all_user_rates.get(row.user_id, 0) or 0
            proj_labor_cost[row.project_id] = proj_labor_cost.get(row.project_id, 0) + (row.hours * rate)
            proj_hours_total[row.project_id] = proj_hours_total.get(row.project_id, 0) + row.hours
        exp_rows = db.query(
            Expense.project_id, func.sum(Expense.amount).label("total_exp")
        ).filter(
            Expense.project_id.in_(all_active_proj_ids),
            Expense.status == "approved",
        ).group_by(Expense.project_id).all()
        proj_expenses = {r.project_id: (r.total_exp or 0) for r in exp_rows}
        inv_rows = db.query(
            Invoice.project_id, func.sum(Invoice.total).label("invoiced")
        ).filter(
            Invoice.project_id.in_(all_active_proj_ids),
            Invoice.status.in_(["sent", "paid", "overdue"]),
        ).group_by(Invoice.project_id).all()
        proj_invoiced = {r.project_id: (r.invoiced or 0) for r in inv_rows}
        for p in projects:
            labor = round(proj_labor_cost.get(p.id, 0), 2)
            expenses = round(proj_expenses.get(p.id, 0), 2)
            total_cost = round(labor + expenses, 2)
            invoiced = round(proj_invoiced.get(p.id, 0), 2)
            budget = p.budget_hours or 0
            budget_hours_used = round(proj_hours_total.get(p.id, 0), 1)
            margin = round(invoiced - total_cost, 2)
            prof_items.append({
                "project": p.name,
                "client": p.client_name,
                "status": p.status,
                "hours_logged": budget_hours_used,
                "budget_hours": budget,
                "hours_pct": round(budget_hours_used / budget * 100, 1) if budget else None,
                "labor_cost": labor,
                "direct_expenses": expenses,
                "total_cost": total_cost,
                "invoiced": invoiced,
                "margin": margin,
                "is_loss": margin < 0,
            })
        prof_items.sort(key=lambda x: x["margin"])

    return {
        "today": now.strftime("%Y-%m-%d"),
        "active_projects": len(projects),
        "projects": [{
            "id": p.id, "code": p.code, "name": p.name,
            "status": p.status, "risk_level": str(p.risk_level),
            "client": p.client_name,
            "budget_hours": p.budget_hours,
            "end_date_planned": str(p.end_date_planned) if p.end_date_planned else None,
        } for p in projects],
        "open_tickets": len(tickets_detail),
        "tickets": tickets_detail,
        "overdue_tasks": len(overdue_tasks_detail),
        "overdue_tasks_detail": overdue_tasks_detail,
        "hours_this_week": round(total_hours_week, 1),
        "hours_by_user_this_week": hours_by_user,
        "hours_by_project_this_week": hours_by_project,
        "team": [{"id": u.id, "name": u.full_name, "role": u.role,
                  "department": getattr(u, "department", None)} for u in team_members],
        "pending_approvals": pending_approvals,
        "team_on_leave_today": active_absences,
        "financial_data_restricted": not can_see_financials,
        "pending_invoices": pending_invoices_count,
        "pending_invoices_amount": round(pending_invoices_amount or 0, 2),
        "overdue_invoices": overdue_invoices,
        "pipeline_opportunities": pipeline_count,
        "profitability": prof_items,
        "projects_at_loss": [x for x in prof_items if x.get("is_loss")],
    }
