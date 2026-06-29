"""approval_engine.analytics — extracted from the former 1827-LOC god-file."""

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


from app.services.approval_engine._base import _load_workflows_by_ids, logger, scope_request_query

def get_financial_audit_entries(db: Session, request_id: str, current_user: User):
    req = scope_request_query(
        db.query(ApprovalRequest), db, current_user
    ).filter(ApprovalRequest.id == request_id).first()
    if not req:
        return None, None
    entries = (
        db.query(FinancialApprovalAuditLog)
        .filter(FinancialApprovalAuditLog.request_id == request_id)
        .order_by(FinancialApprovalAuditLog.created_at.asc())
        .all()
    )
    return req, entries

def get_approval_stats(db: Session, current_user: User) -> dict:
    q = scope_request_query(db.query(ApprovalRequest), db, current_user)
    total    = q.count()
    pending  = q.filter(ApprovalRequest.status == "pending").count()
    approved = q.filter(ApprovalRequest.status == "approved").count()
    rejected = q.filter(ApprovalRequest.status == "rejected").count()
    by_entity = (
        q.with_entities(ApprovalRequest.entity_type, func.count(ApprovalRequest.id))
        .group_by(ApprovalRequest.entity_type)
        .all()
    )
    return {
        "total": total,
        "pending": pending,
        "approved": approved,
        "rejected": rejected,
        "by_entity_type": {e: c for e, c in by_entity},
    }

def _empty_bottleneck_row() -> dict:
    return {
        "workflow_id": None,
        "workflow_name": None,
        "step_order": None,
        "step_name": None,
        "step_timeout_hours": None,
        "decisions_total": 0,
        "approved_count": 0,
        "rejected_count": 0,
        "delegated_count": 0,
        "decision_time_sum_hours": 0.0,
        "decision_time_count": 0,
        "pending_count": 0,
        "pending_age_sum_hours": 0.0,
    }

def _stamp_bottleneck_row(row: dict, wf, step, step_order: int) -> None:
    row["workflow_id"] = wf.id
    row["workflow_name"] = wf.name
    row["step_order"] = step_order
    row["step_name"] = step.name if step else f"Step {step_order}"
    row["step_timeout_hours"] = step.timeout_hours if step else None

def _aggregate_bottleneck_decisions(stats: dict, req, wf, step_map: dict, now: datetime) -> None:
    ordered_decisions = sorted(req.decisions or [], key=lambda d: (d.step_order, d.decided_at or now))
    prev_ts = req.created_at
    for d in ordered_decisions:
        step = step_map.get(d.step_order)
        key = (req.workflow_id, d.step_order)
        row = stats[key]
        _stamp_bottleneck_row(row, wf, step, d.step_order)

        row["decisions_total"] += 1
        if d.decision == "approved":
            row["approved_count"] += 1
        elif d.decision == "rejected":
            row["rejected_count"] += 1
        elif d.decision == "delegated":
            row["delegated_count"] += 1

        if d.decided_at and prev_ts:
            delta_h = max(0.0, (d.decided_at - prev_ts).total_seconds() / 3600.0)
            row["decision_time_sum_hours"] += delta_h
            row["decision_time_count"] += 1
        if d.decided_at:
            prev_ts = d.decided_at

def _aggregate_bottleneck_pending(stats: dict, req, wf, step_map: dict, now: datetime) -> None:
    if not (req.status == "pending" and req.current_step):
        return
    step = step_map.get(req.current_step)
    key = (req.workflow_id, req.current_step)
    row = stats[key]
    _stamp_bottleneck_row(row, wf, step, req.current_step)
    row["pending_count"] += 1
    if req.step_started_at:
        age_h = max(0.0, (now - req.step_started_at).total_seconds() / 3600.0)
        row["pending_age_sum_hours"] += age_h

def _compute_bottleneck_item(row: dict) -> dict:
    decisions_total = row["decisions_total"]
    decision_time_count = row["decision_time_count"]
    pending_count = row["pending_count"]
    reject_rate = (row["rejected_count"] / decisions_total * 100.0) if decisions_total else 0.0
    avg_decision_h = (row["decision_time_sum_hours"] / decision_time_count) if decision_time_count else 0.0
    avg_pending_h = (row["pending_age_sum_hours"] / pending_count) if pending_count else 0.0

    timeout_h = row["step_timeout_hours"] or 0
    sla_risk_pct = (avg_pending_h / timeout_h * 100.0) if timeout_h > 0 else 0.0
    bottleneck_score = avg_decision_h * (1.0 + pending_count * 0.35) * (1.0 + reject_rate / 100.0)

    return {
        "workflow_id": row["workflow_id"],
        "workflow_name": row["workflow_name"],
        "step_order": row["step_order"],
        "step_name": row["step_name"],
        "step_timeout_hours": row["step_timeout_hours"],
        "decisions_total": decisions_total,
        "approved_count": row["approved_count"],
        "rejected_count": row["rejected_count"],
        "delegated_count": row["delegated_count"],
        "rejection_rate_pct": round(reject_rate, 2),
        "avg_decision_time_hours": round(avg_decision_h, 2),
        "pending_count": pending_count,
        "avg_pending_age_hours": round(avg_pending_h, 2),
        "sla_risk_pct": round(sla_risk_pct, 2),
        "bottleneck_score": round(bottleneck_score, 3),
    }

def _compute_weekly_trend(requests) -> list:
    weekly = defaultdict(lambda: {"decisions": 0, "rejected": 0})
    for req in requests:
        for d in (req.decisions or []):
            if not d.decided_at:
                continue
            week_key = d.decided_at.astimezone(timezone.utc).strftime("%G-W%V")
            weekly[week_key]["decisions"] += 1
            if d.decision == "rejected":
                weekly[week_key]["rejected"] += 1

    weekly_trend = []
    for week_key in sorted(weekly.keys()):
        row = weekly[week_key]
        decisions = row["decisions"]
        reject_rate = (row["rejected"] / decisions * 100.0) if decisions else 0.0
        weekly_trend.append({
            "week": week_key,
            "decisions": decisions,
            "rejected": row["rejected"],
            "rejection_rate_pct": round(reject_rate, 2),
        })
    return weekly_trend

def _compute_top_workflows(items: list) -> list:
    top_workflow_map = defaultdict(lambda: {
        "workflow_id": None,
        "workflow_name": None,
        "steps_analyzed": 0,
        "avg_bottleneck_score": 0.0,
        "max_sla_risk_pct": 0.0,
        "pending_total": 0,
    })
    for it in items:
        wf_row = top_workflow_map[it["workflow_id"]]
        wf_row["workflow_id"] = it["workflow_id"]
        wf_row["workflow_name"] = it["workflow_name"]
        wf_row["steps_analyzed"] += 1
        wf_row["avg_bottleneck_score"] += it["bottleneck_score"]
        wf_row["max_sla_risk_pct"] = max(wf_row["max_sla_risk_pct"], it["sla_risk_pct"])
        wf_row["pending_total"] += it["pending_count"]

    top_workflows = []
    for wf in top_workflow_map.values():
        wf["avg_bottleneck_score"] = round(
            wf["avg_bottleneck_score"] / max(1, wf["steps_analyzed"]),
            3,
        )
        top_workflows.append(wf)
    top_workflows.sort(
        key=lambda x: (x["avg_bottleneck_score"], x["max_sla_risk_pct"], x["pending_total"]),
        reverse=True,
    )
    return top_workflows

def _compute_bottleneck_recommendations(items: list) -> list:
    recommendations: list = []
    worst = items[0] if items else None
    if worst and worst["sla_risk_pct"] >= 80:
        recommendations.append({
            "priority": "high",
            "title": f"Mitigar riesgo SLA en '{worst['workflow_name']}' paso {worst['step_order']}",
            "action": "Reducir timeout o activar escalado automatico con fallback a rol.",
            "why": f"Riesgo SLA {worst['sla_risk_pct']}% con {worst['pending_count']} pendientes.",
        })

    high_reject = next((it for it in items if it["rejection_rate_pct"] >= 25), None)
    if high_reject:
        recommendations.append({
            "priority": "medium",
            "title": f"Bajar rechazo en '{high_reject['workflow_name']}' paso {high_reject['step_order']}",
            "action": "Añadir checklist previo y validaciones automaticas antes de enviar a aprobacion.",
            "why": f"Tasa de rechazo {high_reject['rejection_rate_pct']}%.",
        })

    slow = next((it for it in items if it["avg_decision_time_hours"] >= 24), None)
    if slow:
        recommendations.append({
            "priority": "medium",
            "title": f"Acelerar ciclo en '{slow['workflow_name']}' paso {slow['step_order']}",
            "action": "Usar aprobador de respaldo o regla any_in_department para evitar bloqueo por ausencia.",
            "why": f"Tiempo medio de decision {slow['avg_decision_time_hours']}h.",
        })
    return recommendations

def _load_bottleneck_requests(db: Session, current_user: User, workflow_id: Optional[str], since: datetime) -> list:
    rq = db.query(ApprovalRequest).options(joinedload(ApprovalRequest.decisions)).filter(
        ApprovalRequest.created_at >= since
    )
    if workflow_id:
        rq = rq.filter(ApprovalRequest.workflow_id == workflow_id)
    rq = scope_request_query(rq, db, current_user)
    return rq.all()

def get_workflow_bottlenecks(
    db: Session,
    current_user: User,
    workflow_id: Optional[str] = None,
    days: int = 90,
) -> dict:
    """Compute bottleneck metrics per workflow step based on historical decisions.

    Metrics per step:
      - decisions_total
      - rejection_rate_pct
      - avg_decision_time_hours
      - pending_count
      - avg_pending_age_hours
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=max(1, min(days, 365)))

    requests = _load_bottleneck_requests(db, current_user, workflow_id, since)
    workflow_ids = sorted({r.workflow_id for r in requests if r.workflow_id})
    workflows = _load_workflows_by_ids(db, workflow_ids)

    stats = defaultdict(_empty_bottleneck_row)
    for req in requests:
        wf = workflows.get(req.workflow_id)
        if not wf:
            continue
        step_map = {s.step_order: s for s in (wf.steps or [])}
        _aggregate_bottleneck_decisions(stats, req, wf, step_map, now)
        _aggregate_bottleneck_pending(stats, req, wf, step_map, now)

    items = [_compute_bottleneck_item(row) for row in stats.values()]
    items.sort(key=lambda x: x["bottleneck_score"], reverse=True)

    weekly_trend = _compute_weekly_trend(requests)
    top_workflows = _compute_top_workflows(items)
    recommendations = _compute_bottleneck_recommendations(items)

    critical_steps = [
        it for it in items
        if it["sla_risk_pct"] >= 80 or it["pending_count"] >= 3 or it["rejection_rate_pct"] >= 25
    ]
    pending_total = sum(it["pending_count"] for it in items)
    avg_decision_time = round(
        (sum(it["avg_decision_time_hours"] for it in items) / len(items)) if items else 0.0,
        2,
    )

    return {
        "since": since.isoformat(),
        "days": days,
        "workflow_id": workflow_id,
        "count": len(items),
        "items": items,
        "top_bottlenecks": items[:10],
        "summary": {
            "steps_analyzed": len(items),
            "critical_steps": len(critical_steps),
            "pending_total": pending_total,
            "avg_decision_time_hours": avg_decision_time,
        },
        "top_workflows": top_workflows[:5],
        "weekly_trend": weekly_trend[-12:],
        "recommendations": recommendations,
    }

def _empty_approver_load_row() -> dict:
    return {
        "user_id": None,
        "decisions_total": 0,
        "approved_count": 0,
        "rejected_count": 0,
        "decision_time_sum_hours": 0.0,
        "decision_time_count": 0,
        "pending_count": 0,
        "avg_pending_age_hours": 0.0,
    }

def _aggregate_decisions_per_user(decisions, user_stats: dict) -> None:
    for d in decisions:
        row = user_stats[d.approver_id]
        row["user_id"] = d.approver_id
        row["decisions_total"] += 1
        if d.decision == "approved":
            row["approved_count"] += 1
        elif d.decision == "rejected":
            row["rejected_count"] += 1

def _resolve_pending_responsible_user(step, db: Session) -> Optional[str]:
    uid = step.approver_user_id
    if uid:
        return uid
    if step.approver_group_id:
        try:
            g = db.query(ApprovalGroup).filter(ApprovalGroup.id == step.approver_group_id).first()
            members = json.loads(g.member_ids or "[]") if g else []
            return members[0] if members else None
        except Exception:
            logger.warning("Failed to resolve responsible user from approval group=%s", step.approver_group_id, exc_info=True)
            return None
    return None

def _aggregate_pending_per_user(
    pending_requests, workflows: dict, user_stats: dict, now: datetime, db: Session
) -> None:
    for req in pending_requests:
        wf = workflows.get(req.workflow_id)
        if not wf:
            continue
        step = next((s for s in (wf.steps or []) if s.step_order == req.current_step), None)
        if not step:
            continue
        age_h = max(0.0, (now - req.step_started_at).total_seconds() / 3600.0) if req.step_started_at else 0.0
        uid = _resolve_pending_responsible_user(step, db)
        if uid:
            user_stats[uid]["user_id"] = uid
            user_stats[uid]["pending_count"] += 1
            user_stats[uid]["avg_pending_age_hours"] = (
                user_stats[uid]["avg_pending_age_hours"] + age_h
            )

def _build_approver_load_item(uid: str, row: dict, db: Session) -> dict:
    total = row["decisions_total"]
    reject_rate = round(row["rejected_count"] / total * 100, 2) if total else 0.0
    avg_response = round(row["decision_time_sum_hours"] / row["decision_time_count"], 2) if row["decision_time_count"] else 0.0
    pending = row["pending_count"]
    avg_age = round(row["avg_pending_age_hours"] / pending, 2) if pending else 0.0
    load_score = round(pending * 1.5 + avg_response * 0.1, 2)
    user_obj = db.query(User).filter(User.id == uid).first()
    return {
        "user_id": uid,
        "user_name": user_obj.full_name if user_obj else uid,
        "user_email": user_obj.email if user_obj else None,
        "decisions_total": total,
        "approved_count": row["approved_count"],
        "rejected_count": row["rejected_count"],
        "rejection_rate_pct": reject_rate,
        "avg_response_hours": avg_response,
        "pending_count": pending,
        "avg_pending_age_hours": avg_age,
        "load_score": load_score,
    }

def get_approver_load(db: Session, current_user, days: int = 90) -> dict:
    """Compute per-user approval load: pending, decided, avg response time, rejection rate."""
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=max(1, min(days, 365)))

    decisions = (
        db.query(ApprovalDecision)
        .filter(ApprovalDecision.decided_at >= since)
        .all()
    )

    pending_requests = (
        db.query(ApprovalRequest)
        .filter(ApprovalRequest.status == "pending")
        .all()
    )

    user_stats = defaultdict(_empty_approver_load_row)
    _aggregate_decisions_per_user(decisions, user_stats)

    wf_ids = list({r.workflow_id for r in pending_requests if r.workflow_id})
    workflows = _load_workflows_by_ids(db, wf_ids)
    _aggregate_pending_per_user(pending_requests, workflows, user_stats, now, db)

    items = [
        _build_approver_load_item(uid, row, db)
        for uid, row in user_stats.items()
        if uid
    ]

    items.sort(key=lambda x: x["load_score"], reverse=True)
    overloaded = [it for it in items if it["pending_count"] >= 5 or it["avg_pending_age_hours"] >= 48]
    return {
        "days": days,
        "since": since.isoformat(),
        "count": len(items),
        "items": items,
        "overloaded_approvers": overloaded,
    }
