"""Enlace automático de una reunión a su proyecto y cliente (sin pisar lo elegido).

Orden: el evento de calendario (misma URL, o mismo título ±2 h) → su proyecto;
el código de un proyecto en el título; el proyecto en el que son miembros más
asistentes internos (solo si gana uno claro y con al menos dos). Cliente:
correos de asistentes que son contactos de un cliente; si no, el del proyecto.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import timedelta

from sqlalchemy import func, or_
from sqlalchemy.orm import Session


def _evento(db: Session, reunion):
    from app.models.cab import CalendarEvent
    if reunion.calendar_event_id:
        return db.get(CalendarEvent, reunion.calendar_event_id)
    if reunion.join_url:
        url = reunion.join_url[:400]
        ev = db.query(CalendarEvent).filter(or_(CalendarEvent.location.contains(url),
                                                CalendarEvent.description.contains(url))).first()
        if ev:
            return ev
    if reunion.meeting_date and reunion.title:
        margen = timedelta(hours=2)
        return db.query(CalendarEvent).filter(
            func.lower(CalendarEvent.title) == reunion.title.strip().lower(),
            CalendarEvent.start_dt >= reunion.meeting_date - margen,
            CalendarEvent.start_dt <= reunion.meeting_date + margen).first()
    return None


def _por_codigo(db: Session, titulo: str):
    from app.models.project import Project
    if not titulo:
        return None
    for code in set(re.findall(r"[A-Z][A-Z0-9]{1,9}-\d{1,6}|[A-Z][A-Z0-9]{2,9}", titulo)):
        p = db.query(Project).filter(Project.code == code).first()
        if p:
            return p
    return None


def _por_miembros(db: Session, reunion):
    from app.models.project import Project, ProjectMember
    usuarios = [p.user_id for p in reunion.participantes if p.user_id]
    if len(usuarios) < 2:
        return None
    filas = db.query(ProjectMember.project_id).join(Project, Project.id == ProjectMember.project_id).filter(
        ProjectMember.user_id.in_(usuarios), ProjectMember.is_active.isnot(False), Project.is_active.is_(True)).all()
    cuenta = Counter(p for (p,) in filas).most_common(2)
    if not cuenta or cuenta[0][1] < 2 or (len(cuenta) > 1 and cuenta[1][1] == cuenta[0][1]):
        return None
    return db.get(Project, cuenta[0][0])


def _cliente_por_correos(db: Session, reunion):
    from app.models.clients import ClientContact
    correos = {(p.email or "").strip().lower() for p in reunion.participantes if p.email}
    if not correos:
        return None
    filas = db.query(ClientContact.client_id).filter(func.lower(ClientContact.email).in_(correos)).all()
    cuenta = Counter(c for (c,) in filas if c).most_common(1)
    return cuenta[0][0] if cuenta else None


def vincular(db: Session, reunion) -> dict:
    """Rellena `project_id`, `client_id` y `calendar_event_id` si faltan. No confirma."""
    hecho: dict = {}
    ev = _evento(db, reunion)
    if ev is not None and not reunion.calendar_event_id:
        reunion.calendar_event_id = ev.id
        hecho["calendar_event_id"] = ev.id
    if not reunion.project_id:
        proyecto = None
        if ev is not None and ev.project_id:
            from app.models.project import Project
            proyecto = db.get(Project, ev.project_id)
        proyecto = proyecto or _por_codigo(db, reunion.title or "") or _por_miembros(db, reunion)
        if proyecto is not None:
            reunion.project_id = proyecto.id
            hecho["project_id"] = proyecto.id
    if not reunion.client_id:
        cliente = _cliente_por_correos(db, reunion)
        if not cliente and reunion.project_id:
            from app.models.project import Project
            p = db.get(Project, reunion.project_id)
            cliente = getattr(p, "client_id", None)
        if cliente:
            reunion.client_id = cliente
            hecho["client_id"] = cliente
    if hecho:
        from app.services.reuniones.eventos import evento
        evento(db, reunion, "linked", None, hecho)
    return hecho
