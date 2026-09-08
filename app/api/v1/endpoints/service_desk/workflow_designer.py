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

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_any_manager
from app.db.session import get_db
from app.models.user import User
from app.core.abac_enforce import enforce_abac
from app.core.responses import APIResponse, APIListResponse
from app.models.workflow_designer import WorkflowRunStatus
from app.services.service_desk.workflow_designer_service import (
    NODE_CATALOG,
    PROCESS_TYPES,
    add_blueprint_version,
    archive_blueprint,
    blueprint_propio,
    builtin_templates,
    create_blueprint,
    exigir_grafo_valido,
    grafo_de_cabecera,
    publish_version,
    run_propio,
    serialize_blueprint,
    serialize_version,
    validate_graph,
    version_del_blueprint,
)
from app.services.service_desk.workflow_designer_service import (
    list_blueprints as svc_list_blueprints,
)
from app.services.service_desk.workflow_designer_service import (
    list_runs as svc_list_runs,
)
from app.services.service_desk import workflow_engine as engine

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
    exigir_grafo_valido(payload.graph)

    bp = create_blueprint(
        db,
        name=payload.name,
        process_type=payload.process_type,
        graph=payload.graph,
        created_by_user_id=current_user.id,
        description=payload.description,
        organization_id=current_user.organization_id,
    )
    db.commit()
    db.refresh(bp)
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
    bp = blueprint_propio(db, current_user, blueprint_id)
    exigir_grafo_valido(payload.graph)
    version = add_blueprint_version(db, bp, payload.graph, current_user.id)
    db.commit()
    db.refresh(version)
    return APIResponse.ok(data=serialize_version(version))


@router.post("/workflow-designer/blueprints/{blueprint_id}/publish/{version}", summary="Publicar versión de blueprint")
def publish_blueprint_version(
    blueprint_id: str,
    version: int,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    bp = blueprint_propio(db, current_user, blueprint_id)
    target = version_del_blueprint(db, bp, version)
    publish_version(db, bp, target)
    db.commit()
    return APIResponse.ok(data={"ok": True, "blueprint_id": blueprint_id, "published_version": version})


@router.post("/workflow-designer/blueprints/{blueprint_id}/clone", summary="Clonar blueprint")
def clone_blueprint(
    blueprint_id: str,
    payload: BlueprintCloneIn,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    src = blueprint_propio(db, current_user, blueprint_id)
    graph = grafo_de_cabecera(src)
    bp = create_blueprint(
        db,
        name=payload.name,
        process_type=src.process_type,
        graph=graph,
        created_by_user_id=current_user.id,
        description=src.description,
        organization_id=current_user.organization_id,
    )
    db.commit()
    db.refresh(bp)
    return APIResponse.ok(data=serialize_blueprint(bp))


@router.delete("/workflow-designer/blueprints/{blueprint_id}", summary="Archivar blueprint (soft delete)")
def delete_blueprint(
    blueprint_id: str,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "sd_workflow_blueprint", blueprint_id, action="delete")
    bp = blueprint_propio(db, current_user, blueprint_id)
    archive_blueprint(db, bp)
    db.commit()
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
    # La guarda va ANTES de llamar al motor: el motor busca el blueprint por id
    # sin comprobar organizacion, asi que hasta ahora lo unico que impedia
    # ejecutar el blueprint de otro cliente era el filtro implicito.
    bp = blueprint_propio(db, current_user, blueprint_id)
    try:
        run = engine.start_run(
            db,
            blueprint_id=bp.id,
            target_entity_type=payload.target_entity_type,
            target_entity_id=payload.target_entity_id,
            context=payload.context or {},
            user_id=current_user.id,
            organization_id=getattr(current_user, "organization_id", None),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    db.commit()
    db.refresh(run)
    return APIResponse.ok(data={
        "run": engine.serialize_run(run),
        "steps": [engine.serialize_step(s) for s in run.steps],
    })


@router.get("/workflow-designer/runs", summary="Listar ejecuciones")
def list_runs(
    blueprint_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
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
    run = run_propio(db, current_user, run_id)
    if run.status != WorkflowRunStatus.waiting:
        raise HTTPException(400, f"run no está en waiting (estado actual: {run.status.value if hasattr(run.status,'value') else run.status})")
    try:
        engine.resume(db, run, branch=payload.branch, payload=payload.payload, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    db.commit()
    db.refresh(run)
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
    run = run_propio(db, current_user, run_id)
    engine.cancel_run(db, run, reason=reason)
    db.commit()
    return APIResponse.ok(data={"ok": True, "run": engine.serialize_run(run)})
