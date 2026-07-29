"""Herramientas transversales: alertas, búsqueda global, notificaciones y actividad git."""
from __future__ import annotations

from sqlalchemy import or_

from app.models.alert import Alert
from app.models.billing_reports import Invoice
from app.models.clients import Client
from app.models.git_integration import GitPullRequest
from app.models.pipeline import Risk, Opportunity
from app.models.project import Project
from app.models.service_desk import Ticket
from app.models.task import Task
from app.models.user import User


def _get_alerts(tool_input, db, user, now, is_financial_role):
    q = db.query(Alert).filter(Alert.is_resolved == False)
    if tool_input.get("severity"): q = q.filter(Alert.severity == tool_input["severity"])
    if tool_input.get("project_id"): q = q.filter(Alert.project_id == tool_input["project_id"])
    alerts = q.order_by(Alert.created_at.desc()).limit(tool_input.get("limit", 20)).all()
    proj_ids = {a.project_id for a in alerts if a.project_id}
    proj_map = {p.id: p for p in db.query(Project).filter(Project.id.in_(proj_ids)).all()}
    return {"alerts": [{
        "id": a.id, "title": a.title, "description": a.description,
        "alert_type": str(a.alert_type), "severity": str(a.severity),
        "project_name": proj_map[a.project_id].name if a.project_id and a.project_id in proj_map else None,
        "value": a.value, "threshold": a.threshold,
        "created_at": str(a.created_at)[:10] if a.created_at else None,
    } for a in alerts]}


def _search_all(tool_input, db, user, now, is_financial_role):
    query = tool_input.get("query", "")
    lim = tool_input.get("limit_per_entity", 5)
    term = f"%{query}%"
    results = {}

    projects = db.query(Project).filter(
        or_(Project.name.ilike(term), Project.code.ilike(term), Project.client_name.ilike(term))
    ).limit(lim).all()
    if projects:
        results["projects"] = [{"id": p.id, "code": p.code, "name": p.name,
                                "status": p.status, "client": p.client_name} for p in projects]

    tasks = db.query(Task).filter(Task.title.ilike(term)).limit(lim).all()
    if tasks:
        proj_ids = {t.project_id for t in tasks}
        pmap = {p.id: p.name for p in db.query(Project).filter(Project.id.in_(proj_ids)).all()}
        results["tasks"] = [{"id": t.id, "title": t.title, "status": t.status,
                             "priority": t.priority,
                             "project": pmap.get(t.project_id, "?")} for t in tasks]

    tickets = db.query(Ticket).filter(
        or_(Ticket.title.ilike(term), Ticket.number.ilike(term))
    ).limit(lim).all()
    if tickets:
        results["tickets"] = [{"id": t.id, "number": t.number, "title": t.title,
                               "status": t.status, "priority": t.priority} for t in tickets]

    risks = db.query(Risk).filter(
        or_(Risk.title.ilike(term), Risk.code.ilike(term))
    ).limit(lim).all()
    if risks:
        proj_ids = {r.project_id for r in risks}
        pmap = {p.id: p.name for p in db.query(Project).filter(Project.id.in_(proj_ids)).all()}
        results["risks"] = [{"id": r.id, "code": r.code, "title": r.title,
                             "impact": str(r.impact), "status": str(r.status),
                             "project": pmap.get(r.project_id, "?")} for r in risks]

    clients = db.query(Client).filter(Client.name.ilike(term)).limit(lim).all()
    if clients:
        results["clients"] = [{"id": c.id, "name": c.name} for c in clients]

    users = db.query(User).filter(
        or_(User.full_name.ilike(term), User.email.ilike(term))
    ).limit(lim).all()
    if users:
        results["users"] = [{"id": u.id, "name": u.full_name,
                             "role": u.role, "email": u.email} for u in users]

    invoices = db.query(Invoice).filter(
        or_(Invoice.number.ilike(term), Invoice.client_name.ilike(term))
    ).limit(lim).all()
    if invoices:
        results["invoices"] = [{"id": inv.id, "number": inv.number,
                                "client": inv.client_name, "total": inv.total,
                                "status": str(inv.status)} for inv in invoices]

    opps = db.query(Opportunity).filter(
        or_(Opportunity.name.ilike(term), Opportunity.client_name.ilike(term))
    ).limit(lim).all()
    if opps:
        results["opportunities"] = [{"id": o.id, "name": o.name,
                                     "client": o.client_name, "stage": str(o.stage),
                                     "expected_revenue": o.expected_revenue} for o in opps]

    return {"query": query, "found_in": list(results.keys()), "results": results}


def _send_notification(tool_input, db, user, now, is_financial_role):
    from app.models.enterprise import Notification
    sent = []
    for name in (tool_input.get("user_names") or []):
        u = db.query(User).filter(User.full_name.ilike(f"%{name}%")).first()
        if u:
            db.add(Notification(
                user_id=u.id, title="Mensaje del Agente IA",
                body=tool_input["message"], action_url=tool_input.get("link"),
            ))
            sent.append(u.full_name)
    db.flush()
    return {"ok": True, "sent_to": sent}


def _get_git_activity(tool_input, db, user, now, is_financial_role):
    q = db.query(GitPullRequest)
    if tool_input.get("project_id"):
        pid = tool_input["project_id"]
        p = db.query(Project).filter(
            or_(Project.id == pid, Project.name.ilike(f"%{pid}%"), Project.code.ilike(f"%{pid}%"))
        ).first()
        if p: q = q.filter(GitPullRequest.project_id == p.id)
    status = tool_input.get("status", "all")
    if status and status != "all":
        q = q.filter(GitPullRequest.status == status)
    prs = q.order_by(GitPullRequest.created_at.desc()).limit(tool_input.get("limit", 20)).all()
    proj_ids = {pr.project_id for pr in prs if pr.project_id}
    pmap = {p.id: p.name for p in db.query(Project).filter(Project.id.in_(proj_ids)).all()}
    return {
        "pull_requests": [{
            "id": pr.id,
            "repo": pr.repo_full_name,
            "pr_number": pr.pr_number,
            "title": pr.pr_title,
            "author": pr.author_login,
            "source_branch": pr.source_branch,
            "target_branch": pr.target_branch,
            "status": str(pr.status),
            "project": pmap.get(pr.project_id, "?") if pr.project_id else None,
            "merged_at": str(pr.merged_at)[:10] if pr.merged_at else None,
            "created_at": str(pr.created_at)[:10] if pr.created_at else None,
        } for pr in prs]
    }


HANDLERS = {
    "get_alerts": _get_alerts,
    "search_all": _search_all,
    "send_notification": _send_notification,
    "get_git_activity": _get_git_activity,
}
