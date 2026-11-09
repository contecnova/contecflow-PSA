"""Gastos: justificantes, reparto entre proyectos, políticas y kilometraje (revisión 2026-11).

- **Justificantes y documentos**: varios por gasto, en el almacén de ficheros
  (local o S3, `file_storage`); se descargan con una URL firmada de corta vida.
- **Reparto**: un gasto se puede repartir entre proyectos por porcentaje
  (suman 100). Con reparto, lo que cuenta para cada proyecto es su parte; sin
  él, el gasto entero va a su `project_id`.
- **Políticas**: reglas por categoría (o todas) —tope por gasto, tope diario
  por persona, justificante obligatorio desde un importe, explicación
  obligatoria desde un importe— con acción `bloquear` (no se puede enviar) o
  `avisar` (se envía marcado). Lo que excede una política llega al motor de
  aprobaciones como `policy_exceeded`, y un flujo puede pedir un paso más.
- **Kilometraje**: con `km`, el importe lo calcula el servidor con
  `EXPENSE_MILEAGE_RATE`.
"""
from __future__ import annotations

from sqlalchemy import select

import json
import logging
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.expenses import Expense, ExpenseAllocation, ExpenseAttachment, ExpensePolicy, ExpenseStatus
ACCIONES = ("bloquear", "avisar")


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
        raise HTTPException(404, "Gasto no encontrado")
    gestor = es_gestor(db, usuario)
    if e.user_id != usuario.id and not gestor:
        raise HTTPException(404, "Gasto no encontrado")
    if editar and not gestor and e.status != ExpenseStatus.draft:
        raise HTTPException(409, "Sólo se cambia un gasto en borrador")
    return e


# ── Kilometraje ───────────────────────────────────────────────────────────────

def aplicar_kilometraje(db: Session, expense: Expense) -> None:
    if expense.km is None:
        return
    if expense.km <= 0:
        raise HTTPException(400, "Los kilómetros tienen que ser positivos")
    tarifa = float(_aj(db, "EXPENSE_MILEAGE_RATE", expense.organization_id))
    expense.amount = round(float(expense.km) * tarifa, 2)


# ── Justificantes ─────────────────────────────────────────────────────────────

def _adjunto_dict(a: ExpenseAttachment) -> dict:
    return {"id": a.id, "filename": a.filename, "content_type": a.content_type, "size_bytes": a.size_bytes,
            "created_at": a.created_at.isoformat() if a.created_at else None}


def adjuntos(db: Session, usuario, expense_id: str) -> list[dict]:
    _gasto(db, usuario, expense_id)
    return [_adjunto_dict(a) for a in db.query(ExpenseAttachment).filter(ExpenseAttachment.expense_id == expense_id)
            .order_by(ExpenseAttachment.created_at).all()]


def subir_adjunto(db: Session, usuario, expense_id: str, contenido: bytes, nombre: str, tipo: Optional[str]) -> dict:
    from app.services.audit import audit_log
    from app.services.s3_service import file_storage
    e = _gasto(db, usuario, expense_id, editar=True)
    maximo = int(_aj(db, "EXPENSE_ATTACHMENT_MAX_MB", e.organization_id, "int")) * 1024 * 1024
    if not contenido:
        raise HTTPException(400, "El fichero está vacío")
    if len(contenido) > maximo:
        raise HTTPException(413, f"El fichero pasa del máximo ({maximo // (1024 * 1024)} MB)")
    clave, tamano = file_storage.upload_file(contenido, nombre, f"expense-{e.id}", 1, tipo or "application/octet-stream")
    a = ExpenseAttachment(organization_id=e.organization_id, expense_id=e.id, filename=nombre[:255],
                          content_type=tipo, size_bytes=tamano, storage_key=clave, uploaded_by=usuario.id)
    db.add(a)
    if not e.receipt_name:      # el primero hace de justificante principal en las listas
        e.receipt_name = nombre[:255]
    audit_log(db, usuario, "CREATE", "expense_attachments", e.id, e.code, new_values={"fichero": nombre})
    db.commit()
    return _adjunto_dict(a)


def url_de_adjunto(db: Session, usuario, attachment_id: str) -> str:
    from app.services.s3_service import file_storage
    a = db.query(ExpenseAttachment).filter(ExpenseAttachment.id == attachment_id).first()
    if a is None:
        raise HTTPException(404, "Justificante no encontrado")
    _gasto(db, usuario, a.expense_id)
    return file_storage.generate_presigned_url(a.storage_key)


def borrar_adjunto(db: Session, usuario, attachment_id: str) -> None:
    from app.services.audit import audit_log
    from app.services.s3_service import file_storage
    a = db.query(ExpenseAttachment).filter(ExpenseAttachment.id == attachment_id).first()
    if a is None:
        raise HTTPException(404, "Justificante no encontrado")
    e = _gasto(db, usuario, a.expense_id, editar=True)
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
            raise HTTPException(400, "Un proyecto aparece dos veces en el reparto")
        if any(float(p["percentage"]) <= 0 for p in partes):
            raise HTTPException(400, "Cada parte tiene que ser mayor que cero")
        total = sum(float(p["percentage"]) for p in partes)
        if abs(total - 100) > 0.01:
            raise HTTPException(400, f"El reparto suma {round(total, 2)} %, tiene que sumar 100 %")
        existentes = {pid for (pid,) in db.query(Project.id).filter(Project.id.in_(ids)).all()}
        if set(ids) - existentes:
            raise HTTPException(404, "Proyecto no encontrado")
    db.query(ExpenseAllocation).filter(ExpenseAllocation.expense_id == e.id).delete(synchronize_session=False)
    for p in partes:
        db.add(ExpenseAllocation(organization_id=e.organization_id, expense_id=e.id, project_id=p["project_id"],
                                 percentage=round(float(p["percentage"]), 4)))
    audit_log(db, usuario, "UPDATE", "expenses", e.id, e.code, new_values={"reparto": partes})
    db.commit()
    return reparto(db, usuario, expense_id)


def importe_por_proyecto(db: Session, gastos: list[Expense], project_id: str) -> list[tuple[Expense, float]]:
    """(gasto, parte del proyecto). Con reparto cuenta la parte; sin reparto, el gasto entero si es suyo."""
    if not gastos:
        return []
    partes: dict[str, dict[str, float]] = {}
    for r in db.query(ExpenseAllocation).filter(ExpenseAllocation.expense_id.in_([g.id for g in gastos])).all():
        partes.setdefault(r.expense_id, {})[r.project_id] = r.percentage
    salida = []
    for g in gastos:
        if g.id in partes:
            pct = partes[g.id].get(project_id)
            if pct:
                salida.append((g, round(float(g.amount) * pct / 100, 2)))
        elif g.project_id == project_id:
            salida.append((g, float(g.amount)))
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
    totales: dict[str, float] = {}
    for pid in ids:
        for _, importe in importe_por_proyecto(db, gastos, pid):
            totales[pid] = round(totales.get(pid, 0.0) + importe, 2)
    return totales


# ── Políticas ─────────────────────────────────────────────────────────────────

_CAMPOS = ("nombre", "categoria", "limite_por_gasto", "limite_diario", "justificante_desde", "justificacion_desde",
           "accion", "activa")


def _politica_dict(p: ExpensePolicy) -> dict:
    return {k: getattr(p, k) for k in ("id",) + _CAMPOS}


def politicas(db: Session) -> list[dict]:
    return [_politica_dict(p) for p in db.query(ExpensePolicy).order_by(ExpensePolicy.created_at).all()]


def _validar_politica(datos: dict) -> None:
    if "accion" in datos and datos["accion"] not in ACCIONES:
        raise HTTPException(400, f"Acción no válida: {datos['accion']}")
    for k in ("limite_por_gasto", "limite_diario", "justificante_desde", "justificacion_desde"):
        if datos.get(k) is not None and float(datos[k]) < 0:
            raise HTTPException(400, f"«{k}» no puede ser negativo")


def crear_politica(db: Session, usuario, datos: dict) -> dict:
    from app.services.audit import audit_log
    _validar_politica(datos)
    reglas = [datos.get(k) for k in ("limite_por_gasto", "limite_diario", "justificante_desde", "justificacion_desde")]
    if all(r is None for r in reglas):
        raise HTTPException(400, "Una política necesita al menos una regla")
    p = ExpensePolicy(organization_id=usuario.organization_id, created_by=usuario.id,
                      **{k: datos.get(k) for k in _CAMPOS if datos.get(k) is not None})
    db.add(p)
    db.flush()
    audit_log(db, usuario, "CREATE", "expense_policies", p.id, p.nombre, new_values=_politica_dict(p))
    db.commit()
    return _politica_dict(p)


def editar_politica(db: Session, usuario, politica_id: str, datos: dict) -> dict:
    from app.services.audit import audit_log
    p = db.query(ExpensePolicy).filter(ExpensePolicy.id == politica_id).first()
    if p is None:
        raise HTTPException(404, "Política no encontrada")
    _validar_politica(datos)
    antes = _politica_dict(p)
    for k in _CAMPOS:
        if k in datos:
            setattr(p, k, datos[k])
    audit_log(db, usuario, "UPDATE", "expense_policies", p.id, p.nombre, old_values=antes, new_values=_politica_dict(p))
    db.commit()
    return _politica_dict(p)


def borrar_politica(db: Session, usuario, politica_id: str) -> None:
    from app.services.audit import audit_log
    p = db.query(ExpensePolicy).filter(ExpensePolicy.id == politica_id).first()
    if p is None:
        raise HTTPException(404, "Política no encontrada")
    audit_log(db, usuario, "DELETE", "expense_policies", p.id, p.nombre, old_values=_politica_dict(p))
    db.delete(p)
    db.commit()


def _cat(e: Expense) -> str:
    return str(getattr(e.category, "value", e.category))


def evaluar(db: Session, e: Expense) -> list[dict]:
    """Las reglas que el gasto incumple, con la política, la regla y un mensaje que se puede enseñar."""
    from app.services.expense_service import CATEGORY_LABELS
    salida = []
    categoria = _cat(e)
    importe = float(e.amount or 0)
    n_adjuntos = db.query(func.count(ExpenseAttachment.id)).filter(ExpenseAttachment.expense_id == e.id).scalar() or 0
    for p in db.query(ExpensePolicy).filter(ExpensePolicy.activa.is_(True)).all():
        if p.categoria and p.categoria != categoria:
            continue
        ambito = CATEGORY_LABELS.get(p.categoria, p.categoria) if p.categoria else "cualquier categoría"

        def poner(regla, mensaje, p=p):
            salida.append({"politica_id": p.id, "politica": p.nombre, "regla": regla, "accion": p.accion,
                           "mensaje": mensaje})
        if p.limite_por_gasto is not None and importe > p.limite_por_gasto:
            poner("limite_por_gasto", f"{p.nombre}: {importe:.2f} supera el tope de {p.limite_por_gasto:.2f} por gasto ({ambito})")
        if p.limite_diario is not None and e.expense_date:
            dia = db.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
                Expense.user_id == e.user_id, Expense.expense_date == e.expense_date, Expense.id != e.id,
                Expense.status.notin_([ExpenseStatus.rejected]), Expense.is_active.is_(True),
                *( [Expense.category == e.category] if p.categoria else [] )).scalar() or 0
            if float(dia) + importe > p.limite_diario:
                poner("limite_diario", f"{p.nombre}: {float(dia) + importe:.2f} el {e.expense_date.isoformat()} supera "
                                       f"el tope diario de {p.limite_diario:.2f} ({ambito})")
        if p.justificante_desde is not None and importe >= p.justificante_desde and n_adjuntos == 0:
            poner("justificante", f"{p.nombre}: desde {p.justificante_desde:.2f} hay que adjuntar el justificante")
        if p.justificacion_desde is not None and importe >= p.justificacion_desde and not (e.notes or "").strip():
            poner("justificacion", f"{p.nombre}: desde {p.justificacion_desde:.2f} hay que explicar el gasto (notas)")
    return salida


def comprobar(db: Session, usuario, expense_id: str) -> dict:
    e = _gasto(db, usuario, expense_id)
    v = evaluar(db, e)
    return {"incumplimientos": v, "bloquea": any(x["accion"] == "bloquear" for x in v)}


def antes_de_enviar(db: Session, e: Expense) -> dict:
    """Bloquea el envío si alguna política lo exige; guarda los avisos y devuelve el contexto para aprobar."""
    v = evaluar(db, e)
    bloqueos = [x["mensaje"] for x in v if x["accion"] == "bloquear"]
    if bloqueos:
        raise HTTPException(422, "No se puede enviar: " + "; ".join(bloqueos))
    avisos = [x for x in v if x["accion"] == "avisar"]
    e.policy_flags = json.dumps(avisos, ensure_ascii=False) if avisos else None
    return {"policy_exceeded": bool(avisos)}


def avisos_guardados(e: Expense) -> list[dict]:
    try:
        return json.loads(e.policy_flags) if e.policy_flags else []
    except ValueError:
        return []

