"""Dominio `gastos`: el adaptador de prueba del motor (tarea #26).

Mapea el modelo `Expense` existente al catálogo del motor. La migración
completa de gastos al motor (envío, pantalla, retirar `ExpensePolicy`) es la
tarea #27; ver «Extension points» en el README. Lo que #27 tiene que hacer:

    from app.services import politicas
    ev = politicas.evaluar(db, "gastos", gasto)
    if ev["decision"] == "block": raise ErrorDeDominio(422, …)
    pendientes = politicas.requisitos_pendientes(db, "gastos", gasto, ev["resultado"])
    politicas.aplicar_campos(db, "gastos", gasto, ev["resultado"])
    fila = politicas.registrar_evaluacion(db, "gastos", gasto.id, ev, usuario_id=…)
    fuentes.abrir(db, "expense", gasto.id, resumen, gasto.user_id, contexto, evaluacion=ev)
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from app.services.politicas.catalogo import Campo, Dominio, Opcion, registrar

_CATEGORIAS = (("travel", "Viajes"), ("accommodation", "Alojamiento"), ("meals", "Comidas"),
               ("software", "Software"), ("hardware", "Hardware"), ("training", "Formación"),
               ("subcontract", "Subcontratación"), ("other", "Otros"))

CAMPOS = [
    Campo("categoria", "Categoría", "enum", opciones=tuple(Opcion(v, e) for v, e in _CATEGORIAS),
          categoria_de_tabla=True),
    Campo("importe", "Importe", "importe", ayuda="Se compara en la moneda de la condición, al tipo de cambio de la fecha del gasto"),
    Campo("moneda", "Moneda", "texto", operadores=("eq", "ne", "in", "not_in")),
    Campo("fecha", "Fecha del gasto", "fecha"),
    Campo("pais", "País", "pais"),
    Campo("ciudad", "Ciudad", "ciudad"),
    Campo("proyecto", "Proyecto", "entidad", entidad="proyecto"),
    Campo("facturable", "Facturable al cliente", "booleano", asignable=True),
    Campo("descripcion", "Descripción", "texto"),
    Campo("notas", "Justificación (notas)", "texto"),
    Campo("km", "Kilómetros", "numero"),
    Campo("justificantes", "Justificantes adjuntos", "numero"),
    Campo("persona", "Persona", "entidad", entidad="usuario"),
    Campo("rol", "Rol de quien gasta", "entidad", entidad="rol"),
    Campo("departamento", "Departamento", "entidad", entidad="departamento"),
    Campo("equipo", "Equipo", "entidad", entidad="equipo"),
]


def _usuario(db, user_id):
    from app.models.user import User
    return db.query(User).filter(User.id == user_id).first() if user_id else None


def contexto(db, e) -> dict:
    from sqlalchemy import func
    from app.models.expenses import ExpenseAttachment
    u = _usuario(db, e.user_id)
    rol = getattr(getattr(u, "role", None), "value", getattr(u, "role", None))
    adjuntos = db.query(func.count(ExpenseAttachment.id)).filter(ExpenseAttachment.expense_id == e.id).scalar() or 0
    adjuntos += 1 if e.receipt_url else 0
    pais = (e.country or "").upper() or None
    return {
        "categoria": str(getattr(e.category, "value", e.category)),
        "importe": {"cantidad": float(e.amount or 0), "moneda": (e.currency or "").upper() or None},
        "moneda": (e.currency or "").upper() or None,
        "fecha": e.expense_date,
        "pais": pais,
        "ciudad": e.city,
        "proyecto": e.project_id,
        "facturable": bool(e.is_billable),
        "descripcion": e.description,
        "notas": e.notes,
        "km": e.km,
        "justificantes": int(adjuntos),
        "persona": e.user_id,
        "rol": rol,
        "departamento": getattr(u, "department", None),
        "equipo": getattr(u, "team", None),
        "_sujeto": {"usuario_id": e.user_id, "rol": rol, "departamento": getattr(u, "department", None),
                    "equipo": getattr(u, "team", None), "pais": pais, "ciudad": e.city},
        "_fecha": e.expense_date,
    }


def cargar(db, entidad_id: str):
    from app.models.expenses import Expense
    return db.query(Expense).filter(Expense.id == entidad_id).first()


def historicos(db, desde: Optional[date], hasta: Optional[date], limite: int) -> list:
    """Gastos enviados alguna vez (no borradores), los más recientes primero."""
    from app.models.expenses import Expense, ExpenseStatus
    q = db.query(Expense).filter(Expense.is_active.is_(True), Expense.status != ExpenseStatus.draft)
    if desde:
        q = q.filter(Expense.expense_date >= desde)
    if hasta:
        q = q.filter(Expense.expense_date <= hasta)
    return q.order_by(Expense.expense_date.desc(), Expense.created_at.desc()).limit(limite).all()


def resumen(e) -> str:
    return f"{e.code} · {e.description or ''} · {float(e.amount or 0):.2f} {e.currency or ''}".strip()


def cumple_requisito(db, e, requisito: dict) -> bool:
    if requisito.get("tipo") == "require_justification":
        return bool((e.notes or "").strip())
    if requisito.get("tipo") == "require_attachment":
        # Los justificantes no llevan tipo de documento: basta con uno. #27
        # puede guardar el tipo y exigir los de `tipos_de_documento`.
        return contexto(db, e)["justificantes"] > 0
    return True


def aplicar_campo(db, e, campo: str, valor) -> None:
    if campo == "facturable":
        e.is_billable = bool(valor)


registrar(Dominio(
    clave="gastos", etiqueta="Gastos", campos=CAMPOS, contexto=contexto, cargar=cargar,
    historicos=historicos, propietario=lambda e: e.user_id, resumen=resumen,
    tipo_de_aprobacion="expense", cumple_requisito=cumple_requisito, aplicar_campo=aplicar_campo,
))
