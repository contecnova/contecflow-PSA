from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from typing import Optional
from datetime import date

from app.models.pipeline import Contract, WorkOrder
from app.models.project import Project
from app.models.user import User
from app.services.numbering import next_numbered_code

def query_contracts(
    db: Session,
    current_user: User,
    project_id: Optional[str] = None,
    client_id: Optional[str] = None,
    status: Optional[str] = None,
):
    q = db.query(Contract).options(joinedload(Contract.work_orders))
    q = scope_contract_query(q, db, current_user)
    if project_id:
        q = q.filter(Contract.project_id == project_id)
    if client_id:
        q = q.filter(Contract.client_id == client_id)
    if status:
        q = q.filter(Contract.status == status)
    return q.order_by(Contract.created_at.desc())
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from typing import Optional
from datetime import date

from app.models.pipeline import Contract, WorkOrder
from app.models.project import Project
from app.models.user import User
from app.services.numbering import next_numbered_code


def _next_code(db: Session) -> str:
    return next_numbered_code(db, "contract", prefix="CTR", padding=4)


def _next_wo_code(db: Session) -> str:
    return next_numbered_code(db, "work_order", prefix="WO", padding=4)


def scope_contract_query(q, db: Session, current_user: User):
    if current_user.is_superadmin or not current_user.organization_id:
        return q
    return q.join(Project, Project.id == Contract.project_id).filter(
        Project.organization_id == current_user.organization_id
    )


def list_contracts(
    db: Session,
    current_user: User,
    project_id: Optional[str] = None,
    client_id: Optional[str] = None,
    status: Optional[str] = None,
):
    q = db.query(Contract).options(joinedload(Contract.work_orders))
    q = scope_contract_query(q, db, current_user)
    if project_id:
        q = q.filter(Contract.project_id == project_id)
    if client_id:
        q = q.filter(Contract.client_id == client_id)
    if status:
        q = q.filter(Contract.status == status)
    return q.order_by(Contract.created_at.desc()).all()


def check_project_access(db: Session, project_id: str, organization_id: str) -> bool:
    """Returns True if the project belongs to the given organization."""
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.organization_id == organization_id,
    ).first()
    return project is not None


def create_contract(db: Session, current_user_id: str, **kwargs) -> Contract:
    """Raises IntegrityError on duplicate code — caller must handle."""
    c = Contract(code=_next_code(db), created_by=current_user_id, **kwargs)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def get_contract(db: Session, contract_id: str, current_user: User) -> Optional[Contract]:
    return (
        scope_contract_query(db.query(Contract), db, current_user)
        .filter(Contract.id == contract_id)
        .first()
    )


def update_contract(db: Session, c: Contract, updates: dict) -> Contract:
    # Solo permitir campos válidos
    allowed_fields = {
        "name", "status", "total_amount", "hourly_rate", "hours_bag", "monthly_retainer",
        "end_date", "signed_date", "payment_terms", "notes"
    }
    # Controlar transiciones de estado
    allowed_status_transitions = {
        "draft":    ["active", "cancelled"],
        "active":   ["expired", "cancelled"],
        "expired":  [],
        "cancelled": [],
    }
    old_status = str(c.status)
    for k, v in updates.items():
        if k not in allowed_fields:
            continue
        if k == "status":
            new_status = str(v)
            if new_status == old_status:
                continue
            if new_status not in allowed_status_transitions.get(old_status, []):
                raise ValueError(f"Transición de estado no permitida: {old_status} → {new_status}")
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    return c


def delete_contract(db: Session, c: Contract) -> None:
    db.delete(c)
    db.commit()


def create_work_order(
    db: Session,
    contract_id: str,
    project_id: str,
    **kwargs,
) -> WorkOrder:
    wo = WorkOrder(
        code=_next_wo_code(db),
        contract_id=contract_id,
        project_id=project_id,
        **kwargs,
    )
    db.add(wo)
    db.commit()
    db.refresh(wo)
    return wo


def _scoped_wo_query(db: Session, wo_id: str, contract_id: str, current_user: User):
    q = db.query(WorkOrder).filter(WorkOrder.id == wo_id, WorkOrder.contract_id == contract_id)
    if not current_user.is_superadmin and current_user.organization_id:
        q = (
            q.join(Contract, Contract.id == WorkOrder.contract_id)
            .join(Project, Project.id == Contract.project_id)
            .filter(Project.organization_id == current_user.organization_id)
        )
    return q


def get_work_order(db: Session, wo_id: str, contract_id: str, current_user: User) -> Optional[WorkOrder]:
    return _scoped_wo_query(db, wo_id, contract_id, current_user).first()


def update_work_order(db: Session, wo: WorkOrder, updates: dict) -> WorkOrder:
    for k, v in updates.items():
        setattr(wo, k, v)
    db.commit()
    db.refresh(wo)
    return wo


def change_work_order_status(db: Session, wo: WorkOrder, status: str) -> None:
    wo.status = status
    db.commit()


# ── Label constants + serialization helper ────────────────────────────────────

CONTRACT_TYPE_LABELS = {
    "fixed_price": "Precio fijo", "time_material": "Tiempo y material",
    "retainer": "Retainer mensual", "hourly_bag": "Bolsa de horas",
}


def serialize_contract(c) -> dict:
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
