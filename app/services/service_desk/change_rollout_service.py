"""
change_rollout_service.py — Advanced change rollout planning.

Provides:
  - Rollout phase planning (phased rollout with gates)
  - Rollback plan management
  - Testing checklist before deployment
  - Communication plan (stakeholders + channels)
  - What-if impact simulation
  - Rollout status tracking
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.settings import AppSetting

_KEY_PLANS = "sd.change_rollout.plans"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get(db: Session, org_id: Optional[str]) -> dict:
    q = db.query(AppSetting).filter(AppSetting.key == _KEY_PLANS)
    q = q.filter(AppSetting.organization_id == org_id) if org_id else q.filter(AppSetting.organization_id.is_(None))
    row = q.first()
    if not row or not row.value:
        return {}
    try:
        return json.loads(row.value)
    except Exception:
        return {}


def _set(db: Session, org_id: Optional[str], plans: dict) -> None:
    payload = json.dumps(plans, ensure_ascii=False)
    q = db.query(AppSetting).filter(AppSetting.key == _KEY_PLANS)
    q = q.filter(AppSetting.organization_id == org_id) if org_id else q.filter(AppSetting.organization_id.is_(None))
    row = q.first()
    if not row:
        row = AppSetting(key=_KEY_PLANS, organization_id=org_id, value=payload, description="Change rollout plans")
        db.add(row)
    else:
        row.value = payload
    db.commit()


def create_rollout_plan(
    db: Session,
    *,
    org_id: Optional[str],
    change_request_id: str,
    title: str,
    rollout_phases: list[dict],
    rollback_steps: list[str],
    testing_checklist: list[dict],
    communication_plan: list[dict],
    maintenance_window_start: Optional[str],
    maintenance_window_end: Optional[str],
    created_by: str,
) -> dict:
    plans = _get(db, org_id)
    plan_id = str(uuid.uuid4())
    entry = {
        "id": plan_id,
        "change_request_id": change_request_id,
        "title": title,
        "status": "draft",
        "rollout_phases": rollout_phases,
        "rollback_steps": rollback_steps,
        "testing_checklist": testing_checklist,
        "communication_plan": communication_plan,
        "maintenance_window_start": maintenance_window_start,
        "maintenance_window_end": maintenance_window_end,
        "created_by": created_by,
        "created_at": _iso_now(),
        "updated_at": _iso_now(),
        "approved_by": None,
        "approved_at": None,
        "executed_at": None,
        "completed_at": None,
        "current_phase_index": 0,
    }
    plans[plan_id] = entry
    _set(db, org_id, plans)
    return entry


def get_plan(db: Session, *, org_id: Optional[str], plan_id: str) -> dict:
    plans = _get(db, org_id)
    if plan_id not in plans:
        raise ValueError(f"Plan '{plan_id}' not found")
    return plans[plan_id]


def list_plans(db: Session, *, org_id: Optional[str], change_request_id: Optional[str] = None) -> list[dict]:
    plans = list(_get(db, org_id).values())
    if change_request_id:
        plans = [p for p in plans if p["change_request_id"] == change_request_id]
    return sorted(plans, key=lambda p: p["created_at"], reverse=True)


def approve_plan(db: Session, *, org_id: Optional[str], plan_id: str, approver_user_id: str) -> dict:
    plans = _get(db, org_id)
    if plan_id not in plans:
        raise ValueError(f"Plan '{plan_id}' not found")
    plans[plan_id]["status"] = "approved"
    plans[plan_id]["approved_by"] = approver_user_id
    plans[plan_id]["approved_at"] = _iso_now()
    _set(db, org_id, plans)
    return plans[plan_id]


def advance_phase(db: Session, *, org_id: Optional[str], plan_id: str, phase_notes: Optional[str] = None) -> dict:
    plans = _get(db, org_id)
    if plan_id not in plans:
        raise ValueError(f"Plan '{plan_id}' not found")
    plan = plans[plan_id]
    phases = plan.get("rollout_phases", [])
    current = plan["current_phase_index"]

    if plan["status"] not in ("approved", "in_progress"):
        raise ValueError(f"Plan must be approved to advance phases. Status: {plan['status']}")

    if current < len(phases):
        phases[current]["status"] = "completed"
        phases[current]["completed_at"] = _iso_now()
        if phase_notes:
            phases[current]["notes"] = phase_notes

    next_index = current + 1
    plan["current_phase_index"] = next_index
    plan["status"] = "in_progress"
    plan["updated_at"] = _iso_now()

    if next_index >= len(phases):
        plan["status"] = "completed"
        plan["completed_at"] = _iso_now()

    _set(db, org_id, plans)
    return plan


def simulate_impact(
    *,
    affected_services: list[str],
    affected_users_count: int,
    change_type: str,
    rollout_phases: list[dict],
) -> dict:
    """Simple what-if impact simulation."""
    risk_score = 0.0
    if change_type == "emergency":
        risk_score += 0.4
    elif change_type == "normal":
        risk_score += 0.2
    else:
        risk_score += 0.05

    if affected_users_count > 1000:
        risk_score += 0.3
    elif affected_users_count > 100:
        risk_score += 0.15

    risk_score += len(affected_services) * 0.05
    risk_score = min(1.0, risk_score)

    risk_label = "critical" if risk_score >= 0.7 else "high" if risk_score >= 0.4 else "medium" if risk_score >= 0.2 else "low"

    estimated_duration_minutes = 30 + len(rollout_phases) * 15 + len(affected_services) * 5

    return {
        "risk_score": round(risk_score, 3),
        "risk_label": risk_label,
        "affected_services_count": len(affected_services),
        "affected_users_count": affected_users_count,
        "estimated_duration_minutes": estimated_duration_minutes,
        "phases_count": len(rollout_phases),
        "recommended_window": "22:00-06:00" if risk_score >= 0.4 else "business_hours",
        "recommendations": [
            "Prepare rollback script before starting" if risk_score >= 0.4 else None,
            "Notify all affected users 48h in advance" if affected_users_count > 100 else None,
            "Consider phased rollout over multiple days" if len(affected_services) > 5 else None,
        ],
    }
