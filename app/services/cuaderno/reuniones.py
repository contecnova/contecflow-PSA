"""Volcado de notas de reunión: el asistente de reuniones manda resumen y acciones a un cuaderno.

Solo una reunión que la persona puede ver (`reuniones.consultas.obtener`, 404
si no) y a una sección donde puede escribir (por defecto, la primera de su
primer cuaderno). Crea una página con fecha, asistentes, resumen, decisiones,
preguntas abiertas y las acciones como casillas (con fecha y responsable como
chip `@`); las tareas o tickets ya creados desde la reunión salen como chips `#`.
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session

from app.services.audit import audit_log
from app.services.formato_regional import IDIOMA_DE_RESPALDO


def _p(texto: str) -> dict:
    return {"type": "paragraph", "content": [{"type": "text", "text": texto}]} if texto else {"type": "paragraph"}


def _h(texto: str) -> dict:
    return {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": texto}]}


def _lista(textos: list) -> Optional[dict]:
    items = [{"type": "listItem", "content": [_p(str(t))]} for t in textos if str(t).strip()]
    return {"type": "bulletList", "content": items} if items else None


_TITULOS = {
    "es": ("Asistentes", "Resumen", "Decisiones", "Preguntas abiertas", "Acciones", "Reunión"),
    "en": ("Attendees", "Summary", "Decisions", "Open questions", "Actions", "Meeting"),
    "zh": ("参会人员", "摘要", "决定", "待解决问题", "行动项", "会议"),
}


def documento(reunion, idioma: str = "es") -> dict:
    from app.services.reuniones.consultas import _json
    t = _TITULOS.get(idioma, _TITULOS[IDIOMA_DE_RESPALDO])
    contenido: list = []
    fecha = reunion.meeting_date.strftime("%Y-%m-%d %H:%M") if reunion.meeting_date else ""
    contenido.append({"type": "paragraph", "content": [
        {"type": "text", "text": f"{t[5]}: {reunion.title or ''} {fecha}".strip(),
         "marks": [{"type": "link", "attrs": {"href": f"/meetings-ai?meeting={reunion.id}"}}]}]})
    asistentes = [p.name or p.email for p in getattr(reunion, "participantes", []) or [] if (p.name or p.email)]
    for titulo, lista in ((t[0], asistentes), (t[1], None), (t[2], _json(reunion.decisions) or []),
                          (t[3], _json(reunion.open_questions) or [])):
        if lista is None:
            if reunion.summary:
                contenido.extend([_h(titulo), _p(reunion.summary)])
            continue
        bloque = _lista(lista)
        if bloque:
            contenido.extend([_h(titulo), bloque])
    tareas = []
    for i, a in enumerate(reunion.actions or []):
        linea: list = [{"type": "text", "text": a.description}]
        if a.assignee_id:
            linea += [{"type": "text", "text": " "},
                      {"type": "mention", "attrs": {"id": a.assignee_id, "label": a.assignee_name or ""}}]
        if a.task_id:
            linea += [{"type": "text", "text": " "},
                      {"type": "objectRef", "attrs": {"type": "task", "id": a.task_id, "label": a.description[:80]}}]
        if a.ticket_id:
            linea += [{"type": "text", "text": " "},
                      {"type": "objectRef", "attrs": {"type": "ticket", "id": a.ticket_id, "label": a.description[:80]}}]
        tareas.append({"type": "taskItem", "attrs": {"checked": False, "bid": f"m{i}{a.id[:8]}",
                                                     "due": a.due_date.date().isoformat() if a.due_date else None},
                       "content": [{"type": "paragraph", "content": linea}]})
    if tareas:
        contenido.extend([_h(t[4]), {"type": "taskList", "content": tareas}])
    return {"type": "doc", "content": contenido or [{"type": "paragraph"}]}


def volcar(db: Session, usuario, meeting_id: str, section_id: Optional[str] = None) -> dict:
    """Crea la página con el acta en el cuaderno. No confirma."""
    from app.models.cuaderno import Notebook, NotebookSection
    from app.services.cuaderno import contenido as cont
    from app.services.cuaderno import servicio
    from app.services.formato_regional import idioma_de_salida
    from app.services.reuniones.consultas import obtener
    reunion = obtener(db, usuario, meeting_id)
    if not section_id:
        servicio.asegurar_inicial(db, usuario)
        nb = db.query(Notebook).filter(Notebook.owner_id == usuario.id, Notebook.deleted_at.is_(None),
                                       Notebook.is_quick.is_(False)).order_by(Notebook.sort_order).first() \
            or servicio.cuaderno_rapido(db, usuario)[0]
        s = db.query(NotebookSection).filter(NotebookSection.notebook_id == nb.id,
                                             NotebookSection.deleted_at.is_(None)).order_by(NotebookSection.sort_order).first()
        section_id = s.id if s else servicio.cuaderno_rapido(db, usuario)[1].id
    idioma = idioma_de_salida(db, user_id=usuario.id, org_id=getattr(usuario, "organization_id", None))
    doc = cont.validar(documento(reunion, idioma))
    titulo = f"{_TITULOS.get(idioma, _TITULOS[IDIOMA_DE_RESPALDO])[5]} · {reunion.title or ''}".strip()[:300]
    p = servicio.crear_pagina(db, usuario, section_id, {"title": titulo, "content": json.dumps(doc)})
    audit_log(db, usuario, "EXPORT", "meeting_to_notebook", reunion.id, reunion.title or "—",
              metadata={"page_id": p.id})
    return {"page_id": p.id, "section_id": p.section_id, "notebook_id": p.notebook_id, "title": p.title}
