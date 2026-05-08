"""Retention policies, legal hold, audit, eDiscovery."""
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin
from app.db.session import get_db
from app.models.user import User
from app.models.collaboration import (
    CollaborationAuditEvent, CollaborationLegalHold,
    CollaborationMessage, CollaborationRetentionPolicy,
)
from app.schemas.collaboration import (
    AuditEventOut, EDiscoveryRequest,
    LegalHoldIn, LegalHoldOut,
    RetentionPolicyIn, RetentionPolicyOut,
)
from app.services.collaboration import audit_log
from app.services.collaboration._permissions import _org

router = APIRouter()


# ── Retention ────────────────────────────────────────────────────────────────
@router.get("/retention", response_model=List[RetentionPolicyOut], summary="Políticas de retención")
def list_policies(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(CollaborationRetentionPolicy).filter(CollaborationRetentionPolicy.organization_id == _org(current_user)).all()
    return [RetentionPolicyOut(
        id=r.id, name=r.name, scope=r.scope, target_id=r.target_id,
        retention_months=r.retention_months, apply_to=r.apply_to, is_active=r.is_active,
    ) for r in rows]


@router.post("/retention", response_model=RetentionPolicyOut, summary="Crear política de retención",
             dependencies=[Depends(require_admin)])
def create_policy(payload: RetentionPolicyIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.services.collaboration.workspaces import get_or_create_workspace
    ws = get_or_create_workspace(db, current_user)
    row = CollaborationRetentionPolicy(
        organization_id=_org(current_user), workspace_id=ws.id,
        name=payload.name, scope=payload.scope, target_id=payload.target_id,
        retention_months=payload.retention_months, apply_to=payload.apply_to,
    )
    db.add(row)
    audit_log.write(
        db, organization_id=_org(current_user), actor_user_id=current_user.id, actor_client_id=None,
        action="retention.created", entity_type="retention_policy", entity_id=row.id,
        payload=payload.model_dump(),
    )
    db.commit()
    return RetentionPolicyOut(
        id=row.id, name=row.name, scope=row.scope, target_id=row.target_id,
        retention_months=row.retention_months, apply_to=row.apply_to, is_active=row.is_active,
    )


@router.post("/retention/run", summary="Ejecutar barrido de retención (manual)",
             dependencies=[Depends(require_admin)])
def run_retention(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Marks expired messages as deleted according to active policies.

    Legal hold scope is respected — protected messages are NOT removed.
    """
    org = _org(current_user)
    policies = db.query(CollaborationRetentionPolicy).filter(
        CollaborationRetentionPolicy.organization_id == org,
        CollaborationRetentionPolicy.is_active == True,
    ).all()
    now = datetime.utcnow()
    held = _legal_held_message_ids(db, org)
    deleted = 0
    for pol in policies:
        cutoff = now - timedelta(days=30 * pol.retention_months)
        q = db.query(CollaborationMessage).filter(
            CollaborationMessage.organization_id == org,
            CollaborationMessage.sent_at < cutoff,
            CollaborationMessage.status != "deleted",
        )
        if held:
            q = q.filter(~CollaborationMessage.id.in_(held))
        for m in q.all():
            m.status = "deleted"
            m.deleted_at = now
            m.body = "[retention purge]"
            deleted += 1
    audit_log.write(
        db, organization_id=org, actor_user_id=current_user.id, actor_client_id=None,
        action="retention.run", entity_type="retention", entity_id=None,
        payload={"deleted": deleted, "policies": len(policies)},
    )
    db.commit()
    return {"deleted": deleted, "policies_applied": len(policies)}


# ── Legal Hold ───────────────────────────────────────────────────────────────
@router.get("/legal-holds", response_model=List[LegalHoldOut], summary="Casos de legal hold")
def list_holds(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(CollaborationLegalHold).filter(CollaborationLegalHold.organization_id == _org(current_user)).all()
    return [LegalHoldOut(
        id=r.id, case_reference=r.case_reference, description=r.description,
        custodian_user_ids=r.custodian_user_ids or [],
        custodian_client_ids=r.custodian_client_ids or [],
        channel_ids=r.channel_ids or [],
        started_at=r.started_at, ended_at=r.ended_at, is_active=r.is_active,
    ) for r in rows]


@router.post("/legal-holds", response_model=LegalHoldOut, summary="Crear legal hold",
             dependencies=[Depends(require_admin)])
def create_hold(payload: LegalHoldIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = CollaborationLegalHold(
        organization_id=_org(current_user),
        case_reference=payload.case_reference, description=payload.description,
        custodian_user_ids=payload.custodian_user_ids,
        custodian_client_ids=payload.custodian_client_ids,
        channel_ids=payload.channel_ids,
        created_by=current_user.id,
    )
    db.add(row)
    audit_log.write(
        db, organization_id=_org(current_user), actor_user_id=current_user.id, actor_client_id=None,
        action="legal_hold.created", entity_type="legal_hold", entity_id=row.id,
        payload=payload.model_dump(),
    )
    db.commit()
    return LegalHoldOut(
        id=row.id, case_reference=row.case_reference, description=row.description,
        custodian_user_ids=row.custodian_user_ids or [],
        custodian_client_ids=row.custodian_client_ids or [],
        channel_ids=row.channel_ids or [],
        started_at=row.started_at, ended_at=row.ended_at, is_active=row.is_active,
    )


@router.post("/legal-holds/{hold_id}/release", summary="Cerrar legal hold",
             dependencies=[Depends(require_admin)])
def release_hold(hold_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.query(CollaborationLegalHold).filter(CollaborationLegalHold.id == hold_id, CollaborationLegalHold.organization_id == _org(current_user)).first()
    if not row:
        raise HTTPException(404, "Hold no encontrado")
    row.is_active = False
    row.ended_at = datetime.utcnow()
    audit_log.write(
        db, organization_id=_org(current_user), actor_user_id=current_user.id, actor_client_id=None,
        action="legal_hold.released", entity_type="legal_hold", entity_id=hold_id, payload={},
    )
    db.commit()
    return {"ok": True}


def _legal_held_message_ids(db: Session, organization_id: str) -> set[str]:
    rows = db.query(CollaborationLegalHold).filter(
        CollaborationLegalHold.organization_id == organization_id,
        CollaborationLegalHold.is_active == True,
    ).all()
    if not rows:
        return set()
    user_ids = set()
    client_ids = set()
    channel_ids = set()
    for r in rows:
        user_ids.update(r.custodian_user_ids or [])
        client_ids.update(r.custodian_client_ids or [])
        channel_ids.update(r.channel_ids or [])
    msg_q = db.query(CollaborationMessage.id).filter(CollaborationMessage.organization_id == organization_id)
    if user_ids:
        msg_q = msg_q.filter(CollaborationMessage.user_id.in_(user_ids))
    return {r[0] for r in msg_q.all()}


# ── eDiscovery export ────────────────────────────────────────────────────────
@router.post("/ediscovery/export", summary="Export legal (eDiscovery JSON)",
             dependencies=[Depends(require_admin)])
def ediscovery_export(payload: EDiscoveryRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = _org(current_user)
    q = db.query(CollaborationMessage).filter(CollaborationMessage.organization_id == org)
    if payload.user_ids:
        q = q.filter(CollaborationMessage.user_id.in_(payload.user_ids))
    if payload.date_from:
        q = q.filter(CollaborationMessage.sent_at >= payload.date_from)
    if payload.date_to:
        q = q.filter(CollaborationMessage.sent_at <= payload.date_to)
    if payload.keywords:
        for kw in payload.keywords[:5]:
            q = q.filter(CollaborationMessage.body.ilike(f"%{kw}%"))
    rows = q.order_by(CollaborationMessage.sent_at.asc()).limit(20000).all()
    audit_log.write(
        db, organization_id=org, actor_user_id=current_user.id, actor_client_id=None,
        action="ediscovery.export", entity_type="export", entity_id=None,
        payload={"case": payload.case_reference, "matched": len(rows)},
    )
    db.commit()
    return {
        "case_reference": payload.case_reference,
        "exported_at": datetime.utcnow().isoformat(),
        "total": len(rows),
        "messages": [{
            "id": m.id, "conversation_id": m.conversation_id,
            "user_id": m.user_id, "body": m.body, "sent_at": m.sent_at, "status": m.status,
            "type": m.type,
        } for m in rows],
    }


# ── Audit ────────────────────────────────────────────────────────────────────
@router.get("/decisions", summary="Listado de decisiones gobernadas")
def list_decisions(limit: int = 100, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Decisiones registradas con `/decision <texto>` extraídas del audit log."""
    rows = db.query(CollaborationAuditEvent).filter(
        CollaborationAuditEvent.organization_id == _org(current_user),
        CollaborationAuditEvent.action == "decision.recorded",
    ).order_by(CollaborationAuditEvent.created_at.desc()).limit(min(limit, 500)).all()
    out = []
    for r in rows:
        payload = r.payload or {}
        out.append({
            "id": r.id,
            "text": payload.get("text", ""),
            "actor_user_id": r.actor_user_id,
            "conversation_id": r.entity_id,
            "created_at": r.created_at,
        })
    return out


@router.get("/audit", response_model=List[AuditEventOut], summary="Eventos de auditoría",
            dependencies=[Depends(require_admin)])
def list_audit(limit: int = 200, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(CollaborationAuditEvent).filter(
        CollaborationAuditEvent.organization_id == _org(current_user),
    ).order_by(CollaborationAuditEvent.created_at.desc()).limit(min(limit, 1000)).all()
    return [AuditEventOut(
        id=r.id, actor_user_id=r.actor_user_id, action=r.action, entity_type=r.entity_type,
        entity_id=r.entity_id, payload=r.payload or {}, created_at=r.created_at,
    ) for r in rows]


@router.get("/audit/verify", summary="Verificar integridad de la cadena de auditoría",
            dependencies=[Depends(require_admin)])
def verify_audit(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return audit_log.verify_chain(db, _org(current_user))
