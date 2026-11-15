"""Herramientas transversales: alertas, búsqueda global, notificaciones y actividad git."""
from __future__ import annotations

from sqlalchemy import or_

from app.models.alert import Alert
from app.models.clients import Client
from app.models.git_integration import GitPullRequest
from app.models.pipeline import Risk
from app.models.project import Project
from app.services.ai_chat.tool_execution.politica import buscar_persona, por_proyecto_visible


def _get_alerts(tool_input, db, user, now, is_financial_role):
    # Segunda auditoría 2026-11: el alcance de `GET /alerts` (`get_alerts_query`).
    from app.services.alert_service import get_alerts_query
    q = get_alerts_query(db, False, tool_input.get("severity") or None, user)
    if tool_input.get("project_id"):
        q = por_proyecto_visible(q, Alert.project_id, tool_input, db, user)
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
    """Búsqueda del asistente (chat, agente y MCP).

    Segunda auditoría 2026-11: no acotaba nada; por MCP un empleado encontraba
    los proyectos, tickets, facturas y oportunidades de toda la empresa. Ahora usa
    las mismas consultas acotadas que `GET /global-search`
    (`cab_service.busqueda.consulta_de_*`).
    """
    from app.services import politica_de_visibilidad as _vis
    from app.services.cab_service import busqueda as _b
    from app.services.project_service import scope_projects_query

    query = tool_input.get("query", "")
    lim = tool_input.get("limit_per_entity", 5)
    patron = f"%{query.lower()}%"
    term = f"%{query}%"
    results = {}

    projects = _b.consulta_de_proyectos(db, user, patron).limit(lim).all()
    if projects:
        results["projects"] = [{"id": p.id, "code": p.code, "name": p.name,
                                "status": p.status, "client": p.client_name} for p in projects]

    tasks = _b.consulta_de_tareas(db, user, patron).limit(lim).all()
    if tasks:
        results["tasks"] = [{"id": t.id, "title": t.title, "status": t.status,
                             "priority": t.priority,
                             "project": t.project.name if t.project else "?"} for t in tasks]

    tickets = _b.consulta_de_tickets(db, user, patron).limit(lim).all()
    if tickets:
        results["tickets"] = [{"id": t.id, "number": t.number, "title": t.title,
                               "status": t.status, "priority": t.priority} for t in tickets]

    visibles = scope_projects_query(db.query(Project.id), db, user).subquery()
    risks = db.query(Risk).filter(
        or_(Risk.title.ilike(term), Risk.code.ilike(term)),
        Risk.project_id.in_(db.query(visibles.c.id)),
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

    ve_contacto = _vis.ve_contacto_ajeno(user)
    users = _b.consulta_de_personas(db, user, patron).limit(lim).all()
    if users:
        results["users"] = [{"id": u.id, "name": u.full_name, "role": u.role,
                             "email": u.email if ve_contacto else None} for u in users]

    facturas = _b.consulta_de_facturas(db, user, patron)
    invoices = facturas.limit(lim).all() if facturas is not None else []
    if invoices:
        results["invoices"] = [{"id": inv.id, "number": inv.number,
                                "client": inv.client_name, "total": inv.total,
                                "status": str(inv.status)} for inv in invoices]

    oportunidades = _b.consulta_de_oportunidades(db, user, patron)
    opps = oportunidades.limit(lim).all() if oportunidades is not None else []
    if opps:
        results["opportunities"] = [{"id": o.id, "name": o.name,
                                     "client": o.client_name, "stage": str(o.stage),
                                     "expected_revenue": o.expected_revenue} for o in opps]

    return {"query": query, "found_in": list(results.keys()), "results": results}


def _send_notification(tool_input, db, user, now, is_financial_role):
    from app.models.enterprise import Notification
    sent = []
    # Solo a personas que ve quien manda (`politica_de_visibilidad`).
    for name in (tool_input.get("user_names") or []):
        u = buscar_persona(db, user, name)
        if u:
            db.add(Notification(
                user_id=u.id, title="Mensaje del Agente IA",
                body=tool_input["message"], action_url=tool_input.get("link"),
            ))
            sent.append(u.full_name)
    db.flush()
    return {"ok": True, "sent_to": sent}


def _get_git_activity(tool_input, db, user, now, is_financial_role):
    # Los PR de los proyectos que ve (y, para quien ve toda la empresa, también
    # los que no tienen proyecto).
    from app.services import politica_de_visibilidad as _vis
    q = db.query(GitPullRequest)
    if tool_input.get("project_id") or _vis.solo_proyectos_propios(user):
        q = por_proyecto_visible(q, GitPullRequest.project_id, tool_input, db, user)
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
