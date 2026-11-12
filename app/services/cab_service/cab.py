"""Comite de cambios (CAB): cambios pendientes, votos y ventanas de mantenimiento.

Parte de `app.services.cab_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session, joinedload
from app.models.resources import ChangeRequest
from app.models.cab import CABVote, ChangeRequestWindow
from app.models.cab import MaintenanceWindow
from app.services.audit import audit_log
from collections import defaultdict


# ─── CAB Vote helpers ─────────────────────────────────────────────────────────

def get_cab_pending_changes(db: Session, current_user_id: str) -> list:
    crs = db.query(ChangeRequest).options(
        joinedload(ChangeRequest.project),
        joinedload(ChangeRequest.requester),
    ).filter(
        ChangeRequest.status.in_(["submitted", "under_review"])
    ).order_by(ChangeRequest.created_at.desc()).all()

    cr_ids = [cr.id for cr in crs]
    if cr_ids:
        all_votes = db.query(CABVote).filter(CABVote.change_request_id.in_(cr_ids)).all()
        all_windows = db.query(ChangeRequestWindow).filter(
            ChangeRequestWindow.change_request_id.in_(cr_ids)
        ).all()
    else:
        all_votes, all_windows = [], []

    votes_by_cr: dict = defaultdict(list)
    for _v in all_votes:
        votes_by_cr[_v.change_request_id].append(_v)
    windows_by_cr: dict = defaultdict(list)
    for _w in all_windows:
        windows_by_cr[_w.change_request_id].append(_w)

    result = []
    for cr in crs:
        votes = votes_by_cr[cr.id]
        approvals = sum(1 for v in votes if v.vote == "approve")
        rejections = sum(1 for v in votes if v.vote == "reject")
        windows = windows_by_cr[cr.id]
        my_vote = next((v.vote for v in votes if v.voter_id == current_user_id), None)
        result.append({
            "id": cr.id, "code": cr.code, "title": cr.title,
            "status": cr.status,
            "impact": cr.impact,
            "cost_impact": cr.cost_impact,
            "schedule_impact_days": cr.schedule_impact_days,
            "project_name": cr.project.name if cr.project else None,
            "project_code": cr.project.code if cr.project else None,
            "requester": cr.requester.full_name if cr.requester else None,
            "created_at": str(cr.created_at)[:10] if cr.created_at else None,
            "votes": {"approve": approvals, "reject": rejections, "total": len(votes)},
            "my_vote": my_vote,
            "has_window": len(windows) > 0,
            "rollback_plan": windows[0].rollback_plan if windows else None,
        })
    return result


def cast_cab_vote(cr_id: str, vote: str, comment: Optional[str], current_user, db: Session) -> dict:
    cr = db.query(ChangeRequest).filter(ChangeRequest.id == cr_id).first()
    if not cr:
        raise ValueError("CR no encontrada")
    if cr.status not in ["submitted", "under_review"]:
        raise ValueError(f"No se puede votar en estado '{cr.status}'")
    if vote not in ["approve", "reject", "abstain"]:
        raise ValueError("Voto debe ser: approve, reject o abstain")

    existing = db.query(CABVote).filter(
        CABVote.change_request_id == cr_id,
        CABVote.voter_id == current_user.id,
    ).first()
    if existing:
        existing.vote = vote
        existing.comment = comment
    else:
        db.add(CABVote(
            change_request_id=cr_id,
            voter_id=current_user.id,
            vote=vote,
            comment=comment,
        ))

    if cr.status == "submitted":
        cr.status = "under_review"

    audit_log(db, current_user, "CAB_VOTE", "change_requests", cr_id, cr.code,
              new_values={"vote": vote})
    db.commit()

    votes = db.query(CABVote).filter(CABVote.change_request_id == cr_id).all()
    approvals = sum(1 for v in votes if v.vote == "approve")
    rejections = sum(1 for v in votes if v.vote == "reject")
    return {"ok": True, "vote": vote, "approvals": approvals, "rejections": rejections}


def close_cab_vote(cr_id: str, decision: str, reason: Optional[str], current_user, db: Session) -> dict:
    cr = db.query(ChangeRequest).filter(ChangeRequest.id == cr_id).first()
    if not cr:
        raise ValueError("CR no encontrada")
    if decision not in ["approved", "rejected"]:
        raise ValueError("decision debe ser approved o rejected")
    # Revisión 2026-11: sólo se cierra una votación abierta, y una decisión que
    # va contra el recuento (o con empate) necesita su motivo, que queda auditado.
    estado = str(getattr(cr.status, "value", cr.status))
    if estado not in ("submitted", "under_review"):
        raise ValueError(f"Sólo se cierra una votación abierta; esta CR está «{estado}»")
    votos = [v.vote for v in db.query(CABVote).filter(CABVote.change_request_id == cr_id).all()]
    a_favor, en_contra = votos.count("approve"), votos.count("reject")
    mayoria = "approved" if a_favor > en_contra else "rejected" if en_contra > a_favor else None
    if decision != mayoria and not (reason or "").strip():
        raise ValueError(f"La decisión no sigue la votación ({a_favor} a favor, {en_contra} en contra): indica el motivo")
    cr.status = decision
    audit_log(db, current_user, "CAB_CLOSE", "change_requests", cr_id, cr.code,
              new_values={"decision": decision, "reason": reason, "a_favor": a_favor, "en_contra": en_contra})
    db.commit()
    return {"ok": True, "new_status": cr.status}


# ─── Maintenance windows ──────────────────────────────────────────────────────

def list_maintenance_windows(upcoming_only: bool, db: Session) -> list:
    q = db.query(MaintenanceWindow).options(joinedload(MaintenanceWindow.creator))
    if upcoming_only:
        q = q.filter(MaintenanceWindow.start_dt >= datetime.now(timezone.utc))
    windows = q.order_by(MaintenanceWindow.start_dt).limit(50).all()
    return [{
        "id": w.id, "name": w.name, "description": w.description,
        "start_dt": str(w.start_dt)[:16], "end_dt": str(w.end_dt)[:16],
        "environment": w.environment,
        "is_recurring": w.is_recurring,
        "creator": w.creator.full_name if w.creator else None,
        "created_at": str(w.created_at)[:10] if w.created_at else None,
    } for w in windows]


def create_maintenance_window(payload, current_user_id: str, db: Session) -> dict:
    w = MaintenanceWindow(**payload.model_dump(), created_by=current_user_id)
    db.add(w); db.commit(); db.refresh(w)
    return {"ok": True, "id": w.id}


def schedule_cr_in_window(cr_id: str, window_id: str, rollback_plan: Optional[str], test_plan: Optional[str], db: Session) -> dict:
    cr = db.query(ChangeRequest).filter(ChangeRequest.id == cr_id).first()
    if not cr:
        raise ValueError("CR no encontrada")
    if not db.query(MaintenanceWindow).filter(MaintenanceWindow.id == window_id).first():
        raise ValueError("Ventana de mantenimiento no encontrada")
    crw = ChangeRequestWindow(
        change_request_id=cr_id,
        window_id=window_id,
        rollback_plan=rollback_plan,
        test_plan=test_plan,
    )
    db.add(crw); db.commit()
    return {"ok": True}
