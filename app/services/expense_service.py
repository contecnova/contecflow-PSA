"""
expense_service.py — Lógica de negocio para gastos.

Funciones exportadas:
  review_expense(expense_id, approved, rejection_reason, current_user, db)
  export_expenses_excel(date_from, date_to, status, category, db) -> StreamingResponse
  ocr_receipt(db, usuario, image_bytes, content_type) -> dict  (síncrona: el endpoint la pasa por run_db)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User
from app.models.expenses import Expense, ExpenseStatus
from app.services.gastos_avanzados import del_proyecto
from app.models.project import Project
from app.models.project import ProjectStatus
from app.models.user import User as UserModel
from app.models.user import UserRole
from app.services.audit import audit_log
from app.core.errores import ErrorDeDominio

# ── Status alias normalizer ────────────────────────────────────────────────────
# PostgreSQL enforces enum types strictly. The frontend uses "pending" to mean
# "submitted" (awaiting approval). Map legacy aliases to canonical enum values.
_STATUS_ALIASES: dict[str, str] = {
    "pending": "submitted",
}

def _normalize_status(status: Optional[str]) -> Optional[str]:
    if status is None:
        return None
    return _STATUS_ALIASES.get(status.lower(), status)
from app.services.notifications import notify_user
from app.services.numbering import next_numbered_code
from datetime import datetime as _dt
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
        raise ErrorDeDominio(404)
    if expense.status != ExpenseStatus.submitted:
        raise ErrorDeDominio(400, "El gasto no está pendiente de revisión")

    avisos: list[str] = []
    if approved:   # control presupuestario: avisa, o 409 si BUDGET_CONTROL_POLICY = bloquear
        from app.services.presupuestos_seguir import control_de_gasto
        avisos = control_de_gasto(db, expense)

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

    from app.services.approval_engine import fuentes
    fuentes.cerrar(db, "expense", expense.id, "approved" if approved else "rejected",
                   f"Decidido en Gastos por {current_user.full_name}")
    audit_log(
        db, current_user,
        "APPROVE" if approved else "REJECT",
        "expenses", expense.id, expense.description,
        new_values={"status": expense.status, "amount": expense.amount},
    )
    db.commit()
    return {"ok": True, "status": expense.status, "avisos_de_presupuesto": avisos}


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

    q = db.query(Expense).join(
        UserModel, Expense.user_id == UserModel.id, isouter=True
    ).filter(Expense.is_active == True)  # audit #36 soft-delete
    if date_from:
        q = q.filter(Expense.expense_date >= date_from)
    if date_to:
        q = q.filter(Expense.expense_date <= date_to)
    if status:
        q = q.filter(Expense.status == _normalize_status(status))
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

def ocr_receipt(db: Session, usuario, image_bytes: bytes, content_type: str) -> dict:
    """Lee un recibo (imagen o PDF) con el proveedor de IA de la empresa.

    Revisión 2026-11: iba directo a Anthropic con `ANTHROPIC_API_KEY`; con otro
    proveedor no había OCR, y se saltaba la gobernanza y el tope de gasto.
    Ahora pasa por `call_ai` con el recibo como adjunto, y las categorías salen
    del modelo (`ExpenseCategory`), no de una lista escrita en el texto.
    """
    import base64
    import json as _json
    from app.models.expenses import ExpenseCategory
    from app.services.ai_provider_service import call_ai, es_aviso_de_ia

    categorias = "|".join(c.value for c in ExpenseCategory)
    sistema = (
        "Eres un asistente experto en contabilidad. Analiza la imagen de un recibo o factura y extrae "
        "los datos estructurados. Responde SOLO con un JSON válido sin markdown, con las claves: "
        "amount (número), currency (ISO 4217 de 3 letras), merchant (nombre del comercio o emisor), "
        f"date (YYYY-MM-DD), category (una de: {categorias}), "
        "description (descripción breve en español de máximo 80 caracteres). "
        "Si no puedes leer un campo devuelve null para ese campo."
    )
    mensaje = {"role": "user", "content": "Por favor extrae los datos de este recibo.",
               "adjuntos": [{"media": content_type, "datos": base64.b64encode(image_bytes).decode()}]}
    texto = call_ai(
        db, [mensaje], system=sistema, module="expenses_ocr", user_id=getattr(usuario, "id", None),
        max_tokens=500, is_superadmin=bool(getattr(usuario, "is_superadmin", False)),
        organization_id=getattr(usuario, "organization_id", None))
    if es_aviso_de_ia(texto):
        raise ErrorDeDominio(503, texto)
    crudo = texto.strip()
    if crudo.startswith("```"):
        crudo = crudo.split("```")[1].removeprefix("json").strip()
    try:
        extraido = _json.loads(crudo)
    except _json.JSONDecodeError:
        raise ErrorDeDominio(422, "La IA devolvió un formato inesperado. Intenta con otra imagen.")
    if extraido.get("date"):
        try:
            _dt.strptime(extraido["date"], "%Y-%m-%d")
        except ValueError:
            extraido["date"] = None
    categoria = extraido.get("category")
    return {
        "amount": extraido.get("amount"),
        "currency": extraido.get("currency") or settings.DEFAULT_CURRENCY,
        "merchant": extraido.get("merchant"),
        "date": extraido.get("date"),
        "category": categoria if categoria in {c.value for c in ExpenseCategory} else ExpenseCategory.other.value,
        "description": extraido.get("description") or "",
    }


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
    ).filter(
        Expense.user_id == user_id,
        Expense.is_active == True,  # audit #36 soft-delete
    )
    if status:      q = q.filter(Expense.status == _normalize_status(status))
    if project_id:  q = q.filter(del_proyecto(project_id))
    if date_from:   q = q.filter(Expense.expense_date >= date_from)
    if date_to:     q = q.filter(Expense.expense_date <= date_to)
    return q.order_by(Expense.expense_date.desc()).all()



def list_pending_expenses(db: Session, project_id: Optional[str] = None):

    q = db.query(Expense).options(
        joinedload(Expense.user), joinedload(Expense.project)
    ).filter(
        Expense.status == ExpenseStatus.submitted,
        Expense.is_active == True,  # audit #36 soft-delete
    )
    if project_id:
        q = q.filter(del_proyecto(project_id))
    return q.order_by(Expense.submitted_at).all()


def list_all_expenses(
    db: Session,
    current_user,
    status: Optional[str] = None,
    user_id: Optional[str] = None,
):

    q = db.query(Expense).filter(Expense.is_active == True)  # audit #36 soft-delete
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
    if status:   q = q.filter(Expense.status == _normalize_status(status))
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
    ).filter(Expense.is_active == True)  # audit #36 soft-delete
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
    if status:      q = q.filter(Expense.status == _normalize_status(status))
    if project_id:  q = q.filter(del_proyecto(project_id))
    if user_id:     q = q.filter(Expense.user_id == user_id)
    if date_from:   q = q.filter(Expense.expense_date >= date_from)
    if date_to:     q = q.filter(Expense.expense_date <= date_to)
    return q.order_by(Expense.expense_date.desc()).all()


def list_project_expenses(db: Session, project_id: str):

    return db.query(Expense).options(joinedload(Expense.user)).filter(
        del_proyecto(project_id),   # suyo o con una parte del reparto
        Expense.status.in_(["approved", "reimbursed"]),
    ).all()


# ── Create / update / delete ───────────────────────────────────────────────────

def create_expense_record(db: Session, payload, user_id: str, code: str):

    if payload.project_id:
        project = db.query(Project).filter(Project.id == payload.project_id).first()
        if not project:
            raise ErrorDeDominio(404, "Proyecto no encontrado")
        if project.status in [
            ProjectStatus.completed, ProjectStatus.closed,
            ProjectStatus.cancelled, ProjectStatus.archived,
        ]:
            raise ErrorDeDominio(400, "No se pueden generar gastos facturables en proyectos cerrados")

    expense = Expense(code=code, user_id=user_id, **payload.model_dump())
    from app.services.gastos_avanzados import aplicar_kilometraje
    aplicar_kilometraje(db, expense)

    if expense.is_billable and expense.project_id:
        project = db.query(Project).filter(Project.id == expense.project_id).first()
        if project and project.status not in [ProjectStatus.active, ProjectStatus.planning]:
            raise ErrorDeDominio(400, "No se puede marcar gasto como facturable en proyecto no activo")

    db.add(expense)
    db.commit()
    db.refresh(expense)
    expense = db.query(Expense).options(joinedload(Expense.project)).filter(
        Expense.id == expense.id
    ).first()
    # Crear deja un borrador: el evento «enviado» lo emite el envío (`submit_expense_record`).
    return expense


def admin_update_expense(db: Session, expense_id: str, payload):

    e = db.query(Expense).filter(Expense.id == expense_id).first()
    if not e:
        raise ErrorDeDominio(404, "Gasto no encontrado")

    if payload.is_billable and e.project_id:
        project = db.query(Project).filter(Project.id == e.project_id).first()
        if project and project.status not in [ProjectStatus.active, ProjectStatus.planning]:
            raise ErrorDeDominio(400, "No se puede marcar gasto como facturable en proyecto no activo")

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(e, k, v)
    from app.services.gastos_avanzados import aplicar_kilometraje
    aplicar_kilometraje(db, e)
    db.commit()
    db.refresh(e)
    return e


def update_my_expense(db: Session, expense_id: str, user_id: str, payload):

    expense = db.query(Expense).filter(
        Expense.id == expense_id, Expense.user_id == user_id
    ).first()
    if not expense:
        raise ErrorDeDominio(404, "Gasto no encontrado")
    if expense.status not in (ExpenseStatus.draft, ExpenseStatus.rejected):
        raise ErrorDeDominio(400, "Solo se pueden editar gastos en borrador o rechazados")
    if expense.status == ExpenseStatus.rejected:
        # Corregir un gasto rechazado lo devuelve a borrador para volver a enviarlo;
        # el motivo del rechazo se queda a la vista hasta entonces.
        expense.status = ExpenseStatus.draft
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(expense, k, v)
    from app.services.gastos_avanzados import aplicar_kilometraje
    aplicar_kilometraje(db, expense)
    db.commit()
    return expense


def submit_expense_record(db: Session, expense_id: str, user_id: str) -> dict:

    expense = db.query(Expense).filter(
        Expense.id == expense_id, Expense.user_id == user_id
    ).first()
    if not expense:
        raise ErrorDeDominio(404)
    if expense.status != ExpenseStatus.draft:
        raise ErrorDeDominio(400, "El gasto ya ha sido enviado")
    # Revisión 2026-11: las políticas de gasto bloquean aquí o dejan el aviso para la aprobación.
    from app.services.gastos_avanzados import antes_de_enviar
    contexto_politica = antes_de_enviar(db, expense)
    expense.status = ExpenseStatus.submitted
    expense.submitted_at = datetime.now(timezone.utc)
    expense.rejection_reason = None
    db.commit()
    from app.core.events import emit, EventType
    emit(db, EventType.EXPENSE_SUBMITTED,
         {"amount": expense.amount, "category": expense.category, "project_id": expense.project_id},
         resource_type="expense", resource_id=expense_id, project_id=expense.project_id)
    from app.services.approval_engine import fuentes
    fuentes.abrir(db, "expense", expense.id,
                  f"Gasto {expense.code or ''} · {expense.description or ''} · {expense.amount} {expense.currency}",
                  user_id, {"amount": expense.amount, "category": str(getattr(expense.category, "value", expense.category)),
                            "project_id": expense.project_id, **contexto_politica})
    return {"ok": True}


def recall_expense_record(db: Session, expense_id: str, user_id: str) -> dict:

    expense = db.query(Expense).filter(
        Expense.id == expense_id, Expense.user_id == user_id
    ).first()
    if not expense:
        raise ErrorDeDominio(404)
    if expense.status != ExpenseStatus.submitted:
        raise ErrorDeDominio(400, "Solo se pueden retirar gastos enviados")
    expense.status = ExpenseStatus.draft
    expense.submitted_at = None
    from app.services.approval_engine import fuentes
    fuentes.cerrar(db, "expense", expense.id, "cancelled", "Retirado por quien lo envió")
    db.commit()
    return {"ok": True}


def reimburse_expense_record(db: Session, expense_id: str) -> dict:

    expense = db.query(Expense).filter(Expense.id == expense_id).first()
    if not expense:
        raise ErrorDeDominio(404)
    if expense.status != ExpenseStatus.approved:
        raise ErrorDeDominio(400, "El gasto debe estar aprobado")
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
        raise ErrorDeDominio(404)
    if expense.status not in [ExpenseStatus.draft, ExpenseStatus.rejected]:
        raise ErrorDeDominio(400, "Solo se pueden eliminar gastos en borrador o rechazados")
    # audit #36 soft-delete — preserva el histórico para auditoría financiera.
    expense.is_active = False
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
        "km": e.km,
        "policy_flags": _avisos(e),
        "created_at": str(e.created_at)[:10] if e.created_at else None,
    }


def _avisos(e) -> list:
    from app.services.gastos_avanzados import avisos_guardados
    return avisos_guardados(e)
