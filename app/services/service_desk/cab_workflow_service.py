"""Comite de cambios (CAB) de los cambios ITSM.

Auditoria 2026-11: el comite era un JSON en `app_settings` por cambio, sin
pantalla, y aprobar un cambio no pasaba por el: cualquiera con acceso lo
ponia en `approved` con un PATCH. Ahora:

- los miembros salen de la cola configurada como CAB (`SD_CAB_GROUP_ID`); en
  un cambio de emergencia, solo sus responsables (el ECAB). Se pueden pasar a
  mano al iniciar;
- cada voto es una fila de `sd_change_approvals`;
- el cambio se aprueba al llegar al quorum (por defecto, mayoria simple) y se
  rechaza en cuanto el quorum ya no se puede alcanzar;
- la reunion y quien implementa quedan en el propio cambio.

`get_workflow` devuelve la misma forma que el JSON de antes, para no romper a
quien lo leia.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.service_desk import (
    AgentGroupMember,
    ChangeApproval,
    ChangeStatus,
    ChangeType,
    ITSMChangeRequest,
)
from app.models.user import User
from app.services import settings_service as _ss


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _cambio(db: Session, change_id: str) -> ITSMChangeRequest:
    change = db.query(ITSMChangeRequest).filter(ITSMChangeRequest.id == change_id).first()
    if not change:
        raise ValueError("change_not_found")
    return change


def miembros_del_cab(db: Session, change: ITSMChangeRequest) -> list[str]:
    """La cola CAB de la organizacion; en una emergencia, sus responsables."""
    grupo = _ss.get_runtime_str(db, "SD_CAB_GROUP_ID", change.organization_id)
    if not grupo:
        return []
    q = db.query(AgentGroupMember.user_id).filter(AgentGroupMember.group_id == grupo)
    if getattr(change.change_type, "value", change.change_type) == ChangeType.emergency.value:
        q = q.filter(AgentGroupMember.is_lead == True)  # noqa: E712
    ids = [r[0] for r in q.all()]
    activos = {r[0] for r in db.query(User.id).filter(User.id.in_(ids), User.is_active == True).all()}  # noqa: E712
    return [i for i in ids if i in activos]


def _votos(db: Session, change_id: str) -> list[ChangeApproval]:
    return db.query(ChangeApproval).filter(ChangeApproval.change_id == change_id).order_by(
        ChangeApproval.created_at).all()


def _estado(change: ITSMChangeRequest, votos: list[ChangeApproval]) -> str:
    st = getattr(change.status, "value", change.status)
    if st == ChangeStatus.cab_review.value:
        return "cab" if change.cab_meeting_at else "requester"
    if st == ChangeStatus.cancelled.value and change.rejected_reason:
        return "rejected"
    return "executor" if votos else st


def get_workflow(db: Session, *, change_id: str) -> dict | None:
    change = db.query(ITSMChangeRequest).filter(ITSMChangeRequest.id == change_id).first()
    if change is None:
        return None
    votos = _votos(db, change_id)
    if not votos:
        return None
    return {
        "change_id": change_id,
        "status": _estado(change, votos),
        "cab_members": [v.approver_user_id for v in votos],
        "quorum": change.cab_quorum,
        "meeting": ({"scheduled_at": change.cab_meeting_at.isoformat(), "agenda": change.cab_agenda}
                    if change.cab_meeting_at else None),
        "votes": [{"user_id": v.approver_user_id, "name": v.approver.full_name if v.approver else None,
                   "approved": v.decision == "approved", "decision": v.decision, "note": v.note,
                   "voted_at": v.decided_at.isoformat() if v.decided_at else None}
                  for v in votos],
        "executor_user_id": change.implementer_id,
    }


def start_cab_workflow(
    db: Session,
    *,
    change_id: str,
    requester: User,
    manager_user_id: Optional[str] = None,
    cab_members: Optional[list[str]] = None,
    quorum: Optional[int] = None,
) -> dict:
    """Pone el cambio en revision del CAB y pide el voto a cada miembro."""
    from app.services.notifications import notify_user

    change = _cambio(db, change_id)
    miembros = list(dict.fromkeys(cab_members or miembros_del_cab(db, change)))
    if not miembros:
        raise ValueError("cab_sin_miembros: configura la cola del CAB (SD_CAB_GROUP_ID)")
    regla = _ss.get_runtime_str(db, "SD_CAB_APPROVAL_RULE", change.organization_id) or "majority"
    if quorum is None:
        quorum = {"all": len(miembros), "any": 1}.get(regla, len(miembros) // 2 + 1)
    if not 1 <= quorum <= len(miembros):
        raise ValueError("quorum_invalido")

    db.query(ChangeApproval).filter(ChangeApproval.change_id == change_id).delete()
    for uid in miembros:
        db.add(ChangeApproval(organization_id=change.organization_id, change_id=change_id, approver_user_id=uid))
        notify_user(db, uid, "approval_requested", f"CAB: {change.number} — {change.title}"[:255],
                    "Tu voto es necesario para este cambio.", resource="changes", resource_id=change.id,
                    action_url="/service-desk")
    change.cab_quorum = quorum
    if manager_user_id and not change.owner_id:
        change.owner_id = manager_user_id
    change.status = ChangeStatus.cab_review
    change.rejected_reason = None
    db.flush()
    return get_workflow(db, change_id=change_id)


def schedule_cab_meeting(db: Session, *, change_id: str, manager: User, when_iso: str, agenda: str) -> dict:
    change = _cambio(db, change_id)
    if not _votos(db, change_id):
        raise ValueError("cab_workflow_not_found")
    try:
        cuando = datetime.fromisoformat(when_iso.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("fecha_invalida") from exc
    change.cab_meeting_at = cuando if cuando.tzinfo else cuando.replace(tzinfo=timezone.utc)
    change.cab_agenda = agenda
    db.flush()
    return get_workflow(db, change_id=change_id)


def cast_cab_vote(db: Session, *, change_id: str, voter: User, approve: bool, note: str = "") -> dict:
    """Registra el voto y, si ya se puede, decide el cambio."""
    change = _cambio(db, change_id)
    if getattr(change.status, "value", change.status) != ChangeStatus.cab_review.value:
        raise ValueError("el_cambio_no_esta_en_revision_del_cab")
    voto = db.query(ChangeApproval).filter(ChangeApproval.change_id == change_id,
                                           ChangeApproval.approver_user_id == voter.id).first()
    if voto is None:
        raise ValueError("user_not_in_cab")
    if not approve and not (note or "").strip():
        # El motivo es lo que queda como `rejected_reason` del cambio.
        raise ValueError("votar_en_contra_pide_motivo")
    voto.decision = "approved" if approve else "rejected"
    voto.note = note or None
    voto.decided_at = _ahora()
    db.flush()

    votos = _votos(db, change_id)
    a_favor = sum(1 for v in votos if v.decision == "approved")
    en_contra = sum(1 for v in votos if v.decision == "rejected")
    quorum = change.cab_quorum or (len(votos) // 2 + 1)
    if a_favor >= quorum:
        change.status = ChangeStatus.approved
        change.approved_at = _ahora()
        change.approved_by = voter.id
    elif len(votos) - en_contra < quorum:
        # Ya no hay votos suficientes para aprobarlo.
        change.status = ChangeStatus.cancelled
        motivos = [v.note for v in votos if v.decision == "rejected" and v.note]
        change.rejected_reason = "Rechazado por el CAB" + (": " + " · ".join(motivos) if motivos else "")
    db.flush()
    return get_workflow(db, change_id=change_id)


def assign_executor(db: Session, *, change_id: str, executor_user_id: str, manager: User) -> dict:
    change = _cambio(db, change_id)
    if not db.query(User.id).filter(User.id == executor_user_id, User.is_active == True).first():  # noqa: E712
        raise ValueError("executor_not_found")
    change.implementer_id = executor_user_id
    db.flush()
    return get_workflow(db, change_id=change_id)


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
