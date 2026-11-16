"""Dominio `catalogo` del motor de políticas (service desk, mejoras de mercado 16-11-2026).

Peticiones del catálogo del service desk (un ticket con servicio del
catálogo). Las políticas deciden la aprobación condicional sin código:

  · «Servicio es Portátil nuevo y Departamento es Ventas» → +1 nivel;
  · «Prioridad es P1» → aprobar solo;
  · «Cliente es ACME» → avisar a su gestor;
  · «Categoría es Accesos y Persona es externa» → bloquear.

La aprobación de varios niveles es la del motor común con el tipo
``catalog_request`` (`catalog_approval_service`, modo `engine`).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from app.services.politicas.registro import Campo, Dominio, Opcion, registrar

_PRIORIDADES = (Opcion("p1_critical", "P1"), Opcion("p2_high", "P2"), Opcion("p3_medium", "P3"), Opcion("p4_low", "P4"))
_TIPOS = (Opcion("service_request", "Petición de servicio"), Opcion("incident", "Incidencia"),
          Opcion("change", "Cambio"), Opcion("problem", "Problema"), Opcion("question", "Consulta"))

CAMPOS = [
    Campo("servicio", "Servicio del catálogo", "enum", categoria_de_tabla=True),
    Campo("categoria", "Categoría del catálogo", "enum"),
    Campo("tipo_ticket", "Tipo de ticket", "enum", opciones=_TIPOS),
    Campo("prioridad", "Prioridad", "enum", opciones=_PRIORIDADES),
    Campo("cliente", "Cliente", "entidad", entidad="cliente"),
    Campo("proyecto", "Proyecto", "entidad", entidad="proyecto"),
    Campo("departamento", "Departamento de quien pide", "entidad", entidad="departamento"),
    Campo("persona", "Quien pide", "entidad", entidad="usuario"),
    Campo("titulo", "Título", "texto"),
]


def _v(x):
    return getattr(x, "value", x)


def contexto(db, ticket) -> dict:
    from app.models.service_desk import ServiceItem
    from app.models.user import User
    item = db.get(ServiceItem, ticket.service_item_id) if ticket.service_item_id else None
    pide = db.get(User, ticket.requester_user_id or ticket.created_by_user_id) \
        if (ticket.requester_user_id or ticket.created_by_user_id) else None
    return {
        "servicio": ticket.service_item_id, "categoria": item.category_id if item else None,
        "tipo_ticket": _v(ticket.ticket_type), "prioridad": _v(ticket.priority),
        "cliente": ticket.client_id, "proyecto": ticket.project_id,
        "departamento": getattr(pide, "department_id", None) or getattr(pide, "department", None),
        "persona": pide.id if pide else None, "titulo": ticket.title,
        "_sujeto": {"usuario_id": pide.id if pide else None, "rol": _v(getattr(pide, "role", None)),
                    "departamento": getattr(pide, "department", None)},
        "_fecha": (ticket.created_at.date() if ticket.created_at else date.today()),
    }


def cargar(db, entidad_id: str):
    from app.models.service_desk import Ticket
    return db.query(Ticket).filter(Ticket.id == entidad_id, Ticket.service_item_id.isnot(None)).first()


def historicos(db, desde: Optional[date], hasta: Optional[date], limite: int) -> list:
    """Peticiones del catálogo, las más recientes primero (para el simulador)."""
    from app.models.service_desk import Ticket
    q = db.query(Ticket).filter(Ticket.service_item_id.isnot(None))
    if desde:
        q = q.filter(Ticket.created_at >= desde)
    if hasta:
        q = q.filter(Ticket.created_at <= hasta)
    return q.order_by(Ticket.created_at.desc()).limit(limite).all()


def resumen(t) -> str:
    return f"{t.number} · {t.title}"


def opciones_dinamicas(db) -> dict:
    from app.models.service_desk import ServiceCategory, ServiceItem
    return {
        "servicio": [Opcion(s.id, s.name) for s in db.query(ServiceItem).order_by(ServiceItem.name).all()],
        "categoria": [Opcion(c.id, c.name) for c in db.query(ServiceCategory).order_by(ServiceCategory.name).all()],
    }


registrar(Dominio(
    clave="catalogo", etiqueta="Peticiones del catálogo", campos=CAMPOS, contexto=contexto, cargar=cargar,
    historicos=historicos, propietario=lambda t: t.requester_user_id or t.created_by_user_id, resumen=resumen,
    tipo_de_aprobacion="catalog_request", opciones_dinamicas=opciones_dinamicas,
))
