"""
Clarive v20 — thin router delegating to app.services.issue_type_service
  issue-types/{project_id}  — Tipos de issue CRUD + campos por tipo
  task-dependencies         — Dependencias de tareas con tipo y lag
  epic-dependencies         — Dependencias épicas con tipo Gantt
  fts/search                — Búsqueda full-text unificada
  fts/index                 — Indexar/actualizar entrada FTS
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin_or_pm
from app.models.user import User
import app.services.issue_type_service as _svc

router = APIRouter()


def _404(msg: str):
    raise HTTPException(404, f"{msg} no encontrado")


# ════════════════════════════════════════════════════════════════
# Pydantic schemas
# ════════════════════════════════════════════════════════════════

class IssueTypeIn(BaseModel):
    name: str
    value: str
    icon: Optional[str] = None
    color: str = "#7a8aaa"
    description: Optional[str] = None
    is_subtask: bool = False
    sort_order: int = 0
    field_keys: Optional[List[str]] = []


class TaskDepIn(BaseModel):
    from_task_id: str
    to_task_id: str
    dep_type: str = "blocks"
    lag_days: int = 0
    note: Optional[str] = None


class EpicDepIn(BaseModel):
    epic_id: str
    depends_on_id: str
    dep_type: str = "finish_to_start"
    lag_days: int = 0


class FTSIndexIn(BaseModel):
    entity_type: str
    entity_id: str
    project_id: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None
    tags: Optional[str] = None


# ════════════════════════════════════════════════════════════════
# 1. TIPOS DE ISSUE
# ════════════════════════════════════════════════════════════════

@router.get("/issue-types/{project_id}", summary="Tipos de issue del proyecto")
def list_issue_types(
    project_id: str,
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    return _svc.list_issue_types(project_id, db)


@router.post("/issue-types/{project_id}/init", summary="Inicializar tipos de issue estándar")
def init_issue_types(
    project_id: str,
    db: Session = Depends(get_db),
    cu: User = Depends(require_admin_or_pm),
):
    try:
        return _svc.init_issue_types(project_id, db)
    except ValueError as e:
        msg = str(e)
        if msg.startswith("404:"):
            _404(msg[4:])
        raise HTTPException(400, msg)


@router.post("/issue-types/{project_id}", summary="Crear tipo de issue")
def create_issue_type(
    project_id: str,
    p: IssueTypeIn,
    db: Session = Depends(get_db),
    cu: User = Depends(require_admin_or_pm),
):
    try:
        return _svc.create_issue_type(project_id, p.model_dump(), db)
    except ValueError as e:
        msg = str(e)
        if msg.startswith("404:"):
            _404(msg[4:])
        raise HTTPException(400, msg)


@router.patch("/issue-types/{project_id}/{type_id}", summary="Actualizar tipo de issue")
def update_issue_type(
    project_id: str, type_id: str,
    p: IssueTypeIn,
    db: Session = Depends(get_db),
    cu: User = Depends(require_admin_or_pm),
):
    try:
        return _svc.update_issue_type(project_id, type_id, p.model_dump(), db)
    except ValueError as e:
        msg = str(e)
        if msg.startswith("404:"):
            _404(msg[4:])
        raise HTTPException(400, msg)


@router.delete("/issue-types/{project_id}/{type_id}", summary="Eliminar tipo de issue")
def delete_issue_type(
    project_id: str, type_id: str,
    db: Session = Depends(get_db),
    cu: User = Depends(require_admin_or_pm),
):
    try:
        return _svc.delete_issue_type(project_id, type_id, db)
    except ValueError as e:
        msg = str(e)
        if msg.startswith("404:"):
            _404(msg[4:])
        raise HTTPException(400, msg)


# ════════════════════════════════════════════════════════════════
# 2. DEPENDENCIAS DE TAREAS CON TIPO Y METADATOS
# ════════════════════════════════════════════════════════════════

@router.get("/task-dependencies/{project_id}", summary="Grafo de dependencias del proyecto")
def get_task_dependencies(
    project_id: str,
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    return _svc.get_task_dependencies(project_id, db)


@router.post("/task-dependencies", summary="Crear dependencia entre tareas")
def create_task_dependency(
    p: TaskDepIn,
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    try:
        return _svc.create_task_dependency(p.model_dump(), cu.id, db)
    except ValueError as e:
        msg = str(e)
        if msg.startswith("404:"):
            raise HTTPException(404, msg[4:])
        raise HTTPException(400, msg)


@router.patch("/task-dependencies/{dep_id}", summary="Actualizar dependencia")
def update_task_dependency(
    dep_id: str,
    p: TaskDepIn,
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    try:
        return _svc.update_task_dependency(dep_id, p.model_dump(), db)
    except ValueError as e:
        msg = str(e)
        if msg.startswith("404:"):
            raise HTTPException(404, msg[4:])
        raise HTTPException(400, msg)


@router.delete("/task-dependencies/{dep_id}", summary="Eliminar dependencia")
def delete_task_dependency(
    dep_id: str,
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    try:
        return _svc.delete_task_dependency(dep_id, db)
    except ValueError as e:
        msg = str(e)
        if msg.startswith("404:"):
            raise HTTPException(404, msg[4:])
        raise HTTPException(400, msg)


# ════════════════════════════════════════════════════════════════
# 3. DEPENDENCIAS DE ÉPICAS CON TIPO GANTT
# ════════════════════════════════════════════════════════════════

@router.get("/epic-dependencies/{project_id}", summary="Dependencias de épicas del proyecto")
def get_epic_dependencies(
    project_id: str,
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    return _svc.get_epic_dependencies(project_id, db)


@router.post("/epic-dependencies", summary="Crear dependencia entre épicas con tipo")
def create_epic_dependency(
    p: EpicDepIn,
    db: Session = Depends(get_db),
    cu: User = Depends(require_admin_or_pm),
):
    try:
        return _svc.create_epic_dependency(p.model_dump(), cu.id, db)
    except ValueError as e:
        msg = str(e)
        if msg.startswith("404:"):
            raise HTTPException(404, msg[4:])
        raise HTTPException(400, msg)


@router.delete("/epic-dependencies/{dep_id}", summary="Eliminar dependencia de épica")
def delete_epic_dependency(
    dep_id: str,
    db: Session = Depends(get_db),
    cu: User = Depends(require_admin_or_pm),
):
    try:
        return _svc.delete_epic_dependency(dep_id, db)
    except ValueError as e:
        msg = str(e)
        if msg.startswith("404:"):
            raise HTTPException(404, msg[4:])
        raise HTTPException(400, msg)


# ════════════════════════════════════════════════════════════════
# 4. BÚSQUEDA FULL-TEXT UNIFICADA
# ════════════════════════════════════════════════════════════════

@router.post("/fts/index", summary="Indexar o actualizar entrada FTS")
def index_entity(
    p: FTSIndexIn,
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    return _svc.index_entity(p.model_dump(), db)


@router.post("/fts/index/bulk", summary="Indexar múltiples entidades de un proyecto")
def bulk_index(
    project_id: str,
    db: Session = Depends(get_db),
    cu: User = Depends(require_admin_or_pm),
):
    return _svc.bulk_index(project_id, db)


@router.get("/fts/search", summary="Búsqueda full-text unificada")
def fts_search(
    q: str,
    project_id: Optional[str] = None,
    entity_types: Optional[str] = None,
    limit: int = 30,
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    try:
        return _svc.fts_search(q, project_id, entity_types, limit, db)
    except ValueError as e:
        raise HTTPException(400, str(e))
