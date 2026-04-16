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
    list_my_expenses as svc_list_my_expenses,
    list_pending_expenses as svc_list_pending_expenses,
    list_all_expenses as svc_list_all_expenses,
    list_team_expenses as svc_list_team_expenses,
    list_project_expenses as svc_list_project_expenses,
    create_expense_record as svc_create_expense,
    admin_update_expense as svc_admin_update_expense,
    update_my_expense as svc_update_my_expense,
    submit_expense_record as svc_submit_expense,
    recall_expense_record as svc_recall_expense,
    reimburse_expense_record as svc_reimburse_expense,
    delete_my_expense as svc_delete_my_expense,
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
    return [_expense_out(e) for e in svc_list_my_expenses(
        db, current_user.id, status, project_id, date_from, date_to
    )]


@router.get("/pending", summary="Gastos pendientes de aprobación (PM/admin)")
def pending_expenses(
    project_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "expense", action="read")
    return [_expense_out(e) for e in svc_list_pending_expenses(db, project_id)]


@router.get("", summary="Listar todos los gastos (admin/PM) — alias de /team")
def list_all_expenses_alias(
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
    status: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
):
    return [_expense_out(e) for e in svc_list_all_expenses(db, cu, status, user_id)]

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
    expenses = svc_list_team_expenses(
        db, current_user, status, project_id, user_id, date_from, date_to
    )
    total = sum(e.amount for e in expenses)
    billable = sum(e.amount for e in expenses if e.is_billable)
    by_category: dict = {}
    for e in expenses:
        by_category[e.category] = by_category.get(e.category, 0) + e.amount
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
    expenses = svc_list_project_expenses(db, project_id)
    total = sum(e.amount for e in expenses)
    billable = sum(e.amount for e in expenses if e.is_billable)
    by_cat: dict = {}
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
    expense = svc_create_expense(db, payload, current_user.id, _next_code(db))
    return _expense_out(expense)


@router.patch("/{expense_id}", summary="Editar gasto (admin/PM, cualquier estado)")
def update_expense_admin(
    expense_id: str,
    payload: ExpenseIn,
    db: Session = Depends(get_db),
    cu: User = Depends(require_admin_or_pm),
):
    e = svc_admin_update_expense(db, expense_id, payload)
    return _expense_out(e)

@router.patch("/my/{expense_id}", summary="Editar mi gasto (solo borrador)")
def update_expense(
    expense_id: str,
    payload: ExpenseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    expense = svc_update_my_expense(db, expense_id, current_user.id, payload)
    return _expense_out(expense)


@router.post("/my/{expense_id}/submit", summary="Enviar gasto para aprobación")
def submit_expense(
    expense_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc_submit_expense(db, expense_id, current_user.id)


@router.post("/my/{expense_id}/recall", summary="Retirar gasto enviado")
def recall_expense(
    expense_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc_recall_expense(db, expense_id, current_user.id)


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
    return svc_reimburse_expense(db, expense_id)


@router.delete("/my/{expense_id}", summary="Eliminar gasto en borrador")
def delete_expense(
    expense_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc_delete_my_expense(db, expense_id, current_user.id)

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
