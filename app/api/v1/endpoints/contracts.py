from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Optional

from app.db.session import get_db
from app.core.deps import require_admin, require_any_manager
from app.core.abac_enforce import enforce_abac
from app.core.responses import APIListResponse, APIResponse
from app.models.user import User
from app.services import contract_service
from app.services.contract_service import horas_usadas as _horas_usadas, serialize_contract as _contract_out
from app.schemas.contracts import ContractIn, ContractUpdate, WorkOrderIn

router = APIRouter()



@router.get("", response_model=APIListResponse[dict], summary="Listar contratos")
def list_contracts(
    project_id: Optional[str] = None,
    client_id: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    response: Response = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    q = contract_service.query_contracts(db, current_user, project_id=project_id, client_id=client_id, status=status)
    total = q.count()
    contracts = q.offset((page - 1) * page_size).limit(page_size).all()
    if response is not None:
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
    horas = _horas_usadas(db, contracts)
    items = [_contract_out(c, horas[c.id]) for c in contracts]
    return APIListResponse.ok(items=items, total=total, page=page, page_size=page_size)


@router.post("", summary="Crear contrato")
def create_contract(
    payload: ContractIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    if not current_user.is_superadmin and current_user.organization_id:
        if not contract_service.check_project_access(db, payload.project_id, current_user.organization_id):
            raise HTTPException(403, "No puedes crear contratos para proyectos fuera de tu organización")

    try:
        c = contract_service.create_contract(db, current_user.id, **payload.model_dump())
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Código de contrato duplicado. Inténtalo de nuevo.")
    return APIResponse.ok(data=_contract_out(c, _horas_usadas(db, [c])[c.id]))


@router.get("/{contract_id}", summary="Detalle de un contrato")
def get_contract(
    contract_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """Auditoria 2026-08 (hallazgo 37): esta ruta **no existia**.

    `contractsApi` del frontend tiene el CRUD completo —listar, crear,
    actualizar, borrar— y la lectura de uno era la unica cuya ruta no estaba,
    asi que abrir el detalle de un contrato devolvia 404.

    No hay nada que inventar: la busqueda acotada (`get_contract`) y el
    serializador (`serialize_contract`) son los mismos que ya usan el `PATCH` y
    el `DELETE` de aqui debajo.
    """
    c = contract_service.get_contract(db, contract_id, current_user)
    if not c:
        raise HTTPException(404, "Contrato no encontrado")
    return APIResponse.ok(data=_contract_out(c, _horas_usadas(db, [c])[c.id]))


@router.patch("/{contract_id}", summary="Actualizar contrato")
def update_contract(
    contract_id: str,
    payload: ContractUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    c = contract_service.get_contract(db, contract_id, current_user)
    if not c:
        raise HTTPException(404, "Contrato no encontrado")
    c = contract_service.update_contract(db, c, payload.model_dump(exclude_unset=True))
    return APIResponse.ok(data=_contract_out(c, _horas_usadas(db, [c])[c.id]))


@router.delete("/{contract_id}", summary="Eliminar contrato")
def delete_contract(
    contract_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    c = contract_service.get_contract(db, contract_id, current_user)
    if not c:
        raise HTTPException(404, "Contrato no encontrado")
    enforce_abac(db, current_user, "contract", contract_id, action="delete")
    try:
        contract_service.delete_contract(db, c)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return APIResponse.ok(data={"ok": True, "message": "Contrato eliminado correctamente"})


@router.post("/{contract_id}/work-orders", summary="Crear orden de trabajo")
def create_work_order(
    contract_id: str,
    payload: WorkOrderIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    c = contract_service.get_contract(db, contract_id, current_user)
    if not c:
        raise HTTPException(404, "Contrato no encontrado")
    wo = contract_service.create_work_order(
        db, contract_id=contract_id, project_id=c.project_id, **payload.model_dump()
    )
    return APIResponse.ok(data={"id": wo.id, "code": wo.code, "name": wo.name, "status": wo.status})


@router.patch("/{contract_id}/work-orders/{wo_id}", summary="Actualizar orden de trabajo")
def update_work_order(
    contract_id: str,
    wo_id: str,
    payload: WorkOrderIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    wo = contract_service.get_work_order(db, wo_id, contract_id, current_user)
    if not wo:
        raise HTTPException(404, "Orden de trabajo no encontrada")
    wo = contract_service.update_work_order(db, wo, payload.model_dump(exclude_unset=True))
    return APIResponse.ok(data={"id": wo.id, "code": wo.code, "status": wo.status})


@router.patch("/{contract_id}/work-orders/{wo_id}/status", summary="Cambiar estado OT")
def change_wo_status(
    contract_id: str,
    wo_id: str,
    status: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    wo = contract_service.get_work_order(db, wo_id, contract_id, current_user)
    if not wo:
        raise HTTPException(404, "OT no encontrada")
    contract_service.change_work_order_status(db, wo, status)
    return APIResponse.ok(data={"ok": True})
