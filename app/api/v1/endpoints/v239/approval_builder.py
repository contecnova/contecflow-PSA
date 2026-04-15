from __future__ import annotations

from typing import List

from fastapi import APIRouter, Body, Depends

from app.core.deps import get_current_user, require_any_manager
from app.models.user import User

router = APIRouter()


@router.get("/approval-workflows/builder/schema", summary="Get visual workflow builder schema (node types, edge types)")
def get_workflow_builder_schema(
    current_user: User = Depends(get_current_user),
):
    return {
        "version": "1.0",
        "node_types": [
            {
                "type": "start",
                "label": "Start",
                "description": "Workflow trigger (submission event)",
                "icon": "play",
                "color": "#10b981",
                "inputs": [],
                "outputs": ["next"],
                "config_schema": {
                    "entity_type": {"type": "enum", "options": ["timesheet", "expense", "contract", "po"], "required": True},
                    "min_amount": {"type": "number", "required": False},
                },
            },
            {
                "type": "approval_step",
                "label": "Approval Step",
                "description": "Human approval required",
                "icon": "check-circle",
                "color": "#6366f1",
                "inputs": ["prev"],
                "outputs": ["approved", "rejected"],
                "config_schema": {
                    "approver_type": {"type": "enum", "options": ["role", "user", "manager", "auto"], "required": True},
                    "approver_role": {"type": "string", "required": False},
                    "approver_user_id": {"type": "string", "required": False},
                    "timeout_hours": {"type": "number", "default": 48},
                    "escalate_on_timeout": {"type": "boolean", "default": True},
                    "require_comment": {"type": "boolean", "default": False},
                },
            },
            {
                "type": "condition",
                "label": "Condition",
                "description": "Branch on field value",
                "icon": "git-branch",
                "color": "#f59e0b",
                "inputs": ["prev"],
                "outputs": ["true", "false"],
                "config_schema": {
                    "field": {"type": "string", "required": True},
                    "operator": {"type": "enum", "options": ["eq", "ne", "gt", "lt", "gte", "lte", "contains"], "required": True},
                    "value": {"type": "string", "required": True},
                },
            },
            {
                "type": "action",
                "label": "Action",
                "description": "Automated action (notify, update field, call webhook)",
                "icon": "zap",
                "color": "#06b6d4",
                "inputs": ["prev"],
                "outputs": ["next"],
                "config_schema": {
                    "action_type": {"type": "enum", "options": ["notify_role", "notify_user", "update_status", "call_webhook", "send_email"], "required": True},
                    "params": {"type": "object", "required": False},
                },
            },
            {
                "type": "end",
                "label": "End",
                "description": "Workflow complete",
                "icon": "stop-circle",
                "color": "#ef4444",
                "inputs": ["prev"],
                "outputs": [],
                "config_schema": {
                    "final_status": {"type": "enum", "options": ["approved", "rejected", "cancelled"], "required": True},
                },
            },
        ],
        "edge_types": [
            {"type": "default", "label": "Next", "color": "#6b7280"},
            {"type": "approved", "label": "Approved", "color": "#10b981"},
            {"type": "rejected", "label": "Rejected", "color": "#ef4444"},
            {"type": "true", "label": "True", "color": "#3b82f6"},
            {"type": "false", "label": "False", "color": "#f59e0b"},
        ],
        "canvas": {"default_zoom": 1.0, "grid_snap": 20},
    }


@router.post("/approval-workflows/builder/validate", summary="Validate a visual workflow graph structure")
def validate_workflow_graph(
    graph: dict = Body(...),
    current_user: User = Depends(require_any_manager),
):
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    errors: List[str] = []
    warnings: List[str] = []

    edge_sources = {e.get("source") for e in edges}
    edge_targets = {e.get("target") for e in edges}

    starts = [n for n in nodes if n.get("type") == "start"]
    if len(starts) == 0:
        errors.append("Workflow must have exactly one 'start' node")
    elif len(starts) > 1:
        errors.append("Workflow must have exactly one 'start' node (found multiple)")

    for node in nodes:
        nid = node.get("id")
        if node.get("type") != "end" and nid not in edge_sources:
            errors.append(f"Node '{node.get('type', nid)}' has no outgoing edges")

    for node in nodes:
        nid = node.get("id")
        if node.get("type") != "start" and nid not in edge_targets:
            warnings.append(f"Node '{node.get('type', nid)}' has no incoming edges")

    ends = [n for n in nodes if n.get("type") == "end"]
    if not ends:
        errors.append("Workflow must have at least one 'end' node")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }
