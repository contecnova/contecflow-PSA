"""
cmdb_3d_service.py — CMDB 3D dependency mapping and Asset-CMDB impact linking.

Provides:
  - 3D graph data for dependency visualization (nodes with x,y,z positions)
  - Blast radius calculation from a CI (Configuration Item)
  - Asset ↔ CMDB CI linking with impact propagation
  - Impact path tracing (which assets/services are affected by a CI failure)
"""
from __future__ import annotations
import logging

import json
import math
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.settings import AppSetting

_KEY_3D_LAYOUT = "sd.cmdb.3d_layout"
_KEY_ASSET_LINKS = "sd.cmdb.asset_links"

LAYER_LABELS = {
    0: "Infrastructure",
    1: "Platform",
    2: "Application",
    3: "Business Service",
}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get(db: Session, key: str, org_id: Optional[str], default: Any) -> Any:
    q = db.query(AppSetting).filter(AppSetting.key == key)
    q = q.filter(AppSetting.organization_id == org_id) if org_id else q.filter(AppSetting.organization_id.is_(None))
    row = q.first()
    if not row or not row.value:
        return default
    try:
        return json.loads(row.value)
    except Exception:
        logging.getLogger(__name__).debug("_get: excepcion ignorada", exc_info=True)
        return default


def _set(db: Session, key: str, org_id: Optional[str], value: Any) -> None:
    payload = json.dumps(value, ensure_ascii=False)
    q = db.query(AppSetting).filter(AppSetting.key == key)
    q = q.filter(AppSetting.organization_id == org_id) if org_id else q.filter(AppSetting.organization_id.is_(None))
    row = q.first()
    if not row:
        row = AppSetting(key=key, organization_id=org_id, value=payload, description=f"CMDB 3D: {key}")
        db.add(row)
    else:
        row.value = payload
    db.commit()


def get_3d_graph(
    db: Session,
    *,
    org_id: Optional[str],
    max_nodes: int = 200,
) -> dict[str, Any]:
    """
    Return 3D graph data for the CMDB dependency map.
    Nodes have x,y,z positions based on layer and cluster layout.
    """
    # Layer mapping: ci_type -> layer index for visualization
    _CI_TYPE_LAYER = {
        "server": 0, "database": 0,
        "network": 1, "integration": 1,
        "application": 2, "module": 2,
        "service": 3, "other": 3,
    }

    # Segunda auditoria 2026-11: `org_id` se ignoraba (solo protegia la
    # TenantSession, que no filtra al superadmin) y, si la organizacion no
    # tenia CIs —o si la consulta fallaba—, se devolvian 8 CIs de demostracion
    # inventados como si fueran reales. Ahora se filtra por la organizacion y
    # un CMDB vacio es un grafo vacio: estado honesto, que la pantalla pinta
    # como "sin datos". Un error de base de datos ya no se disfraza.
    from app.models.service_desk import ConfigurationItem, CIRelation
    q_cis = db.query(ConfigurationItem)
    q_rels = db.query(CIRelation)
    if org_id:
        q_cis = q_cis.filter(ConfigurationItem.organization_id == org_id)
        q_rels = q_rels.filter(CIRelation.organization_id == org_id)
    cis = q_cis.order_by(ConfigurationItem.name).limit(max_nodes).all()
    ids = {ci.id for ci in cis}
    # Solo aristas entre nodos devueltos: una arista hacia un CI que no esta
    # en el grafo no se puede pintar.
    rels = q_rels.filter(
        CIRelation.source_ci_id.in_(ids), CIRelation.target_ci_id.in_(ids),
    ).limit(max_nodes * 2).all() if ids else []

    nodes = []
    for i, ci in enumerate(cis):
        ci_type_val = ci.ci_type.value if hasattr(ci.ci_type, 'value') else str(ci.ci_type)
        layer = _CI_TYPE_LAYER.get(ci_type_val, i % 4)
        angle = (i / max(len(cis), 1)) * 2 * math.pi
        r = 50 + layer * 30
        nodes.append({
            "id": ci.id,
            "name": ci.name,
            "type": ci_type_val,
            "layer": layer,
            "layer_label": LAYER_LABELS.get(layer, "Unknown"),
            "x": round(r * math.cos(angle), 2),
            "y": round(layer * 60 - 90, 2),
            "z": round(r * math.sin(angle), 2),
            "status": ci.status.value if hasattr(ci.status, 'value') else str(ci.status),
        })

    edges = [
        {"source": r.source_ci_id, "target": r.target_ci_id, "type": r.relation_type.value if hasattr(r.relation_type, 'value') else str(r.relation_type)}
        for r in rels
    ]

    return {
        "nodes": nodes,
        "edges": edges,
        "layers": LAYER_LABELS,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


def calculate_blast_radius(
    db: Session,
    *,
    org_id: Optional[str],
    ci_id: str,
    max_depth: int = 5,
) -> dict[str, Any]:
    """Calculate which CIs/services are impacted if ci_id fails."""
    graph = get_3d_graph(db, org_id=org_id)
    edges = graph["edges"]
    nodes_map = {n["id"]: n for n in graph["nodes"]}

    # BFS from ci_id following dependency edges (what depends ON this CI)
    # Auditoria 2026-11-22 (A-SD20): iba al reves (de origen a destino). En
    # `A depends_on B` el que depende es el ORIGEN: si cae B, cae A. Se recorre
    # de destino a origen y con los mismos tipos que el analisis de impacto de
    # `cmdb_relation_service.get_ci_impact_payload`, para que los dos digan lo mismo.
    tipos_de_impacto = {"depends_on", "hosts", "part_of"}
    adj: dict[str, list[str]] = {}
    for e in edges:
        if e.get("type") in tipos_de_impacto:
            adj.setdefault(e["target"], []).append(e["source"])

    visited: set[str] = set()
    queue = [(ci_id, 0)]
    impacted = []

    while queue:
        node_id, depth = queue.pop(0)
        if node_id in visited or depth > max_depth:
            continue
        visited.add(node_id)
        if node_id != ci_id:
            info = nodes_map.get(node_id, {"id": node_id, "name": node_id, "type": "unknown"})
            impacted.append({**info, "impact_depth": depth})
        for neighbor in adj.get(node_id, []):
            if neighbor not in visited:
                queue.append((neighbor, depth + 1))

    return {
        "ci_id": ci_id,
        "ci_name": nodes_map.get(ci_id, {}).get("name", ci_id),
        "impacted_count": len(impacted),
        "impacted_cis": impacted,
        "max_depth_reached": max_depth,
    }


# ── Asset ↔ CMDB CI linking ───────────────────────────────────────────────────

def link_asset_to_ci(
    db: Session,
    *,
    org_id: Optional[str],
    asset_id: str,
    ci_id: str,
    link_type: str = "physical_to_logical",
    notes: Optional[str] = None,
    created_by: str,
) -> dict:
    links: list = _get(db, _KEY_ASSET_LINKS, org_id, [])
    # Check for existing link
    existing = next((l for l in links if l["asset_id"] == asset_id and l["ci_id"] == ci_id), None)
    if existing:
        return existing
    entry = {
        "id": str(uuid.uuid4()),
        "asset_id": asset_id,
        "ci_id": ci_id,
        "link_type": link_type,
        "notes": notes,
        "created_by": created_by,
        "created_at": _iso_now(),
    }
    links.append(entry)
    _set(db, _KEY_ASSET_LINKS, org_id, links)
    return entry


def get_asset_impact(
    db: Session,
    *,
    org_id: Optional[str],
    asset_id: str,
) -> dict[str, Any]:
    """Return all CIs linked to an asset and their blast radius."""
    links: list = _get(db, _KEY_ASSET_LINKS, org_id, [])
    asset_links = [l for l in links if l["asset_id"] == asset_id]

    impacts = []
    for link in asset_links:
        blast = calculate_blast_radius(db, org_id=org_id, ci_id=link["ci_id"])
        impacts.append({
            "link": link,
            "blast_radius": blast,
        })

    return {
        "asset_id": asset_id,
        "linked_ci_count": len(asset_links),
        "total_impacted_cis": sum(i["blast_radius"]["impacted_count"] for i in impacts),
        "impacts": impacts,
    }


def list_asset_links(db: Session, *, org_id: Optional[str]) -> list[dict]:
    return _get(db, _KEY_ASSET_LINKS, org_id, [])
