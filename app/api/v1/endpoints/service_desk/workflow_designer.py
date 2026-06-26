"""Service Desk visual workflow designer endpoints."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_any_manager
from app.db.session import get_db
from app.models.user import User
from app.core.abac_enforce import enforce_abac
from app.core.tenancy import org_scoped_or_404
from app.models.workflow_designer import (
    WorkflowBlueprint, WorkflowBlueprintVersion,
    WorkflowRun, WorkflowRunStatus,
)
from app.services.service_desk.workflow_designer_service import (
    NODE_CATALOG,
    PROCESS_TYPES,
    add_blueprint_version,
    archive_blueprint,
    builtin_templates,
    create_blueprint,
    publish_version,
    serialize_blueprint,
    serialize_version,
    validate_graph,
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
    return {
        "version": "2.0",
        "process_types": PROCESS_TYPES,
        "node_types": NODE_CATALOG,
    }


@router.get("/workflow-designer/templates", summary="Plantillas pre-construidas")
def list_templates(current_user: User = Depends(get_current_user)):
    return builtin_templates()


@router.post("/workflow-designer/validate", summary="Validar grafo de workflow")
def validate_workflow_graph(
    graph: dict = Body(...), current_user: User = Depends(require_any_manager)
):
    return validate_graph(graph)


@router.get("/workflow-designer/blueprints", summary="Listar blueprints de workflow")
def list_blueprints(
    process_type: Optional[str] = Query(None),
    include_archived: bool = Query(False),
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    q = db.query(WorkflowBlueprint).order_by(
        WorkflowBlueprint.updated_at.desc().nullslast(),
        WorkflowBlueprint.created_at.desc(),
    )
    if process_type:
        q = q.filter(WorkflowBlueprint.process_type == process_type)
    if not include_archived:
        q = q.filter(WorkflowBlueprint.is_active == True)  # noqa: E712
    return [serialize_blueprint(bp) for bp in q.all()]


@router.post("/workflow-designer/blueprints", summary="Crear blueprint de workflow")
def create_workflow_blueprint(
    payload: BlueprintCreateIn,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    validation = validate_graph(payload.graph)
    if not validation.get("valid"):
        raise HTTPException(status_code=400, detail={"message": "invalid graph", **validation})

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
    return serialize_blueprint(bp)


@router.get("/workflow-designer/blueprints/{blueprint_id}", summary="Detalle blueprint + versiones")
def get_blueprint(
    blueprint_id: str,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    bp = org_scoped_or_404(db, WorkflowBlueprint, blueprint_id, current_user, detail="Blueprint not found")
    versions = [serialize_version(v) for v in bp.versions]
    return {"blueprint": serialize_blueprint(bp), "versions": versions}


@router.post("/workflow-designer/blueprints/{blueprint_id}/versions", summary="Añadir versión de blueprint")
def create_blueprint_version(
    blueprint_id: str,
    payload: BlueprintVersionIn,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    bp = org_scoped_or_404(db, WorkflowBlueprint, blueprint_id, current_user, detail="Blueprint not found")

    validation = validate_graph(payload.graph)
    if not validation.get("valid"):
        raise HTTPException(status_code=400, detail={"message": "invalid graph", **validation})

    version = add_blueprint_version(db, bp, payload.graph, current_user.id)
    db.commit()
    db.refresh(version)
    return serialize_version(version)


@router.post("/workflow-designer/blueprints/{blueprint_id}/publish/{version}", summary="Publicar versión de blueprint")
def publish_blueprint_version(
    blueprint_id: str,
    version: int,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    bp = org_scoped_or_404(db, WorkflowBlueprint, blueprint_id, current_user, detail="Blueprint not found")

    target = (
        db.query(WorkflowBlueprintVersion)
        .filter(
            WorkflowBlueprintVersion.blueprint_id == blueprint_id,
            WorkflowBlueprintVersion.version == version,
        )
        .first()
    )
    if not target:
        raise HTTPException(404, "Version not found")

    publish_version(db, bp, target)
    db.commit()
    return {"ok": True, "blueprint_id": blueprint_id, "published_version": version}


@router.post("/workflow-designer/blueprints/{blueprint_id}/clone", summary="Clonar blueprint")
def clone_blueprint(
    blueprint_id: str,
    payload: BlueprintCloneIn,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    src = org_scoped_or_404(db, WorkflowBlueprint, blueprint_id, current_user, detail="Blueprint not found")
    # Toma la versión publicada si la hay, si no la última creada
    head = next((v for v in src.versions if v.is_published), None) or (src.versions[0] if src.versions else None)
    if not head:
        raise HTTPException(400, "Blueprint sin versiones para clonar")
    import json as _json
    graph = _json.loads(head.graph_json or "{}")
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
    return serialize_blueprint(bp)


@router.delete("/workflow-designer/blueprints/{blueprint_id}", summary="Archivar blueprint (soft delete)")
def delete_blueprint(
    blueprint_id: str,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "sd_workflow_blueprint", blueprint_id, action="delete")
    bp = org_scoped_or_404(db, WorkflowBlueprint, blueprint_id, current_user, detail="Blueprint not found")
    archive_blueprint(db, bp)
    db.commit()
    return {"ok": True, "archived": True}


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
    try:
        run = engine.start_run(
            db,
            blueprint_id=blueprint_id,
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
    return {
        "run": engine.serialize_run(run),
        "steps": [engine.serialize_step(s) for s in run.steps],
    }


@router.get("/workflow-designer/runs", summary="Listar ejecuciones")
def list_runs(
    blueprint_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    q = db.query(WorkflowRun).order_by(WorkflowRun.started_at.desc())
    if blueprint_id:
        q = q.filter(WorkflowRun.blueprint_id == blueprint_id)
    if status:
        q = q.filter(WorkflowRun.status == status)
    return [engine.serialize_run(r) for r in q.limit(limit).all()]


@router.get("/workflow-designer/runs/{run_id}", summary="Detalle de ejecución + historial")
def get_run(
    run_id: str,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    return {
        "run": engine.serialize_run(run),
        "steps": [engine.serialize_step(s) for s in run.steps],
    }


@router.post("/workflow-designer/runs/{run_id}/resume", summary="Reanudar ejecución pausada (aprobación / wait)")
def resume_run(
    run_id: str,
    payload: RunResumeIn,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    if run.status != WorkflowRunStatus.waiting:
        raise HTTPException(400, f"run no está en waiting (estado actual: {run.status.value if hasattr(run.status,'value') else run.status})")
    try:
        engine.resume(db, run, branch=payload.branch, payload=payload.payload, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    db.commit()
    db.refresh(run)
    return {
        "run": engine.serialize_run(run),
        "steps": [engine.serialize_step(s) for s in run.steps],
    }


@router.post("/workflow-designer/runs/{run_id}/cancel", summary="Cancelar ejecución")
def cancel_run(
    run_id: str,
    reason: Optional[str] = Body(None, embed=True),
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    engine.cancel_run(db, run, reason=reason)
    db.commit()
    return {"ok": True, "run": engine.serialize_run(run)}
