from fastapi import Body, APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date

from app.db.session import get_db
from app.core.abac_enforce import enforce_abac
from app.core.deps import get_current_user, require_admin, require_admin_or_hr, require_admin_or_pm, require_any_manager, require_internal_user
from app.core.responses import APIListResponse, APIResponse
from app.models.user import User, UserRole, UserStatus
from app.schemas import (
    UserCreate, UserUpdate, UserSelfUpdate, UserPublic, UserWithRate, UserLoad
)
from app.services.user_service import (
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
    list_users_paged,
    list_active_users_with_rates,
    get_user_by_id,
    update_self_profile,
    deactivate_user_record,
    delete_user_record,
)

router = APIRouter()


@router.get("", response_model=APIListResponse[UserPublic], summary="Listar todos los recursos")
def list_users(
    department: Optional[str] = None,
    role: Optional[UserRole] = None,
    status: Optional[UserStatus] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=1000),
    response: Response = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_internal_user),
):
    enforce_abac(db, current_user, "user", action="read")

    users, total = list_users_paged(
        db, current_user,
        department=department, role=role, status=status, search=search,
        page=page, page_size=page_size,
    )
    if response is not None:
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
    return APIListResponse.ok(items=users, total=total, page=page, page_size=page_size)


@router.get("/with-rates", response_model=APIListResponse[UserWithRate], summary="Listar recursos con tarifas (admin/hr)")
def list_users_with_rates(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_hr),
):
    enforce_abac(db, current_user, "user", action="read")
    items = list_active_users_with_rates(db, current_user)
    return APIListResponse.ok(items=items, total=len(items))


@router.get("/load", response_model=APIListResponse[UserLoad], summary="Mapa de carga actual de todos los recursos")
def get_load_map(
    week_start: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "user", action="read")
    items = get_load_map_payload(db, current_user, week_start)
    return APIListResponse.ok(items=items, total=len(items))


@router.get("/org-chart", response_model=APIResponse[dict], summary="Org chart jerárquico")
def get_org_chart(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enforce_abac(db, current_user, "user", action="read")
    return APIResponse.ok(data=get_org_chart_payload(db, current_user))


@router.get("/me/approval-chain", summary="Mi cadena de aprobación")
def my_approval_chain(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enforce_abac(db, current_user, "user", current_user.id, action="read")
    chain = approval_chain_for_user(current_user, db, current_user)
    return APIResponse.ok(data={
        "user_id": current_user.id,
        "user_name": current_user.full_name,
        "chain": chain,
        "direct_approver": chain[0] if chain else None,
    })


@router.get("/me/preferences", summary="Obtener preferencias del usuario actual")
def get_my_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data=get_preferences_payload(current_user.id, db))


@router.patch("/me/preferences", summary="Actualizar preferencias del usuario actual")
def update_my_preferences(
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data=update_preferences_record(current_user.id, payload, db))


@router.patch("/me", response_model=APIResponse[UserPublic], summary="El usuario actualiza su propio perfil")
def update_my_profile(
    payload: UserSelfUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    update_data = payload.model_dump(exclude_unset=True)

    return APIResponse.ok(data=update_self_profile(current_user, update_data, db))


@router.get("/{user_id}/approval-chain", summary="Cadena de aprobación de un usuario")
def user_approval_chain(
    user_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_pm),
):
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(404, "Usuario no encontrado")
    enforce_abac(db, _, "user", user_id, action="read")
    _ensure_same_org_user_access(user, _)
    chain = approval_chain_for_user(user, db, _)
    return APIResponse.ok(data={
        "user_id": user.id,
        "user_name": user.full_name,
        "chain": chain,
        "direct_approver": chain[0] if chain else None,
    })


@router.get("/{user_id}", response_model=APIResponse[UserWithRate], summary="Detalle de un recurso")
def get_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == UserRole.employee and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Acceso denegado")

    enforce_abac(db, current_user, "user", user_id, action="read")

    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    _ensure_same_org_user_access(user, current_user)

    if current_user.role not in [UserRole.admin, UserRole.hr]:
        user.hourly_rate = None

    return APIResponse.ok(data=user)


@router.post("", response_model=APIResponse[UserPublic], summary="Crear nuevo recurso")
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    enforce_abac(db, current_user, "user", action="create")
    return APIResponse.ok(data=create_user_record(payload, current_user, db))


@router.patch("/{user_id}", response_model=APIResponse[UserPublic], summary="Actualizar recurso")
def update_user(
    user_id: str,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enforce_abac(db, current_user, "user", user_id, action="update")
    return APIResponse.ok(data=update_user_record(user_id, payload, current_user, db))


@router.delete("/{user_id}", summary="Desactivar recurso (soft delete)")
def deactivate_user(
    user_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    _ensure_same_org_user_access(user, _)
    enforce_abac(db, _, "user", user_id, action="delete")
    deactivate_user_record(user, db)
    return APIResponse.ok(data={"message": f"Usuario {user.username} desactivado"})


@router.delete("/{user_id}/permanent", summary="Eliminar usuario permanentemente")
def delete_user_permanent(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="No puedes eliminarte a ti mismo")
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    _ensure_same_org_user_access(user, current_user)
    enforce_abac(db, current_user, "user", user_id, action="delete")
    delete_user_record(user, db)
    return APIResponse.ok(data={"message": f"Usuario {user.username} eliminado permanentemente"})


@router.get("/{user_id}/productivity", summary="Estadísticas de productividad de un recurso")
def get_user_productivity(
    user_id: str,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enforce_abac(db, current_user, "user", user_id, action="read")
    return APIResponse.ok(data=get_user_productivity_payload(user_id, date_from, date_to, current_user, db))


@router.patch("/{user_id}/manager", summary="Cambiar manager de un usuario")
def set_user_manager(
    user_id: str,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    enforce_abac(db, current_user, "user", user_id, action="update")
    return APIResponse.ok(data=set_manager_record(user_id, payload.get("manager_id"), current_user, db))
