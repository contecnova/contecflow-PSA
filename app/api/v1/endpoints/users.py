from fastapi import Body, APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date

from app.db.session import get_db
from app.core.abac_enforce import enforce_abac
from app.core.deps import get_current_user, require_admin, require_admin_or_hr, require_admin_or_pm, require_any_manager, require_internal_user
from app.models.user import User, UserRole, UserStatus
from app.schemas import (
    UserCreate, UserUpdate, UserSelfUpdate, UserPublic, UserWithRate, UserLoad
)
from app.services.user_service import (
    scope_users_query as _scope_users_query,
    ensure_same_org_user_access as _ensure_same_org_user_access,
    get_load_map_payload,
    get_org_chart_payload,
    approval_chain_for_user,
    create_user_record,
    update_user_record,
    get_user_productivity_payload,
    set_manager_record,
    get_preferences_payload,
    update_preferences_record,
)

router = APIRouter()


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
    return get_load_map_payload(db, current_user, week_start)


@router.get("/org-chart", summary="Org chart jerárquico")
def get_org_chart(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enforce_abac(db, current_user, "user", action="read")
    return get_org_chart_payload(db, current_user)


@router.get("/me/approval-chain", summary="Mi cadena de aprobación")
def my_approval_chain(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enforce_abac(db, current_user, "user", current_user.id, action="read")
    chain = approval_chain_for_user(current_user, db, current_user)
    return {
        "user_id": current_user.id,
        "user_name": current_user.full_name,
        "chain": chain,
        "direct_approver": chain[0] if chain else None,
    }


@router.get("/me/preferences", summary="Obtener preferencias del usuario actual")
def get_my_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_preferences_payload(current_user.id, db)


@router.patch("/me/preferences", summary="Actualizar preferencias del usuario actual")
def update_my_preferences(
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return update_preferences_record(current_user.id, payload, db)


@router.patch("/me", response_model=UserPublic, summary="El usuario actualiza su propio perfil")
def update_my_profile(
    payload: UserSelfUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    allowed_fields = {"first_name", "last_name", "full_name", "phone", "job_title", "avatar_url"}
    update_data = payload.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        if field in allowed_fields:
            setattr(current_user, field, value)
            if field in ("first_name", "last_name"):
                fn = current_user.first_name or ""
                ln = current_user.last_name or ""
                if fn or ln:
                    current_user.full_name = f"{fn} {ln}".strip()

    db.commit()
    db.refresh(current_user)
    return current_user


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
    chain = approval_chain_for_user(user, db, _)
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
    if current_user.role == UserRole.employee and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Acceso denegado")

    enforce_abac(db, current_user, "user", user_id, action="read")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    _ensure_same_org_user_access(user, current_user)

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
    return create_user_record(payload, current_user, db)


@router.patch("/{user_id}", response_model=UserPublic, summary="Actualizar recurso")
def update_user(
    user_id: str,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enforce_abac(db, current_user, "user", user_id, action="update")
    return update_user_record(user_id, payload, current_user, db)


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
    enforce_abac(db, current_user, "user", user_id, action="read")
    return get_user_productivity_payload(user_id, date_from, date_to, current_user, db)


@router.patch("/{user_id}/manager", summary="Cambiar manager de un usuario")
def set_user_manager(
    user_id: str,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    enforce_abac(db, current_user, "user", user_id, action="update")
    return set_manager_record(user_id, payload.get("manager_id"), current_user, db)
