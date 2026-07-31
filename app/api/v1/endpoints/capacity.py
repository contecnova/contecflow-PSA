from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date, timedelta

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager
from app.core.abac_enforce import enforce_abac
from app.core.responses import APIResponse, APIListResponse
from app.models.user import User
from app.core.config import settings
from app.services.psa_flows import create_capacity_plan_flow
from app.services import capacity_service

router = APIRouter()

_get_weeks = capacity_service.get_weeks


@router.get("/overview", summary="Vista de capacidad futura del equipo")
def get_capacity_overview(
    weeks: int = Query(8, ge=1, le=26),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """
    Returns a grid: users x weeks with planned hours, actual hours and load %.
    """
    today = date.today()
    week_list = _get_weeks(today, weeks)

    users = capacity_service.get_active_users(db, current_user.organization_id)
    user_ids = [u.id for u in users]

    plans = capacity_service.get_plans_for_period(db, week_list[0], week_list[-1], user_ids)

    actual_data = capacity_service.get_actual_hours_by_week(
        db, week_list[0], week_list[-1] + timedelta(days=6)
    )

    # Build actual hours by user/week
    actual_by_user_week = {}
    for row in actual_data:
        uid = row.user_id
        week_raw = row.week

        if isinstance(week_raw, str):
            # SQLite: 'YYYY-WW'
            year, w = week_raw.split('-')
            week_num = int(w)
            if week_num == 0:
                continue
            week_start = date.fromisocalendar(int(year), week_num, 1)
        else:
            ws = week_raw.date() if hasattr(week_raw, 'date') else week_raw
            week_start = ws - timedelta(days=ws.weekday())

        key = (uid, str(week_start))
        actual_by_user_week[key] = actual_by_user_week.get(key, 0) + row.hours

    # Build planned hours by user/week
    planned_by_user_week = {}
    for p in plans:
        key = (p.user_id, str(p.week_start))
        planned_by_user_week[key] = planned_by_user_week.get(key, 0) + p.planned_hours

    result = []
    for user in users:
        weeks_data = []
        for ws in week_list:
            key = (user.id, str(ws))
            is_past = ws < today - timedelta(days=today.weekday())
            actual = actual_by_user_week.get(key, 0)
            planned = planned_by_user_week.get(key, 0)
            capacity = user.weekly_capacity_hours or settings.DEFAULT_WEEKLY_CAPACITY_HOURS
            hours = actual if is_past else planned
            load_pct = round((hours / capacity) * 100, 1) if capacity > 0 else 0
            weeks_data.append({
                "week_start": str(ws),
                "planned_hours": planned,
                "actual_hours": actual,
                "hours": hours,
                "capacity": capacity,
                "load_pct": load_pct,
                "is_past": is_past,
            })
        result.append({
            "user_id": user.id,
            "user_name": user.full_name,
            "department": user.department,
            "role": user.role,
            "capacity": user.weekly_capacity_hours or settings.DEFAULT_WEEKLY_CAPACITY_HOURS,
            "weeks": weeks_data,
        })

    return APIResponse.ok(data={
        "weeks": [str(w) for w in week_list],
        "users": result,
    })


@router.get("/plans", summary="Listar planes de capacidad")
def list_plans(
    user_id: Optional[str] = None,
    project_id: Optional[str] = None,
    week_from: Optional[date] = None,
    week_to: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    plans = capacity_service.list_capacity_plans(db, user_id, project_id, week_from, week_to)
    return APIListResponse.ok(items=[{
        "id": p.id,
        "user_id": p.user_id,
        "user_name": p.user.full_name if p.user else "—",
        "project_id": p.project_id,
        "project_name": p.project.name if p.project else None,
        "project_code": p.project.code if p.project else None,
        "week_start": str(p.week_start),
        "planned_hours": p.planned_hours,
        "notes": p.notes,
    } for p in plans])


@router.get("/availability", summary="Disponibilidad de recursos para nuevos proyectos")
def get_availability(
    weeks: int = Query(4, ge=1, le=12),
    min_hours: float = Query(0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """Shows available hours per person for the next N weeks."""
    today = date.today()
    week_list = _get_weeks(today, weeks)

    users = capacity_service.get_active_users(db, current_user.organization_id)
    user_ids = [u.id for u in users]

    plans = capacity_service.get_plans_for_period(db, week_list[0], week_list[-1], user_ids)

    planned_by_user_week = {}
    for p in plans:
        key = (p.user_id, str(p.week_start))
        planned_by_user_week[key] = planned_by_user_week.get(key, 0) + p.planned_hours

    result = []
    for user in users:
        capacity = user.weekly_capacity_hours or settings.DEFAULT_WEEKLY_CAPACITY_HOURS
        weekly_available = []
        for ws in week_list:
            planned = planned_by_user_week.get((user.id, str(ws)), 0)
            available = max(0, capacity - planned)
            weekly_available.append({
                "week_start": str(ws),
                "available_hours": round(available, 1),
                "planned_hours": round(planned, 1),
                "capacity": capacity,
                "load_pct": round((planned / capacity) * 100, 1) if capacity > 0 else 0,
            })
        avg_available = sum(w["available_hours"] for w in weekly_available) / len(weekly_available)
        if avg_available >= min_hours:
            result.append({
                "user_id": user.id,
                "user_name": user.full_name,
                "role": user.role,
                "department": user.department,
                "capacity": capacity,
                "avg_available_hours": round(avg_available, 1),
                "weeks": weekly_available,
            })

    result.sort(key=lambda x: x["avg_available_hours"], reverse=True)
    return APIListResponse.ok(items=result)


# -- Board - vista de planificacion visual -----------------------------------
@router.get("/board", summary="Board de planificacion: planes por usuario y semana")
def get_capacity_board(
    week_from: Optional[str] = Query(None),
    week_to:   Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Devuelve todos los CapacityPlan en el rango de semanas dado,
    con el nombre del proyecto incluido (para el planificador visual).
    """
    wf = date.fromisoformat(week_from) if week_from else None
    wt = date.fromisoformat(week_to) if week_to else None

    plans = capacity_service.get_plans_board(db, wf, wt)

    project_ids = {p.project_id for p in plans if p.project_id}
    projects = capacity_service.get_project_names(db, project_ids)

    return APIListResponse.ok(items=[
        {
            "id":            p.id,
            "user_id":       p.user_id,
            "project_id":    p.project_id,
            "project_name":  projects.get(str(p.project_id), "Sin proyecto") if p.project_id else None,
            "week_start":    str(p.week_start),
            "planned_hours": p.planned_hours,
            "notes":         p.notes,
        }
        for p in plans
    ])


@router.post("/plans", summary="Crear plan de capacidad")
def create_capacity_plan(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = payload.get("user_id", current_user.id)
    week_start_val = payload.get("week_start")
    week_start = date.fromisoformat(week_start_val) if week_start_val else None
    new_hours = float(payload.get("planned_hours", 8))

    if not week_start:
        raise HTTPException(status_code=400, detail="week_start es obligatorio")

    plan = create_capacity_plan_flow(
        db=db,
        current_user=current_user,
        user_id=user_id,
        week_start=week_start,
        new_hours=new_hours,
        project_id=payload.get("project_id") or None,
        notes=payload.get("notes"),
    )
    return APIResponse.ok(data={"id": plan.id, "user_id": plan.user_id, "week_start": str(plan.week_start),
            "planned_hours": plan.planned_hours, "project_id": plan.project_id})


@router.patch("/plans/{plan_id}", summary="Mover o actualizar plan de capacidad")
def update_capacity_plan(
    plan_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plan = capacity_service.get_capacity_plan_by_id(db, plan_id)
    if not plan:
        raise HTTPException(404)
    capacity_service.update_capacity_plan(db, plan, payload)
    return APIResponse.ok(data={"ok": True, "id": plan.id})


@router.delete("/plans/{plan_id}", summary="Eliminar plan de capacidad")
def delete_capacity_plan(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plan = capacity_service.get_capacity_plan_by_id(db, plan_id)
    if not plan:
        raise HTTPException(404)
    enforce_abac(db, current_user, "capacity_plan", plan_id, action="delete")
    capacity_service.delete_capacity_plan(db, plan)
    return APIResponse.ok(data={"ok": True, "message": "Plan de capacidad eliminado correctamente"})


@router.get("/leveling", summary="Nivelacion de recursos -- detecta conflictos y sugiere redistribucion")
def get_resource_leveling(
    week_from: date = Query(...),
    week_to: date = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """
    Detects overallocation conflicts in CapacityPlan entries for the given range
    and suggests moving overloaded hours to adjacent free weeks per user.
    Returns:
      - conflicts: list of {user, week, planned_hours, capacity, overload_hours}
      - suggestions: list of {user, from_week, to_week, hours_to_move, plan_id}
    """
    users = capacity_service.get_active_users(db, current_user.organization_id)
    user_map = {u.id: u for u in users}
    leveling_user_ids = list(user_map.keys())

    plans = capacity_service.get_plans_for_leveling(db, week_from, week_to, leveling_user_ids)

    # Aggregate planned hours per (user, week)
    from collections import defaultdict
    totals: dict = defaultdict(float)
    plan_list: dict = defaultdict(list)
    for p in plans:
        key = (p.user_id, p.week_start)
        totals[key] += p.planned_hours
        plan_list[key].append(p)

    # Collect all weeks in range
    monday = week_from - timedelta(days=week_from.weekday())
    end_monday = week_to - timedelta(days=week_to.weekday())
    all_weeks: List[date] = []
    cur = monday
    while cur <= end_monday:
        all_weeks.append(cur)
        cur += timedelta(weeks=1)

    conflicts = []
    suggestions = []

    for uid, user in user_map.items():
        cap = float(user.weekly_capacity_hours or settings.DEFAULT_WEEKLY_CAPACITY_HOURS or 40)
        loads = {w: totals.get((uid, w), 0.0) for w in all_weeks}

        for week in all_weeks:
            planned = loads[week]
            if planned > cap:
                overload = round(planned - cap, 2)
                conflicts.append({
                    "user_id": uid,
                    "user_name": user.full_name,
                    "week": str(week),
                    "planned_hours": round(planned, 2),
                    "capacity_hours": cap,
                    "overload_hours": overload,
                })
                # Suggest moving overload to the nearest future week with free capacity
                for candidate in all_weeks:
                    if candidate <= week:
                        continue
                    free = cap - loads.get(candidate, 0.0)
                    if free <= 0:
                        continue
                    move = min(overload, free)
                    # Find the largest plan in the overloaded week to partially redistribute
                    week_plans = plan_list.get((uid, week), [])
                    if not week_plans:
                        break
                    biggest_plan = max(week_plans, key=lambda x: x.planned_hours)
                    suggestions.append({
                        "user_id": uid,
                        "user_name": user.full_name,
                        "from_week": str(week),
                        "to_week": str(candidate),
                        "hours_to_move": round(move, 2),
                        "plan_id": biggest_plan.id,
                        "project_name": biggest_plan.project.name if biggest_plan.project else None,
                    })
                    loads[candidate] = loads.get(candidate, 0.0) + move
                    overload -= move
                    if overload <= 0:
                        break

    return APIResponse.ok(data={
        "conflicts": conflicts,
        "suggestions": suggestions,
        "summary": {
            "total_conflicts": len(conflicts),
            "total_overload_hours": round(sum(c["overload_hours"] for c in conflicts), 2),
            "users_affected": len({c["user_id"] for c in conflicts}),
        },
    })
