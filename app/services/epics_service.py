"""
Epics service — business logic extracted from epics.py endpoint.
Covers: Wiki page serialisation, epic serialisation, mentions,
        block-to-text conversion, and NQL parsing.
"""
from __future__ import annotations

import json
import re
from typing import List

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.epics import (
    WikiPage, WikiSpace, WikiVersion, WikiTemplate, WikiComment,
    Epic, EpicTask, EpicDependency,
    SavedFilter, TaskStateSnapshot, Mention, ThreadedComment,
)
from app.models.epics import WikiTemplate as _WT
from app.models.project import Project
from app.models.task import Task
from datetime import date
from datetime import date, timedelta
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from sqlalchemy.orm import joinedload as _jl


# ── Wiki page serialisers ─────────────────────────────────────────────────────

def serialize_page(p: WikiPage) -> dict:
    return {
        "id": p.id, "space_id": p.space_id, "parent_id": p.parent_id,
        "title": p.title, "slug": p.slug, "is_published": p.is_published,
        "sort_order": p.sort_order,
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
        "task_count": len(e.epic_tasks or []),
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }


# ── Mentions ──────────────────────────────────────────────────────────────────

def extract_mentions(content: str) -> List[str]:
    return re.findall(r'@([\w\-\.]+)', content or '')


def save_mentions(entity_type: str, entity_id: str, content: str, by_id: str, db: Session):
    for handle in extract_mentions(content):
        u = db.query(User).filter(
            or_(User.username == handle, User.email == handle)
        ).first()
        if u and u.id != by_id:
            db.add(Mention(
                mentioned_user=u.id, mentioned_by=by_id,
                entity_type=entity_type, entity_id=entity_id,
                context_text=content[:300],
            ))


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
        return ""


# ── NQL parser ────────────────────────────────────────────────────────────────

def parse_nql(nql: str) -> dict:
    conds = {}
    for m in re.finditer(
            r'(\w+)\s*(!=|=|IN|LIKE|>|<)\s*["\']?([^"\'AND\s]+)["\']?',
            nql, re.IGNORECASE):
        conds[m.group(1).lower()] = {"op": m.group(2).upper(), "val": m.group(3).strip()}
    return conds


# ── Wiki Spaces ───────────────────────────────────────────────────────────────

def list_wiki_spaces(project_id, db) -> list:
    q = db.query(WikiSpace).options(joinedload(WikiSpace.pages))
    if project_id:
        q = q.filter(WikiSpace.project_id == project_id)
    return [
        {"id": s.id, "name": s.name, "slug": s.slug,
         "description": s.description, "project_id": s.project_id,
         "is_public": s.is_public, "page_count": len(s.pages),
         "created_at": s.created_at.isoformat() if s.created_at else None}
        for s in q.all()
    ]


def create_wiki_space(data: dict, created_by_id, db) -> dict:
    if db.query(WikiSpace).filter(WikiSpace.slug == data["slug"]).first():
        raise HTTPException(400, f"Ya existe un espacio con slug '{data['slug']}'")
    s = WikiSpace(**data, created_by=created_by_id)
    db.add(s); db.commit(); db.refresh(s)
    return {"id": s.id, "name": s.name, "slug": s.slug, "project_id": s.project_id}


def update_wiki_space(space_id: str, data: dict, db) -> dict:
    s = db.query(WikiSpace).filter(WikiSpace.id == space_id).first()
    if not s: raise HTTPException(404, "Espacio no encontrado")
    for k, v in data.items(): setattr(s, k, v)
    db.commit(); db.refresh(s)
    return {"id": s.id, "name": s.name, "slug": s.slug}


def delete_wiki_space(space_id: str, db) -> dict:
    s = db.query(WikiSpace).filter(WikiSpace.id == space_id).first()
    if not s: raise HTTPException(404, "Espacio no encontrado")
    db.delete(s); db.commit()
    return {"deleted": True}


# ── Wiki Pages ────────────────────────────────────────────────────────────────

def list_wiki_pages(space_id: str, db) -> list:
    pages = (db.query(WikiPage)
             .filter(WikiPage.space_id == space_id)
             .order_by(WikiPage.sort_order).all())
    return build_page_tree(pages)


def create_wiki_page(space_id: str, title: str, slug: str, content,
                     parent_id, is_published: bool, sort_order: int,
                     created_by_id, db) -> dict:
    if not db.query(WikiSpace).filter(WikiSpace.id == space_id).first():
        raise HTTPException(404, "Espacio no encontrado")
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
    page = db.query(WikiPage).filter(WikiPage.id == page_id).first()
    if not page: raise HTTPException(404, "Página no encontrada")
    return serialize_page_full(page)


def update_wiki_page(page_id: str, title: str, slug: str, content,
                     parent_id, sort_order: int, is_published: bool,
                     change_note: str, updated_by_id, db) -> dict:
    page = db.query(WikiPage).filter(WikiPage.id == page_id).first()
    if not page: raise HTTPException(404, "Página no encontrada")
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


def delete_wiki_page(page_id: str, db) -> dict:
    page = db.query(WikiPage).filter(WikiPage.id == page_id).first()
    if not page: raise HTTPException(404, "Página no encontrada")
    kids = db.query(WikiPage).filter(WikiPage.parent_id == page_id).count()
    if kids:
        raise HTTPException(400, f"Esta página tiene {kids} subpáginas — elimínalas primero")
    db.delete(page); db.commit()
    return {"deleted": True}


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
    if not ver: raise HTTPException(404, "Versión no encontrada")
    page = db.query(WikiPage).filter(WikiPage.id == page_id).first()
    if not page: raise HTTPException(404, "Página no encontrada")
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


def search_wiki_pages(q: str, space_id, db) -> list:
    query = db.query(WikiPage).filter(
        or_(WikiPage.title.ilike(f"%{q}%"), WikiPage.content_text.ilike(f"%{q}%")))
    if space_id:
        query = query.filter(WikiPage.space_id == space_id)
    return [{"id": p.id, "title": p.title, "space_id": p.space_id, "slug": p.slug,
             "updated_at": p.updated_at.isoformat() if p.updated_at else None}
            for p in query.limit(20).all()]


# ── Wiki Templates ────────────────────────────────────────────────────────────

def list_wiki_templates(db) -> list:
    ts = db.query(_WT).order_by(_WT.is_system.desc(), _WT.name).all()
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
    if not c: raise HTTPException(404, "Comentario no encontrado")
    c.is_resolved = True; db.commit()
    return {"resolved": True}


# ── Epics CRUD ────────────────────────────────────────────────────────────────

def list_epics_records(project_id: str, db) -> list:
    epics = (db.query(Epic)
             .options(_jl(Epic.epic_tasks))
             .filter(Epic.project_id == project_id)
             .order_by(Epic.sort_order, Epic.start_date).all())
    return [serialize_epic(e) for e in epics]


def create_epic_record(data: dict, project_id: str, created_by_id, db) -> dict:
    if not db.query(Project).filter(Project.id == project_id).first():
        raise HTTPException(404, "Proyecto no encontrado")
    e = Epic(**data, project_id=project_id, created_by=created_by_id)
    db.add(e); db.commit(); db.refresh(e)
    return serialize_epic(e)


def get_epic_record(epic_id: str, db) -> dict:
    e = (db.query(Epic)
         .options(_jl(Epic.epic_tasks), _jl(Epic.dependencies))
         .filter(Epic.id == epic_id).first())
    if not e: raise HTTPException(404, "Épica no encontrada")
    d = serialize_epic(e)
    d["tasks"] = []
    for et in (e.epic_tasks or []):
        t = db.query(Task).filter(Task.id == et.task_id).first()
        if t:
            d["tasks"].append({"id": t.id, "title": t.title, "status": t.status,
                               "story_points": t.story_points,
                               "assigned_to_user_id": t.assigned_to_user_id})
    d["dependencies"] = [dep.depends_on_id for dep in (e.dependencies or [])]
    return d


def update_epic_record(epic_id: str, data: dict, db) -> dict:
    e = db.query(Epic).filter(Epic.id == epic_id).first()
    if not e: raise HTTPException(404, "Épica no encontrada")
    for k, v in data.items(): setattr(e, k, v)
    db.commit(); db.refresh(e)
    return serialize_epic(e)


def delete_epic_record(epic_id: str, db) -> dict:
    e = db.query(Epic).filter(Epic.id == epic_id).first()
    if not e: raise HTTPException(404, "Épica no encontrada")
    db.delete(e); db.commit()
    return {"deleted": True}


def add_task_to_epic_record(epic_id: str, task_id: str, db) -> dict:
    if not db.query(Epic).filter(Epic.id == epic_id).first():
        raise HTTPException(404, "Épica no encontrada")
    if not db.query(Task).filter(Task.id == task_id).first():
        raise HTTPException(404, "Tarea no encontrada")
    if not db.query(EpicTask).filter(EpicTask.epic_id == epic_id, EpicTask.task_id == task_id).first():
        db.add(EpicTask(epic_id=epic_id, task_id=task_id)); db.commit()
    return {"linked": True}


def remove_task_from_epic_record(epic_id: str, task_id: str, db) -> dict:
    et = db.query(EpicTask).filter(EpicTask.epic_id == epic_id, EpicTask.task_id == task_id).first()
    if et: db.delete(et); db.commit()
    return {"unlinked": True}


def add_epic_dependency(epic_id: str, depends_on_id: str, db) -> dict:
    if epic_id == depends_on_id:
        raise HTTPException(400, "Una épica no puede depender de sí misma")
    if not db.query(EpicDependency).filter(
            EpicDependency.epic_id == epic_id,
            EpicDependency.depends_on_id == depends_on_id).first():
        db.add(EpicDependency(epic_id=epic_id, depends_on_id=depends_on_id)); db.commit()
    return {"linked": True}


def remove_epic_dependency(epic_id: str, depends_on_id: str, db) -> dict:
    dep = db.query(EpicDependency).filter(
        EpicDependency.epic_id == epic_id,
        EpicDependency.depends_on_id == depends_on_id).first()
    if dep: db.delete(dep); db.commit()
    return {"unlinked": True}


def get_roadmap_data(project_id: str, db) -> dict:
    epics = (db.query(Epic)
             .options(_jl(Epic.epic_tasks), _jl(Epic.dependencies))
             .filter(Epic.project_id == project_id)
             .order_by(Epic.start_date, Epic.sort_order).all())
    items = []
    for e in epics:
        total = len(e.epic_tasks or [])
        done  = sum(
            1 for et in (e.epic_tasks or [])
            for t in [db.query(Task).filter(Task.id == et.task_id).first()]
            if t and t.status == "done"
        )
        items.append({
            **serialize_epic(e),
            "done_tasks":   done,
            "total_tasks":  total,
            "progress":     round(done / total * 100) if total else 0,
            "dependencies": [d.depends_on_id for d in (e.dependencies or [])],
        })
    return {"project_id": project_id, "epics": items}


# ── NQL ───────────────────────────────────────────────────────────────────────

def execute_nql_search(entity_type: str, query: str, limit: int, db) -> dict:
    conds = parse_nql(query)

    if entity_type == "task":
        q = db.query(Task)
        if "status"   in conds: q = q.filter(Task.status    == conds["status"]["val"])
        if "priority" in conds: q = q.filter(Task.priority  == conds["priority"]["val"])
        if "project"  in conds: q = q.filter(Task.project_id== conds["project"]["val"])
        if "title"    in conds: q = q.filter(Task.title.ilike(f"%{conds['title']['val']}%"))
        results = q.limit(limit).all()
        return {"entity_type": "task", "count": len(results),
                "results": [{"id": t.id, "title": t.title, "status": t.status,
                             "priority": t.priority, "project_id": t.project_id}
                            for t in results]}

    if entity_type == "project":
        q = db.query(Project)
        if "status" in conds: q = q.filter(Project.status == conds["status"]["val"])
        if "name"   in conds: q = q.filter(Project.name.ilike(f"%{conds['name']['val']}%"))
        results = q.limit(limit).all()
        return {"entity_type": "project", "count": len(results),
                "results": [{"id": r.id, "name": r.name, "status": r.status} for r in results]}

    if entity_type == "epic":
        q = db.query(Epic)
        if "status"   in conds: q = q.filter(Epic.status   == conds["status"]["val"])
        if "priority" in conds: q = q.filter(Epic.priority == conds["priority"]["val"])
        if "title"    in conds: q = q.filter(Epic.title.ilike(f"%{conds['title']['val']}%"))
        results = q.limit(limit).all()
        return {"entity_type": "epic", "count": len(results),
                "results": [serialize_epic(e) for e in results]}

    raise HTTPException(400, f"entity_type '{entity_type}' no soportado. Usa: task, project, epic")


def list_saved_filters(entity_type, user_id, db) -> list:
    q = db.query(SavedFilter).filter(
        or_(SavedFilter.created_by == user_id, SavedFilter.is_shared == True))
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
        SavedFilter.id == filter_id, SavedFilter.created_by == user_id).first()
    if not f: raise HTTPException(404, "Filtro no encontrado")
    db.delete(f); db.commit()
    return {"deleted": True}


# ── CFD (Cumulative Flow Diagram) ─────────────────────────────────────────────

def take_cfd_snapshot(project_id: str, sprint_id, db) -> dict:
    today = date.today().isoformat()
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


def get_cfd_data(project_id: str, sprint_id, days: int, db) -> dict:
    since = (date.today() - timedelta(days=days)).isoformat()
    q = db.query(TaskStateSnapshot).filter(
        TaskStateSnapshot.project_id == project_id,
        TaskStateSnapshot.snap_date  >= since)
    if sprint_id:
        q = q.filter(TaskStateSnapshot.sprint_id == sprint_id)
    snaps = q.order_by(TaskStateSnapshot.snap_date).all()
    by_date: dict = {}
    all_statuses: set = set()
    for s in snaps:
        by_date.setdefault(s.snap_date, {})[s.status] = s.count
        all_statuses.add(s.status)
    statuses = sorted(all_statuses)
    data = [{"date": d, **by_date[d]} for d in sorted(by_date)]
    return {"project_id": project_id, "statuses": statuses, "data": data}


# ── Mentions ──────────────────────────────────────────────────────────────────

def get_my_mentions(user_id, only_unread: bool, db) -> list:
    q = db.query(Mention).filter(Mention.mentioned_user == user_id)
    if only_unread:
        q = q.filter(Mention.is_read == False)
    mentions = q.order_by(Mention.created_at.desc()).limit(50).all()
    return [{"id": m.id, "entity_type": m.entity_type, "entity_id": m.entity_id,
             "context_text": m.context_text, "is_read": m.is_read,
             "created_at": m.created_at.isoformat() if m.created_at else None}
            for m in mentions]


def mark_all_mentions_read(user_id, db) -> dict:
    updated = db.query(Mention).filter(
        Mention.mentioned_user == user_id, Mention.is_read == False,
    ).update({"is_read": True})
    db.commit()
    return {"marked_read": updated}


# ── Threaded Comments ─────────────────────────────────────────────────────────

def list_threaded_comments(entity_type: str, entity_id: str, db) -> list:
    def _ser(c):
        return {"id": c.id, "content": c.content, "created_by": c.created_by,
                "is_resolved": c.is_resolved,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "replies": [_ser(r) for r in (c.replies or [])]}
    root = (db.query(ThreadedComment)
            .filter(ThreadedComment.entity_type == entity_type,
                    ThreadedComment.entity_id   == entity_id,
                    ThreadedComment.parent_id   == None)
            .options(_jl(ThreadedComment.replies))
            .order_by(ThreadedComment.created_at).all())
    return [_ser(c) for c in root]


def add_threaded_comment(entity_type: str, entity_id: str, content: str,
                          parent_id, created_by_id, db) -> dict:
    c = ThreadedComment(entity_type=entity_type, entity_id=entity_id,
                        content=content, parent_id=parent_id, created_by=created_by_id)
    db.add(c); db.flush()
    save_mentions(entity_type, entity_id, content, created_by_id, db)
    db.commit(); db.refresh(c)
    return {"id": c.id, "content": c.content, "entity_type": entity_type,
            "entity_id": entity_id, "parent_id": c.parent_id}


def edit_threaded_comment(comment_id: str, content: str, user_id, db) -> dict:
    c = db.query(ThreadedComment).filter(
        ThreadedComment.id == comment_id,
        ThreadedComment.created_by == user_id).first()
    if not c: raise HTTPException(404, "Comentario no encontrado")
    c.content = content; db.commit()
    return {"id": c.id, "content": c.content}


def resolve_threaded_comment(comment_id: str, db) -> dict:
    c = db.query(ThreadedComment).filter(ThreadedComment.id == comment_id).first()
    if not c: raise HTTPException(404, "Comentario no encontrado")
    c.is_resolved = True; db.commit()
    return {"resolved": True}


def delete_threaded_comment(comment_id: str, user_id, db) -> dict:
    c = db.query(ThreadedComment).filter(
        ThreadedComment.id == comment_id,
        ThreadedComment.created_by == user_id).first()
    if not c: raise HTTPException(404, "Comentario no encontrado")
    if c.replies:
        raise HTTPException(400, "No se puede eliminar un comentario con respuestas")
    db.delete(c); db.commit()
    return {"deleted": True}
