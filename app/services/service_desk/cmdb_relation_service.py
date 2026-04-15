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

    return CIRelation(
        source_ci_id=src_id,
        target_ci_id=tgt_id,
        relation_type=payload.get("relation_type", "depends_on"),
        notes=payload.get("notes"),
    )


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
