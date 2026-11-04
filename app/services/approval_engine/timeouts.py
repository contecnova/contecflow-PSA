"""approval_engine.timeouts — extracted from the former 1827-LOC god-file."""

from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.billing_reports import FinancialApprovalAuditLog
from app.models.billing_reports import ApprovalRequest
from app.models.billing_reports import ApprovalDecision
from app.models.billing_reports import ApprovalStep
from datetime import timedelta


from app.services.approval_engine._base import _FINANCIAL_ENTITY_TYPES

# Auditoria 2026-11. Tres defectos: el rechazo por caducidad cerraba la
# solicitud pero no tocaba la entidad (el gasto seguia pendiente en su
# pantalla); auto-aprobar y escalar sumaban 1 al paso sin mirar si era el
# ultimo, y la solicitud se quedaba «pendiente» de un paso que no existe; y
# escalar se SALTABA el paso en vez de pasarselo a la persona de escalado.

def _actor(req, step, db: Session):
    """Quien firma lo que decide el reloj: el aprobador del paso, la persona de
    escalado o, si no hay, un admin activo de la organizacion de la solicitud."""
    from app.models.user import User, UserRole
    for uid in (getattr(step, "approver_user_id", None), getattr(step, "escalate_to_user_id", None)):
        if uid:
            u = db.query(User).filter(User.id == uid).first()
            if u:
                return u
    q = db.query(User).filter(User.role == UserRole.admin, User.is_active.is_(True))
    if req.organization_id:
        q = q.filter(User.organization_id == req.organization_id)
    return q.first()


def _cerrar(req, decision: str, nota: str, now: datetime, actor, db: Session) -> None:
    from app.services.approval_engine._base import _apply_entity_final_decision
    req.status = decision
    req.final_decision = decision
    req.final_note = nota
    req.completed_at = now
    db.flush()
    if actor is not None:
        _apply_entity_final_decision(req, decision, actor, db)


def _siguiente_o_cerrar(req, step, now: datetime, nota: str, db: Session) -> str:
    """Tras aprobar un paso: el siguiente aplicable o, si era el ultimo, aprobada."""
    from app.services.approval_engine._base import notify_approver
    from app.services.approval_engine.requests import _step_condition_met
    pasos = db.query(ApprovalStep).filter(ApprovalStep.workflow_id == req.workflow_id).order_by(
        ApprovalStep.step_order).all()
    siguientes = [s for s in pasos if s.step_order > req.current_step and not s.is_optional
                  and _step_condition_met(s, req)]
    if siguientes:
        req.current_step = siguientes[0].step_order
        req.step_started_at = now
        notify_approver(req, siguientes[0], db)
        return "auto_approved"
    _cerrar(req, "approved", nota, now, _actor(req, step, db), db)
    return "auto_approved"


def _ya_escalado(req, step) -> bool:
    return any(d.step_order == step.step_order and d.decision == "delegated"
               and (d.note or "").startswith("Escalado automáticamente")
               for d in (req.decisions or []))


def _handle_timeout_escalate(req, step, now: datetime, info: dict, db: Session) -> str:
    """Pasa el paso a la persona de escalado (sin saltarlo). Si ya se escalo y
    vuelve a caducar, o no hay a quien escalar, se rechaza."""
    from app.services.approval_engine._base import notify_approver
    if step.escalate_to_user_id and not _ya_escalado(req, step):
        db.add(ApprovalDecision(
            request_id=req.id,
            step_order=step.step_order,
            approver_id=step.escalate_to_user_id,
            decision="delegated",
            note="Escalado automáticamente por timeout",
            decided_at=now,
        ))
        req.step_started_at = now
        notify_approver(req, step, db, explicit_user_id=step.escalate_to_user_id)
        info["escalated_to"] = step.escalate_to_user_id
        return "escalated"
    _cerrar(req, "rejected", "Rechazado automáticamente por timeout (sin escalado posible)", now,
            _actor(req, step, db), db)
    info["rejected"] = True
    return "rejected"


def _handle_timeout_auto_approve(req, step, now: datetime, info: dict, db: Session) -> str:
    firma = _actor(req, step, db)
    if firma is None:
        # Nadie en cuyo nombre aprobar: no se aprueba a ciegas.
        return _handle_timeout_reject(req, step, now, info, db)
    db.add(ApprovalDecision(
        request_id=req.id,
        step_order=step.step_order,
        approver_id=firma.id,
        decision="approved",
        note="Aprobado automáticamente por timeout",
        decided_at=now,
    ))
    info["auto_approved"] = True
    return _siguiente_o_cerrar(req, step, now, "Aprobado automáticamente por timeout", db)


def _handle_timeout_reject(req, step, now: datetime, info: dict, db: Session) -> str:
    _cerrar(req, "rejected", "Rechazado automáticamente por timeout", now, _actor(req, step, db), db)
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
    inicio = req.step_started_at
    if inicio.tzinfo is None:
        inicio = inicio.replace(tzinfo=timezone.utc)
    timeout_at = inicio + timedelta(hours=step.timeout_hours)
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
        manejador = {"escalate": _handle_timeout_escalate, "auto_approve": _handle_timeout_auto_approve,
                     "reject": _handle_timeout_reject, "auto_reject": _handle_timeout_reject}.get(action)
        if manejador is None:
            continue
        # Cada solicitud en su organizacion. Lo que se aplica a la entidad
        # (revisar un gasto…) confirma por su cuenta, asi que no cabe en un
        # savepoint: si falla se deshace lo pendiente y se sigue con las demas.
        from app.services.service_desk.ticket_events import como_organizacion
        try:
            with como_organizacion(db, req.organization_id):
                bucket = manejador(req, step, now, info, db)
                db.commit()
        except Exception:
            import logging
            db.rollback()
            logging.getLogger(__name__).exception("timeout de la aprobacion %s", req.id)
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
