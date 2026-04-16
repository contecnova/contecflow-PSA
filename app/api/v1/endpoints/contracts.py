from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Optional
from datetime import date
from pydantic import BaseModel

from app.db.session import get_db
from app.core.deps import require_admin, require_any_manager
from app.models.user import User
from app.models.pipeline import Contract, WorkOrder
from app.services import contract_service

router = APIRouter()


CONTRACT_TYPE_LABELS = {
    "fixed_price": "Precio fijo", "time_material": "Tiempo y material",
    "retainer": "Retainer mensual", "hourly_bag": "Bolsa de horas"
}

class ContractIn(BaseModel):
    name: str
    project_id: str
    client_name: str
    contract_type: str
    total_amount: Optional[float] = None
    hourly_rate: Optional[float] = None
    hours_bag: Optional[float] = None
    monthly_retainer: Optional[float] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    signed_date: Optional[date] = None
    client_contact: Optional[str] = None
    payment_terms: Optional[str] = None
    notes: Optional[str] = None

class ContractUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    total_amount: Optional[float] = None
    hourly_rate: Optional[float] = None
    hours_bag: Optional[float] = None
    monthly_retainer: Optional[float] = None
    end_date: Optional[date] = None
    signed_date: Optional[date] = None
    payment_terms: Optional[str] = None
    notes: Optional[str] = None

class WorkOrderIn(BaseModel):
    name: str
    amount: Optional[float] = None
    hours: Optional[float] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    description: Optional[str] = None


def _contract_out(c: Contract) -> dict:
    hours_pct = None
    if c.hours_bag and c.hours_bag > 0:
        hours_pct = round(((c.hours_used or 0) / c.hours_bag) * 100, 1)

    return {
        "id": c.id, "code": c.code, "name": c.name,
        "project_id": c.project_id,
        "client_id": c.client_id, "client_name": c.client_name, "client_contact": c.client_contact,
        "contract_type": c.contract_type,
        "contract_type_label": CONTRACT_TYPE_LABELS.get(c.contract_type, c.contract_type),
        "status": c.status,
        "total_amount": c.total_amount,
        "hourly_rate": c.hourly_rate,
        "hours_bag": c.hours_bag,
        "hours_used": c.hours_used,
        "hours_pct": hours_pct,
        "monthly_retainer": c.monthly_retainer,
        "start_date": str(c.start_date) if c.start_date else None,
        "end_date": str(c.end_date) if c.end_date else None,
        "signed_date": str(c.signed_date) if c.signed_date else None,
        "payment_terms": c.payment_terms,
        "notes": c.notes,
        "work_orders": [{
            "id": wo.id, "code": wo.code, "name": wo.name,
            "amount": wo.amount, "hours": wo.hours, "status": wo.status,
            "start_date": str(wo.start_date) if wo.start_date else None,
            "end_date": str(wo.end_date) if wo.end_date else None,
        } for wo in (c.work_orders or [])],
    }


@router.get("", summary="Listar contratos")
def list_contracts(
    project_id: Optional[str] = None,
    client_id: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    contracts = contract_service.list_contracts(
        db, current_user, project_id=project_id, client_id=client_id, status=status
    )
    return [_contract_out(c) for c in contracts]


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
    return _contract_out(c)


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
    return _contract_out(c)


@router.delete("/{contract_id}", summary="Eliminar contrato")
def delete_contract(
    contract_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    c = contract_service.get_contract(db, contract_id, current_user)
    if not c:
        raise HTTPException(404, "Contrato no encontrado")
    contract_service.delete_contract(db, c)
    return {"ok": True}


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
    return {"id": wo.id, "code": wo.code, "name": wo.name, "status": wo.status}


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
    return {"id": wo.id, "code": wo.code, "status": wo.status}


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
    return {"ok": True}
