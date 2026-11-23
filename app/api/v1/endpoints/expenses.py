"""
Expenses endpoint — project-linked expense management with approval workflow.
"""
from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date

from app.db.session import get_db
from app.core.deps import (
    get_current_user,
    requiere_capacidad,
)
from app.core.abac_enforce import enforce_abac
from app.core.uploads import UploadProfile, read_and_validate_upload
from app.core.paginacion import Paginacion, exponer, lista_paginada, paginacion
from app.core.responses import APIListResponse, APIResponse
from app.models.user import User
from app.services.expense_service import (
    acotar_gasto_del_externo,
    review_expense as svc_review_expense,
    export_expenses_excel,
    ocr_receipt as svc_ocr_receipt,
    list_my_expenses as svc_list_my_expenses,
    list_pending_expenses as svc_list_pending_expenses,
    list_all_expenses as svc_list_all_expenses,
    team_expenses_page as svc_team_expenses_page,
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


# Rev. 166 (fase 2): búsqueda (`q`: código, descripción y, en pendientes y
# equipo, quien lo pide), categoría y orden (`sort` + `direction`) en el
# servidor, para que paginar no los limite a la página cargada.
_ORDEN = Query(None, pattern="^(code|category|description|amount|status|expense_date|submitted_at)$")
_DIRECCION = Query(None, pattern="^(asc|desc)$")


@router.get("/my", response_model=APIListResponse[dict], summary="Mis gastos")
def my_expenses(
    status: Optional[str] = None,
    project_id: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    category: Optional[str] = Query(None, max_length=30),
    q: Optional[str] = Query(None, max_length=200),
    sort: Optional[str] = _ORDEN,
    direction: Optional[str] = _DIRECCION,
    response: Response = None,
    pagina: Paginacion = Depends(paginacion),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resultado = svc_list_my_expenses(
        db, current_user.id, status, project_id, date_from, date_to, pagina=pagina,
        category=category, texto=q, sort=sort, direction=direction,
    )
    return lista_paginada(response, resultado.mapear(_expense_out))


@router.get("/my/totals", summary="Totales de mis gastos con los mismos filtros (no solo la página)")
def my_expenses_totals(
    status: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    category: Optional[str] = Query(None, max_length=30),
    q: Optional[str] = Query(None, max_length=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.services.expense_service import query_my_expenses, totales_de_lista
    return APIResponse.ok(data=totales_de_lista(
        query_my_expenses(db, current_user.id, status, None, date_from, date_to, category, q)))


@router.get("/pending", summary="Gastos pendientes de aprobación (PM/admin)")
def pending_expenses(
    project_id: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    category: Optional[str] = Query(None, max_length=30),
    q: Optional[str] = Query(None, max_length=200),
    sort: Optional[str] = _ORDEN,
    direction: Optional[str] = _DIRECCION,
    response: Response = None,
    pagina: Paginacion = Depends(paginacion),
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("gastos.responsables")),
):
    enforce_abac(db, current_user, "expense", action="read")
    resultado = svc_list_pending_expenses(db, project_id, pagina=pagina, category=category, texto=q,
                                          date_from=date_from, date_to=date_to, sort=sort, direction=direction)
    return lista_paginada(response, resultado.mapear(_expense_out))


@router.get("/pending/totals", summary="Totales de los gastos pendientes con los mismos filtros")
def pending_expenses_totals(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    category: Optional[str] = Query(None, max_length=30),
    q: Optional[str] = Query(None, max_length=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("gastos.responsables")),
):
    enforce_abac(db, current_user, "expense", action="read")
    from app.services.expense_service import query_pending_expenses, totales_de_lista
    return APIResponse.ok(data=totales_de_lista(query_pending_expenses(db, None, category, q, date_from, date_to)))


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
    category: Optional[str] = Query(None, max_length=30),
    q: Optional[str] = Query(None, max_length=200),
    sort: Optional[str] = _ORDEN,
    direction: Optional[str] = _DIRECCION,
    response: Response = None,
    pagina: Paginacion = Depends(paginacion),
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("gastos.responsables")),
):
    """Los totales son de todos los gastos filtrados, no solo de la pagina."""
    enforce_abac(db, current_user, "expense", action="read")
    datos = svc_team_expenses_page(
        db, current_user, status, project_id, user_id, date_from, date_to, pagina=pagina,
        category=category, texto=q, sort=sort, direction=direction,
    )
    exponer(response, datos["pagina"])
    return APIResponse.ok(data={
        "expenses": [_expense_out(e) for e in datos["pagina"].items],
        "total": round(datos["total"], 2),
        "billable_total": round(datos["billable_total"], 2),
        "by_category": {k: round(v, 2) for k, v in datos["by_category"].items()},
    })


@router.get("/summary/{project_id}", summary="Resumen de gastos por proyecto")
def project_expense_summary(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("gastos.responsables")),
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
    # Externos como internos (16-11-2026): presentar un gasto propio, tambien el
    # subcontratado (proyecto suyo, `acotar_gasto_del_externo`).
    _rol: User = Depends(requiere_capacidad("gastos.trabajar")),
):
    acotar_gasto_del_externo(db, payload, current_user)
    expense = svc_create_expense(db, payload, current_user.id, _next_code(db))
    return APIResponse.ok(data=_expense_out(expense))


@router.patch("/{expense_id}", summary="Editar gasto (admin/PM, cualquier estado)")
def update_expense_admin(
    expense_id: str,
    payload: ExpenseIn,
    db: Session = Depends(get_db),
    cu: User = Depends(requiere_capacidad("gastos.dirigir")),
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
    current_user: User = Depends(requiere_capacidad("gastos.responsables")),
):
    enforce_abac(db, current_user, "expense", expense_id, action="approve")
    return APIResponse.ok(data=svc_review_expense(expense_id, payload.approved, payload.rejection_reason, current_user, db))


@router.post("/{expense_id}/reimburse", summary="Marcar como reembolsado")
def reimburse_expense(
    expense_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("gastos.responsables")),
):
    enforce_abac(db, current_user, "expense", expense_id, action="approve")
    return APIResponse.ok(data=svc_reimburse_expense(db, expense_id, current_user))   # M88


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
    current_user: User = Depends(requiere_capacidad("gastos.responsables")),
):
    from app.api.descargas import respuesta_de_descarga
    return respuesta_de_descarga(export_expenses_excel(date_from, date_to, status, category, db, current_user))


# ── OCR receipt scanning (v24) ────────────────────────────────────────────────
@router.post("/ocr", summary="Escaner OCR de recibo con IA — extrae importe, comercio y fecha")
async def ocr_receipt(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(requiere_capacidad("gastos.usar")),  # auditoria 2026-09: excepcion revisada: escanear el recibo del gasto propio
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


# ── Revisión 2026-11: justificantes y reparto. Rev. 166 (#27): las políticas
# de gasto son del motor común (`/policies`, dominio `gastos`); aquí solo la
# vista previa del envío. La lógica vive en `gastos_avanzados.py` y
# `gastos_politicas.py`.

from pydantic import BaseModel, Field  # noqa: E402

from app.services import gastos_avanzados as gav  # noqa: E402
from app.services import gastos_politicas  # noqa: E402


class ParteIn(BaseModel):
    project_id: str = Field(min_length=1, max_length=36)
    percentage: float = Field(gt=0, le=100)


class TipoDeDocumentoIn(BaseModel):
    document_type: Optional[str] = Field(None, max_length=40)


@router.get("/{expense_id}/policy-preview",
            summary="Qué pasará al enviar el gasto: políticas, niveles, avisos y documentos (sin efectos)")
def policy_preview(expense_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("gastos.usar"))):
    return APIResponse.ok(data=gastos_politicas.previsualizar(db, current_user, expense_id))


@router.get("/{expense_id}/attachments", summary="Justificantes y documentos del gasto")
def list_attachments(expense_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("gastos.trabajar"))):
    # Externos como internos (16-11-2026): justificantes del gasto propio
    # (`gastos_avanzados._gasto`: el dueño o un gestor; si no, 404).
    return APIResponse.ok(data={"items": gav.adjuntos(db, current_user, expense_id)})


@router.post("/{expense_id}/attachments", summary="Adjuntar un justificante o documento (con su tipo de documento)")
async def add_attachment(expense_id: str, file: UploadFile = File(...),
                         document_type: Optional[str] = Form(None, max_length=40), db: Session = Depends(get_db),
                         current_user: User = Depends(requiere_capacidad("gastos.trabajar"))):
    # Externos como internos (16-11-2026): solo sobre el gasto propio en borrador (`_gasto(editar=True)`).
    contenido = await read_and_validate_upload(file, UploadProfile.RECEIPT)
    from app.core.async_db import run_db
    return APIResponse.ok(data=await run_db(gav.subir_adjunto, db, current_user, expense_id, contenido,
                                            file.filename or "justificante", file.content_type, document_type))


@router.patch("/attachments/{attachment_id}", summary="Cambiar el tipo de documento de un justificante")
def set_attachment_type(attachment_id: str, body: TipoDeDocumentoIn, db: Session = Depends(get_db),
                        current_user: User = Depends(requiere_capacidad("gastos.trabajar"))):
    # Externos como internos (16-11-2026): solo sobre el gasto propio en borrador.
    return APIResponse.ok(data=gav.tipar_adjunto(db, current_user, attachment_id, body.document_type))


@router.get("/attachments/{attachment_id}/url", summary="URL firmada y de corta vida para ver el justificante")
def attachment_url(attachment_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("gastos.trabajar"))):
    # Externos como internos (16-11-2026): solo de un gasto propio.
    return APIResponse.ok(data={"url": gav.url_de_adjunto(db, current_user, attachment_id)})


@router.delete("/attachments/{attachment_id}", summary="Quitar un justificante")
def delete_attachment(attachment_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("gastos.trabajar"))):
    # Externos como internos (16-11-2026): solo sobre el gasto propio en borrador.
    gav.borrar_adjunto(db, current_user, attachment_id)
    return APIResponse.ok(data={"ok": True})


@router.get("/{expense_id}/allocations", summary="Reparto del gasto entre proyectos")
def get_allocations(expense_id: str, db: Session = Depends(get_db), current_user: User = Depends(requiere_capacidad("gastos.usar"))):
    return APIResponse.ok(data={"items": gav.reparto(db, current_user, expense_id)})


@router.put("/{expense_id}/allocations", summary="Repartir el gasto entre proyectos (suma 100 %; vacío lo quita)")
def put_allocations(expense_id: str, body: list[ParteIn], db: Session = Depends(get_db),
                    current_user: User = Depends(requiere_capacidad("gastos.usar"))):
    return APIResponse.ok(data={"items": gav.repartir(db, current_user, expense_id, [p.model_dump() for p in body])})
