"""Catálogos de clave editables por empresa (19-11-2026).

Auditoría de hardcodeados: `ClientIndustry`, `ExpenseCategory` y `ProjectType`
eran enums de BD cerrados; una empresa no podía añadir un sector, una
categoría de gasto ni un tipo de proyecto (el de proyecto ya tenía catálogo,
`custom_project_types`, pero la columna era enum y rechazaba lo que no fuera de
los cinco de siempre). Desde la revisión 186 las columnas guardan la clave
(VARCHAR) y la clave se valida contra su catálogo:

* `project_types`       → `CustomProjectType`     → `projects.project_type`
* `client_industries`   → `CustomClientIndustry`  → `clients.industry`
* `expense_categories`  → `CustomExpenseCategory` → `expenses.category`

Las filas globales (`organization_id = NULL`) son los valores de siempre, con
las mismas claves (compatibilidad del API). Los enums de Python siguen
existiendo solo como lista de claves del sistema (sembrado y código antiguo).
El frontend traduce la etiqueta por clave (`catalogos.<catalogo>.<clave>`) y
usa `label` de respaldo para las claves propias de cada empresa.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.models.settings import CustomClientIndustry, CustomExpenseCategory, CustomProjectType
from app.services.settings_service.catalogos import DEFAULT_PROJECT_TYPES, _exigir_propio, _sellar

DEFAULT_CLIENT_INDUSTRIES = [
    ("technology", "Tecnología", "#00d4ff"),
    ("finance", "Finanzas", "#00e5a0"),
    ("healthcare", "Salud", "#ec4899"),
    ("retail", "Comercio", "#ffb800"),
    ("manufacturing", "Industria", "#7c3aed"),
    ("education", "Educación", "#38bdf8"),
    ("consulting", "Consultoría", "#2dd4bf"),
    ("real_estate", "Inmobiliario", "#84cc16"),
    ("media", "Medios", "#f97316"),
    ("other", "Otro", "#7a8aaa"),
]

DEFAULT_EXPENSE_CATEGORIES = [
    ("travel", "Viajes", "#00d4ff"),
    ("accommodation", "Alojamiento", "#7c3aed"),
    ("meals", "Comidas", "#ffb800"),
    ("software", "Software", "#38bdf8"),
    ("hardware", "Hardware", "#2dd4bf"),
    ("training", "Formación", "#00e5a0"),
    ("subcontract", "Subcontratación", "#ec4899"),
    ("other", "Otro", "#7a8aaa"),
]

#: nombre → (modelo, valores del sistema, nombre del campo para los mensajes)
CATALOGOS = {
    "project_types": (CustomProjectType, DEFAULT_PROJECT_TYPES, "tipo de proyecto"),
    "client_industries": (CustomClientIndustry, DEFAULT_CLIENT_INDUSTRIES, "sector"),
    "expense_categories": (CustomExpenseCategory, DEFAULT_EXPENSE_CATEGORIES, "categoría de gasto"),
}


def _modelo(nombre: str):
    return CATALOGOS[nombre][0]


def _sembrar(db: Session, nombre: str) -> None:
    modelo, valores, _ = CATALOGOS[nombre]
    if db.query(modelo).count() == 0:
        for i, (value, label, color) in enumerate(valores):
            db.add(modelo(value=value, label=label, color=color, sort_order=i))
        db.commit()


def listar(db: Session, nombre: str) -> list:
    """Valores activos del catálogo (globales + los de la empresa del contexto)."""
    _sembrar(db, nombre)
    modelo = _modelo(nombre)
    return db.query(modelo).filter(modelo.is_active == True).order_by(modelo.sort_order).all()  # noqa: E712


def crear(db: Session, nombre: str, datos: dict):
    modelo = _modelo(nombre)
    if db.query(modelo).filter(modelo.value == datos["value"], modelo.is_active == True).first():  # noqa: E712
        raise error(409, "elemento_duplicado", detail="Ya existe un valor con esa clave")
    item = modelo(**_sellar(db, datos))
    db.add(item); db.commit(); db.refresh(item)
    return item


def actualizar(db: Session, nombre: str, item_id: str, datos: dict):
    modelo = _modelo(nombre)
    item = db.query(modelo).filter(modelo.id == item_id).first()
    if not item:
        raise ValueError("not_found")
    _exigir_propio(db, item)
    for k, v in datos.items():
        setattr(item, k, v)
    db.commit(); db.refresh(item)
    return item


def borrar(db: Session, nombre: str, item_id: str) -> dict:
    modelo = _modelo(nombre)
    item = db.query(modelo).filter(modelo.id == item_id).first()
    if not item:
        raise ValueError("not_found")
    _exigir_propio(db, item)
    item.is_active = False
    db.commit()
    return {"ok": True}


def clave(valor) -> Optional[str]:
    """Clave en texto plano: acepta el enum antiguo (`ProjectType.rd`) o el texto."""
    if valor is None or valor == "":
        return None
    return str(getattr(valor, "value", valor)).strip()


def exigir_clave(db: Session, nombre: str, valor) -> Optional[str]:
    """Devuelve la clave si está activa en el catálogo de la empresa; si no, 422.

    `None`/vacío pasa (los campos opcionales siguen siéndolo).
    """
    k = clave(valor)
    if k is None:
        return None
    _sembrar(db, nombre)
    modelo, _, campo = CATALOGOS[nombre]
    if db.query(modelo.id).filter(modelo.value == k, modelo.is_active == True).first() is None:  # noqa: E712
        raise _no_existe(campo, k)
    return k


def _no_existe(campo: str, k: str):
    """422 con código (errores con código, 19-11-2026): `no_encontrado` + `que`."""
    return error(422, "no_encontrado", que="valor_de_catalogo",
                 detail=f"El {campo} «{k}» no existe en el catálogo de la empresa (Configuración)")


# ── Validación en un solo sitio: antes de cada flush ─────────────────────────
#
# Los proyectos, clientes y gastos se crean desde muchos sitios (pantallas,
# importaciones, pipeline, plantillas, IA). En vez de validar en cada uno, un
# `before_flush` comprueba la clave de los objetos nuevos o con la clave
# cambiada. Sin sembrar (no se puede hacer commit dentro de un flush): con el
# catálogo vacío valen las claves del sistema.

#: (módulo, clase, atributo, catálogo)
_VIGILADOS = (
    ("app.models.project", "Project", "project_type", "project_types"),
    ("app.models.clients", "Client", "industry", "client_industries"),
    ("app.models.expenses", "Expense", "category", "expense_categories"),
)
_clases: dict = {}


def _clase(modulo: str, nombre: str):
    if (modulo, nombre) not in _clases:
        import importlib
        _clases[(modulo, nombre)] = getattr(importlib.import_module(modulo), nombre)
    return _clases[(modulo, nombre)]


def _clave_valida(session, catalogo: str, k: str) -> bool:
    modelo, valores, _ = CATALOGOS[catalogo]
    with session.no_autoflush:
        if session.query(modelo.id).filter(modelo.value == k, modelo.is_active == True).first() is not None:  # noqa: E712
            return True
        if session.query(modelo.id).first() is None:
            return k in {v[0] for v in valores}
    return False


def validar_claves_antes_de_guardar(session, flush_context=None, instances=None) -> None:
    """`before_flush`: la clave de tipo/sector/categoría existe en su catálogo (o 422)."""
    from sqlalchemy import inspect as _inspect
    candidatos = list(session.new) + [o for o in session.dirty if o not in session.new]
    if not candidatos:
        return
    for modulo, nombre, atributo, catalogo in _VIGILADOS:
        clase = _clase(modulo, nombre)
        for obj in candidatos:
            if not isinstance(obj, clase):
                continue
            if obj not in session.new and not _inspect(obj).attrs[atributo].history.has_changes():
                continue
            k = clave(getattr(obj, atributo, None))
            if k is None:
                continue
            if getattr(obj, atributo) != k:
                setattr(obj, atributo, k)  # el enum antiguo se guarda como su clave
            if not _clave_valida(session, catalogo, k):
                raise _no_existe(CATALOGOS[catalogo][2], k)


def _registrar() -> None:
    from sqlalchemy import event
    from sqlalchemy.orm import Session as _Session
    if not event.contains(_Session, "before_flush", validar_claves_antes_de_guardar):
        event.listen(_Session, "before_flush", validar_claves_antes_de_guardar)


_registrar()
