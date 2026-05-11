"""
expense_service.py — Lógica de negocio para gastos.

Funciones exportadas:
  review_expense(expense_id, approved, rejection_reason, current_user, db)
  export_expenses_excel(date_from, date_to, status, category, db) -> StreamingResponse
  ocr_receipt(image_bytes, content_type) -> dict  (async)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User
from app.models.expenses import Expense, ExpenseStatus
from app.models.project import Project
from app.models.project import ProjectStatus
from app.models.user import User as UserModel
from app.models.user import UserRole
from app.services.audit import audit_log
from app.services.notifications import notify_user
from app.services.numbering import next_numbered_code
from datetime import datetime as _dt
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

logger = logging.getLogger(__name__)

_CATEGORY_LABELS = {
    "travel": "Viaje",
    "accommodation": "Alojamiento",
    "meals": "Comidas",
    "software": "Software",
    "hardware": "Hardware",
    "training": "Formación",
    "marketing": "Marketing",
    "office": "Oficina",
    "other": "Otro",
}

_STATUS_LABELS = {
    "draft": "Borrador",
    "submitted": "Enviado",
    "approved": "Aprobado",
    "rejected": "Rechazado",
    "reimbursed": "Reembolsado",
}


# ── Review (approve / reject) ──────────────────────────────────────────────────

def review_expense(
    expense_id: str,
    approved: bool,
    rejection_reason: Optional[str],
    current_user: User,
    db: Session,
) -> dict:
    """Approve or reject a submitted expense. Sends notification and writes audit log."""

    expense = db.query(Expense).filter(Expense.id == expense_id).first()
    if not expense:
        raise HTTPException(404)
    if expense.status != ExpenseStatus.submitted:
        raise HTTPException(400, "El gasto no está pendiente de revisión")

    expense.reviewed_by = current_user.id
    expense.reviewed_at = datetime.now(timezone.utc)

    if approved:
        expense.status = ExpenseStatus.approved
        expense.rejection_reason = None
        notify_user(
            db, expense.user_id, "expense_approved",
            f"Gasto aprobado: {expense.description[:50]}",
            f"{current_user.full_name} aprobó tu gasto de {expense.amount} {expense.currency}",
            resource="expenses", resource_id=expense.id, action_url="/expenses",
        )
    else:
        expense.status = ExpenseStatus.rejected
        expense.rejection_reason = rejection_reason
        notify_user(
            db, expense.user_id, "expense_rejected",
            f"Gasto rechazado: {expense.description[:50]}",
            f"Motivo: {rejection_reason or 'Sin motivo especificado'}",
            resource="expenses", resource_id=expense.id, action_url="/expenses",
        )

    audit_log(
        db, current_user,
        "APPROVE" if approved else "REJECT",
        "expenses", expense.id, expense.description,
        new_values={"status": expense.status, "amount": expense.amount},
    )
    db.commit()
    return {"ok": True, "status": expense.status}


# ── Excel export ───────────────────────────────────────────────────────────────

def export_expenses_excel(
    date_from: Optional[object],
    date_to: Optional[object],
    status: Optional[str],
    category: Optional[str],
    db: Session,
):
    """
    Build and return a StreamingResponse with an Excel workbook of filtered expenses.
    """
    import io

    q = db.query(Expense).join(UserModel, Expense.user_id == UserModel.id, isouter=True)
    if date_from:
        q = q.filter(Expense.expense_date >= date_from)
    if date_to:
        q = q.filter(Expense.expense_date <= date_to)
    if status:
        q = q.filter(Expense.status == status)
    if category:
        q = q.filter(Expense.category == category)
    expenses = q.order_by(Expense.expense_date.desc()).all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Gastos"

    headers = [
        "Fecha", "Empleado", "Categoría", "Descripción", "Importe",
        "Moneda", "Proyecto", "Estado", "Facturable", "Notas", "URL Justificante",
    ]
    header_fill = PatternFill("solid", fgColor="0D1B3E")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    for row, e in enumerate(expenses, 2):
        row_data = [
            str(e.expense_date) if e.expense_date else "",
            e.user.full_name if e.user else "",
            _CATEGORY_LABELS.get(e.category, e.category or ""),
            e.description or "",
            e.amount or 0,
            e.currency or settings.DEFAULT_CURRENCY,
            e.project.name if hasattr(e, "project") and e.project else "",
            _STATUS_LABELS.get(str(e.status).replace("ExpenseStatus.", ""), str(e.status)),
            "Sí" if e.is_billable else "No",
            e.notes or "",
            e.receipt_url or "",
        ]
        for col, val in enumerate(row_data, 1):
            ws.cell(row=row, column=col, value=val)

    for col, w in enumerate([12, 20, 14, 35, 10, 8, 20, 12, 10, 25, 35], 1):
        ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = w

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"gastos_{date_from or 'todos'}_{date_to or 'hoy'}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── OCR receipt ────────────────────────────────────────────────────────────────

async def ocr_receipt(image_bytes: bytes, content_type: str) -> dict:
    """
    Send a receipt image to Claude Vision and extract structured expense fields.
    Returns: { amount, currency, merchant, date, category, description }
    Raises HTTPException on error.
    """
    import base64
    import json as _json
    import urllib.request

    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(503, "API de IA no configurada (ANTHROPIC_API_KEY ausente).")

    b64 = base64.b64encode(image_bytes).decode()
    media_type = content_type if content_type != "application/pdf" else "image/png"

    _SYSTEM = (
        "Eres un asistente experto en contabilidad. Analiza la imagen de un recibo o factura y extrae "
        "los datos estructurados. Responde SOLO con un JSON válido sin markdown, con las claves: "
        "amount (número), currency (ISO 4217 de 3 letras), merchant (nombre del comercio o emisor), "
        "date (YYYY-MM-DD), category (una de: travel|accommodation|meals|software|hardware|training|subcontract|other), "
        "description (descripción breve en español de máximo 80 caracteres). "
        "Si no puedes leer un campo devuelve null para ese campo."
    )

    payload = {
        "model": "claude-3-5-sonnet-20241022",
        "max_tokens": 500,
        "system": _SYSTEM,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                {"type": "text", "text": "Por favor extrae los datos de este recibo."},
            ],
        }],
    }
    data = _json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{settings.ANTHROPIC_API_URL}/messages",
        data=data,
        headers={
            "Content-Type": "application/json",
            "x-api-key": settings.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            response_body = _json.loads(resp.read().decode())

        raw_text = response_body["content"][0]["text"].strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1].lstrip("json").strip()

        extracted = _json.loads(raw_text)

        if extracted.get("date"):
            try:
                _dt.strptime(extracted["date"], "%Y-%m-%d")
            except ValueError:
                extracted["date"] = None

        return {
            "amount": extracted.get("amount"),
            "currency": extracted.get("currency", settings.DEFAULT_CURRENCY),
            "merchant": extracted.get("merchant"),
            "date": extracted.get("date"),
            "category": extracted.get("category", "other"),
            "description": extracted.get("description", ""),
        }
    except HTTPException:
        raise
    except _json.JSONDecodeError:
        raise HTTPException(422, "La IA devolvió un formato inesperado. Intenta con otra imagen.")
    except Exception as exc:
        logger.error("OCR receipt error: %s", exc, exc_info=True)
        raise HTTPException(500, "Error al procesar el recibo. Por favor, inténtalo de nuevo.")


# ── List / query helpers ───────────────────────────────────────────────────────

def list_my_expenses(
    db: Session,
    user_id: str,
    status: Optional[str] = None,
    project_id: Optional[str] = None,
    date_from=None,
    date_to=None,
):

    q = db.query(Expense).options(
        joinedload(Expense.project), joinedload(Expense.reviewer)
    ).filter(Expense.user_id == user_id)
    if status:      q = q.filter(Expense.status == status)
    if project_id:  q = q.filter(Expense.project_id == project_id)
    if date_from:   q = q.filter(Expense.expense_date >= date_from)
    if date_to:     q = q.filter(Expense.expense_date <= date_to)
    return q.order_by(Expense.expense_date.desc()).all()


def list_pending_expenses(db: Session, project_id: Optional[str] = None):

    q = db.query(Expense).options(
        joinedload(Expense.user), joinedload(Expense.project)
    ).filter(Expense.status == ExpenseStatus.submitted)
    if project_id:
        q = q.filter(Expense.project_id == project_id)
    return q.order_by(Expense.submitted_at).all()


def list_all_expenses(
    db: Session,
    current_user,
    status: Optional[str] = None,
    user_id: Optional[str] = None,
):

    q = db.query(Expense)
    if current_user.role not in (UserRole.admin, UserRole.pm, UserRole.hr):
        q = q.filter(Expense.user_id == current_user.id)
    elif not current_user.is_superadmin and current_user.organization_id:
        org_user_ids = db.query(UserModel.id).filter(
            UserModel.organization_id == current_user.organization_id
        ).scalar_subquery()
        org_project_ids = db.query(Project.id).filter(
            Project.organization_id == current_user.organization_id
        ).scalar_subquery()
        q = q.filter(or_(
            Expense.user_id.in_(org_user_ids),
            Expense.project_id.in_(org_project_ids),
        ))
    if status:   q = q.filter(Expense.status == status)
    if user_id:  q = q.filter(Expense.user_id == user_id)
    return q.order_by(Expense.created_at.desc()).limit(200).all()


def list_team_expenses(
    db: Session,
    current_user,
    status=None,
    project_id=None,
    user_id=None,
    date_from=None,
    date_to=None,
):

    q = db.query(Expense).options(
        joinedload(Expense.user), joinedload(Expense.project), joinedload(Expense.reviewer)
    )
    if not current_user.is_superadmin and current_user.organization_id:
        org_user_ids = db.query(UserModel.id).filter(
            UserModel.organization_id == current_user.organization_id
        ).scalar_subquery()
        org_project_ids = db.query(Project.id).filter(
            Project.organization_id == current_user.organization_id
        ).scalar_subquery()
        q = q.filter(or_(
            Expense.user_id.in_(org_user_ids),
            Expense.project_id.in_(org_project_ids),
        ))
    if status:      q = q.filter(Expense.status == status)
    if project_id:  q = q.filter(Expense.project_id == project_id)
    if user_id:     q = q.filter(Expense.user_id == user_id)
    if date_from:   q = q.filter(Expense.expense_date >= date_from)
    if date_to:     q = q.filter(Expense.expense_date <= date_to)
    return q.order_by(Expense.expense_date.desc()).all()


def list_project_expenses(db: Session, project_id: str):

    return db.query(Expense).options(joinedload(Expense.user)).filter(
        Expense.project_id == project_id,
        Expense.status.in_(["approved", "reimbursed"]),
    ).all()


# ── Create / update / delete ───────────────────────────────────────────────────

def create_expense_record(db: Session, payload, user_id: str, code: str):

    if payload.project_id:
        project = db.query(Project).filter(Project.id == payload.project_id).first()
        if not project:
            raise HTTPException(404, "Proyecto no encontrado")
        if project.status in [
            ProjectStatus.completed, ProjectStatus.closed,
            ProjectStatus.cancelled, ProjectStatus.archived,
        ]:
            raise HTTPException(400, "No se pueden generar gastos facturables en proyectos cerrados")

    expense = Expense(code=code, user_id=user_id, **payload.model_dump())

    if expense.is_billable and expense.project_id:
        project = db.query(Project).filter(Project.id == expense.project_id).first()
        if project and project.status not in [ProjectStatus.active, ProjectStatus.planning]:
            raise HTTPException(400, "No se puede marcar gasto como facturable en proyecto no activo")

    db.add(expense)
    db.commit()
    db.refresh(expense)
    expense = db.query(Expense).options(joinedload(Expense.project)).filter(
        Expense.id == expense.id
    ).first()
    from app.core.events import emit, EventType
    emit(db, EventType.EXPENSE_SUBMITTED,
         {"code": expense.code, "amount": expense.amount, "category": expense.category,
          "project_id": expense.project_id, "status": str(expense.status)},
         resource_type="expense", resource_id=expense.id, project_id=expense.project_id)
    return expense


def admin_update_expense(db: Session, expense_id: str, payload):

    e = db.query(Expense).filter(Expense.id == expense_id).first()
    if not e:
        raise HTTPException(404, "Gasto no encontrado")

    if payload.is_billable and e.project_id:
        project = db.query(Project).filter(Project.id == e.project_id).first()
        if project and project.status not in [ProjectStatus.active, ProjectStatus.planning]:
            raise HTTPException(400, "No se puede marcar gasto como facturable en proyecto no activo")

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(e, k, v)
    db.commit()
    db.refresh(e)
    return e


def update_my_expense(db: Session, expense_id: str, user_id: str, payload):

    expense = db.query(Expense).filter(
        Expense.id == expense_id, Expense.user_id == user_id
    ).first()
    if not expense:
        raise HTTPException(404, "Gasto no encontrado")
    if expense.status != ExpenseStatus.draft:
        raise HTTPException(400, "Solo se pueden editar gastos en borrador")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(expense, k, v)
    db.commit()
    return expense


def submit_expense_record(db: Session, expense_id: str, user_id: str) -> dict:

    expense = db.query(Expense).filter(
        Expense.id == expense_id, Expense.user_id == user_id
    ).first()
    if not expense:
        raise HTTPException(404)
    if expense.status != ExpenseStatus.draft:
        raise HTTPException(400, "El gasto ya ha sido enviado")
    expense.status = ExpenseStatus.submitted
    expense.submitted_at = datetime.now(timezone.utc)
    db.commit()
    from app.core.events import emit, EventType
    emit(db, EventType.EXPENSE_SUBMITTED,
         {"amount": expense.amount, "category": expense.category, "project_id": expense.project_id},
         resource_type="expense", resource_id=expense_id, project_id=expense.project_id)
    return {"ok": True}


def recall_expense_record(db: Session, expense_id: str, user_id: str) -> dict:

    expense = db.query(Expense).filter(
        Expense.id == expense_id, Expense.user_id == user_id
    ).first()
    if not expense:
        raise HTTPException(404)
    if expense.status != ExpenseStatus.submitted:
        raise HTTPException(400, "Solo se pueden retirar gastos enviados")
    expense.status = ExpenseStatus.draft
    expense.submitted_at = None
    db.commit()
    return {"ok": True}


def reimburse_expense_record(db: Session, expense_id: str) -> dict:

    expense = db.query(Expense).filter(Expense.id == expense_id).first()
    if not expense:
        raise HTTPException(404)
    if expense.status != ExpenseStatus.approved:
        raise HTTPException(400, "El gasto debe estar aprobado")
    expense.status = ExpenseStatus.reimbursed
    expense.reimbursed_at = datetime.now(timezone.utc)
    db.commit()
    from app.core.events import emit, EventType
    emit(db, EventType.EXPENSE_APPROVED,
         {"amount": expense.amount, "category": expense.category, "project_id": expense.project_id,
          "status": "reimbursed"},
         resource_type="expense", resource_id=expense_id, project_id=expense.project_id)
    return {"ok": True}


def delete_my_expense(db: Session, expense_id: str, user_id: str) -> dict:

    expense = db.query(Expense).filter(
        Expense.id == expense_id, Expense.user_id == user_id
    ).first()
    if not expense:
        raise HTTPException(404)
    if expense.status not in [ExpenseStatus.draft, ExpenseStatus.rejected]:
        raise HTTPException(400, "Solo se pueden eliminar gastos en borrador o rechazados")
    db.delete(expense)
    db.commit()
    return {"ok": True, "message": "Gasto eliminado correctamente"}


# ── Label constants + serialization helpers ────────────────────────────────

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


def next_expense_code(db: Session) -> str:
    return next_numbered_code(db, "expense", prefix="EXP", padding=4)


def serialize_expense(e) -> dict:
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
