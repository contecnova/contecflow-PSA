from collections import deque

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models.service_desk import CIRelation, ConfigurationItem
from app.models.user import User
from app.services.service_desk.scoping import scope_ci_query as _scope_ci_query


def _get_scoped_ci_or_404(db: Session, current_user: User, ci_id: str, detail: str = "CI no encontrado"):
    ci = _scope_ci_query(db.query(ConfigurationItem), db, current_user).filter(
        ConfigurationItem.id == ci_id
    ).first()
    if not ci:
        raise HTTPException(404, detail)
    return ci


def get_ci_relations_payload(db: Session, current_user: User, ci_id: str) -> list[dict]:
    _get_scoped_ci_or_404(db, current_user, ci_id)
    visible_ci_ids = _scope_ci_query(
        db.query(ConfigurationItem.id), db, current_user
    ).scalar_subquery()

    relations = db.query(CIRelation).options(
        joinedload(CIRelation.source_ci),
        joinedload(CIRelation.target_ci),
    ).filter(
        or_(CIRelation.source_ci_id == ci_id, CIRelation.target_ci_id == ci_id),
        CIRelation.source_ci_id.in_(visible_ci_ids),
        CIRelation.target_ci_id.in_(visible_ci_ids),
    ).all()

    return [
        {
            "id": r.id,
            "relation_type": r.relation_type.value,
            "source": {
                "id": r.source_ci.id,
                "name": r.source_ci.name,
                "type": r.source_ci.ci_type.value,
            },
            "target": {
                "id": r.target_ci.id,
                "name": r.target_ci.name,
                "type": r.target_ci.ci_type.value,
            },
            "notes": r.notes,
        }
        for r in relations
    ]


def build_ci_relation(db: Session, current_user: User, payload: dict) -> CIRelation:
    src_id = payload.get("source_ci_id")
    tgt_id = payload.get("target_ci_id")
    if not src_id or not tgt_id:
        raise HTTPException(422, "source_ci_id y target_ci_id son obligatorios")

    _get_scoped_ci_or_404(db, current_user, src_id, "CI origen no encontrado")
    _get_scoped_ci_or_404(db, current_user, tgt_id, "CI destino no encontrado")

    rel = CIRelation(
        source_ci_id=src_id,
        target_ci_id=tgt_id,
        relation_type=payload.get("relation_type", "depends_on"),
        notes=payload.get("notes"),
    )
    db.add(rel)
    return rel


def get_ci_impact_payload(
    db: Session,
    current_user: User,
    ci_id: str,
    max_depth: int = 5,
    limit: int = 500,
) -> dict:
    """BFS traversal of the CI dependency graph.

    Args:
        max_depth: Maximum number of hops from the root CI (1 = direct dependents only).
        limit:     Cap on the total number of impacted CIs returned (prevents
                   unbounded results on large CMDBs).

    Returns a dict with::

        {
            "ci_id": str,
            "impacted_count": int,
            "truncated": bool,   # True when limit was hit before full traversal
            "max_depth": int,
            "impacted": [
                {
                    "ci_id": str,
                    "ci_name": str,
                    "ci_type": str,
                    "criticality": str | None,
                    "relation": str,
                    "depth": int,     # hop distance from root
                },
                ...
            ]
        }
    """
    _get_scoped_ci_or_404(db, current_user, ci_id)
    visible_ci_ids = _scope_ci_query(
        db.query(ConfigurationItem.id), db, current_user
    ).scalar_subquery()

    visited: set = set()
    # Queue items: (ci_id, depth)
    queue: deque = deque([(ci_id, 0)])
    impacted: list = []
    truncated = False

    while queue:
        if len(impacted) >= limit:
            truncated = True
            break

        current, depth = queue.popleft()
        if current in visited:
            continue
        visited.add(current)

        if depth >= max_depth:
            continue

        dependents = db.query(CIRelation).filter(
            CIRelation.target_ci_id == current,
            CIRelation.relation_type.in_(["depends_on", "hosts", "part_of"]),
            CIRelation.source_ci_id.in_(visible_ci_ids),
            CIRelation.target_ci_id.in_(visible_ci_ids),
        ).all()

        for dep in dependents:
            if dep.source_ci_id in visited:
                continue
            if len(impacted) >= limit:
                truncated = True
                break

            ci = _scope_ci_query(
                db.query(ConfigurationItem).filter(ConfigurationItem.id == dep.source_ci_id),
                db,
                current_user,
            ).first()
            if ci:
                impacted.append(
                    {
                        "ci_id": ci.id,
                        "ci_name": ci.name,
                        "ci_type": ci.ci_type.value,
                        "criticality": ci.criticality,
                        "relation": dep.relation_type.value,
                        "depth": depth + 1,
                    }
                )
            queue.append((dep.source_ci_id, depth + 1))

    return {
        "ci_id": ci_id,
        "impacted_count": len(impacted),
        "truncated": truncated,
        "max_depth": max_depth,
        "impacted": impacted,
    }


def get_ci_topology_graph_payload(
    db: Session,
    current_user: User,
    ci_id: str,
    radius: int = 2,
    limit: int = 300,
) -> dict:
    """Return topology graph around one CI for frontend graph rendering."""
    root = _get_scoped_ci_or_404(db, current_user, ci_id)
    visible_ci_ids = _scope_ci_query(db.query(ConfigurationItem.id), db, current_user).scalar_subquery()

    queue: deque = deque([(ci_id, 0)])
    visited: set[str] = set()
    nodes: dict[str, dict] = {
        root.id: {
            "id": root.id,
            "name": root.name,
            "ci_type": root.ci_type.value,
            "criticality": root.criticality,
            "is_root": True,
            "depth": 0,
        }
    }
    edges: list[dict] = []

    while queue and len(nodes) < limit:
        current_id, depth = queue.popleft()
        if current_id in visited or depth >= radius:
            continue
        visited.add(current_id)

        rels = (
            db.query(CIRelation)
            .filter(
                or_(CIRelation.source_ci_id == current_id, CIRelation.target_ci_id == current_id),
                CIRelation.source_ci_id.in_(visible_ci_ids),
                CIRelation.target_ci_id.in_(visible_ci_ids),
            )
            .all()
        )

        for rel in rels:
            neighbor_id = rel.target_ci_id if rel.source_ci_id == current_id else rel.source_ci_id
            if neighbor_id not in nodes:
                neighbor = _scope_ci_query(
                    db.query(ConfigurationItem).filter(ConfigurationItem.id == neighbor_id),
                    db,
                    current_user,
                ).first()
                if neighbor:
                    nodes[neighbor.id] = {
                        "id": neighbor.id,
                        "name": neighbor.name,
                        "ci_type": neighbor.ci_type.value,
                        "criticality": neighbor.criticality,
                        "is_root": False,
                        "depth": depth + 1,
                    }
            edge_id = rel.id
            edges.append(
                {
                    "id": edge_id,
                    "source": rel.source_ci_id,
                    "target": rel.target_ci_id,
                    "relation_type": rel.relation_type.value,
                }
            )
            if neighbor_id not in visited:
                queue.append((neighbor_id, depth + 1))

    unique_edges = {e["id"]: e for e in edges}
    return {
        "root_ci_id": ci_id,
        "radius": radius,
        "nodes": list(nodes.values()),
        "edges": list(unique_edges.values()),
        "truncated": len(nodes) >= limit,
    }
