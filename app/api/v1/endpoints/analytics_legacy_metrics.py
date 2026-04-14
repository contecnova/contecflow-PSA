from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.imputation import Imputation
from app.models.project import Project
from app.models.resources import Absence, ChangeRequest, Deliverable
from app.models.task import Task
from app.models.user import User


LEGACY_METRIC_IDS = [
    "hours_by_project",
    "hours_by_week",
    "hours_by_month",
    "hours_by_department",
    "hours_billable_vs_internal",
    "cost_by_project",
    "cost_by_person",
    "cost_by_month",
        # Migrated metrics removed: hours_by_project, hours_by_week, hours_by_month, hours_by_department, hours_billable_vs_internal, cost_by_project, cost_by_person, cost_by_month, budget_consumption, cost_vs_budget, hours_heatmap
    "deliverables_status",
    "risks_by_level",
    "pipeline_by_stage",
    "absences_by_type",
    "absences_by_person",
    "absences_by_month",
    "load_by_week",
    "change_requests_status",
    "hours_heatmap",
    "tickets_by_status",
    "tickets_by_type",
    "tickets_by_priority",
    "ticket_resolution_time",
    "ticket_sla_compliance",
    "ticket_volume_trend",
    "ticket_csat",
    "sprint_velocity",
    "sprint_completion_rate",
    "tasks_lead_time",
    "tasks_blocked_by_project",
    "tasks_overdue",
    "contracts_by_status",
    "win_rate_evolution",
    "license_expiry_timeline",
    "assets_by_type",
    "semantic_accuracy_trend",
    "semantic_assignments_by_mode",
]


def _month_label(d) -> str:
    months = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    if hasattr(d, "month"):
        return f"{months[d.month - 1]} {d.year}"
    return str(d)


def run_legacy_metric(
    metric_id: str,
    *,
    db: Session,
    d_from,
    d_to,
    top_n: int,
    project_id: Optional[str],
    user_id: Optional[str],
    project_ids: Optional[list[str]],
) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    meta_patch: dict = {}

    if metric_id == "hours_by_project":
        q = db.query(Project.name.label("name"), Project.code.label("code"), func.sum(Imputation.hours).label("value")).join(
            Imputation,
            Imputation.project_id == Project.id,
        ).filter(Imputation.date.between(d_from, d_to))
        if user_id:
            q = q.filter(Imputation.user_id == user_id)
        rows = [{"label": f"{r.code} {r.name}", "value": round(r.value or 0, 1)} for r in q.group_by(Project.name, Project.code).order_by(func.sum(Imputation.hours).desc()).limit(top_n).all()]

    elif metric_id == "hours_by_week":
        imps = db.query(Imputation.date, Imputation.hours).filter(Imputation.date.between(d_from, d_to))
        if project_id:
            imps = imps.filter(Imputation.project_id == project_id)
        if user_id:
            imps = imps.filter(Imputation.user_id == user_id)
        weekly = {}
        for imp in imps.all():
            ws = imp.date - timedelta(days=imp.date.weekday())
            key = str(ws)
            weekly[key] = weekly.get(key, 0) + imp.hours
        rows = [{"label": k[5:], "full_label": k, "value": round(v, 1)} for k, v in sorted(weekly.items())]

    elif metric_id == "hours_by_month":
        imps = db.query(Imputation.date, Imputation.hours).filter(Imputation.date.between(d_from, d_to))
        if project_id:
            imps = imps.filter(Imputation.project_id == project_id)
        if user_id:
            imps = imps.filter(Imputation.user_id == user_id)
        monthly = {}
        for imp in imps.all():
            key = imp.date.strftime("%Y-%m")
            monthly[key] = monthly.get(key, 0) + imp.hours
        rows = [{"label": _month_label(date.fromisoformat(k + "-01")), "value": round(v, 1)} for k, v in sorted(monthly.items())]

    elif metric_id == "hours_by_department":
        q = db.query(User.department.label("dept"), func.sum(Imputation.hours).label("value")).join(
            Imputation,
            Imputation.user_id == User.id,
        ).filter(Imputation.date.between(d_from, d_to)).filter(User.department.isnot(None))
        if project_id:
            q = q.filter(Imputation.project_id == project_id)
        rows = [{"label": r.dept or "Sin depto", "value": round(r.value or 0, 1)} for r in q.group_by(User.department).order_by(func.sum(Imputation.hours).desc()).all()]

    elif metric_id == "hours_billable_vs_internal":
        from sqlalchemy import case
        q = db.query(
            User.full_name.label("name"),
            func.sum(case((Imputation.is_billable == True, Imputation.hours), else_=0)).label("billable"),
            func.sum(case((Imputation.is_billable == False, Imputation.hours), else_=0)).label("internal"),
        ).join(Imputation, Imputation.user_id == User.id).filter(Imputation.date.between(d_from, d_to))
        if project_id:
            q = q.filter(Imputation.project_id == project_id)
        rows = [{"label": r.name, "billable": round(r.billable or 0, 1), "internal": round(r.internal or 0, 1), "value": round((r.billable or 0) + (r.internal or 0), 1)} for r in q.group_by(User.full_name).order_by(func.sum(Imputation.hours).desc()).limit(top_n).all()]

    elif metric_id == "cost_by_project":
        q = db.query(Project.name, Project.code, func.sum(Imputation.cost_amount).label("value")).join(
            Imputation,
            Imputation.project_id == Project.id,
        ).filter(Imputation.date.between(d_from, d_to))
        rows = [{"label": f"{r.code} {r.name}", "value": round(r.value or 0, 2)} for r in q.group_by(Project.name, Project.code).order_by(func.sum(Imputation.cost_amount).desc()).limit(top_n).all()]

    elif metric_id == "cost_by_person":
        q = db.query(User.full_name, func.sum(Imputation.cost_amount).label("value")).join(Imputation, Imputation.user_id == User.id).filter(Imputation.date.between(d_from, d_to))
        if project_id:
            q = q.filter(Imputation.project_id == project_id)
        rows = [{"label": r.full_name, "value": round(r.value or 0, 2)} for r in q.group_by(User.full_name).order_by(func.sum(Imputation.cost_amount).desc()).limit(top_n).all()]

    elif metric_id == "cost_by_month":
        imps = db.query(Imputation.date, Imputation.cost_amount).filter(Imputation.date.between(d_from, d_to))
        if project_id:
            imps = imps.filter(Imputation.project_id == project_id)
        monthly = {}
        for imp in imps.all():
            key = imp.date.strftime("%Y-%m")
            monthly[key] = monthly.get(key, 0) + (imp.cost_amount or 0)
        rows = [{"label": _month_label(date.fromisoformat(k + "-01")), "value": round(v, 2)} for k, v in sorted(monthly.items())]

    elif metric_id == "budget_consumption":
        projects = db.query(Project).filter(Project.budget_amount.isnot(None), Project.budget_amount > 0).all()
        for p in projects[:top_n]:
            cost = db.query(func.sum(Imputation.cost_amount)).filter(Imputation.project_id == p.id).scalar() or 0
            pct = round(cost / p.budget_amount * 100, 1)
            rows.append({"label": f"{p.code}", "value": pct, "cost": round(cost, 0), "budget": p.budget_amount, "status": "critical" if pct > 100 else "warning" if pct > 85 else "ok"})
        rows.sort(key=lambda x: x["value"], reverse=True)

    elif metric_id == "cost_vs_budget":
        projects = db.query(Project).filter(Project.budget_amount.isnot(None)).all()
        for p in projects[:top_n]:
            cost = db.query(func.sum(Imputation.cost_amount)).filter(Imputation.project_id == p.id).scalar() or 0
            rows.append({"label": p.code, "budget": p.budget_amount or 0, "cost": round(cost, 0), "value": round(cost, 0)})
        rows.sort(key=lambda x: x["cost"], reverse=True)

    elif metric_id == "tasks_by_status":
        STATUS_LABELS = {"todo": "Por hacer", "in_progress": "En curso", "in_review": "En revisión", "done": "Hecho", "blocked": "Bloqueado"}
        q = db.query(Task.status, func.count(Task.id).label("count"))
        if project_ids:
            q = q.filter(Task.project_id.in_(project_ids))
        rows = [{"label": STATUS_LABELS.get(r.status, r.status), "value": r.count} for r in q.group_by(Task.status).all()]

    elif metric_id == "tasks_by_project":
        q = db.query(Project.name, Project.code, func.count(Task.id).label("count")).join(Task, Task.project_id == Project.id).group_by(Project.name, Project.code).order_by(func.count(Task.id).desc()).limit(top_n)
        rows = [{"label": f"{r.code}", "value": r.count} for r in q.all()]

    elif metric_id == "projects_by_status":
        STATUS_LABELS = {"planning": "Planificación", "active": "Activo", "paused": "Pausado", "closed": "Cerrado", "cancelled": "Cancelado"}
        q = db.query(Project.status, func.count(Project.id).label("count")).group_by(Project.status)
        if project_ids:
            q = q.filter(Project.id.in_(project_ids))
        rows = [{"label": STATUS_LABELS.get(r.status, r.status), "value": r.count} for r in q.all()]

    elif metric_id == "deliverables_status":
        STATUS_LABELS = {"planned": "Planificado", "in_progress": "En curso", "in_review": "En revisión", "delivered": "Entregado", "accepted": "Aceptado", "rejected": "Rechazado"}
        q = db.query(Deliverable.status, func.count(Deliverable.id).label("count")).group_by(Deliverable.status)
        if project_ids:
            q = q.filter(Deliverable.project_id.in_(project_ids))
        rows = [{"label": STATUS_LABELS.get(r.status, r.status), "value": r.count} for r in q.all()]

    elif metric_id == "risks_by_level":
        from app.api.v1.endpoints.risks import _risk_level, _risk_score
        from app.models.pipeline import Risk
        risks = db.query(Risk).filter(Risk.status.notin_(["closed"])).all()
        levels = {}
        for r in risks:
            lvl = _risk_level(_risk_score(r.probability, r.impact))
            levels[lvl] = levels.get(lvl, 0) + 1
        LEVEL_LABELS = {"critical": "Crítico", "high": "Alto", "medium": "Medio", "low": "Bajo"}
        rows = [{"label": LEVEL_LABELS.get(k, k), "value": v} for k, v in sorted(levels.items(), key=lambda x: ["critical", "high", "medium", "low"].index(x[0]))]

    elif metric_id == "pipeline_by_stage":
        from app.models.pipeline import Opportunity
        STAGE_LABELS = {"lead": "Lead", "qualification": "Cualificación", "proposal": "Propuesta", "negotiation": "Negociación", "won": "Ganada", "lost": "Perdida"}
        q = db.query(Opportunity.stage, func.count(Opportunity.id).label("count"), func.sum(Opportunity.expected_revenue).label("revenue"), func.avg(Opportunity.probability).label("avg_prob")).group_by(Opportunity.stage)
        for r in q.all():
            weighted = (r.revenue or 0) * (r.avg_prob or 0) / 100
            rows.append({"label": STAGE_LABELS.get(r.stage, r.stage), "count": r.count, "revenue": round(r.revenue or 0, 0), "weighted": round(weighted, 0), "value": round(weighted, 0)})

    elif metric_id == "absences_by_type":
        from app.models.resources import AbsenceStatus
        TYPE_LABELS = {"vacation": "Vacaciones", "sick": "Baja médica", "personal": "Personal", "training": "Formación", "maternity": "Maternidad", "paternity": "Paternidad", "other": "Otro"}
        q = db.query(Absence.type, func.sum(Absence.working_days).label("days")).filter(Absence.status == AbsenceStatus.approved, Absence.start_date.between(d_from, d_to)).group_by(Absence.type)
        rows = [{"label": TYPE_LABELS.get(r.type, r.type), "value": round(r.days or 0, 1)} for r in q.all()]

    elif metric_id == "absences_by_person":
        from app.models.resources import AbsenceStatus
        q = db.query(User.full_name, func.sum(Absence.working_days).label("days")).join(Absence, Absence.user_id == User.id).filter(Absence.status == AbsenceStatus.approved, Absence.start_date.between(d_from, d_to)).group_by(User.full_name).order_by(func.sum(Absence.working_days).desc()).limit(top_n)
        rows = [{"label": r.full_name, "value": round(r.days or 0, 1)} for r in q.all()]

    elif metric_id == "absences_by_month":
        from app.models.resources import AbsenceStatus
        monthly = {}
        for a in db.query(Absence).filter(Absence.status == AbsenceStatus.approved, Absence.start_date.between(d_from, d_to)).all():
            key = a.start_date.strftime("%Y-%m")
            monthly[key] = monthly.get(key, 0) + (a.working_days or 0)
        rows = [{"label": _month_label(date.fromisoformat(k + "-01")), "value": round(v, 1)} for k, v in sorted(monthly.items())]

    elif metric_id == "load_by_week":
        users_all = db.query(User).filter(User.is_active == True).all()
        total_capacity = sum(u.weekly_capacity_hours or settings.DEFAULT_WEEKLY_CAPACITY_HOURS for u in users_all)
        imps = db.query(Imputation.date, func.sum(Imputation.hours).label("h")).filter(Imputation.date.between(d_from, d_to)).group_by(Imputation.date).all()
        weekly = {}
        for row in imps:
            ws = row.date - timedelta(days=row.date.weekday())
            key = str(ws)
            weekly[key] = weekly.get(key, 0) + row.h
        for k, v in sorted(weekly.items()):
            rows.append({"label": k[5:], "value": round(v / total_capacity * 100, 1) if total_capacity > 0 else 0, "hours": round(v, 1)})

    elif metric_id == "change_requests_status":
        STATUS_LABELS = {"draft": "Borrador", "submitted": "Enviado", "under_review": "En revisión", "approved": "Aprobado", "rejected": "Rechazado", "implemented": "Implementado"}
        q = db.query(ChangeRequest.status, func.count(ChangeRequest.id).label("count"), func.sum(ChangeRequest.cost_impact).label("cost"), func.sum(ChangeRequest.schedule_impact_days).label("days")).group_by(ChangeRequest.status)
        if project_ids:
            q = q.filter(ChangeRequest.project_id.in_(project_ids))
        rows = [{"label": STATUS_LABELS.get(r.status, r.status), "value": r.count, "cost_impact": round(r.cost or 0, 0), "days_impact": r.days or 0} for r in q.all()]

    elif metric_id == "hours_heatmap":
        imps = db.query(User.full_name, Imputation.date, func.sum(Imputation.hours).label("h")).join(User, User.id == Imputation.user_id).filter(Imputation.date.between(d_from, d_to))
        if project_id:
            imps = imps.filter(Imputation.project_id == project_id)
        imps = imps.group_by(User.full_name, Imputation.date).all()
        heatmap = {}
        weeks = set()
        for row in imps:
            ws = str(row.date - timedelta(days=row.date.weekday()))
            weeks.add(ws)
            key = (row.full_name, ws)
            heatmap[key] = heatmap.get(key, 0) + row.h
        week_list = sorted(weeks)[-16:]
        persons = list({k[0] for k in heatmap.keys()})[:top_n]
        for p in persons:
            row_data = {"label": p}
            for w in week_list:
                row_data[w[5:]] = round(heatmap.get((p, w), 0), 1)
            rows.append(row_data)
        meta_patch = {"weeks": [w[5:] for w in week_list], "persons": persons}

    elif metric_id == "tickets_by_status":
        from app.models.service_desk import Ticket
        STATUS_LABELS = {"new": "Nuevo", "assigned": "Asignado", "in_progress": "En proceso", "pending_client": "Pendiente cliente", "resolved": "Resuelto", "closed": "Cerrado"}
        q = db.query(Ticket.status, func.count(Ticket.id).label("n")).group_by(Ticket.status)
        if project_id:
            q = q.filter(Ticket.project_id == project_id)
        rows = [{"label": STATUS_LABELS.get(r.status, r.status), "value": r.n} for r in q.all()]

    elif metric_id == "tickets_by_type":
        from app.models.service_desk import Ticket
        TYPE_LABELS = {"incident": "Incidencia", "request": "Solicitud", "question": "Consulta", "problem": "Problema", "change": "Cambio"}
        q = db.query(Ticket.ticket_type, func.count(Ticket.id).label("n")).group_by(Ticket.ticket_type)
        if project_id:
            q = q.filter(Ticket.project_id == project_id)
        rows = [{"label": TYPE_LABELS.get(str(r.ticket_type).replace("TicketType.", ""), str(r.ticket_type)), "value": r.n} for r in q.all()]

    elif metric_id == "tickets_by_priority":
        from app.models.service_desk import Ticket
        PRIO_LABELS = {"p1_critical": "P1 Crítica", "p2_high": "P2 Alta", "p3_medium": "P3 Media", "p4_low": "P4 Baja"}
        q = db.query(Ticket.priority, func.count(Ticket.id).label("n")).group_by(Ticket.priority)
        if project_id:
            q = q.filter(Ticket.project_id == project_id)
        rows = [{"label": PRIO_LABELS.get(str(r.priority).replace("TicketPriority.", ""), str(r.priority)), "value": r.n} for r in q.all()]

    elif metric_id == "ticket_resolution_time":
        from app.db.session import is_postgres
        from app.models.service_desk import Ticket
        type_labels = {"incident": "Incidencia", "request": "Solicitud", "question": "Consulta", "change": "Cambio"}
        if is_postgres():
            _avg_days = (func.extract("epoch", func.avg(Ticket.resolved_at - Ticket.created_at)) / 86400).label("avg_days")
        else:
            _avg_days = func.avg(func.julianday(Ticket.resolved_at) - func.julianday(Ticket.created_at)).label("avg_days")
        rows_raw = db.query(Ticket.ticket_type, func.count(Ticket.id).label("n"), _avg_days).filter(Ticket.resolved_at.isnot(None), Ticket.created_at.isnot(None)).group_by(Ticket.ticket_type).all()
        rows = [{"label": type_labels.get(str(r.ticket_type).replace("TicketType.", ""), str(r.ticket_type)), "value": round((r.avg_days or 0) * 24, 1), "count": r.n} for r in rows_raw]

    elif metric_id == "ticket_sla_compliance":
        from app.models.service_desk import Ticket
        monthly = {}
        for t in db.query(Ticket.created_at, Ticket.sla_response_status, Ticket.sla_resolution_status).filter(Ticket.created_at.isnot(None)).all():
            if t.created_at:
                key = str(t.created_at)[:7]
                if key not in monthly:
                    monthly[key] = {"total": 0, "ok_resp": 0, "ok_res": 0}
                monthly[key]["total"] += 1
                if str(t.sla_response_status) in ("ok", "SLAStatus.ok"):
                    monthly[key]["ok_resp"] += 1
                if str(t.sla_resolution_status) in ("ok", "SLAStatus.ok"):
                    monthly[key]["ok_res"] += 1
        for k in sorted(monthly.keys())[-12:]:
            m = monthly[k]
            pct = round(m["ok_res"] / m["total"] * 100, 1) if m["total"] > 0 else 0
            rows.append({"label": k, "value": pct, "total": m["total"], "ok": m["ok_res"]})

    elif metric_id == "ticket_volume_trend":
        from app.models.service_desk import Ticket
        monthly = {}
        for t in db.query(Ticket.created_at).filter(Ticket.created_at.isnot(None)).all():
            k = str(t.created_at)[:7]
            if k not in monthly:
                monthly[k] = {"opened": 0, "closed": 0}
            monthly[k]["opened"] += 1
        for t in db.query(Ticket.resolved_at).filter(Ticket.resolved_at.isnot(None)).all():
            k = str(t.resolved_at)[:7]
            if k not in monthly:
                monthly[k] = {"opened": 0, "closed": 0}
            monthly[k]["closed"] += 1
        for k in sorted(monthly.keys())[-12:]:
            m = monthly[k]
            rows.append({"label": k, "opened": m["opened"], "closed": m["closed"], "value": m["opened"]})

    elif metric_id == "ticket_csat":
        from app.models.service_desk import Ticket
        users_data = db.query(User).filter(User.is_active == True).all()
        for u in users_data[:top_n]:
            ratings = db.query(Ticket.csat_score).filter(Ticket.assigned_to_user_id == u.id, Ticket.csat_score.isnot(None)).all()
            if ratings:
                avg = sum(r.csat_score for r in ratings) / len(ratings)
                rows.append({"label": u.full_name, "value": round(avg, 2), "count": len(ratings)})
        rows.sort(key=lambda x: -x["value"])

    elif metric_id == "sprint_velocity":
        from app.models.sprints import Sprint, SprintTask
        sprints_q = db.query(Sprint)
        if project_id:
            sprints_q = sprints_q.filter(Sprint.project_id == project_id)
        for sp in sprints_q.order_by(Sprint.start_date).limit(20).all():
            done_pts = db.query(func.sum(Task.story_points)).join(SprintTask, SprintTask.task_id == Task.id).filter(SprintTask.sprint_id == sp.id, Task.status == "done").scalar() or 0
            total_pts = db.query(func.sum(Task.story_points)).join(SprintTask, SprintTask.task_id == Task.id).filter(SprintTask.sprint_id == sp.id).scalar() or 0
            rows.append({"label": sp.name[:20], "completed": done_pts, "planned": total_pts, "value": done_pts})

    elif metric_id == "sprint_completion_rate":
        from app.models.sprints import Sprint, SprintTask
        sprints_q = db.query(Sprint)
        if project_id:
            sprints_q = sprints_q.filter(Sprint.project_id == project_id)
        for sp in sprints_q.order_by(Sprint.start_date).limit(20).all():
            done_pts = db.query(func.sum(Task.story_points)).join(SprintTask, SprintTask.task_id == Task.id).filter(SprintTask.sprint_id == sp.id, Task.status == "done").scalar() or 0
            total_pts = db.query(func.sum(Task.story_points)).join(SprintTask, SprintTask.task_id == Task.id).filter(SprintTask.sprint_id == sp.id).scalar() or 0
            pct = round(done_pts / total_pts * 100, 1) if total_pts > 0 else 0
            rows.append({"label": sp.name[:20], "value": pct, "done": done_pts, "total": total_pts})

    elif metric_id == "tasks_lead_time":
        import logging
        logger = logging.getLogger(__name__)
        projects_q = db.query(Project).filter(Project.status == "active")
        if project_id:
            projects_q = projects_q.filter(Project.id == project_id)
        for proj in projects_q.all():
            done_tasks = db.query(Task).filter(Task.project_id == proj.id, Task.status == "done", Task.completed_at.isnot(None), Task.created_at.isnot(None)).all()
            if done_tasks:
                lead_times = []
                for t in done_tasks:
                    try:
                        lead_times.append((t.completed_at - t.created_at).days)
                    except Exception as e:
                        logger.warning("Skipping task %s for lead time due invalid dates: %s", t.id, e)
                if lead_times:
                    rows.append({"label": proj.code or proj.name[:20], "value": round(sum(lead_times) / len(lead_times), 1), "count": len(lead_times)})
        rows.sort(key=lambda x: -x["value"])

    elif metric_id == "tasks_blocked_by_project":
        projects_q = db.query(Project).filter(Project.status == "active")
        if project_id:
            projects_q = projects_q.filter(Project.id == project_id)
        for proj in projects_q.all():
            n = db.query(func.count(Task.id)).filter(Task.project_id == proj.id, Task.status == "blocked").scalar() or 0
            if n > 0:
                rows.append({"label": proj.code or proj.name[:20], "value": n})
        rows.sort(key=lambda x: -x["value"])

    elif metric_id == "tasks_overdue":
        from datetime import date as date_
        today = date_.today()
        projects_q = db.query(Project).filter(Project.status == "active")
        if project_id:
            projects_q = projects_q.filter(Project.id == project_id)
        for proj in projects_q.all():
            n = db.query(func.count(Task.id)).filter(Task.project_id == proj.id, Task.due_date < today, Task.status.notin_(["done", "cancelled"])).scalar() or 0
            if n > 0:
                rows.append({"label": proj.code or proj.name[:20], "value": n})
        rows.sort(key=lambda x: -x["value"])

    elif metric_id == "contracts_by_status":
        from app.models.pipeline import Contract
        STATUS_LABELS = {"draft": "Borrador", "active": "Activo", "completed": "Completado", "cancelled": "Cancelado"}
        rows_raw = db.query(Contract.status, func.count(Contract.id).label("n"), func.sum(Contract.total_amount).label("total")).group_by(Contract.status).all()
        rows = [{"label": STATUS_LABELS.get(r.status, r.status), "value": round(r.total or 0, 0), "count": r.n} for r in rows_raw]

    elif metric_id == "win_rate_evolution":
        from app.models.pipeline import Opportunity
        monthly = {}
        for opp in db.query(Opportunity).filter(Opportunity.created_at >= d_from).all():
            k = str(opp.created_at)[:7] if opp.created_at else "unknown"
            if k not in monthly:
                monthly[k] = {"won": 0, "lost": 0, "total": 0}
            monthly[k]["total"] += 1
            if str(opp.stage) in ("won", "Stage.won"):
                monthly[k]["won"] += 1
            elif str(opp.stage) in ("lost", "Stage.lost"):
                monthly[k]["lost"] += 1
        for k in sorted(monthly.keys())[-12:]:
            m = monthly[k]
            closed = m["won"] + m["lost"]
            pct = round(m["won"] / closed * 100, 1) if closed > 0 else 0
            rows.append({"label": k, "value": pct, "won": m["won"], "total": m["total"]})

    elif metric_id == "license_expiry_timeline":
        from datetime import date as date_
        from app.models.alm import ALMLicense
        today = date_.today()
        end = today.replace(month=12, day=31) if today.month <= 6 else today.replace(year=today.year + 1, month=6, day=30)
        lics = db.query(ALMLicense).filter(ALMLicense.expiry_date.isnot(None), ALMLicense.expiry_date >= today, ALMLicense.expiry_date <= end, ALMLicense.status != "cancelled").all()
        monthly = {}
        for lic in lics:
            k = str(lic.expiry_date)[:7]
            if k not in monthly:
                monthly[k] = 0
            monthly[k] += 1
        rows = [{"label": k, "value": v} for k, v in sorted(monthly.items())]

    elif metric_id == "assets_by_type":
        from app.models.alm import ALMAsset
        ASSET_TYPE_LABELS = {"laptop": "Portátil", "desktop": "Sobremesa", "server": "Servidor", "phone": "Teléfono", "tablet": "Tablet", "monitor": "Monitor", "printer": "Impresora", "other": "Otro"}
        rows_raw = db.query(ALMAsset.type, func.count(ALMAsset.id).label("n")).filter(ALMAsset.status != "retired").group_by(ALMAsset.type).all()
        rows = [{"label": ASSET_TYPE_LABELS.get(str(r.type).replace("AssetType.", ""), str(r.type)), "value": r.n} for r in rows_raw]

    elif metric_id == "semantic_accuracy_trend":
        from app.models.semantic_engine import SemAssignment
        monthly = {}
        for sa in db.query(SemAssignment).filter(SemAssignment.was_accepted.isnot(None)).all():
            k = str(sa.created_at)[:7] if sa.created_at else "unknown"
            if k not in monthly:
                monthly[k] = {"accepted": 0, "total": 0}
            monthly[k]["total"] += 1
            if sa.was_accepted:
                monthly[k]["accepted"] += 1
        for k in sorted(monthly.keys())[-12:]:
            m = monthly[k]
            pct = round(m["accepted"] / m["total"] * 100, 1) if m["total"] > 0 else 0
            rows.append({"label": k, "value": pct, "accepted": m["accepted"], "total": m["total"]})

    elif metric_id == "semantic_assignments_by_mode":
        from app.models.semantic_engine import SemAssignment
        MODE_LABELS = {"semantic": "Semántico", "llm": "LLM", "hybrid": "Híbrido", "expert_cache_exact": "Cache exacto", "expert_cache_semantic": "Cache semántico", "rules_only": "Solo reglas"}
        rows_raw = db.query(SemAssignment.engine_mode, func.count(SemAssignment.id).label("n")).group_by(SemAssignment.engine_mode).all()
        rows = [{"label": MODE_LABELS.get(r.engine_mode or "", r.engine_mode or "Desconocido"), "value": r.n} for r in rows_raw if r.engine_mode]

    return rows, meta_patch
