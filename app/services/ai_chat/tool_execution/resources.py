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


def _get_imputations(tool_input, db, user, now, is_financial_role):
    q = db.query(Imputation)
    if tool_input.get("project_id"):
        pid = tool_input["project_id"]
        p = db.query(Project).filter(
            or_(Project.id == pid, Project.name.ilike(f"%{pid}%"), Project.code.ilike(f"%{pid}%"))
        ).first()
        if p: q = q.filter(Imputation.project_id == p.id)
    if tool_input.get("user_name"):
        u = db.query(User).filter(User.full_name.ilike(f"%{tool_input['user_name']}%")).first()
        if u: q = q.filter(Imputation.user_id == u.id)
    if tool_input.get("date_from"):
        from datetime import date as _date
        q = q.filter(Imputation.date >= _date.fromisoformat(tool_input["date_from"]))
    if tool_input.get("date_to"):
        from datetime import date as _date
        q = q.filter(Imputation.date <= _date.fromisoformat(tool_input["date_to"]))
    imps = q.order_by(Imputation.date.desc()).limit(tool_input.get("limit", 50)).all()
    group_by = tool_input.get("group_by")
    if group_by == "user":
        agg = {}
        for i in imps:
            agg.setdefault(i.user_id, {"user_id": i.user_id, "hours": 0, "cost": 0, "entries": 0})
            agg[i.user_id]["hours"] = round(agg[i.user_id]["hours"] + (i.hours or 0), 2)
            agg[i.user_id]["cost"] = round(agg[i.user_id]["cost"] + (i.cost_amount or 0), 2)
            agg[i.user_id]["entries"] += 1
        user_ids = list(agg.keys())
        umap = {u.id: u.full_name for u in db.query(User).filter(User.id.in_(user_ids)).all()}
        for v in agg.values(): v["user_name"] = umap.get(v["user_id"], "?")
        return {"grouped_by": "user", "data": sorted(agg.values(), key=lambda x: -x["hours"])}
    elif group_by == "project":
        agg = {}
        for i in imps:
            agg.setdefault(i.project_id, {"project_id": i.project_id, "hours": 0, "cost": 0})
            agg[i.project_id]["hours"] = round(agg[i.project_id]["hours"] + (i.hours or 0), 2)
            agg[i.project_id]["cost"] = round(agg[i.project_id]["cost"] + (i.cost_amount or 0), 2)
        proj_ids = list(agg.keys())
        pmap = {p.id: f"{p.code} {p.name}" for p in db.query(Project).filter(Project.id.in_(proj_ids)).all()}
        for v in agg.values(): v["project_name"] = pmap.get(v["project_id"], "?")
        return {"grouped_by": "project", "data": sorted(agg.values(), key=lambda x: -x["hours"])}
    else:
        user_ids = {i.user_id for i in imps}
        proj_ids = {i.project_id for i in imps}
        umap = {u.id: u.full_name for u in db.query(User).filter(User.id.in_(user_ids)).all()}
        pmap = {p.id: p.name for p in db.query(Project).filter(Project.id.in_(proj_ids)).all()}
        total_hours = sum(i.hours or 0 for i in imps)
        total_cost = sum(i.cost_amount or 0 for i in imps)
        return {
            "total_hours": round(total_hours, 2),
            "total_cost": round(total_cost, 2),
            "entries": [{
                "date": str(i.date), "hours": i.hours,
                "cost": i.cost_amount, "billable": i.is_billable,
                "user": umap.get(i.user_id, "?"),
                "project": pmap.get(i.project_id, "?"),
                "description": (i.description or "")[:80],
            } for i in imps]
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
