"""Busqueda global en proyectos, tareas, tickets, usuarios, facturas y oportunidades.

Parte de `app.services.cab_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
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


# ─── Global Search ────────────────────────────────────────────────────────────

def _search_projects(db: Session, q_lower: str, limit: int) -> list:
    projects = db.query(Project).filter(
        _or(
            func.lower(Project.name).like(q_lower),
            func.lower(Project.code).like(q_lower),
            func.lower(Project.client_name).like(q_lower),
        )
    ).limit(limit).all()
    return [{
        "id": p.id, "type": "project",
        "title": p.name, "subtitle": f"{p.code} · {p.client_name or '—'}",
        "status": p.status, "url": "/projects",
        "icon": "⬡",
    } for p in projects]


def _search_tasks(db: Session, q_lower: str, limit: int) -> list:
    tasks = db.query(Task).options(joinedload(Task.project)).filter(
        _or(
            func.lower(Task.title).like(q_lower),
            func.lower(Task.code).like(q_lower),
            func.lower(Task.description).like(q_lower),
        )
    ).limit(limit).all()
    return [{
        "id": t.id, "type": "task",
        "title": t.title,
        "subtitle": f"{t.project.code if t.project else '—'} · {t.status}",
        "status": t.status, "url": "/tasks",
        "icon": "▦",
    } for t in tasks]


def _search_tickets(db: Session, q_lower: str, limit: int) -> list:
    tickets = db.query(Ticket).filter(
        _or(
            func.lower(Ticket.title).like(q_lower),
            func.lower(Ticket.number).like(q_lower),
            func.lower(Ticket.requester_name).like(q_lower),
        )
    ).limit(limit).all()
    return [{
        "id": t.id, "type": "ticket",
        "title": t.title,
        "subtitle": f"#{t.number} · {t.status} · {t.priority}",
        "status": t.status, "url": "/service-desk",
        "icon": "🎫",
    } for t in tickets]


def _search_users(db: Session, q_lower: str, limit: int) -> list:
    users = db.query(UserModel).filter(
        UserModel.is_active == True,
        _or(
            func.lower(UserModel.full_name).like(q_lower),
            func.lower(UserModel.email).like(q_lower),
            func.lower(UserModel.username).like(q_lower),
        )
    ).limit(limit).all()
    return [{
        "id": u.id, "type": "user",
        "title": u.full_name,
        "subtitle": f"{u.role} · {u.email}",
        "url": "/resources",
        "icon": "👤",
    } for u in users]


def _search_invoices(db: Session, q_lower: str, limit: int) -> list:
    invoices = db.query(Inv).filter(
        _or(
            func.lower(Inv.number).like(q_lower),
            func.lower(Inv.client_name).like(q_lower),
        )
    ).limit(limit).all()
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


def _search_opportunities(db: Session, q_lower: str, limit: int) -> list:
    opps = db.query(Opp).filter(
        _or(
            func.lower(Opp.name).like(q_lower),
            func.lower(Opp.client_name).like(q_lower),
        )
    ).limit(limit).all()
    return [{
        "id": o.id, "type": "opportunity",
        "title": o.name,
        "subtitle": f"{o.client_name or '—'} · {o.stage}",
        "url": "/pipeline",
        "icon": "🎪",
    } for o in opps]


def global_search(q: str, types: Optional[str], limit: int, db: Session) -> dict:

    search_types = types.split(",") if types else ["projects", "tasks", "tickets", "users", "invoices", "opportunities"]
    q_lower = f"%{q.lower()}%"
    results = {}

    if "projects" in search_types:
        results["projects"] = _search_projects(db, q_lower, limit // 3)
    if "tasks" in search_types:
        results["tasks"] = _search_tasks(db, q_lower, limit // 3)
    if "tickets" in search_types:
        results["tickets"] = _search_tickets(db, q_lower, limit // 4)
    if "users" in search_types:
        results["users"] = _search_users(db, q_lower, limit // 4)
    if "invoices" in search_types:
        results["invoices"] = _search_invoices(db, q_lower, 10)
    if "opportunities" in search_types:
        results["opportunities"] = _search_opportunities(db, q_lower, 10)

    all_results = []
    for items in results.values():
        all_results.extend(items)
    return {
        "query": q,
        "total": sum(len(v) for v in results.values()),
        "grouped": results,
        "flat": all_results[:limit],
    }
