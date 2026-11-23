import logging
import json
from datetime import datetime, timezone as tz
from typing import Optional

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
from app.core.errores import ErrorDeDominio
from app.core.codigos_de_error import error, desde_valor


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

    from app.models.service_desk import ChangeStatus

    cambio = get_change_by_id(db, current_user, change_id)
    if not cambio:
        raise ErrorDeDominio(404)

    TERMINALES = {
        ChangeStatus.implemented,
        ChangeStatus.closed_success,
        ChangeStatus.closed_failed,
    }
    if cambio.status in TERMINALES:
        raise error(409, "cambio_no_cancelable", estado=cambio.status.value)

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


def _a_utc(valor) -> datetime:
    """Fecha ISO de la API en UTC sin perder su zona.

    Auditoria 2026-11-22 (servicios m-z, 4.3): `.replace(tzinfo=utc)` pisaba
    el desfase de una fecha con zona («10:00+01:00» quedaba 10:00 UTC, una hora
    tarde). Con zona se convierte; sin ella se sigue tomando como UTC. Una
    fecha ilegible es un 422, no un 500.
    """
    if isinstance(valor, datetime):
        fecha = valor
    else:
        try:
            fecha = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
        except ValueError:
            raise error(422, "fecha_no_valida")
    return fecha.replace(tzinfo=tz.utc) if fecha.tzinfo is None else fecha.astimezone(tz.utc)


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
        q = q.filter(ITSMChangeRequest.created_at >= _a_utc(date_from))
    if date_to:
        q = q.filter(ITSMChangeRequest.created_at <= _a_utc(date_to))
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
        raise error(404, "no_encontrado", detail="Change request no encontrado", que="solicitud_de_cambio")
    return serialize_change(change, full=full)


def serialize_change(change: ITSMChangeRequest, full: bool = False) -> dict:
    base = {
        "id": change.id,
        "number": change.number,
        "title": change.title,
        "change_type": change.change_type.value if change.change_type else None,
        "standard_model_id": change.standard_model_id,
        "standard_model_name": getattr(change.standard_model, "name", None),
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
        "auto_risk_label": _score_to_label(change.auto_risk_score, change),
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
                # 19-11-2026: nombre y tipo de cada CI afectado, para que la
                # pantalla (pestaña Impacto, simulación) no enseñe el id.
                "affected_ci_details": _detalles_de_cis(change),
            }
        )
    return base


def _detalles_de_cis(change: ITSMChangeRequest) -> list[dict]:
    """`[{id, name, code, ci_type}]` de los CIs afectados, en su orden; los que ya
    no existen salen con `name` None (la pantalla dice «CI que ya no está»)."""
    ids = [str(x) for x in _lista_json(change.affected_cis)]
    if not ids:
        return []
    from sqlalchemy.orm import object_session
    db = object_session(change)
    encontrados: dict = {}
    if db is not None:
        from app.models.service_desk import ConfigurationItem
        filas = db.query(ConfigurationItem).filter(ConfigurationItem.id.in_(ids)).all()
        encontrados = {ci.id: ci for ci in filas}
    salida = []
    for i in ids:
        ci = encontrados.get(i)
        salida.append({"id": i, "name": getattr(ci, "name", None), "code": getattr(ci, "code", None),
                       "ci_type": getattr(getattr(ci, "ci_type", None), "value", getattr(ci, "ci_type", None))})
    return salida


def _lista_json(raw) -> list:
    try:
        valor = json.loads(raw or "[]")
    except (ValueError, TypeError):
        return []
    return valor if isinstance(valor, list) else []


def _score_to_label(score, change=None) -> str | None:
    # 19-11-2026: los cortes de RISK_LEVEL_* de la empresa (antes 75/55/30 aquí
    # frente a 75/50/25 del ajuste).
    if score is None:
        return None
    from sqlalchemy.orm import object_session
    from app.core.umbrales import nivel_de_riesgo
    return nivel_de_riesgo(score, object_session(change) if change is not None else None, registro=change)


def _load_window(suggested_window_json: str | None) -> dict | None:
    if not suggested_window_json:
        return None
    try:
        import json
        return json.loads(suggested_window_json)
    except Exception:
        logging.getLogger(__name__).debug("_load_window: excepcion ignorada", exc_info=True)
        return None


def next_change_number(db: Session) -> str:
    return next_numbered_code(db, "itsm_change", prefix="CHG", padding=5, separator="")


def build_change_request(payload: dict, requester_id: str, number: str) -> ITSMChangeRequest:
    if not payload.get("title") or not payload.get("description"):
        raise error(422, "campos_obligatorios", detail="title y description son obligatorios", campos="title, description")

    change = ITSMChangeRequest(
        number=number,
        title=payload["title"],
        description=payload["description"],
        # El tipo lo fija el servidor (A-SD19): `standard` solo con un modelo
        # del catalogo que encaje (`cambios_estandar_service.aplicar_tipo_pedido`).
        change_type="normal",
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
        change.planned_start = _a_utc(payload["planned_start"])
    if payload.get("planned_end"):
        change.planned_end = _a_utc(payload["planned_end"])
    return change


def apply_change_update(change: ITSMChangeRequest, payload: dict, current_user_id: str) -> None:
    for field in (
        "title",
        "description",
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
            setattr(change, dt_field, _a_utc(payload[dt_field]))


# Estados a los que no se llega con un PATCH: los decide el CAB.
_SOLO_POR_EL_CAB = {"approved"}
#: El tipo (y el modelo estandar) solo se cambia antes de la revision.
_TIPO_EDITABLE_EN = {ChangeStatus.draft.value, ChangeStatus.submitted.value}
#: Cierres que cuentan para la tasa de fallo del modelo estandar.
_CIERRES = {ChangeStatus.closed_success.value: True, ChangeStatus.closed_failed.value: False}
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
        raise error(409, "cab_no_configurado", detail="No hay comité de cambios configurado (Service Desk → ajustes, SD_CAB_GROUP_ID): un cambio normal o de emergencia necesita su aprobación") from exc


def exigir_transicion_de_cambio(actual, nuevo: str) -> None:
    """409 si la maquina de estados no admite `actual → nuevo`.

    Auditoria 2026-11-22 (C-SD3): solo se impedia `approved`; cualquier otro
    salto valia (`draft → in_progress → closed_success`), asi que el CAB se
    evitaba con dos PATCH. La tabla es `TRANSICIONES_DE_CAMBIO`.
    """
    from app.models.service_desk._enums import TRANSICIONES_DE_CAMBIO
    actual = getattr(actual, "value", actual)
    if nuevo not in TRANSICIONES_DE_CAMBIO:
        raise error(422, "estado_no_valido", estado=nuevo)
    if nuevo not in TRANSICIONES_DE_CAMBIO.get(actual, frozenset()):
        raise error(409, "cambio_transicion_no_permitida", desde=actual, hasta=nuevo)


def _aplicar_estado(db: Session, change: ITSMChangeRequest, nuevo: str, current_user: User) -> None:
    """Las transiciones con reglas: aprobar es del CAB y programar mira el calendario.

    Auditoria 2026-11: cualquiera con acceso al cambio lo ponia en `approved`
    con un PATCH, sin pasar por el comite. 2026-11-22: ademas, cualquier otro
    salto pasa por `exigir_transicion_de_cambio`.
    """
    from app.services.service_desk.change_calendar_service import exigir_ventana_libre

    if nuevo in _SOLO_POR_EL_CAB:
        raise error(409, "cambio_aprobar_por_cab")
    exigir_transicion_de_cambio(change.status, nuevo)
    if nuevo in _A_REVISION:
        _pasar_a_revision(db, change, current_user)
        return
    if nuevo == "scheduled":
        estado = getattr(change.status, "value", change.status)
        if estado != "approved":
            raise error(409, "cambio_solo_aprobado_programable")
        exigir_ventana_libre(db, change)
    change.status = nuevo
    if nuevo in _CIERRES:
        from app.services.service_desk.cambios_estandar_service import anotar_cierre
        anotar_cierre(db, change, _CIERRES[nuevo], current_user)


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
        logging.getLogger(__name__).debug("_maybe_auto_approve: excepcion ignorada", exc_info=True)
        change_type_val = ""

    if change_type_val != "standard":
        return False
    # A-SD19: solo con un modelo aprobado, vigente y que cubra el cambio; si no,
    # el servidor lo pasa a `normal` y va al CAB.
    from app.services.service_desk import cambios_estandar_service as _ce
    if not _ce.puede_aprobarse_como_estandar(db, change):
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
    _ce.anotar_uso(change)
    return True


def create_change_record(db: Session, current_user: User, payload: dict) -> ITSMChangeRequest:
    number = next_change_number(db)
    change = build_change_request(payload, current_user.id, number)
    if payload.get("affected_cis") is not None:
        cis = payload["affected_cis"]
        change.affected_cis = json.dumps(list(cis)) if isinstance(cis, (list, tuple)) else cis
    if change.organization_id is None and not current_user.is_superadmin:
        change.organization_id = current_user.organization_id
    from app.services.service_desk.cambios_estandar_service import aplicar_tipo_pedido
    aplicar_tipo_pedido(db, current_user, change, payload)
    enforce_change_org_constraints(db, current_user, change)
    db.add(change)
    db.flush()  # assign id before scoring
    _auto_score_change(db, change)
    _maybe_auto_approve(db, change)
    return change


def update_change_record(db: Session, current_user: User, change_id: str, payload: dict) -> ITSMChangeRequest:
    change = get_change_by_id(db, current_user, change_id)
    if not change:
        raise ErrorDeDominio(404)

    prev_status = change.status.value if hasattr(change.status, "value") else change.status
    # El formulario de edicion manda el tipo siempre: solo cuenta si cambia.
    tipo_actual = getattr(change.change_type, "value", change.change_type)
    cambia_tipo = (payload.get("change_type", tipo_actual) != tipo_actual
                   or payload.get("standard_model_id", change.standard_model_id) != change.standard_model_id)
    if cambia_tipo and prev_status not in _TIPO_EDITABLE_EN:
        raise error(409, "cambio_tipo_no_editable", estado=prev_status)
    apply_change_update(change, payload, current_user.id)
    if cambia_tipo:
        from app.services.service_desk.cambios_estandar_service import aplicar_tipo_pedido
        aplicar_tipo_pedido(db, current_user, change, payload)
    enforce_change_org_constraints(db, current_user, change)
    nuevo = payload.get("status")
    if nuevo and nuevo != prev_status:
        _aplicar_estado(db, change, nuevo, current_user)
    return change


def approve_change_record(db: Session, current_user: User, change_id: str, payload: dict) -> ITSMChangeRequest:
    change = get_change_by_id(db, current_user, change_id)
    if not change:
        raise ErrorDeDominio(404)

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
            raise desde_valor(422, exc) from exc
        if getattr(current_user.role, "value", current_user.role) != "admin" and not current_user.is_superadmin:
            raise error(403, "cab_solo_miembros")
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
            raise error(403, "responsable_fuera_de_empresa", detail="No puedes asignar owner fuera de tu organización")

    if change.related_ticket_id:
        ticket = _scope_ticket_query(db.query(Ticket), db, current_user).filter(Ticket.id == change.related_ticket_id).first()
        if not ticket:
            raise error(403, "ticket_relacionado_fuera_de_empresa", detail="Ticket relacionado fuera de tu organización")

    if change.related_problem_id:
        problem = _scope_problem_query(db.query(Problem), db, current_user).filter(Problem.id == change.related_problem_id).first()
        if not problem:
            raise error(403, "problema_relacionado_fuera_de_empresa", detail="Problema relacionado fuera de tu organización")
