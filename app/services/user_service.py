"""
user_service.py — Lógica de negocio para usuarios y recursos.

Funciones exportadas:
  scope_users_query(q, current_user) -> Query
  ensure_same_org_user_access(target_user, current_user)
  get_load_map_payload(db, current_user, week_start) -> list
  get_org_chart_payload(db, current_user) -> dict
  approval_chain_for_user(user, db, requesting_user) -> list
  create_user_record(payload, current_user, db) -> User
  update_user_record(user_id, payload, current_user, db) -> User
  get_user_productivity_payload(user_id, date_from, date_to, current_user, db) -> dict
  set_manager_record(user_id, manager_id, current_user, db) -> dict
  get_preferences_payload(user_id, db) -> dict
  update_preferences_record(user_id, payload, db) -> dict
"""
from __future__ import annotations

import json
import uuid
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings


# ── Query helpers ──────────────────────────────────────────────────────────────

def scope_users_query(q, current_user):
    from app.models.user import User
    if current_user.organization_id:
        q = q.filter(User.organization_id == current_user.organization_id)
    return q


def ensure_same_org_user_access(target_user, current_user) -> None:
    from fastapi import HTTPException
    if not current_user.organization_id:
        return
    if target_user.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")


# ── Load map ───────────────────────────────────────────────────────────────────

def get_load_map_payload(db: Session, current_user, week_start: Optional[date] = None) -> list:
    from app.models.user import User, UserStatus
    from app.models.imputation import Imputation
    from app.models.task import Task, TaskStatus
    from app.schemas import UserLoad, UserPublic

    if not week_start:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    month_start = week_start.replace(day=1)

    users = scope_users_query(
        db.query(User).filter(User.is_active == True, User.status == UserStatus.active),
        current_user,
    ).all()
    if not users:
        return []

    user_ids = [u.id for u in users]

    week_hours_rows = (
        db.query(Imputation.user_id, func.sum(Imputation.hours).label("total"))
        .filter(Imputation.user_id.in_(user_ids), Imputation.date >= week_start, Imputation.date <= week_end)
        .group_by(Imputation.user_id).all()
    )
    week_hours = {row.user_id: float(row.total) for row in week_hours_rows}

    month_hours_rows = (
        db.query(Imputation.user_id, func.sum(Imputation.hours).label("total"))
        .filter(Imputation.user_id.in_(user_ids), Imputation.date >= month_start, Imputation.date <= week_end)
        .group_by(Imputation.user_id).all()
    )
    month_hours = {row.user_id: float(row.total) for row in month_hours_rows}

    active_tasks_rows = (
        db.query(Task.assignee_id, func.count(Task.id).label("cnt"))
        .filter(Task.assignee_id.in_(user_ids), Task.status.in_([TaskStatus.in_progress, TaskStatus.todo]))
        .group_by(Task.assignee_id).all()
    )
    active_tasks_map = {row.assignee_id: row.cnt for row in active_tasks_rows}

    active_projects_rows = (
        db.query(Imputation.user_id, func.count(func.distinct(Imputation.project_id)).label("cnt"))
        .filter(Imputation.user_id.in_(user_ids), Imputation.date >= week_start, Imputation.date <= week_end)
        .group_by(Imputation.user_id).all()
    )
    active_projects_map = {row.user_id: row.cnt for row in active_projects_rows}

    result = []
    for user in users:
        hours_week   = week_hours.get(user.id, 0.0)
        hours_month  = month_hours.get(user.id, 0.0)
        active_tasks = active_tasks_map.get(user.id, 0)
        active_proj  = active_projects_map.get(user.id, 0)
        capacity = user.weekly_capacity_hours or settings.DEFAULT_WEEKLY_CAPACITY_HOURS
        load_pct = round((hours_week / capacity) * 100, 1) if capacity > 0 else 0
        result.append(UserLoad(
            user=UserPublic.model_validate(user),
            current_load_pct=load_pct,
            hours_this_week=hours_week,
            hours_this_month=hours_month,
            active_tasks=active_tasks,
            active_projects=active_proj,
        ))

    result.sort(key=lambda x: x.current_load_pct, reverse=True)
    return result


# ── Org chart ──────────────────────────────────────────────────────────────────

def get_org_chart_payload(db: Session, current_user) -> dict:
    from app.models.user import User
    users = scope_users_query(db.query(User).filter(User.is_active == True), current_user).all()
    user_map = {u.id: {
        "id": u.id, "full_name": u.full_name, "job_title": u.job_title,
        "department": u.department, "role": u.role.value, "email": u.email,
        "manager_id": u.manager_id, "avatar_url": u.avatar_url,
        "children": []
    } for u in users}
    roots = []
    for uid, node in user_map.items():
        mid = node["manager_id"]
        if mid and mid in user_map:
            user_map[mid]["children"].append(node)
        else:
            roots.append(node)
    return {"nodes": roots, "total": len(user_map)}


# ── Approval chain ─────────────────────────────────────────────────────────────

def approval_chain_for_user(user, db: Session, requesting_user) -> list:
    """Walk the manager hierarchy for `user`, returning list of manager dicts."""
    chain = []
    current = user
    visited = set()
    while current.manager_id and current.manager_id not in visited:
        visited.add(current.id)
        from app.models.user import User
        manager = db.query(User).filter(User.id == current.manager_id).first()
        if not manager:
            break
        ensure_same_org_user_access(manager, requesting_user)
        chain.append({
            "id": manager.id,
            "full_name": manager.full_name,
            "job_title": manager.job_title,
            "department": manager.department,
            "role": manager.role.value,
            "level": len(chain) + 1,
        })
        current = manager
        if len(chain) >= 5:
            break
    return chain


# ── Create user ────────────────────────────────────────────────────────────────

def create_user_record(payload, current_user, db: Session):
    from fastapi import HTTPException
    from app.models.user import User
    from app.core.security import get_password_hash, validate_password_policy

    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="Username ya existe")
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email ya registrado")

    if payload.password:
        ok, err = validate_password_policy(payload.password)
        if not ok:
            raise HTTPException(status_code=400, detail=err)

    user_data = payload.model_dump(exclude={"password"})
    if current_user.organization_id:
        payload_org_id = user_data.get("organization_id")
        if payload_org_id and payload_org_id != current_user.organization_id:
            raise HTTPException(status_code=403, detail="No puedes crear usuarios en otra organización")
        user_data["organization_id"] = current_user.organization_id

    user = User(**user_data)
    if payload.password:
        user.hashed_password = get_password_hash(payload.password)

    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ── Update user ────────────────────────────────────────────────────────────────

def update_user_record(user_id: str, payload, current_user, db: Session):
    from fastapi import HTTPException
    from app.models.user import User, UserRole

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    ensure_same_org_user_access(user, current_user)

    if current_user.id != user_id and current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="No tienes permiso para editar este usuario")

    if current_user.role != UserRole.admin:
        if payload.role is not None or payload.hourly_rate is not None:
            raise HTTPException(status_code=403, detail="Solo admin puede cambiar rol o tarifa")

    if current_user.organization_id and payload.organization_id not in (None, current_user.organization_id):
        raise HTTPException(status_code=403, detail="No puedes mover usuarios a otra organización")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return user


# ── Productivity ───────────────────────────────────────────────────────────────

def get_user_productivity_payload(
    user_id: str,
    date_from: Optional[date],
    date_to: Optional[date],
    current_user,
    db: Session,
) -> dict:
    from fastapi import HTTPException
    from app.models.user import User, UserRole
    from app.models.imputation import Imputation
    from app.models.task import Task, TaskStatus

    if current_user.role == UserRole.employee and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Acceso denegado")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    ensure_same_org_user_access(user, current_user)

    if not date_from:
        date_from = date.today().replace(day=1)
    if not date_to:
        date_to = date.today()

    total_logged = db.query(func.sum(Imputation.hours)).filter(
        Imputation.user_id == user_id,
        Imputation.date.between(date_from, date_to),
    ).scalar() or 0.0

    tasks_done = db.query(func.count(Task.id)).filter(
        Task.assignee_id == user_id,
        Task.status == TaskStatus.done,
        Task.completed_at >= date_from,
        Task.completed_at <= date_to,
    ).scalar() or 0

    by_project = db.query(
        Imputation.project_id,
        func.sum(Imputation.hours).label("hours"),
    ).filter(
        Imputation.user_id == user_id,
        Imputation.date.between(date_from, date_to),
    ).group_by(Imputation.project_id).all()

    return {
        "user_id": user_id,
        "user_name": user.full_name,
        "period_start": date_from,
        "period_end": date_to,
        "total_hours_logged": total_logged,
        "tasks_completed": tasks_done,
        "by_project": [{"project_id": r[0], "hours": r[1]} for r in by_project],
    }


# ── Set manager ────────────────────────────────────────────────────────────────

def set_manager_record(user_id: str, manager_id: Optional[str], current_user, db: Session) -> dict:
    from fastapi import HTTPException
    from app.models.user import User

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "Usuario no encontrado")
    ensure_same_org_user_access(user, current_user)

    if manager_id:
        manager = db.query(User).filter(User.id == manager_id).first()
        if not manager:
            raise HTTPException(404, "Manager no encontrado")
        ensure_same_org_user_access(manager, current_user)
        # Detect cycles
        check = manager
        while check.manager_id:
            if check.manager_id == user_id:
                raise HTTPException(400, "Ciclo detectado en la jerarquía")
            check = db.query(User).filter(User.id == check.manager_id).first()
            if not check:
                break
            ensure_same_org_user_access(check, current_user)

    user.manager_id = manager_id
    db.commit()
    return {"ok": True, "manager_id": manager_id}


# ── Preferences ────────────────────────────────────────────────────────────────

def get_preferences_payload(user_id: str, db: Session) -> dict:
    from app.models.user import UserPreference
    pref = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
    if not pref:
        return {
            "dashboard_widgets": None, "accent_color": "#4f8ef7",
            "theme_mode": "dark", "sidebar_collapsed": False,
            "language": settings.DEFAULT_LANGUAGE, "ui_density": "normal", "extra": None,
        }
    return {
        "dashboard_widgets": json.loads(pref.dashboard_widgets) if pref.dashboard_widgets else None,
        "accent_color":      pref.accent_color or "#4f8ef7",
        "theme_mode":        pref.theme_mode or "dark",
        "sidebar_collapsed": pref.sidebar_collapsed or False,
        "language":          pref.language or settings.DEFAULT_LANGUAGE,
        "ui_density":        pref.ui_density or "normal",
        "extra":             json.loads(pref.extra) if pref.extra else None,
    }


# ── Paged user list ────────────────────────────────────────────────────────────

def list_users_paged(
    db: Session,
    current_user,
    department: Optional[str] = None,
    role=None,
    status=None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
):
    from app.models.user import User
    q = scope_users_query(db.query(User), current_user)
    if department:
        q = q.filter(User.department == department)
    if role:
        q = q.filter(User.role == role)
    if status:
        q = q.filter(User.status == status)
    if search:
        q = q.filter(
            (User.full_name.ilike(f"%{search}%"))
            | (User.username.ilike(f"%{search}%"))
            | (User.email.ilike(f"%{search}%"))
        )
    total = q.count()
    users = q.offset((page - 1) * page_size).limit(page_size).all()
    return users, total


def list_active_users_with_rates(db: Session, current_user):
    from app.models.user import User
    return scope_users_query(
        db.query(User).filter(User.is_active == True),
        current_user,
    ).all()


# ── Single user lookup ─────────────────────────────────────────────────────────

def get_user_by_id(db: Session, user_id: str):
    from app.models.user import User
    return db.query(User).filter(User.id == user_id).first()


# ── Self-profile update ────────────────────────────────────────────────────────

def update_self_profile(user, update_data: dict, db: Session):
    allowed_fields = {"first_name", "last_name", "full_name", "phone", "job_title", "avatar_url"}
    for field, value in update_data.items():
        if field in allowed_fields:
            setattr(user, field, value)
            if field in ("first_name", "last_name"):
                fn = user.first_name or ""
                ln = user.last_name or ""
                if fn or ln:
                    user.full_name = f"{fn} {ln}".strip()
    db.commit()
    db.refresh(user)
    return user


# ── Deactivate / delete user ───────────────────────────────────────────────────

def deactivate_user_record(user, db: Session) -> None:
    from app.models.user import UserStatus
    user.is_active = False
    user.status = UserStatus.inactive
    db.commit()


def delete_user_record(user, db: Session) -> None:
    db.delete(user)
    db.commit()


# ── Preferences ────────────────────────────────────────────────────────────────

def update_preferences_record(user_id: str, payload: dict, db: Session) -> dict:
    from app.models.user import UserPreference
    pref = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
    if not pref:
        pref = UserPreference(id=str(uuid.uuid4()), user_id=user_id)
        db.add(pref)

    if "dashboard_widgets" in payload:
        pref.dashboard_widgets = json.dumps(payload["dashboard_widgets"]) if payload["dashboard_widgets"] is not None else None
    if "accent_color"      in payload: pref.accent_color      = payload["accent_color"]
    if "theme_mode"        in payload: pref.theme_mode        = payload["theme_mode"]
    if "sidebar_collapsed" in payload: pref.sidebar_collapsed = payload["sidebar_collapsed"]
    if "language"          in payload: pref.language          = payload["language"]
    if "ui_density"        in payload: pref.ui_density        = payload["ui_density"]
    if "extra" in payload:
        pref.extra = json.dumps(payload["extra"]) if payload["extra"] is not None else None

    db.commit()
    return {"ok": True}
