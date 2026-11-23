"""
Epics service — business logic extracted from epics.py endpoint.
Covers: Wiki page serialisation, epic serialisation, mentions,
        block-to-text conversion, and NQL parsing.
"""
from __future__ import annotations
import logging

import json
import re
from typing import List

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.epics import (
    WikiPage, WikiSpace, WikiVersion, WikiComment,
    Epic, EpicTask, EpicDependency,
    SavedFilter, TaskStateSnapshot, Mention, ThreadedComment,
)
from app.models.epics import WikiTemplate as _WT
from app.models.project import Project
from app.models.task import Task
from app.models.service_desk import Ticket
from datetime import date, timedelta
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from sqlalchemy.orm import joinedload as _jl
from app.core import timeutil
from app.core.errores import ErrorDeDominio
from app.core.codigos_de_error import error


# ── Wiki page serialisers ─────────────────────────────────────────────────────

def serialize_page(p: WikiPage) -> dict:
    return {
        "id": p.id, "space_id": p.space_id, "parent_id": p.parent_id,
        "title": p.title, "slug": p.slug, "is_published": p.is_published,
        "sort_order": p.sort_order,
        "visibility": p.visibility or "team",
        "created_by": p.created_by, "updated_by": p.updated_by,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def serialize_page_full(p: WikiPage) -> dict:
    d = serialize_page(p)
    d["content"] = json.loads(p.content) if p.content else []
    d["content_text"] = p.content_text or ""
    return d


def build_page_tree(pages: list, parent_id=None) -> list:
    return [
        {**serialize_page(p), "children": build_page_tree(pages, p.id)}
        for p in pages if p.parent_id == parent_id
    ]


# ── Epic serialiser ───────────────────────────────────────────────────────────

def serialize_epic(e: Epic) -> dict:
    return {
        "id": e.id, "project_id": e.project_id, "title": e.title,
        "description": e.description, "color": e.color,
        "status": e.status, "priority": e.priority,
        "start_date": e.start_date, "end_date": e.end_date,
        "sort_order": e.sort_order,
        # Segunda auditoría 2026-11: solo los vínculos activos (desvincular una
        # tarea pone `is_active = False`; antes seguía contando).
        "task_count": sum(1 for et in (e.epic_tasks or []) if et.is_active),
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }


# ── Mentions ──────────────────────────────────────────────────────────────────

def extract_mentions(content: str) -> List[str]:
    # Mention format is strict email-only: @user@domain.tld
    return re.findall(r'@([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})', content or '')


def save_mentions(entity_type: str, entity_id: str, content: str, by_id: str, db: Session):
    for handle in extract_mentions(content):
        normalized = (handle or "").strip().lower()
        u = db.query(User).filter(func.lower(User.email) == normalized).first()
        if u and u.id != by_id:
            db.add(Mention(
                mentioned_user=u.id, mentioned_by=by_id,
                entity_type=entity_type, entity_id=entity_id,
                context_text=content[:300],
            ))


def _resolve_threaded_entity_id(entity_type: str, entity_ref: str, db: Session) -> str:
    ref = (entity_ref or "").strip()
    if not ref:
        raise error(400, "campo_obligatorio", detail="entity_id requerido", campo="entity_id")

    if entity_type == "task":
        task = db.query(Task).filter(or_(Task.id == ref, func.upper(Task.code) == ref.upper())).first()
        if not task:
            raise error(404, "no_encontrado", detail=f"Tarea '{entity_ref}' no encontrada", que="tarea")
        return task.id

    if entity_type == "ticket":
        ticket = db.query(Ticket).filter(or_(Ticket.id == ref, func.upper(Ticket.number) == ref.upper())).first()
        if not ticket:
            raise error(404, "no_encontrado", detail=f"Ticket '{entity_ref}' no encontrado", que="ticket")
        return ticket.id

    return ref


# ── Block → plain text ────────────────────────────────────────────────────────

def blocks_to_text(blocks_json: str) -> str:
    if not blocks_json:
        return ""
    try:
        blocks = json.loads(blocks_json)
        parts = []
        for b in blocks:
            if isinstance(b, dict) and b.get("content"):
                parts.append(str(b["content"]))
        return " ".join(parts)
    except Exception:
        logging.getLogger(__name__).warning("blocks_to_text: excepcion ignorada", exc_info=True)
        return ""


# ── NQL parser ────────────────────────────────────────────────────────────────

def parse_nql(nql: str) -> dict:
    # Segunda auditoría 2026-11: el valor era la clase `[^"'AND\s]+`, que (sin
    # distinguir mayúsculas) excluía las letras a, n y d: `status = done` daba
    # `do`. Ahora el valor va entre comillas (admite espacios) o es una palabra
    # sin espacios; el `AND` entre condiciones queda fuera porque lo separa el espacio.
    conds = {}
    for m in re.finditer(
            r"""(\w+)\s*(!=|=|\bIN\b|\bLIKE\b|>|<)\s*(?:"([^"]*)"|'([^']*)'|([^\s"']+))""",
            nql, re.IGNORECASE):
        valor = next(g for g in m.group(3, 4, 5) if g is not None)
        conds[m.group(1).lower()] = {"op": m.group(2).upper(), "val": valor.strip()}
    return conds


# ── Alcance por rol (segunda auditoría 2026-11) ───────────────────────────────
# La wiki y las épicas solo pedían sesión: un empleado o un subcontratado leía
# las de cualquier proyecto. Ahora siguen a su proyecto padre:
# - un espacio de proyecto, a quien ve el proyecto (`scope_projects_query`);
# - un espacio sin proyecto (de empresa), a la plantilla interna; al externo,
#   solo si es público (`is_public`);
# - una épica, a quien ve su proyecto (`politica_de_visibilidad.exigir_proyecto_visible`).
# Quien ve todos los proyectos de la empresa (gestión) no cambia.

def acotar_espacios(q, db, viewer):
    from sqlalchemy import and_
    from app.services import politica_de_visibilidad as _vis
    if not _vis.solo_proyectos_propios(viewer):
        return q
    from app.services.project_service import scope_projects_query
    visibles = scope_projects_query(db.query(Project.id), db, viewer).subquery()
    sin_proyecto = WikiSpace.project_id.is_(None)
    if _vis.es_externo(viewer):
        sin_proyecto = and_(sin_proyecto, WikiSpace.is_public == True)  # noqa: E712
    return q.filter(or_(WikiSpace.project_id.in_(db.query(visibles.c.id)), sin_proyecto))


def exigir_espacio_visible(db, viewer, space_id: str) -> None:
    if not acotar_espacios(db.query(WikiSpace.id), db, viewer).filter(WikiSpace.id == space_id).first():
        raise error(404, "no_encontrado", detail="Espacio no encontrado", que="espacio")


def exigir_pagina_visible(db, viewer, page_id: str) -> None:
    pagina = db.query(WikiPage.space_id).filter(WikiPage.id == page_id).first()
    if not pagina:
        raise error(404, "no_encontrado", detail="Página no encontrada", que="pagina")
    try:
        exigir_espacio_visible(db, viewer, pagina.space_id)
    except ErrorDeDominio:
        raise error(404, "no_encontrado", detail="Página no encontrada", que="pagina")


def exigir_epica_visible(db, viewer, epic_id: str) -> None:
    from app.services import politica_de_visibilidad as _vis
    epica = db.query(Epic.project_id).filter(Epic.id == epic_id).first()
    if not epica:
        raise error(404, "no_encontrado", detail="Épica no encontrada", que="epica")
    try:
        _vis.exigir_proyecto_visible(db, viewer, epica.project_id)
    except ErrorDeDominio:
        raise error(404, "no_encontrado", detail="Épica no encontrada", que="epica")


def acotar_plantillas(q, viewer):
    """Las plantillas de wiki son contenido de empresa, sin espacio: la misma regla
    que un espacio sin proyecto. La plantilla interna las ve todas; el externo,
    solo las del sistema (no son contenido de la empresa)."""
    from app.services import politica_de_visibilidad as _vis
    return q.filter(_WT.is_system == True) if _vis.es_externo(viewer) else q  # noqa: E712


def _ve_proyecto_de_hilo(db, viewer, entity_id: str) -> None:
    from app.services import politica_de_visibilidad as _vis
    if not db.query(Project.id).filter(Project.id == entity_id).first():
        raise error(404, "no_encontrado", detail="Proyecto no encontrado", que="proyecto")
    _vis.exigir_proyecto_visible(db, viewer, entity_id)


def _ve_tarea_de_hilo(db, viewer, entity_id: str) -> None:
    from app.services.task_service import get_task_record
    get_task_record(db, entity_id, viewer)


def _ve_ticket_de_hilo(db, viewer, entity_id: str) -> None:
    from app.services.service_desk.scoping import get_scoped_ticket_or_404
    get_scoped_ticket_or_404(db, viewer, entity_id)


#: Tipo de entidad de un hilo (`ThreadedComment.entity_type`) → la guarda de
#: lectura de esa entidad. Un tipo sin guarda, solo el administrador.
_LECTURA_DE_HILO = {
    "task": _ve_tarea_de_hilo,
    "ticket": _ve_ticket_de_hilo,
    "project": _ve_proyecto_de_hilo,
    "epic": lambda db, viewer, entity_id: exigir_epica_visible(db, viewer, entity_id),
    "wiki_page": lambda db, viewer, entity_id: exigir_pagina_visible(db, viewer, entity_id),
}


def exigir_lectura_de_hilo(db, viewer, entity_type: str, entity_id: str) -> str:
    """Segunda auditoría 2026-11: los comentarios en hilo (`/epics/comments`) solo
    pedían sesión. Ahora hay que poder leer la entidad dueña, con su alcance.
    Devuelve el id resuelto (una tarea o un ticket se pueden pedir por código)."""
    from app.models.user import UserRole
    resuelto = _resolve_threaded_entity_id(entity_type, entity_id, db)
    guarda = _LECTURA_DE_HILO.get(entity_type)
    if guarda is not None:
        guarda(db, viewer, resuelto)
    elif not (getattr(viewer, "is_superadmin", False) or viewer.role == UserRole.admin):
        raise error(404, "no_encontrado", detail="Entidad no encontrada", que="entidad")
    return resuelto


# ── Wiki Spaces ───────────────────────────────────────────────────────────────

def list_wiki_spaces(project_id, db, viewer) -> list:
    q = db.query(WikiSpace).options(joinedload(WikiSpace.pages)).filter(WikiSpace.is_active == True)
    q = acotar_espacios(q, db, viewer)
    if project_id:
        q = q.filter(WikiSpace.project_id == project_id)
    return [
        {"id": s.id, "name": s.name, "slug": s.slug,
         "description": s.description, "project_id": s.project_id,
         "is_public": s.is_public, "page_count": len([p for p in s.pages if p.is_active]),
         "created_at": s.created_at.isoformat() if s.created_at else None}
        for s in q.all()
    ]


def create_wiki_space(data: dict, created_by_id, db) -> dict:
    if db.query(WikiSpace).filter(WikiSpace.slug == data["slug"], WikiSpace.is_active == True).first():
        raise error(400, "espacio_ya_existe", detail=f"Ya existe un espacio con slug '{data['slug']}'", slug=data['slug'])
    s = WikiSpace(**data, created_by=created_by_id)
    db.add(s); db.commit(); db.refresh(s)
    return {"id": s.id, "name": s.name, "slug": s.slug, "project_id": s.project_id}


def update_wiki_space(space_id: str, data: dict, db) -> dict:
    s = db.query(WikiSpace).filter(WikiSpace.id == space_id, WikiSpace.is_active == True).first()
    if not s: raise error(404, "no_encontrado", detail="Espacio no encontrado", que="espacio")
    for k, v in data.items(): setattr(s, k, v)
    db.commit(); db.refresh(s)
    return {"id": s.id, "name": s.name, "slug": s.slug}


def delete_wiki_space(space_id: str, db) -> dict:
    s = db.query(WikiSpace).filter(WikiSpace.id == space_id, WikiSpace.is_active == True).first()
    if not s: raise error(404, "no_encontrado", detail="Espacio no encontrado", que="espacio")
    active_pages = db.query(func.count(WikiPage.id)).filter(
        WikiPage.space_id == space_id,
        WikiPage.is_active == True,
    ).scalar() or 0
    if active_pages > 0:
        raise error(400, "espacio_con_paginas", detail=f"No se puede eliminar: el espacio tiene {active_pages} pagina(s) activas", n=active_pages)
    s.is_active = False
    if s.slug:
        s.slug = f"{s.slug}__deleted__{s.id[:8]}"
    db.commit()
    return {"ok": True, "message": "Espacio wiki eliminado correctamente"}


# ── Wiki Pages ────────────────────────────────────────────────────────────────

def list_wiki_pages(space_id: str, db) -> list:
    pages = (db.query(WikiPage)
             .filter(WikiPage.space_id == space_id, WikiPage.is_active == True)
             .order_by(WikiPage.sort_order).all())
    return build_page_tree(pages)


def create_wiki_page(space_id: str, title: str, slug: str, content,
                     parent_id, is_published: bool, sort_order: int,
                     created_by_id, db) -> dict:
    if not db.query(WikiSpace).filter(WikiSpace.id == space_id, WikiSpace.is_active == True).first():
        raise error(404, "no_encontrado", detail="Espacio no encontrado", que="espacio")
    content_json = json.dumps(content or [])
    content_text = blocks_to_text(content_json)
    page = WikiPage(
        space_id=space_id, parent_id=parent_id,
        title=title, slug=slug,
        content=content_json, content_text=content_text,
        is_published=is_published, sort_order=sort_order,
        created_by=created_by_id, updated_by=created_by_id,
    )
    db.add(page); db.flush()
    db.add(WikiVersion(
        page_id=page.id, version_num=1,
        title=title, content=content_json, content_text=content_text,
        change_note="Página creada", created_by=created_by_id,
    ))
    db.commit(); db.refresh(page)
    return serialize_page_full(page)


def get_wiki_page(page_id: str, db) -> dict:
    page = db.query(WikiPage).filter(WikiPage.id == page_id, WikiPage.is_active == True).first()
    if not page: raise error(404, "no_encontrado", detail="Página no encontrada", que="pagina")
    return serialize_page_full(page)


def update_wiki_page(page_id: str, title: str, slug: str, content,
                     parent_id, sort_order: int, is_published: bool,
                     change_note: str, updated_by_id, db) -> dict:
    page = db.query(WikiPage).filter(WikiPage.id == page_id, WikiPage.is_active == True).first()
    if not page: raise error(404, "no_encontrado", detail="Página no encontrada", que="pagina")
    content_json = json.dumps(content or [])
    content_text = blocks_to_text(content_json)
    last_v = db.query(func.max(WikiVersion.version_num)).filter(
        WikiVersion.page_id == page_id).scalar() or 0
    db.add(WikiVersion(
        page_id=page_id, version_num=last_v + 1,
        title=title, content=content_json, content_text=content_text,
        change_note=change_note or "Actualización", created_by=updated_by_id,
    ))
    page.title        = title
    page.slug         = slug
    page.content      = content_json
    page.content_text = content_text
    page.parent_id    = parent_id
    page.sort_order   = sort_order
    page.is_published = is_published
    page.updated_by   = updated_by_id
    db.commit(); db.refresh(page)
    return serialize_page_full(page)


def cambiar_visibilidad_wiki_page(page_id: str, visibility: str, updated_by_id, db) -> dict:
    """Solo la visibilidad (team | portal | public). Auditoria 2026-11: la
    interfaz del portal la cambiaba con un PATCH a una ruta que no existia, y
    el PATCH completo exige titulo y slug y reescribe el contenido."""
    if visibility not in ("team", "portal", "public"):
        raise error(422, "visibilidad_no_valida", detail="Visibilidad no valida")
    page = db.query(WikiPage).filter(WikiPage.id == page_id, WikiPage.is_active == True).first()
    if not page: raise error(404, "no_encontrado", detail="Página no encontrada", que="pagina")
    page.visibility = visibility
    page.updated_by = updated_by_id
    db.commit(); db.refresh(page)
    return serialize_page(page)


def delete_wiki_page(page_id: str, db) -> dict:
    page = db.query(WikiPage).filter(WikiPage.id == page_id, WikiPage.is_active == True).first()
    if not page: raise error(404, "no_encontrado", detail="Página no encontrada", que="pagina")
    kids = db.query(WikiPage).filter(WikiPage.parent_id == page_id, WikiPage.is_active == True).count()
    if kids:
        raise error(400, "pagina_con_subpaginas", n=kids)
    page.is_active = False
    db.commit()
    return {"ok": True, "message": "Pagina wiki eliminada correctamente"}


def list_page_versions(page_id: str, db) -> list:
    vs = (db.query(WikiVersion)
          .filter(WikiVersion.page_id == page_id)
          .order_by(WikiVersion.version_num.desc()).all())
    return [{"id": v.id, "version_num": v.version_num, "title": v.title,
             "change_note": v.change_note, "created_by": v.created_by,
             "created_at": v.created_at.isoformat() if v.created_at else None}
            for v in vs]


def restore_wiki_version(page_id: str, version_num: int, restored_by_id, db) -> dict:
    ver = db.query(WikiVersion).filter(
        WikiVersion.page_id == page_id,
        WikiVersion.version_num == version_num).first()
    if not ver: raise error(404, "no_encontrado", detail="Versión no encontrada", que="version")
    page = db.query(WikiPage).filter(WikiPage.id == page_id).first()
    if not page: raise error(404, "no_encontrado", detail="Página no encontrada", que="pagina")
    last_v = db.query(func.max(WikiVersion.version_num)).filter(
        WikiVersion.page_id == page_id).scalar() or 0
    db.add(WikiVersion(
        page_id=page_id, version_num=last_v + 1,
        title=ver.title, content=ver.content, content_text=ver.content_text,
        change_note=f"Restaurado desde versión {version_num}", created_by=restored_by_id,
    ))
    page.title = ver.title; page.content = ver.content
    page.content_text = ver.content_text; page.updated_by = restored_by_id
    db.commit()
    return {"restored": True, "new_version": last_v + 1}


def search_wiki_pages(q: str, space_id, db, viewer) -> list:
    espacios = acotar_espacios(db.query(WikiSpace.id), db, viewer).subquery()
    query = db.query(WikiPage).filter(
        # M86: texto buscado escapado (`%` y `_` literales).
        or_(WikiPage.title.ilike(f"%{_esc(q)}%", escape="\\"), WikiPage.content_text.ilike(f"%{_esc(q)}%", escape="\\")),
        WikiPage.is_active == True,
        WikiPage.space_id.in_(db.query(espacios.c.id)),
    )
    if space_id:
        query = query.filter(WikiPage.space_id == space_id)
    return [{"id": p.id, "title": p.title, "space_id": p.space_id, "slug": p.slug,
             "updated_at": p.updated_at.isoformat() if p.updated_at else None}
            for p in query.limit(20).all()]


# ── Wiki Templates ────────────────────────────────────────────────────────────

def list_wiki_templates(db, viewer) -> list:
    ts = acotar_plantillas(db.query(_WT), viewer).order_by(_WT.is_system.desc(), _WT.name).all()
    return [{"id": t.id, "name": t.name, "description": t.description,
             "icon": t.icon, "is_system": t.is_system} for t in ts]


def create_wiki_template(name: str, description, icon, content, created_by_id, db) -> dict:
    t = _WT(name=name, description=description, icon=icon,
            content=json.dumps(content or []), created_by=created_by_id)
    db.add(t); db.commit(); db.refresh(t)
    return {"id": t.id, "name": t.name}


# ── Wiki Comments ─────────────────────────────────────────────────────────────

def list_wiki_page_comments(page_id: str, db) -> list:
    def _ser(c):
        return {"id": c.id, "content": c.content, "created_by": c.created_by,
                "is_resolved": c.is_resolved,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "replies": [_ser(r) for r in (c.replies or [])]}
    cs = (db.query(WikiComment)
          .filter(WikiComment.page_id == page_id, WikiComment.parent_id == None)
          .options(_jl(WikiComment.replies))
          .order_by(WikiComment.created_at).all())
    return [_ser(c) for c in cs]


def add_wiki_page_comment(page_id: str, content: str, parent_id, created_by_id, db) -> dict:
    c = WikiComment(page_id=page_id, content=content, parent_id=parent_id, created_by=created_by_id)
    db.add(c); db.flush()
    save_mentions("wiki_comment", c.id, content, created_by_id, db)
    db.commit(); db.refresh(c)
    return {"id": c.id, "content": c.content}


def resolve_wiki_page_comment(comment_id: str, db) -> dict:
    c = db.query(WikiComment).filter(WikiComment.id == comment_id).first()
    if not c: raise error(404, "no_encontrado", detail="Comentario no encontrado", que="comentario")
    c.is_resolved = True; db.commit()
    return {"resolved": True}


# ── Epics CRUD ────────────────────────────────────────────────────────────────

def list_epics_records(project_id: str, db) -> list:
    epics = (db.query(Epic)
             .options(_jl(Epic.epic_tasks))
             .filter(Epic.project_id == project_id, Epic.is_active == True)
             .order_by(Epic.sort_order, Epic.start_date).all())
    return [serialize_epic(e) for e in epics]


def create_epic_record(data: dict, project_id: str, created_by_id, db) -> dict:
    if not db.query(Project).filter(Project.id == project_id).first():
        raise error(404, "no_encontrado", detail="Proyecto no encontrado", que="proyecto")
    e = Epic(**data, project_id=project_id, created_by=created_by_id)
    db.add(e); db.commit(); db.refresh(e)
    return serialize_epic(e)


def get_epic_record(epic_id: str, db) -> dict:
    e = (db.query(Epic)
         .options(_jl(Epic.epic_tasks), _jl(Epic.dependencies))
         .filter(Epic.id == epic_id, Epic.is_active == True).first())
    if not e: raise error(404, "no_encontrado", detail="Épica no encontrada", que="epica")
    d = serialize_epic(e)
    d["tasks"] = []
    for et in (e.epic_tasks or []):
        if not et.is_active:
            continue
        t = db.query(Task).filter(Task.id == et.task_id).first()
        if t:
            # Auditoria 2026-08: aqui habia `t.assigned_to_user_id`, y esa es
            # la columna de `Ticket`, no de `Task` —en `Task` se llama
            # `assignee_id`—. Reventaba con `AttributeError`, asi que el detalle
            # de un epic **no se podia leer** en cuanto tenia una tarea. La
            # clave de la respuesta se conserva para no cambiar el contrato.
            d["tasks"].append({"id": t.id, "title": t.title, "status": t.status,
                               "story_points": t.story_points,
                               "assigned_to_user_id": t.assignee_id})
    d["dependencies"] = [dep.depends_on_id for dep in (e.dependencies or []) if dep.is_active]
    return d


def update_epic_record(epic_id: str, data: dict, db) -> dict:
    e = db.query(Epic).filter(Epic.id == epic_id, Epic.is_active == True).first()
    if not e: raise error(404, "no_encontrado", detail="Épica no encontrada", que="epica")
    for k, v in data.items(): setattr(e, k, v)
    db.commit(); db.refresh(e)
    return serialize_epic(e)


def delete_epic_record(epic_id: str, db) -> dict:
    e = db.query(Epic).filter(Epic.id == epic_id, Epic.is_active == True).first()
    if not e: raise error(404, "no_encontrado", detail="Épica no encontrada", que="epica")
    active_tasks = db.query(func.count(EpicTask.id)).filter(EpicTask.epic_id == epic_id, EpicTask.is_active == True).scalar() or 0
    active_deps = db.query(func.count(EpicDependency.id)).filter(EpicDependency.epic_id == epic_id, EpicDependency.is_active == True).scalar() or 0
    if active_tasks or active_deps:
        raise error(400, "epica_con_tareas", detail=f"No se puede eliminar: tareas={active_tasks}, dependencias={active_deps}", tareas=active_tasks, dependencias=active_deps)
    e.is_active = False
    db.commit()
    return {"ok": True, "message": "Epica eliminada correctamente"}


def add_task_to_epic_record(epic_id: str, task_id: str, db) -> dict:
    if not db.query(Epic).filter(Epic.id == epic_id, Epic.is_active == True).first():
        raise error(404, "no_encontrado", detail="Épica no encontrada", que="epica")
    if not db.query(Task).filter(Task.id == task_id).first():
        raise error(404, "no_encontrado", detail="Tarea no encontrada", que="tarea")
    if not db.query(EpicTask).filter(EpicTask.epic_id == epic_id, EpicTask.task_id == task_id, EpicTask.is_active == True).first():
        db.add(EpicTask(epic_id=epic_id, task_id=task_id)); db.commit()
    return {"linked": True}


def remove_task_from_epic_record(epic_id: str, task_id: str, db) -> dict:
    et = db.query(EpicTask).filter(
        EpicTask.epic_id == epic_id,
        EpicTask.task_id == task_id,
        EpicTask.is_active == True,
    ).first()
    if et:
        et.is_active = False
        db.commit()
    return {"ok": True, "message": "Tarea desvinculada correctamente"}


def add_epic_dependency(epic_id: str, depends_on_id: str, db) -> dict:
    if epic_id == depends_on_id:
        raise error(400, "epica_depende_de_si_misma")
    if not db.query(EpicDependency).filter(
        EpicDependency.epic_id == epic_id,
        EpicDependency.depends_on_id == depends_on_id,
        EpicDependency.is_active == True,
    ).first():
        db.add(EpicDependency(epic_id=epic_id, depends_on_id=depends_on_id)); db.commit()
    return {"linked": True}


def remove_epic_dependency(epic_id: str, depends_on_id: str, db) -> dict:
    dep = db.query(EpicDependency).filter(
        EpicDependency.epic_id == epic_id,
        EpicDependency.depends_on_id == depends_on_id,
        EpicDependency.is_active == True,
    ).first()
    if dep:
        dep.is_active = False
        db.commit()
    return {"ok": True, "message": "Dependencia eliminada correctamente"}


def get_roadmap_data(project_id: str, db) -> dict:
    epics = (db.query(Epic)
             .options(_jl(Epic.epic_tasks), _jl(Epic.dependencies))
             .filter(Epic.project_id == project_id, Epic.is_active == True)
             .order_by(Epic.start_date, Epic.sort_order).all())
    items = []
    for e in epics:
        total = sum(1 for et in (e.epic_tasks or []) if et.is_active)
        done  = sum(
            1 for et in (e.epic_tasks or []) if et.is_active
            for t in [db.query(Task).filter(Task.id == et.task_id).first()]
            if t and t.status == "done"
        )
        items.append({
            **serialize_epic(e),
            "done_tasks":   done,
            "total_tasks":  total,
            "progress":     round(done / total * 100) if total else 0,
            "dependencies": [d.depends_on_id for d in (e.dependencies or []) if d.is_active],
        })
    return {"project_id": project_id, "epics": items}


# ── NQL ───────────────────────────────────────────────────────────────────────

#: Qué se puede buscar con NQL y cómo. Por cada entidad: el modelo, un filtro
#: base opcional, el mapa de condición NQL a columna, y cómo se serializa.
#:
#: Auditoría 2026-09 (hallazgo 18): eran tres bloques con la misma forma
#: —construir consulta, aplicar condiciones, serializar— escritos a mano.
#: Declararlos deja claro de un vistazo **qué campos se pueden buscar en cada
#: entidad**, que es justo lo que alguien necesita saber para escribir una
#: consulta, y estaba repartido entre veinte líneas de `if`.
#:
#: `ilike` marca las condiciones que buscan por texto parcial; las demás son
#: igualdad exacta.
def _nql_tareas_visibles(db, viewer):
    from app.services.tasks.queries import build_task_list_query
    return build_task_list_query(db, viewer)


def _nql_proyectos_visibles(db, viewer):
    from app.services.project_service import scope_projects_query
    return scope_projects_query(db.query(Project), db, viewer)


def _nql_epicas_visibles(db, viewer):
    proyectos = _nql_proyectos_visibles(db, viewer).with_entities(Project.id).subquery()
    return db.query(Epic).filter(Epic.project_id.in_(db.query(proyectos.c.id)))


#: `consulta`: la consulta de partida, ya acotada a lo que `viewer` ve (segunda
#: auditoría 2026-11: antes partía de la tabla entera de la empresa).
_ENTIDADES_NQL: dict[str, dict] = {
    "task": {
        "consulta": _nql_tareas_visibles,
        "base": None,
        "campos": {
            "status":   (lambda: Task.status, False),
            "priority": (lambda: Task.priority, False),
            "project":  (lambda: Task.project_id, False),
            "title":    (lambda: Task.title, True),
        },
        "serializar": lambda t: {
            "id": t.id, "title": t.title, "status": t.status,
            "priority": t.priority, "project_id": t.project_id,
        },
    },
    "project": {
        "consulta": _nql_proyectos_visibles,
        "base": None,
        "campos": {
            "status": (lambda: Project.status, False),
            "name":   (lambda: Project.name, True),
        },
        "serializar": lambda p: {"id": p.id, "name": p.name, "status": p.status},
    },
    "epic": {
        "consulta": _nql_epicas_visibles,
        "base": lambda: Epic.is_active == True,  # noqa: E712
        "campos": {
            "status":   (lambda: Epic.status, False),
            "priority": (lambda: Epic.priority, False),
            "title":    (lambda: Epic.title, True),
        },
        "serializar": serialize_epic,
    },
}


def _esc(texto: str) -> str:
    from app.services.service_desk.ticket_query_service import escapar_like
    return escapar_like(texto or "")


def _condicion_nql(col, op: str, valor: str, parcial: bool):
    """M86 (auditoría 22-11-2026): el operador se aplica (antes `!=`, `IN`, `>` y
    `<` se trataban todos como `=` o contiene) y el texto de LIKE va escapado.

    `=`: igual (o contiene, en campos de texto libre); `!=`: distinto (o no
    contiene); `IN`: uno de la lista separada por comas; `LIKE`: contiene;
    `>`/`<`: orden (texto o número, como compare la base).
    """
    from app.services.service_desk.ticket_query_service import escapar_like
    patron = f"%{escapar_like(valor)}%"
    if op == "IN":
        return col.in_([v.strip() for v in valor.split(",") if v.strip()])
    if op == "LIKE" or (op == "=" and parcial):
        return col.ilike(patron, escape="\\")
    if op == "!=":
        return ~col.ilike(patron, escape="\\") if parcial else col != valor
    if op == ">":
        return col > valor
    if op == "<":
        return col < valor
    return col == valor


def execute_nql_search(entity_type: str, query: str, limit: int, db, viewer) -> dict:
    """Busca con una consulta NQL sobre una de las entidades declaradas."""
    spec = _ENTIDADES_NQL.get(entity_type)
    if spec is None:
        raise error(400, "tipo_de_entidad_no_soportado", detail=f"entity_type '{entity_type}' no soportado. "
            f"Usa: {', '.join(sorted(_ENTIDADES_NQL))}", tipo=entity_type, opciones=', '.join(sorted(_ENTIDADES_NQL)))

    condiciones = parse_nql(query)
    q = spec["consulta"](db, viewer)
    if spec["base"]:
        q = q.filter(spec["base"]())

    for nombre, (columna, parcial) in spec["campos"].items():
        if nombre not in condiciones:
            continue
        q = q.filter(_condicion_nql(columna(), condiciones[nombre]["op"], condiciones[nombre]["val"], parcial))

    resultados = q.limit(limit).all()
    return {
        "entity_type": entity_type,
        "count": len(resultados),
        "results": [spec["serializar"](r) for r in resultados],
    }


def list_saved_filters(entity_type, user_id, db) -> list:
    q = db.query(SavedFilter).filter(
        or_(SavedFilter.created_by == user_id, SavedFilter.is_shared == True),
        SavedFilter.is_active == True,
    )
    if entity_type:
        q = q.filter(SavedFilter.entity_type == entity_type)
    return [{"id": f.id, "name": f.name, "entity_type": f.entity_type,
             "nql_query": f.nql_query, "is_shared": f.is_shared}
            for f in q.all()]


def create_saved_filter(data: dict, created_by_id, db) -> dict:
    f = SavedFilter(**data, created_by=created_by_id)
    db.add(f); db.commit(); db.refresh(f)
    return {"id": f.id, "name": f.name, "nql_query": f.nql_query}


def delete_saved_filter(filter_id: str, user_id, db) -> dict:
    f = db.query(SavedFilter).filter(
        SavedFilter.id == filter_id,
        SavedFilter.created_by == user_id,
        SavedFilter.is_active == True,
    ).first()
    if not f: raise error(404, "no_encontrado", detail="Filtro no encontrado", que="filtro")
    f.is_active = False
    db.commit()
    return {"ok": True, "message": "Filtro eliminado correctamente"}


# ── CFD (Cumulative Flow Diagram) ─────────────────────────────────────────────

def take_cfd_snapshot(project_id: str, sprint_id, db) -> dict:
    today = timeutil.today().isoformat()
    db.query(TaskStateSnapshot).filter(
        TaskStateSnapshot.project_id == project_id,
        TaskStateSnapshot.snap_date  == today,
    ).delete()
    counts = (db.query(Task.status, func.count(Task.id))
              .filter(Task.project_id == project_id)
              .group_by(Task.status).all())
    for status, cnt in counts:
        db.add(TaskStateSnapshot(
            project_id=project_id, sprint_id=sprint_id,
            snap_date=today, status=status, count=cnt))
    db.commit()
    return {"date": today, "states": len(counts)}


def get_cfd_data(project_id: str, sprint_id, p, db) -> dict:
    """Flujo acumulado del proyecto en el periodo ``p`` (periodo libre, 16-11-2026).

    Las fotos son diarias (``snap_date`` ``YYYY-MM-DD``) y cuentan existencias
    (tareas en cada estado), no sucesos: al agrupar por semana o mes cada tramo
    toma la **última foto** del tramo, no la suma. No se rellenan tramos sin
    foto con ceros (pintaría una caída que no ha ocurrido): solo salen los
    tramos con datos, cada uno con su ``t`` ISO y su ``clave``.
    """
    q = db.query(TaskStateSnapshot).filter(
        TaskStateSnapshot.project_id == project_id,
        TaskStateSnapshot.snap_date >= p.fecha_desde.isoformat(),
        TaskStateSnapshot.snap_date <= p.fecha_hasta.isoformat())
    if sprint_id:
        q = q.filter(TaskStateSnapshot.sprint_id == sprint_id)
    snaps = q.order_by(TaskStateSnapshot.snap_date).all()
    by_date: dict = {}
    all_statuses: set = set()
    for s in snaps:
        by_date.setdefault(s.snap_date, {})[s.status] = s.count
        all_statuses.add(s.status)
    statuses = sorted(all_statuses)
    # Última foto de cada tramo (las fechas van ordenadas: la última pisa).
    por_tramo: dict = {}
    for d in sorted(by_date):
        k = p.clave(date.fromisoformat(d))
        if k is not None:
            por_tramo[k] = (d, by_date[d])
    data = [{"t": p.instante_de_clave(k), "clave": k, "date": d, **{st: 0 for st in statuses}, **counts}
            for k, (d, counts) in sorted(por_tramo.items())]
    return {"project_id": project_id, "statuses": statuses, "data": data, "periodo": p.a_dict()}


# ── Mentions ──────────────────────────────────────────────────────────────────

def get_my_mentions(user_id, only_unread: bool, db) -> list:
    q = db.query(Mention).filter(Mention.mentioned_user == user_id)
    if only_unread:
        q = q.filter(Mention.is_read == False)
    mentions = q.order_by(Mention.created_at.desc()).limit(50).all()
    actor_ids = {m.mentioned_by for m in mentions if m.mentioned_by}
    actor_map = {}
    if actor_ids:
        users = db.query(User).filter(User.id.in_(list(actor_ids))).all()
        actor_map = {
            u.id: {
                "email": (u.email or "").lower() if u.email else None,
                "name": u.full_name or u.username,
            }
            for u in users
        }
    return [{"id": m.id, "entity_type": m.entity_type, "entity_id": m.entity_id,
             "context_text": m.context_text, "is_read": m.is_read,
             "created_at": m.created_at.isoformat() if m.created_at else None,
             "mentioned_by_email": (actor_map.get(m.mentioned_by) or {}).get("email"),
             "mentioned_by_name": (actor_map.get(m.mentioned_by) or {}).get("name")}
            for m in mentions]


def mark_all_mentions_read(user_id, db) -> dict:
    updated = db.query(Mention).filter(
        Mention.mentioned_user == user_id, Mention.is_read == False,
    ).update({"is_read": True})
    db.commit()
    return {"marked_read": updated}


# ── Threaded Comments ─────────────────────────────────────────────────────────

def list_threaded_comments(entity_type: str, entity_id: str, db) -> list:
    resolved_entity_id = _resolve_threaded_entity_id(entity_type, entity_id, db)

    def _collect_user_ids(nodes) -> set[str]:
        ids = set()
        for n in nodes:
            if n.created_by:
                ids.add(n.created_by)
            for r in (n.replies or []):
                if r.created_by:
                    ids.add(r.created_by)
        return ids

    root = (db.query(ThreadedComment)
            .filter(ThreadedComment.entity_type == entity_type,
            ThreadedComment.entity_id   == resolved_entity_id,
                ThreadedComment.parent_id   == None,
                ThreadedComment.is_active   == True)
            .options(_jl(ThreadedComment.replies))
            .order_by(ThreadedComment.created_at).all())

    user_ids = _collect_user_ids(root)
    users_by_id = {}
    if user_ids:
        users = db.query(User).filter(User.id.in_(list(user_ids))).all()
        users_by_id = {
            u.id: {
                "email": (u.email or "").lower() if u.email else None,
                "name": u.full_name or u.username,
            }
            for u in users
        }

    def _ser(c):
        author = users_by_id.get(c.created_by) or {}
        return {"id": c.id, "content": c.content, "created_by": c.created_by,
                "created_by_email": author.get("email"),
                "created_by_name": author.get("name"),
                "is_resolved": c.is_resolved,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            "replies": [_ser(r) for r in (c.replies or []) if r.is_active]}

    return [_ser(c) for c in root]


def add_threaded_comment(entity_type: str, entity_id: str, content: str,
                          parent_id, created_by_id, db) -> dict:
    resolved_entity_id = _resolve_threaded_entity_id(entity_type, entity_id, db)

    c = ThreadedComment(entity_type=entity_type, entity_id=resolved_entity_id,
                        content=content, parent_id=parent_id, created_by=created_by_id)
    db.add(c); db.flush()
    save_mentions(entity_type, resolved_entity_id, content, created_by_id, db)
    db.commit(); db.refresh(c)
    return {"id": c.id, "content": c.content, "entity_type": entity_type,
        "entity_id": resolved_entity_id, "parent_id": c.parent_id}


def edit_threaded_comment(comment_id: str, content: str, user_id, db) -> dict:
    c = db.query(ThreadedComment).filter(
        ThreadedComment.id == comment_id,
        ThreadedComment.created_by == user_id,
        ThreadedComment.is_active == True,
    ).first()
    if not c: raise error(404, "no_encontrado", detail="Comentario no encontrado", que="comentario")
    c.content = content; db.commit()
    return {"id": c.id, "content": c.content}


def resolve_threaded_comment(comment_id: str, db) -> dict:
    c = db.query(ThreadedComment).filter(ThreadedComment.id == comment_id, ThreadedComment.is_active == True).first()
    if not c: raise error(404, "no_encontrado", detail="Comentario no encontrado", que="comentario")
    c.is_resolved = True; db.commit()
    return {"resolved": True}


def delete_threaded_comment(comment_id: str, user_id, db) -> dict:
    c = db.query(ThreadedComment).filter(
        ThreadedComment.id == comment_id,
        ThreadedComment.created_by == user_id,
        ThreadedComment.is_active == True,
    ).first()
    if not c: raise error(404, "no_encontrado", detail="Comentario no encontrado", que="comentario")
    if [r for r in (c.replies or []) if r.is_active]:
        raise error(400, "comentario_con_respuestas")
    c.is_active = False
    db.commit()
    return {"ok": True, "message": "Comentario eliminado correctamente"}
