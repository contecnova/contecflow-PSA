"""approval_engine.timeouts — extracted from the former 1827-LOC god-file."""

from __future__ import annotations
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from collections import defaultdict
from sqlalchemy.orm import Session, joinedload
from app.models.user import User
from app.models.billing_reports import FinancialApprovalAuditLog
from app.models.billing_reports import ApprovalRequest
from app.models.billing_reports import ApprovalWorkflow
from app.models.billing_reports import ApprovalDecision
from app.models.billing_reports import ApprovalStep
from app.models.billing_reports import ApprovalGroup
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import func


from app.services.approval_engine._base import _FINANCIAL_ENTITY_TYPES

def _handle_timeout_escalate(req, step, now: datetime, info: dict, db: Session) -> str:
    """Apply 'escalate' timeout action. Returns counter bucket name."""
    if step.escalate_to_user_id:
        db.add(ApprovalDecision(
            request_id=req.id,
            step_order=step.step_order,
            approver_id=step.escalate_to_user_id,
            decision="delegated",
            note="Escalado automáticamente por timeout",
            decided_at=now,
        ))
        req.current_step += 1
        req.step_started_at = now
        info["escalated_to"] = step.escalate_to_user_id
        return "escalated"
    req.status = "rejected"
    req.final_decision = "rejected"
    req.final_note = "Rechazado automáticamente por timeout (sin escalado)"
    req.completed_at = now
    info["rejected"] = True
    return "rejected"

def _handle_timeout_auto_approve(req, step, now: datetime, info: dict, db: Session) -> str:
    db.add(ApprovalDecision(
        request_id=req.id,
        step_order=step.step_order,
        approver_id=step.approver_user_id,
        decision="approved",
        note="Aprobado automáticamente por timeout",
        decided_at=now,
    ))
    req.current_step += 1
    req.step_started_at = now
    info["auto_approved"] = True
    return "auto_approved"

def _handle_timeout_reject(req, step, now: datetime, info: dict, db: Session) -> str:
    req.status = "rejected"
    req.final_decision = "rejected"
    req.final_note = "Rechazado automáticamente por timeout"
    req.completed_at = now
    info["rejected"] = True
    return "rejected"

def _log_timeout_audit_event(req, step, action: str, now: datetime, db: Session) -> None:
    if req.entity_type not in _FINANCIAL_ENTITY_TYPES:
        return
    db.add(FinancialApprovalAuditLog(
        request_id=req.id,
        entity_type=req.entity_type,
        entity_id=req.entity_id,
        action="timeout",
        decision=action,
        actor_user_id=None,
        step_order=step.step_order,
        note=f"Acción automática por timeout: {action}",
        created_at=now,
    ))

def _step_is_expired(step, req, now: datetime) -> bool:
    if not step or not step.timeout_hours or not req.step_started_at:
        return False
    timeout_at = req.step_started_at + timedelta(hours=step.timeout_hours)
    return now >= timeout_at

def process_approval_timeouts(db: Session) -> dict:
    """
    Procesa todas las solicitudes de aprobación pendientes y aplica la acción configurada
    (escalar, auto-aprobar o rechazar) para los pasos que superaron su timeout.
    Devuelve un resumen de las acciones realizadas.
    """
    now = datetime.now(timezone.utc)
    counters = {"escalated": 0, "auto_approved": 0, "rejected": 0}
    updated = 0
    details: list = []

    requests = db.query(ApprovalRequest).filter(ApprovalRequest.status == "pending").all()
    for req in requests:
        step = (
            db.query(ApprovalStep)
            .filter(
                ApprovalStep.workflow_id == req.workflow_id,
                ApprovalStep.step_order == req.current_step,
            )
            .first()
        )
        if not _step_is_expired(step, req, now):
            continue

        action = (step.on_timeout or "escalate").lower()
        info = {"request_id": req.id, "step": step.step_order, "action": action}

        if action == "escalate":
            bucket = _handle_timeout_escalate(req, step, now, info, db)
        elif action == "auto_approve":
            bucket = _handle_timeout_auto_approve(req, step, now, info, db)
        elif action == "reject":
            bucket = _handle_timeout_reject(req, step, now, info, db)
        else:
            continue

        counters[bucket] = counters.get(bucket, 0) + 1
        _log_timeout_audit_event(req, step, action, now, db)
        updated += 1
        details.append(info)

    db.commit()
    return {
        "updated": updated,
        "escalated": counters["escalated"],
        "auto_approved": counters["auto_approved"],
        "rejected": counters["rejected"],
        "details": details,
    }
