"""Service-desk visual workflow designer — pure business logic.

Validación robusta + serialización + ejemplos (templates) listos para usar.
"""
from __future__ import annotations

import json
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.workflow_designer import (
    WorkflowBlueprint,
    WorkflowBlueprintStatus,
    WorkflowBlueprintVersion,
)


# ── Catálogo de nodos ─────────────────────────────────────────────────────────
# El frontend lo consume vía /workflow-designer/schema. Cada entrada describe
# qué metadatos puede llevar el nodo y qué outputs produce.
NODE_CATALOG: list[dict] = [
    {"type": "start",        "label": "Inicio",          "outputs": ["next"],                    "fields": []},
    {"type": "end",          "label": "Fin",             "outputs": [],                          "fields": ["final_status"]},
    {"type": "state",        "label": "Estado",          "outputs": ["next"],                    "fields": ["status", "assignee_role", "sla_hours"]},
    # FIX: el tipo "action" se usaba en tests y workflows existentes pero no
    # estaba registrado en el catálogo → validate_graph rechazaba como tipo
    # desconocido. Es un nodo genérico que ejecuta una acción nombrada
    # (set_priority, set_assignee, set_status, run_script, etc.) con params.
    {"type": "action",       "label": "Acción",          "outputs": ["next"],                    "fields": ["action", "params"]},
    {"type": "decision",     "label": "Decisión",        "outputs": ["true", "false"],           "fields": ["expression"]},
    {"type": "approval",     "label": "Aprobación",      "outputs": ["approved", "rejected"],    "fields": ["approver_role", "deadline_hours"]},
    {"type": "wait",         "label": "Espera / Timer",  "outputs": ["next"],                    "fields": ["wait_minutes", "until_field"]},
    {"type": "notify",       "label": "Notificar",       "outputs": ["next"],                    "fields": ["channel", "template_id", "recipients"]},
    {"type": "http_call",    "label": "Llamada HTTP",    "outputs": ["success", "failure"],      "fields": ["method", "url", "headers", "body_template"]},
    {"type": "create_ticket","label": "Crear ticket",    "outputs": ["next"],                    "fields": ["queue", "title_template", "priority"]},
]

ALLOWED_NODE_TYPES = {n["type"] for n in NODE_CATALOG}
PROCESS_TYPES = ["ticket", "change", "approval"]


# ── Validación ────────────────────────────────────────────────────────────────
def validate_graph(graph: dict) -> dict:
    """Valida un grafo {nodes:[], edges:[]}.

    Comprobaciones:
      • Estructura básica (listas, ids).
      • Tipos de nodo permitidos.
      • Exactamente 1 nodo `start` y al menos 1 `end`.
      • Sin ids duplicados.
      • Sin aristas que apunten a nodos inexistentes.
      • Conectividad: todos los nodos alcanzables desde `start`.
      • Todos los nodos pueden llegar a algún `end` (no hay caminos sin salida).
      • Detecta ciclos (warning, no error — los workflows pueden tener loops).
      • Avisa si decisión / aprobación carece de los puertos esperados.
    """
    errors: list[str] = []
    warnings: list[str] = []

    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return {"valid": False, "errors": ["graph debe incluir nodes[] y edges[]"], "warnings": []}

    if not nodes:
        return {"valid": False, "errors": ["el grafo está vacío"], "warnings": []}

    # IDs y tipos
    seen_ids: set[str] = set()
    node_by_id: dict[str, dict] = {}
    for n in nodes:
        nid = str(n.get("id", "")).strip()
        if not nid:
            errors.append("hay un nodo sin id")
            continue
        if nid in seen_ids:
            errors.append(f"id de nodo duplicado: {nid!r}")
            continue
        seen_ids.add(nid)
        node_by_id[nid] = n
        ntype = str(n.get("type", "")).strip()
        if ntype not in ALLOWED_NODE_TYPES:
            errors.append(f"nodo {nid!r} usa tipo desconocido {ntype!r}")

    starts = [n for n in nodes if n.get("type") == "start"]
    ends = [n for n in nodes if n.get("type") == "end"]
    if len(starts) != 1:
        errors.append(f"el workflow debe tener exactamente 1 nodo 'start' (encontrados: {len(starts)})")
    if not ends:
        errors.append("el workflow debe tener al menos un nodo 'end'")

    # Edges → indexar
    out_adj: dict[str, list[tuple[str, str]]] = defaultdict(list)  # source → [(target, branch)]
    in_adj: dict[str, list[str]] = defaultdict(list)               # target → [source]
    for idx, e in enumerate(edges):
        src = str(e.get("source", "")).strip()
        tgt = str(e.get("target", "")).strip()
        branch = str(e.get("branch", e.get("type", "default")))
        if not src or not tgt:
            errors.append(f"arista #{idx} sin source/target válidos")
            continue
        if src not in node_by_id:
            errors.append(f"arista #{idx}: source {src!r} no existe")
        if tgt not in node_by_id:
            errors.append(f"arista #{idx}: target {tgt!r} no existe")
        if src == tgt:
            warnings.append(f"arista en bucle sobre el mismo nodo {src!r}")
        out_adj[src].append((tgt, branch))
        in_adj[tgt].append(src)

    if errors:
        # Si la estructura es inválida no merece la pena seguir con análisis avanzado
        return {"valid": False, "errors": errors, "warnings": warnings,
                "node_count": len(nodes), "edge_count": len(edges)}

    # Salidas requeridas según tipo
    catalog_by_type = {n["type"]: n for n in NODE_CATALOG}
    for n in nodes:
        nid = str(n["id"])
        ntype = n.get("type")
        spec = catalog_by_type.get(ntype, {})
        required_outputs = spec.get("outputs", [])
        actual_branches = {b for _, b in out_adj.get(nid, [])}
        for req in required_outputs:
            if req not in actual_branches:
                warnings.append(f"nodo {nid!r} ({ntype}) no tiene salida '{req}' conectada")
        # Inputs / outputs según tipo
        if ntype == "start" and in_adj.get(nid):
            warnings.append(f"nodo start {nid!r} tiene aristas de entrada")
        if ntype == "end" and out_adj.get(nid):
            warnings.append(f"nodo end {nid!r} tiene aristas de salida")
        if ntype not in {"start", "end"}:
            if not in_adj.get(nid):
                warnings.append(f"nodo {nid!r} no tiene entrada")
            if not out_adj.get(nid):
                warnings.append(f"nodo {nid!r} no tiene salida")

    # Alcanzabilidad desde start
    start_id = str(starts[0]["id"]) if starts else None
    if start_id:
        seen = {start_id}
        q = deque([start_id])
        while q:
            cur = q.popleft()
            for tgt, _ in out_adj.get(cur, []):
                if tgt not in seen:
                    seen.add(tgt)
                    q.append(tgt)
        unreachable = [nid for nid in node_by_id if nid not in seen]
        if unreachable:
            warnings.append(f"nodos inalcanzables desde start: {', '.join(sorted(unreachable))}")

    # Pueden llegar a un end (búsqueda en el grafo invertido desde cada end)
    if ends:
        reach_end = set()
        q = deque(str(e["id"]) for e in ends)
        for eid in q:
            reach_end.add(eid)
        while q:
            cur = q.popleft()
            for src in in_adj.get(cur, []):
                if src not in reach_end:
                    reach_end.add(src)
                    q.append(src)
        dead_ends = [nid for nid in node_by_id if nid not in reach_end]
        if dead_ends:
            warnings.append(f"nodos sin camino a un end: {', '.join(sorted(dead_ends))}")

    # Ciclos (warning — no siempre son errores en automation)
    visiting: dict[str, int] = {nid: 0 for nid in node_by_id}  # 0=no visto · 1=en pila · 2=cerrado
    cycle_found = False

    def dfs(nid: str) -> None:
        nonlocal cycle_found
        visiting[nid] = 1
        for tgt, _ in out_adj.get(nid, []):
            if visiting.get(tgt, 0) == 1:
                cycle_found = True
                return
            if visiting.get(tgt, 0) == 0:
                dfs(tgt)
                if cycle_found:
                    return
        visiting[nid] = 2

    for nid in node_by_id:
        if visiting[nid] == 0:
            dfs(nid)
            if cycle_found:
                warnings.append("el grafo contiene un ciclo (asegúrate de que está intencionado)")
                break

    return {
        "valid": True,
        "errors": [],
        "warnings": warnings,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


# ── Compilación ───────────────────────────────────────────────────────────────
def compile_rules_from_graph(graph: dict) -> dict:
    """Convierte el grafo en una representación declarativa estable.

    El motor de ejecución (futuro) consumirá `rules_json`, no el grafo bruto."""
    node_map = {str(n.get("id")): n for n in graph.get("nodes", [])}
    transitions = []
    for e in graph.get("edges", []):
        transitions.append({
            "from": str(e.get("source", "")),
            "to": str(e.get("target", "")),
            "branch": str(e.get("branch", e.get("type", "default"))),
            "condition": e.get("condition"),
        })

    compiled_nodes = []
    for nid, node in node_map.items():
        compiled_nodes.append({
            "id": nid,
            "type": node.get("type"),
            "label": node.get("label") or node.get("data", {}).get("label"),
            "config": node.get("config") or node.get("data", {}).get("config", {}),
        })

    return {
        "engine": "sd-declarative-v1",
        "nodes": compiled_nodes,
        "transitions": transitions,
    }


# ── CRUD blueprints ───────────────────────────────────────────────────────────
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


def archive_blueprint(db: Session, blueprint: WorkflowBlueprint) -> None:
    blueprint.is_active = False
    blueprint.status = WorkflowBlueprintStatus.archived
    db.flush()


def serialize_blueprint(bp: WorkflowBlueprint) -> dict:
    published = next((v for v in bp.versions if v.is_published), None)
    return {
        "id": bp.id,
        "name": bp.name,
        "description": bp.description,
        "process_type": bp.process_type,
        "scope": bp.scope,
        # Enum → valor str para JSON serializable
        "status": bp.status.value if hasattr(bp.status, "value") else bp.status,
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


# ── Templates pre-construidas ─────────────────────────────────────────────────
def builtin_templates() -> list[dict]:
    """Plantillas listas para clonar como punto de partida."""
    return [
        {
            "id": "incident_triage",
            "name": "Triaje de incidentes",
            "process_type": "ticket",
            "description": "Asignación + priorización + escalado por SLA",
            "graph": {
                "nodes": [
                    {"id": "n1", "type": "start", "position": {"x": 60, "y": 200}, "data": {"label": "Nuevo ticket"}},
                    {"id": "n2", "type": "decision", "position": {"x": 240, "y": 200}, "data": {"label": "¿Crítico?", "config": {"expression": "priority == 'P1'"}}},
                    {"id": "n3", "type": "state", "position": {"x": 460, "y": 90}, "data": {"label": "Asignado L2", "config": {"status": "in_progress", "assignee_role": "support_l2", "sla_hours": 2}}},
                    {"id": "n4", "type": "state", "position": {"x": 460, "y": 310}, "data": {"label": "Cola estándar", "config": {"status": "queued", "assignee_role": "support_l1", "sla_hours": 24}}},
                    {"id": "n5", "type": "approval", "position": {"x": 700, "y": 90}, "data": {"label": "Confirmar resolución", "config": {"approver_role": "support_lead"}}},
                    {"id": "n6", "type": "end", "position": {"x": 920, "y": 200}, "data": {"label": "Cerrado"}},
                ],
                "edges": [
                    {"id": "e1", "source": "n1", "target": "n2", "branch": "next"},
                    {"id": "e2", "source": "n2", "target": "n3", "branch": "true"},
                    {"id": "e3", "source": "n2", "target": "n4", "branch": "false"},
                    {"id": "e4", "source": "n3", "target": "n5", "branch": "next"},
                    {"id": "e5", "source": "n5", "target": "n6", "branch": "approved"},
                    {"id": "e6", "source": "n5", "target": "n3", "branch": "rejected"},
                    {"id": "e7", "source": "n4", "target": "n6", "branch": "next"},
                ],
            },
        },
        {
            "id": "change_approval",
            "name": "Aprobación de cambios (CAB)",
            "process_type": "change",
            "description": "Riesgo bajo auto-aprobado · alto requiere CAB",
            "graph": {
                "nodes": [
                    {"id": "n1", "type": "start", "position": {"x": 60, "y": 200}, "data": {"label": "Nuevo cambio"}},
                    {"id": "n2", "type": "decision", "position": {"x": 240, "y": 200}, "data": {"label": "¿Riesgo?", "config": {"expression": "risk in ('high','critical')"}}},
                    {"id": "n3", "type": "approval", "position": {"x": 470, "y": 90}, "data": {"label": "Aprueba CAB", "config": {"approver_role": "cab_member", "deadline_hours": 48}}},
                    {"id": "n4", "type": "state", "position": {"x": 470, "y": 310}, "data": {"label": "Auto-aprobado", "config": {"status": "approved"}}},
                    {"id": "n5", "type": "state", "position": {"x": 720, "y": 200}, "data": {"label": "Programado", "config": {"status": "scheduled"}}},
                    {"id": "n6", "type": "end", "position": {"x": 940, "y": 90}, "data": {"label": "Rechazado"}},
                    {"id": "n7", "type": "end", "position": {"x": 940, "y": 300}, "data": {"label": "Implementado"}},
                ],
                "edges": [
                    {"id": "e1", "source": "n1", "target": "n2", "branch": "next"},
                    {"id": "e2", "source": "n2", "target": "n3", "branch": "true"},
                    {"id": "e3", "source": "n2", "target": "n4", "branch": "false"},
                    {"id": "e4", "source": "n3", "target": "n5", "branch": "approved"},
                    {"id": "e5", "source": "n3", "target": "n6", "branch": "rejected"},
                    {"id": "e6", "source": "n4", "target": "n5", "branch": "next"},
                    {"id": "e7", "source": "n5", "target": "n7", "branch": "next"},
                ],
            },
        },
        {
            "id": "vacation_request",
            "name": "Solicitud de vacaciones",
            "process_type": "approval",
            "description": "Aprobación del responsable + notificación a RRHH",
            "graph": {
                "nodes": [
                    {"id": "n1", "type": "start", "position": {"x": 60, "y": 200}, "data": {"label": "Solicitud"}},
                    {"id": "n2", "type": "approval", "position": {"x": 280, "y": 200}, "data": {"label": "Aprueba responsable", "config": {"approver_role": "manager", "deadline_hours": 72}}},
                    {"id": "n3", "type": "notify", "position": {"x": 520, "y": 100}, "data": {"label": "Aviso a RRHH", "config": {"channel": "email", "recipients": "hr@company.com"}}},
                    {"id": "n4", "type": "notify", "position": {"x": 520, "y": 300}, "data": {"label": "Aviso al solicitante (no)", "config": {"channel": "in_app"}}},
                    {"id": "n5", "type": "end", "position": {"x": 760, "y": 100}, "data": {"label": "Aprobado"}},
                    {"id": "n6", "type": "end", "position": {"x": 760, "y": 300}, "data": {"label": "Rechazado"}},
                ],
                "edges": [
                    {"id": "e1", "source": "n1", "target": "n2", "branch": "next"},
                    {"id": "e2", "source": "n2", "target": "n3", "branch": "approved"},
                    {"id": "e3", "source": "n2", "target": "n4", "branch": "rejected"},
                    {"id": "e4", "source": "n3", "target": "n5", "branch": "next"},
                    {"id": "e5", "source": "n4", "target": "n6", "branch": "next"},
                ],
            },
        },
    ]
