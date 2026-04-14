from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from typing import Optional
from datetime import date
from pydantic import BaseModel

from app.db.session import get_db
from app.core.deps import require_admin, require_any_manager
from app.models.user import User
from app.models.pipeline import Contract, WorkOrder
from app.models.project import Project
from app.services.numbering import next_numbered_code

router = APIRouter()


def _scope_contract_query(q, db: Session, current_user: User):
    if current_user.is_superadmin or not current_user.organization_id:
        return q
    return q.join(Project, Project.id == Contract.project_id).filter(
        Project.organization_id == current_user.organization_id
    )

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


def _next_code(db: Session) -> str:
    return next_numbered_code(db, "contract", prefix="CTR", padding=4)

def _next_wo_code(db: Session) -> str:
    return next_numbered_code(db, "work_order", prefix="WO", padding=4)


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
    q = db.query(Contract).options(joinedload(Contract.work_orders))
    q = _scope_contract_query(q, db, current_user)
    if project_id:
        q = q.filter(Contract.project_id == project_id)
    if client_id:
        q = q.filter(Contract.client_id == client_id)
    if status:
        q = q.filter(Contract.status == status)
    return [_contract_out(c) for c in q.order_by(Contract.created_at.desc()).all()]


@router.post("", summary="Crear contrato")
def create_contract(
    payload: ContractIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    if not current_user.is_superadmin and current_user.organization_id:
        project = db.query(Project).filter(
            Project.id == payload.project_id,
            Project.organization_id == current_user.organization_id,
        ).first()
        if not project:
            raise HTTPException(403, "No puedes crear contratos para proyectos fuera de tu organización")

    try:
        c = Contract(code=_next_code(db), created_by=current_user.id, **payload.model_dump())
        db.add(c)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Código de contrato duplicado. Inténtalo de nuevo.")
    db.refresh(c)
    return _contract_out(c)


@router.patch("/{contract_id}", summary="Actualizar contrato")
def update_contract(
    contract_id: str,
    payload: ContractUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    c = _scope_contract_query(db.query(Contract), db, current_user).filter(Contract.id == contract_id).first()
    if not c:
        raise HTTPException(404, "Contrato no encontrado")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    db.commit(); db.refresh(c)
    return _contract_out(c)


@router.delete("/{contract_id}", summary="Eliminar contrato")
def delete_contract(
    contract_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    c = _scope_contract_query(db.query(Contract), db, current_user).filter(Contract.id == contract_id).first()
    if not c:
        raise HTTPException(404, "Contrato no encontrado")
    db.delete(c); db.commit()
    return {"ok": True}


@router.post("/{contract_id}/work-orders", summary="Crear orden de trabajo")
def create_work_order(
    contract_id: str,
    payload: WorkOrderIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    c = _scope_contract_query(db.query(Contract), db, current_user).filter(Contract.id == contract_id).first()
    if not c:
        raise HTTPException(404, "Contrato no encontrado")
    wo = WorkOrder(code=_next_wo_code(db), contract_id=contract_id, project_id=c.project_id, **payload.model_dump())
    db.add(wo); db.commit(); db.refresh(wo)
    return {"id": wo.id, "code": wo.code, "name": wo.name, "status": wo.status}


@router.patch("/{contract_id}/work-orders/{wo_id}", summary="Actualizar orden de trabajo")
def update_work_order(
    contract_id: str,
    wo_id: str,
    payload: WorkOrderIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    wo_q = db.query(WorkOrder).filter(WorkOrder.id == wo_id, WorkOrder.contract_id == contract_id)
    if not current_user.is_superadmin and current_user.organization_id:
        wo_q = wo_q.join(Contract, Contract.id == WorkOrder.contract_id).join(Project, Project.id == Contract.project_id).filter(
            Project.organization_id == current_user.organization_id
        )
    wo = wo_q.first()
    if not wo:
        raise HTTPException(404, "Orden de trabajo no encontrada")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(wo, k, v)
    db.commit(); db.refresh(wo)
    return {"id": wo.id, "code": wo.code, "status": wo.status}


@router.patch("/{contract_id}/work-orders/{wo_id}/status", summary="Cambiar estado OT")
def change_wo_status(
    contract_id: str,
    wo_id: str,
    status: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    wo_q = db.query(WorkOrder).filter(WorkOrder.id == wo_id, WorkOrder.contract_id == contract_id)
    if not current_user.is_superadmin and current_user.organization_id:
        wo_q = wo_q.join(Contract, Contract.id == WorkOrder.contract_id).join(Project, Project.id == Contract.project_id).filter(
            Project.organization_id == current_user.organization_id
        )
    wo = wo_q.first()
    if not wo:
        raise HTTPException(404, "OT no encontrada")
    wo.status = status
    db.commit()
    return {"ok": True}
