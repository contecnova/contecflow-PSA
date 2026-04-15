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
    from fastapi import HTTPException
    from app.models.expenses import Expense, ExpenseStatus
    from app.services.audit import audit_log
    from app.services.notifications import notify_user

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
    from fastapi.responses import StreamingResponse
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from app.models.expenses import Expense
    from app.models.user import User as UserModel

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
    from datetime import datetime as _dt
    from fastapi import HTTPException

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
