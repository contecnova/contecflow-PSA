"""
Expenses endpoint — project-linked expense management with approval workflow.
"""
from fastapi import APIRouter, Depends, Query, UploadFile, File
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date

from app.db.session import get_db
from app.core.deps import (
    get_current_user,
    require_admin,
    require_admin_or_pm,
    require_any_manager,
    require_internal_user,
)
from app.core.abac_enforce import enforce_abac
from app.core.uploads import UploadProfile, read_and_validate_upload
from app.core.responses import APIListResponse, APIResponse
from app.models.user import User
from app.services.expense_service import (
    review_expense as svc_review_expense,
    export_expenses_excel,
    ocr_receipt as svc_ocr_receipt,
    list_my_expenses as svc_list_my_expenses,
    list_pending_expenses as svc_list_pending_expenses,
    list_all_expenses as svc_list_all_expenses,
    list_team_expenses as svc_list_team_expenses,
    create_expense_record as svc_create_expense,
    admin_update_expense as svc_admin_update_expense,
    update_my_expense as svc_update_my_expense,
    submit_expense_record as svc_submit_expense,
    recall_expense_record as svc_recall_expense,
    reimburse_expense_record as svc_reimburse_expense,
    delete_my_expense as svc_delete_my_expense,
    next_expense_code as _next_code, serialize_expense as _expense_out,
)
from app.schemas.expenses import ExpenseIn, ExpenseCreate, ExpenseUpdate, ExpenseReviewPayload as ReviewPayload

router = APIRouter()


@router.get("/my", response_model=APIListResponse[dict], summary="Mis gastos")
def my_expenses(
    status: Optional[str] = None,
    project_id: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = [_expense_out(e) for e in svc_list_my_expenses(
        db, current_user.id, status, project_id, date_from, date_to
    )]
    return APIListResponse.ok(items=items)


@router.get("/pending", summary="Gastos pendientes de aprobación (PM/admin)")
def pending_expenses(
    project_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "expense", action="read")
    items = [_expense_out(e) for e in svc_list_pending_expenses(db, project_id)]
    return APIListResponse.ok(items=items, total=len(items))


@router.get("", summary="Listar todos los gastos (admin/PM) — alias de /team")
def list_all_expenses_alias(
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
    status: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
):
    items = [_expense_out(e) for e in svc_list_all_expenses(db, cu, status, user_id)]
    return APIListResponse.ok(items=items, total=len(items))

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
    return APIResponse.ok(data={
        "expenses": [_expense_out(e) for e in expenses],
        "total": round(total, 2),
        "billable_total": round(billable, 2),
        "by_category": {k: round(v, 2) for k, v in by_category.items()},
    })


@router.get("/summary/{project_id}", summary="Resumen de gastos por proyecto")
def project_expense_summary(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    # Revisión 2026-11: con reparto entre proyectos cuenta la parte de este proyecto.
    from app.services.gastos_avanzados import gastos_de_proyecto
    partes = gastos_de_proyecto(db, project_id)
    expenses = [e for e, _ in partes]
    total = sum(importe for _, importe in partes)
    billable = sum(importe for e, importe in partes if e.is_billable)
    by_cat: dict = {}
    for e, importe in partes:
        by_cat[e.category] = by_cat.get(e.category, 0) + importe
    return APIResponse.ok(data={
        "total": round(total, 2),
        "billable": round(billable, 2),
        "non_billable": round(total - billable, 2),
        "count": len(expenses),
        "by_category": {k: round(v, 2) for k, v in by_cat.items()},
        "expenses": [_expense_out(e) for e in expenses],
    })


@router.post("", summary="Crear gasto")
def create_expense(
    payload: ExpenseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: excepcion revisada: presentar un gasto propio
):
    expense = svc_create_expense(db, payload, current_user.id, _next_code(db))
    return APIResponse.ok(data=_expense_out(expense))


@router.patch("/{expense_id}", summary="Editar gasto (admin/PM, cualquier estado)")
def update_expense_admin(
    expense_id: str,
    payload: ExpenseIn,
    db: Session = Depends(get_db),
    cu: User = Depends(require_admin_or_pm),
):
    e = svc_admin_update_expense(db, expense_id, payload)
    return APIResponse.ok(data=_expense_out(e))

@router.patch("/my/{expense_id}", summary="Editar mi gasto (solo borrador)")
def update_expense(
    expense_id: str,
    payload: ExpenseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    expense = svc_update_my_expense(db, expense_id, current_user.id, payload)
    return APIResponse.ok(data=_expense_out(expense))


@router.post("/my/{expense_id}/submit", summary="Enviar gasto para aprobación")
def submit_expense(
    expense_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data=svc_submit_expense(db, expense_id, current_user.id))


@router.post("/my/{expense_id}/recall", summary="Retirar gasto enviado")
def recall_expense(
    expense_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data=svc_recall_expense(db, expense_id, current_user.id))


@router.post("/{expense_id}/review", summary="Aprobar o rechazar gasto (PM/admin)")
def review_expense(
    expense_id: str,
    payload: ReviewPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "expense", expense_id, action="approve")
    return APIResponse.ok(data=svc_review_expense(expense_id, payload.approved, payload.rejection_reason, current_user, db))


@router.post("/{expense_id}/reimburse", summary="Marcar como reembolsado")
def reimburse_expense(
    expense_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "expense", expense_id, action="approve")
    return APIResponse.ok(data=svc_reimburse_expense(db, expense_id))


@router.delete("/my/{expense_id}", summary="Eliminar gasto en borrador")
def delete_expense(
    expense_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enforce_abac(db, current_user, "expense", expense_id, action="delete")
    return APIResponse.ok(data=svc_delete_my_expense(db, expense_id, current_user.id))

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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: excepcion revisada: escanear el recibo del gasto propio
):
    # Auditoría 2026-08 (P1-8): aquí sólo se comprobaba `file.content_type`, que
    # es un valor que elige el cliente — renombrar la cabecera bastaba para
    # colar cualquier contenido. El perfil RECEIPT valida además extensión,
    # bytes mágicos y que el tipo real coincida con el declarado, y acota el
    # tamaño ANTES de bufferizar el fichero completo.
    image_bytes = await read_and_validate_upload(file, UploadProfile.RECEIPT)
    from app.core.async_db import run_db
    extracted = await run_db(svc_ocr_receipt, db, current_user, image_bytes, file.content_type)
    return APIResponse.ok(data={"ok": True, "extracted": extracted})


# ── Revisión 2026-11: políticas, justificantes y reparto ──────────────────────
# La lógica vive en `app/services/gastos_avanzados.py`.

from pydantic import BaseModel, Field  # noqa: E402

from app.services import gastos_avanzados as gav  # noqa: E402


class PoliticaIn(BaseModel):
    nombre: Optional[str] = Field(None, min_length=2, max_length=200)
    categoria: Optional[str] = Field(None, max_length=30)
    limite_por_gasto: Optional[float] = Field(None, ge=0)
    limite_diario: Optional[float] = Field(None, ge=0)
    justificante_desde: Optional[float] = Field(None, ge=0)
    justificacion_desde: Optional[float] = Field(None, ge=0)
    accion: Optional[str] = Field(None, pattern="^(bloquear|avisar)$")
    activa: Optional[bool] = None


class ParteIn(BaseModel):
    project_id: str = Field(min_length=1, max_length=36)
    percentage: float = Field(gt=0, le=100)


@router.get("/policies", summary="Políticas de gasto de la empresa")
def list_policies(db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data={"items": gav.politicas(db)})


@router.post("/policies", summary="Crear una política de gasto (admin)")
def create_policy(body: PoliticaIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    return APIResponse.ok(data=gav.crear_politica(db, current_user, body.model_dump(exclude_unset=True)))


@router.patch("/policies/{policy_id}", summary="Editar una política de gasto (admin)")
def update_policy(policy_id: str, body: PoliticaIn, db: Session = Depends(get_db),
                  current_user: User = Depends(require_admin)):
    return APIResponse.ok(data=gav.editar_politica(db, current_user, policy_id, body.model_dump(exclude_unset=True)))


@router.delete("/policies/{policy_id}", summary="Borrar una política de gasto (admin)")
def delete_policy(policy_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    gav.borrar_politica(db, current_user, policy_id)
    return APIResponse.ok(data={"ok": True})


@router.get("/{expense_id}/policy-check", summary="Qué políticas incumple el gasto (antes de enviarlo)")
def policy_check(expense_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data=gav.comprobar(db, current_user, expense_id))


@router.get("/{expense_id}/attachments", summary="Justificantes y documentos del gasto")
def list_attachments(expense_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data={"items": gav.adjuntos(db, current_user, expense_id)})


@router.post("/{expense_id}/attachments", summary="Adjuntar un justificante o documento")
async def add_attachment(expense_id: str, file: UploadFile = File(...), db: Session = Depends(get_db),
                         current_user: User = Depends(require_internal_user)):
    contenido = await read_and_validate_upload(file, UploadProfile.RECEIPT)
    from app.core.async_db import run_db
    return APIResponse.ok(data=await run_db(gav.subir_adjunto, db, current_user, expense_id, contenido,
                                            file.filename or "justificante", file.content_type))


@router.get("/attachments/{attachment_id}/url", summary="URL firmada y de corta vida para ver el justificante")
def attachment_url(attachment_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data={"url": gav.url_de_adjunto(db, current_user, attachment_id)})


@router.delete("/attachments/{attachment_id}", summary="Quitar un justificante")
def delete_attachment(attachment_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    gav.borrar_adjunto(db, current_user, attachment_id)
    return APIResponse.ok(data={"ok": True})


@router.get("/{expense_id}/allocations", summary="Reparto del gasto entre proyectos")
def get_allocations(expense_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data={"items": gav.reparto(db, current_user, expense_id)})


@router.put("/{expense_id}/allocations", summary="Repartir el gasto entre proyectos (suma 100 %; vacío lo quita)")
def put_allocations(expense_id: str, body: list[ParteIn], db: Session = Depends(get_db),
                    current_user: User = Depends(require_internal_user)):
    return APIResponse.ok(data={"items": gav.repartir(db, current_user, expense_id, [p.model_dump() for p in body])})
