"""Busqueda global en proyectos, tareas, tickets, usuarios, facturas y oportunidades.

Parte de `app.services.cab_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.

Segunda auditoría 2026-11: cada sección pasa por el MISMO alcance que el listado
de su entidad (no hay una regla propia de la búsqueda). Antes solo se acotaban
las personas: un empleado o un subcontratado encontraba los proyectos, tareas y
tickets de toda la empresa, y sus facturas y oportunidades.

- proyectos: `scope_projects_query`;
- tareas: `build_task_list_query` (el de `GET /tasks`);
- tickets: `scope_ticket_query`;
- personas: `politica_de_visibilidad.acotar_personas`;
- facturas y oportunidades: solo a quien lee su módulo
  (`politica_de_visibilidad.ve_modulo_financiero`: el rol de sus rutas y la
  matriz GRC), y con el alcance de su listado (`_scope_invoice_query`,
  `scope_opportunity_query`).

Las `consulta_de_*` devuelven la consulta acotada (o `None` si el rol no puede
leer esa entidad) para que otras búsquedas (la del asistente de IA) las reutilicen.
"""
from __future__ import annotations

from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
from app.models.project import Project
from app.models.task import Task
from app.models.billing_reports import Invoice as Inv
from app.models.pipeline import Opportunity as Opp
from app.models.service_desk import Ticket
from app.models.user import User as UserModel
from sqlalchemy import or_ as _or
from app.services import politica_de_visibilidad as _vis

#: Módulo GRC de cada sección financiera (el primer segmento de su ruta).
MODULO_DE_FACTURAS = "invoices"
MODULO_DE_OPORTUNIDADES = "pipeline"


# ─── Consultas acotadas (reutilizables) ───────────────────────────────────────

def consulta_de_proyectos(db: Session, viewer, patron: str):
    from app.services.project_service import scope_projects_query
    return scope_projects_query(db.query(Project), db, viewer).filter(
        _or(
            func.lower(Project.name).like(patron),
            func.lower(Project.code).like(patron),
            func.lower(Project.client_name).like(patron),
        )
    )


def consulta_de_tareas(db: Session, viewer, patron: str):
    from app.services.tasks.queries import build_task_list_query
    return build_task_list_query(db, viewer).options(joinedload(Task.project)).filter(
        _or(
            func.lower(Task.title).like(patron),
            func.lower(Task.code).like(patron),
            func.lower(Task.description).like(patron),
        )
    )


def consulta_de_tickets(db: Session, viewer, patron: str):
    from app.services.service_desk.scoping import scope_ticket_query
    return scope_ticket_query(db.query(Ticket), db, viewer).filter(
        _or(
            func.lower(Ticket.title).like(patron),
            func.lower(Ticket.number).like(patron),
            func.lower(Ticket.requester_name).like(patron),
        )
    )


def consulta_de_personas(db: Session, viewer, patron: str):
    ve_contacto = _vis.ve_contacto_ajeno(viewer)
    campos = [UserModel.full_name, UserModel.username] + ([UserModel.email] if ve_contacto else [])
    return _vis.acotar_personas(db.query(UserModel).filter(
        UserModel.is_active == True,
        _or(*(func.lower(c).like(patron) for c in campos)),
    ), db, viewer)


def consulta_de_facturas(db: Session, viewer, patron: str):
    if not _vis.ve_modulo_financiero(db, viewer, MODULO_DE_FACTURAS):
        return None
    from app.services.billing_reports_service._comun import _scope_invoice_query
    return _scope_invoice_query(db).filter(
        _or(
            func.lower(Inv.number).like(patron),
            func.lower(Inv.client_name).like(patron),
        )
    )


def consulta_de_oportunidades(db: Session, viewer, patron: str):
    if not _vis.ve_modulo_financiero(db, viewer, MODULO_DE_OPORTUNIDADES):
        return None
    from app.services.pipeline_service import scope_opportunity_query
    return scope_opportunity_query(db.query(Opp).filter(Opp.is_active == True), db, viewer).filter(
        _or(
            func.lower(Opp.name).like(patron),
            func.lower(Opp.client_name).like(patron),
        )
    )


# ─── Global Search ────────────────────────────────────────────────────────────

def _search_projects(db: Session, q_lower: str, limit: int, viewer) -> list:
    projects = consulta_de_proyectos(db, viewer, q_lower).limit(limit).all()
    return [{
        "id": p.id, "type": "project",
        "title": p.name, "subtitle": f"{p.code} · {p.client_name or '—'}",
        "status": p.status, "url": "/projects",
        "icon": "⬡",
    } for p in projects]


def _search_tasks(db: Session, q_lower: str, limit: int, viewer) -> list:
    tasks = consulta_de_tareas(db, viewer, q_lower).limit(limit).all()
    return [{
        "id": t.id, "type": "task",
        "title": t.title,
        "subtitle": f"{t.project.code if t.project else '—'} · {t.status}",
        "status": t.status, "url": "/tasks",
        "icon": "▦",
    } for t in tasks]


def _search_tickets(db: Session, q_lower: str, limit: int, viewer) -> list:
    tickets = consulta_de_tickets(db, viewer, q_lower).limit(limit).all()
    return [{
        "id": t.id, "type": "ticket",
        "title": t.title,
        "subtitle": f"#{t.number} · {t.status} · {t.priority}",
        "status": t.status, "url": "/service-desk",
        "icon": "🎫",
    } for t in tickets]


def _search_users(db: Session, q_lower: str, limit: int, viewer) -> list:
    # Segunda auditoría 2026-11: las personas que ve quien busca
    # (`politica_de_visibilidad`); sin correo para quien no ve el contacto ajeno.
    ve_contacto = _vis.ve_contacto_ajeno(viewer)
    users = consulta_de_personas(db, viewer, q_lower).limit(limit).all()
    return [{
        "id": u.id, "type": "user",
        "title": u.full_name,
        "subtitle": f"{u.role} · {u.email}" if ve_contacto else f"{u.role}",
        "url": "/resources",
        "icon": "👤",
    } for u in users]


def _search_invoices(db: Session, q_lower: str, limit: int, viewer) -> list:
    consulta = consulta_de_facturas(db, viewer, q_lower)
    if consulta is None:
        return []
    invoices = consulta.limit(limit).all()
    from app.services.formato_regional import simbolo_de_moneda
    simbolos: dict = {}

    def _simbolo(i) -> str:
        clave = (getattr(i, "organization_id", None), getattr(i, "currency", None))
        if clave not in simbolos:
            simbolos[clave] = simbolo_de_moneda(db, clave[0], moneda=clave[1])
        return simbolos[clave]

    return [{
        "id": i.id, "type": "invoice",
        "title": i.number,
        "subtitle": f"{i.client_name or '—'} · {i.total} {_simbolo(i)} · {i.status}",
        "status": i.status, "url": "/invoices",
        "icon": "🧾",
    } for i in invoices]


def _search_opportunities(db: Session, q_lower: str, limit: int, viewer) -> list:
    consulta = consulta_de_oportunidades(db, viewer, q_lower)
    if consulta is None:
        return []
    opps = consulta.limit(limit).all()
    return [{
        "id": o.id, "type": "opportunity",
        "title": o.name,
        "subtitle": f"{o.client_name or '—'} · {o.stage}",
        "url": "/pipeline",
        "icon": "🎪",
    } for o in opps]


def global_search(q: str, types: Optional[str], limit: int, db: Session, viewer) -> dict:

    search_types = types.split(",") if types else ["projects", "tasks", "tickets", "users", "invoices", "opportunities"]
    q_lower = f"%{q.lower()}%"
    results = {}

    if "projects" in search_types:
        results["projects"] = _search_projects(db, q_lower, limit // 3, viewer)
    if "tasks" in search_types:
        results["tasks"] = _search_tasks(db, q_lower, limit // 3, viewer)
    if "tickets" in search_types:
        results["tickets"] = _search_tickets(db, q_lower, limit // 4, viewer)
    if "users" in search_types:
        results["users"] = _search_users(db, q_lower, limit // 4, viewer)
    if "invoices" in search_types:
        results["invoices"] = _search_invoices(db, q_lower, 10, viewer)
    if "opportunities" in search_types:
        results["opportunities"] = _search_opportunities(db, q_lower, 10, viewer)

    all_results = []
    for items in results.values():
        all_results.extend(items)
    return {
        "query": q,
        "total": sum(len(v) for v in results.values()),
        "grouped": results,
        "flat": all_results[:limit],
    }
