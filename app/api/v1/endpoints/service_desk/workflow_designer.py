"""Service Desk visual workflow designer endpoints.

Auditoria 2026-08 (hallazgo 22, tanda 2). Los 14 puntos de acceso a base estan
en `services/service_desk/workflow_designer_service.py`, y al moverlos aparecio
una **asimetria dentro de este mismo fichero**: los endpoints de blueprint
usaban `org_scoped_or_404` y los de ejecucion buscaban por id **sin acotar por
organizacion**, confiando en el filtro implicito de `TenantSession`. Reanudar y
**cancelar** una ejecucion son escrituras, y una escritura no debe apoyarse en
una red de seguridad: `organization_id` es nullable en estos modelos y en esta
misma auditoria se comprobo que hay caminos con sesiones sin contexto de tenant.
Ahora la guarda es explicita y se lee.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_any_manager
from app.db.session import get_db
from app.models.user import User
from app.core.abac_enforce import enforce_abac
from app.core.responses import APIResponse, APIListResponse
from app.services.service_desk.workflow_designer_service import (
    NODE_CATALOG,
    PROCESS_TYPES,
    anadir_version_confirmada,
    archivar_blueprint_confirmado,
    blueprint_propio,
    builtin_templates,
    cancelar_ejecucion,
    clonar_blueprint_confirmado,
    crear_blueprint_confirmado,
    iniciar_ejecucion,
    publicar_version_confirmada,
    reanudar_ejecucion,
    run_propio,
    serialize_blueprint,
    serialize_version,
    validate_graph,
)
from app.services.service_desk.workflow_designer_service import (
    list_blueprints as svc_list_blueprints,
)
from app.services.service_desk.workflow_designer_service import (
    list_runs as svc_list_runs,
)
from app.services.service_desk import workflow_engine as engine
from app.core.constantes import MAX_TAMANO_DE_PAGINA

router = APIRouter()


class BlueprintCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    process_type: str = Field(..., pattern="^(ticket|change|approval)$")
    description: Optional[str] = None
    graph: dict


class BlueprintVersionIn(BaseModel):
    graph: dict


class BlueprintCloneIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


@router.get("/workflow-designer/schema", summary="Catálogo de tipos de nodo + tipos de proceso")
def get_workflow_designer_schema(current_user: User = Depends(get_current_user)):
    return APIResponse.ok(data={
        "version": "2.0",
        "process_types": PROCESS_TYPES,
        "node_types": NODE_CATALOG,
    })


@router.get("/workflow-designer/templates", summary="Plantillas pre-construidas")
def list_templates(current_user: User = Depends(get_current_user)):
    return APIListResponse.ok(items=builtin_templates())


@router.post("/workflow-designer/validate", summary="Validar grafo de workflow")
def validate_workflow_graph(
    graph: dict = Body(...), current_user: User = Depends(require_any_manager)
):
    return APIResponse.ok(data=validate_graph(graph))


@router.get("/workflow-designer/blueprints", summary="Listar blueprints de workflow")
def list_blueprints(
    process_type: Optional[str] = Query(None),
    include_archived: bool = Query(False),
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    filas = svc_list_blueprints(
        db, current_user, process_type=process_type, include_archived=include_archived)
    return APIListResponse.ok(items=[serialize_blueprint(bp) for bp in filas])


@router.post("/workflow-designer/blueprints", summary="Crear blueprint de workflow")
def create_workflow_blueprint(
    payload: BlueprintCreateIn,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    bp = crear_blueprint_confirmado(
        db, current_user,
        name=payload.name,
        process_type=payload.process_type,
        graph=payload.graph,
        description=payload.description,
    )
    return APIResponse.ok(data=serialize_blueprint(bp))


@router.get("/workflow-designer/blueprints/{blueprint_id}", summary="Detalle blueprint + versiones")
def get_blueprint(
    blueprint_id: str,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    bp = blueprint_propio(db, current_user, blueprint_id)
    versions = [serialize_version(v) for v in bp.versions]
    return APIResponse.ok(data={"blueprint": serialize_blueprint(bp), "versions": versions})


@router.post("/workflow-designer/blueprints/{blueprint_id}/versions", summary="Añadir versión de blueprint")
def create_blueprint_version(
    blueprint_id: str,
    payload: BlueprintVersionIn,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    version = anadir_version_confirmada(db, current_user, blueprint_id, payload.graph)
    return APIResponse.ok(data=serialize_version(version))


@router.post("/workflow-designer/blueprints/{blueprint_id}/publish/{version}", summary="Publicar versión de blueprint")
def publish_blueprint_version(
    blueprint_id: str,
    version: int,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    publicar_version_confirmada(db, current_user, blueprint_id, version)
    return APIResponse.ok(data={"ok": True, "blueprint_id": blueprint_id, "published_version": version})


@router.post("/workflow-designer/blueprints/{blueprint_id}/clone", summary="Clonar blueprint")
def clone_blueprint(
    blueprint_id: str,
    payload: BlueprintCloneIn,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    bp = clonar_blueprint_confirmado(db, current_user, blueprint_id, payload.name)
    return APIResponse.ok(data=serialize_blueprint(bp))


@router.delete("/workflow-designer/blueprints/{blueprint_id}", summary="Archivar blueprint (soft delete)")
def delete_blueprint(
    blueprint_id: str,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "sd_workflow_blueprint", blueprint_id, action="delete")
    archivar_blueprint_confirmado(db, current_user, blueprint_id)
    return APIResponse.ok(data={"ok": True, "archived": True})


# ── Runtime: ejecuciones ─────────────────────────────────────────────────────
class RunStartIn(BaseModel):
    target_entity_type: Optional[str] = Field(None, max_length=40)
    target_entity_id: Optional[str] = Field(None, max_length=64)
    context: Optional[dict] = Field(default_factory=dict)


class RunResumeIn(BaseModel):
    branch: Optional[str] = Field(None, max_length=40)
    payload: Optional[dict] = Field(default_factory=dict)


@router.post("/workflow-designer/blueprints/{blueprint_id}/runs", summary="Iniciar ejecución del blueprint")
def start_run(
    blueprint_id: str,
    payload: RunStartIn,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    # La guarda de organizacion va antes del motor: ver `iniciar_ejecucion`.
    run = iniciar_ejecucion(
        db, current_user, blueprint_id,
        target_entity_type=payload.target_entity_type,
        target_entity_id=payload.target_entity_id,
        context=payload.context or {},
    )
    return APIResponse.ok(data={
        "run": engine.serialize_run(run),
        "steps": [engine.serialize_step(s) for s in run.steps],
    })


@router.get("/workflow-designer/runs", summary="Listar ejecuciones")
def list_runs(
    blueprint_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=MAX_TAMANO_DE_PAGINA),
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    filas = svc_list_runs(
        db, current_user, blueprint_id=blueprint_id, status=status, limit=limit)
    return APIListResponse.ok(items=[engine.serialize_run(r) for r in filas])


@router.get("/workflow-designer/runs/{run_id}", summary="Detalle de ejecución + historial")
def get_run(
    run_id: str,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    run = run_propio(db, current_user, run_id)
    return APIResponse.ok(data={
        "run": engine.serialize_run(run),
        "steps": [engine.serialize_step(s) for s in run.steps],
    })


@router.post("/workflow-designer/runs/{run_id}/resume", summary="Reanudar ejecución pausada (aprobación / wait)")
def resume_run(
    run_id: str,
    payload: RunResumeIn,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    run = reanudar_ejecucion(db, current_user, run_id, branch=payload.branch, payload=payload.payload)
    return APIResponse.ok(data={
        "run": engine.serialize_run(run),
        "steps": [engine.serialize_step(s) for s in run.steps],
    })


@router.post("/workflow-designer/runs/{run_id}/cancel", summary="Cancelar ejecución")
def cancel_run(
    run_id: str,
    reason: Optional[str] = Body(None, embed=True),
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    run = cancelar_ejecucion(db, current_user, run_id, reason)
    return APIResponse.ok(data={"ok": True, "run": engine.serialize_run(run)})
