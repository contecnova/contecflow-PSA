"""approval_engine._base — extracted from the former 1827-LOC god-file."""

from __future__ import annotations
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload
from app.models.user import User
from app.models.billing_reports import FinancialApprovalAuditLog
from app.models.billing_reports import ApprovalRequest
from app.models.billing_reports import ApprovalWorkflow
from app.models.billing_reports import ApprovalGroup


logger = logging.getLogger(__name__)

_FINANCIAL_ENTITY_TYPES = {
    "timesheet", "expense", "milestone", "purchase", "invoice",
    "contract", "budget", "leave", "deliverable", "proposal",
    "subcontractor", "scope_change", "hire", "price_change",
}

_WORKFLOW_TEMPLATES = [
    {
        "id": "legal_strict_v1",
        "name": "Legal - Strict Review",
        "description": "Aprobacion legal multi-nivel para documentos sensibles.",
        "entity_type": "document",
        "trigger_conditions": {"category": "legal", "amount_gt": 0},
        "steps": [
            {"step_order": 1, "name": "Legal Lead", "approver_type": "role", "approver_role": "pm", "timeout_hours": 48, "on_timeout": "escalate"},
            {"step_order": 2, "name": "Finance Review", "approver_type": "role", "approver_role": "admin", "timeout_hours": 48, "on_timeout": "escalate"},
        ],
    },
    {
        "id": "engineering_delivery_v1",
        "name": "Engineering Deliverable",
        "description": "Flujo para entregables de ingenieria con validacion tecnica y de negocio.",
        "entity_type": "document",
        "trigger_conditions": {"category": "deliverable"},
        "steps": [
            {"step_order": 1, "name": "Team Lead", "approver_type": "role", "approver_role": "team_lead", "timeout_hours": 36, "on_timeout": "escalate"},
            {"step_order": 2, "name": "Project Manager", "approver_type": "role", "approver_role": "pm", "timeout_hours": 36, "on_timeout": "escalate"},
        ],
    },
    {
        "id": "expense_high_amount_v1",
        "name": "Expense - High Amount",
        "description": "Aprobacion escalonada para gastos altos.",
        "entity_type": "expense",
        "trigger_conditions": {"amount_gt": 1000},
        "steps": [
            {"step_order": 1, "name": "Direct Manager", "approver_type": "manager", "timeout_hours": 24, "on_timeout": "escalate"},
            {"step_order": 2, "name": "Finance", "approver_type": "role", "approver_role": "admin", "timeout_hours": 24, "on_timeout": "escalate"},
        ],
    },
]

def scope_request_query(q, db: Session, current_user: User):
    if current_user.is_superadmin or not current_user.organization_id:
        return q
    org_user_ids = db.query(User.id).filter(
        User.organization_id == current_user.organization_id
    ).scalar_subquery()
    return q.filter(ApprovalRequest.requested_by.in_(org_user_ids))

def log_financial_approval_event(
    db: Session,
    request_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
    actor_user_id: Optional[str],
    step_order: Optional[int] = None,
    decision: Optional[str] = None,
    note: Optional[str] = None,
    metadata_: Optional[str] = None,
) -> None:
    if entity_type not in _FINANCIAL_ENTITY_TYPES:
        return
    db.add(FinancialApprovalAuditLog(
        id=str(uuid.uuid4()),
        request_id=request_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        decision=decision,
        actor_user_id=actor_user_id,
        step_order=step_order,
        note=note,
        metadata_=metadata_,
    ))

def notify_approver(
    request,
    step,
    db: Session,
    explicit_user_id: Optional[str] = None,
) -> None:
    """Avisa a TODOS los que pueden decidir el paso: en la aplicacion y por correo.

    Revision 2026-11: antes solo en la aplicacion, y solo a un usuario concreto
    o al *primero* del rol; con aprobador grupo, departamento o responsable no
    se avisaba a nadie.
    """
    try:
        from app.models.enterprise import Notification, NotificationType
        ids = {explicit_user_id} if explicit_user_id else aprobadores_del_paso(request, step, db)
        # Fuera de la oficina: el aviso tambien va a su delegado.
        for ausente in db.query(User).filter(User.id.in_(ids), User.away_delegate_id.isnot(None)).all():
            if ausente_hoy(ausente):
                ids = ids | {ausente.away_delegate_id}
        titulo = f"Aprobación requerida: {request.entity_type}"
        cuerpo = f"{request.entity_summary or request.entity_id} — Paso {step.step_order}: {step.name}"
        for approver_id in sorted(i for i in ids if i and i != request.requested_by):
            db.add(Notification(
                id=str(uuid.uuid4()), user_id=approver_id, type=NotificationType.approval_requested,
                title=titulo, body=cuerpo, resource="approval_request", resource_id=request.id,
            ))
            _correo_de_aprobacion(db, approver_id, titulo, cuerpo, request)
        if not explicit_user_id:
            _aviso_al_canal(db, request, step)
    except Exception:
        logger.warning("Failed to create approval notification", exc_info=True)


def _aviso_al_canal(db: Session, request, step) -> None:
    """Una vez por paso, al canal de Slack/Teams configurado (si escucha el evento)."""
    try:
        from app.services.integrations import notify_event
        solicitante = db.query(User.full_name).filter(User.id == request.requested_by).first()
        notify_event("approval.required", {
            "id": request.id, "title": request.entity_summary or request.entity_id,
            "entity_type": request.entity_type, "step": f"{step.step_order} · {step.name}",
            "requester": solicitante[0] if solicitante else "—",
        }, db)
    except Exception:
        logger.warning("No se pudo avisar al canal de la aprobacion %s", request.id, exc_info=True)


def aprobadores_del_paso(request, step, db: Session) -> set:
    """Ids de los usuarios activos que pueden decidir el paso."""
    if step is None:
        return set()
    q = db.query(User.id).filter(User.is_active == True)  # noqa: E712
    tipo = step.approver_type or ""
    ids: set = set()
    if tipo == "user" and step.approver_user_id:
        ids.add(step.approver_user_id)
    elif tipo == "role" and step.approver_role:
        ids |= {u for (u,) in q.filter(User.role == step.approver_role).all()}
    elif tipo == "any_in_department" and step.approver_department:
        ids |= {u for (u,) in q.filter(User.department == step.approver_department).all()}
    elif tipo == "manager":
        fila = db.query(User.manager_id).filter(User.id == request.requested_by).first()
        if fila and fila[0]:
            ids.add(fila[0])
    if step.approver_group_id:
        grupo = db.query(ApprovalGroup).filter(ApprovalGroup.id == step.approver_group_id).first()
        try:
            ids |= set(json.loads(grupo.member_ids or "[]")) if grupo else set()
        except ValueError:
            pass
    return ids


def _correo_de_aprobacion(db: Session, user_id: str, titulo: str, cuerpo: str, request) -> None:
    from app.core.config import settings as _cfg
    from app.services.preferencias_de_aviso import quiere
    if not quiere(db, user_id, "approval_requested", "email"):
        return
    from app.services.notification_service import send_email_notification
    fila = db.query(User.email).filter(User.id == user_id).first()
    if not fila or not fila[0]:
        return
    from app.services.approval_engine.por_correo import crear_enlace
    bandeja = f"{_cfg.FRONTEND_URL.rstrip('/')}/approvals?request={request.id}"
    send_email_notification(
        fila[0], titulo,
        f"{cuerpo}\n\nAprobar o rechazar desde aquí (sin entrar): {crear_enlace(db, request, user_id)}"
        f"\n\nO en la bandeja: {bandeja}")

def find_default_workflow(entity_type: str, db: Session, category: Optional[str] = None):
    """Find the best-matching workflow for an entity type.

    For documents, first tries a category-specific workflow (trigger_conditions contains
    the category key), then falls back to the generic document default.
    """
    if entity_type == "document" and category:
        # Look for workflows whose trigger_conditions specify this category
        candidates = db.query(ApprovalWorkflow).filter(
            ApprovalWorkflow.entity_type == "document",
            ApprovalWorkflow.is_active == True,
        ).all()
        for wf in sorted(candidates, key=lambda w: (not w.is_default)):
            try:
                conditions = json.loads(wf.trigger_conditions or "{}")
            # intentional: best-effort fallback, log noise outweighs diagnostic value
            except (ValueError, TypeError):
                conditions = {}
            if conditions.get("category") == category:
                return wf

    return db.query(ApprovalWorkflow).filter(
        ApprovalWorkflow.entity_type == entity_type,
        ApprovalWorkflow.is_default == True,
        ApprovalWorkflow.is_active == True,
    ).first()

def elegir_flujo(db: Session, entity_type: str, context: Optional[dict] = None):
    """El flujo que aplica a una solicitud: el mas especifico cuyas condiciones encajan.

    Revision 2026-11: las condiciones del flujo (`trigger_conditions`, p. ej.
    `{"amount_gt": 1000}`) solo las usaba la simulacion; crear una solicitud
    cogia siempre el flujo por defecto, asi que «facturas de mas de 10.000 €
    van a direccion» no se cumplia. Sin ninguna que encaje, el por defecto.
    """
    context = context or {}
    especificos = []
    for wf in db.query(ApprovalWorkflow).filter(ApprovalWorkflow.entity_type == entity_type,
                                                ApprovalWorkflow.is_active == True).all():  # noqa: E712
        cond = _parse_trigger_conditions(wf.trigger_conditions)
        if cond and _matches_conditions(cond, context):
            especificos.append((len(cond), bool(wf.is_default), wf))
    if especificos:
        especificos.sort(key=lambda x: (-x[0], not x[1]))
        return especificos[0][2]
    return find_default_workflow(entity_type, db, category=context.get("category"))


def _esta_en_el_grupo(step, current_user: User, db: Session) -> bool:
    """Si el usuario pertenece al grupo aprobador del paso.

    El JSON malformado se registra y cuenta como «no pertenece»: un grupo
    corrupto no puede autorizar, y tampoco puede tumbar la aprobación entera.
    """
    if not step.approver_group_id:
        return False
    grupo = db.query(ApprovalGroup).filter(ApprovalGroup.id == step.approver_group_id).first()
    if not grupo:
        return False
    try:
        return current_user.id in json.loads(grupo.member_ids or "[]")
    except Exception:
        logger.warning(
            "Failed to parse approval group member_ids for group=%s", grupo.id, exc_info=True,
        )
        return False


#: Cómo autoriza cada tipo de aprobador. Auditoría 2026-09 (hallazgo 18): eran
#: cinco `if` seguidos. Como tabla se ve la lista cerrada de formas de aprobar,
#: y que **no hay ninguna que dé paso a un administrador por serlo** — eso es
#: deliberado: quien aprueba tiene que estar configurado explícitamente.
_APROBADORES = {
    "user": lambda step, u, requested_by, db: step.approver_user_id == u.id,
    "role": lambda step, u, requested_by, db: u.role == step.approver_role,
    "any_in_department": lambda step, u, requested_by, db: (
        u.department == step.approver_department
    ),
    "manager": lambda step, u, requested_by, db: _es_su_responsable(u, requested_by, db),
}


def _es_su_responsable(current_user: User, requested_by: str, db: Session) -> bool:
    """Si quien aprueba es el responsable directo de quien pidió."""
    solicitante = db.query(User).filter(User.id == requested_by).first()
    return bool(solicitante and solicitante.manager_id == current_user.id)


def _is_authorized(step, current_user: User, requested_by: str, db: Session, req=None) -> bool:
    """Si este usuario puede resolver el paso: directamente o como delegado de un ausente.

    La delegacion por ausencia mira un solo nivel (el ausente se comprueba sin
    sus propios delegados): A en B y B en A no da un bucle.
    """
    if _autorizado_directo(step, current_user, requested_by, db, req):
        return True
    return any(_autorizado_directo(step, ausente, requested_by, db, req)
               for ausente in _ausentes_que_me_delegan(current_user, db))


def _autorizado_directo(step, current_user: User, requested_by: str, db: Session, req=None) -> bool:
    """Si este usuario puede resolver este paso de aprobación.

    La pertenencia al grupo se mira **siempre** que el paso tenga grupo, aunque
    el tipo de aprobador sea otro: un paso puede declarar un grupo y además un
    rol, y estar en el grupo basta.
    """
    if _esta_en_el_grupo(step, current_user, db):
        return True
    # Auditoria 2026-11: la persona de escalado del paso tambien puede
    # resolverlo (antes se le avisaba y la bandeja le negaba la decision).
    if step.escalate_to_user_id and step.escalate_to_user_id == current_user.id:
        return True
    # Revision 2026-11: a quien se delega el paso puede decidirlo (antes se le
    # avisaba y la bandeja le devolvia 403).
    if req is not None and any(
            d.decision == "delegated" and d.step_order == req.current_step
            and getattr(d, "delegate_to", None) == current_user.id for d in (req.decisions or [])):
        return True
    if step.approver_type == "group":
        # Ya se ha comprobado arriba; si no estaba en el grupo, no hay más vías.
        return False

    regla = _APROBADORES.get(step.approver_type or "")
    return bool(regla and regla(step, current_user, requested_by, db))


def ausente_hoy(usuario) -> bool:
    from app.core import timeutil
    hoy = timeutil.today()
    return bool(getattr(usuario, "away_delegate_id", None) and usuario.away_from and usuario.away_until
                and usuario.away_from <= hoy <= usuario.away_until)


def _ausentes_que_me_delegan(current_user, db: Session) -> list:
    """Usuarios ausentes hoy que han dejado sus aprobaciones a `current_user`.

    Se guarda en la sesion: la bandeja lo pregunta una vez por solicitud.
    """
    cache = db.info.setdefault("_ausentes_que_delegan", {})
    if current_user.id not in cache:
        candidatos = db.query(User).filter(User.away_delegate_id == current_user.id,
                                           User.is_active == True).all()  # noqa: E712
        cache[current_user.id] = [u for u in candidatos if ausente_hoy(u)]
    return cache[current_user.id]

def _parse_trigger_conditions(raw: Optional[str]) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        logger.warning("Failed to parse approval trigger conditions JSON", exc_info=True)
        return {}

def _matches_conditions(conditions: dict, context: dict) -> bool:
    if not conditions:
        return True
    category = context.get("category")
    department = context.get("department")
    amount = context.get("amount")

    if conditions.get("category") and category != conditions.get("category"):
        return False
    if conditions.get("department") and department != conditions.get("department"):
        return False
    # Revisión 2026-11: «excede una política de gasto» y «de este proyecto».
    if conditions.get("policy_exceeded") is not None and bool(context.get("policy_exceeded")) != bool(conditions["policy_exceeded"]):
        return False
    if conditions.get("project_id") and context.get("project_id") != conditions.get("project_id"):
        return False
    try:
        if conditions.get("amount_gt") is not None and float(amount or 0) <= float(conditions["amount_gt"]):
            return False
        if conditions.get("amount_gte") is not None and float(amount or 0) < float(conditions["amount_gte"]):
            return False
        if conditions.get("amount_lt") is not None and float(amount or 0) >= float(conditions["amount_lt"]):
            return False
        if conditions.get("amount_lte") is not None and float(amount or 0) > float(conditions["amount_lte"]):
            return False
    except Exception:
        logger.warning("Failed to evaluate amount conditions for approval (amount=%r)", amount, exc_info=True)
        return False
    return True

def serialize_step(s) -> dict:
    return {
        "id": s.id, "step_order": s.step_order, "name": s.name,
        "approver_type": s.approver_type, "approver_role": s.approver_role,
        "approver_user_id": s.approver_user_id,
        "approver_user_name": s.approver.full_name if s.approver else None,
        "approver_group_id": getattr(s, "approver_group_id", None),
        "is_optional": s.is_optional, "timeout_hours": s.timeout_hours,
        "on_timeout": s.on_timeout,
        # v2 enterprise
        "parallel_quorum": getattr(s, "parallel_quorum", False),
        "required_approvals": getattr(s, "required_approvals", 1),
        "step_condition": getattr(s, "step_condition", None),
        "requires_attachment": getattr(s, "requires_attachment", False),
        "reminder_hours": getattr(s, "reminder_hours", None),
    }

def serialize_workflow(w, include_steps: bool = False) -> dict:
    d = {
        "id": w.id, "name": w.name, "description": w.description,
        "entity_type": w.entity_type, "is_active": w.is_active,
        "is_default": w.is_default,
        "trigger_conditions": w.trigger_conditions,
        "step_count": len(w.steps or []),
        "created_at": str(w.created_at)[:10] if w.created_at else None,
        # v2 enterprise
        "chain_on_approval_workflow_id": getattr(w, "chain_on_approval_workflow_id", None),
        "sla_block_on_breach": getattr(w, "sla_block_on_breach", False),
        "auto_approval_rules": getattr(w, "auto_approval_rules", None),
    }
    if include_steps:
        d["steps"] = [serialize_step(s) for s in (w.steps or [])]
    return d

def serialize_approval_request(r) -> dict:
    return {
        "id": r.id, "workflow_id": r.workflow_id,
        "entity_type": r.entity_type, "entity_id": r.entity_id,
        "entity_summary": r.entity_summary,
        "requested_by": r.requested_by,
        "requester_name": r.requester.full_name if r.requester else None,
        "current_step": r.current_step,
        "status": r.status,
        "final_decision": r.final_decision,
        "final_note": r.final_note,
        "completed_at": str(r.completed_at)[:16] if r.completed_at else None,
        "created_at": str(r.created_at)[:16] if r.created_at else None,
        "decisions": [
            {
                "step_order": d.step_order,
                "approver_id": d.approver_id,
                "approver_name": d.approver.full_name if d.approver else None,
                "decision": d.decision,
                "note": d.note,
                "attachment_url": getattr(d, "attachment_url", None),
                "decided_at": str(d.decided_at)[:16] if d.decided_at else None,
            }
            for d in (r.decisions or [])
        ],
        "escalated": getattr(r, "escalated", False),
        "auto_approved": getattr(r, "auto_approved", False),
        "rejected": getattr(r, "rejected", False),
    }

def _load_workflows_by_ids(db: Session, workflow_ids: list) -> dict:
    if not workflow_ids:
        return {}
    return {
        w.id: w
        for w in db.query(ApprovalWorkflow).options(joinedload(ApprovalWorkflow.steps)).filter(
            ApprovalWorkflow.id.in_(workflow_ids)
        ).all()
    }

def exigir_que_no_sea_suyo(db: Session, solicitante_id, usuario: User, modulo: str, entidad_id) -> None:
    """Quien pide no aprueba (segregación de funciones), también fuera de la bandeja.

    Revisión 2026-11. La bandeja de aprobaciones ya lo impedía, pero varias
    rutas aprueban directamente —ausencias, imputaciones, documentos sin flujo,
    peticiones de cambio de proyecto, cambios ITSM de emergencia y la decisión
    de un administrador fuera del CAB— y ninguna comparaba al que aprueba con
    el que pidió: un responsable podía aprobarse su propia ausencia. Lanza 403
    y deja la infracción registrada si hay una regla SoD para ese módulo.
    """
    if not solicitante_id or solicitante_id != usuario.id:
        return
    try:
        from app.services.grc_sod import record_sod_violation
        from app.models.billing_reports import SodRule
        regla = db.query(SodRule).filter(SodRule.module_a == modulo, SodRule.module_b == modulo,
                                         SodRule.action_b == "aprobar", SodRule.is_active == True).first()  # noqa: E712
        if regla:
            record_sod_violation(db=db, rule_id=regla.id, user_id=usuario.id, role=str(usuario.role),
                                 context_type=modulo, context_id=str(entidad_id))
            db.commit()
    except Exception:
        logger.warning("No se pudo registrar la infracción SoD de %s %s", modulo, entidad_id, exc_info=True)
    raise HTTPException(403, "SoD: no puedes aprobar lo que has pedido tú (segregación de funciones)")


def _record_sod_violation(req, current_user: User, db: Session) -> None:
    try:
        from app.services.grc_sod import record_sod_violation
        from app.models.billing_reports import SodRule
        matching = db.query(SodRule).filter(
            SodRule.module_a == req.entity_type,
            SodRule.action_a == "crear",
            SodRule.module_b == req.entity_type,
            SodRule.action_b == "aprobar",
            SodRule.is_active == True,
        ).first()
        if matching:
            record_sod_violation(
                db=db,
                rule_id=matching.id,
                user_id=current_user.id,
                role=str(current_user.role),
                context_type="approval_request",
                context_id=req.id,
            )
            db.flush()
    except Exception:
        logger.warning("Failed to record SoD violation for approval request=%s user=%s", req.id, current_user.id, exc_info=True)

def _notify_requester_approved(req, db: Session) -> None:
    try:
        from app.models.enterprise import Notification, NotificationType
        db.add(Notification(
            id=str(uuid.uuid4()),
            user_id=req.requested_by,
            type=NotificationType.system,
            title="Solicitud aprobada",
            body=f"{req.entity_summary or req.entity_id} ha sido aprobada",
            resource="approval_request",
            resource_id=req.id,
        ))
        db.commit()
    except Exception:
        logger.warning("Failed to notify requester of approved request=%s", req.id, exc_info=True)

def _apply_entity_final_decision(req, final_decision: str, actor, db: Session) -> None:
    """Propagate the final approval decision back to the source entity.

    Currently handles:
      - entity_type == "document": updates Document.approval_status, approved_by, approved_at
      - expense, timesheet, leave: la revision de su pantalla (`fuentes.aplicar`)
    """
    from app.services.approval_engine import fuentes
    if req.entity_type == "mcp_action":    # revisión 2026-11: escritura de un agente externo
        from app.services.mcp_service import aplicar_decision
        aplicar_decision(req.entity_id, final_decision, db)
        return
    if req.entity_type in fuentes.TIPOS:
        fuentes.aplicar(req, final_decision, actor, db)
        return
    if req.entity_type != "document":
        return
    try:
        from app.models.documents import Document, ApprovalStatus
        doc = db.query(Document).filter(Document.id == req.entity_id).first()
        if not doc:
            return
        if final_decision == "approved":
            doc.approval_status = ApprovalStatus.approved
            doc.approved_by = actor.id
            doc.approved_at = datetime.now(timezone.utc)
        elif final_decision == "rejected":
            doc.approval_status = ApprovalStatus.rejected
        db.add(doc)
        db.commit()
    except Exception:
        logger.warning("_apply_entity_final_decision failed for document %s", req.entity_id, exc_info=True)
