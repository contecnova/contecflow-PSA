"""
Clarive v20 — Endpoints:
  issue-types/{project_id}     — Tipos de issue CRUD + campos por tipo
  task-dependencies            — Dependencias de tareas con tipo y lag
  epic-dependencies            — Dependencias épicas con tipo Gantt
  fts/search                   — Búsqueda full-text unificada
  fts/index/{entity_type}/{id} — Indexar/actualizar entrada FTS
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from typing import Optional, List
from pydantic import BaseModel

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin_or_pm
from app.models.user import User
from app.models.project import Project
from app.models.task import Task
from app.models.epics import Epic
from app.models.issue_types import (
    IssueType, IssueTypeField,
    TaskDependencyMeta, TaskDepType,
    EpicDependencyMeta, EpicDepType,
    FTSEntry,
)

router = APIRouter()


def _404(msg: str):
    raise HTTPException(404, f"{msg} no encontrado")


# ════════════════════════════════════════════════════════════════
# 1. TIPOS DE ISSUE
# ════════════════════════════════════════════════════════════════

SYSTEM_ISSUE_TYPES = [
    ("Historia",  "story",       "📖", "#00d4ff", "Historia de usuario — funcionalidad desde la perspectiva del usuario", False, 0),
    ("Tarea",     "task",        "✅", "#00e5a0", "Unidad de trabajo técnico o de desarrollo",                           False, 1),
    ("Bug",       "bug",         "🐛", "#ff4757", "Defecto o error a corregir",                                         False, 2),
    ("Mejora",    "improvement", "✨", "#ffb800", "Mejora sobre una funcionalidad existente",                           False, 3),
    ("Épica",     "epic",        "🎯", "#7c3aed", "Objetivo estratégico de alto nivel (vinculado a módulo Épicas)",     False, 4),
    ("Subtarea",  "subtask",     "🔧", "#7a8aaa", "Parte de otra tarea principal",                                     True,  5),
    ("Spike",     "spike",       "🔍", "#f97316", "Investigación técnica o de negocio sin entregable directo",         False, 6),
]


def _ser_it(it: IssueType) -> dict:
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


class IssueTypeIn(BaseModel):
    name: str
    value: str
    icon: Optional[str] = None
    color: str = "#7a8aaa"
    description: Optional[str] = None
    is_subtask: bool = False
    sort_order: int = 0
    field_keys: Optional[List[str]] = []  # campos v18 requeridos para este tipo


@router.get("/issue-types/{project_id}", summary="Tipos de issue del proyecto")
def list_issue_types(
    project_id: str,
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    types = (db.query(IssueType)
             .options(joinedload(IssueType.fields))
             .filter(IssueType.project_id == project_id)
             .order_by(IssueType.sort_order).all())
    return [_ser_it(t) for t in types]


@router.post("/issue-types/{project_id}/init", summary="Inicializar tipos de issue estándar")
def init_issue_types(
    project_id: str,
    db: Session = Depends(get_db),
    cu: User = Depends(require_admin_or_pm),
):
    if not db.query(Project).filter(Project.id == project_id).first():
        _404("Proyecto")
    existing = db.query(IssueType).filter(IssueType.project_id == project_id).count()
    if existing > 0:
        raise HTTPException(400, "Este proyecto ya tiene tipos de issue definidos")
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


@router.post("/issue-types/{project_id}", summary="Crear tipo de issue")
def create_issue_type(
    project_id: str,
    p: IssueTypeIn,
    db: Session = Depends(get_db),
    cu: User = Depends(require_admin_or_pm),
):
    if not db.query(Project).filter(Project.id == project_id).first():
        _404("Proyecto")
    existing = db.query(IssueType).filter(
        IssueType.project_id == project_id, IssueType.value == p.value).first()
    if existing:
        raise HTTPException(400, f"Ya existe el tipo '{p.value}' en este proyecto")
    it = IssueType(
        project_id=project_id, name=p.name, value=p.value,
        icon=p.icon, color=p.color, description=p.description,
        is_subtask=p.is_subtask, sort_order=p.sort_order,
    )
    db.add(it); db.flush()
    for key in (p.field_keys or []):
        db.add(IssueTypeField(issue_type_id=it.id, field_key=key))
    db.commit(); db.refresh(it)
    return _ser_it(it)


@router.patch("/issue-types/{project_id}/{type_id}", summary="Actualizar tipo de issue")
def update_issue_type(
    project_id: str, type_id: str,
    p: IssueTypeIn,
    db: Session = Depends(get_db),
    cu: User = Depends(require_admin_or_pm),
):
    it = db.query(IssueType).filter(
        IssueType.id == type_id, IssueType.project_id == project_id).first()
    if not it: _404("Tipo de issue")
    it.name        = p.name
    it.icon        = p.icon
    it.color       = p.color
    it.description = p.description
    it.is_subtask  = p.is_subtask
    it.sort_order  = p.sort_order
    # Actualizar campos: borrar todos y recrear
    for f in (it.fields or []):
        db.delete(f)
    db.flush()
    for key in (p.field_keys or []):
        db.add(IssueTypeField(issue_type_id=it.id, field_key=key))
    db.commit(); db.refresh(it)
    return _ser_it(it)


@router.delete("/issue-types/{project_id}/{type_id}", summary="Eliminar tipo de issue")
def delete_issue_type(
    project_id: str, type_id: str,
    db: Session = Depends(get_db),
    cu: User = Depends(require_admin_or_pm),
):
    it = db.query(IssueType).filter(
        IssueType.id == type_id, IssueType.project_id == project_id).first()
    if not it: _404("Tipo de issue")
    # Verificar tareas en uso
    in_use = db.query(Task).filter(Task.issue_type == it.value, Task.project_id == project_id).count()
    if in_use:
        raise HTTPException(400, f"No se puede eliminar: {in_use} tareas usan este tipo. Reasígnalas primero")
    db.delete(it); db.commit()
    return {"deleted": True}


# ════════════════════════════════════════════════════════════════
# 2. DEPENDENCIAS DE TAREAS CON TIPO Y METADATOS
# ════════════════════════════════════════════════════════════════

class TaskDepIn(BaseModel):
    from_task_id: str
    to_task_id: str
    dep_type: str = "blocks"
    lag_days: int = 0
    note: Optional[str] = None


def _ser_dep(d: TaskDependencyMeta, db: Session) -> dict:
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


@router.get("/task-dependencies/{project_id}", summary="Grafo de dependencias del proyecto")
def get_task_dependencies(
    project_id: str,
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    # Tareas del proyecto
    task_ids = {t.id for t in db.query(Task).filter(Task.project_id == project_id).all()}
    deps = db.query(TaskDependencyMeta).filter(
        TaskDependencyMeta.from_task_id.in_(task_ids)).all()
    # Nodos (tareas)
    tasks = db.query(Task).filter(Task.project_id == project_id).all()
    nodes = [{"id": t.id, "title": t.title, "status": t.status,
              "priority": t.priority, "issue_type": t.issue_type,
              "story_points": t.story_points} for t in tasks]
    edges = [_ser_dep(d, db) for d in deps]
    return {"project_id": project_id, "nodes": nodes, "edges": edges}


@router.post("/task-dependencies", summary="Crear dependencia entre tareas")
def create_task_dependency(
    p: TaskDepIn,
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if p.from_task_id == p.to_task_id:
        raise HTTPException(400, "Una tarea no puede depender de sí misma")
    for tid in [p.from_task_id, p.to_task_id]:
        if not db.query(Task).filter(Task.id == tid).first():
            raise HTTPException(404, f"Tarea {tid} no encontrada")
    # Verificar que no existe ya
    existing = db.query(TaskDependencyMeta).filter(
        TaskDependencyMeta.from_task_id == p.from_task_id,
        TaskDependencyMeta.to_task_id   == p.to_task_id).first()
    if existing:
        raise HTTPException(400, "Esta dependencia ya existe")
    try:
        dep_type = TaskDepType(p.dep_type)
    except ValueError:
        raise HTTPException(400, f"Tipo inválido: {p.dep_type}. Válidos: {[e.value for e in TaskDepType]}")
    d = TaskDependencyMeta(
        from_task_id=p.from_task_id, to_task_id=p.to_task_id,
        dep_type=dep_type, lag_days=p.lag_days, note=p.note, created_by=cu.id,
    )
    db.add(d); db.commit(); db.refresh(d)
    return _ser_dep(d, db)


@router.patch("/task-dependencies/{dep_id}", summary="Actualizar dependencia")
def update_task_dependency(
    dep_id: str,
    p: TaskDepIn,
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    d = db.query(TaskDependencyMeta).filter(TaskDependencyMeta.id == dep_id).first()
    if not d: _404("Dependencia")
    try:
        d.dep_type = TaskDepType(p.dep_type)
    except ValueError:
        raise HTTPException(400, f"Tipo inválido: {p.dep_type}")
    d.lag_days = p.lag_days
    d.note     = p.note
    db.commit(); db.refresh(d)
    return _ser_dep(d, db)


@router.delete("/task-dependencies/{dep_id}", summary="Eliminar dependencia")
def delete_task_dependency(
    dep_id: str,
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    d = db.query(TaskDependencyMeta).filter(TaskDependencyMeta.id == dep_id).first()
    if not d: _404("Dependencia")
    db.delete(d); db.commit()
    return {"deleted": True}


# ════════════════════════════════════════════════════════════════
# 3. DEPENDENCIAS DE ÉPICAS CON TIPO GANTT
# ════════════════════════════════════════════════════════════════

class EpicDepIn(BaseModel):
    epic_id: str
    depends_on_id: str
    dep_type: str = "finish_to_start"
    lag_days: int = 0


def _ser_epic_dep(d: EpicDependencyMeta, db: Session) -> dict:
    fe = db.query(Epic).filter(Epic.id == d.epic_id).first()
    te = db.query(Epic).filter(Epic.id == d.depends_on_id).first()
    return {
        "id": d.id,
        "epic_id": d.epic_id, "epic_title": fe.title if fe else None,
        "depends_on_id": d.depends_on_id, "depends_on_title": te.title if te else None,
        "dep_type": d.dep_type.value if d.dep_type else "finish_to_start",
        "lag_days": d.lag_days or 0,
    }


@router.get("/epic-dependencies/{project_id}", summary="Dependencias de épicas del proyecto")
def get_epic_dependencies(
    project_id: str,
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    epic_ids = {e.id for e in db.query(Epic).filter(Epic.project_id == project_id).all()}
    deps = db.query(EpicDependencyMeta).filter(
        EpicDependencyMeta.epic_id.in_(epic_ids)).all()
    return [_ser_epic_dep(d, db) for d in deps]


@router.post("/epic-dependencies", summary="Crear dependencia entre épicas con tipo")
def create_epic_dependency(
    p: EpicDepIn,
    db: Session = Depends(get_db),
    cu: User = Depends(require_admin_or_pm),
):
    if p.epic_id == p.depends_on_id:
        raise HTTPException(400, "Una épica no puede depender de sí misma")
    for eid in [p.epic_id, p.depends_on_id]:
        if not db.query(Epic).filter(Epic.id == eid).first():
            raise HTTPException(404, f"Épica {eid} no encontrada")
    existing = db.query(EpicDependencyMeta).filter(
        EpicDependencyMeta.epic_id == p.epic_id,
        EpicDependencyMeta.depends_on_id == p.depends_on_id).first()
    if existing:
        raise HTTPException(400, "Esta dependencia ya existe")
    try:
        dep_type = EpicDepType(p.dep_type)
    except ValueError:
        raise HTTPException(400, f"Tipo inválido: {p.dep_type}")
    d = EpicDependencyMeta(
        epic_id=p.epic_id, depends_on_id=p.depends_on_id,
        dep_type=dep_type, lag_days=p.lag_days, created_by=cu.id,
    )
    db.add(d); db.commit(); db.refresh(d)
    return _ser_epic_dep(d, db)


@router.delete("/epic-dependencies/{dep_id}", summary="Eliminar dependencia de épica")
def delete_epic_dependency(
    dep_id: str,
    db: Session = Depends(get_db),
    cu: User = Depends(require_admin_or_pm),
):
    d = db.query(EpicDependencyMeta).filter(EpicDependencyMeta.id == dep_id).first()
    if not d: _404("Dependencia")
    db.delete(d); db.commit()
    return {"deleted": True}


# ════════════════════════════════════════════════════════════════
# 4. BÚSQUEDA FULL-TEXT UNIFICADA
# ════════════════════════════════════════════════════════════════

class FTSIndexIn(BaseModel):
    entity_type: str
    entity_id: str
    project_id: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None
    tags: Optional[str] = None


@router.post("/fts/index", summary="Indexar o actualizar entrada FTS")
def index_entity(
    p: FTSIndexIn,
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    existing = db.query(FTSEntry).filter(
        FTSEntry.entity_type == p.entity_type,
        FTSEntry.entity_id   == p.entity_id).first()
    if existing:
        existing.title      = p.title
        existing.body       = p.body
        existing.tags       = p.tags
        existing.project_id = p.project_id
    else:
        db.add(FTSEntry(**p.model_dump()))
    db.commit()
    return {"indexed": True}


@router.post("/fts/index/bulk", summary="Indexar múltiples entidades de un proyecto")
def bulk_index(
    project_id: str,
    db: Session = Depends(get_db),
    cu: User = Depends(require_admin_or_pm),
):
    """Reconstruye el índice FTS completo de un proyecto."""
    count = 0
    # Tareas
    for t in db.query(Task).filter(Task.project_id == project_id).all():
        _upsert_fts(db, "task", t.id, project_id,
                    title=t.title,
                    body=f"{t.description or ''} {t.status} {t.priority or ''}",
                    tags=f"{t.issue_type or ''} {t.status}")
        count += 1
    # Épicas
    from app.models.epics import Epic
    for e in db.query(Epic).filter(Epic.project_id == project_id).all():
        _upsert_fts(db, "epic", e.id, project_id,
                    title=e.title,
                    body=f"{e.description or ''} {e.status} {e.priority}")
        count += 1
    # Páginas wiki del proyecto (vía espacios)
    from app.models.epics import WikiSpace, WikiPage
    spaces = db.query(WikiSpace).filter(WikiSpace.project_id == project_id).all()
    for sp in spaces:
        for pg in db.query(WikiPage).filter(WikiPage.space_id == sp.id).all():
            _upsert_fts(db, "wiki_page", pg.id, project_id,
                        title=pg.title, body=pg.content_text or "")
            count += 1
    db.commit()
    return {"indexed": count, "project_id": project_id}


def _upsert_fts(db, entity_type, entity_id, project_id, title="", body="", tags=""):
    ex = db.query(FTSEntry).filter(
        FTSEntry.entity_type == entity_type,
        FTSEntry.entity_id   == entity_id).first()
    if ex:
        ex.title = title; ex.body = body; ex.tags = tags
    else:
        db.add(FTSEntry(entity_type=entity_type, entity_id=entity_id,
                        project_id=project_id, title=title, body=body, tags=tags))


@router.get("/fts/search", summary="Búsqueda full-text unificada")
def fts_search(
    q: str,
    project_id: Optional[str] = None,
    entity_types: Optional[str] = None,   # "task,wiki_page,epic" separado por comas
    limit: int = 30,
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not q or len(q.strip()) < 2:
        raise HTTPException(400, "La consulta debe tener al menos 2 caracteres")

    terms = [t.strip() for t in q.split() if t.strip()]
    query = db.query(FTSEntry)

    if project_id:
        query = query.filter(FTSEntry.project_id == project_id)

    if entity_types:
        types = [t.strip() for t in entity_types.split(",") if t.strip()]
        query = query.filter(FTSEntry.entity_type.in_(types))

    # Filtro: todos los términos deben aparecer en título o cuerpo
    for term in terms:
        query = query.filter(
            or_(
                FTSEntry.title.ilike(f"%{term}%"),
                FTSEntry.body.ilike(f"%{term}%"),
                FTSEntry.tags.ilike(f"%{term}%"),
            )
        )

    results = query.order_by(FTSEntry.updated_at.desc()).limit(limit).all()

    # Calcular relevancia simple: cuántos términos aparecen en título
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


def _snippet(body: Optional[str], terms: List[str], length: int = 150) -> str:
    """Extrae un fragmento del cuerpo alrededor del primer término encontrado."""
    if not body: return ""
    body_lower = body.lower()
    for term in terms:
        idx = body_lower.find(term.lower())
        if idx >= 0:
            start = max(0, idx - 40)
            end   = min(len(body), idx + length)
            snip  = body[start:end].strip()
            return ("..." if start > 0 else "") + snip + ("..." if end < len(body) else "")
    return body[:length] + ("..." if len(body) > length else "")


@router.delete("/fts/index/{entity_type}/{entity_id}", summary="Eliminar entrada FTS")
def delete_fts_entry(
    entity_type: str, entity_id: str,
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    entry = db.query(FTSEntry).filter(
        FTSEntry.entity_type == entity_type,
        FTSEntry.entity_id   == entity_id).first()
    if entry:
        db.delete(entry); db.commit()
    return {"deleted": True}
