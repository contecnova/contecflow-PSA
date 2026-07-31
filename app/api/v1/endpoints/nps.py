"""
Customer NPS + Health Trend endpoints.

Routes:
  POST /nps/{client_id}/responses          — submit NPS score
  GET  /nps/{client_id}/responses          — list NPS history for a client
  GET  /nps/{client_id}/summary            — NPS score summary + trend
  POST /nps/{client_id}/health-snapshot    — record a health snapshot (admin/pm)
  GET  /nps/{client_id}/health             — health history for a client
  GET  /nps/health/trend                   — aggregate health trend across all clients
  GET  /nps/leaderboard                    — top/bottom clients by health score
"""

from datetime import timedelta
from app.core.timeutil import utcnow
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.responses import APIResponse, APIListResponse
from app.models.user import User, UserRole
from app.services import nps_service

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────

class NPSCreate(BaseModel):
    score:      int = Field(..., ge=0, le=10)
    comment:    Optional[str] = None
    respondent: Optional[str] = None
    source:     str = "manual"


class HealthSnapshotCreate(BaseModel):
    health_score:        float = Field(..., ge=0, le=100)
    nps_component:       Optional[float] = None
    delivery_component:  Optional[float] = None
    budget_component:    Optional[float] = None
    activity_component:  Optional[float] = None
    note:                Optional[str] = None


# ── NPS Routes ───────────────────────────────────────────────────────────

@router.post("/{client_id}/responses", status_code=201)
def submit_nps(
    client_id: str,
    body: NPSCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if not nps_service.client_exists(db, client_id):
        raise HTTPException(404, "Cliente no encontrado")

    entry = nps_service.create_nps_entry(
        db,
        client_id  = client_id,
        score      = body.score,
        comment    = body.comment,
        respondent = body.respondent,
        source     = body.source,
    )
    return APIResponse.ok(data={
        "id":        entry.id,
        "score":     entry.score,
        "category":  entry.category,
        "created_at":entry.created_at,
    })


@router.get("/{client_id}/responses")
def list_nps_responses(
    client_id: str,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rows = nps_service.list_nps_responses(db, client_id, limit)
    return APIListResponse.ok(items=[
        {
            "id":        r.id,
            "score":     r.score,
            "category":  r.category,
            "comment":   r.comment,
            "respondent":r.respondent,
            "source":    r.source,
            "created_at":r.created_at,
        }
        for r in rows
    ])


@router.get("/{client_id}/summary")
def client_nps_summary(
    client_id: str,
    days: int = Query(90, ge=7, le=365),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    cutoff    = utcnow() - timedelta(days=days)
    responses = nps_service.get_nps_responses_since(db, client_id, cutoff)
    summary   = nps_service.compute_nps_summary(responses)
    return APIResponse.ok(data={**summary, "days": days})


# ── Health Snapshot Routes ────────────────────────────────────────────────

@router.post("/{client_id}/health-snapshot", status_code=201)
def create_health_snapshot(
    client_id: str,
    body: HealthSnapshotCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in (UserRole.admin, UserRole.pm):
        raise HTTPException(403, "Solo admins/PMs pueden crear snapshots")
    if not nps_service.client_exists(db, client_id):
        raise HTTPException(404, "Cliente no encontrado")

    snap = nps_service.create_health_snapshot(
        db,
        client_id           = client_id,
        health_score        = body.health_score,
        nps_component       = body.nps_component,
        delivery_component  = body.delivery_component,
        budget_component    = body.budget_component,
        activity_component  = body.activity_component,
        note                = body.note,
    )
    return APIResponse.ok(data={"id": snap.id, "health_score": snap.health_score, "snapshot_at": snap.snapshot_at})


@router.post("/{client_id}/health-compute", status_code=201)
def auto_compute_health(
    client_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Auto-compute health score from current data signals and save a snapshot."""
    if current_user.role not in (UserRole.admin, UserRole.pm):
        raise HTTPException(403, "Solo admins/PMs pueden computar salud")
    if not nps_service.client_exists(db, client_id):
        raise HTTPException(404, "Cliente no encontrado")

    snap = nps_service.compute_and_save_health(db, client_id)
    return APIResponse.ok(data={"id": snap.id, "health_score": snap.health_score, "snapshot_at": snap.snapshot_at})


@router.get("/{client_id}/health")
def client_health_history(
    client_id: str,
    limit: int = Query(30, le=120),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rows = nps_service.get_health_history(db, client_id, limit)
    return APIListResponse.ok(items=[
        {
            "id":                 r.id,
            "health_score":       r.health_score,
            "nps_component":      r.nps_component,
            "delivery_component": r.delivery_component,
            "budget_component":   r.budget_component,
            "activity_component": r.activity_component,
            "note":               r.note,
            "snapshot_at":        r.snapshot_at,
        }
        for r in rows
    ])


# ── Cross-client trend + leaderboard ─────────────────────────────────────

@router.get("/health/trend")
def health_trend_all(
    days: int = Query(90, ge=7, le=365),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Aggregate average health score per week across all clients."""
    cutoff = utcnow() - timedelta(days=days)
    rows   = nps_service.get_health_trend(db, cutoff)

    weekly: dict = {}
    for r in rows:
        week = r.snapshot_at.strftime("%Y-W%W")
        weekly.setdefault(week, []).append(r.health_score)

    return APIListResponse.ok(items=[
        {"week": k, "avg_health": round(sum(v) / len(v), 1), "count": len(v)}
        for k, v in sorted(weekly.items())
    ])


@router.get("/leaderboard")
def health_leaderboard(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Return latest health score per client, ordered best-to-worst."""
    rows = nps_service.get_health_leaderboard(db)
    return APIListResponse.ok(items=[
        {
            "client_id":    snap.client_id,
            "client_name":  name,
            "health_score": snap.health_score,
            "snapshot_at":  snap.snapshot_at,
        }
        for snap, name in rows
    ])
