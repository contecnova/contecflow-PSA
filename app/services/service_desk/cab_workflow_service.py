from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.service_desk import ChangeStatus, ITSMChangeRequest
from app.models.settings import AppSetting
from app.models.user import User
import logging

logger = logging.getLogger(__name__)

CAB_KEY_PREFIX = "sd.cab.workflow."


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cab_key(change_id: str) -> str:
    return f"{CAB_KEY_PREFIX}{change_id}"


def _setting_row(db: Session, key: str) -> Optional[AppSetting]:
    return db.query(AppSetting).filter(AppSetting.key == key).first()


def _load(db: Session, change_id: str) -> dict | None:
    row = _setting_row(db, _cab_key(change_id))
    if not row or not row.value:
        return None
    try:
        return json.loads(row.value)
    except Exception:
        return None


def _save(db: Session, change_id: str, state: dict) -> None:
    key = _cab_key(change_id)
    payload = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    row = _setting_row(db, key)
    if row is None:
        db.add(AppSetting(key=key, description=f"CAB workflow for change {change_id}", value=payload))
    else:
        row.value = payload
    db.flush()


def default_templates() -> dict:
    return {
        "testing_plan": {
            "pre_checks": ["Backup validado", "Healthcheck pre-cambio", "Capacidad confirmada"],
            "execution_checks": ["Errores en logs", "Latencia", "Integraciones clave"],
            "post_checks": ["Smoke tests", "KPIs estables", "Monitoreo 30 min"],
        },
        "comms_plan": {
            "pre_change": "Avisar stakeholders 24h antes",
            "during_change": "Actualizar cada 30 min",
            "post_change": "Enviar resultado y seguimiento",
        },
    }


def start_cab_workflow(
    db: Session,
    *,
    change_id: str,
    requester: User,
    manager_user_id: str,
    cab_members: list[str],
    quorum: Optional[int] = None,
) -> dict:
    change = db.query(ITSMChangeRequest).filter(ITSMChangeRequest.id == change_id).first()
    if not change:
        raise ValueError("change_not_found")

    quorum_n = quorum if quorum is not None else max(1, (len(cab_members) // 2) + 1)
    state = {
        "change_id": change_id,
        "status": "requester",
        "requester_id": requester.id,
        "manager_user_id": manager_user_id,
        "cab_members": cab_members,
        "quorum": quorum_n,
        "meeting": None,
        "votes": [],
        "history": [{"stage": "requester", "at": _iso_now(), "by": requester.id}],
        "templates": default_templates(),
        "executor_user_id": None,
    }
    _save(db, change_id, state)
    change.status = ChangeStatus.cab_review
    return state


def schedule_cab_meeting(
    db: Session,
    *,
    change_id: str,
    manager: User,
    when_iso: str,
    agenda: str,
) -> dict:
    state = _load(db, change_id)
    if not state:
        raise ValueError("cab_workflow_not_found")

    state["meeting"] = {
        "scheduled_at": when_iso,
        "agenda": agenda,
        "scheduled_by": manager.id,
        "created_at": _iso_now(),
    }
    state["status"] = "cab"
    state["history"].append({"stage": "cab", "at": _iso_now(), "by": manager.id})
    _save(db, change_id, state)
    return state


def cast_cab_vote(
    db: Session,
    *,
    change_id: str,
    voter: User,
    approve: bool,
    note: str = "",
) -> dict:
    state = _load(db, change_id)
    if not state:
        raise ValueError("cab_workflow_not_found")
    if voter.id not in state.get("cab_members", []):
        raise ValueError("user_not_in_cab")

    votes = [v for v in state.get("votes", []) if v.get("user_id") != voter.id]
    votes.append(
        {
            "user_id": voter.id,
            "approved": bool(approve),
            "note": note,
            "voted_at": _iso_now(),
        }
    )
    state["votes"] = votes

    approvals = sum(1 for v in votes if v.get("approved"))
    rejections = sum(1 for v in votes if not v.get("approved"))
    quorum = int(state.get("quorum", 1))

    if approvals >= quorum:
        state["status"] = "executor"
        state["history"].append({"stage": "executor", "at": _iso_now(), "by": voter.id})
        change = db.query(ITSMChangeRequest).filter(ITSMChangeRequest.id == change_id).first()
        if change:
            change.status = ChangeStatus.approved
            change.approved_at = datetime.now(timezone.utc)
            change.approved_by = voter.id
    elif rejections >= quorum:
        state["status"] = "rejected"
        change = db.query(ITSMChangeRequest).filter(ITSMChangeRequest.id == change_id).first()
        if change:
            change.status = ChangeStatus.cancelled

    _save(db, change_id, state)
    return state


def assign_executor(db: Session, *, change_id: str, executor_user_id: str, manager: User) -> dict:
    state = _load(db, change_id)
    if not state:
        raise ValueError("cab_workflow_not_found")
    state["executor_user_id"] = executor_user_id
    state["history"].append({"stage": "executor_assigned", "at": _iso_now(), "by": manager.id})
    _save(db, change_id, state)
    return state


def get_workflow(db: Session, *, change_id: str) -> dict | None:
    return _load(db, change_id)
