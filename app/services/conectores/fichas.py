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

from fastapi import HTTPException
from sqlalchemy.orm import Session


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
        raise HTTPException(403, "Los contratos sólo los abren los responsables")
    c = get_contract(db, id_, usuario)
    if c is None:
        raise HTTPException(404, "Contrato no encontrado")
    return c


def _articulo(db, usuario, id_):
    from app.services.service_desk.kb_service import get_scoped_kb_article_or_404
    return get_scoped_kb_article_or_404(db, usuario, id_)


FICHAS: dict[str, Ficha] = {
    "ticket": Ficha("ticket", "Tickets", _ticket, lambda o: f"{o.number} — {o.title}"),
    "contract": Ficha("contract", "Contratos", _contrato, lambda o: f"{o.code} — {o.name}"),
    "project": Ficha("project", "Proyectos", _proyecto, lambda o: f"{o.code} — {o.name}"),
    "kb_article": Ficha("kb_article", "Base de conocimiento", _articulo, lambda o: f"{o.number} — {o.title}"),
}


def registrar_ficha(ficha: Ficha) -> None:
    """Para los módulos que se declaran aparte (lecciones, gastos, presupuestos)."""
    FICHAS[ficha.clave] = ficha


def ficha(clave: str) -> Ficha:
    if clave not in FICHAS:
        raise HTTPException(404, f"Tipo de ficha desconocido: {clave}")
    return FICHAS[clave]


def cargar(db: Session, usuario, clave: str, entidad_id: str):
    """`(ficha, objeto)` vistos por `usuario`, o la misma 404/403 que su pantalla."""
    f = ficha(clave)
    return f, f.cargar(db, usuario, str(entidad_id))
