"""Puntuacion de riesgo de un cambio, informe de impacto, ventana de mantenimiento y matriz de riesgo.

Parte de `app.services.service_desk.change_impact_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.service_desk import (
    CIRelation,
    ConfigurationItem,
    ITSMChangeRequest,
    ChangeRisk,
    ChangeType,
    Ticket,
)
# ══════════════════════════════════════════════════════════════════════════════
# v23.10.44 — Automated Change Impact Analysis + Rollback Plan (new)
# ══════════════════════════════════════════════════════════════════════════════

import math


logger = logging.getLogger("app.services.service_desk.change_impact_service")

# ── Risk scoring weights ──────────────────────────────────────────────────────

_CHANGE_TYPE_RISK = {
    ChangeType.standard: 10,
    ChangeType.normal: 40,
    ChangeType.emergency: 80,
}

_CURRENT_RISK_SCORE = {
    ChangeRisk.low: 10,
    ChangeRisk.medium: 35,
    ChangeRisk.high: 65,
    ChangeRisk.critical: 90,
}

# Number of affected CIs → risk contribution (capped at 30)
def _ci_count_risk(n: int) -> int:
    if n == 0:
        return 0
    elif n <= 2:
        return 10
    elif n <= 5:
        return 20
    else:
        return 30


# Downtime minutes → risk contribution (capped at 20)
def _downtime_risk(minutes: int) -> int:
    if minutes == 0:
        return 0
    elif minutes <= 30:
        return 5
    elif minutes <= 120:
        return 10
    elif minutes <= 480:
        return 15
    else:
        return 20


# ── CI dependency expansion ───────────────────────────────────────────────────

def _expand_ci_dependencies(
    db: Session,
    ci_ids: list[str],
    depth: int = 2,
) -> list[str]:
    """BFS-expand *ci_ids* via CIRelation to depth *depth*.

    Returns deduplicated list of all reachable CI IDs (including originals).
    """
    visited: set[str] = set(ci_ids)
    frontier = list(ci_ids)

    for _ in range(depth):
        if not frontier:
            break
        related = (
            db.query(CIRelation)
            .filter(
                CIRelation.source_ci_id.in_(frontier)
                | CIRelation.target_ci_id.in_(frontier)
            )
            .all()
        )
        next_frontier: list[str] = []
        for rel in related:
            for cid in (rel.source_ci_id, rel.target_ci_id):
                if cid not in visited:
                    visited.add(cid)
                    next_frontier.append(cid)
        frontier = next_frontier

    return list(visited)


def _get_ci_details(db: Session, ci_ids: list[str]) -> list[dict]:
    """Return lightweight info dicts for the given CI IDs."""
    if not ci_ids:
        return []
    cis = (
        db.query(ConfigurationItem)
        .filter(ConfigurationItem.id.in_(ci_ids))
        .all()
    )
    return [
        {
            "id": ci.id,
            "name": ci.name,
            "ci_type": ci.ci_type,
            "status": ci.status,
            "criticality": getattr(ci, "criticality", "normal"),
        }
        for ci in cis
    ]


# ── Open-ticket overlap ───────────────────────────────────────────────────────

def _open_tickets_on_cis(db: Session, ci_ids: list[str]) -> int:
    """Count open tickets linked to any of the CIs affected by the change."""
    if not ci_ids:
        return 0
    return (
        db.query(func.count(Ticket.id))
        .filter(
            Ticket.ci_id.in_(ci_ids),
            Ticket.status.notin_(["resolved", "closed"]),
        )
        .scalar()
        or 0
    )


# ── Incident history in window ────────────────────────────────────────────────

def _incident_count_last_days(
    db: Session, ci_ids: list[str], days: int = 30
) -> int:
    """Count incidents involving these CIs in the last *days* days."""
    if not ci_ids:
        return 0
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    return (
        db.query(func.count(Ticket.id))
        .filter(
            Ticket.ci_id.in_(ci_ids),
            Ticket.created_at >= cutoff,
        )
        .scalar()
        or 0
    )


# ── Maintenance window suggestion ─────────────────────────────────────────────

def suggest_maintenance_window(
    db: Session,
    change: ITSMChangeRequest,
    ci_ids: Optional[list[str]] = None,
) -> dict:
    """Suggest the lowest-incident 4-hour window over the next 7 days.

    Uses hourly incident frequency over the last 28 days to find the
    quietest combination of day-of-week + hour.

    Returns:
        {
          "day_of_week": 0-6 (0=Mon),
          "hour_utc": 0-23,
          "window_label": "Tuesday 02:00–06:00 UTC",
          "avg_incidents_in_window": float,
          "confidence": "low|medium|high",
        }
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=28)

    q = db.query(Ticket.created_at).filter(
        Ticket.created_at >= cutoff,
        Ticket.ticket_type == "incident",
    )
    if ci_ids:
        q = q.filter(Ticket.ci_id.in_(ci_ids))

    incidents = q.all()

    # Build hour_of_week frequency matrix (7 days × 24 hours)
    freq: list[list[int]] = [[0] * 24 for _ in range(7)]
    for (ts,) in incidents:
        if ts:
            ts_utc = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts
            dow = ts_utc.weekday()  # 0=Mon
            freq[dow][ts_utc.hour] += 1

    # Find 4-consecutive-hour window with minimum sum
    best_dow = 0
    best_hour = 2  # default: 02:00 UTC weekday
    best_sum = float("inf")

    for dow in range(7):
        for h in range(24):
            window_sum = sum(freq[dow][(h + i) % 24] for i in range(4))
            if window_sum < best_sum:
                best_sum = window_sum
                best_dow = dow
                best_hour = h

    _days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    window_label = f"{_days[best_dow]} {best_hour:02d}:00–{(best_hour+4)%24:02d}:00 UTC"

    confidence = "high" if len(incidents) >= 50 else ("medium" if len(incidents) >= 10 else "low")

    return {
        "day_of_week": best_dow,
        "hour_utc": best_hour,
        "window_label": window_label,
        "avg_incidents_in_window": round(best_sum / 4, 2),
        "confidence": confidence,
    }


# ── Risk scoring ──────────────────────────────────────────────────────────────

def score_change_risk(
    db: Session,
    change: ITSMChangeRequest,
) -> dict:
    """Compute automated risk score 0-100 for a Change Request.

    Components:
      - Change type             (10-80 pts)
      - Number of affected CIs  (0-30 pts)
      - Downtime planned        (0-20 pts)
      - Open tickets on CIs     (0-15 pts  penalty)
      - Recent incident history (0-15 pts  penalty)

    Returns:
        {
          "score": int,         # 0-100
          "risk_label": str,    # low|medium|high|critical
          "components": dict,
          "ci_ids_direct": list,
          "ci_ids_expanded": list,
        }
    """
    # Parse affected CIs from JSON
    direct_ci_ids: list[str] = []
    try:
        if change.affected_cis:
            raw = json.loads(change.affected_cis)
            direct_ci_ids = raw if isinstance(raw, list) else []
    except (json.JSONDecodeError, TypeError):
        direct_ci_ids = []

    expanded_ci_ids = _expand_ci_dependencies(db, direct_ci_ids, depth=2)

    # Scoring components
    type_score = _CHANGE_TYPE_RISK.get(change.change_type, 40)
    ci_score = _ci_count_risk(len(expanded_ci_ids))
    downtime_score = _downtime_risk(change.downtime_minutes or 0)

    open_tickets_n = _open_tickets_on_cis(db, expanded_ci_ids)
    open_tickets_penalty = min(15, open_tickets_n * 3)

    recent_incidents = _incident_count_last_days(db, expanded_ci_ids, days=30)
    incident_penalty = min(15, recent_incidents * 2)

    total = type_score + ci_score + downtime_score + open_tickets_penalty + incident_penalty
    total = min(100, total)

    risk_label = (
        "critical" if total >= 75
        else "high" if total >= 55
        else "medium" if total >= 30
        else "low"
    )

    return {
        "score": total,
        "risk_label": risk_label,
        "components": {
            "change_type_score": type_score,
            "ci_count_score": ci_score,
            "downtime_score": downtime_score,
            "open_tickets_penalty": open_tickets_penalty,
            "incident_penalty": incident_penalty,
        },
        "ci_ids_direct": direct_ci_ids,
        "ci_ids_expanded": expanded_ci_ids,
    }


# ── Impact report ─────────────────────────────────────────────────────────────

def generate_impact_report(db: Session, change_id: str) -> dict:
    """Generate a comprehensive impact analysis report for CAB review.

    Returns a structured dict ready to be serialised as JSON and stored
    in `sd_change_requests.impact_analysis_json`.
    """
    change = db.query(ITSMChangeRequest).filter(ITSMChangeRequest.id == change_id).first()
    if not change:
        return {"error": f"Change {change_id} not found"}

    risk_data = score_change_risk(db, change)
    ci_details = _get_ci_details(db, risk_data["ci_ids_expanded"])

    # CI criticality summary
    critical_cis = [c for c in ci_details if c.get("criticality") in ("critical", "high")]

    window = suggest_maintenance_window(db, change, risk_data["ci_ids_expanded"])

    open_incidents = _open_tickets_on_cis(db, risk_data["ci_ids_expanded"])
    recent_incidents_30d = _incident_count_last_days(db, risk_data["ci_ids_expanded"], 30)

    report = {
        "change_id": change_id,
        "change_number": change.number,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "risk_score": risk_data["score"],
        "risk_label": risk_data["risk_label"],
        "risk_components": risk_data["components"],
        "affected_cis": {
            "direct_count": len(risk_data["ci_ids_direct"]),
            "expanded_count": len(risk_data["ci_ids_expanded"]),
            "critical_cis": [c["name"] for c in critical_cis],
            "ci_list": ci_details,
        },
        "open_incidents_on_cis": open_incidents,
        "incidents_last_30d": recent_incidents_30d,
        "suggested_window": window,
        "summary": (
            f"Change '{change.title}' affects {len(risk_data['ci_ids_expanded'])} CIs "
            f"(direct: {len(risk_data['ci_ids_direct'])}). "
            f"Risk score: {risk_data['score']}/100 ({risk_data['risk_label'].upper()}). "
            f"Suggested maintenance window: {window['window_label']}."
        ),
    }

    return report


_CRITICALITY_RISK_SCORE = {"critical": 4, "high": 3, "medium": 2, "low": 1}
_RISK_LEVEL_THRESHOLDS = {"critical": 12, "high": 8, "medium": 4}


def _risk_level_label(score: float) -> str:
    if score >= _RISK_LEVEL_THRESHOLDS["critical"]:
        return "critical"
    if score >= _RISK_LEVEL_THRESHOLDS["high"]:
        return "high"
    if score >= _RISK_LEVEL_THRESHOLDS["medium"]:
        return "medium"
    return "low"


def get_risk_matrix_for_change(db: Session, change_id: str) -> list[dict]:
    """Calculate per-CI risk matrix for all CIs affected by the change."""
    change = db.query(ITSMChangeRequest).filter(ITSMChangeRequest.id == change_id).first()
    if not change:
        raise ValueError(f"Change {change_id} not found")

    risk_data = score_change_risk(db, change)
    ci_ids = risk_data.get("ci_ids_expanded", [])

    matrix: list[dict] = []
    for ci_id in ci_ids:
        ci = db.query(ConfigurationItem).filter(ConfigurationItem.id == ci_id).first()
        if not ci:
            continue
        criticality = (getattr(ci, "criticality", None) or "medium").lower()
        crit_score = _CRITICALITY_RISK_SCORE.get(criticality, 2)

        dep_count = (
            db.query(CIRelation)
            .filter(CIRelation.target_ci_id == ci_id)
            .count()
        )
        recent_incidents = _incident_count_last_days(db, [ci_id], days=30)
        dep_factor = math.sqrt(dep_count + 1)
        incident_factor = min(recent_incidents * 0.5, 2.0)
        risk_score = round(crit_score * dep_factor * (1 + incident_factor), 2)

        matrix.append({
            "ci_id": ci_id,
            "ci_name": ci.name,
            "ci_type": ci.ci_type.value,
            "criticality": criticality,
            "dependency_count": dep_count,
            "recent_incidents": recent_incidents,
            "risk_score": risk_score,
            "impact_level": _risk_level_label(risk_score),
        })

    matrix.sort(key=lambda x: x["risk_score"], reverse=True)
    return matrix
