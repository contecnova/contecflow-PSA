"""Retention policies, legal hold, audit, eDiscovery."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin
from app.core.ratelimit import limiter
from app.db.session import get_db
from app.models.user import User
from app.schemas.collaboration import (
    AuditEventOut, EDiscoveryRequest,
    LegalHoldIn, LegalHoldOut,
    RetentionPolicyIn, RetentionPolicyOut,
)
from app.services.collaboration import audit_log
from app.services.collaboration import compliance as svc
from app.services.collaboration._permissions import _org
from app.core.responses import APIListResponse, APIResponse

router = APIRouter()
# Auditoria 2026-08 (hallazgo 22). Los 18 puntos de acceso a base de este
# fichero estan ahora en `app/services/collaboration/compliance.py`, y al
# moverlos aparecio un defecto en el legal hold: retenia solo por usuario
# custodio e ignoraba clientes y canales. Ver la cabecera de ese modulo.


# ── Retention ────────────────────────────────────────────────────────────────
@router.get("/retention", response_model=APIListResponse[RetentionPolicyOut], summary="Políticas de retención")
def list_policies(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = [
        RetentionPolicyOut(
            id=r.id, name=r.name, scope=r.scope, target_id=r.target_id,
            retention_months=r.retention_months, apply_to=r.apply_to,
            is_active=r.is_active,
        )
        for r in svc.list_policies(db, current_user)
    ]
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/retention", response_model=APIResponse[RetentionPolicyOut], summary="Crear política de retención",
             dependencies=[Depends(require_admin)])
def create_policy(payload: RetentionPolicyIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = svc.create_policy(db, current_user, payload.model_dump())
    return APIResponse.ok(data=RetentionPolicyOut(
        id=row.id, name=row.name, scope=row.scope, target_id=row.target_id,
        retention_months=row.retention_months, apply_to=row.apply_to,
        is_active=row.is_active,
    ))


@router.post("/retention/run", summary="Ejecutar barrido de retención (manual)",
             dependencies=[Depends(require_admin)])
def run_retention(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Marca como borrados los mensajes vencidos segun las politicas activas.

    El legal hold se respeta: los mensajes retenidos NO se borran.
    """
    return APIResponse.ok(data=svc.run_retention(db, current_user))


@router.get("/retention/settings", summary="Config retention por tenant", dependencies=[Depends(require_admin)])
def get_retention_settings(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return APIResponse.ok(data=svc.get_retention_settings(db, _org(current_user)))


@router.put("/retention/settings", summary="Actualizar config retention por tenant", dependencies=[Depends(require_admin)])
def put_retention_settings(payload: dict, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return APIResponse.ok(data=svc.set_retention_settings(db, _org(current_user), payload))


# ── Legal Hold ───────────────────────────────────────────────────────────────
@router.get("/legal-holds", response_model=APIListResponse[LegalHoldOut], summary="Casos de legal hold")
def list_holds(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = [
        LegalHoldOut(
            id=r.id, case_reference=r.case_reference, description=r.description,
            custodian_user_ids=r.custodian_user_ids or [],
            custodian_client_ids=r.custodian_client_ids or [],
            channel_ids=r.channel_ids or [],
            started_at=r.started_at, ended_at=r.ended_at, is_active=r.is_active,
        )
        for r in svc.list_holds(db, current_user)
    ]
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/legal-holds", response_model=APIResponse[LegalHoldOut], summary="Crear legal hold",
             dependencies=[Depends(require_admin)])
def create_hold(payload: LegalHoldIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = svc.create_hold(db, current_user, payload.model_dump())
    return APIResponse.ok(data=LegalHoldOut(
        id=row.id, case_reference=row.case_reference, description=row.description,
        custodian_user_ids=row.custodian_user_ids or [],
        custodian_client_ids=row.custodian_client_ids or [],
        channel_ids=row.channel_ids or [],
        started_at=row.started_at, ended_at=row.ended_at, is_active=row.is_active,
    ))


@router.post("/legal-holds/{hold_id}/release", summary="Cerrar legal hold",
             dependencies=[Depends(require_admin)])
def release_hold(hold_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc.release_hold(db, current_user, hold_id)
    return APIResponse.ok(data={"ok": True})


# ── eDiscovery export ────────────────────────────────────────────────────────
@router.post("/ediscovery/export", summary="Export legal (eDiscovery JSON)",
             dependencies=[Depends(require_admin)])
def ediscovery_export(payload: EDiscoveryRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return APIResponse.ok(data=svc.ediscovery_export(
        db, current_user,
        case_reference=payload.case_reference, user_ids=payload.user_ids,
        date_from=payload.date_from, date_to=payload.date_to,
        keywords=payload.keywords,
    ))


# ── Audit ────────────────────────────────────────────────────────────────────
@router.get("/decisions", response_model=APIListResponse[dict], summary="Listado de decisiones gobernadas")
def list_decisions(limit: int = 100, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Decisiones registradas por comando de decision, extraidas del audit log."""
    out = svc.list_decisions(db, current_user, limit)
    return APIListResponse.ok(items=out, total=len(out))


@router.get("/audit", response_model=APIListResponse[AuditEventOut], summary="Eventos de auditoría",
            dependencies=[Depends(require_admin)])
@limiter.limit("30/minute")
def list_audit(request: Request, limit: int = 200, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = [
        AuditEventOut(
            id=r.id, actor_user_id=r.actor_user_id, action=r.action,
            entity_type=r.entity_type, entity_id=r.entity_id,
            payload=r.payload or {}, created_at=r.created_at,
        )
        for r in svc.list_audit(db, current_user, limit)
    ]
    return APIListResponse.ok(items=items, total=len(items))


@router.get("/audit/verify", summary="Verificar integridad de la cadena de auditoría",
            dependencies=[Depends(require_admin)])
def verify_audit(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return APIResponse.ok(data=audit_log.verify_chain(db, _org(current_user)))
