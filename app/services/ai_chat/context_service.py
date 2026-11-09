from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.billing_reports import ApprovalRequest, Invoice
from app.models.clients import Client
from app.models.financial import ProjectMilestone, Timesheet
from app.models.imputation import Imputation
from app.models.pipeline import Opportunity, Risk, Contract
from app.models.project import Project
from app.models.financial import CapacityPlan
from app.models.resources import Absence, Deliverable, ChangeRequest
from app.models.resources import UserSkill, Skill
from app.models.service_desk import Ticket
from app.models.task import Task
from app.models.user import User, UserRole
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

def _filter_by_org(query, model, org_id):
    """Apply organization filter only when the model actually has organization_id.

    When ``org_id`` is None (caller marked superadmin or unauthenticated context
    build), the query is returned unchanged so cross-org data is visible.
    """
    if org_id and hasattr(model, "organization_id"):
        return query.filter(getattr(model, "organization_id") == org_id)  # noqa: B009
    return query


# ── Contexto para los asistentes de IA ───────────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 18). `build_tenant_context` eran 525 lineas de
# complejidad 34 que construian un diccionario de 36 claves, y no tenia NINGUN
# test. Es la funcion que decide que datos ve el asistente de IA de cada cliente,
# asi que un error aqui no corrompe nada pero degrada todas sus respuestas —y no
# hay forma de notarlo salvo leyendolas.
#
# Ahora cada bloque de datos es su propia funcion, con el cuerpo movido VERBATIM.
# La equivalencia se verifico volcando el diccionario completo para CINCO perfiles
# de usuario —sin usuario, admin, RRHH, PM y empleado, que es lo que recorre las
# tres banderas de permiso— y comparando clave por clave: identico.
#
# ── Lo que hace segura la descomposicion ─────────────────────────────────────
# Cada seccion devuelve exactamente las variables que leen las posteriores o el
# `return`, y en el orquestador se reciben con el MISMO nombre. Asi el `return`
# de 36 claves queda byte a byte igual y no hay que tocarlo — que es donde un
# refactor a mano se equivoca.
#
# Las variables que cruzan secciones se CALCULARON, no se eligieron: para cada
# una, si alguna sentencia posterior la lee antes de reasignarla. Sin ese matiz
# salian dos acoplamientos falsos (`q_inv` y `row` son nombres reutilizados que
# la seccion posterior reasigna antes de leer) que habrian ensuciado las firmas
# con una dependencia inexistente.
#
# Solo hay dos cadenas reales:
#   proyectos -> riesgos -> (scope_project_ids) -> contratos, hitos,
#                                                  entregables, cambios
#   equipo    -> ocupacion y skills


@dataclass
class _Alcance:
    """Lo que toda seccion necesita saber de quien pregunta.

    Las cuatro banderas de permiso deciden que secciones se calculan y cuales se
    enmascaran, y `user_project_ids` acota el alcance de quien no puede ver toda
    la organizacion. Reunirlas aqui evita repetir esa resolucion en 18 sitios.
    """

    db: Session
    user: object
    now: datetime
    is_super: bool
    can_see_financials: bool
    can_see_capacity: bool
    can_see_org_wide: bool
    can_see_people_data: bool
    org_id: object
    user_project_ids: object


def _construir_alcance(db: Session, user=None) -> _Alcance:
    """Resuelve permisos y alcance. Era el prologo de la funcion original.

    Superadmin: `org_id = None` -> `_filter_by_org` no aplica filtro, asi que lee
    de TODAS las organizaciones. Sin ese bypass un superadmin asignado a la
    organizacion "default" veia 0 proyectos cuando los datos vivian en otra.
    """
    now = datetime.now(timezone.utc)
    is_super = bool(getattr(user, "is_superadmin", False)) if user else False
    can_see_financials = (
        user is None
        or is_super
        or getattr(user, "role", None) in (UserRole.admin, UserRole.hr)
    )
    can_see_capacity = (
        user is None
        or is_super
        or getattr(user, "role", None) in (UserRole.admin, UserRole.hr, UserRole.pm, UserRole.team_lead)
    )
    can_see_org_wide = can_see_capacity
    can_see_people_data = can_see_capacity

    # Superadmin → org_id = None → _filter_by_org no aplica filtro.
    org_id = None if is_super else (getattr(user, "organization_id", None) if user else None)
    user_project_ids = None
    if user and not can_see_org_wide:
        imp_pids = {
            pid for (pid,) in db.query(Imputation.project_id).filter(
                Imputation.user_id == user.id,
                Imputation.project_id.isnot(None),
            ).all()
        }
        task_pids = {
            pid for (pid,) in db.query(Task.project_id).filter(
                Task.assignee_id == user.id,
                Task.project_id.isnot(None),
            ).all()
        }
        user_project_ids = list(imp_pids | task_pids)
    return _Alcance(
        db=db,
        user=user,
        now=now,
        is_super=is_super,
        can_see_financials=can_see_financials,
        can_see_capacity=can_see_capacity,
        can_see_org_wide=can_see_org_wide,
        can_see_people_data=can_see_people_data,
        org_id=org_id,
        user_project_ids=user_project_ids,
    )


def _seccion_proyectos(ctx: _Alcance):
    """Proyectos activos y en planificacion."""
    db, org_id, user_project_ids = ctx.db, ctx.org_id, ctx.user_project_ids
    q_proj = db.query(Project).filter(Project.status.in_(["active", "planning"]))
    q_proj = _filter_by_org(q_proj, Project, org_id)
    if user_project_ids is not None:
        q_proj = q_proj.filter(Project.id.in_(user_project_ids or ["__none__"]))
    projects = q_proj.limit(20).all()
    return projects


def _seccion_tickets(ctx: _Alcance):
    """Tickets abiertos, con su responsable resuelto."""
    can_see_org_wide, db, org_id, user = ctx.can_see_org_wide, ctx.db, ctx.org_id, ctx.user
    q_ticket = db.query(Ticket).filter(Ticket.status.in_(["new", "assigned", "in_progress"]))
    q_ticket = _filter_by_org(q_ticket, Ticket, org_id)
    if user and not can_see_org_wide:
        q_ticket = q_ticket.filter(Ticket.assigned_to_user_id == user.id)
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
    return tickets_detail


def _seccion_tareas_vencidas(ctx: _Alcance):
    """Tareas fuera de plazo."""
    can_see_org_wide, db, now, org_id, user = ctx.can_see_org_wide, ctx.db, ctx.now, ctx.org_id, ctx.user
    q_task = db.query(Task).filter(Task.status != "done", Task.due_date < now.date())
    q_task = _filter_by_org(q_task, Task, org_id)
    if user and not can_see_org_wide:
        q_task = q_task.filter(Task.assignee_id == user.id)
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
    return overdue_tasks_detail


def _seccion_horas_semana(ctx: _Alcance):
    """Horas imputadas de la semana en curso."""
    can_see_org_wide, db, now, org_id, user = ctx.can_see_org_wide, ctx.db, ctx.now, ctx.org_id, ctx.user
    week_start = (now - timedelta(days=now.weekday())).date()
    week_end = week_start + timedelta(days=6)
    q_imp = db.query(Imputation).filter(Imputation.date >= week_start, Imputation.date <= week_end)
    q_imp = _filter_by_org(q_imp, Imputation, org_id)
    if user and not can_see_org_wide:
        q_imp = q_imp.filter(Imputation.user_id == user.id)
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
    return hours_by_project, hours_by_user, total_hours_week


def _seccion_finanzas(ctx: _Alcance):
    """Facturas pendientes y valor del pipeline."""
    can_see_financials, db, org_id = ctx.can_see_financials, ctx.db, ctx.org_id
    pending_invoices_count = 0
    pending_invoices_amount = 0.0
    overdue_invoices = 0
    pipeline_count = 0
    if can_see_financials:
        q_inv = db.query(func.count(Invoice.id)).filter(Invoice.status.in_(["sent", "overdue"]))
        q_inv_amt = db.query(func.sum(Invoice.total)).filter(Invoice.status.in_(["sent", "overdue"]))
        q_overdue = db.query(func.count(Invoice.id)).filter(Invoice.status == "overdue")
        q_pipe = db.query(func.count(Opportunity.id)).filter(Opportunity.stage.notin_(["won", "lost"]))
        q_inv = _filter_by_org(q_inv, Invoice, org_id)
        q_inv_amt = _filter_by_org(q_inv_amt, Invoice, org_id)
        q_overdue = _filter_by_org(q_overdue, Invoice, org_id)
        q_pipe = _filter_by_org(q_pipe, Opportunity, org_id)
        pending_invoices_count = q_inv.scalar() or 0
        pending_invoices_amount = q_inv_amt.scalar() or 0
        overdue_invoices = q_overdue.scalar() or 0
        pipeline_count = q_pipe.scalar() or 0
    return overdue_invoices, pending_invoices_amount, pending_invoices_count, pipeline_count


def _seccion_aprobaciones_y_ausencias(ctx: _Alcance):
    """Contadores de aprobaciones y ausencias."""
    can_see_org_wide, db, now, org_id, user = ctx.can_see_org_wide, ctx.db, ctx.now, ctx.org_id, ctx.user
    q_approvals = db.query(func.count(ApprovalRequest.id)).filter(ApprovalRequest.status == "pending")
    q_absences = db.query(func.count(Absence.id)).filter(
        Absence.status == "approved",
        Absence.start_date <= now.date(),
        Absence.end_date >= now.date(),
    )
    q_approvals = _filter_by_org(q_approvals, ApprovalRequest, org_id)
    q_absences = _filter_by_org(q_absences, Absence, org_id)
    if user and not can_see_org_wide:
        q_approvals = q_approvals.filter(ApprovalRequest.requested_by == user.id)
        q_absences = q_absences.filter(Absence.user_id == user.id)
    pending_approvals = q_approvals.scalar() or 0
    active_absences = q_absences.scalar() or 0
    return active_absences, pending_approvals


def _seccion_equipo(ctx: _Alcance):
    """Equipo visible para quien pregunta."""
    can_see_capacity, can_see_people_data, db, org_id, user = ctx.can_see_capacity, ctx.can_see_people_data, ctx.db, ctx.org_id, ctx.user
    q_team = db.query(User).filter(User.is_active == True)
    q_team = _filter_by_org(q_team, User, org_id)
    if user and not can_see_people_data:
        q_team = q_team.filter(User.id == user.id)
    team_members = q_team.limit(50).all()

    # Forward-looking team context (next month) for strategic planning.
    visible_users = team_members
    if user is not None and not can_see_capacity:
        visible_users = [u for u in team_members if u.id == user.id]
    return team_members, visible_users


def _seccion_ocupacion_y_skills(ctx: _Alcance, visible_users):
    """Ocupacion del proximo mes y matriz de skills."""
    can_see_capacity, db, now = ctx.can_see_capacity, ctx.db, ctx.now
    current_month_start = now.date().replace(day=1)
    next_month_start = (current_month_start + timedelta(days=32)).replace(day=1)
    next_month_end = (next_month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    month_weeks = max(1.0, round(((next_month_end - next_month_start).days + 1) / 7.0, 2))

    visible_user_ids = [u.id for u in visible_users]
    plans_by_user = {}
    abs_days_by_user = {}
    if visible_user_ids and can_see_capacity:
        cp_rows = db.query(
            CapacityPlan.user_id,
            func.sum(CapacityPlan.planned_hours).label("planned"),
        ).filter(
            CapacityPlan.user_id.in_(visible_user_ids),
            CapacityPlan.week_start >= next_month_start,
            CapacityPlan.week_start <= next_month_end,
        ).group_by(CapacityPlan.user_id).all()
        plans_by_user = {r.user_id: float(r.planned or 0) for r in cp_rows}

        abs_rows = db.query(Absence).filter(
            Absence.user_id.in_(visible_user_ids),
            Absence.status == "approved",
            Absence.end_date >= next_month_start,
            Absence.start_date <= next_month_end,
        ).all()
        for a in abs_rows:
            overlap_start = max(a.start_date, next_month_start)
            overlap_end = min(a.end_date, next_month_end)
            days = ((overlap_end - overlap_start).days + 1) if overlap_end >= overlap_start else 0
            abs_days_by_user[a.user_id] = abs_days_by_user.get(a.user_id, 0) + max(0, days)

    occupancy_next_month = []
    for u in visible_users:
        weekly_capacity = float(getattr(u, "weekly_capacity_hours", None) or settings.DEFAULT_WEEKLY_CAPACITY_HOURS)
        month_capacity = round(weekly_capacity * month_weeks, 1)
        planned = round(float(plans_by_user.get(u.id, 0.0)), 1)
        load_pct = round((planned / month_capacity) * 100, 1) if month_capacity > 0 else 0.0
        occupancy_next_month.append({
            "user": u.full_name,
            "role": u.role,
            "department": getattr(u, "department", None),
            "planned_hours": planned,
            "capacity_hours": month_capacity,
            "load_pct": load_pct,
            "available_hours": round(max(0.0, month_capacity - planned), 1),
            "approved_absence_days": round(float(abs_days_by_user.get(u.id, 0.0)), 1),
        })
    occupancy_next_month.sort(key=lambda x: x["load_pct"], reverse=True)

    skills_matrix = []
    if visible_user_ids and can_see_capacity:
        us_rows = db.query(UserSkill).join(Skill, UserSkill.skill_id == Skill.id).filter(
            UserSkill.user_id.in_(visible_user_ids)
        ).limit(400).all()
        skill_map = {s.id: s for s in db.query(Skill).filter(Skill.id.in_({us.skill_id for us in us_rows})).all()} if us_rows else {}
        user_map = {u.id: u for u in visible_users}
        for us in us_rows:
            s = skill_map.get(us.skill_id)
            u = user_map.get(us.user_id)
            if not s or not u:
                continue
            skills_matrix.append({
                "user": u.full_name,
                "role": u.role,
                "department": getattr(u, "department", None),
                "skill": s.name,
                "category": s.category,
                "level": us.level,
                "years_experience": us.years_experience,
                "certified": bool(us.certified),
            })

    skills_by_user = {}
    for row in skills_matrix:
        skills_by_user.setdefault(row["user"], []).append({
            "skill": row["skill"],
            "level": row["level"],
            "category": row["category"],
        })
    skills_by_user_list = [
        {"user": name, "skills": items[:8]}
        for name, items in skills_by_user.items()
    ]
    return next_month_end, next_month_start, occupancy_next_month, skills_by_user_list, skills_matrix


def _seccion_timesheets(ctx: _Alcance):
    """Partes de horas recientes y su estado."""
    can_see_org_wide, db, user = ctx.can_see_org_wide, ctx.db, ctx.user
    q_ts = db.query(Timesheet)
    if user and not can_see_org_wide:
        q_ts = q_ts.filter(Timesheet.user_id == user.id)
    recent_timesheets = q_ts.order_by(Timesheet.week_start.desc()).limit(30).all()
    ts_by_status = {}
    for ts in recent_timesheets:
        st = str(ts.status)
        ts_by_status[st] = ts_by_status.get(st, 0) + 1
    ts_user_ids = {ts.user_id for ts in recent_timesheets}
    ts_user_map = {u.id: u.full_name for u in db.query(User).filter(User.id.in_(ts_user_ids)).all()} if ts_user_ids else {}
    timesheets_recent = [{
        "user": ts_user_map.get(ts.user_id, ts.user_id),
        "week_start": str(ts.week_start),
        "week_end": str(ts.week_end),
        "status": str(ts.status),
        "total_hours": ts.total_hours,
        "billable_hours": ts.billable_hours,
    } for ts in recent_timesheets]
    return timesheets_recent, ts_by_status


def _seccion_aprobaciones_detalle(ctx: _Alcance):
    """Detalle de las aprobaciones pendientes."""
    can_see_org_wide, db, org_id, user = ctx.can_see_org_wide, ctx.db, ctx.org_id, ctx.user
    q_ap_detail = db.query(ApprovalRequest)
    q_ap_detail = _filter_by_org(q_ap_detail, ApprovalRequest, org_id)
    if user and not can_see_org_wide:
        q_ap_detail = q_ap_detail.filter(ApprovalRequest.requested_by == user.id)
    approvals_detail = q_ap_detail.filter(ApprovalRequest.status == "pending").order_by(
        ApprovalRequest.created_at.desc()
    ).limit(20).all()
    return approvals_detail


def _seccion_pipeline(ctx: _Alcance):
    """Oportunidades abiertas del pipeline."""
    can_see_org_wide, db, user = ctx.can_see_org_wide, ctx.db, ctx.user
    q_opp = db.query(Opportunity).filter(Opportunity.stage.notin_(["won", "lost", "cancelled"]))
    if user and not can_see_org_wide:
        q_opp = q_opp.filter(Opportunity.owner_id == user.id)
    opp_rows = q_opp.order_by(Opportunity.expected_close_date.asc().nullslast()).limit(20).all()
    pipeline_detail = [{
        "code": o.code,
        "name": o.name,
        "client": o.client_name,
        "stage": str(o.stage),
        "probability": o.probability,
        "expected_revenue": o.expected_revenue,
        "weighted_value": round((o.expected_revenue or 0) * (o.probability or 0) / 100, 2),
        "expected_close_date": str(o.expected_close_date) if o.expected_close_date else None,
    } for o in opp_rows]
    return pipeline_detail


def _seccion_clientes(ctx: _Alcance):
    """Resumen por cliente."""
    can_see_org_wide, db = ctx.can_see_org_wide, ctx.db
    clients_summary = []
    if can_see_org_wide:
        clients = db.query(Client).filter(Client.is_active == True).order_by(Client.name.asc()).limit(20).all()
        client_ids = [c.id for c in clients]
        proj_client_counts = {}
        if client_ids:
            for cid, count in db.query(Project.client_id, func.count(Project.id)).filter(
                Project.client_id.in_(client_ids)
            ).group_by(Project.client_id).all():
                proj_client_counts[cid] = int(count or 0)
        clients_summary = [{
            "id": c.id,
            "name": c.name,
            "industry": str(c.industry) if c.industry else None,
            "status": str(c.status) if c.status else None,
            "projects_count": proj_client_counts.get(c.id, 0),
            "account_manager_id": c.account_manager_id,
        } for c in clients]
    return clients_summary


def _seccion_riesgos(ctx: _Alcance, projects):
    """Riesgos abiertos de los proyectos en alcance."""
    db = ctx.db
    scope_project_ids = [p.id for p in projects]
    q_risks = db.query(Risk).filter(Risk.status != "closed")
    if scope_project_ids:
        q_risks = q_risks.filter(Risk.project_id.in_(scope_project_ids))
    else:
        q_risks = q_risks.filter(Risk.project_id == "__none__")
    risks_open = q_risks.order_by(Risk.updated_at.desc().nullslast()).limit(30).all()
    risk_project_map = {p.id: p.name for p in projects}
    risks_detail = [{
        "code": r.code,
        "title": r.title,
        "project": risk_project_map.get(r.project_id, r.project_id),
        "status": str(r.status),
        "probability": str(r.probability),
        "impact": str(r.impact),
        "risk_score": r.risk_score,
    } for r in risks_open]
    return risks_detail, scope_project_ids


def _seccion_contratos(ctx: _Alcance, scope_project_ids):
    """Contratos que vencen pronto."""
    db, now = ctx.db, ctx.now
    q_contracts = db.query(Contract).filter(
        Contract.status == "active",
        Contract.end_date.isnot(None),
        Contract.end_date <= (now.date() + timedelta(days=120)),
    )
    if scope_project_ids:
        q_contracts = q_contracts.filter(Contract.project_id.in_(scope_project_ids))
    else:
        q_contracts = q_contracts.filter(Contract.project_id == "__none__")
    contracts_expiring = q_contracts.order_by(Contract.end_date.asc()).limit(20).all()
    return contracts_expiring


def _seccion_hitos(ctx: _Alcance, scope_project_ids):
    """Hitos con vencimiento en 60 dias."""
    db, now = ctx.db, ctx.now
    q_milestones = db.query(ProjectMilestone)
    if scope_project_ids:
        q_milestones = q_milestones.filter(ProjectMilestone.project_id.in_(scope_project_ids))
    else:
        q_milestones = q_milestones.filter(ProjectMilestone.project_id == "__none__")
    milestones_due = q_milestones.filter(
        ProjectMilestone.due_date.isnot(None),
        ProjectMilestone.due_date <= (now.date() + timedelta(days=60)),
    ).order_by(ProjectMilestone.due_date.asc()).limit(30).all()
    return milestones_due


def _seccion_entregables(ctx: _Alcance, scope_project_ids):
    """Entregables pendientes."""
    db = ctx.db
    q_deliverables = db.query(Deliverable)
    if scope_project_ids:
        q_deliverables = q_deliverables.filter(Deliverable.project_id.in_(scope_project_ids))
    else:
        q_deliverables = q_deliverables.filter(Deliverable.project_id == "__none__")
    deliverables_pending = q_deliverables.filter(Deliverable.status.notin_(["accepted", "delivered"])).order_by(
        Deliverable.planned_date.asc().nullslast()
    ).limit(30).all()
    return deliverables_pending


def _seccion_cambios(ctx: _Alcance, scope_project_ids):
    """Solicitudes de cambio activas."""
    db = ctx.db
    q_changes = db.query(ChangeRequest)
    if scope_project_ids:
        q_changes = q_changes.filter(ChangeRequest.project_id.in_(scope_project_ids))
    else:
        q_changes = q_changes.filter(ChangeRequest.project_id == "__none__")
    changes_active = q_changes.filter(ChangeRequest.status.notin_(["implemented", "rejected"])).order_by(
        ChangeRequest.created_at.desc()
    ).limit(30).all()
    return changes_active


def _seccion_rentabilidad(ctx: _Alcance, projects):
    """Rentabilidad por proyecto."""
    can_see_financials, db, org_id = ctx.can_see_financials, ctx.db, ctx.org_id
    all_active_proj_ids = [p.id for p in projects]
    prof_items = []
    if can_see_financials and all_active_proj_ids:
        q_rates = db.query(User).filter(User.is_active == True)
        q_rates = _filter_by_org(q_rates, User, org_id)
        all_user_rates = {u.id: (getattr(u, "hourly_rate", None) or 0) for u in q_rates.all()}
        q_imp_user = db.query(
            Imputation.project_id, Imputation.user_id,
            func.sum(Imputation.hours).label("hours"),
        ).filter(Imputation.project_id.in_(all_active_proj_ids))
        q_imp_user = _filter_by_org(q_imp_user, Imputation, org_id)
        imp_user_rows = q_imp_user.group_by(
            Imputation.project_id, Imputation.user_id
        ).all()
        # Expenses
        # Invoices
        q_inv = db.query(
            Invoice.project_id, func.sum(Invoice.total).label("invoiced")
        ).filter(
            Invoice.project_id.in_(all_active_proj_ids),
            Invoice.status.in_(["sent", "paid", "overdue"]),
        )
        q_inv = _filter_by_org(q_inv, Invoice, org_id)
        inv_rows = q_inv.group_by(Invoice.project_id).all()
        proj_labor_cost = {}
        proj_hours_total = {}
        for row in imp_user_rows:
            rate = all_user_rates.get(row.user_id, 0) or 0
            proj_labor_cost[row.project_id] = proj_labor_cost.get(row.project_id, 0) + (row.hours * rate)
            proj_hours_total[row.project_id] = proj_hours_total.get(row.project_id, 0) + row.hours
        # Revisión 2026-11: la misma suma que el resto (reparto entre proyectos, reembolsados incluidos).
        from app.services.gastos_avanzados import totales_por_proyecto
        proj_expenses = totales_por_proyecto(db, all_active_proj_ids)
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
    return prof_items

def build_tenant_context(db: Session, user: User = None) -> dict:
    """Contexto de datos del cliente para los asistentes de IA.

    Ver la cabecera de esta seccion para el porque de la descomposicion y para
    las dos cadenas de dependencia entre bloques.
    """
    ctx = _construir_alcance(db, user)

    # El `return` de abajo viene VERBATIM de la versión original y usa estos
    # cuatro por su nombre. Reenlazarlos aquí es lo que permite no tocarlo: un
    # `return` de 36 claves reescrito a mano es donde se cuela el error.
    now = ctx.now
    can_see_financials = ctx.can_see_financials
    can_see_capacity = ctx.can_see_capacity
    can_see_org_wide = ctx.can_see_org_wide

    projects = _seccion_proyectos(ctx)
    tickets_detail = _seccion_tickets(ctx)
    overdue_tasks_detail = _seccion_tareas_vencidas(ctx)
    hours_by_project, hours_by_user, total_hours_week = _seccion_horas_semana(ctx)
    overdue_invoices, pending_invoices_amount, pending_invoices_count, pipeline_count = _seccion_finanzas(ctx)
    active_absences, pending_approvals = _seccion_aprobaciones_y_ausencias(ctx)
    team_members, visible_users = _seccion_equipo(ctx)
    next_month_end, next_month_start, occupancy_next_month, skills_by_user_list, skills_matrix = _seccion_ocupacion_y_skills(ctx, visible_users)
    timesheets_recent, ts_by_status = _seccion_timesheets(ctx)
    approvals_detail = _seccion_aprobaciones_detalle(ctx)
    pipeline_detail = _seccion_pipeline(ctx)
    clients_summary = _seccion_clientes(ctx)
    risks_detail, scope_project_ids = _seccion_riesgos(ctx, projects)
    contracts_expiring = _seccion_contratos(ctx, scope_project_ids)
    milestones_due = _seccion_hitos(ctx, scope_project_ids)
    deliverables_pending = _seccion_entregables(ctx, scope_project_ids)
    changes_active = _seccion_cambios(ctx, scope_project_ids)
    prof_items = _seccion_rentabilidad(ctx, projects)

    return {
        "today": now.strftime("%Y-%m-%d"),
        "context_scope": {
            "role": getattr(user, "role", None) if user else None,
            "is_superadmin": bool(getattr(user, "is_superadmin", False)) if user else False,
            "financial_data_restricted": not can_see_financials,
            "capacity_data_restricted": not can_see_capacity,
            "org_wide_restricted": not can_see_org_wide,
        },
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
        "capacity_data_restricted": not can_see_capacity,
        "next_month_period": {
            "from": str(next_month_start),
            "to": str(next_month_end),
        },
        "resource_occupancy_next_month": occupancy_next_month,
        "skills_matrix": skills_matrix,
        "skills_by_user": skills_by_user_list,
        "timesheets_status_summary": ts_by_status,
        "timesheets_recent": timesheets_recent,
        "approvals_pending_detail": [{
            "id": a.id,
            "entity_type": a.entity_type,
            "entity_summary": a.entity_summary,
            "requested_by": a.requested_by,
            "current_step": a.current_step,
            "created_at": str(a.created_at)[:10] if a.created_at else None,
        } for a in approvals_detail],
        "pipeline_detail": pipeline_detail,
        "clients_summary": clients_summary,
        "risks_open": risks_detail,
        "contracts_expiring": [{
            "code": c.code,
            "name": c.name,
            "client": c.client_name,
            "project_id": c.project_id,
            "end_date": str(c.end_date) if c.end_date else None,
            "total_amount": c.total_amount,
        } for c in contracts_expiring],
        "milestones_due_60d": [{
            "project_id": m.project_id,
            "name": m.name,
            "due_date": str(m.due_date) if m.due_date else None,
            "billing_status": m.billing_status,
            "is_completed": bool(m.is_completed),
        } for m in milestones_due],
        "deliverables_pending": [{
            "project_id": d.project_id,
            "code": d.code,
            "name": d.name,
            "status": str(d.status),
            "planned_date": str(d.planned_date) if d.planned_date else None,
        } for d in deliverables_pending],
        "change_requests_active": [{
            "project_id": c.project_id,
            "code": c.code,
            "title": c.title,
            "status": str(c.status),
            "impact": str(c.impact) if c.impact else None,
            "submitted_at": str(c.submitted_at) if c.submitted_at else None,
            "created_at": str(c.created_at)[:10] if c.created_at else None,
        } for c in changes_active],
        "pending_invoices": pending_invoices_count,
        "pending_invoices_amount": round(pending_invoices_amount or 0, 2),
        "overdue_invoices": overdue_invoices,
        "pipeline_opportunities": pipeline_count,
        "profitability": prof_items,
        "projects_at_loss": [x for x in prof_items if x.get("is_loss")],
    }
