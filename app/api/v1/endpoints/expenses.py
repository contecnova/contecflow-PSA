"""
Expenses endpoint — project-linked expense management with approval workflow.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, select, or_
from typing import Optional
from datetime import date, datetime, timezone
from pydantic import BaseModel

from app.db.session import get_db
from app.services.audit import audit_log
from app.services.notifications import notify_user
from app.core.deps import get_current_user, require_any_manager, require_admin_or_pm
from app.core.abac_enforce import enforce_abac
from app.models.user import User, UserRole
from app.models.project import Project, ProjectStatus
from app.models.expenses import Expense, ExpenseStatus
from app.core.config import settings
from app.services.numbering import next_numbered_code
from app.services.expense_service import (
    review_expense as svc_review_expense,
    export_expenses_excel,
    ocr_receipt as svc_ocr_receipt,
)

router = APIRouter()

class ExpenseIn(BaseModel):
    user_id: Optional[str] = None
    project_id: Optional[str] = None
    category: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    expense_date: Optional[date] = None
    description: Optional[str] = None
    notes: Optional[str] = None
    receipt_url: Optional[str] = None
    status: Optional[str] = None
    is_billable: Optional[bool] = None

CATEGORY_LABELS = {
    "travel": "Viajes y transporte",
    "accommodation": "Alojamiento",
    "meals": "Dietas y comidas",
    "software": "Software y licencias",
    "hardware": "Hardware y equipamiento",
    "training": "Formación",
    "subcontract": "Subcontratación",
    "other": "Otros",
}

def _next_code(db: Session) -> str:
    return next_numbered_code(db, "expense", prefix="EXP", padding=4)

def _expense_out(e: Expense) -> dict:
    return {
        "id": e.id, "code": e.code,
        "user_id": e.user_id,
        "user_name": e.user.full_name if e.user else None,
        "project_id": e.project_id,
        "project_name": e.project.name if e.project else None,
        "contract_id": e.contract_id,
        "category": e.category,
        "category_label": CATEGORY_LABELS.get(e.category, e.category),
        "description": e.description,
        "amount": e.amount,
        "currency": e.currency,
        "expense_date": str(e.expense_date) if e.expense_date else None,
        "is_billable": e.is_billable,
        "receipt_url": e.receipt_url,
        "receipt_name": e.receipt_name,
        "status": e.status,
        "submitted_at": str(e.submitted_at)[:16] if e.submitted_at else None,
        "reviewed_by_name": e.reviewer.full_name if e.reviewer else None,
        "reviewed_at": str(e.reviewed_at)[:16] if e.reviewed_at else None,
        "rejection_reason": e.rejection_reason,
        "reimbursed_at": str(e.reimbursed_at)[:10] if e.reimbursed_at else None,
        "notes": e.notes,
        "created_at": str(e.created_at)[:10] if e.created_at else None,
    }


class ExpenseCreate(BaseModel):
    project_id: Optional[str] = None
    contract_id: Optional[str] = None
    category: str
    description: str
    amount: float
    currency: str = settings.DEFAULT_CURRENCY
    expense_date: date
    is_billable: bool = True
    receipt_name: Optional[str] = None
    notes: Optional[str] = None

class ExpenseUpdate(BaseModel):
    category: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[float] = None
    expense_date: Optional[date] = None
    is_billable: Optional[bool] = None
    notes: Optional[str] = None

class ReviewPayload(BaseModel):
    approved: bool
    rejection_reason: Optional[str] = None


@router.get("/my", summary="Mis gastos")
def my_expenses(
    status: Optional[str] = None,
    project_id: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Expense).options(
        joinedload(Expense.project), joinedload(Expense.reviewer)
    ).filter(Expense.user_id == current_user.id)
    if status:      q = q.filter(Expense.status == status)
    if project_id:  q = q.filter(Expense.project_id == project_id)
    if date_from:   q = q.filter(Expense.expense_date >= date_from)
    if date_to:     q = q.filter(Expense.expense_date <= date_to)
    return [_expense_out(e) for e in q.order_by(Expense.expense_date.desc()).all()]


@router.get("/pending", summary="Gastos pendientes de aprobación (PM/admin)")
def pending_expenses(
    project_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "expense", action="read")
    q = db.query(Expense).options(
        joinedload(Expense.user), joinedload(Expense.project)
    ).filter(Expense.status == ExpenseStatus.submitted)
    if project_id:
        q = q.filter(Expense.project_id == project_id)
    return [_expense_out(e) for e in q.order_by(Expense.submitted_at).all()]


@router.get("", summary="Listar todos los gastos (admin/PM) — alias de /team")
def list_all_expenses_alias(
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
    status: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
):
    q = db.query(Expense)
    if cu.role not in (UserRole.admin, UserRole.pm, UserRole.hr):
        q = q.filter(Expense.user_id == cu.id)
    elif not cu.is_superadmin and cu.organization_id:
        org_user_ids = db.query(User.id).filter(
            User.organization_id == cu.organization_id
        ).scalar_subquery()
        org_project_ids = db.query(Project.id).filter(
            Project.organization_id == cu.organization_id
        ).scalar_subquery()
        q = q.filter(
            or_(
                Expense.user_id.in_(org_user_ids),
                Expense.project_id.in_(org_project_ids),
            )
        )
    if status: q = q.filter(Expense.status == status)
    if user_id: q = q.filter(Expense.user_id == user_id)
    items = q.order_by(Expense.created_at.desc()).limit(200).all()
    return [_expense_out(e) for e in items]

@router.get("/team", summary="Todos los gastos del equipo (admin/PM)")
def team_expenses(
    status: Optional[str] = None,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "expense", action="read")
    q = db.query(Expense).options(
        joinedload(Expense.user), joinedload(Expense.project), joinedload(Expense.reviewer)
    )
    if not current_user.is_superadmin and current_user.organization_id:
        org_user_ids = db.query(User.id).filter(
            User.organization_id == current_user.organization_id
        ).scalar_subquery()
        org_project_ids = db.query(Project.id).filter(
            Project.organization_id == current_user.organization_id
        ).scalar_subquery()
        q = q.filter(
            or_(
                Expense.user_id.in_(org_user_ids),
                Expense.project_id.in_(org_project_ids),
            )
        )
    if status:      q = q.filter(Expense.status == status)
    if project_id:  q = q.filter(Expense.project_id == project_id)
    if user_id:     q = q.filter(Expense.user_id == user_id)
    if date_from:   q = q.filter(Expense.expense_date >= date_from)
    if date_to:     q = q.filter(Expense.expense_date <= date_to)
    expenses = q.order_by(Expense.expense_date.desc()).all()

    total = sum(e.amount for e in expenses)
    billable = sum(e.amount for e in expenses if e.is_billable)
    by_category = {}
    for e in expenses:
        cat = e.category
        by_category[cat] = by_category.get(cat, 0) + e.amount

    return {
        "expenses": [_expense_out(e) for e in expenses],
        "total": round(total, 2),
        "billable_total": round(billable, 2),
        "by_category": {k: round(v, 2) for k, v in by_category.items()},
    }


@router.get("/summary/{project_id}", summary="Resumen de gastos por proyecto")
def project_expense_summary(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    expenses = db.query(Expense).options(joinedload(Expense.user)).filter(
        Expense.project_id == project_id,
        Expense.status.in_(["approved", "reimbursed"])
    ).all()
    total = sum(e.amount for e in expenses)
    billable = sum(e.amount for e in expenses if e.is_billable)
    by_cat = {}
    for e in expenses:
        by_cat[e.category] = by_cat.get(e.category, 0) + e.amount
    return {
        "total": round(total, 2),
        "billable": round(billable, 2),
        "non_billable": round(total - billable, 2),
        "count": len(expenses),
        "by_category": {k: round(v, 2) for k, v in by_cat.items()},
        "expenses": [_expense_out(e) for e in expenses],
    }


@router.post("", summary="Crear gasto")
def create_expense(
    payload: ExpenseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.project_id:
        project = db.query(Project).filter(Project.id == payload.project_id).first()
        if not project:
            raise HTTPException(404, "Proyecto no encontrado")
        if project.status in [ProjectStatus.completed, ProjectStatus.closed, ProjectStatus.cancelled, ProjectStatus.archived]:
            raise HTTPException(400, "No se pueden generar gastos facturables en proyectos cerrados")

    expense = Expense(
        code=_next_code(db),
        user_id=current_user.id,
        **payload.model_dump(),
    )

    if expense.is_billable and expense.project_id:
        project = db.query(Project).filter(Project.id == expense.project_id).first()
        if project and project.status not in [ProjectStatus.active, ProjectStatus.planning]:
            raise HTTPException(400, "No se puede marcar gasto como facturable en proyecto no activo")

    db.add(expense); db.commit(); db.refresh(expense)
    expense = db.query(Expense).options(joinedload(Expense.project)).filter(Expense.id == expense.id).first()
    return _expense_out(expense)


@router.patch("/{expense_id}", summary="Editar gasto (admin/PM, cualquier estado)")
def update_expense_admin(
    expense_id: str,
    payload: ExpenseIn,
    db: Session = Depends(get_db),
    cu: User = Depends(require_admin_or_pm),
):
    from app.models.expenses import Expense
    e = db.query(Expense).filter(Expense.id == expense_id).first()
    if not e: raise HTTPException(404, "Gasto no encontrado")

    if payload.is_billable and e.project_id:
        project = db.query(Project).filter(Project.id == e.project_id).first()
        if project and project.status not in [ProjectStatus.active, ProjectStatus.planning]:
            raise HTTPException(400, "No se puede marcar gasto como facturable en proyecto no activo")

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(e, k, v)
    db.commit(); db.refresh(e)
    return _expense_out(e)

@router.patch("/my/{expense_id}", summary="Editar mi gasto (solo borrador)")
def update_expense(
    expense_id: str,
    payload: ExpenseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    expense = db.query(Expense).filter(Expense.id == expense_id, Expense.user_id == current_user.id).first()
    if not expense: raise HTTPException(404, "Gasto no encontrado")
    if expense.status != ExpenseStatus.draft:
        raise HTTPException(400, "Solo se pueden editar gastos en borrador")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(expense, k, v)
    db.commit()
    return _expense_out(expense)


@router.post("/my/{expense_id}/submit", summary="Enviar gasto para aprobación")
def submit_expense(
    expense_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    expense = db.query(Expense).filter(Expense.id == expense_id, Expense.user_id == current_user.id).first()
    if not expense: raise HTTPException(404)
    if expense.status != ExpenseStatus.draft:
        raise HTTPException(400, "El gasto ya ha sido enviado")
    expense.status = ExpenseStatus.submitted
    expense.submitted_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


@router.post("/my/{expense_id}/recall", summary="Retirar gasto enviado")
def recall_expense(
    expense_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    expense = db.query(Expense).filter(Expense.id == expense_id, Expense.user_id == current_user.id).first()
    if not expense: raise HTTPException(404)
    if expense.status != ExpenseStatus.submitted:
        raise HTTPException(400, "Solo se pueden retirar gastos enviados")
    expense.status = ExpenseStatus.draft
    expense.submitted_at = None
    db.commit()
    return {"ok": True}


@router.post("/{expense_id}/review", summary="Aprobar o rechazar gasto (PM/admin)")
def review_expense(
    expense_id: str,
    payload: ReviewPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "expense", expense_id, action="approve")
    return svc_review_expense(expense_id, payload.approved, payload.rejection_reason, current_user, db)


@router.post("/{expense_id}/reimburse", summary="Marcar como reembolsado")
def reimburse_expense(
    expense_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    expense = db.query(Expense).filter(Expense.id == expense_id).first()
    if not expense: raise HTTPException(404)
    if expense.status != ExpenseStatus.approved:
        raise HTTPException(400, "El gasto debe estar aprobado")
    expense.status = ExpenseStatus.reimbursed
    expense.reimbursed_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


@router.delete("/my/{expense_id}", summary="Eliminar gasto en borrador")
def delete_expense(
    expense_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    expense = db.query(Expense).filter(Expense.id == expense_id, Expense.user_id == current_user.id).first()
    if not expense: raise HTTPException(404)
    if expense.status not in [ExpenseStatus.draft, ExpenseStatus.rejected]:
        raise HTTPException(400, "Solo se pueden eliminar gastos en borrador o rechazados")
    db.delete(expense); db.commit()
    return {"ok": True}

@router.get("/export", summary="Exportar gastos a Excel")
def export_expenses(
    date_from: Optional[date] = None,
    date_to:   Optional[date] = None,
    status:    Optional[str]  = None,
    category:  Optional[str]  = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return export_expenses_excel(date_from, date_to, status, category, db)


# ── OCR receipt scanning (v24) ────────────────────────────────────────────────
@router.post("/ocr", summary="Escaner OCR de recibo con IA — extrae importe, comercio y fecha")
async def ocr_receipt(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    allowed_types = {"image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf"}
    if file.content_type not in allowed_types:
        raise HTTPException(400, f"Tipo de archivo no soportado: {file.content_type}. Usa JPEG, PNG, WebP o PDF.")
    image_bytes = await file.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(400, "El archivo no puede superar 10 MB.")
    extracted = await svc_ocr_receipt(image_bytes, file.content_type)
    return {"ok": True, "extracted": extracted}
