"""
Service Desk — Alert Correlation & Deduplication endpoints (ITSM-P03).

Routes:
  GET  /sd/alert-clusters              — current clusters in the correlation window
  GET  /sd/alert-clusters/stats        — aggregate stats
  POST /sd/alert-clusters/merge        — merge a cluster into a Problem
  POST /sd/alert-clusters/run-scan     — admin: trigger clustering + auto-create Problems
  POST /sd/tickets/{ticket_id}/deduplicate — check / apply deduplication for a ticket
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.responses import APIResponse
from app.core.tenancy import org_scoped_or_404
from app.db.session import get_db
from app.models.user import User

router = APIRouter(tags=["Service Desk - Alert Correlation"])


class MergeClusterIn(BaseModel):
    ticket_ids: list[str] = Field(..., min_length=2)
    auto_rca: bool = True


# ── Cluster endpoints ─────────────────────────────────────────────────────────


@router.get(
    "/alert-clusters",
    summary="Listar clusters de alertas activos",
)
def list_alert_clusters(
    window_hours: int = Query(4, ge=1, le=72, description="Ventana temporal en horas"),
    min_size: int = Query(2, ge=2, le=20, description="Tamaño mínimo del cluster"),
    organization_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return all active alert clusters within the correlation window.

    Clusters are scored using CI affinity, category, priority, temporal proximity,
    and semantic title similarity (when embeddings are available).
    """
    from app.services.service_desk.alert_correlation_service import (
        cluster_open_alerts,
        _enrich_cluster_score,
    )
    from app.models.service_desk import Ticket

    org = organization_id or getattr(current_user, "organization_id", None)
    clusters = cluster_open_alerts(
        db,
        organization_id=org,
        window_hours=window_hours,
        min_cluster_size=min_size,
    )

    # Semantic enrichment
    if clusters:
        all_ids = [tid for c in clusters for tid in c.ticket_ids]
        tickets_map = {t.id: t for t in db.query(Ticket).filter(Ticket.id.in_(all_ids)).all()}
        from app.services.service_desk.alert_correlation_service import _enrich_cluster_score
        clusters = [_enrich_cluster_score(c, tickets_map) for c in clusters]

    return APIResponse.ok(data={
        "window_hours": window_hours,
        "clusters": [
            {
                "cluster_id": c.cluster_id,
                "size": c.size,
                "ticket_ids": c.ticket_ids,
                "ticket_numbers": c.ticket_numbers,
                "ci_id": c.ci_id,
                "category": c.category,
                "priority": c.priority,
                "correlation_score": c.correlation_score,
                "suggested_action": c.suggested_action,
                "root_ci_ids": c.root_ci_ids,
                "earliest_at": c.earliest_at.isoformat() if c.earliest_at else None,
                "latest_at": c.latest_at.isoformat() if c.latest_at else None,
            }
            for c in clusters
        ],
        "total": len(clusters),
    })


@router.get(
    "/alert-clusters/stats",
    summary="Estadísticas de correlación de alertas",
)
def alert_cluster_stats(
    organization_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return aggregate correlation stats for the current window."""
    from app.services.service_desk.alert_correlation_service import get_correlation_stats

    org = organization_id or getattr(current_user, "organization_id", None)
    return APIResponse.ok(data=get_correlation_stats(db, organization_id=org))


@router.post(
    "/alert-clusters/merge",
    summary="Fusionar cluster en un Problema",
    status_code=201,
)
def merge_cluster_to_problem(
    payload: MergeClusterIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a Problem record from a correlation cluster and link all tickets.

    The new Problem will have auto_detected=True and, if auto_rca=True,
    an AI-generated RCA suggestion.
    """
    if current_user.role not in ("admin", "support"):
        raise HTTPException(status_code=403, detail="Only admin/support can merge clusters")

    from app.services.service_desk.alert_correlation_service import merge_cluster_to_problem as _merge
    from app.services.service_desk.ticket_ops_service import commit_or_rollback

    try:
        result = _merge(db, ticket_ids=payload.ticket_ids, current_user=current_user, auto_rca=payload.auto_rca)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True, **result})


@router.post(
    "/alert-clusters/run-scan",
    summary="Ejecutar escaneo de correlación (admin)",
)
def run_correlation_scan(
    organization_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Admin-only: trigger a full alert correlation scan.

    High-confidence clusters (score >= 0.65, size >= 3) automatically
    generate Problem records if none already exist.
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    from app.services.service_desk.alert_correlation_service import run_correlation_scan_job

    org = organization_id or getattr(current_user, "organization_id", None)
    return APIResponse.ok(data=run_correlation_scan_job(db, organization_id=org))


# ── Per-ticket deduplication ──────────────────────────────────────────────────


@router.post(
    "/tickets/{ticket_id}/deduplicate",
    summary="Verificar y aplicar deduplicación a un ticket",
)
def deduplicate_ticket(
    ticket_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Check whether *ticket_id* is a duplicate of an existing open ticket
    (same CI + category + priority within the deduplication window) and,
    if so, create a 'duplicates' link to the parent.

    Returns: {is_duplicate, parent_ticket_id, parent_number}
    """
    from app.models.service_desk import Ticket
    from app.services.service_desk.incident_intelligence_service import deduplicate_new_ticket
    from app.services.service_desk.ticket_ops_service import commit_or_rollback

    ticket = org_scoped_or_404(db, Ticket, ticket_id, current_user, detail="Ticket not found")

    result = deduplicate_new_ticket(db, ticket, acting_user_id=current_user.id)
    commit_or_rollback(db)
    return APIResponse.ok(data=result)
