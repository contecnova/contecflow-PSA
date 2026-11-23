"""
expense_service.py — Lógica de negocio para gastos.

Funciones exportadas:
  review_expense(expense_id, approved, rejection_reason, current_user, db)
  export_expenses_excel(date_from, date_to, status, category, db) -> Descarga
  ocr_receipt(db, usuario, image_bytes, content_type) -> dict  (síncrona: el endpoint la pasa por run_db)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import case, func, false
from sqlalchemy.orm import Session

from app.services.settings_service import por_empresa as _pe
from app.models.user import User
from app.models.expenses import Expense, ExpenseStatus
from app.services.gastos_avanzados import CATEGORY_LABELS, del_proyecto, etiqueta_de_categoria
from app.models.project import Project
from app.models.project import ProjectStatus
from app.models.user import User as UserModel
from app.services.audit import audit_log
from app.core.errores import ErrorDeDominio
from app.core.paginacion import Pagina, Paginacion, paginar
from app.core.codigos_de_error import error
from app.core.config import settings  # topes de tokens de IA (19-11-2026)

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
from app.core.descargas import Descarga
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

logger = logging.getLogger(__name__)

# 23-11-2026: las etiquetas de categoria y estado salen de `textos_de_salida`
# (`gastos_avanzados.etiqueta_de_categoria`, `gastos.estado.*`), no de aqui.


def _tx_aprob(clave: str, db, usuario, **params) -> str:
    """Texto del historial de la bandeja de aprobaciones, en el idioma de quien actua."""
    from app.services.formato_regional import idioma_de_salida
    from app.services.textos_de_salida import texto
    return texto(clave, idioma_de_salida(db, user_id=getattr(usuario, "id", None)), **params)


# ── Review (approve / reject) ──────────────────────────────────────────────────

def review_expense(
    expense_id: str,
    approved: bool,
    rejection_reason: Optional[str],
    current_user: User,
    db: Session,
) -> dict:
    """Approve or reject a submitted expense. Sends notification and writes audit log."""

    # M88 (auditoría 22-11-2026): la fila se bloquea (dos revisores a la vez no
    # deciden dos veces) y nadie aprueba su propio gasto (segregación de funciones).
    q = db.query(Expense).filter(Expense.id == expense_id)
    from app.db.session import is_postgres
    if is_postgres():
        q = q.with_for_update()
    expense = q.first()
    if not expense:
        raise ErrorDeDominio(404)
    if expense.status != ExpenseStatus.submitted:
        raise error(400, "gasto_no_pendiente")
    from app.services.approval_engine._base import exigir_que_no_sea_suyo
    exigir_que_no_sea_suyo(db, expense.user_id, current_user, "expense", expense.id)
    # Rev. 166 (#27): los niveles que pidió una política se deciden en la bandeja
    # de aprobaciones; revisar aquí los saltaría.
    from app.services.gastos_politicas import pendiente_con_pasos_de_politica
    if pendiente_con_pasos_de_politica(db, expense.id):
        raise error(409, "gasto_requiere_aprobacion_politica")

    avisos: list[str] = []
    if approved:   # control presupuestario: avisa, o 409 si BUDGET_CONTROL_POLICY = bloquear
        from app.services.presupuestos_seguir import control_de_gasto
        avisos = control_de_gasto(db, expense)

    expense.reviewed_by = current_user.id
    expense.reviewed_at = datetime.now(timezone.utc)

    if approved:
        expense.status = ExpenseStatus.approved
        expense.rejection_reason = None
        from app.services.formato_regional import idioma_de_salida as _ids
        from app.services.textos_de_salida import texto as _tx
        _id = _ids(db, user_id=expense.user_id)
        notify_user(
            db, expense.user_id, "expense_approved",
            _tx("gasto.aprobado.titulo", _id, descripcion=expense.description[:50]),
            _tx("gasto.aprobado.mensaje", _id, nombre=current_user.full_name,
                importe=expense.amount, moneda=expense.currency),
            resource="expenses", resource_id=expense.id, action_url="/expenses",
        )
    else:
        expense.status = ExpenseStatus.rejected
        expense.rejection_reason = rejection_reason
        from app.services.formato_regional import idioma_de_salida as _ids
        from app.services.textos_de_salida import texto as _tx
        _id = _ids(db, user_id=expense.user_id)
        notify_user(
            db, expense.user_id, "expense_rejected",
            _tx("gasto.rechazado.titulo", _id, descripcion=expense.description[:50]),
            _tx("gasto.rechazado.mensaje", _id,
                motivo=rejection_reason or _tx("gasto.rechazado.sin_motivo", _id)),
            resource="expenses", resource_id=expense.id, action_url="/expenses",
        )

    from app.services.approval_engine import fuentes
    fuentes.cerrar(db, "expense", expense.id, "approved" if approved else "rejected",
                   _tx_aprob("gasto.decidido", db, current_user, nombre=current_user.full_name))
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
    current_user=None,
):
    """
    El Excel de los gastos filtrados, como `Descarga` (el endpoint la sirve).

    Auditoría 22-11-2026 (A40): el filtro de categoría estaba dentro del
    `if status:` (sin estado se ignoraba; con estado y sin categoría filtraba
    `category IS NULL` y salía vacío). Y (A25) se acota con el mismo criterio
    que la lista del equipo (`query_team_expenses`): la empresa de quien
    exporta, no solo el filtro de sesión.
    """
    import io

    if current_user is not None:
        q = query_team_expenses(db, current_user, status=status, date_from=date_from, date_to=date_to)
    else:
        q = db.query(Expense).filter(Expense.is_active == True)  # audit #36 soft-delete
        if date_from:
            q = q.filter(Expense.expense_date >= date_from)
        if date_to:
            q = q.filter(Expense.expense_date <= date_to)
        if status:
            q = q.filter(Expense.status == _normalize_status(status))
    if category:
        q = q.filter(Expense.category == category)
    expenses = q.order_by(None).order_by(Expense.expense_date.desc()).all()

    # Auditoría 22-11-2026 (hardcode): cabeceras, estados y «Sí/No» en el idioma
    # de quien exporta (antes, castellano fijo); `textos_de_salida` por clave.
    from app.services.formato_regional import idioma_de_salida
    from app.services.textos_de_salida import texto as _tx
    idioma = idioma_de_salida(db, user_id=getattr(current_user, "id", None),
                              org_id=getattr(current_user, "organization_id", None))

    wb = Workbook()
    ws = wb.active
    ws.title = _tx("gastos.excel.hoja", idioma)

    headers = [_tx(f"gastos.excel.{k}", idioma) for k in (
        "fecha", "empleado", "categoria", "descripcion", "importe",
        "moneda", "proyecto", "estado", "facturable", "notas", "justificante")]
    header_fill = PatternFill("solid", fgColor="0D1B3E")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    # 19-11-2026: etiquetas del catálogo de la empresa (incluye sus categorías propias).
    from app.services.settings_service import catalogos_de_clave as _cat
    _etiquetas_cat = {c.value: c.label for c in _cat.listar(db, "expense_categories")}
    for row, e in enumerate(expenses, 2):
        row_data = [
            str(e.expense_date) if e.expense_date else "",
            e.user.full_name if e.user else "",
            _etiquetas_cat.get(e.category, etiqueta_de_categoria(e.category, idioma)),
            e.description or "",
            e.amount or 0,
            e.currency or _pe.moneda_de_empresa(db, registro=e),
            e.project.name if hasattr(e, "project") and e.project else "",
            _tx(f"gastos.estado.{getattr(e.status, 'value', e.status)}", idioma),
            _tx("gastos.excel.si" if e.is_billable else "gastos.excel.no", idioma),
            e.notes or "",
            e.receipt_url or "",
        ]
        # 22-11-2026 (02 A39): descripción, notas o proyecto con `=...` eran
        # fórmulas al abrir el Excel; se neutralizan (comilla delante).
        from app.core.celdas_seguras import neutralizar_formula
        for col, val in enumerate(row_data, 1):
            ws.cell(row=row, column=col, value=neutralizar_formula(val))

    for col, w in enumerate([12, 20, 14, 35, 10, 8, 20, 12, 10, 25, 35], 1):
        ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = w

    buf = io.BytesIO()
    wb.save(buf)

    filename = f"gastos_{date_from or 'todos'}_{date_to or 'hoy'}.xlsx"
    return Descarga(
        contenido=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        cabeceras={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── OCR receipt ────────────────────────────────────────────────────────────────

def ocr_receipt(db: Session, usuario, image_bytes: bytes, content_type: str) -> dict:
    """Lee un recibo (imagen o PDF) con el proveedor de IA de la empresa.

    Revisión 2026-11: iba directo a Anthropic con `ANTHROPIC_API_KEY`; con otro
    proveedor no había OCR, y se saltaba la gobernanza y el tope de gasto.
    Ahora pasa por `call_ai` con el recibo como adjunto, y las categorías salen
    del catálogo de la empresa (`custom_expense_categories`, 19-11-2026), no de
    una lista escrita en el texto.
    """
    import base64
    import json as _json
    from app.services.ai_provider_service import call_ai, es_aviso_de_ia
    from app.services.settings_service import catalogos_de_clave as _cat

    claves_cat = [c.value for c in _cat.listar(db, "expense_categories")]
    categorias = "|".join(claves_cat)
    # 18-11-2026: la descripción en el idioma del usuario (antes, castellano fijo).
    from app.services.formato_regional import idioma_de_salida, nombre_del_idioma
    _nombre_idioma = nombre_del_idioma(idioma_de_salida(
        db, user_id=getattr(usuario, "id", None), org_id=getattr(usuario, "organization_id", None)))
    sistema = (
        "Eres un asistente experto en contabilidad. Analiza la imagen de un recibo o factura y extrae "
        "los datos estructurados. Responde SOLO con un JSON válido sin markdown, con las claves: "
        "amount (número), currency (ISO 4217 de 3 letras), merchant (nombre del comercio o emisor), "
        f"date (YYYY-MM-DD), category (una de: {categorias}), "
        f"description (descripción breve en {_nombre_idioma} de máximo 80 caracteres). "
        "Si no puedes leer un campo devuelve null para ese campo."
    )
    mensaje = {"role": "user", "content": "Por favor extrae los datos de este recibo.",
               "adjuntos": [{"media": content_type, "datos": base64.b64encode(image_bytes).decode()}]}
    texto = call_ai(
        db, [mensaje], system=sistema, module="expenses_ocr", user_id=getattr(usuario, "id", None),
        max_tokens=settings.AI_BRIEF_ANSWER_MAX_TOKENS, is_superadmin=bool(getattr(usuario, "is_superadmin", False)),
        organization_id=getattr(usuario, "organization_id", None))
    if es_aviso_de_ia(texto):
        raise error(503, "ia_no_disponible", detail=texto)
    crudo = texto.strip()
    if crudo.startswith("```"):
        crudo = crudo.split("```")[1].removeprefix("json").strip()
    try:
        extraido = _json.loads(crudo)
    except _json.JSONDecodeError:
        raise error(422, "ia_formato_inesperado")
    if extraido.get("date"):
        try:
            _dt.strptime(extraido["date"], "%Y-%m-%d")
        except ValueError:
            extraido["date"] = None
    categoria = extraido.get("category")
    return {
        "amount": extraido.get("amount"),
        "currency": extraido.get("currency") or _pe.moneda_de_empresa(db, registro=usuario),
        "merchant": extraido.get("merchant"),
        "date": extraido.get("date"),
        "category": categoria if categoria in claves_cat else ("other" if "other" in claves_cat else None),
        "description": extraido.get("description") or "",
    }


# ── List / query helpers ───────────────────────────────────────────────────────
# Rev. 166 (fase 2): las tres listas (mías, pendientes, equipo) se paginan en el
# servidor, así que buscar, filtrar por categoría y ordenar también se hacen
# aquí: hacerlo en el navegador solo miraría la página cargada.

#: Columnas por las que la pantalla puede ordenar (lista cerrada).
ORDEN_DE_GASTOS = {"code": Expense.code, "category": Expense.category, "description": Expense.description,
                   "amount": Expense.amount, "status": Expense.status, "expense_date": Expense.expense_date,
                   "submitted_at": Expense.submitted_at}


def filtrar_lista(q, *, category: Optional[str] = None, texto: Optional[str] = None,
                  con_solicitante: bool = False):
    """Categoría exacta y texto en código o descripción (y nombre de quien lo pide)."""
    if category:
        q = q.filter(Expense.category == category)
    if texto and texto.strip():
        patron = f"%{texto.strip()}%"
        opciones = [Expense.code.ilike(patron), Expense.description.ilike(patron)]
        if con_solicitante:
            opciones.append(Expense.user.has(UserModel.full_name.ilike(patron)))
        q = q.filter(or_(*opciones))
    return q


def ordenar_lista(q, sort: Optional[str], direction: Optional[str], *defecto):
    """Orden pedido (si es una columna conocida) o el de siempre; siempre desempata por id."""
    columna = ORDEN_DE_GASTOS.get(sort or "")
    if columna is None:
        return q.order_by(*defecto, Expense.id)
    return q.order_by(columna.desc() if direction == "desc" else columna.asc(), Expense.id)


def query_my_expenses(db: Session, user_id: str, status=None, project_id=None, date_from=None, date_to=None,
                      category=None, texto=None):
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
    return filtrar_lista(q, category=category, texto=texto)


def list_my_expenses(
    db: Session,
    user_id: str,
    status: Optional[str] = None,
    project_id: Optional[str] = None,
    date_from=None,
    date_to=None,
    pagina: Optional[Paginacion] = None,
    category: Optional[str] = None,
    texto: Optional[str] = None,
    sort: Optional[str] = None,
    direction: Optional[str] = None,
) -> Pagina:
    q = query_my_expenses(db, user_id, status, project_id, date_from, date_to, category, texto)
    q = ordenar_lista(q, sort, direction, Expense.expense_date.desc())
    return paginar(q, pagina, "expenses.my")


def query_pending_expenses(db: Session, project_id=None, category=None, texto=None, date_from=None, date_to=None):
    q = db.query(Expense).options(
        joinedload(Expense.user), joinedload(Expense.project)
    ).filter(
        Expense.status == ExpenseStatus.submitted,
        Expense.is_active == True,  # audit #36 soft-delete
    )
    if project_id:
        q = q.filter(del_proyecto(project_id))
    if date_from:   q = q.filter(Expense.expense_date >= date_from)
    if date_to:     q = q.filter(Expense.expense_date <= date_to)
    return filtrar_lista(q, category=category, texto=texto, con_solicitante=True)


def list_pending_expenses(db: Session, project_id: Optional[str] = None,
                          pagina: Optional[Paginacion] = None, category: Optional[str] = None,
                          texto: Optional[str] = None, date_from=None, date_to=None,
                          sort: Optional[str] = None, direction: Optional[str] = None) -> Pagina:
    q = query_pending_expenses(db, project_id, category, texto, date_from, date_to)
    q = ordenar_lista(q, sort, direction, Expense.submitted_at)
    return paginar(q, pagina, "expenses.pending")


def totales_de_lista(q) -> dict:
    """Cuántos gastos, su suma y cuántos están enviados, sobre TODOS los filtrados (no la página)."""
    sub = q.order_by(None).with_entities(Expense.id, Expense.amount, Expense.status).subquery()
    n, total, enviados = q.session.query(
        func.count(sub.c.id), func.coalesce(func.sum(sub.c.amount), 0),
        func.coalesce(func.sum(case((sub.c.status == ExpenseStatus.submitted, 1), else_=0)), 0)).one()
    return {"count": int(n), "total_amount": round(float(total), 2), "submitted_count": int(enviados)}


def list_all_expenses(
    db: Session,
    current_user,
    status: Optional[str] = None,
    user_id: Optional[str] = None,
):

    q = db.query(Expense).filter(Expense.is_active == True)  # audit #36 soft-delete
    # 18-11-2026: quién ve los gastos de todos es el mismo criterio que en la ficha y
    # los justificantes (`gastos_avanzados.es_gestor`: ajuste por empresa
    # `EXPENSE_MANAGER_ROLES`). Antes aquí era admin/pm/hr fijo: RR. HH. veía la
    # lista de todos pero no podía abrir ninguno.
    from app.services.gastos_avanzados import es_gestor
    if not (getattr(current_user, "is_superadmin", False) or es_gestor(db, current_user)):
        q = q.filter(Expense.user_id == current_user.id)
    elif not current_user.is_superadmin and not current_user.organization_id:
        # A25: un gestor sin empresa no ve los gastos de todas (antes, sin filtro).
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


def query_team_expenses(
    db: Session,
    current_user,
    status=None,
    project_id=None,
    user_id=None,
    date_from=None,
    date_to=None,
):
    """Consulta de los gastos del equipo, filtrada y ordenada, sin ejecutar."""

    q = db.query(Expense).options(
        joinedload(Expense.user), joinedload(Expense.project), joinedload(Expense.reviewer)
    ).filter(Expense.is_active == True)  # audit #36 soft-delete
    if not current_user.is_superadmin and not current_user.organization_id:
        # A25: sin empresa, ninguna fila (antes, las de todas las empresas).
        q = q.filter(false())
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
    if status:      q = q.filter(Expense.status == _normalize_status(status))
    if project_id:  q = q.filter(del_proyecto(project_id))
    if user_id:     q = q.filter(Expense.user_id == user_id)
    if date_from:   q = q.filter(Expense.expense_date >= date_from)
    if date_to:     q = q.filter(Expense.expense_date <= date_to)
    return q.order_by(Expense.expense_date.desc(), Expense.id)


def team_expenses_page(db: Session, current_user, status=None, project_id=None, user_id=None,
                       date_from=None, date_to=None, pagina: Optional[Paginacion] = None,
                       category: Optional[str] = None, texto: Optional[str] = None,
                       sort: Optional[str] = None, direction: Optional[str] = None) -> dict:
    """Pagina de gastos del equipo y sus totales, calculados sobre TODOS los filtrados.

    Segunda auditoria 2026-11: los totales se sumaban en Python sobre la lista
    entera; ahora salen de un agregado SQL, asi que paginar la lista no los
    cambia.
    """
    q = query_team_expenses(db, current_user, status, project_id, user_id, date_from, date_to)
    q = filtrar_lista(q, category=category, texto=texto, con_solicitante=True)
    q = ordenar_lista(q.order_by(None), sort, direction, Expense.expense_date.desc())
    filtrados = q.order_by(None).with_entities(
        Expense.id, Expense.amount, Expense.is_billable, Expense.category).subquery()
    total, facturable = db.query(
        func.coalesce(func.sum(filtrados.c.amount), 0),
        func.coalesce(func.sum(case((filtrados.c.is_billable == True, filtrados.c.amount), else_=0)), 0),  # noqa: E712
    ).one()
    por_categoria = dict(db.query(filtrados.c.category, func.sum(filtrados.c.amount))
                         .group_by(filtrados.c.category).all())
    return {
        "pagina": paginar(q, pagina, "expenses.team"),
        "total": float(total),
        "billable_total": float(facturable),
        "by_category": por_categoria,
    }


# ── Create / update / delete ───────────────────────────────────────────────────

def create_expense_record(db: Session, payload, user_id: str, code: str):

    if payload.project_id:
        project = db.query(Project).filter(Project.id == payload.project_id).first()
        if not project:
            raise error(404, "no_encontrado", detail="Proyecto no encontrado", que="proyecto")
        if project.status in [
            ProjectStatus.completed, ProjectStatus.closed,
            ProjectStatus.cancelled, ProjectStatus.archived,
        ]:
            raise error(400, "gasto_facturable_proyecto_cerrado")

    expense = Expense(code=code, user_id=user_id, **payload.model_dump())
    from app.services.gastos_avanzados import aplicar_kilometraje
    aplicar_kilometraje(db, expense)

    if expense.is_billable and expense.project_id:
        project = db.query(Project).filter(Project.id == expense.project_id).first()
        if project and project.status not in [ProjectStatus.active, ProjectStatus.planning]:
            raise error(400, "gasto_facturable_proyecto_inactivo")

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
        raise error(404, "no_encontrado", detail="Gasto no encontrado", que="gasto")

    if payload.is_billable and e.project_id:
        project = db.query(Project).filter(Project.id == e.project_id).first()
        if project and project.status not in [ProjectStatus.active, ProjectStatus.planning]:
            raise error(400, "gasto_facturable_proyecto_inactivo")

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
        raise error(404, "no_encontrado", detail="Gasto no encontrado", que="gasto")
    if expense.status not in (ExpenseStatus.draft, ExpenseStatus.rejected):
        raise error(400, "gasto_no_editable")
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
        raise error(400, "gasto_ya_enviado")
    # Rev. 166 (#27): el motor de políticas decide aquí (ver gastos_politicas):
    # 422 solo si una política BLOQUEA o falta un requisito; un exceso pide
    # más aprobación o avisa, y eso entra en la solicitud de aprobación.
    from app.services import gastos_politicas
    ev = gastos_politicas.al_enviar(db, expense, user_id)
    expense.status = ExpenseStatus.submitted
    expense.submitted_at = datetime.now(timezone.utc)
    expense.rejection_reason = None
    # M106: envío + evaluación + solicitud de aprobación en una sola transacción
    # (`tras_enviar` confirma); el evento sale después.
    gastos_politicas.tras_enviar(db, expense, ev, user_id)
    from app.core.events import emit, EventType
    emit(db, EventType.EXPENSE_SUBMITTED,
         {"amount": expense.amount, "category": expense.category, "project_id": expense.project_id},
         resource_type="expense", resource_id=expense_id, project_id=expense.project_id)
    return {"ok": True, "decision": ev["decision"]}


def recall_expense_record(db: Session, expense_id: str, user_id: str) -> dict:

    expense = db.query(Expense).filter(
        Expense.id == expense_id, Expense.user_id == user_id
    ).first()
    if not expense:
        raise ErrorDeDominio(404)
    if expense.status != ExpenseStatus.submitted:
        raise error(400, "gasto_solo_enviado_retirable")
    expense.status = ExpenseStatus.draft
    expense.submitted_at = None
    from app.services.approval_engine import fuentes
    fuentes.cerrar(db, "expense", expense.id, "cancelled", _tx_aprob("gasto.retirado", db, current_user))
    db.commit()
    return {"ok": True}


def reimburse_expense_record(db: Session, expense_id: str, current_user: Optional[User] = None) -> dict:
    # M88 (auditoría 22-11-2026): bloqueo de fila (no se reembolsa dos veces),
    # nadie se reembolsa su propio gasto y el reembolso queda en `audit_log`.
    q = db.query(Expense).filter(Expense.id == expense_id)
    from app.db.session import is_postgres
    if is_postgres():
        q = q.with_for_update()
    expense = q.first()
    if not expense:
        raise ErrorDeDominio(404)
    if expense.status != ExpenseStatus.approved:
        raise error(400, "gasto_no_aprobado")
    if current_user is not None:
        from app.services.approval_engine._base import exigir_que_no_sea_suyo
        exigir_que_no_sea_suyo(db, expense.user_id, current_user, "expense", expense.id)
    expense.status = ExpenseStatus.reimbursed
    expense.reimbursed_at = datetime.now(timezone.utc)
    audit_log(db, current_user, "REIMBURSE", "expenses", expense.id, expense.code,
              old_values={"status": "approved"}, new_values={"status": "reimbursed", "amount": expense.amount,
                                                             "currency": expense.currency})
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
        raise error(400, "gasto_no_eliminable")
    # audit #36 soft-delete — preserva el histórico para auditoría financiera.
    expense.is_active = False
    db.commit()
    return {"ok": True, "message": "Gasto eliminado correctamente"}


# ── Label constants + serialization helpers ────────────────────────────────
# CATEGORY_LABELS vive en gastos_avanzados (importado arriba): rompe el ciclo.


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
        "country": e.country,
        "city": e.city,
        "attendees": e.attendees,
        "trip": e.trip,
        "policy_flags": _avisos(e),
        "policy_summary": _resumen_politica(e),
        "created_at": str(e.created_at)[:10] if e.created_at else None,
    }


def _avisos(e) -> list:
    from app.services.gastos_politicas import avisos_guardados
    return avisos_guardados(e)


def _resumen_politica(e):
    from app.services.gastos_politicas import resumen_guardado
    return resumen_guardado(e)


def acotar_gasto_del_externo(db: Session, payload, user: User) -> None:
    """Externos como internos (16-11-2026): el subcontratado presenta su gasto
    (el servicio lo crea a su nombre, `user_id=current_user.id`), pero el
    proyecto ha de ser uno de los suyos (`scope_projects_query`; 404 si no) y
    sin contrato: los contratos son datos comerciales de la empresa."""
    from app.services.politica_de_visibilidad import es_externo
    if not es_externo(user):
        return
    from app.core.errores import ErrorDeDominio
    from app.models.project import Project
    from app.services.project_service import scope_projects_query
    if payload.contract_id:
        raise error(403, "contratos_no_disponibles_rol")
    if payload.project_id and not scope_projects_query(db.query(Project.id), db, user).filter(
            Project.id == payload.project_id).first():
        raise error(404, "no_encontrado", detail="Proyecto no encontrado", que="proyecto")
