import json
from datetime import datetime, timezone as tz
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.services.numbering import next_numbered_code

from app.models.service_desk import ChangeStatus, ITSMChangeRequest, Problem, Ticket
from app.models.user import User
from app.services.service_desk.scoping import (
    _org_user_ids_subquery,
    scope_problem_query as _scope_problem_query,
    scope_ticket_query as _scope_ticket_query,
)


def cancelar_cambio(db, current_user, change_id: str) -> dict:
    """Cancela una solicitud de cambio. Es el boton de borrar de la interfaz.

    Auditoria 2026-08 (hallazgo 37). `DELETE /sd/changes/{id}` **no existia**,
    asi que el boton de borrar de un cambio **no hacia nada** — el otro borrado
    silencioso de la auditoria.

    **No borra la fila.** Una solicitud de cambio es un registro de gobernanza:
    tiene aprobaciones, ventana de mantenimiento, plan de rollback y su
    historial. `ChangeStatus` **si** tiene `cancelled`, que es exactamente el
    estado que corresponde.

    Un cambio ya implementado **no se cancela**: eso seria reescribir lo que
    paso. Se responde 409, no 400: el conflicto es con el estado actual del
    recurso.
    """
    from fastapi import HTTPException

    from app.models.service_desk import ChangeStatus

    cambio = get_change_by_id(db, current_user, change_id)
    if not cambio:
        raise HTTPException(404)

    TERMINALES = {
        ChangeStatus.implemented,
        ChangeStatus.closed_success,
        ChangeStatus.closed_failed,
    }
    if cambio.status in TERMINALES:
        raise HTTPException(
            409,
            f"No se puede cancelar un cambio en estado "
            f"{cambio.status.value}: ya se ha ejecutado")

    ya_estaba = cambio.status == ChangeStatus.cancelled
    if not ya_estaba:
        cambio.status = ChangeStatus.cancelled
    return {
        "ok": True,
        "id": cambio.id,
        "status": ChangeStatus.cancelled.value,
        "already_cancelled": ya_estaba,
    }


def scope_change_query(q, db: Session, current_user: User):
    if current_user.is_superadmin:
        return q
    org_user_ids = _org_user_ids_subquery(db, current_user)
    if org_user_ids is None:
        return q.filter(False)
    return q.filter(
        or_(
            ITSMChangeRequest.requester_id.in_(org_user_ids),
            ITSMChangeRequest.owner_id.in_(org_user_ids),
        )
    )


def build_change_list_query(
    db: Session,
    current_user: User,
    status: Optional[str],
    change_type: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
):
    q = db.query(ITSMChangeRequest).options(
        joinedload(ITSMChangeRequest.requester),
        joinedload(ITSMChangeRequest.owner),
    )
    q = scope_change_query(q, db, current_user)
    if status:
        q = q.filter(ITSMChangeRequest.status == status)
    if change_type:
        q = q.filter(ITSMChangeRequest.change_type == change_type)
    if date_from:
        q = q.filter(ITSMChangeRequest.created_at >= datetime.fromisoformat(date_from).replace(tzinfo=tz.utc))
    if date_to:
        q = q.filter(ITSMChangeRequest.created_at <= datetime.fromisoformat(date_to).replace(tzinfo=tz.utc))
    return q


def list_changes_payload(
    db: Session,
    current_user: User,
    status: Optional[str],
    change_type: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
    page: int,
    page_size: int,
) -> list[dict]:
    q = build_change_list_query(db, current_user, status, change_type, date_from, date_to)
    changes = (
        q.order_by(ITSMChangeRequest.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return [serialize_change(c) for c in changes]


def get_change_by_id(db: Session, current_user: User, change_id: str):
    return scope_change_query(db.query(ITSMChangeRequest), db, current_user).filter(
        ITSMChangeRequest.id == change_id
    ).first()


def get_change_payload(db: Session, current_user: User, change_id: str, full: bool = False) -> dict:
    change = get_change_by_id(db, current_user, change_id)
    if not change:
        raise HTTPException(404, "Change request no encontrado")
    return serialize_change(change, full=full)


def serialize_change(change: ITSMChangeRequest, full: bool = False) -> dict:
    base = {
        "id": change.id,
        "number": change.number,
        "title": change.title,
        "change_type": change.change_type.value if change.change_type else None,
        "status": change.status.value if change.status else None,
        "risk": change.risk.value if change.risk else None,
        "priority": change.priority.value if change.priority else None,
        "planned_start": str(change.planned_start) if change.planned_start else None,
        "planned_end": str(change.planned_end) if change.planned_end else None,
        "actual_start": str(change.actual_start) if change.actual_start else None,
        "actual_end": str(change.actual_end) if change.actual_end else None,
        "requester_id": change.requester_id,
        "requester": change.requester.full_name if change.requester else None,
        "owner_id": change.owner_id,
        "owner": change.owner.full_name if change.owner else None,
        "approved_by": change.approved_by,
        "approved_at": str(change.approved_at) if change.approved_at else None,
        "pir_success": change.pir_success,
        "pir_date": str(change.pir_date) if change.pir_date else None,
        "downtime_minutes": change.downtime_minutes,
        "created_at": str(change.created_at),
        "affected_cis": _lista_json(change.affected_cis),
        "release_id": change.release_id,
        "implementer_id": change.implementer_id,
        "rejected_reason": change.rejected_reason,
        # ITSM-P05: automated risk score always visible in list
        "auto_risk_score": change.auto_risk_score,
        "auto_risk_label": _score_to_label(change.auto_risk_score),
        "impact_analyzed": change.impact_analysis_json is not None,
        "suggested_window": _load_window(change.suggested_window_json),
    }
    if full:
        base.update(
            {
                "description": change.description,
                "business_justification": change.business_justification,
                "implementation_plan": change.implementation_plan,
                "rollback_plan": change.rollback_plan,
                "test_plan": change.test_plan,
                "impact_description": change.impact_description,
                "pir_notes": change.pir_notes,
            }
        )
    return base


def _lista_json(raw) -> list:
    try:
        valor = json.loads(raw or "[]")
    except (ValueError, TypeError):
        return []
    return valor if isinstance(valor, list) else []


def _score_to_label(score) -> str | None:
    if score is None:
        return None
    if score >= 75:
        return "critical"
    if score >= 55:
        return "high"
    if score >= 30:
        return "medium"
    return "low"


def _load_window(suggested_window_json: str | None) -> dict | None:
    if not suggested_window_json:
        return None
    try:
        import json
        return json.loads(suggested_window_json)
    except Exception:
        return None


def next_change_number(db: Session) -> str:
    return next_numbered_code(db, "itsm_change", prefix="CHG", padding=5, separator="")


def build_change_request(payload: dict, requester_id: str, number: str) -> ITSMChangeRequest:
    if not payload.get("title") or not payload.get("description"):
        raise HTTPException(422, "title y description son obligatorios")

    change = ITSMChangeRequest(
        number=number,
        title=payload["title"],
        description=payload["description"],
        change_type=payload.get("change_type", "normal"),
        risk=payload.get("risk", "medium"),
        priority=payload.get("priority", "p3_medium"),
        implementation_plan=payload.get("implementation_plan"),
        rollback_plan=payload.get("rollback_plan"),
        test_plan=payload.get("test_plan"),
        business_justification=payload.get("business_justification"),
        impact_description=payload.get("impact_description"),
        downtime_minutes=payload.get("downtime_minutes", 0),
        requester_id=requester_id,
        owner_id=payload.get("owner_id"),
        related_ticket_id=payload.get("related_ticket_id"),
        related_problem_id=payload.get("related_problem_id"),
    )
    if payload.get("planned_start"):
        change.planned_start = datetime.fromisoformat(payload["planned_start"]).replace(tzinfo=tz.utc)
    if payload.get("planned_end"):
        change.planned_end = datetime.fromisoformat(payload["planned_end"]).replace(tzinfo=tz.utc)
    return change


def apply_change_update(change: ITSMChangeRequest, payload: dict, current_user_id: str) -> None:
    for field in (
        "title",
        "description",
        "change_type",
        "risk",
        "priority",
        "implementation_plan",
        "rollback_plan",
        "test_plan",
        "business_justification",
        "impact_description",
        "downtime_minutes",
        "pir_notes",
        "pir_success",
        "owner_id",
        "release_id",
    ):
        if field in payload:
            setattr(change, field, payload[field])
    if "affected_cis" in payload:
        cis = payload["affected_cis"]
        change.affected_cis = json.dumps(list(cis)) if isinstance(cis, (list, tuple)) else cis

    for dt_field in ("planned_start", "planned_end", "actual_start", "actual_end", "pir_date"):
        if dt_field in payload and payload[dt_field]:
            setattr(change, dt_field, datetime.fromisoformat(payload[dt_field]).replace(tzinfo=tz.utc))


# Estados a los que no se llega con un PATCH: los decide el CAB.
_SOLO_POR_EL_CAB = {"approved"}
_A_REVISION = {"submitted", "cab_review"}


def _pasar_a_revision(db: Session, change: ITSMChangeRequest, current_user: User) -> None:
    """Estandar de bajo riesgo: se aprueba sola. El resto, al CAB."""
    from app.services.service_desk import cab_workflow_service as cab

    db.flush()
    _auto_score_change(db, change)
    if _maybe_auto_approve(db, change):
        return
    try:
        cab.start_cab_workflow(db, change_id=change.id, requester=current_user)
    except ValueError as exc:
        raise HTTPException(409, "No hay comité de cambios configurado (Service Desk → ajustes, "
                                 "SD_CAB_GROUP_ID): un cambio normal o de emergencia necesita su aprobación") from exc


def _aplicar_estado(db: Session, change: ITSMChangeRequest, nuevo: str, current_user: User) -> None:
    """Las transiciones con reglas: aprobar es del CAB y programar mira el calendario.

    Auditoria 2026-11: cualquiera con acceso al cambio lo ponia en `approved`
    con un PATCH, sin pasar por el comite.
    """
    from app.services.service_desk.change_calendar_service import exigir_ventana_libre

    if nuevo in _SOLO_POR_EL_CAB:
        raise HTTPException(409, "Un cambio se aprueba votando en el CAB, no editándolo")
    if nuevo in _A_REVISION:
        _pasar_a_revision(db, change, current_user)
        return
    if nuevo == "scheduled":
        estado = getattr(change.status, "value", change.status)
        if estado != "approved":
            raise HTTPException(409, "Solo se programa un cambio aprobado")
        exigir_ventana_libre(db, change)
    change.status = nuevo


def approve_change_request(change: ITSMChangeRequest, approved: bool, approver_id: str, reason: Optional[str]) -> None:
    change.status = ChangeStatus.approved if approved else ChangeStatus.cancelled
    change.approved_at = datetime.now(tz.utc)
    change.approved_by = approver_id
    if not approved:
        change.rejected_reason = reason or "Rechazado por CAB"


def _auto_score_change(db: Session, change: ITSMChangeRequest) -> None:
    """Run impact analysis and persist scores back to the change. No-commit.

    Called after the change is added to the session (id assigned) but before commit.
    Failures are silenced so they never block change creation.
    """
    try:
        from app.services.service_desk.change_impact_service import score_and_persist
        score_and_persist(db, change.id)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "Auto-score failed for change %s: %s", change.id, exc
        )


def _maybe_auto_approve(
    db: Session,
    change: ITSMChangeRequest,
    system_user_id: str | None = None,
) -> bool:
    """Auto-approve 'standard' changes with low risk score.

    Returns True if the change was auto-approved.
    """
    from app.models.service_desk import ChangeStatus
    try:
        change_type_val = change.change_type.value if hasattr(change.change_type, "value") else change.change_type
    except Exception:
        change_type_val = ""

    if change_type_val != "standard":
        return False
    score = change.auto_risk_score
    from app.services import settings_service as _ss
    maximo = _ss.get_runtime_int(db, "SD_CHANGE_AUTO_APPROVE_MAX_RISK", change.organization_id)
    if score is None or score > maximo:
        return False

    change.status = ChangeStatus.approved
    change.approved_at = datetime.now(tz.utc)
    # Lo aprueba la regla, no una persona: `approved_by` es una clave a usuarios
    # y antes recibia el texto "system-auto-approve".
    change.approved_by = system_user_id
    return True


def create_change_record(db: Session, current_user: User, payload: dict) -> ITSMChangeRequest:
    number = next_change_number(db)
    change = build_change_request(payload, current_user.id, number)
    enforce_change_org_constraints(db, current_user, change)
    db.add(change)
    db.flush()  # assign id before scoring
    _auto_score_change(db, change)
    _maybe_auto_approve(db, change)
    return change


def update_change_record(db: Session, current_user: User, change_id: str, payload: dict) -> ITSMChangeRequest:
    change = get_change_by_id(db, current_user, change_id)
    if not change:
        raise HTTPException(404)

    prev_status = change.status.value if hasattr(change.status, "value") else change.status
    apply_change_update(change, payload, current_user.id)
    enforce_change_org_constraints(db, current_user, change)
    nuevo = payload.get("status")
    if nuevo and nuevo != prev_status:
        _aplicar_estado(db, change, nuevo, current_user)
    return change


def approve_change_record(db: Session, current_user: User, change_id: str, payload: dict) -> ITSMChangeRequest:
    change = get_change_by_id(db, current_user, change_id)
    if not change:
        raise HTTPException(404)

    # Un miembro del CAB vota; un administrador fuera del comite decide por
    # encima (queda como quien lo aprobo o rechazo).
    from app.services.service_desk import cab_workflow_service as cab
    aprobar = payload.get("approved", True)
    try:
        cab.cast_cab_vote(db, change_id=change.id, voter=current_user, approve=aprobar,
                          note=payload.get("reason") or "")
        return change
    except ValueError as exc:
        if str(exc) != "user_not_in_cab":
            raise HTTPException(422, str(exc)) from exc
        if getattr(current_user.role, "value", current_user.role) != "admin" and not current_user.is_superadmin:
            raise HTTPException(403, "Solo vota un miembro del CAB")
    from app.services.approval_engine._base import exigir_que_no_sea_suyo
    exigir_que_no_sea_suyo(db, change.requester_id, current_user, "itsm_change", change.id)
    approve_change_request(change, approved=aprobar, approver_id=current_user.id, reason=payload.get("reason"))
    return change


def enforce_change_org_constraints(db: Session, current_user: User, change: ITSMChangeRequest) -> None:
    if current_user.is_superadmin or not current_user.organization_id:
        return

    if change.owner_id:
        owner = db.query(User).filter(User.id == change.owner_id).first()
        if not owner or owner.organization_id != current_user.organization_id:
            raise HTTPException(403, "No puedes asignar owner fuera de tu organización")

    if change.related_ticket_id:
        ticket = _scope_ticket_query(db.query(Ticket), db, current_user).filter(Ticket.id == change.related_ticket_id).first()
        if not ticket:
            raise HTTPException(403, "Ticket relacionado fuera de tu organización")

    if change.related_problem_id:
        problem = _scope_problem_query(db.query(Problem), db, current_user).filter(Problem.id == change.related_problem_id).first()
        if not problem:
            raise HTTPException(403, "Problema relacionado fuera de tu organización")
