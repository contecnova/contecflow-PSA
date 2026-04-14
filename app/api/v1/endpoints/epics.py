"""Clarive v19 — Wiki, Épicas, NQL, CFD, Menciones"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, func
from typing import Optional, List
from pydantic import BaseModel
from datetime import date, timedelta
import json
import re

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin_or_pm
from app.models.user import User
from app.models.project import Project
from app.models.task import Task
from app.models.epics import (
    WikiSpace, WikiPage, WikiVersion, WikiTemplate, WikiComment,
    Epic, EpicTask, EpicDependency,
    SavedFilter, TaskStateSnapshot, Mention, ThreadedComment,
)

router = APIRouter()

# ── helpers ───────────────────────────────────────────────────────────────────

def _404(msg: str):
    raise HTTPException(404, f"{msg} no encontrado")

def _ser_page(p: WikiPage) -> dict:
    return {
        "id": p.id, "space_id": p.space_id, "parent_id": p.parent_id,
        "title": p.title, "slug": p.slug, "is_published": p.is_published,
        "sort_order": p.sort_order,
        "created_by": p.created_by, "updated_by": p.updated_by,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }

def _ser_page_full(p: WikiPage) -> dict:
    d = _ser_page(p)
    d["content"] = json.loads(p.content) if p.content else []
    d["content_text"] = p.content_text or ""
    return d

def _build_tree(pages: list, parent_id=None) -> list:
    return [
        {**_ser_page(p), "children": _build_tree(pages, p.id)}
        for p in pages if p.parent_id == parent_id
    ]

def _ser_epic(e: Epic) -> dict:
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

def _extract_mentions(content: str) -> List[str]:
    return re.findall(r'@([\w\-\.]+)', content or '')

def _save_mentions(entity_type: str, entity_id: str, content: str, by_id: str, db: Session):
    for handle in _extract_mentions(content):
        u = db.query(User).filter(
            or_(User.username == handle, User.email == handle)
        ).first()
        if u and u.id != by_id:
            db.add(Mention(
                mentioned_user=u.id, mentioned_by=by_id,
                entity_type=entity_type, entity_id=entity_id,
                context_text=content[:300],
            ))

def _blocks_to_text(blocks_json: str) -> str:
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


# ══════════════════════════════════════════════════════════════════════
# 1. WIKI — ESPACIOS
# ══════════════════════════════════════════════════════════════════════

class WikiSpaceIn(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    project_id: Optional[str] = None
    is_public: bool = False


@router.get("/wiki/spaces")
def list_spaces(project_id: Optional[str] = None,
                db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
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


@router.post("/wiki/spaces")
def create_space(p: WikiSpaceIn, db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    if db.query(WikiSpace).filter(WikiSpace.slug == p.slug).first():
        raise HTTPException(400, f"Ya existe un espacio con slug '{p.slug}'")
    s = WikiSpace(**p.model_dump(), created_by=cu.id)
    db.add(s); db.commit(); db.refresh(s)
    return {"id": s.id, "name": s.name, "slug": s.slug, "project_id": s.project_id}


@router.patch("/wiki/spaces/{space_id}")
def update_space(space_id: str, p: WikiSpaceIn,
                 db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    s = db.query(WikiSpace).filter(WikiSpace.id == space_id).first()
    if not s: _404("Espacio")
    for k, v in p.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    db.commit(); db.refresh(s)
    return {"id": s.id, "name": s.name, "slug": s.slug}


@router.delete("/wiki/spaces/{space_id}")
def delete_space(space_id: str, db: Session = Depends(get_db),
                 cu: User = Depends(require_admin_or_pm)):
    s = db.query(WikiSpace).filter(WikiSpace.id == space_id).first()
    if not s: _404("Espacio")
    db.delete(s); db.commit()
    return {"deleted": True}


# ══════════════════════════════════════════════════════════════════════
# 2. WIKI — PÁGINAS
# ══════════════════════════════════════════════════════════════════════

class WikiPageIn(BaseModel):
    title: str
    slug: str
    content: Optional[List] = []
    parent_id: Optional[str] = None
    is_published: bool = True
    sort_order: int = 0
    change_note: Optional[str] = None


@router.get("/wiki/spaces/{space_id}/pages")
def list_pages(space_id: str, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    pages = (db.query(WikiPage)
             .filter(WikiPage.space_id == space_id)
             .order_by(WikiPage.sort_order).all())
    return _build_tree(pages)


@router.post("/wiki/spaces/{space_id}/pages")
def create_page(space_id: str, p: WikiPageIn,
                db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    if not db.query(WikiSpace).filter(WikiSpace.id == space_id).first():
        _404("Espacio")
    content_json = json.dumps(p.content or [])
    content_text = _blocks_to_text(content_json)
    page = WikiPage(
        space_id=space_id, parent_id=p.parent_id,
        title=p.title, slug=p.slug,
        content=content_json, content_text=content_text,
        is_published=p.is_published, sort_order=p.sort_order,
        created_by=cu.id, updated_by=cu.id,
    )
    db.add(page); db.flush()
    db.add(WikiVersion(
        page_id=page.id, version_num=1,
        title=p.title, content=content_json, content_text=content_text,
        change_note="Página creada", created_by=cu.id,
    ))
    db.commit(); db.refresh(page)
    return _ser_page_full(page)


@router.get("/wiki/pages/{page_id}")
def get_page(page_id: str, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    page = db.query(WikiPage).filter(WikiPage.id == page_id).first()
    if not page: _404("Página")
    return _ser_page_full(page)


@router.patch("/wiki/pages/{page_id}")
def update_page(page_id: str, p: WikiPageIn,
                db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    page = db.query(WikiPage).filter(WikiPage.id == page_id).first()
    if not page: _404("Página")
    content_json = json.dumps(p.content or [])
    content_text = _blocks_to_text(content_json)
    last_v = db.query(func.max(WikiVersion.version_num)).filter(
        WikiVersion.page_id == page_id).scalar() or 0
    db.add(WikiVersion(
        page_id=page_id, version_num=last_v + 1,
        title=p.title, content=content_json, content_text=content_text,
        change_note=p.change_note or "Actualización", created_by=cu.id,
    ))
    page.title        = p.title
    page.slug         = p.slug
    page.content      = content_json
    page.content_text = content_text
    page.parent_id    = p.parent_id
    page.sort_order   = p.sort_order
    page.is_published = p.is_published
    page.updated_by   = cu.id
    db.commit(); db.refresh(page)
    return _ser_page_full(page)


@router.delete("/wiki/pages/{page_id}")
def delete_page(page_id: str, db: Session = Depends(get_db),
                cu: User = Depends(require_admin_or_pm)):
    page = db.query(WikiPage).filter(WikiPage.id == page_id).first()
    if not page: _404("Página")
    kids = db.query(WikiPage).filter(WikiPage.parent_id == page_id).count()
    if kids:
        raise HTTPException(400, f"Esta página tiene {kids} subpáginas — elimínalas primero")
    db.delete(page); db.commit()
    return {"deleted": True}


@router.get("/wiki/pages/{page_id}/versions")
def page_versions(page_id: str, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    vs = (db.query(WikiVersion)
          .filter(WikiVersion.page_id == page_id)
          .order_by(WikiVersion.version_num.desc()).all())
    return [{"id": v.id, "version_num": v.version_num, "title": v.title,
             "change_note": v.change_note, "created_by": v.created_by,
             "created_at": v.created_at.isoformat() if v.created_at else None}
            for v in vs]


@router.post("/wiki/pages/{page_id}/restore/{version_num}")
def restore_version(page_id: str, version_num: int,
                    db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    ver = db.query(WikiVersion).filter(
        WikiVersion.page_id == page_id,
        WikiVersion.version_num == version_num).first()
    if not ver: _404("Versión")
    page = db.query(WikiPage).filter(WikiPage.id == page_id).first()
    if not page: _404("Página")
    last_v = db.query(func.max(WikiVersion.version_num)).filter(
        WikiVersion.page_id == page_id).scalar() or 0
    db.add(WikiVersion(
        page_id=page_id, version_num=last_v + 1,
        title=ver.title, content=ver.content, content_text=ver.content_text,
        change_note=f"Restaurado desde versión {version_num}", created_by=cu.id,
    ))
    page.title = ver.title; page.content = ver.content
    page.content_text = ver.content_text; page.updated_by = cu.id
    db.commit()
    return {"restored": True, "new_version": last_v + 1}


@router.get("/wiki/search")
def search_wiki(q: str, space_id: Optional[str] = None,
                db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    query = db.query(WikiPage).filter(
        or_(WikiPage.title.ilike(f"%{q}%"), WikiPage.content_text.ilike(f"%{q}%")))
    if space_id:
        query = query.filter(WikiPage.space_id == space_id)
    pages = query.limit(20).all()
    return [{"id": p.id, "title": p.title, "space_id": p.space_id, "slug": p.slug,
             "updated_at": p.updated_at.isoformat() if p.updated_at else None}
            for p in pages]


# ── Wiki templates ─────────────────────────────────────────────────────────────

@router.get("/wiki/templates")
def list_templates(db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    ts = db.query(WikiTemplate).order_by(WikiTemplate.is_system.desc(), WikiTemplate.name).all()
    return [{"id": t.id, "name": t.name, "description": t.description,
             "icon": t.icon, "is_system": t.is_system} for t in ts]


class WikiTemplateIn(BaseModel):
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    content: Optional[List] = []


@router.post("/wiki/templates")
def create_template(p: WikiTemplateIn, db: Session = Depends(get_db),
                    cu: User = Depends(require_admin_or_pm)):
    t = WikiTemplate(name=p.name, description=p.description, icon=p.icon,
                     content=json.dumps(p.content or []), created_by=cu.id)
    db.add(t); db.commit(); db.refresh(t)
    return {"id": t.id, "name": t.name}


# ── Wiki comments ──────────────────────────────────────────────────────────────

class WikiCommentIn(BaseModel):
    content: str
    parent_id: Optional[str] = None


@router.get("/wiki/pages/{page_id}/comments")
def page_comments(page_id: str, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    def _ser(c):
        return {"id": c.id, "content": c.content, "created_by": c.created_by,
                "is_resolved": c.is_resolved,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "replies": [_ser(r) for r in (c.replies or [])]}
    cs = (db.query(WikiComment)
          .filter(WikiComment.page_id == page_id, WikiComment.parent_id == None)
          .options(joinedload(WikiComment.replies))
          .order_by(WikiComment.created_at).all())
    return [_ser(c) for c in cs]


@router.post("/wiki/pages/{page_id}/comments")
def add_wiki_comment(page_id: str, p: WikiCommentIn,
                     db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    c = WikiComment(page_id=page_id, content=p.content, parent_id=p.parent_id, created_by=cu.id)
    db.add(c); db.flush()
    _save_mentions("wiki_comment", c.id, p.content, cu.id, db)
    db.commit(); db.refresh(c)
    return {"id": c.id, "content": c.content}


@router.patch("/wiki/comments/{comment_id}/resolve")
def resolve_wiki_comment(comment_id: str, db: Session = Depends(get_db),
                         cu: User = Depends(get_current_user)):
    c = db.query(WikiComment).filter(WikiComment.id == comment_id).first()
    if not c: _404("Comentario")
    c.is_resolved = True; db.commit()
    return {"resolved": True}


# ══════════════════════════════════════════════════════════════════════
# 3. ÉPICAS Y ROADMAP
# ══════════════════════════════════════════════════════════════════════

class EpicIn(BaseModel):
    title: str
    description: Optional[str] = None
    color: str = "#7c3aed"
    status: str = "open"
    priority: str = "medium"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    sort_order: int = 0


@router.get("/epics")
def list_epics(project_id: str,
               db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    epics = (db.query(Epic)
             .options(joinedload(Epic.epic_tasks))
             .filter(Epic.project_id == project_id)
             .order_by(Epic.sort_order, Epic.start_date).all())
    return [_ser_epic(e) for e in epics]


@router.post("/epics")
def create_epic(p: EpicIn, project_id: str,
                db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    if not db.query(Project).filter(Project.id == project_id).first():
        _404("Proyecto")
    e = Epic(**p.model_dump(), project_id=project_id, created_by=cu.id)
    db.add(e); db.commit(); db.refresh(e)
    return _ser_epic(e)


@router.get("/epics/{epic_id}")
def get_epic(epic_id: str, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    e = (db.query(Epic)
         .options(joinedload(Epic.epic_tasks), joinedload(Epic.dependencies))
         .filter(Epic.id == epic_id).first())
    if not e: _404("Épica")
    d = _ser_epic(e)
    d["tasks"] = []
    for et in (e.epic_tasks or []):
        t = db.query(Task).filter(Task.id == et.task_id).first()
        if t:
            d["tasks"].append({
                "id": t.id, "title": t.title, "status": t.status,
                "story_points": t.story_points,
                "assigned_to_user_id": t.assigned_to_user_id,
            })
    d["dependencies"] = [dep.depends_on_id for dep in (e.dependencies or [])]
    return d


@router.patch("/epics/{epic_id}")
def update_epic(epic_id: str, p: EpicIn,
                db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    e = db.query(Epic).filter(Epic.id == epic_id).first()
    if not e: _404("Épica")
    for k, v in p.model_dump(exclude_unset=True).items():
        setattr(e, k, v)
    db.commit(); db.refresh(e)
    return _ser_epic(e)


@router.delete("/epics/{epic_id}")
def delete_epic(epic_id: str, db: Session = Depends(get_db),
                cu: User = Depends(require_admin_or_pm)):
    e = db.query(Epic).filter(Epic.id == epic_id).first()
    if not e: _404("Épica")
    db.delete(e); db.commit()
    return {"deleted": True}


@router.post("/epics/{epic_id}/tasks/{task_id}")
def add_task_to_epic(epic_id: str, task_id: str,
                     db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    if not db.query(Epic).filter(Epic.id == epic_id).first():
        _404("Épica")
    if not db.query(Task).filter(Task.id == task_id).first():
        _404("Tarea")
    if not db.query(EpicTask).filter(
            EpicTask.epic_id == epic_id, EpicTask.task_id == task_id).first():
        db.add(EpicTask(epic_id=epic_id, task_id=task_id))
        db.commit()
    return {"linked": True}


@router.delete("/epics/{epic_id}/tasks/{task_id}")
def remove_task_from_epic(epic_id: str, task_id: str,
                          db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    et = db.query(EpicTask).filter(
        EpicTask.epic_id == epic_id, EpicTask.task_id == task_id).first()
    if et:
        db.delete(et); db.commit()
    return {"unlinked": True}


@router.post("/epics/{epic_id}/dependencies/{depends_on_id}")
def add_dependency(epic_id: str, depends_on_id: str,
                   db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    if epic_id == depends_on_id:
        raise HTTPException(400, "Una épica no puede depender de sí misma")
    if not db.query(EpicDependency).filter(
            EpicDependency.epic_id == epic_id,
            EpicDependency.depends_on_id == depends_on_id).first():
        db.add(EpicDependency(epic_id=epic_id, depends_on_id=depends_on_id))
        db.commit()
    return {"linked": True}


@router.delete("/epics/{epic_id}/dependencies/{depends_on_id}")
def remove_dependency(epic_id: str, depends_on_id: str,
                      db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    dep = db.query(EpicDependency).filter(
        EpicDependency.epic_id == epic_id,
        EpicDependency.depends_on_id == depends_on_id).first()
    if dep:
        db.delete(dep); db.commit()
    return {"unlinked": True}


@router.get("/roadmap")
def get_roadmap(project_id: str,
                db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    epics = (db.query(Epic)
             .options(joinedload(Epic.epic_tasks), joinedload(Epic.dependencies))
             .filter(Epic.project_id == project_id)
             .order_by(Epic.start_date, Epic.sort_order).all())
    items = []
    for e in epics:
        total = len(e.epic_tasks or [])
        done  = 0
        for et in (e.epic_tasks or []):
            t = db.query(Task).filter(Task.id == et.task_id).first()
            if t and t.status == "done":
                done += 1
        items.append({
            **_ser_epic(e),
            "done_tasks":   done,
            "total_tasks":  total,
            "progress":     round(done / total * 100) if total else 0,
            "dependencies": [d.depends_on_id for d in (e.dependencies or [])],
        })
    return {"project_id": project_id, "epics": items}


# ══════════════════════════════════════════════════════════════════════
# 4. NQL — BÚSQUEDA AVANZADA
# ══════════════════════════════════════════════════════════════════════

class NQLIn(BaseModel):
    entity_type: str   # task, project, epic
    query: str
    limit: int = 50


def _parse_nql(nql: str) -> dict:
    conds = {}
    for m in re.finditer(
            r'(\w+)\s*(!=|=|IN|LIKE|>|<)\s*["\']?([^"\'AND\s]+)["\']?',
            nql, re.IGNORECASE):
        conds[m.group(1).lower()] = {"op": m.group(2).upper(), "val": m.group(3).strip()}
    return conds


@router.post("/nql/search")
def nql_search(p: NQLIn, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    conds = _parse_nql(p.query)

    if p.entity_type == "task":
        q = db.query(Task)
        if "status"    in conds: q = q.filter(Task.status    == conds["status"]["val"])
        if "priority"  in conds: q = q.filter(Task.priority  == conds["priority"]["val"])
        if "project"   in conds: q = q.filter(Task.project_id== conds["project"]["val"])
        if "title"     in conds: q = q.filter(Task.title.ilike(f"%{conds['title']['val']}%"))
        results = q.limit(p.limit).all()
        return {"entity_type": "task", "count": len(results),
                "results": [{"id": t.id, "title": t.title, "status": t.status,
                             "priority": t.priority, "project_id": t.project_id}
                            for t in results]}

    if p.entity_type == "project":
        q = db.query(Project)
        if "status" in conds: q = q.filter(Project.status == conds["status"]["val"])
        if "name"   in conds: q = q.filter(Project.name.ilike(f"%{conds['name']['val']}%"))
        results = q.limit(p.limit).all()
        return {"entity_type": "project", "count": len(results),
                "results": [{"id": r.id, "name": r.name, "status": r.status}
                            for r in results]}

    if p.entity_type == "epic":
        q = db.query(Epic)
        if "status"   in conds: q = q.filter(Epic.status   == conds["status"]["val"])
        if "priority" in conds: q = q.filter(Epic.priority == conds["priority"]["val"])
        if "title"    in conds: q = q.filter(Epic.title.ilike(f"%{conds['title']['val']}%"))
        results = q.limit(p.limit).all()
        return {"entity_type": "epic", "count": len(results),
                "results": [_ser_epic(e) for e in results]}

    raise HTTPException(400, f"entity_type '{p.entity_type}' no soportado. Usa: task, project, epic")


@router.get("/filters")
def list_filters(entity_type: Optional[str] = None,
                 db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    q = db.query(SavedFilter).filter(
        or_(SavedFilter.created_by == cu.id, SavedFilter.is_shared == True))
    if entity_type:
        q = q.filter(SavedFilter.entity_type == entity_type)
    return [{"id": f.id, "name": f.name, "entity_type": f.entity_type,
             "nql_query": f.nql_query, "is_shared": f.is_shared}
            for f in q.all()]


class SavedFilterIn(BaseModel):
    name: str
    entity_type: str
    nql_query: str
    is_shared: bool = False


@router.post("/filters")
def save_filter(p: SavedFilterIn, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    f = SavedFilter(**p.model_dump(), created_by=cu.id)
    db.add(f); db.commit(); db.refresh(f)
    return {"id": f.id, "name": f.name, "nql_query": f.nql_query}


@router.delete("/filters/{filter_id}")
def delete_filter(filter_id: str, db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    f = db.query(SavedFilter).filter(
        SavedFilter.id == filter_id, SavedFilter.created_by == cu.id).first()
    if not f: _404("Filtro")
    db.delete(f); db.commit()
    return {"deleted": True}


# ══════════════════════════════════════════════════════════════════════
# 5. CUMULATIVE FLOW DIAGRAM
# ══════════════════════════════════════════════════════════════════════

@router.post("/cfd/snapshot")
def take_snapshot(project_id: str, sprint_id: Optional[str] = None,
                  db: Session = Depends(get_db), cu: User = Depends(require_admin_or_pm)):
    today = date.today().isoformat()
    db.query(TaskStateSnapshot).filter(
        TaskStateSnapshot.project_id == project_id,
        TaskStateSnapshot.snap_date == today).delete()
    q = db.query(Task.status, func.count(Task.id)).filter(Task.project_id == project_id)
    counts = q.group_by(Task.status).all()
    for status, cnt in counts:
        db.add(TaskStateSnapshot(
            project_id=project_id, sprint_id=sprint_id,
            snap_date=today, status=status, count=cnt))
    db.commit()
    return {"date": today, "states": len(counts)}


@router.get("/cfd")
def get_cfd(project_id: str, sprint_id: Optional[str] = None, days: int = 30,
            db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    since = (date.today() - timedelta(days=days)).isoformat()
    q = db.query(TaskStateSnapshot).filter(
        TaskStateSnapshot.project_id == project_id,
        TaskStateSnapshot.snap_date >= since)
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


# ══════════════════════════════════════════════════════════════════════
# 6. @MENCIONES
# ══════════════════════════════════════════════════════════════════════

@router.get("/mentions")
def my_mentions(only_unread: bool = True,
                db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    q = db.query(Mention).filter(Mention.mentioned_user == cu.id)
    if only_unread:
        q = q.filter(Mention.is_read == False)
    mentions = q.order_by(Mention.created_at.desc()).limit(50).all()
    return [{"id": m.id, "entity_type": m.entity_type, "entity_id": m.entity_id,
             "context_text": m.context_text, "is_read": m.is_read,
             "created_at": m.created_at.isoformat() if m.created_at else None}
            for m in mentions]

# POST /mentions/{mention_id}/read is served by activity.py (v24) — no duplicate here.

@router.post("/mentions/read-all")
def mark_all_read(db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    updated = db.query(Mention).filter(
        Mention.mentioned_user == cu.id, Mention.is_read == False).update({"is_read": True})
    db.commit()
    return {"marked_read": updated}


# ══════════════════════════════════════════════════════════════════════
# 7. COMENTARIOS THREADED
# ══════════════════════════════════════════════════════════════════════

class ThreadedCommentIn(BaseModel):
    content: str
    parent_id: Optional[str] = None


@router.get("/comments")
def get_comments(entity_type: str, entity_id: str,
                 db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    def _ser(c):
        return {"id": c.id, "content": c.content, "created_by": c.created_by,
                "is_resolved": c.is_resolved,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "replies": [_ser(r) for r in (c.replies or [])]}
    root = (db.query(ThreadedComment)
            .filter(ThreadedComment.entity_type == entity_type,
                    ThreadedComment.entity_id   == entity_id,
                    ThreadedComment.parent_id   == None)
            .options(joinedload(ThreadedComment.replies))
            .order_by(ThreadedComment.created_at).all())
    return [_ser(c) for c in root]


@router.post("/comments")
def add_comment(entity_type: str, entity_id: str, p: ThreadedCommentIn,
                db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    c = ThreadedComment(entity_type=entity_type, entity_id=entity_id,
                        content=p.content, parent_id=p.parent_id, created_by=cu.id)
    db.add(c); db.flush()
    _save_mentions(entity_type, entity_id, p.content, cu.id, db)
    db.commit(); db.refresh(c)
    return {"id": c.id, "content": c.content, "entity_type": entity_type,
            "entity_id": entity_id, "parent_id": c.parent_id}


@router.patch("/comments/{comment_id}")
def edit_comment(comment_id: str, p: ThreadedCommentIn,
                 db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    c = db.query(ThreadedComment).filter(
        ThreadedComment.id == comment_id,
        ThreadedComment.created_by == cu.id).first()
    if not c: _404("Comentario")
    c.content = p.content; db.commit()
    return {"id": c.id, "content": c.content}


@router.patch("/comments/{comment_id}/resolve")
def resolve_comment(comment_id: str, db: Session = Depends(get_db),
                    cu: User = Depends(get_current_user)):
    c = db.query(ThreadedComment).filter(ThreadedComment.id == comment_id).first()
    if not c: _404("Comentario")
    c.is_resolved = True; db.commit()
    return {"resolved": True}


@router.delete("/comments/{comment_id}")
def delete_comment(comment_id: str, db: Session = Depends(get_db),
                   cu: User = Depends(get_current_user)):
    c = db.query(ThreadedComment).filter(
        ThreadedComment.id == comment_id,
        ThreadedComment.created_by == cu.id).first()
    if not c: _404("Comentario")
    if c.replies:
        raise HTTPException(400, "No se puede eliminar un comentario con respuestas")
    db.delete(c); db.commit()
    return {"deleted": True}
