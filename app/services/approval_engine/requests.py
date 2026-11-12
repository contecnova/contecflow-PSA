"""approval_engine.requests — extracted from the former 1827-LOC god-file."""

from __future__ import annotations
import json
import operator
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session, joinedload
from app.models.user import User
from app.models.billing_reports import ApprovalRequest
from app.models.billing_reports import ApprovalWorkflow
from app.models.billing_reports import ApprovalDecision
from app.core.errores import ErrorDeDominio


from app.services.approval_engine._base import _apply_entity_final_decision, _is_authorized, _notify_requester_approved, _record_sod_violation, find_default_workflow, log_financial_approval_event, logger, notify_approver, scope_request_query

def create_approval_request(payload, db: Session, current_user: User, confirmar: bool = True) -> dict:
    """
    payload must have: workflow_id (optional), entity_type, entity_id, entity_summary (optional)
    Returns serialised ApprovalRequest dict (caller should use _request_out).
    Raises HTTPException if no workflow found.

    `confirmar=False` (revisión 2026-11): la abre una automatización dentro de
    su propia transacción; se hace flush y quien llama confirma.
    """

    wf_id = payload.workflow_id
    if not wf_id:
        from app.services.approval_engine._base import elegir_flujo
        contexto = dict(getattr(payload, "context", None) or {})
        contexto.setdefault("category", getattr(payload, "category", None))
        # El departamento de quien pide, para las condiciones por departamento.
        contexto.setdefault("department", getattr(current_user, "department", None))
        wf = elegir_flujo(db, payload.entity_type, contexto)
        if not wf:
            raise ErrorDeDominio(
                404, f"No hay flujo de aprobación configurado para '{payload.entity_type}'"
            )
        wf_id = wf.id
    else:
        wf = db.query(ApprovalWorkflow).filter(ApprovalWorkflow.id == wf_id).first()
        if not wf:
            raise ErrorDeDominio(404, "Flujo no encontrado")

    # ── Auto-aprobación: comprobar reglas antes de crear la solicitud ──────────
    auto_result = _check_auto_approval(wf, payload)
    if auto_result:
        # Crear la solicitud ya aprobada directamente
        req = ApprovalRequest(
            id=str(uuid.uuid4()),
            workflow_id=wf_id,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            entity_summary=getattr(payload, 'entity_summary', None),
            requested_by=current_user.id,
            current_step=1,
            status="approved",
            final_decision="approved",
            final_note=f"Auto-aprobado por regla: {auto_result}",
            completed_at=datetime.now(timezone.utc),
            step_started_at=datetime.now(timezone.utc),
        )
        db.add(req)
        db.flush()
        log_financial_approval_event(
            db=db, request_id=req.id, entity_type=req.entity_type,
            entity_id=req.entity_id, action="approved", decision="approved",
            actor_user_id=current_user.id, step_order=0,
            note=req.final_note,
        )
        _apply_entity_final_decision(req, "approved", current_user, db)
        if confirmar:
            db.commit()
            db.refresh(req)
        else:
            db.flush()
        return req

    req = ApprovalRequest(
        id=str(uuid.uuid4()),
        workflow_id=wf_id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        entity_summary=getattr(payload, 'entity_summary', None),
        requested_by=current_user.id,
        current_step=1,
        status="pending",
        step_started_at=datetime.now(timezone.utc),
    )
    db.add(req)
    db.flush()
    log_financial_approval_event(
        db=db,
        request_id=req.id,
        entity_type=req.entity_type,
        entity_id=req.entity_id,
        action="requested",
        actor_user_id=current_user.id,
        step_order=1,
        note=getattr(payload, 'entity_summary', None),
    )

    # Skip steps whose condition is not met
    first_step = _first_active_step(wf.steps, req)
    if first_step:
        notify_approver(req, first_step, db)

    if confirmar:
        db.commit()
        db.refresh(req)
    else:
        db.flush()
    from app.core.events import emit, EventType
    emit(db, EventType.APPROVAL_REQUESTED,
         {"entity_type": req.entity_type, "entity_id": req.entity_id,
          "summary": req.entity_summary, "workflow_id": req.workflow_id},
         resource_type="approval_request", resource_id=req.id)
    return req

def _load_request_and_workflow_for_decision(
    request_id: str, db: Session, current_user: User
):
    """Load request, workflow and current step for a decision, raising HTTPException on errors."""
    req = db.query(ApprovalRequest).options(
        joinedload(ApprovalRequest.decisions)
    )
    req = scope_request_query(req, db, current_user).filter(
        ApprovalRequest.id == request_id
    ).first()
    if not req:
        raise ErrorDeDominio(404)
    if req.status != "pending":
        raise ErrorDeDominio(400, f"La solicitud ya está en estado '{req.status}'")

    wf = db.query(ApprovalWorkflow).options(
        joinedload(ApprovalWorkflow.steps)
    ).filter(ApprovalWorkflow.id == req.workflow_id).first()
    if not wf:
        raise ErrorDeDominio(404, "Flujo no encontrado")

    steps = sorted(wf.steps, key=lambda s: s.step_order)
    step = next((s for s in steps if s.step_order == req.current_step), None)
    if not step:
        raise ErrorDeDominio(400, "No se encontró el paso actual del flujo de aprobación")
    return req, wf, steps, step

def _validate_decision_authorization(
    req, step, decision: str, attachment_url: Optional[str], current_user: User, db: Session
) -> None:
    """Apply authorization / SoD / attachment / double-vote validations."""
    if not _is_authorized(step, current_user, req.requested_by, db, req=req):
        raise ErrorDeDominio(403, "No tienes permiso para aprobar este paso")

    if req.requested_by == current_user.id:
        _record_sod_violation(req, current_user, db)
        raise ErrorDeDominio(
            403,
            "SoD: el solicitante no puede aprobar su propia solicitud "
            "(Segregación de Funciones — crear ≠ aprobar)",
        )

    if step.requires_attachment and decision in ("approved", "rejected") and not attachment_url:
        raise ErrorDeDominio(400, "Este paso requiere adjuntar un documento para emitir la decisión")

    existing_vote = next(
        (d for d in (req.decisions or [])
         if d.step_order == req.current_step and d.approver_id == current_user.id
         # Auditoria 2026-11: la fila «delegated» del escalado por caducidad
         # registra a quien se pasa el paso; no es un voto suyo.
         and d.decision != "delegated"),
        None
    )
    if existing_vote:
        raise ErrorDeDominio(400, "Ya has emitido tu voto en este paso")

def _record_decision_row(
    req, decision: str, note: Optional[str], delegate_to: Optional[str],
    attachment_url: Optional[str], current_user: User, db: Session
) -> None:
    """Persist the ApprovalDecision row and the audit log entry."""
    db.add(ApprovalDecision(
        id=str(uuid.uuid4()),
        request_id=req.id,
        step_order=req.current_step,
        approver_id=current_user.id,
        decision=decision,
        note=note,
        attachment_url=attachment_url,
        delegate_to=delegate_to if decision == "delegated" else None,
    ))
    db.flush()
    log_financial_approval_event(
        db=db,
        request_id=req.id,
        entity_type=req.entity_type,
        entity_id=req.entity_id,
        action=decision,
        decision=decision,
        actor_user_id=current_user.id,
        step_order=req.current_step,
        note=note,
        metadata_=f"delegate_to={delegate_to}" if decision == "delegated" else None,
    )
    db.refresh(req)

def _apply_rejected_decision(req, note: Optional[str], current_user: User, db: Session) -> None:
    req.status = "rejected"
    req.final_decision = "rejected"
    req.final_note = note
    req.completed_at = datetime.now(timezone.utc)
    _apply_entity_final_decision(req, "rejected", current_user, db)

def _apply_delegated_decision(
    req, steps, note: Optional[str], delegate_to: Optional[str], db: Session
) -> None:
    if not delegate_to:
        raise ErrorDeDominio(400, "Debes indicar delegate_to para delegar la aprobación")
    req.final_note = f"Delegado a {delegate_to} ({note or 'sin nota'})"
    db.commit()
    notify_approver(
        req,
        next((s for s in steps if s.step_order == req.current_step), None),
        db,
        explicit_user_id=delegate_to,
    )

def _quorum_satisfied(req, step) -> bool:
    """Return True if the parallel-quorum requirement of `step` is met by current votes."""
    if not step.parallel_quorum:
        return True
    step_approvals = [
        d for d in (req.decisions or [])
        if d.step_order == req.current_step and d.decision == "approved"
    ]
    required = step.required_approvals or 1
    return len(step_approvals) >= required

def _apply_approved_decision(
    req, wf, steps, step, current_user: User, db: Session
) -> bool:
    """Apply an approved decision. Returns True if the workflow stayed on the current
    step (waiting for more quorum votes) and the caller should return early."""
    if not _quorum_satisfied(req, step):
        db.commit()
        db.refresh(req)
        return True

    next_steps = [
        s for s in steps
        if s.step_order > req.current_step
        and not s.is_optional
        and _step_condition_met(s, req)
    ]
    if next_steps:
        req.current_step = next_steps[0].step_order
        req.step_started_at = datetime.now(timezone.utc)
        req.last_reminder_at = None
        db.commit()
        notify_approver(req, next_steps[0], db)
    else:
        req.status = "approved"
        req.final_decision = "approved"
        req.completed_at = datetime.now(timezone.utc)
        db.commit()
        _notify_requester_approved(req, db)
        _apply_entity_final_decision(req, "approved", current_user, db)
        if wf.chain_on_approval_workflow_id:
            _trigger_chained_workflow(req, wf.chain_on_approval_workflow_id, current_user, db)
    return False

def _emit_decision_event(req, decision: str, note: Optional[str], current_user: User, db: Session) -> None:
    from app.core.events import emit, EventType
    event_type = (
        EventType.APPROVAL_APPROVED if req.final_decision == "approved"
        else EventType.APPROVAL_REJECTED if req.final_decision == "rejected"
        else EventType.APPROVAL_REQUESTED
    )
    emit(db, event_type,
         {"entity_type": req.entity_type, "entity_id": req.entity_id,
          "summary": req.entity_summary, "decision": decision, "note": note},
         resource_type="approval_request", resource_id=req.id,
         actor=current_user)

def decide_approval_request(
    request_id: str,
    decision: str,
    note: Optional[str],
    delegate_to: Optional[str],
    db: Session,
    current_user: User,
    attachment_url: Optional[str] = None,
):
    """
    Apply an approval decision (approved | rejected | delegated).
    Returns the updated ApprovalRequest ORM object.
    Raises HTTPException on validation failures.
    """
    req, wf, steps, step = _load_request_and_workflow_for_decision(request_id, db, current_user)
    _validate_decision_authorization(req, step, decision, attachment_url, current_user, db)
    from app.services.approval_engine import fuentes
    fuentes.comprobar_antes(req, decision, db)
    _record_decision_row(req, decision, note, delegate_to, attachment_url, current_user, db)

    if decision == "rejected":
        _apply_rejected_decision(req, note, current_user, db)
    elif decision == "delegated":
        _apply_delegated_decision(req, steps, note, delegate_to, db)
    elif decision == "approved":
        early_return = _apply_approved_decision(req, wf, steps, step, current_user, db)
        if early_return:
            return req

    db.commit()
    db.refresh(req)
    _emit_decision_event(req, decision, note, current_user, db)
    return req

def get_pending_for_user(db: Session, current_user: User) -> list:
    """Return all pending ApprovalRequests where the current user is the step approver."""

    pending_q = db.query(ApprovalRequest).filter(
        ApprovalRequest.status == "pending"
    ).options(
        joinedload(ApprovalRequest.requester),
        joinedload(ApprovalRequest.decisions),
    )
    pending = scope_request_query(pending_q, db, current_user).all()
    if not pending:
        return []

    wf_ids = list({req.workflow_id for req in pending if req.workflow_id})
    workflows = {
        wf.id: wf
        for wf in db.query(ApprovalWorkflow).options(
            joinedload(ApprovalWorkflow.steps)
        ).filter(ApprovalWorkflow.id.in_(wf_ids)).all()
    }

    result = []
    for req in pending:
        wf = workflows.get(req.workflow_id)
        if not wf:
            continue
        step = next((s for s in wf.steps if s.step_order == req.current_step), None)
        if not step:
            continue
        if _is_authorized(step, current_user, req.requested_by, db, req=req):
            result.append((req, step))

    return result

def list_approval_requests(
    db: Session,
    current_user: User,
    status: Optional[str] = None,
    entity_type: Optional[str] = None,
    mine: bool = True,
):
    q = db.query(ApprovalRequest).options(
        joinedload(ApprovalRequest.requester),
        joinedload(ApprovalRequest.decisions),
    )
    q = scope_request_query(q, db, current_user)
    if status:
        q = q.filter(ApprovalRequest.status == status)
    if entity_type:
        q = q.filter(ApprovalRequest.entity_type == entity_type)
    if mine:
        q = q.filter(ApprovalRequest.requested_by == current_user.id)
    return q.order_by(ApprovalRequest.created_at.desc()).limit(100).all()

def cancel_approval_request(db: Session, request_id: str, current_user: User):
    req = scope_request_query(
        db.query(ApprovalRequest), db, current_user
    ).filter(ApprovalRequest.id == request_id).first()
    if not req:
        raise ErrorDeDominio(404)
    if req.requested_by != current_user.id and current_user.role not in ("admin", "pm"):
        raise ErrorDeDominio(403)
    req.status = "cancelled"
    req.completed_at = datetime.now(timezone.utc)
    log_financial_approval_event(
        db=db,
        request_id=req.id,
        entity_type=req.entity_type,
        entity_id=req.entity_id,
        action="cancelled",
        actor_user_id=current_user.id,
        step_order=req.current_step,
    )
    db.commit()
    from app.core.events import emit, EventType
    emit(db, EventType.APPROVAL_REJECTED,
         {"entity_type": req.entity_type, "entity_id": req.entity_id,
          "summary": req.entity_summary, "action": "cancelled"},
         resource_type="approval_request", resource_id=req.id,
         actor=current_user)
    return req

# ── Condiciones de aprobacion ────────────────────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 18). `_check_auto_approval` era complejidad 18 y
# decide si una solicitud se aprueba SIN REVISION HUMANA. No tenia un solo test.
#
# Las MISMAS cuatro condiciones estaban escritas dos veces —aqui y en
# `_step_condition_met`— con manejo de error OPUESTO, y esa asimetria es
# correcta y deliberada. Las dos fallan hacia «hace falta aprobacion humana»:
#
#   · en la auto-aprobacion, un importe que no se puede leer hace que la regla
#     NO aplique, asi que no se auto-aprueba;
#   · en la condicion de un paso, un importe que no se puede leer deja el paso
#     ACTIVO, asi que se exige la aprobacion de ese paso.
#
# Ahora la tabla es una y el sentido del fallo es un parametro con nombre
# (`si_no_se_puede_evaluar`), para que la asimetria se vea en la llamada en vez
# de estar escondida en dos copias.

# Comparaciones de importe: `amount_lt` exige que el importe sea MENOR que el
# umbral, `amount_gt` que sea MAYOR. Estrictas las dos: un importe igual al
# umbral no cumple ninguna.
_COMPARACIONES_DE_IMPORTE = {
    "amount_lt": operator.lt,
    "amount_gt": operator.gt,
}

# Condiciones de igualdad exacta sobre el contexto.
_IGUALDADES = ("department", "category")


def _condiciones_cumplidas(
    conds: dict, ctx: dict, *, si_no_se_puede_evaluar: bool, donde: str
) -> bool:
    """Evalua las condiciones presentes en `conds` contra el contexto `ctx`.

    Solo se evaluan las claves que estan en `conds`: una condicion ausente no
    restringe nada. `si_no_se_puede_evaluar` dice que significa un importe
    ilegible —ver la nota de cabecera—, y se evaluan TODAS las condiciones
    aunque una ya haya fallado, para que el registro de diagnostico sea el mismo
    que antes.
    """
    cumple = True
    for clave, comparar in _COMPARACIONES_DE_IMPORTE.items():
        if clave not in conds:
            continue
        try:
            if not comparar(float(ctx.get("amount", 0)), float(conds[clave])):
                cumple = False
        except Exception:
            logger.debug(
                "%s: no se pudo evaluar %s con ctx=%r", donde, clave, ctx, exc_info=True
            )
            if not si_no_se_puede_evaluar:
                cumple = False
    for clave in _IGUALDADES:
        if clave in conds and ctx.get(clave) != conds[clave]:
            cumple = False
    return cumple


def _check_auto_approval(wf, payload) -> Optional[str]:
    """Return rule label if auto-approval applies, else None.

    Decide si se salta la revision humana, asi que todo lo dudoso cuenta como
    «no aplica»: sin reglas, con reglas ilegibles o con una regla SIN
    condiciones, se devuelve None y la solicitud sigue el flujo normal. Lo
    ultimo importa: una regla vacia auto-aprobaria todo, y aqui no aprueba nada.
    """
    if not wf.auto_approval_rules:
        return None
    # Audit #61: validate via Pydantic with BC fallback. Historic rows that
    # don't match the schema are returned as raw dicts so the engine keeps
    # working while the data is migrated.
    from app.schemas.approvals import parse_auto_approval_rules
    rules = parse_auto_approval_rules(wf.auto_approval_rules)
    if not rules:
        return None

    # `payload.context` es un campo declarado del esquema, asi que el
    # `hasattr` que habia aqui siempre era verdadero: octava instancia del
    # patron de acceso tolerante que la auditoria viene retirando. El
    # `isinstance` es el control que de verdad hace falta — un contexto que no
    # sea un diccionario se trata como vacio.
    ctx = payload.context if isinstance(payload.context, dict) else {}

    for rule in rules:
        if rule.get("action") != "auto_approve":
            continue
        conds = rule.get("conditions", {})
        if not conds:
            continue
        if _condiciones_cumplidas(
            conds, ctx, si_no_se_puede_evaluar=False, donde="auto_approve"
        ):
            return rule.get("label", "auto-rule")
    return None


def _first_active_step(steps, req):
    """Return first step whose condition is met (or first step if no conditions)."""
    ordered = sorted(steps, key=lambda s: s.step_order)
    for s in ordered:
        if not s.is_optional and _step_condition_met(s, req):
            return s
    return ordered[0] if ordered else None

def _step_condition_met(step, req) -> bool:
    """Evaluate step.step_condition JSON against the request context.

    Todo lo dudoso cuenta como «el paso esta activo», que es el sentido seguro:
    un paso activo exige aprobacion. Sin condicion, con condicion ilegible o con
    un importe que no se puede leer, se devuelve True.

    Es el sentido OPUESTO al de la auto-aprobacion, y es correcto: alli lo
    dudoso significa «no auto-aprobar». Las dos fallan hacia pedir una firma
    humana. Ver la nota de `_condiciones_cumplidas`.
    """
    if not step.step_condition:
        return True
    try:
        cond = json.loads(step.step_condition)
    except Exception:
        logger.warning(
            "Failed to parse approval step_condition for step=%s",
            getattr(step, "id", None), exc_info=True,
        )
        return True
    ctx = {}
    try:
        ctx = json.loads(req.entity_summary or "{}")
    except Exception:
        logger.debug(
            "Approval request entity_summary not JSON for req=%s",
            getattr(req, "id", None), exc_info=True,
        )
    return _condiciones_cumplidas(
        cond, ctx,
        si_no_se_puede_evaluar=True,
        donde=f"step_condition step={getattr(step, 'id', None)}",
    )


def _trigger_chained_workflow(req, chain_wf_id: str, actor, db: Session) -> None:
    """Create a new approval request for the chained workflow."""
    try:
        chain_wf = db.query(ApprovalWorkflow).filter(ApprovalWorkflow.id == chain_wf_id).first()
        if not chain_wf or not chain_wf.is_active:
            return
        chained = ApprovalRequest(
            id=str(uuid.uuid4()),
            workflow_id=chain_wf_id,
            entity_type=req.entity_type,
            entity_id=req.entity_id,
            entity_summary=f"[Encadenado de {req.id[:8]}] {req.entity_summary or ''}",
            requested_by=req.requested_by,
            current_step=1,
            status="pending",
            step_started_at=datetime.now(timezone.utc),
        )
        db.add(chained)
        db.commit()
        first = _first_active_step(chain_wf.steps or [], chained)
        if first:
            notify_approver(chained, first, db)
    except Exception:
        logger.warning("_trigger_chained_workflow failed", exc_info=True)
