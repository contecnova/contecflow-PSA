"""Las fichas de contecflow que pueden tener documentos de contecmind (revisión 2026-11).

Una sola lista para enlaces, carpetas y pantallas: añadir una ficha nueva es
añadir una línea aquí (o `registrar_ficha` desde su módulo).

Cada ficha se carga con EL MISMO cargador que usa su propia pantalla
(`get_scoped_ticket_or_404`, `get_project_scoped_or_404`…): si alguien no
puede abrir el ticket, tampoco ve ni toca sus documentos. Un contrato, además,
sólo lo abren los responsables, igual que `GET /contracts/{id}`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session
from app.core.codigos_de_error import error


@dataclass(frozen=True)
class Ficha:
    clave: str
    carpeta: str                                    # nombre de la carpeta del tipo en contecmind
    cargar: Callable[[Session, object, str], object]  # (db, usuario, id) → objeto o HTTPException 404/403
    nombre: Callable[[object], str]


def _ticket(db, usuario, id_):
    from app.services.service_desk.scoping import get_scoped_ticket_or_404
    return get_scoped_ticket_or_404(db, usuario, id_)


def _proyecto(db, usuario, id_):
    from app.services.project_service import get_project_scoped_or_404
    return get_project_scoped_or_404(db, id_, usuario)


def _contrato(db, usuario, id_):
    from app.models.user import UserRole
    from app.services.contract_service import get_contract
    if getattr(usuario, "role", None) not in (UserRole.admin, UserRole.pm, UserRole.team_lead, UserRole.hr):
        raise error(403, "contratos_solo_responsables", detail="Los contratos sólo los abren los responsables")
    c = get_contract(db, id_, usuario)
    if c is None:
        raise error(404, "no_encontrado", detail="Contrato no encontrado", que="contrato")
    return c


def _articulo(db, usuario, id_):
    from app.services.service_desk.kb_service import get_scoped_kb_article_or_404
    return get_scoped_kb_article_or_404(db, usuario, id_)


# 23-11-2026: lecciones, gastos y presupuestos. La pantalla las declaraba
# (`conectores.ts`) y el servidor respondía 404 `tipo_desconocido`. Cada una
# con la misma regla de visibilidad que su propia ficha.

def _leccion(db, usuario, id_):
    """Como `GET /lessons/{id}` (`proyectos.usar`): la visibilidad por origen de `lecciones._puede_ver`."""
    from app.core import capacidades
    from app.services import lecciones
    if not capacidades.tiene(db, usuario, "proyectos.usar"):
        raise error(403, "sin_permiso")
    leccion = lecciones._cargar(db, id_)
    if not lecciones._puede_ver(db, usuario, leccion):
        raise error(404, "no_encontrado", detail="Lección no encontrada", que="leccion")
    return leccion


def _gasto(db, usuario, id_):
    """Como los justificantes del gasto (`gastos.trabajar`): el dueño o quien lo gestiona."""
    from app.core import capacidades
    from app.services.gastos_avanzados import _gasto as gasto_visible
    if not capacidades.tiene(db, usuario, "gastos.trabajar"):
        raise error(403, "sin_permiso")
    return gasto_visible(db, usuario, id_)


def _presupuesto(db, usuario, id_):
    """Como `GET /budgets/{id}` (`presupuestos.gestionar`)."""
    from app.core import capacidades
    from app.services.budgets_service import _cargar
    if not capacidades.tiene(db, usuario, "presupuestos.gestionar"):
        raise error(403, "sin_permiso")
    return _cargar(db, id_)


FICHAS: dict[str, Ficha] = {
    "ticket": Ficha("ticket", "Tickets", _ticket, lambda o: f"{o.number} — {o.title}"),
    "contract": Ficha("contract", "Contratos", _contrato, lambda o: f"{o.code} — {o.name}"),
    "project": Ficha("project", "Proyectos", _proyecto, lambda o: f"{o.code} — {o.name}"),
    "kb_article": Ficha("kb_article", "Base de conocimiento", _articulo, lambda o: f"{o.number} — {o.title}"),
    "lesson": Ficha("lesson", "Lecciones aprendidas", _leccion, lambda o: f"{o.codigo} — {o.titulo}"),
    "expense": Ficha("expense", "Gastos", _gasto, lambda o: f"{o.code} — {o.description}"),
    "budget": Ficha("budget", "Presupuestos", _presupuesto, lambda o: f"{o.name} · v{o.version}"),
}


def registrar_ficha(ficha: Ficha) -> None:
    """Para los módulos que se declaran aparte (lecciones, gastos, presupuestos)."""
    FICHAS[ficha.clave] = ficha


def ficha(clave: str) -> Ficha:
    if clave not in FICHAS:
        raise error(404, "tipo_desconocido", detail=f"Tipo de ficha desconocido: {clave}", tipo=clave)
    return FICHAS[clave]


def cargar(db: Session, usuario, clave: str, entidad_id: str):
    """`(ficha, objeto)` vistos por `usuario`, o la misma 404/403 que su pantalla."""
    f = ficha(clave)
    return f, f.cargar(db, usuario, str(entidad_id))
