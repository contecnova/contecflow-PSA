"""
issue_type_service — business logic extracted from app/api/v1/endpoints/issue_types.py
Covers: issue types CRUD, epic dependencies, FTS index & search (rev. 173: las
dependencias de tareas viven solo en task_service / TaskDependency).
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
    EpicDependencyMeta, EpicDepType,
    FTSEntry,
)
from app.models.epics import WikiSpace, WikiPage
from app.core.codigos_de_error import error, ErrorConCodigo


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

def tipos_validos(project_id: str, db: Session) -> set[str]:
    """Los del catalogo activo del proyecto; sin catalogo, los de sistema."""
    propios = {v for (v,) in db.query(IssueType.value).filter(
        IssueType.project_id == project_id, IssueType.is_active.is_(True))}
    return propios or {v for _, v, *_ in SYSTEM_ISSUE_TYPES}


def validar_tipo(project_id: str, valor: Optional[str], db: Session) -> None:
    if not valor:
        return
    validos = tipos_validos(project_id, db)
    if valor not in validos:
        raise error(422, "tipo_incidencia_no_valido", detail=f"Tipo de incidencia «{valor}» no existe en el proyecto. "
                                 f"Válidos: {', '.join(sorted(validos))}", tipo=valor, validos=', '.join(sorted(validos)))


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
        .filter(
            IssueType.project_id == project_id,
            IssueType.is_active == True,  # audit #36 soft-delete
        )
        .order_by(IssueType.sort_order).all()
    )
    return [serialize_issue_type(t) for t in types]


def init_issue_types(project_id: str, db: Session) -> dict:
    if not db.query(Project).filter(Project.id == project_id).first():
        raise ErrorConCodigo("no_encontrado", detail="404:Proyecto no encontrado", que="proyecto")
    existing = db.query(IssueType).filter(IssueType.project_id == project_id).count()
    if existing > 0:
        raise ErrorConCodigo("tipos_incidencia_ya_definidos", detail="Este proyecto ya tiene tipos de issue definidos")
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
        raise ErrorConCodigo("no_encontrado", detail="404:Proyecto no encontrado", que="proyecto")
    existing = db.query(IssueType).filter(
        IssueType.project_id == project_id,
        IssueType.value == payload_dict["value"],
    ).first()
    if existing:
        raise ErrorConCodigo("tipo_incidencia_ya_existe", detail=f"Ya existe el tipo '{payload_dict['value']}' en este proyecto", tipo=payload_dict['value'])
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
        raise ErrorConCodigo("no_encontrado", detail="404:Tipo de issue no encontrado", que="tipo_de_incidencia")
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
        raise ErrorConCodigo("no_encontrado", detail="404:Tipo de issue no encontrado", que="tipo_de_incidencia")
    in_use = db.query(Task).filter(
        Task.issue_type == it.value, Task.project_id == project_id
    ).count()
    if in_use:
        raise ErrorConCodigo("tipo_incidencia_en_uso", n=in_use)
    # audit #36 soft-delete — el tipo conserva su histórico para tareas legacy.
    it.is_active = False
    db.commit()
    return {"deleted": True}


# ════════════════════════════════════════════════════════════════
# 2. DEPENDENCIAS DE TAREAS
# ════════════════════════════════════════════════════════════════

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
        raise ErrorConCodigo("epica_depende_de_si_misma")
    for eid in [epic_id, depends_on_id]:
        if not db.query(Epic).filter(Epic.id == eid).first():
            raise ErrorConCodigo("no_encontrado", detail=f"404:Épica {eid} no encontrada", que="epica")
    existing = db.query(EpicDependencyMeta).filter(
        EpicDependencyMeta.epic_id == epic_id,
        EpicDependencyMeta.depends_on_id == depends_on_id,
    ).first()
    if existing:
        raise ErrorConCodigo("dependencia_ya_existe")
    try:
        dep_type = EpicDepType(payload_dict.get("dep_type", "finish_to_start"))
    except ValueError:
        raise ErrorConCodigo("tipo_no_valido_valor", detail=f"Tipo inválido: {payload_dict.get('dep_type')}", tipo=payload_dict.get('dep_type'))
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
        raise ErrorConCodigo("no_encontrado", detail="404:Dependencia no encontrada", que="dependencia")
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


def _acotar_indice(query, db: Session, viewer):
    """Segunda auditoría 2026-11: el índice solo devuelve lo que `viewer` ve.

    Antes bastaba la sesión: cualquiera (también el subcontratado) leía título y
    fragmento de las tareas, épicas y páginas de wiki de todos los proyectos.
    Ahora, solo de los proyectos de su alcance (`scope_projects_query`) y, en las
    tareas, las de su listado (`build_task_list_query`). Las entradas sin proyecto
    quedan para quien ve todos los proyectos de la empresa.
    """
    from sqlalchemy import and_
    from app.services import politica_de_visibilidad as _vis
    from app.services.project_service import scope_projects_query
    from app.services.tasks.queries import build_task_list_query
    proyectos = scope_projects_query(db.query(Project.id), db, viewer).subquery()
    tareas = build_task_list_query(db, viewer).with_entities(Task.id).subquery()
    en_su_proyecto = FTSEntry.project_id.in_(db.query(proyectos.c.id))
    query = query.filter(or_(
        and_(FTSEntry.entity_type != "task", en_su_proyecto),
        and_(FTSEntry.entity_type == "task", en_su_proyecto, FTSEntry.entity_id.in_(db.query(tareas.c.id))),
        *([FTSEntry.project_id.is_(None)] if not _vis.solo_proyectos_propios(viewer) else []),
    ))
    return query


def fts_search(
    q: str,
    project_id: Optional[str],
    entity_types: Optional[str],
    limit: int,
    db: Session,
    viewer,
) -> dict:
    if not q or len(q.strip()) < 2:
        raise ErrorConCodigo("consulta_minimo_2")
    terms = [t.strip() for t in q.split() if t.strip()]
    query = _acotar_indice(db.query(FTSEntry), db, viewer)
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
