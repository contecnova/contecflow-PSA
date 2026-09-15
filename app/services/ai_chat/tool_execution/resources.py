"""Herramientas de recursos: disponibilidad, usuarios, imputaciones, ausencias, timesheets, skills y planes de capacidad."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, or_

from app.core.config import settings
from app.models.financial import Timesheet
from app.models.imputation import Imputation
from app.models.project import Project
from app.models.resources import Skill, UserSkill, Absence
from app.models.user import User, UserRole


def _get_resource_availability(tool_input, db, user, now, is_financial_role):
    users = db.query(User).filter(User.is_active == True).limit(30).all()
    week_start = (now - timedelta(days=now.weekday())).date()
    if tool_input.get("week_offset", 0):
        week_start += timedelta(weeks=tool_input["week_offset"])
    week_end = week_start + timedelta(days=6)
    result = []
    for u in users:
        hours = db.query(func.sum(Imputation.hours)).filter(
            Imputation.user_id == u.id,
            Imputation.date >= week_start, Imputation.date <= week_end,
        ).scalar() or 0
        cap = u.weekly_capacity_hours or settings.DEFAULT_WEEKLY_CAPACITY_HOURS
        result.append({"id": u.id, "name": u.full_name, "role": u.role,
                       "hours_logged": round(hours, 1), "capacity": cap,
                       "utilization_pct": round(hours / cap * 100, 1) if cap else 0})
    result.sort(key=lambda x: x["hours_logged"])
    return {"resources": result, "week": str(week_start)}


def _get_users_list(tool_input, db, user, now, is_financial_role):
    q = db.query(User)
    if tool_input.get("active_only", True): q = q.filter(User.is_active == True)
    if tool_input.get("role"): q = q.filter(User.role == tool_input["role"])
    users = q.order_by(User.full_name).limit(50).all()
    can_see_rates = user.role in (UserRole.admin, UserRole.hr)
    return {"users": [{
        "id": u.id, "name": u.full_name, "email": u.email,
        "role": u.role, "department": getattr(u, "department", None),
        "hourly_rate": getattr(u, "hourly_rate", None) if can_see_rates else None,
    } for u in users]}


def _filtrar_imputaciones(tool_input, db):
    """Aplica los filtros que traiga la herramienta y devuelve las imputaciones.

    El proyecto y el usuario se buscan por **texto aproximado** a propósito: la
    herramienta la invoca un modelo de lenguaje, que pasa lo que el usuario
    escribió («el proyecto de Acme»), no un identificador. Si la búsqueda no
    encaja con nada, el filtro **no se aplica** — y eso es deliberado: es lo
    que hacía, y devolver todo es más útil que devolver vacío sin explicación.
    """
    from datetime import date as _date

    q = db.query(Imputation)

    pid = tool_input.get("project_id")
    if pid:
        proyecto = db.query(Project).filter(or_(
            Project.id == pid,
            Project.name.ilike(f"%{pid}%"),
            Project.code.ilike(f"%{pid}%"),
        )).first()
        if proyecto:
            q = q.filter(Imputation.project_id == proyecto.id)

    nombre = tool_input.get("user_name")
    if nombre:
        usuario = db.query(User).filter(User.full_name.ilike(f"%{nombre}%")).first()
        if usuario:
            q = q.filter(Imputation.user_id == usuario.id)

    if tool_input.get("date_from"):
        q = q.filter(Imputation.date >= _date.fromisoformat(tool_input["date_from"]))
    if tool_input.get("date_to"):
        q = q.filter(Imputation.date <= _date.fromisoformat(tool_input["date_to"]))

    return q.order_by(Imputation.date.desc()).limit(tool_input.get("limit", 50)).all()


def _agrupar_imputaciones(imps, db, por: str) -> dict:
    """Suma horas y coste por usuario o por proyecto.

    Los nombres se resuelven en **una** consulta por lote y no una por fila: con
    cincuenta imputaciones eso es la diferencia entre dos consultas y cien.
    """
    campo = "user_id" if por == "user" else "project_id"
    agregado: dict = {}
    for i in imps:
        clave = getattr(i, campo)
        fila = agregado.setdefault(clave, {campo: clave, "hours": 0, "cost": 0, "entries": 0})
        fila["hours"] = round(fila["hours"] + (i.hours or 0), 2)
        fila["cost"] = round(fila["cost"] + (i.cost_amount or 0), 2)
        fila["entries"] += 1

    ids = list(agregado.keys())
    if por == "user":
        nombres = {u.id: u.full_name for u in db.query(User).filter(User.id.in_(ids)).all()}
        etiqueta = "user_name"
    else:
        nombres = {
            p.id: f"{p.code} {p.name}"
            for p in db.query(Project).filter(Project.id.in_(ids)).all()
        }
        etiqueta = "project_name"
    for fila in agregado.values():
        fila[etiqueta] = nombres.get(fila[campo], "?")

    return {
        "grouped_by": por,
        "data": sorted(agregado.values(), key=lambda x: -x["hours"]),
    }


def _get_imputations(tool_input, db, user, now, is_financial_role):
    """Imputaciones de horas, en detalle o agrupadas por usuario o proyecto."""
    imps = _filtrar_imputaciones(tool_input, db)

    agrupar = tool_input.get("group_by")
    if agrupar in ("user", "project"):
        return _agrupar_imputaciones(imps, db, agrupar)

    nombres_usuario = {
        u.id: u.full_name
        for u in db.query(User).filter(User.id.in_({i.user_id for i in imps})).all()
    }
    nombres_proyecto = {
        p.id: p.name
        for p in db.query(Project).filter(Project.id.in_({i.project_id for i in imps})).all()
    }
    return {
        "total_hours": round(sum(i.hours or 0 for i in imps), 2),
        "total_cost": round(sum(i.cost_amount or 0 for i in imps), 2),
        "entries": [{
            "date": str(i.date), "hours": i.hours,
            "cost": i.cost_amount, "billable": i.is_billable,
            "user": nombres_usuario.get(i.user_id, "?"),
            "project": nombres_proyecto.get(i.project_id, "?"),
            "description": (i.description or "")[:80],
        } for i in imps],
    }


def _get_absences(tool_input, db, user, now, is_financial_role):
    q = db.query(Absence)
    if tool_input.get("user_name"):
        u = db.query(User).filter(User.full_name.ilike(f"%{tool_input['user_name']}%")).first()
        if u: q = q.filter(Absence.user_id == u.id)
    if tool_input.get("date_from"):
        from datetime import date as _date
        q = q.filter(Absence.end_date >= _date.fromisoformat(tool_input["date_from"]))
    if tool_input.get("date_to"):
        from datetime import date as _date
        q = q.filter(Absence.start_date <= _date.fromisoformat(tool_input["date_to"]))
    status = tool_input.get("status", "")
    if status and status != "all": q = q.filter(Absence.status == status)
    else: q = q.filter(Absence.status.notin_(["cancelled"]))
    absences = q.order_by(Absence.start_date.desc()).limit(tool_input.get("limit", 30)).all()
    user_ids = {a.user_id for a in absences}
    umap = {u.id: u.full_name for u in db.query(User).filter(User.id.in_(user_ids)).all()}
    return {"absences": [{
        "id": a.id, "user": umap.get(a.user_id, "?"),
        "type": str(a.type), "status": str(a.status),
        "start_date": str(a.start_date), "end_date": str(a.end_date),
        "working_days": a.working_days, "reason": a.reason,
    } for a in absences]}


def _get_timesheets(tool_input, db, user, now, is_financial_role):
    q = db.query(Timesheet)
    status = tool_input.get("status", "")
    if status and status != "all": q = q.filter(Timesheet.status == status)
    if tool_input.get("user_name"):
        u = db.query(User).filter(User.full_name.ilike(f"%{tool_input['user_name']}%")).first()
        if u: q = q.filter(Timesheet.user_id == u.id)
    if tool_input.get("week_from"):
        from datetime import date as _date
        q = q.filter(Timesheet.week_start >= _date.fromisoformat(tool_input["week_from"]))
    timesheets = q.order_by(Timesheet.week_start.desc()).limit(tool_input.get("limit", 30)).all()
    user_ids = {t.user_id for t in timesheets}
    umap = {u.id: u.full_name for u in db.query(User).filter(User.id.in_(user_ids)).all()}
    return {"timesheets": [{
        "id": ts.id, "user": umap.get(ts.user_id, "?"),
        "week_start": str(ts.week_start), "week_end": str(ts.week_end),
        "status": str(ts.status), "total_hours": ts.total_hours,
        "billable_hours": ts.billable_hours, "total_cost": ts.total_cost,
    } for ts in timesheets]}


def _get_skills(tool_input, db, user, now, is_financial_role):
    q = db.query(UserSkill).join(Skill, UserSkill.skill_id == Skill.id)
    if tool_input.get("skill_name"):
        q = q.filter(Skill.name.ilike(f"%{tool_input['skill_name']}%"))
    if tool_input.get("category"):
        q = q.filter(Skill.category == tool_input["category"])
    if tool_input.get("user_name"):
        u = db.query(User).filter(User.full_name.ilike(f"%{tool_input['user_name']}%")).first()
        if u: q = q.filter(UserSkill.user_id == u.id)
    user_skills = q.limit(50).all()
    skill_ids = {us.skill_id for us in user_skills}
    user_ids = {us.user_id for us in user_skills}
    skill_map = {s.id: s for s in db.query(Skill).filter(Skill.id.in_(skill_ids)).all()}
    user_map = {u.id: u.full_name for u in db.query(User).filter(User.id.in_(user_ids)).all()}
    return {"skills": [{
        "user": user_map.get(us.user_id, "?"),
        "skill": skill_map[us.skill_id].name if us.skill_id in skill_map else "?",
        "category": str(skill_map[us.skill_id].category) if us.skill_id in skill_map else None,
        "level": str(us.level) if us.level else None,
    } for us in user_skills]}


def _get_capacity_plans(tool_input, db, user, now, is_financial_role):
    from app.models.financial import CapacityPlan
    from datetime import date as _date
    q = db.query(CapacityPlan)
    if tool_input.get("user_name"):
        u = db.query(User).filter(User.full_name.ilike(f"%{tool_input['user_name']}%")).first()
        if u: q = q.filter(CapacityPlan.user_id == u.id)
    if tool_input.get("project_id"):
        q = q.filter(CapacityPlan.project_id == tool_input["project_id"])
    if tool_input.get("week_from"):
        q = q.filter(CapacityPlan.week_start >= _date.fromisoformat(tool_input["week_from"]))
    if tool_input.get("week_to"):
        q = q.filter(CapacityPlan.week_start <= _date.fromisoformat(tool_input["week_to"]))
    plans = q.order_by(CapacityPlan.week_start.desc()).limit(tool_input.get("limit", 40)).all()
    user_ids = {p.user_id for p in plans}
    proj_ids = {p.project_id for p in plans if p.project_id}
    umap = {u.id: u.full_name for u in db.query(User).filter(User.id.in_(user_ids)).all()}
    pmap = {p.id: p.name for p in db.query(Project).filter(Project.id.in_(proj_ids)).all()}
    total_hours = sum(p.planned_hours or 0 for p in plans)
    return {
        "total_planned_hours": round(total_hours, 2),
        "plans": [{
            "id": p.id,
            "user": umap.get(p.user_id, "?"),
            "project": pmap.get(p.project_id, "?") if p.project_id else None,
            "week_start": str(p.week_start),
            "planned_hours": p.planned_hours,
            "notes": p.notes,
        } for p in plans]
    }


HANDLERS = {
    "get_resource_availability": _get_resource_availability,
    "get_users_list": _get_users_list,
    "get_imputations": _get_imputations,
    "get_absences": _get_absences,
    "get_timesheets": _get_timesheets,
    "get_skills": _get_skills,
    "get_capacity_plans": _get_capacity_plans,
}
