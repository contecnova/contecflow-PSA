"""Gastos: justificantes, reparto entre proyectos, políticas y kilometraje (revisión 2026-11).

- **Justificantes y documentos**: varios por gasto, en el almacén de ficheros
  (local o S3, `file_storage`); se descargan con una URL firmada de corta vida.
- **Reparto**: un gasto se puede repartir entre proyectos por porcentaje
  (suman 100). Con reparto, lo que cuenta para cada proyecto es su parte; sin
  él, el gasto entero va a su `project_id`.
- **Tipo de documento** de cada justificante (rev. 166): uno de
  `POLICY_DOCUMENT_TYPES`, para que una política pida, p. ej., la factura.
- **Kilometraje**: con `km`, el importe lo calcula el servidor con la tarifa
  por km del país (y ciudad) del gasto —la tabla de referencia de gastos con
  uso «kilometraje», en Políticas y reglas— o, sin fila, con
  `EXPENSE_MILEAGE_RATE`.

Las políticas de gasto viven en el motor común (`app/services/politicas`,
dominio `gastos`); el envío las aplica en `gastos_politicas.py` (rev. 166).
"""
from __future__ import annotations

from sqlalchemy import select

import logging
from typing import Optional

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.expenses import Expense, ExpenseAllocation, ExpenseAttachment, ExpenseStatus
from app.core.errores import ErrorDeDominio
from app.core.codigos_de_error import error

_CATEGORIAS_DE_SERIE = ("travel", "accommodation", "meals", "software", "hardware", "training",
                        "marketing", "office", "subcontract", "other")


def etiqueta_de_categoria(categoria, idioma=None) -> str:
    """Nombre de la categoria de serie en `idioma` (23-11-2026: unica fuente; antes habia
    dos diccionarios en castellano, aqui y en `expense_service`)."""
    from app.services.textos_de_salida import texto
    return texto(f"gasto.categoria.{categoria}", idioma) if categoria in _CATEGORIAS_DE_SERIE else (categoria or "")


#: Por compatibilidad: etiquetas en el idioma de respaldo (castellano).
CATEGORY_LABELS = {c: etiqueta_de_categoria(c) for c in _CATEGORIAS_DE_SERIE}


def _aj(db: Session, clave: str, org, tipo: str = "float"):
    from app.services import settings_service as s
    return {"float": s.get_runtime_float, "int": s.get_runtime_int, "str": s.get_runtime_str}[tipo](db, clave, org)


def es_gestor(db: Session, usuario) -> bool:
    roles = {r.strip() for r in str(_aj(db, "EXPENSE_MANAGER_ROLES", usuario.organization_id, "str") or "").split(",")}
    return str(getattr(usuario.role, "value", usuario.role)) in roles


def _gasto(db: Session, usuario, expense_id: str, *, editar: bool = False) -> Expense:
    """El gasto, si es de quien llama o quien llama lo gestiona. Para cambiarlo, el dueño sólo en borrador."""
    e = db.query(Expense).filter(Expense.id == expense_id).first()
    if e is None:
        raise error(404, "no_encontrado", detail="Gasto no encontrado", que="gasto")
    gestor = es_gestor(db, usuario)
    if e.user_id != usuario.id and not gestor:
        raise error(404, "no_encontrado", detail="Gasto no encontrado", que="gasto")
    if editar and not gestor and e.status != ExpenseStatus.draft:
        raise error(409, "solo_estado_borrador", detail="Sólo se cambia un gasto en borrador")
    return e


# ── Kilometraje ───────────────────────────────────────────────────────────────

def aplicar_kilometraje(db: Session, expense: Expense) -> None:
    """Importe = km × tarifa. La tarifa: la de la tabla «kilometraje» para el
    país/ciudad y fecha del gasto (convertida a la moneda del gasto al tipo de
    su fecha); sin tabla o sin fila, `EXPENSE_MILEAGE_RATE`."""
    if expense.km is None:
        return
    if expense.km <= 0:
        raise error(400, "kilometros_positivos")
    from app.services.politicas.dominios.gastos import tarifa_por_km
    fila = tarifa_por_km(db, expense) if expense.expense_date else None
    if fila is None:
        tarifa = float(_aj(db, "EXPENSE_MILEAGE_RATE", expense.organization_id))
    else:
        tarifa = fila["cantidad"]
        desde, hacia = (fila["moneda"] or "").upper(), (expense.currency or "").upper()
        if desde and hacia and desde != hacia:
            from app.services.politicas.dominios.gastos import _tipo
            tipo = _tipo(db, desde, hacia, expense.expense_date, {})
            if tipo is None:
                raise error(422, "tarifa_km_sin_tipo_de_cambio", nombre=fila['tabla'], moneda=desde, desde=desde, hasta=hacia, fecha=expense.expense_date.isoformat())
            tarifa *= tipo
    expense.amount = float(_cent(Decimal(str(expense.km)) * Decimal(str(tarifa))))   # M3: céntimo exacto


# ── Justificantes ─────────────────────────────────────────────────────────────

#: A33 (auditoría 22-11-2026): estados en los que un justificante ya es soporte
#: de un gasto aprobado o pagado: nadie (tampoco el gestor) lo sube, cambia ni
#: borra. Es el estándar de las herramientas de gastos (el justificante de un
#: gasto aprobado es documento contable y fiscal con plazo legal de
#: conservación); para corregirlo se rechaza o se anula el gasto. Además, el
#: bloqueo legal general (`app/db/bloqueo_legal.py`, tipo `expense_attachments`)
#: impide borrarlo mientras haya un bloqueo activo.
ESTADOS_CON_JUSTIFICANTE_FIRME = (ExpenseStatus.approved, ExpenseStatus.reimbursed)


def _justificantes_editables(e: Expense) -> None:
    if e.status in ESTADOS_CON_JUSTIFICANTE_FIRME:
        raise error(409, "justificante_de_gasto_aprobado")

def _adjunto_dict(a: ExpenseAttachment) -> dict:
    return {"id": a.id, "filename": a.filename, "content_type": a.content_type, "size_bytes": a.size_bytes,
            "document_type": a.document_type, "created_at": a.created_at.isoformat() if a.created_at else None}


def _tipo_de_documento(db: Session, org, tipo: Optional[str]) -> Optional[str]:
    """Vacío o uno de los tipos configurados (`POLICY_DOCUMENT_TYPES`)."""
    if not tipo:
        return None
    from app.services.politicas.servicio import tipos_de_documento
    if tipo not in tipos_de_documento(db, org):
        raise error(422, "tipo_de_documento_no_configurado", tipo=tipo)
    return tipo


def adjuntos(db: Session, usuario, expense_id: str) -> list[dict]:
    _gasto(db, usuario, expense_id)
    return [_adjunto_dict(a) for a in db.query(ExpenseAttachment).filter(ExpenseAttachment.expense_id == expense_id)
            .order_by(ExpenseAttachment.created_at).all()]


def subir_adjunto(db: Session, usuario, expense_id: str, contenido: bytes, nombre: str, tipo: Optional[str],
                  tipo_de_documento: Optional[str] = None) -> dict:
    from app.services.audit import audit_log
    from app.services.s3_service import file_storage
    e = _gasto(db, usuario, expense_id, editar=True)
    _justificantes_editables(e)
    tipo_de_documento = _tipo_de_documento(db, e.organization_id, tipo_de_documento)
    maximo = int(_aj(db, "EXPENSE_ATTACHMENT_MAX_MB", e.organization_id, "int")) * 1024 * 1024
    if not contenido:
        raise error(400, "fichero_vacio")
    if len(contenido) > maximo:
        raise error(413, "fichero_demasiado_grande", detail=f"El fichero pasa del máximo ({maximo // (1024 * 1024)} MB)", max=maximo // (1024 * 1024))
    clave, tamano = file_storage.upload_file(contenido, nombre, f"expense-{e.id}", 1, tipo or "application/octet-stream")
    a = ExpenseAttachment(organization_id=e.organization_id, expense_id=e.id, filename=nombre[:255],
                          content_type=tipo, size_bytes=tamano, storage_key=clave, uploaded_by=usuario.id,
                          document_type=tipo_de_documento)
    db.add(a)
    if not e.receipt_name:      # el primero hace de justificante principal en las listas
        e.receipt_name = nombre[:255]
    audit_log(db, usuario, "CREATE", "expense_attachments", e.id, e.code,
              new_values={"fichero": nombre, "tipo_de_documento": tipo_de_documento})
    db.commit()
    return _adjunto_dict(a)


def tipar_adjunto(db: Session, usuario, attachment_id: str, tipo_de_documento: Optional[str]) -> dict:
    """Cambia el tipo de documento de un justificante (mientras el gasto se puede editar)."""
    from app.services.audit import audit_log
    a = db.query(ExpenseAttachment).filter(ExpenseAttachment.id == attachment_id).first()
    if a is None:
        raise error(404, "no_encontrado", detail="Justificante no encontrado", que="justificante")
    e = _gasto(db, usuario, a.expense_id, editar=True)
    _justificantes_editables(e)
    antes = a.document_type
    a.document_type = _tipo_de_documento(db, e.organization_id, tipo_de_documento)
    audit_log(db, usuario, "UPDATE", "expense_attachments", e.id, e.code,
              old_values={"tipo_de_documento": antes}, new_values={"tipo_de_documento": a.document_type})
    db.commit()
    return _adjunto_dict(a)


def url_de_adjunto(db: Session, usuario, attachment_id: str) -> str:
    from app.services.s3_service import file_storage
    a = db.query(ExpenseAttachment).filter(ExpenseAttachment.id == attachment_id).first()
    if a is None:
        raise error(404, "no_encontrado", detail="Justificante no encontrado", que="justificante")
    _gasto(db, usuario, a.expense_id)
    return file_storage.generate_presigned_url(a.storage_key)


def borrar_adjunto(db: Session, usuario, attachment_id: str) -> None:
    from app.services.audit import audit_log
    from app.services.s3_service import file_storage
    a = db.query(ExpenseAttachment).filter(ExpenseAttachment.id == attachment_id).first()
    if a is None:
        raise error(404, "no_encontrado", detail="Justificante no encontrado", que="justificante")
    e = _gasto(db, usuario, a.expense_id, editar=True)
    _justificantes_editables(e)
    audit_log(db, usuario, "DELETE", "expense_attachments", e.id, e.code, old_values={"fichero": a.filename})
    db.delete(a)
    db.flush()
    if e.receipt_name == a.filename:
        resto = db.query(ExpenseAttachment).filter(ExpenseAttachment.expense_id == e.id).first()
        e.receipt_name = resto.filename if resto else None
    db.commit()
    try:
        file_storage.delete_file(a.storage_key)
    except Exception:   # el registro ya no está; un fichero huérfano no rompe nada
        logging.getLogger(__name__).warning("gastos: no se pudo borrar %s", a.storage_key, exc_info=True)


# ── Reparto entre proyectos ───────────────────────────────────────────────────

def reparto(db: Session, usuario, expense_id: str) -> list[dict]:
    _gasto(db, usuario, expense_id)
    return [{"project_id": r.project_id, "project_name": r.project.name if r.project else None,
             "percentage": r.percentage}
            for r in db.query(ExpenseAllocation).filter(ExpenseAllocation.expense_id == expense_id).all()]


def repartir(db: Session, usuario, expense_id: str, partes: list[dict]) -> list[dict]:
    from app.models.project import Project
    from app.services.audit import audit_log
    e = _gasto(db, usuario, expense_id, editar=True)
    if partes:
        ids = [p["project_id"] for p in partes]
        if len(set(ids)) != len(ids):
            raise error(400, "reparto_proyecto_repetido")
        if any(float(p["percentage"]) <= 0 for p in partes):
            raise error(400, "reparto_parte_cero")
        total = sum(Decimal(str(p["percentage"])) for p in partes)
        # M3: exactamente 100 % a dos decimales (antes pasaba el 99,99 %).
        if total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) != Decimal("100.00"):
            raise error(400, "reparto_no_suma_100", suma=round(total, 2))
        existentes = {pid for (pid,) in db.query(Project.id).filter(Project.id.in_(ids)).all()}
        if set(ids) - existentes:
            raise error(404, "no_encontrado", detail="Proyecto no encontrado", que="proyecto")
    db.query(ExpenseAllocation).filter(ExpenseAllocation.expense_id == e.id).delete(synchronize_session=False)
    for p in partes:
        db.add(ExpenseAllocation(organization_id=e.organization_id, expense_id=e.id, project_id=p["project_id"],
                                 percentage=round(float(p["percentage"]), 4)))
    audit_log(db, usuario, "UPDATE", "expenses", e.id, e.code, new_values={"reparto": partes})
    db.commit()
    return reparto(db, usuario, expense_id)


def _cent(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _partes_cuadradas(importe, pcts: dict) -> dict:
    """M3 (auditoría 22-11-2026): el reparto en céntimos y CUADRADO: el resto del
    redondeo va a la parte mayor, así que la suma de las partes es el gasto
    (antes cada parte se redondeaba por su lado y sobraban o faltaban céntimos)."""
    total = _cent(importe)
    partes = {pid: _cent(total * Decimal(str(pct)) / 100) for pid, pct in pcts.items() if pct}
    if partes and abs(sum(Decimal(str(x)) for x in pcts.values()) - 100) < Decimal("0.01"):
        mayor = max(partes, key=lambda k: (partes[k], k))
        partes[mayor] += total - sum(partes.values())
    return {k: float(v) for k, v in partes.items()}


def importe_por_proyecto(db: Session, gastos: list[Expense], project_id: str) -> list[tuple[Expense, float]]:
    """(gasto, parte del proyecto). Con reparto cuenta la parte; sin reparto, el gasto entero si es suyo."""
    return [(g, imp) for _, g, imp in importe_por_proyectos(db, gastos, [project_id])]


def importe_por_proyectos(db: Session, gastos: list[Expense], project_ids) -> list[tuple[str, Expense, float]]:
    """`importe_por_proyecto` para varios proyectos con UNA consulta de repartos
    (auditoría 22-11-2026, M3: antes una por proyecto): ``[(project_id, gasto, parte)]``."""
    if not gastos:
        return []
    ids = set(project_ids)
    partes: dict[str, dict[str, float]] = {}
    for r in db.query(ExpenseAllocation).filter(ExpenseAllocation.expense_id.in_([g.id for g in gastos])).all():
        partes.setdefault(r.expense_id, {})[r.project_id] = r.percentage
    salida = []
    for g in gastos:
        if g.id in partes:
            for pid, imp in _partes_cuadradas(g.amount, partes[g.id]).items():
                if pid in ids:
                    salida.append((pid, g, imp))
        elif g.project_id in ids:
            salida.append((g.project_id, g, float(g.amount)))
    return salida


def gastos_de_proyecto(db: Session, project_id: str) -> list[tuple[Expense, float]]:
    """Gastos aprobados o reembolsados que tocan al proyecto, directamente o por reparto."""
    from sqlalchemy import or_
    ids_por_reparto = db.query(ExpenseAllocation.expense_id).filter(ExpenseAllocation.project_id == project_id)
    gastos = db.query(Expense).filter(
        Expense.status.in_(COSTE),
        or_(Expense.project_id == project_id, Expense.id.in_(ids_por_reparto))).all()
    return importe_por_proyecto(db, gastos, project_id)


COSTE = (ExpenseStatus.approved, ExpenseStatus.reimbursed)   # un gasto reembolsado sigue siendo coste


def del_proyecto(project_id: str):
    """Condición «el gasto toca al proyecto»: es suyo o le llega una parte por reparto."""
    from sqlalchemy import or_
    return or_(Expense.project_id == project_id,
               Expense.id.in_(select(ExpenseAllocation.expense_id).where(ExpenseAllocation.project_id == project_id)))


def coste_en_proyectos(db: Session, desde, hasta, project_ids: Optional[list] = None) -> list[tuple[Expense, float]]:
    """(gasto, importe) de los gastos que son coste entre dos fechas.

    Sin `project_ids`, cada gasto entero. Con ellos, la parte que toca a esos
    proyectos: la suma de sus porcentajes de reparto, o el gasto entero si no
    tiene reparto y su proyecto está en la lista. Revisión 2026-11: las
    métricas filtradas por proyecto miraban sólo el proyecto propio del gasto.
    """
    from sqlalchemy import or_
    q = db.query(Expense).filter(Expense.status.in_(COSTE), Expense.expense_date >= desde, Expense.expense_date <= hasta)
    if not project_ids:
        return [(g, float(g.amount or 0)) for g in q.all()]
    ids = list(project_ids)
    por_reparto = db.query(ExpenseAllocation.expense_id).filter(ExpenseAllocation.project_id.in_(ids))
    gastos = q.filter(or_(Expense.project_id.in_(ids), Expense.id.in_(por_reparto))).all()
    partes: dict[str, float] = {}
    con_reparto: set[str] = set()
    for r in db.query(ExpenseAllocation).filter(ExpenseAllocation.expense_id.in_([g.id for g in gastos] or [""])).all():
        con_reparto.add(r.expense_id)
        if r.project_id in ids:
            partes[r.expense_id] = partes.get(r.expense_id, 0.0) + float(r.percentage or 0)
    salida = []
    for g in gastos:
        if g.id in con_reparto:
            if partes.get(g.id):
                salida.append((g, round(float(g.amount or 0) * partes[g.id] / 100, 2)))
        elif g.project_id in ids:
            salida.append((g, float(g.amount or 0)))
    return salida


def totales_por_proyecto(db: Session, project_ids, *, desde=None, hasta=None) -> dict[str, float]:
    """Gasto aprobado o reembolsado de cada proyecto, contando la parte del reparto.

    Una sola regla para todas las sumas por proyecto (rentabilidad del
    asistente, métricas, resumen): con reparto cuenta la parte; sin él, el
    gasto entero va a su `project_id`. La consulta es ORM, con el filtro de
    empresa de la sesión.
    """
    from sqlalchemy import or_
    ids = [p for p in project_ids if p]
    if not ids:
        return {}
    por_reparto = db.query(ExpenseAllocation.expense_id).filter(ExpenseAllocation.project_id.in_(ids))
    q = db.query(Expense).filter(Expense.status.in_(COSTE),
                                 or_(Expense.project_id.in_(ids), Expense.id.in_(por_reparto)))
    if desde is not None:
        q = q.filter(Expense.expense_date >= desde)
    if hasta is not None:
        q = q.filter(Expense.expense_date <= hasta)
    gastos = q.all()
    # M3 (auditoría 22-11-2026): una consulta de repartos (antes una por
    # proyecto) y cada gasto convertido a la moneda de la empresa con el tipo de
    # su fecha (antes se sumaban euros, dólares y libras tal cual). Los tipos
    # que falten se avisan (`TiposQueFaltan` de quien llama), no se esconden.
    from app.services.currency_rates_service import TablaDeTipos, tipo_o_aviso
    from app.services.settings_service.por_empresa import moneda_de_empresa
    moneda = moneda_de_empresa(db)
    totales: dict[str, float] = {}
    with TablaDeTipos(db):
        for pid, g, importe in importe_por_proyectos(db, gastos, ids):
            de = (g.currency or moneda).upper()
            if de != moneda:
                importe = importe * tipo_o_aviso(db, de, moneda, g.expense_date)
            totales[pid] = round(totales.get(pid, 0.0) + importe, 2)
    return totales
