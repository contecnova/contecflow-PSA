"""Service Desk visual workflow designer endpoints."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_any_manager
from app.db.session import get_db
from app.models.user import User
from app.models.workflow_designer import WorkflowBlueprint, WorkflowBlueprintVersion
from app.services.service_desk.workflow_designer_service import (
    add_blueprint_version,
    create_blueprint,
    publish_version,
    serialize_blueprint,
    serialize_version,
    validate_graph,
)

router = APIRouter()


class BlueprintCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    process_type: str = Field(..., pattern="^(ticket|change|approval)$")
    description: Optional[str] = None
    graph: dict


class BlueprintVersionIn(BaseModel):
    graph: dict


@router.get("/workflow-designer/schema", summary="Schema para diseñador visual de workflows")
def get_workflow_designer_schema(current_user: User = Depends(get_current_user)):
    return {
        "version": "1.0",
        "process_types": ["ticket", "change", "approval"],
        "node_types": [
            {"type": "start", "outputs": ["next"]},
            {"type": "condition", "outputs": ["true", "false"]},
            {"type": "action", "outputs": ["next"]},
            {"type": "approval_step", "outputs": ["approved", "rejected"]},
            {"type": "wait", "outputs": ["next"]},
            {"type": "notify", "outputs": ["next"]},
            {"type": "end", "outputs": []},
        ],
    }


@router.post("/workflow-designer/validate", summary="Validar grafo de workflow")
def validate_workflow_graph(
    graph: dict = Body(...), current_user: User = Depends(require_any_manager)
):
    return validate_graph(graph)


@router.get("/workflow-designer/blueprints", summary="Listar blueprints de workflow")
def list_blueprints(
    process_type: Optional[str] = Query(None),
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    q = db.query(WorkflowBlueprint).order_by(WorkflowBlueprint.updated_at.desc(), WorkflowBlueprint.created_at.desc())
    if process_type:
        q = q.filter(WorkflowBlueprint.process_type == process_type)
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
    )
    db.commit()
    db.refresh(bp)
    return serialize_blueprint(bp)


@router.get("/workflow-designer/blueprints/{blueprint_id}", summary="Detalle blueprint")
def get_blueprint(
    blueprint_id: str,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    bp = db.query(WorkflowBlueprint).filter(WorkflowBlueprint.id == blueprint_id).first()
    if not bp:
        raise HTTPException(404, "Blueprint not found")
    versions = [serialize_version(v) for v in bp.versions]
    return {"blueprint": serialize_blueprint(bp), "versions": versions}


@router.post("/workflow-designer/blueprints/{blueprint_id}/versions", summary="Añadir versión de blueprint")
def create_blueprint_version(
    blueprint_id: str,
    payload: BlueprintVersionIn,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    bp = db.query(WorkflowBlueprint).filter(WorkflowBlueprint.id == blueprint_id).first()
    if not bp:
        raise HTTPException(404, "Blueprint not found")

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
    bp = db.query(WorkflowBlueprint).filter(WorkflowBlueprint.id == blueprint_id).first()
    if not bp:
        raise HTTPException(404, "Blueprint not found")

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
