"""Alert Correlation Service — ML clustering by CI + temporal window + semantic similarity.

Agrupa alertas/tickets abiertos en clusters basándose en:
  - CI afectado (ci_id)
  - Categoría
  - Prioridad numérica
  - Proximidad temporal (ventana configurable)
  - Similitud semántica del título (embedding cosine, si disponible)

Cuando hay sklearn disponible usa DBSCAN; en caso contrario usa un algoritmo
greedy basado en distancia euclidiana.

API pública:
  cluster_open_alerts(db, organization_id, window_hours) → list[AlertCluster]
  merge_cluster_to_problem(db, ticket_ids, current_user)  → Problem
  get_correlation_stats(db, organization_id)              → dict
  run_correlation_scan_job(db)                            → dict  (Celery task)
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.service_desk import Ticket, TicketStatus, TicketPriority
from app.models.user import User

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_WINDOW_HOURS = 4          # only consider tickets created within this window
MIN_CLUSTER_SIZE = 2              # min tickets for a cluster to be actionable
DBSCAN_EPS = 0.35                 # DBSCAN neighborhood radius (0-1 feature space)
DBSCAN_MIN_SAMPLES = 2            # DBSCAN min neighbours to form core point


def _apply_org_scope(q, db: Session, organization_id: Optional[str]):
    """Scope ticket query to an organization without relying on Ticket.organization_id.

    Service Desk tickets are scoped indirectly through related users/projects.
    """
    if not organization_id:
        return q

    org_user_ids = db.query(User.id).filter(User.organization_id == organization_id).scalar_subquery()
    org_project_ids = db.query(Project.id).filter(Project.organization_id == organization_id).scalar_subquery()

    return q.filter(
        or_(
            Ticket.requester_user_id.in_(org_user_ids),
            Ticket.assigned_to_user_id.in_(org_user_ids),
            Ticket.created_by_user_id.in_(org_user_ids),
            Ticket.project_id.in_(org_project_ids),
        )
    )


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class AlertCluster:
    cluster_id: str                        # deterministic hash of member ids
    ticket_ids: list[str]
    ticket_numbers: list[str]
    ci_id: Optional[str]
    category: Optional[str]
    priority: str
    earliest_at: datetime
    latest_at: datetime
    size: int
    correlation_score: float               # 0-1; higher = more tightly correlated
    suggested_action: str                  # "create_problem" | "review" | "monitor"
    root_ci_ids: list[str] = field(default_factory=list)  # CIs in dependency chain


# ── Feature engineering ───────────────────────────────────────────────────────

_PRIORITY_NUM = {
    TicketPriority.p1_critical: 1.0,
    TicketPriority.p2_high:     0.75,
    TicketPriority.p3_medium:   0.50,
    TicketPriority.p4_low:      0.25,
}


def _ci_hash(ci_id: Optional[str]) -> float:
    """Map CI id to a stable float in [0, 1] for feature vector."""
    if not ci_id:
        return 0.0
    digest = int(hashlib.md5(ci_id.encode(), usedforsecurity=False).hexdigest()[:8], 16)
    return (digest % 10_000) / 10_000.0


def _category_hash(category: Optional[str]) -> float:
    if not category:
        return 0.0
    digest = int(hashlib.md5(category.lower().encode(), usedforsecurity=False).hexdigest()[:8], 16)
    return (digest % 10_000) / 10_000.0


def _ticket_category(t) -> Optional[str]:
    """Devuelve un identificador estable de "categoría" para un Ticket usando
    la mejor fuente disponible: service_item.category_id si está enlazado,
    de lo contrario el ticket_type.

    FIX: ``Ticket`` no expone una columna ``category`` directa — el atributo
    estaba mal asumido y rompía clustering / stats con AttributeError. La
    semántica que el clustering necesita es solo un discriminador estable,
    cualquiera de los dos sirve.
    """
    if t is None:
        return None
    try:
        si = getattr(t, "service_item", None)
        cat_id = getattr(si, "category_id", None) if si is not None else None
        if cat_id:
            return str(cat_id)
    # intentional: best-effort fallback, log noise outweighs diagnostic value
    except Exception:
        pass
    tt = getattr(t, "ticket_type", None)
    if tt is None:
        return None
    return str(getattr(tt, "value", tt))


def _time_offset(created_at: Optional[datetime], window_start: datetime) -> float:
    """Return fraction of window elapsed (0-1) at ticket creation time."""
    if not created_at:
        return 0.5
    delta = (created_at - window_start).total_seconds()
    window_seconds = DEFAULT_WINDOW_HOURS * 3600
    return max(0.0, min(1.0, delta / window_seconds))


def _build_feature_matrix(tickets: list[Ticket], window_start: datetime) -> list[list[float]]:
    """Build a (n_tickets × 4) feature matrix.

    Features: [ci_hash, category_hash, priority_num, time_offset]
    """
    return [
        [
            _ci_hash(t.ci_id),
            _category_hash(_ticket_category(t)),
            _PRIORITY_NUM.get(t.priority, 0.5),
            _time_offset(t.created_at, window_start),
        ]
        for t in tickets
    ]


# ── Clustering ────────────────────────────────────────────────────────────────

def _dbscan_labels(X: list[list[float]]) -> list[int]:
    """Run DBSCAN via sklearn. Returns per-sample cluster labels (-1 = noise)."""
    try:
        from sklearn.cluster import DBSCAN  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415
        arr = np.array(X, dtype=float)
        labels = DBSCAN(eps=DBSCAN_EPS, min_samples=DBSCAN_MIN_SAMPLES, metric="euclidean").fit_predict(arr)
        return labels.tolist()
    except ImportError:
        logger.debug("sklearn not available — using greedy fallback clustering")
        return _greedy_labels(X)


def _euclidean(a: list[float], b: list[float]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def _greedy_labels(X: list[list[float]]) -> list[int]:
    """Simple greedy clustering: same CI + same category → same cluster."""
    labels = [-1] * len(X)
    cluster_id = 0
    assigned: set[int] = set()
    for i in range(len(X)):
        if i in assigned:
            continue
        group = [i]
        for j in range(i + 1, len(X)):
            if j in assigned:
                continue
            dist = _euclidean(X[i], X[j])
            if dist <= DBSCAN_EPS:
                group.append(j)
        if len(group) >= DBSCAN_MIN_SAMPLES:
            for idx in group:
                labels[idx] = cluster_id
                assigned.add(idx)
            cluster_id += 1
    return labels


# ── CI dependency expansion ───────────────────────────────────────────────────

def _expand_ci_dependencies(db: Session, ci_ids: list[str]) -> list[str]:
    """Return the set of root CIs that the given CIs depend on (1 hop)."""
    if not ci_ids:
        return []
    try:
        from app.models.cmdb import CMDBRelation  # noqa: PLC0415
        rows = (
            db.query(CMDBRelation.target_ci_id)
            .filter(
                CMDBRelation.source_ci_id.in_(ci_ids),
                CMDBRelation.relation_type.in_(["depends_on", "runs_on"]),
            )
            .all()
        )
        return [r[0] for r in rows if r[0]]
    except Exception as exc:  # noqa: BLE001
        logger.debug("CI dependency expansion failed: %s", exc)
        return []


# ── Public API ────────────────────────────────────────────────────────────────

def cluster_open_alerts(
    db: Session,
    *,
    organization_id: Optional[str] = None,
    window_hours: int = DEFAULT_WINDOW_HOURS,
    min_cluster_size: int = MIN_CLUSTER_SIZE,
) -> list[AlertCluster]:
    """Cluster open tickets/alerts by CI + category + temporal proximity.

    Only considers tickets created within *window_hours* that are still open
    (not resolved/closed/cancelled) and not already linked to a Problem.

    Returns a list of AlertCluster objects sorted by size descending.
    """
    window_start = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    q = db.query(Ticket).filter(
        Ticket.status.not_in(
            [TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled]
        ),
        Ticket.problem_id.is_(None),
        Ticket.created_at >= window_start,
    )
    q = _apply_org_scope(q, db, organization_id)

    tickets = q.order_by(Ticket.created_at.asc()).all()

    if len(tickets) < min_cluster_size:
        return []

    X = _build_feature_matrix(tickets, window_start)
    labels = _dbscan_labels(X)

    # Group tickets by cluster label (ignore noise label -1)
    groups: dict[int, list[Ticket]] = {}
    for ticket, label in zip(tickets, labels):
        if label == -1:
            continue
        groups.setdefault(label, []).append(ticket)

    clusters: list[AlertCluster] = []
    for _label, members in groups.items():
        if len(members) < min_cluster_size:
            continue

        ticket_ids = [t.id for t in members]
        cluster_hash = hashlib.md5(
            ":".join(sorted(ticket_ids)).encode(), usedforsecurity=False
        ).hexdigest()[:12]

        # Compute correlation score: fraction of members sharing same CI+category
        ci_ids = [t.ci_id for t in members if t.ci_id]
        # FIX: usar helper _ticket_category — Ticket no tiene .category directa.
        member_cats = [_ticket_category(t) for t in members]
        categories = [c for c in member_cats if c]
        dominant_ci = max(set(ci_ids), key=ci_ids.count) if ci_ids else None
        dominant_cat = max(set(categories), key=categories.count) if categories else None
        same_ci = sum(1 for t in members if t.ci_id == dominant_ci) / len(members) if dominant_ci else 0.0
        same_cat = sum(1 for c in member_cats if c == dominant_cat) / len(members) if dominant_cat else 0.0
        correlation_score = round((same_ci * 0.6 + same_cat * 0.4), 3)

        priorities = [t.priority for t in members if t.priority]
        top_priority = priorities[0] if priorities else "p3_medium"
        for p in priorities:
            if _PRIORITY_NUM.get(p, 0) > _PRIORITY_NUM.get(top_priority, 0):
                top_priority = p

        timestamps = [t.created_at for t in members if t.created_at]
        earliest = min(timestamps) if timestamps else datetime.now(timezone.utc)
        latest = max(timestamps) if timestamps else datetime.now(timezone.utc)

        # CI dependency expansion for root cause hint
        root_cis = _expand_ci_dependencies(db, [c for c in ci_ids if c])

        if correlation_score >= 0.70 and len(members) >= 3:
            action = "create_problem"
        elif correlation_score >= 0.40:
            action = "review"
        else:
            action = "monitor"

        clusters.append(AlertCluster(
            cluster_id=cluster_hash,
            ticket_ids=ticket_ids,
            ticket_numbers=[t.number for t in members],
            ci_id=dominant_ci,
            category=dominant_cat,
            priority=str(top_priority),
            earliest_at=earliest,
            latest_at=latest,
            size=len(members),
            correlation_score=correlation_score,
            suggested_action=action,
            root_ci_ids=root_cis,
        ))

    clusters.sort(key=lambda c: (c.size, c.correlation_score), reverse=True)
    return clusters


def merge_cluster_to_problem(
    db: Session,
    *,
    ticket_ids: list[str],
    current_user,
    auto_rca: bool = True,
) -> dict:
    """Create a Problem from a correlation cluster and link all tickets.

    Delegates to problem_service.create_problem_from_correlation.
    Does NOT commit — caller must commit.
    """
    from app.services.service_desk.problem_service import create_problem_from_correlation  # noqa: PLC0415

    # Infer category and priority from the tickets
    tickets = db.query(Ticket).filter(Ticket.id.in_(ticket_ids)).all()
    if not tickets:
        raise ValueError("No se encontraron tickets para el cluster")

    # FIX: helper para evitar AttributeError ('Ticket' no tiene .category directa)
    categories = [c for c in (_ticket_category(t) for t in tickets) if c]
    category = max(set(categories), key=categories.count) if categories else "general"

    priorities = [t.priority for t in tickets if t.priority]
    priority = str(priorities[0]) if priorities else "p3_medium"
    for p in priorities:
        if _PRIORITY_NUM.get(p, 0) > _PRIORITY_NUM.get(priority, 0):
            priority = str(p)

    problem = create_problem_from_correlation(
        db,
        ticket_ids=ticket_ids,
        category=category,
        priority=priority,
        auto_rca=auto_rca,
    )
    return {"problem_id": problem.id, "problem_number": problem.number, "linked_tickets": len(ticket_ids)}


def get_correlation_stats(db: Session, *, organization_id: Optional[str] = None) -> dict:
    """Return stats about recent alert correlation patterns."""
    window_start = datetime.now(timezone.utc) - timedelta(hours=DEFAULT_WINDOW_HOURS)

    q = db.query(Ticket).filter(
        Ticket.status.not_in([TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled]),
        Ticket.created_at >= window_start,
    )
    q = _apply_org_scope(q, db, organization_id)

    open_tickets = q.count()
    clusters = cluster_open_alerts(db, organization_id=organization_id)
    tickets_in_clusters = sum(c.size for c in clusters)

    return {
        "window_hours": DEFAULT_WINDOW_HOURS,
        "open_tickets_in_window": open_tickets,
        "clusters_detected": len(clusters),
        "tickets_in_clusters": tickets_in_clusters,
        "tickets_needing_problem": sum(1 for c in clusters if c.suggested_action == "create_problem"),
        "top_clusters": [
            {
                "cluster_id": c.cluster_id,
                "size": c.size,
                "ci_id": c.ci_id,
                "category": c.category,
                "priority": c.priority,
                "correlation_score": c.correlation_score,
                "suggested_action": c.suggested_action,
                "ticket_numbers": c.ticket_numbers,
                "root_ci_ids": c.root_ci_ids,
            }
            for c in clusters[:10]
        ],
    }


# ── Semantic similarity enrichment ────────────────────────────────────────────

def _semantic_score(tickets: list[Ticket]) -> float:
    """Compute average pairwise cosine similarity of ticket titles/descriptions.

    Returns a score in [0, 1]. Falls back to 0.0 if embeddings are unavailable.
    Capped at 10 pairs for performance (sample from largest cluster).
    """
    if len(tickets) < 2:
        return 0.0
    try:
        from app.services.service_desk.incident_intelligence_service import (  # noqa: PLC0415
            _embed_text,
            _cosine_similarity,
        )
        sample = tickets[:5]  # limit to 5 to avoid O(n²) blowup
        texts = [f"{t.title or ''} {t.description or ''}"[:300] for t in sample]
        embeddings = [_embed_text(tx) for tx in texts]
        sims = []
        for i in range(len(embeddings)):
            for j in range(i + 1, len(embeddings)):
                sims.append(_cosine_similarity(embeddings[i], embeddings[j]))
        return round(sum(sims) / len(sims), 3) if sims else 0.0
    except Exception:
        return 0.0


def _enrich_cluster_score(cluster: AlertCluster, tickets_by_id: dict[str, Ticket]) -> AlertCluster:
    """Re-score a cluster by blending structural score with semantic similarity."""
    members = [tickets_by_id[tid] for tid in cluster.ticket_ids if tid in tickets_by_id]
    sem = _semantic_score(members)
    # Blend: 70% structural, 30% semantic
    blended = round(cluster.correlation_score * 0.70 + sem * 0.30, 3)
    cluster.correlation_score = blended

    # Re-evaluate suggested action with richer score
    if blended >= 0.65 and cluster.size >= 3:
        cluster.suggested_action = "create_problem"
    elif blended >= 0.35:
        cluster.suggested_action = "review"
    else:
        cluster.suggested_action = "monitor"

    return cluster


# ── Auto-scan job ─────────────────────────────────────────────────────────────

def run_correlation_scan_job(db: Session, *, organization_id: Optional[str] = None) -> dict:
    """Celery-callable job: cluster alerts and auto-create Problems where warranted.

    For each cluster with suggested_action == "create_problem":
    - Checks no existing open Problem already covers those tickets
    - Calls merge_cluster_to_problem() and commits

    Returns: {clusters_found, problems_created, errors}
    """
    clusters = cluster_open_alerts(db, organization_id=organization_id, window_hours=DEFAULT_WINDOW_HOURS)

    # Semantic enrichment pass
    if clusters:
        all_ticket_ids: list[str] = []
        for c in clusters:
            all_ticket_ids.extend(c.ticket_ids)
        tickets_map: dict[str, Ticket] = {
            t.id: t
            for t in db.query(Ticket).filter(Ticket.id.in_(all_ticket_ids)).all()
        }
        clusters = [_enrich_cluster_score(c, tickets_map) for c in clusters]

    stats = {"clusters_found": len(clusters), "problems_created": 0, "errors": 0}

    for cluster in clusters:
        if cluster.suggested_action != "create_problem":
            continue

        # Skip if any ticket already linked to a Problem
        already_linked = (
            db.query(Ticket)
            .filter(
                Ticket.id.in_(cluster.ticket_ids),
                Ticket.problem_id.isnot(None),
            )
            .count()
        )
        if already_linked:
            continue

        try:
            result = merge_cluster_to_problem(db, ticket_ids=cluster.ticket_ids, current_user=None)
            db.commit()
            logger.info(
                "Alert correlation: auto-created Problem %s for cluster %s (%d tickets)",
                result["problem_number"],
                cluster.cluster_id,
                cluster.size,
            )
            stats["problems_created"] += 1
        except Exception as exc:
            db.rollback()
            logger.error("Alert correlation: failed to create Problem for cluster %s: %s", cluster.cluster_id, exc)
            stats["errors"] += 1

    return stats
