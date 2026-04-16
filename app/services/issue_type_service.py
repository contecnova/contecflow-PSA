"""
issue_type_service — business logic extracted from app/api/v1/endpoints/issue_types.py
Covers: issue types CRUD, task dependencies, epic dependencies, FTS index & search.
"""
from __future__ import annotations

from typing import Optional, List

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_

from app.models.project import Project
from app.models.task import Task
from app.models.epics import Epic
from app.models.issue_types import (
    IssueType, IssueTypeField,
    TaskDependencyMeta, TaskDepType,
    EpicDependencyMeta, EpicDepType,
    FTSEntry,
)


SYSTEM_ISSUE_TYPES = [
    ("Historia",  "story",       "📖", "#00d4ff", "Historia de usuario — funcionalidad desde la perspectiva del usuario", False, 0),
    ("Tarea",     "task",        "✅", "#00e5a0", "Unidad de trabajo técnico o de desarrollo",                           False, 1),
    ("Bug",       "bug",         "🐛", "#ff4757", "Defecto o error a corregir",                                         False, 2),
    ("Mejora",    "improvement", "✨", "#ffb800", "Mejora sobre una funcionalidad existente",                           False, 3),
    ("Épica",     "epic",        "🎯", "#7c3aed", "Objetivo estratégico de alto nivel (vinculado a módulo Épicas)",     False, 4),
    ("Subtarea",  "subtask",     "🔧", "#7a8aaa", "Parte de otra tarea principal",                                     True,  5),
    ("Spike",     "spike",       "🔍", "#f97316", "Investigación técnica o de negocio sin entregable directo",         False, 6),
]


# ════════════════════════════════════════════════════════════════
# SERIALIZERS
# ════════════════════════════════════════════════════════════════

def serialize_issue_type(it: IssueType) -> dict:
    return {
        "id": it.id, "project_id": it.project_id,
        "name": it.name, "value": it.value,
        "icon": it.icon, "color": it.color,
        "description": it.description,
        "is_subtask": it.is_subtask,
        "sort_order": it.sort_order,
        "field_keys": [f.field_key for f in (it.fields or [])],
        "created_at": it.created_at.isoformat() if it.created_at else None,
    }


def serialize_task_dep(d: TaskDependencyMeta, db: Session) -> dict:
    ft = db.query(Task).filter(Task.id == d.from_task_id).first()
    tt = db.query(Task).filter(Task.id == d.to_task_id).first()
    return {
        "id": d.id,
        "from_task_id": d.from_task_id, "from_task_title": ft.title if ft else None,
        "from_task_status": ft.status if ft else None,
        "to_task_id": d.to_task_id,   "to_task_title": tt.title if tt else None,
        "to_task_status": tt.status if tt else None,
        "dep_type": d.dep_type.value if d.dep_type else "blocks",
        "lag_days": d.lag_days or 0,
        "note": d.note,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }


def serialize_epic_dep(d: EpicDependencyMeta, db: Session) -> dict:
    fe = db.query(Epic).filter(Epic.id == d.epic_id).first()
    te = db.query(Epic).filter(Epic.id == d.depends_on_id).first()
    return {
        "id": d.id,
        "epic_id": d.epic_id, "epic_title": fe.title if fe else None,
        "depends_on_id": d.depends_on_id, "depends_on_title": te.title if te else None,
        "dep_type": d.dep_type.value if d.dep_type else "finish_to_start",
        "lag_days": d.lag_days or 0,
    }


# ════════════════════════════════════════════════════════════════
# 1. TIPOS DE ISSUE
# ════════════════════════════════════════════════════════════════

def list_issue_types(project_id: str, db: Session) -> list:
    types = (
        db.query(IssueType)
        .options(joinedload(IssueType.fields))
        .filter(IssueType.project_id == project_id)
        .order_by(IssueType.sort_order).all()
    )
    return [serialize_issue_type(t) for t in types]


def init_issue_types(project_id: str, db: Session) -> dict:
    if not db.query(Project).filter(Project.id == project_id).first():
        raise ValueError("404:Proyecto no encontrado")
    existing = db.query(IssueType).filter(IssueType.project_id == project_id).count()
    if existing > 0:
        raise ValueError("Este proyecto ya tiene tipos de issue definidos")
    created = []
    for name, value, icon, color, desc, is_sub, order in SYSTEM_ISSUE_TYPES:
        it = IssueType(
            project_id=project_id, name=name, value=value,
            icon=icon, color=color, description=desc,
            is_subtask=is_sub, sort_order=order,
        )
        db.add(it)
        created.append(value)
    db.commit()
    return {"initialized": True, "types": created}


def create_issue_type(project_id: str, payload_dict: dict, db: Session) -> dict:
    if not db.query(Project).filter(Project.id == project_id).first():
        raise ValueError("404:Proyecto no encontrado")
    existing = db.query(IssueType).filter(
        IssueType.project_id == project_id,
        IssueType.value == payload_dict["value"],
    ).first()
    if existing:
        raise ValueError(f"Ya existe el tipo '{payload_dict['value']}' en este proyecto")
    it = IssueType(
        project_id=project_id,
        name=payload_dict["name"],
        value=payload_dict["value"],
        icon=payload_dict.get("icon"),
        color=payload_dict.get("color", "#7a8aaa"),
        description=payload_dict.get("description"),
        is_subtask=payload_dict.get("is_subtask", False),
        sort_order=payload_dict.get("sort_order", 0),
    )
    db.add(it); db.flush()
    for key in (payload_dict.get("field_keys") or []):
        db.add(IssueTypeField(issue_type_id=it.id, field_key=key))
    db.commit(); db.refresh(it)
    return serialize_issue_type(it)


def update_issue_type(project_id: str, type_id: str, payload_dict: dict, db: Session) -> dict:
    it = db.query(IssueType).filter(
        IssueType.id == type_id, IssueType.project_id == project_id
    ).first()
    if not it:
        raise ValueError("404:Tipo de issue no encontrado")
    it.name        = payload_dict["name"]
    it.icon        = payload_dict.get("icon")
    it.color       = payload_dict.get("color", "#7a8aaa")
    it.description = payload_dict.get("description")
    it.is_subtask  = payload_dict.get("is_subtask", False)
    it.sort_order  = payload_dict.get("sort_order", 0)
    for f in (it.fields or []):
        db.delete(f)
    db.flush()
    for key in (payload_dict.get("field_keys") or []):
        db.add(IssueTypeField(issue_type_id=it.id, field_key=key))
    db.commit(); db.refresh(it)
    return serialize_issue_type(it)


def delete_issue_type(project_id: str, type_id: str, db: Session) -> dict:
    it = db.query(IssueType).filter(
        IssueType.id == type_id, IssueType.project_id == project_id
    ).first()
    if not it:
        raise ValueError("404:Tipo de issue no encontrado")
    in_use = db.query(Task).filter(
        Task.issue_type == it.value, Task.project_id == project_id
    ).count()
    if in_use:
        raise ValueError(f"No se puede eliminar: {in_use} tareas usan este tipo. Reasígnalas primero")
    db.delete(it); db.commit()
    return {"deleted": True}


# ════════════════════════════════════════════════════════════════
# 2. DEPENDENCIAS DE TAREAS
# ════════════════════════════════════════════════════════════════

def get_task_dependencies(project_id: str, db: Session) -> dict:
    task_ids = {t.id for t in db.query(Task).filter(Task.project_id == project_id).all()}
    deps = db.query(TaskDependencyMeta).filter(
        TaskDependencyMeta.from_task_id.in_(task_ids)
    ).all()
    tasks = db.query(Task).filter(Task.project_id == project_id).all()
    nodes = [
        {"id": t.id, "title": t.title, "status": t.status,
         "priority": t.priority, "issue_type": t.issue_type,
         "story_points": t.story_points}
        for t in tasks
    ]
    edges = [serialize_task_dep(d, db) for d in deps]
    return {"project_id": project_id, "nodes": nodes, "edges": edges}


def create_task_dependency(payload_dict: dict, created_by: str, db: Session) -> dict:
    from_id = payload_dict["from_task_id"]
    to_id = payload_dict["to_task_id"]
    if from_id == to_id:
        raise ValueError("Una tarea no puede depender de sí misma")
    for tid in [from_id, to_id]:
        if not db.query(Task).filter(Task.id == tid).first():
            raise ValueError(f"404:Tarea {tid} no encontrada")
    existing = db.query(TaskDependencyMeta).filter(
        TaskDependencyMeta.from_task_id == from_id,
        TaskDependencyMeta.to_task_id   == to_id,
    ).first()
    if existing:
        raise ValueError("Esta dependencia ya existe")
    try:
        dep_type = TaskDepType(payload_dict.get("dep_type", "blocks"))
    except ValueError:
        valid = [e.value for e in TaskDepType]
        raise ValueError(f"Tipo inválido: {payload_dict.get('dep_type')}. Válidos: {valid}")
    d = TaskDependencyMeta(
        from_task_id=from_id, to_task_id=to_id,
        dep_type=dep_type,
        lag_days=payload_dict.get("lag_days", 0),
        note=payload_dict.get("note"),
        created_by=created_by,
    )
    db.add(d); db.commit(); db.refresh(d)
    return serialize_task_dep(d, db)


def update_task_dependency(dep_id: str, payload_dict: dict, db: Session) -> dict:
    d = db.query(TaskDependencyMeta).filter(TaskDependencyMeta.id == dep_id).first()
    if not d:
        raise ValueError("404:Dependencia no encontrada")
    try:
        d.dep_type = TaskDepType(payload_dict.get("dep_type", "blocks"))
    except ValueError:
        raise ValueError(f"Tipo inválido: {payload_dict.get('dep_type')}")
    d.lag_days = payload_dict.get("lag_days", 0)
    d.note     = payload_dict.get("note")
    db.commit(); db.refresh(d)
    return serialize_task_dep(d, db)


def delete_task_dependency(dep_id: str, db: Session) -> dict:
    d = db.query(TaskDependencyMeta).filter(TaskDependencyMeta.id == dep_id).first()
    if not d:
        raise ValueError("404:Dependencia no encontrada")
    db.delete(d); db.commit()
    return {"deleted": True}


# ════════════════════════════════════════════════════════════════
# 3. DEPENDENCIAS DE ÉPICAS
# ════════════════════════════════════════════════════════════════

def get_epic_dependencies(project_id: str, db: Session) -> list:
    epic_ids = {e.id for e in db.query(Epic).filter(Epic.project_id == project_id).all()}
    deps = db.query(EpicDependencyMeta).filter(
        EpicDependencyMeta.epic_id.in_(epic_ids)
    ).all()
    return [serialize_epic_dep(d, db) for d in deps]


def create_epic_dependency(payload_dict: dict, created_by: str, db: Session) -> dict:
    epic_id = payload_dict["epic_id"]
    depends_on_id = payload_dict["depends_on_id"]
    if epic_id == depends_on_id:
        raise ValueError("Una épica no puede depender de sí misma")
    for eid in [epic_id, depends_on_id]:
        if not db.query(Epic).filter(Epic.id == eid).first():
            raise ValueError(f"404:Épica {eid} no encontrada")
    existing = db.query(EpicDependencyMeta).filter(
        EpicDependencyMeta.epic_id == epic_id,
        EpicDependencyMeta.depends_on_id == depends_on_id,
    ).first()
    if existing:
        raise ValueError("Esta dependencia ya existe")
    try:
        dep_type = EpicDepType(payload_dict.get("dep_type", "finish_to_start"))
    except ValueError:
        raise ValueError(f"Tipo inválido: {payload_dict.get('dep_type')}")
    d = EpicDependencyMeta(
        epic_id=epic_id, depends_on_id=depends_on_id,
        dep_type=dep_type,
        lag_days=payload_dict.get("lag_days", 0),
        created_by=created_by,
    )
    db.add(d); db.commit(); db.refresh(d)
    return serialize_epic_dep(d, db)


def delete_epic_dependency(dep_id: str, db: Session) -> dict:
    d = db.query(EpicDependencyMeta).filter(EpicDependencyMeta.id == dep_id).first()
    if not d:
        raise ValueError("404:Dependencia no encontrada")
    db.delete(d); db.commit()
    return {"deleted": True}


# ════════════════════════════════════════════════════════════════
# 4. FULL-TEXT SEARCH
# ════════════════════════════════════════════════════════════════

def _upsert_fts(db: Session, entity_type: str, entity_id: str, project_id: str,
                title: str = "", body: str = "", tags: str = "") -> None:
    ex = db.query(FTSEntry).filter(
        FTSEntry.entity_type == entity_type,
        FTSEntry.entity_id   == entity_id,
    ).first()
    if ex:
        ex.title = title; ex.body = body; ex.tags = tags
    else:
        db.add(FTSEntry(
            entity_type=entity_type, entity_id=entity_id,
            project_id=project_id, title=title, body=body, tags=tags,
        ))


def index_entity(payload_dict: dict, db: Session) -> dict:
    entity_type = payload_dict["entity_type"]
    entity_id   = payload_dict["entity_id"]
    existing = db.query(FTSEntry).filter(
        FTSEntry.entity_type == entity_type,
        FTSEntry.entity_id   == entity_id,
    ).first()
    if existing:
        existing.title      = payload_dict.get("title")
        existing.body       = payload_dict.get("body")
        existing.tags       = payload_dict.get("tags")
        existing.project_id = payload_dict.get("project_id")
    else:
        db.add(FTSEntry(
            entity_type=entity_type,
            entity_id=entity_id,
            project_id=payload_dict.get("project_id"),
            title=payload_dict.get("title"),
            body=payload_dict.get("body"),
            tags=payload_dict.get("tags"),
        ))
    db.commit()
    return {"indexed": True}


def bulk_index(project_id: str, db: Session) -> dict:
    from app.models.epics import WikiSpace, WikiPage
    count = 0
    for t in db.query(Task).filter(Task.project_id == project_id).all():
        _upsert_fts(
            db, "task", t.id, project_id,
            title=t.title,
            body=f"{t.description or ''} {t.status} {t.priority or ''}",
            tags=f"{t.issue_type or ''} {t.status}",
        )
        count += 1
    for e in db.query(Epic).filter(Epic.project_id == project_id).all():
        _upsert_fts(
            db, "epic", e.id, project_id,
            title=e.title,
            body=f"{e.description or ''} {e.status} {e.priority}",
        )
        count += 1
    spaces = db.query(WikiSpace).filter(WikiSpace.project_id == project_id).all()
    for sp in spaces:
        for pg in db.query(WikiPage).filter(WikiPage.space_id == sp.id).all():
            _upsert_fts(db, "wiki_page", pg.id, project_id,
                        title=pg.title, body=pg.content_text or "")
            count += 1
    db.commit()
    return {"indexed": count, "project_id": project_id}


def _snippet(body: Optional[str], terms: List[str], length: int = 150) -> str:
    if not body:
        return ""
    body_lower = body.lower()
    for term in terms:
        idx = body_lower.find(term.lower())
        if idx != -1:
            start = max(0, idx - 40)
            end = min(len(body), start + length)
            snippet = body[start:end]
            if start > 0:
                snippet = "…" + snippet
            if end < len(body):
                snippet = snippet + "…"
            return snippet
    return body[:length] + ("…" if len(body) > length else "")


def fts_search(
    q: str,
    project_id: Optional[str],
    entity_types: Optional[str],
    limit: int,
    db: Session,
) -> dict:
    if not q or len(q.strip()) < 2:
        raise ValueError("La consulta debe tener al menos 2 caracteres")
    terms = [t.strip() for t in q.split() if t.strip()]
    query = db.query(FTSEntry)
    if project_id:
        query = query.filter(FTSEntry.project_id == project_id)
    if entity_types:
        types = [t.strip() for t in entity_types.split(",") if t.strip()]
        query = query.filter(FTSEntry.entity_type.in_(types))
    for term in terms:
        query = query.filter(
            or_(
                FTSEntry.title.ilike(f"%{term}%"),
                FTSEntry.body.ilike(f"%{term}%"),
                FTSEntry.tags.ilike(f"%{term}%"),
            )
        )
    results = query.order_by(FTSEntry.updated_at.desc()).limit(limit).all()

    def relevance(r):
        title_lower = (r.title or "").lower()
        return sum(1 for t in terms if t.lower() in title_lower)

    results.sort(key=relevance, reverse=True)
    return {
        "query": q,
        "count": len(results),
        "results": [
            {
                "entity_type":  r.entity_type,
                "entity_id":    r.entity_id,
                "project_id":   r.project_id,
                "title":        r.title,
                "snippet":      _snippet(r.body, terms),
                "updated_at":   r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in results
        ],
    }
