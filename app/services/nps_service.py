"""Service layer for NPS and Client Health Snapshot operations."""

from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.nps import ClientNPS, ClientHealthSnapshot, NPSCategory
from app.models.clients import Client


# ── Internal helpers ──────────────────────────────────────────────────────

def _nps_category(score: int) -> NPSCategory:
    if score >= 9:
        return NPSCategory.promoter
    if score >= 7:
        return NPSCategory.passive
    return NPSCategory.detractor


def _compute_nps(responses: List[ClientNPS]) -> Optional[float]:
    if not responses:
        return None
    total = len(responses)
    promoters  = sum(1 for r in responses if r.category == NPSCategory.promoter)
    detractors = sum(1 for r in responses if r.category == NPSCategory.detractor)
    return round((promoters - detractors) / total * 100, 1)


# ── Public service functions ──────────────────────────────────────────────

def client_exists(db: Session, client_id: str) -> bool:
    return db.query(Client).filter(Client.id == client_id).first() is not None


def create_nps_entry(
    db: Session,
    client_id: str,
    score: int,
    comment: Optional[str],
    respondent: Optional[str],
    source: str,
) -> ClientNPS:
    entry = ClientNPS(
        client_id  = client_id,
        score      = score,
        category   = _nps_category(score),
        comment    = comment,
        respondent = respondent,
        source     = source,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def list_nps_responses(db: Session, client_id: str, limit: int) -> List[ClientNPS]:
    return (
        db.query(ClientNPS)
        .filter(ClientNPS.client_id == client_id)
        .order_by(ClientNPS.created_at.desc())
        .limit(limit)
        .all()
    )


def get_nps_responses_since(db: Session, client_id: str, cutoff: datetime) -> List[ClientNPS]:
    return (
        db.query(ClientNPS)
        .filter(
            ClientNPS.client_id == client_id,
            ClientNPS.created_at >= cutoff,
        )
        .order_by(ClientNPS.created_at)
        .all()
    )


def compute_nps_summary(responses: List[ClientNPS]) -> dict:
    """Return NPS + breakdown dict; no db access needed."""
    nps        = _compute_nps(responses)
    promoters  = sum(1 for r in responses if r.category == NPSCategory.promoter)
    passives   = sum(1 for r in responses if r.category == NPSCategory.passive)
    detractors = sum(1 for r in responses if r.category == NPSCategory.detractor)

    monthly: dict = {}
    for r in responses:
        key = r.created_at.strftime("%Y-%m")
        monthly.setdefault(key, []).append(r)

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
    }


def create_health_snapshot(
    db: Session,
    client_id: str,
    health_score: float,
    nps_component: Optional[float],
    delivery_component: Optional[float],
    budget_component: Optional[float],
    activity_component: Optional[float],
    note: Optional[str],
) -> ClientHealthSnapshot:
    snap = ClientHealthSnapshot(
        client_id           = client_id,
        health_score        = health_score,
        nps_component       = nps_component,
        delivery_component  = delivery_component,
        budget_component    = budget_component,
        activity_component  = activity_component,
        note                = note,
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return snap


def compute_and_save_health(db: Session, client_id: str) -> ClientHealthSnapshot:
    """Auto-compute health score from current signals and persist a snapshot."""
    cutoff    = datetime.utcnow() - timedelta(days=90)
    responses = get_nps_responses_since(db, client_id, cutoff)
    nps_score = _compute_nps(responses)
    nps_component = ((nps_score or 0) + 100) / 2 if nps_score is not None else 50.0
    score = round((nps_component * 0.4) + (70 * 0.2) + (70 * 0.2) + (70 * 0.2), 1)
    score = min(max(score, 0), 100)

    snap = ClientHealthSnapshot(client_id=client_id, health_score=score, note="Auto-computed")
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return snap


def get_health_history(db: Session, client_id: str, limit: int) -> List[ClientHealthSnapshot]:
    return (
        db.query(ClientHealthSnapshot)
        .filter(ClientHealthSnapshot.client_id == client_id)
        .order_by(ClientHealthSnapshot.snapshot_at.desc())
        .limit(limit)
        .all()
    )


def get_health_trend(db: Session, cutoff: datetime) -> List[ClientHealthSnapshot]:
    return (
        db.query(ClientHealthSnapshot)
        .filter(ClientHealthSnapshot.snapshot_at >= cutoff)
        .order_by(ClientHealthSnapshot.snapshot_at)
        .all()
    )


def get_health_leaderboard(db: Session):
    subq = (
        db.query(
            ClientHealthSnapshot.client_id,
            func.max(ClientHealthSnapshot.snapshot_at).label("latest"),
        )
        .group_by(ClientHealthSnapshot.client_id)
        .subquery()
    )
    return (
        db.query(ClientHealthSnapshot, Client.name)
        .join(
            subq,
            (ClientHealthSnapshot.client_id == subq.c.client_id)
            & (ClientHealthSnapshot.snapshot_at == subq.c.latest),
        )
        .join(Client, Client.id == ClientHealthSnapshot.client_id)
        .order_by(ClientHealthSnapshot.health_score.desc())
        .all()
    )
