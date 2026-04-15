from fastapi import Body, APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from typing import Optional, List
from datetime import date, timedelta

from app.db.session import get_db
from app.core.abac_enforce import enforce_abac
from app.core.deps import get_current_user, require_admin, require_admin_or_hr, require_admin_or_pm, require_any_manager, require_internal_user
from app.models.user import User, UserRole, UserStatus, UserPreference
from app.models.imputation import Imputation
from app.models.task import Task, TaskStatus
from app.schemas.users import (
    UserCreate, UserUpdate, UserSelfUpdate, UserPublic, UserWithRate, UserLoad
)
from app.core.security import get_password_hash, validate_password_policy
from app.core.config import settings

router = APIRouter()


def _scope_users_query(q, current_user: User):
    if current_user.organization_id:
        q = q.filter(User.organization_id == current_user.organization_id)
    return q


def _ensure_same_org_user_access(target_user: User, current_user: User) -> None:
    if not current_user.organization_id:
        return
    if target_user.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")


@router.get("", response_model=List[UserPublic], summary="Listar todos los recursos")
def list_users(
    department: Optional[str] = None,
    role: Optional[UserRole] = None,
    status: Optional[UserStatus] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    response: Response = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_internal_user),
):
    enforce_abac(db, current_user, "user", action="read")

    q = _scope_users_query(db.query(User), current_user)
    if department:
        q = q.filter(User.department == department)
    if role:
        q = q.filter(User.role == role)
    if status:
        q = q.filter(User.status == status)
    if search:
        q = q.filter(
            (User.full_name.ilike(f"%{search}%")) |
            (User.username.ilike(f"%{search}%")) |
            (User.email.ilike(f"%{search}%"))
        )

    total = q.count()
    users = q.offset((page - 1) * page_size).limit(page_size).all()
    if response is not None:
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
    return users


@router.get("/with-rates", response_model=List[UserWithRate], summary="Listar recursos con tarifas (admin/hr)")
def list_users_with_rates(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_hr),
):
    enforce_abac(db, current_user, "user", action="read")
    return _scope_users_query(
        db.query(User).filter(User.is_active == True),
        current_user,
    ).all()


@router.get("/load", response_model=List[UserLoad], summary="Mapa de carga actual de todos los recursos")
def get_load_map(
    week_start: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "user", action="read")

    if not week_start:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    month_start = week_start.replace(day=1)

    users = _scope_users_query(
        db.query(User).filter(User.is_active == True, User.status == UserStatus.active),
        current_user,
    ).all()
    if not users:
        return []

    user_ids = [u.id for u in users]

    # Aggregate weekly hours per user in a single query
    week_hours_rows = (
        db.query(Imputation.user_id, func.sum(Imputation.hours).label("total"))
        .filter(
            Imputation.user_id.in_(user_ids),
            Imputation.date >= week_start,
            Imputation.date <= week_end,
        )
        .group_by(Imputation.user_id)
        .all()
    )
    week_hours = {row.user_id: float(row.total) for row in week_hours_rows}

    # Aggregate month hours per user in a single query
    month_hours_rows = (
        db.query(Imputation.user_id, func.sum(Imputation.hours).label("total"))
        .filter(
            Imputation.user_id.in_(user_ids),
            Imputation.date >= month_start,
            Imputation.date <= week_end,
        )
        .group_by(Imputation.user_id)
        .all()
    )
    month_hours = {row.user_id: float(row.total) for row in month_hours_rows}

    # Active tasks count per user in a single query
    active_tasks_rows = (
        db.query(Task.assignee_id, func.count(Task.id).label("cnt"))
        .filter(
            Task.assignee_id.in_(user_ids),
            Task.status.in_([TaskStatus.in_progress, TaskStatus.todo]),
        )
        .group_by(Task.assignee_id)
        .all()
    )
    active_tasks_map = {row.assignee_id: row.cnt for row in active_tasks_rows}

    # Active projects (distinct) per user within the current week
    active_projects_rows = (
        db.query(Imputation.user_id, func.count(func.distinct(Imputation.project_id)).label("cnt"))
        .filter(
            Imputation.user_id.in_(user_ids),
            Imputation.date >= week_start,
            Imputation.date <= week_end,
        )
        .group_by(Imputation.user_id)
        .all()
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


# ── Org Chart ──────────────────────────────────────────────────────────────────
@router.get("/org-chart", summary="Org chart jerárquico")
def get_org_chart(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Devuelve la jerarquía de reporting en forma de árbol."""
    enforce_abac(db, current_user, "user", action="read")
    users = _scope_users_query(db.query(User).filter(User.is_active == True), current_user).all()
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


# ── Cadena de aprobación ───────────────────────────────────────────────────────
@router.get("/me/approval-chain", summary="Mi cadena de aprobación")
def my_approval_chain(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Devuelve la jerarquía de aprobación: quién aprueba mis solicitudes."""
    enforce_abac(db, current_user, "user", current_user.id, action="read")
    chain = []
    user = current_user
    visited = set()
    while user.manager_id and user.manager_id not in visited:
        visited.add(user.id)
        manager = db.query(User).filter(User.id == user.manager_id).first()
        if not manager:
            break
        _ensure_same_org_user_access(manager, current_user)
        chain.append({
            "id": manager.id,
            "full_name": manager.full_name,
            "job_title": manager.job_title,
            "department": manager.department,
            "role": manager.role.value,
            "level": len(chain) + 1,
        })
        user = manager
        if len(chain) >= 5:  # máximo 5 niveles
            break
    return {
        "user_id": current_user.id,
        "user_name": current_user.full_name,
        "chain": chain,
        "direct_approver": chain[0] if chain else None,
    }

@router.get("/{user_id}/approval-chain", summary="Cadena de aprobación de un usuario")
def user_approval_chain(
    user_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_pm),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "Usuario no encontrado")
    enforce_abac(db, _, "user", user_id, action="read")
    _ensure_same_org_user_access(user, _)
    chain = []
    current = user
    visited = set()
    while current.manager_id and current.manager_id not in visited:
        visited.add(current.id)
        manager = db.query(User).filter(User.id == current.manager_id).first()
        if not manager:
            break
        _ensure_same_org_user_access(manager, _)
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
    return {
        "user_id": user.id,
        "user_name": user.full_name,
        "chain": chain,
        "direct_approver": chain[0] if chain else None,
    }



@router.get("/{user_id}", response_model=UserWithRate, summary="Detalle de un recurso")
def get_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Employees can only see their own profile
    if current_user.role == UserRole.employee and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Acceso denegado")

    enforce_abac(db, current_user, "user", user_id, action="read")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    _ensure_same_org_user_access(user, current_user)

    # Hide hourly_rate from non-admin/hr
    if current_user.role not in [UserRole.admin, UserRole.hr]:
        user.hourly_rate = None

    return user


@router.post("", response_model=UserPublic, summary="Crear nuevo recurso")
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    enforce_abac(db, current_user, "user", action="create")

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



@router.patch("/me", response_model=UserPublic, summary="El usuario actualiza su propio perfil")
def update_my_profile(
    payload: UserSelfUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Permite al usuario editar su propio perfil:
    nombre, apellidos, teléfono, cargo, avatar_url.
    No puede cambiar su rol, tarifa, estado ni departamento.
    """
    allowed_fields = {"first_name", "last_name", "full_name", "phone", "job_title", "avatar_url"}
    update_data = payload.model_dump(exclude_unset=True)

    # Filtrar solo campos permitidos (doble seguridad)
    for field, value in update_data.items():
        if field in allowed_fields:
            setattr(current_user, field, value)
            # Si cambia first o last, recalcular full_name
            if field in ("first_name", "last_name"):
                fn = current_user.first_name or ""
                ln = current_user.last_name or ""
                if fn or ln:
                    current_user.full_name = f"{fn} {ln}".strip()

    db.commit()
    db.refresh(current_user)
    return current_user

@router.patch("/{user_id}", response_model=UserPublic, summary="Actualizar recurso")
def update_user(
    user_id: str,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    _ensure_same_org_user_access(user, current_user)
    enforce_abac(db, current_user, "user", user_id, action="update")

    # Solo el propio usuario o un admin pueden editar el perfil
    if current_user.id != user_id and current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="No tienes permiso para editar este usuario")

    # Only admin can update role or hourly_rate
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


@router.delete("/{user_id}", summary="Desactivar recurso (soft delete)")
def deactivate_user(
    user_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    _ensure_same_org_user_access(user, _)
    enforce_abac(db, _, "user", user_id, action="delete")
    user.is_active = False
    user.status = UserStatus.inactive
    db.commit()
    return {"message": f"Usuario {user.username} desactivado"}


@router.delete("/{user_id}/permanent", summary="Eliminar usuario permanentemente")
def delete_user_permanent(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="No puedes eliminarte a ti mismo")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    _ensure_same_org_user_access(user, current_user)
    enforce_abac(db, current_user, "user", user_id, action="delete")
    db.delete(user)
    db.commit()
    return {"message": f"Usuario {user.username} eliminado permanentemente"}


@router.get("/{user_id}/productivity", summary="Estadísticas de productividad de un recurso")
def get_user_productivity(
    user_id: str,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Employees can only see their own stats
    if current_user.role == UserRole.employee and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Acceso denegado")

    enforce_abac(db, current_user, "user", user_id, action="read")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    _ensure_same_org_user_access(user, current_user)

    if not date_from:
        date_from = date.today().replace(day=1)
    if not date_to:
        date_to = date.today()

    # Hours logged
    total_logged = db.query(func.sum(Imputation.hours)).filter(
        Imputation.user_id == user_id,
        Imputation.date.between(date_from, date_to),
    ).scalar() or 0.0

    # Tasks completed
    tasks_done = db.query(func.count(Task.id)).filter(
        Task.assignee_id == user_id,
        Task.status == TaskStatus.done,
        Task.completed_at >= date_from,
        Task.completed_at <= date_to,
    ).scalar() or 0

    # Imputations by project
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

@router.patch("/{user_id}/manager", summary="Cambiar manager de un usuario")
def set_user_manager(
    user_id: str,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user: raise HTTPException(404, "Usuario no encontrado")
    _ensure_same_org_user_access(user, current_user)
    enforce_abac(db, current_user, "user", user_id, action="update")
    manager_id = payload.get("manager_id")
    if manager_id:
        manager = db.query(User).filter(User.id == manager_id).first()
        if not manager: raise HTTPException(404, "Manager no encontrado")
        _ensure_same_org_user_access(manager, current_user)
        # Evitar ciclos
        check = manager
        while check.manager_id:
            if check.manager_id == user_id:
                raise HTTPException(400, "Ciclo detectado en la jerarquía")
            check = db.query(User).filter(User.id == check.manager_id).first()
            if not check: break
            _ensure_same_org_user_access(check, current_user)
    user.manager_id = manager_id
    db.commit()
    return {"ok": True, "manager_id": manager_id}

# ── Preferencias de usuario ────────────────────────────────────────────────────
@router.get("/me/preferences", summary="Obtener preferencias del usuario actual")
def get_my_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    import json as _json
    pref = db.query(UserPreference).filter(UserPreference.user_id == current_user.id).first()
    if not pref:
        return {
            "dashboard_widgets": None, "accent_color": "#4f8ef7",
            "theme_mode": "dark", "sidebar_collapsed": False,
            "language": settings.DEFAULT_LANGUAGE, "ui_density": "normal", "extra": None,
        }
    return {
        "dashboard_widgets": _json.loads(pref.dashboard_widgets) if pref.dashboard_widgets else None,
        "accent_color":      pref.accent_color or "#4f8ef7",
        "theme_mode":        pref.theme_mode or "dark",
        "sidebar_collapsed": pref.sidebar_collapsed or False,
        "language":          pref.language or settings.DEFAULT_LANGUAGE,
        "ui_density":        pref.ui_density or "normal",
        "extra":             _json.loads(pref.extra) if pref.extra else None,
    }


@router.patch("/me/preferences", summary="Actualizar preferencias del usuario actual")
def update_my_preferences(
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    import json as _json
    import uuid as _uuid
    pref = db.query(UserPreference).filter(UserPreference.user_id == current_user.id).first()
    if not pref:
        pref = UserPreference(id=str(_uuid.uuid4()), user_id=current_user.id)
        db.add(pref)

    if "dashboard_widgets" in payload:
        pref.dashboard_widgets = _json.dumps(payload["dashboard_widgets"]) if payload["dashboard_widgets"] is not None else None
    if "accent_color"    in payload: pref.accent_color    = payload["accent_color"]
    if "theme_mode"      in payload: pref.theme_mode      = payload["theme_mode"]
    if "sidebar_collapsed" in payload: pref.sidebar_collapsed = payload["sidebar_collapsed"]
    if "language"        in payload: pref.language        = payload["language"]
    if "ui_density"      in payload: pref.ui_density      = payload["ui_density"]
    if "extra"           in payload:
        pref.extra = _json.dumps(payload["extra"]) if payload["extra"] is not None else None

    db.commit()
    return {"ok": True}

