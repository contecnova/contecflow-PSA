from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.workflow_designer import (
    WorkflowBlueprint,
    WorkflowBlueprintStatus,
    WorkflowBlueprintVersion,
)


_ALLOWED_NODE_TYPES = {
    "start", "condition", "action", "approval_step", "wait", "notify", "end"
}


def validate_graph(graph: dict) -> dict:
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(nodes, list) or not isinstance(edges, list):
        return {"valid": False, "errors": ["graph must include nodes[] and edges[]"], "warnings": []}

    starts = [n for n in nodes if n.get("type") == "start"]
    ends = [n for n in nodes if n.get("type") == "end"]

    if len(starts) != 1:
        errors.append("workflow must contain exactly one start node")
    if not ends:
        errors.append("workflow must contain at least one end node")

    node_ids = {str(n.get("id")) for n in nodes if n.get("id")}
    edge_sources = {str(e.get("source")) for e in edges if e.get("source")}
    edge_targets = {str(e.get("target")) for e in edges if e.get("target")}

    for n in nodes:
        ntype = str(n.get("type"))
        nid = str(n.get("id", ""))
        if ntype not in _ALLOWED_NODE_TYPES:
            errors.append(f"node {nid} has unsupported type '{ntype}'")
        if ntype != "end" and nid and nid not in edge_sources:
            warnings.append(f"node {nid} has no outgoing edge")
        if ntype != "start" and nid and nid not in edge_targets:
            warnings.append(f"node {nid} has no incoming edge")

    for e in edges:
        source = str(e.get("source", ""))
        target = str(e.get("target", ""))
        if source and source not in node_ids:
            errors.append(f"edge source '{source}' not found")
        if target and target not in node_ids:
            errors.append(f"edge target '{target}' not found")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


def compile_rules_from_graph(graph: dict) -> dict:
    """Compile graph into a deterministic declarative rule payload."""
    node_map = {str(n.get("id")): n for n in graph.get("nodes", [])}
    edges = graph.get("edges", [])
    transitions = []
    for e in edges:
        transitions.append({
            "from": str(e.get("source", "")),
            "to": str(e.get("target", "")),
            "condition": e.get("type", "default"),
        })

    compiled_nodes = []
    for nid, node in node_map.items():
        compiled_nodes.append({
            "id": nid,
            "type": node.get("type"),
            "config": node.get("config", {}),
        })

    return {
        "engine": "sd-declarative-v1",
        "nodes": compiled_nodes,
        "transitions": transitions,
    }


def create_blueprint(
    db: Session,
    name: str,
    process_type: str,
    graph: dict,
    created_by_user_id: Optional[str],
    description: Optional[str] = None,
) -> WorkflowBlueprint:
    bp = WorkflowBlueprint(
        name=name,
        description=description,
        process_type=process_type,
        status=WorkflowBlueprintStatus.draft,
        latest_version=1,
        created_by_user_id=created_by_user_id,
    )
    db.add(bp)
    db.flush()

    ver = WorkflowBlueprintVersion(
        blueprint_id=bp.id,
        version=1,
        graph_json=json.dumps(graph),
        rules_json=json.dumps(compile_rules_from_graph(graph)),
        created_by_user_id=created_by_user_id,
        is_published=False,
    )
    db.add(ver)
    db.flush()
    return bp


def add_blueprint_version(
    db: Session,
    blueprint: WorkflowBlueprint,
    graph: dict,
    created_by_user_id: Optional[str],
) -> WorkflowBlueprintVersion:
    next_version = (blueprint.latest_version or 1) + 1
    ver = WorkflowBlueprintVersion(
        blueprint_id=blueprint.id,
        version=next_version,
        graph_json=json.dumps(graph),
        rules_json=json.dumps(compile_rules_from_graph(graph)),
        created_by_user_id=created_by_user_id,
        is_published=False,
    )
    blueprint.latest_version = next_version
    blueprint.status = WorkflowBlueprintStatus.draft
    db.add(ver)
    db.flush()
    return ver


def publish_version(
    db: Session,
    blueprint: WorkflowBlueprint,
    version: WorkflowBlueprintVersion,
) -> None:
    for v in blueprint.versions:
        if v.is_published:
            v.is_published = False
            v.published_at = None
    version.is_published = True
    version.published_at = datetime.now(timezone.utc)
    blueprint.status = WorkflowBlueprintStatus.published
    db.flush()


def serialize_blueprint(bp: WorkflowBlueprint) -> dict:
    published = next((v for v in bp.versions if v.is_published), None)
    return {
        "id": bp.id,
        "name": bp.name,
        "description": bp.description,
        "process_type": bp.process_type,
        "scope": bp.scope,
        "status": bp.status,
        "latest_version": bp.latest_version,
        "published_version": published.version if published else None,
        "is_active": bp.is_active,
        "created_at": bp.created_at,
        "updated_at": bp.updated_at,
    }


def serialize_version(v: WorkflowBlueprintVersion) -> dict:
    return {
        "id": v.id,
        "blueprint_id": v.blueprint_id,
        "version": v.version,
        "graph": json.loads(v.graph_json or "{}"),
        "rules": json.loads(v.rules_json or "{}"),
        "is_published": v.is_published,
        "published_at": v.published_at,
        "created_at": v.created_at,
    }
