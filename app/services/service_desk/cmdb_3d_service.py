"""
cmdb_3d_service.py — CMDB 3D dependency mapping and Asset-CMDB impact linking.

Provides:
  - 3D graph data for dependency visualization (nodes with x,y,z positions)
  - Blast radius calculation from a CI (Configuration Item)
  - Asset ↔ CMDB CI linking with impact propagation
  - Impact path tracing (which assets/services are affected by a CI failure)
"""
from __future__ import annotations

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
    # Try to load from CMDB models if available
    try:
        from app.models.service_desk import ConfigurationItem, CIRelationship
        cis = db.query(ConfigurationItem).limit(max_nodes).all()
        rels = db.query(CIRelationship).limit(max_nodes * 2).all()

        nodes = []
        for i, ci in enumerate(cis):
            layer = ci.layer if hasattr(ci, "layer") else (i % 4)
            angle = (i / max(len(cis), 1)) * 2 * math.pi
            r = 50 + layer * 30
            nodes.append({
                "id": ci.id,
                "name": ci.name if hasattr(ci, "name") else ci.id,
                "type": ci.ci_type if hasattr(ci, "ci_type") else "unknown",
                "layer": layer,
                "layer_label": LAYER_LABELS.get(layer, "Unknown"),
                "x": round(r * math.cos(angle), 2),
                "y": round(layer * 60 - 90, 2),
                "z": round(r * math.sin(angle), 2),
                "status": ci.status if hasattr(ci, "status") else "active",
            })

        edges = [
            {"source": r.source_ci_id, "target": r.target_ci_id, "type": r.relationship_type if hasattr(r, "relationship_type") else "depends_on"}
            for r in rels
        ]

    except Exception:
        # Fallback demo data
        nodes = _generate_demo_nodes()
        edges = _generate_demo_edges(nodes)

    return {
        "nodes": nodes,
        "edges": edges,
        "layers": LAYER_LABELS,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


def _generate_demo_nodes() -> list[dict]:
    demo = [
        ("ci-db-01", "PostgreSQL Primary", "database", 0),
        ("ci-db-02", "PostgreSQL Replica", "database", 0),
        ("ci-app-01", "App Server A", "application", 2),
        ("ci-app-02", "App Server B", "application", 2),
        ("ci-lb-01", "Load Balancer", "network", 1),
        ("ci-cache-01", "Redis Cache", "platform", 1),
        ("ci-svc-crm", "CRM Service", "service", 3),
        ("ci-svc-itsm", "ITSM Service", "service", 3),
    ]
    nodes = []
    for i, (nid, name, typ, layer) in enumerate(demo):
        angle = (i / len(demo)) * 2 * math.pi
        r = 50 + layer * 30
        nodes.append({
            "id": nid, "name": name, "type": typ, "layer": layer,
            "layer_label": LAYER_LABELS.get(layer, "Unknown"),
            "x": round(r * math.cos(angle), 2),
            "y": round(layer * 60 - 90, 2),
            "z": round(r * math.sin(angle), 2),
            "status": "active",
        })
    return nodes


def _generate_demo_edges(nodes: list[dict]) -> list[dict]:
    pairs = [
        ("ci-lb-01", "ci-app-01"), ("ci-lb-01", "ci-app-02"),
        ("ci-app-01", "ci-db-01"), ("ci-app-02", "ci-db-01"),
        ("ci-db-01", "ci-db-02"), ("ci-app-01", "ci-cache-01"),
        ("ci-svc-crm", "ci-lb-01"), ("ci-svc-itsm", "ci-lb-01"),
    ]
    return [{"source": s, "target": t, "type": "depends_on"} for s, t in pairs]


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
    adj: dict[str, list[str]] = {}
    for e in edges:
        # If target depends on source, then if source fails, target is impacted
        adj.setdefault(e["source"], []).append(e["target"])

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
