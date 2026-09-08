"""Service-desk visual workflow designer — pure business logic.

Validación robusta + serialización + ejemplos (templates) listos para usar.
"""
from __future__ import annotations

import json
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.workflow_designer import (
    WorkflowBlueprint,
    WorkflowBlueprintStatus,
    WorkflowBlueprintVersion,
    WorkflowRun,
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
# ── Validación de grafos de workflow ─────────────────────────────────────────
#
# Auditoría 2026-08 (hallazgo 18). `validate_graph` eran 157 líneas de
# complejidad 42 con las nueve comprobaciones de su propio docstring encadenadas
# en un único ámbito. El docstring ya las enumeraba una por una: cada
# comprobación es ahora su función.
#
# El ORDEN de los mensajes es parte del contrato —la interfaz los presenta en
# lista— así que se conserva exactamente. Verificado comparando la salida de las
# 38 combinaciones de grafo (los nueve controles, los casos degenerados y un caso
# por cada tipo de nodo permitido) antes y después: idénticas.
#
# Errores y avisos se acumulan en listas que se pasan por parámetro en lugar de
# devolverse: así el orden de aparición queda determinado por el orden en que se
# llaman las comprobaciones, que es lo que hay que preservar.


def _indexar_nodos(nodes: list, errors: list[str]) -> dict[str, dict]:
    """Valida ids y tipos, y devuelve el índice por id.

    Un nodo sin id o con id repetido se descarta del índice: sin identidad no se
    puede razonar sobre sus aristas, y seguir con él produciría errores en
    cascada que esconden el original.
    """
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
    return node_by_id


def _comprobar_extremos(nodes: list, errors: list[str]) -> tuple[list, list]:
    """Exactamente un `start` y al menos un `end`.

    Más de un `start` no es ambigüedad estética: la comprobación de
    alcanzabilidad parte de uno solo, así que el resto del grafo quedaría sin
    analizar.
    """
    starts = [n for n in nodes if n.get("type") == "start"]
    ends = [n for n in nodes if n.get("type") == "end"]
    if len(starts) != 1:
        errors.append(
            f"el workflow debe tener exactamente 1 nodo 'start' (encontrados: {len(starts)})"
        )
    if not ends:
        errors.append("el workflow debe tener al menos un nodo 'end'")
    return starts, ends


def _indexar_aristas(
    edges: list,
    node_by_id: dict[str, dict],
    errors: list[str],
    warnings: list[str],
) -> tuple[dict[str, list[tuple[str, str]]], dict[str, list[str]]]:
    """Valida las aristas y devuelve las adyacencias directa e inversa.

    `branch` acepta también la clave `type` por compatibilidad con grafos
    guardados por versiones anteriores del diseñador.
    """
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
    return out_adj, in_adj


def _avisar_puertos_y_conexiones(
    nodes: list,
    out_adj: dict[str, list[tuple[str, str]]],
    in_adj: dict[str, list[str]],
    warnings: list[str],
) -> None:
    """Salidas que el tipo de nodo declara, y entradas/salidas mínimas.

    Son avisos y no errores a propósito: un grafo a medio dibujar tiene que poder
    guardarse. Lo que no puede es guardarse sin que nadie lo señale.
    """
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
        if ntype == "start" and in_adj.get(nid):
            warnings.append(f"nodo start {nid!r} tiene aristas de entrada")
        if ntype == "end" and out_adj.get(nid):
            warnings.append(f"nodo end {nid!r} tiene aristas de salida")
        if ntype not in {"start", "end"}:
            if not in_adj.get(nid):
                warnings.append(f"nodo {nid!r} no tiene entrada")
            if not out_adj.get(nid):
                warnings.append(f"nodo {nid!r} no tiene salida")


def _avisar_inalcanzables(
    starts: list,
    node_by_id: dict[str, dict],
    out_adj: dict[str, list[tuple[str, str]]],
    warnings: list[str],
) -> None:
    """Nodos a los que no se llega desde `start`: trabajo que nunca se ejecuta."""
    start_id = str(starts[0]["id"]) if starts else None
    if not start_id:
        return
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


def _avisar_sin_camino_a_end(
    ends: list,
    node_by_id: dict[str, dict],
    in_adj: dict[str, list[str]],
    warnings: list[str],
) -> None:
    """Nodos desde los que no se alcanza ningún `end`.

    Se recorre el grafo INVERTIDO partiendo de los `end`: es la forma barata de
    responder «¿quién puede terminar?» de una sola pasada, en lugar de una
    búsqueda por cada nodo.
    """
    if not ends:
        return
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


def _hay_ciclo(
    node_by_id: dict[str, dict],
    out_adj: dict[str, list[tuple[str, str]]],
) -> bool:
    """¿Contiene el grafo algún ciclo?

    Búsqueda en profundidad con marcas de tres estados: 0 = no visto,
    1 = en la pila actual, 2 = cerrado. Encontrar un nodo en estado 1 significa
    que se ha vuelto a él sin salir, que es la definición de ciclo.

    Un ciclo es AVISO y no error: los workflows de automatización pueden tener
    bucles intencionados (reintentos, escalados que vuelven a un paso anterior).
    """
    visiting: dict[str, int] = {nid: 0 for nid in node_by_id}

    def dfs(nid: str) -> bool:
        visiting[nid] = 1
        for tgt, _ in out_adj.get(nid, []):
            estado = visiting.get(tgt, 0)
            if estado == 1:
                return True
            if estado == 0 and dfs(tgt):
                return True
        visiting[nid] = 2
        return False

    for nid in node_by_id:
        if visiting[nid] == 0 and dfs(nid):
            return True
    return False


def _avisar_tipos_que_el_motor_no_ejecuta(nodes: list, warnings: list[str]) -> None:
    """Avisa si el grafo usa un tipo de nodo que el motor no sabe ejecutar.

    Aviso y no error a proposito: el catalogo acepta esos tipos a proposito
    —hay grafos guardados que los usan— y convertirlo en error impediria
    guardarlos. Pero sin este aviso el flujo se guardaba como VALIDO y moria al
    llegar la ejecucion a ese nodo, con el run en estado de error y sin que
    quien lo diseno hubiera recibido ninguna senal.

    Hoy el unico tipo asi es `action`: esta en el catalogo, el editor no ofrece
    campos para configurarlo y `_execute_node` lanza `ValueError` al llegar. Ver
    la nota de cabecera de `_execute_node` en `workflow_engine.py`.

    El import es diferido para no acoplar el orden de carga de los dos modulos,
    que hasta ahora no se importaban entre si.
    """
    from app.services.service_desk.workflow_engine import TIPOS_EJECUTABLES

    sin_motor = sorted({
        str(n.get("type")) for n in nodes
        if str(n.get("type")) in ALLOWED_NODE_TYPES
        and str(n.get("type")) not in TIPOS_EJECUTABLES
    })
    for tipo in sin_motor:
        warnings.append(
            f"el nodo de tipo '{tipo}' se puede guardar pero el motor no sabe "
            f"ejecutarlo: la ejecución fallará al llegar a él"
        )


def validate_graph(graph: dict) -> dict:
    """Valida un grafo {nodes:[], edges:[]}.

    Comprobaciones, en el orden en que se aplican —que es el orden en que
    aparecen los mensajes, y forma parte del contrato con la interfaz:

      • Estructura básica (listas, no vacío).
      • Ids únicos y tipos de nodo permitidos.
      • Exactamente 1 nodo `start` y al menos 1 `end`.
      • Aristas con source/target existentes.
      • Puertos esperados según el tipo de nodo, y entradas/salidas mínimas.
      • Conectividad: todos los nodos alcanzables desde `start`.
      • Todos los nodos pueden llegar a algún `end`.
      • Tipos que el catálogo acepta pero el motor no ejecuta (aviso).
      • Ciclos (aviso, no error — los workflows pueden tener bucles).

    Si la estructura tiene ERRORES se corta antes del análisis avanzado: sobre un
    grafo con aristas a nodos inexistentes, la alcanzabilidad y los ciclos
    producirían avisos derivados que esconderían el problema real.
    """
    errors: list[str] = []
    warnings: list[str] = []

    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return {"valid": False, "errors": ["graph debe incluir nodes[] y edges[]"], "warnings": []}

    if not nodes:
        return {"valid": False, "errors": ["el grafo está vacío"], "warnings": []}

    node_by_id = _indexar_nodos(nodes, errors)
    starts, ends = _comprobar_extremos(nodes, errors)
    out_adj, in_adj = _indexar_aristas(edges, node_by_id, errors, warnings)

    if errors:
        return {"valid": False, "errors": errors, "warnings": warnings,
                "node_count": len(nodes), "edge_count": len(edges)}

    _avisar_tipos_que_el_motor_no_ejecuta(nodes, warnings)
    _avisar_puertos_y_conexiones(nodes, out_adj, in_adj, warnings)
    _avisar_inalcanzables(starts, node_by_id, out_adj, warnings)
    _avisar_sin_camino_a_end(ends, node_by_id, in_adj, warnings)
    if _hay_ciclo(node_by_id, out_adj):
        warnings.append("el grafo contiene un ciclo (asegúrate de que está intencionado)")

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
    organization_id: Optional[str] = None,
) -> WorkflowBlueprint:
    bp = WorkflowBlueprint(
        name=name,
        description=description,
        process_type=process_type,
        status=WorkflowBlueprintStatus.draft,
        latest_version=1,
        created_by_user_id=created_by_user_id,
        organization_id=organization_id,
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
        organization_id=organization_id,
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
        organization_id=blueprint.organization_id,
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
                    {"id": "n3", "type": "notify", "position": {"x": 520, "y": 100}, "data": {"label": "Aviso a RRHH", "config": {"channel": "email", "recipients": "hr@example.com"}}},
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


# ── Consultas y guardas, movidas del endpoint ────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 22, tanda 2). Los 14 puntos de acceso a base de
# `endpoints/service_desk/workflow_designer.py` estaban ahi, y al moverlos
# aparecio una asimetria dentro del mismo fichero: los endpoints de blueprint
# usaban `org_scoped_or_404` y los de ejecucion buscaban por id **sin acotar por
# organizacion**, confiando en el filtro implicito de `TenantSession`.
#
# Esa confianza no se sostiene: `organization_id` es nullable en estos modelos
# —una fila sin organizacion es invisible para el filtro—, el motor se invoca
# tambien desde caminos de fondo con sesiones sin contexto, y en esta misma
# auditoria se comprobo que el WebSocket del chat corria sin contexto de tenant
# durante toda la conexion. La guarda explicita es la que se puede leer y la que
# no depende de por donde entre la llamada.

def _org_de(user) -> Optional[str]:
    return getattr(user, "organization_id", None)


def list_blueprints(
    db: Session, user, *, process_type: Optional[str] = None,
    include_archived: bool = False,
) -> list[WorkflowBlueprint]:
    """Los blueprints de la organizacion del usuario, mas recientes primero."""
    q = db.query(WorkflowBlueprint).filter(
        WorkflowBlueprint.organization_id == _org_de(user)
    ).order_by(
        WorkflowBlueprint.updated_at.desc().nullslast(),
        WorkflowBlueprint.created_at.desc(),
    )
    if process_type:
        q = q.filter(WorkflowBlueprint.process_type == process_type)
    if not include_archived:
        q = q.filter(WorkflowBlueprint.is_active == True)  # noqa: E712
    return q.all()


def blueprint_propio(db: Session, user, blueprint_id: str) -> WorkflowBlueprint:
    """El blueprint, si es de la organizacion del usuario. 404 si no.

    Un blueprint de otra organizacion y uno inexistente dan **el mismo 404**: la
    diferencia revelaria que existe.
    """
    fila = (
        db.query(WorkflowBlueprint)
        .filter(
            WorkflowBlueprint.id == blueprint_id,
            WorkflowBlueprint.organization_id == _org_de(user),
        )
        .first()
    )
    if not fila:
        raise HTTPException(404, "Blueprint not found")
    return fila


def version_del_blueprint(
    db: Session, blueprint: WorkflowBlueprint, version: int,
) -> WorkflowBlueprintVersion:
    """Una version concreta de ese blueprint.

    No lleva filtro de organizacion y es correcto: se busca por
    `blueprint_id` de un blueprint que ya se comprobo que es del usuario, asi
    que el ambito llega por la clave padre.
    """
    fila = (
        db.query(WorkflowBlueprintVersion)
        .filter(
            WorkflowBlueprintVersion.blueprint_id == blueprint.id,
            WorkflowBlueprintVersion.version == version,
        )
        .first()
    )
    if not fila:
        raise HTTPException(404, "Version not found")
    return fila


def grafo_de_cabecera(blueprint: WorkflowBlueprint) -> dict:
    """El grafo de la version publicada, o de la ultima creada si no hay.

    Es lo que se clona. Sin ninguna version no hay nada que clonar y se dice.
    """
    cabecera = next((v for v in blueprint.versions if v.is_published), None)
    if cabecera is None:
        cabecera = blueprint.versions[0] if blueprint.versions else None
    if cabecera is None:
        raise HTTPException(400, "Blueprint sin versiones para clonar")
    return json.loads(cabecera.graph_json or "{}")


def list_runs(
    db: Session, user, *, blueprint_id: Optional[str] = None,
    status: Optional[str] = None, limit: int = 50,
) -> list[WorkflowRun]:
    """Las ejecuciones de la organizacion del usuario, mas recientes primero."""
    q = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.organization_id == _org_de(user))
        .order_by(WorkflowRun.started_at.desc())
    )
    if blueprint_id:
        q = q.filter(WorkflowRun.blueprint_id == blueprint_id)
    if status:
        q = q.filter(WorkflowRun.status == status)
    return q.limit(limit).all()


def run_propio(db: Session, user, run_id: str) -> WorkflowRun:
    """La ejecucion, si es de la organizacion del usuario. 404 si no.

    Esta es la guarda que faltaba: `resume` y `cancel` buscaban por id a secas,
    asi que reanudar o **cancelar** una ejecucion dependia solo del filtro
    implicito. Cancelar es una escritura, y una escritura no debe apoyarse en
    una red de seguridad.
    """
    fila = (
        db.query(WorkflowRun)
        .filter(
            WorkflowRun.id == run_id,
            WorkflowRun.organization_id == _org_de(user),
        )
        .first()
    )
    if not fila:
        raise HTTPException(404, "Run not found")
    return fila


def exigir_grafo_valido(graph: dict) -> None:
    """Rechaza un grafo invalido con el detalle de por que.

    El endpoint repetia estas cuatro lineas en dos sitios.
    """
    validacion = validate_graph(graph)
    if not validacion.get("valid"):
        raise HTTPException(
            status_code=400, detail={"message": "invalid graph", **validacion})
