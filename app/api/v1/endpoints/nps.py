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

from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.nps import ClientNPS, ClientHealthSnapshot, NPSCategory
from app.models.clients import Client
from app.models.user import User, UserRole

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


# ── Helpers ──────────────────────────────────────────────────────────────

def _nps_category(score: int) -> NPSCategory:
    if score >= 9:
        return NPSCategory.promoter
    if score >= 7:
        return NPSCategory.passive
    return NPSCategory.detractor


def _compute_nps(responses: List[ClientNPS]) -> Optional[float]:
    """Standard NPS formula: %promoters - %detractors (range -100 to 100)."""
    if not responses:
        return None
    total = len(responses)
    promoters  = sum(1 for r in responses if r.category == NPSCategory.promoter)
    detractors = sum(1 for r in responses if r.category == NPSCategory.detractor)
    return round((promoters - detractors) / total * 100, 1)


def _compute_health(client_id, db: Session) -> float:
    """Compute composite health score from latest NPS + delivery/budget signals."""
    # NPS component (last 90 days)
    cutoff = datetime.utcnow() - timedelta(days=90)
    responses = db.query(ClientNPS).filter(
        ClientNPS.client_id == client_id,
        ClientNPS.created_at >= cutoff,
    ).all()
    nps_score = _compute_nps(responses)
    # Map NPS (-100..100) → 0-100
    nps_component = ((nps_score or 0) + 100) / 2 if nps_score is not None else 50.0

    # Other components: use 70 as neutral default when no data
    health = round((nps_component * 0.4) + (70 * 0.2) + (70 * 0.2) + (70 * 0.2), 1)
    return min(max(health, 0), 100)


# ── NPS Routes ───────────────────────────────────────────────────────────

@router.post("/{client_id}/responses", status_code=201)
def submit_nps(
    client_id: str,
    body: NPSCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if not db.query(Client).filter(Client.id == client_id).first():
        raise HTTPException(404, "Cliente no encontrado")

    entry = ClientNPS(
        client_id  = client_id,
        score      = body.score,
        category   = _nps_category(body.score),
        comment    = body.comment,
        respondent = body.respondent,
        source     = body.source,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return {
        "id":        entry.id,
        "score":     entry.score,
        "category":  entry.category,
        "created_at":entry.created_at,
    }


@router.get("/{client_id}/responses")
def list_nps_responses(
    client_id: str,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rows = (
        db.query(ClientNPS)
        .filter(ClientNPS.client_id == client_id)
        .order_by(ClientNPS.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
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
    ]


@router.get("/{client_id}/summary")
def client_nps_summary(
    client_id: str,
    days: int = Query(90, ge=7, le=365),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    cutoff = datetime.utcnow() - timedelta(days=days)
    responses = db.query(ClientNPS).filter(
        ClientNPS.client_id == client_id,
        ClientNPS.created_at >= cutoff,
    ).order_by(ClientNPS.created_at).all()

    nps = _compute_nps(responses)
    promoters  = sum(1 for r in responses if r.category == NPSCategory.promoter)
    passives   = sum(1 for r in responses if r.category == NPSCategory.passive)
    detractors = sum(1 for r in responses if r.category == NPSCategory.detractor)

    # Monthly breakdown for trend chart
    monthly: dict = {}
    for r in responses:
        key = r.created_at.strftime("%Y-%m")
        if key not in monthly:
            monthly[key] = []
        monthly[key].append(r)

    trend = [
        {"month": k, "nps": _compute_nps(v), "count": len(v)}
        for k, v in sorted(monthly.items())
    ]

    return {
        "nps":        nps,
        "total":      len(responses),
        "promoters":  promoters,
        "passives":   passives,
        "detractors": detractors,
        "trend":      trend,
        "days":       days,
    }


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
    if not db.query(Client).filter(Client.id == client_id).first():
        raise HTTPException(404, "Cliente no encontrado")

    snap = ClientHealthSnapshot(
        client_id           = client_id,
        health_score        = body.health_score,
        nps_component       = body.nps_component,
        delivery_component  = body.delivery_component,
        budget_component    = body.budget_component,
        activity_component  = body.activity_component,
        note                = body.note,
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return {"id": snap.id, "health_score": snap.health_score, "snapshot_at": snap.snapshot_at}


@router.post("/{client_id}/health-compute", status_code=201)
def auto_compute_health(
    client_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Auto-compute health score from current data signals and save a snapshot."""
    if current_user.role not in (UserRole.admin, UserRole.pm):
        raise HTTPException(403, "Solo admins/PMs pueden computar salud")
    if not db.query(Client).filter(Client.id == client_id).first():
        raise HTTPException(404, "Cliente no encontrado")

    score = _compute_health(client_id, db)
    snap = ClientHealthSnapshot(client_id=client_id, health_score=score, note="Auto-computed")
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return {"id": snap.id, "health_score": snap.health_score, "snapshot_at": snap.snapshot_at}


@router.get("/{client_id}/health")
def client_health_history(
    client_id: str,
    limit: int = Query(30, le=120),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rows = (
        db.query(ClientHealthSnapshot)
        .filter(ClientHealthSnapshot.client_id == client_id)
        .order_by(ClientHealthSnapshot.snapshot_at.desc())
        .limit(limit)
        .all()
    )
    return [
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
    ]


# ── Cross-client trend + leaderboard ─────────────────────────────────────

@router.get("/health/trend")
def health_trend_all(
    days: int = Query(90, ge=7, le=365),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Aggregate average health score per week across all clients."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = (
        db.query(ClientHealthSnapshot)
        .filter(ClientHealthSnapshot.snapshot_at >= cutoff)
        .order_by(ClientHealthSnapshot.snapshot_at)
        .all()
    )
    # Group by ISO week
    weekly: dict = {}
    for r in rows:
        week = r.snapshot_at.strftime("%Y-W%W")
        if week not in weekly:
            weekly[week] = []
        weekly[week].append(r.health_score)

    return [
        {"week": k, "avg_health": round(sum(v) / len(v), 1), "count": len(v)}
        for k, v in sorted(weekly.items())
    ]


@router.get("/leaderboard")
def health_leaderboard(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Return latest health score per client, ordered best-to-worst."""
    # Latest snapshot per client via subquery
    subq = (
        db.query(
            ClientHealthSnapshot.client_id,
            func.max(ClientHealthSnapshot.snapshot_at).label("latest"),
        )
        .group_by(ClientHealthSnapshot.client_id)
        .subquery()
    )
    rows = (
        db.query(ClientHealthSnapshot, Client.name)
        .join(subq, (ClientHealthSnapshot.client_id == subq.c.client_id) &
              (ClientHealthSnapshot.snapshot_at == subq.c.latest))
        .join(Client, Client.id == ClientHealthSnapshot.client_id)
        .order_by(ClientHealthSnapshot.health_score.desc())
        .all()
    )
    return [
        {
            "client_id":    snap.client_id,
            "client_name":  name,
            "health_score": snap.health_score,
            "snapshot_at":  snap.snapshot_at,
        }
        for snap, name in rows
    ]
