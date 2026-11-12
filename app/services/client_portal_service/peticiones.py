"""Peticiones de funcionalidad del cliente y las peticiones de cambio que generan.

Parte de `app.services.client_portal_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from app.models.billing_reports import ApprovalRequest
from app.models.client_portal import ClientUser
from app.models.client_portal import FeatureRequest, FeatureRequestStatus
from app.models.project import Project as ProjectModel
from app.models.resources import ChangeRequest, ChangeRequestStatus
from app.models.resources import ChangeRequestImpact
from app.services.approval_workflows import find_default_workflow
from app.services.notifications import publish_user_notification
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from app.core.background import spawn

from app.services.client_portal_service.serializacion import fr_out
from app.services.client_portal_service.autenticacion import logger


# ── Feature Requests ──────────────────────────────────────────────────────────

def list_feature_requests(status: Optional[str], current_client, db: Session) -> list:

    accessible = current_client.get_project_ids()
    q = db.query(FeatureRequest).filter(
        FeatureRequest.project_id.in_(accessible) if len(accessible) > 1
        else FeatureRequest.project_id == accessible[0] if accessible
        else FeatureRequest.project_id == None
    )
    if status:
        q = q.filter(FeatureRequest.status == status)
    frs = q.order_by(FeatureRequest.submitted_at.desc()).all()
    result = []
    for f in frs:
        item = fr_out(f)
        # Auditoria 2026-11: `str()` de un enum de texto da «FeatureRequestStatus.new»
        # en Python 3.12: nunca coincidia y el cliente no podia editar ni retirar.
        item["can_edit_by_client"] = f.client_id == current_client.id and getattr(f.status, "value", f.status) in {
            FeatureRequestStatus.new.value, FeatureRequestStatus.reviewing.value,
        }
        result.append(item)
    return result


def list_all_feature_requests(
    project_id: Optional[str], client_id: Optional[str],
    client_org_id: Optional[str], status: Optional[str],
    current_user, db: Session
) -> list:

    q = db.query(FeatureRequest).options(
        joinedload(FeatureRequest.client), joinedload(FeatureRequest.project)
    )
    if getattr(current_user, "organization_id", None) and not getattr(current_user, "is_superadmin", False):
        q = q.filter(FeatureRequest.project.has(ProjectModel.organization_id == current_user.organization_id))
    if project_id:
        q = q.filter(FeatureRequest.project_id == project_id)
    if client_id:
        q = q.filter(FeatureRequest.client_id == client_id)
    if client_org_id:
        q = q.filter(FeatureRequest.client.has(ClientUser.client_org_id == client_org_id))
    if status:
        q = q.filter(FeatureRequest.status == status)
    frs = q.order_by(FeatureRequest.submitted_at.desc()).all()
    crs = _peticiones_de_cambio(db, frs)
    result = []
    for f in frs:
        d = fr_out(f)
        d["project_name"] = f.project.name if f.project else "—"
        d["client_name"] = f.client.full_name if f.client else "—"
        d.update(_detalle_de_cr(crs.get(getattr(f, "change_request_id", None))))
        result.append(d)
    return result


_CR_IMPACT_LABELS = {"low": "Bajo", "medium": "Medio", "high": "Alto", "critical": "Crítico"}


def _peticiones_de_cambio(db: Session, frs) -> dict:
    """Las CR enlazadas a `frs`, en una consulta, por id."""
    ids = {f.change_request_id for f in frs if getattr(f, "change_request_id", None)}
    if not ids:
        return {}
    return {cr.id: cr for cr in db.query(ChangeRequest).filter(ChangeRequest.id.in_(ids)).all()}


def _detalle_de_cr(cr) -> dict:
    """Lo que el modal de detalle de CR del equipo lee de la peticion.

    Auditoria 2026-11: el modal pintaba impacto, coste, plazo, notas y fechas de
    la CR y `fr_out` no los mandaba, asi que salian siempre como «—». Solo va en
    el listado del equipo: las notas de resolucion son internas y `fr_out` lo
    usa tambien el portal del cliente.
    """
    if cr is None:
        return {}
    impacto = getattr(cr.impact, "value", cr.impact)
    return {
        "impact": impacto,
        "impact_label": _CR_IMPACT_LABELS.get(impacto, impacto),
        "cost_impact": cr.cost_impact,
        "schedule_impact_days": cr.schedule_impact_days,
        "resolution_notes": cr.resolution_notes,
        "approved_at": str(cr.approved_at) if cr.approved_at else None,
        "implemented_at": str(cr.implemented_at) if cr.implemented_at else None,
    }


def create_feature_request(payload, current_client, db: Session) -> dict:
    import re as _re

    if not current_client.can_request_changes:
        raise ValueError("No tienes permisos para solicitar cambios")
    accessible = current_client.get_project_ids()
    target_project_id = getattr(payload, "project_id", None) or (accessible[0] if accessible else None)
    if not target_project_id:
        raise ValueError("No tienes un proyecto asignado para enviar solicitudes")
    if accessible and target_project_id not in accessible:
        raise ValueError("No tienes acceso a ese proyecto")
    max_fr = db.query(func.max(FeatureRequest.code)).filter(
        FeatureRequest.project_id == target_project_id
    ).scalar()
    if max_fr:
        _m = _re.search(r"(\d+)$", max_fr)
        next_fr_num = (int(_m.group(1)) + 1) if _m else 1
    else:
        next_fr_num = 1
    fr_data = payload.model_dump()
    fr_data.pop("project_id", None)
    fr = FeatureRequest(
        code=f"FR-{next_fr_num:03d}",
        project_id=target_project_id,
        client_id=current_client.id,
        **fr_data,
    )
    db.add(fr)
    db.commit()
    db.refresh(fr)
    return fr_out(fr)


def update_feature_request(fr_id: str, payload, current_client, db: Session) -> dict:

    accessible = current_client.get_project_ids()
    fr = db.query(FeatureRequest).filter(
        FeatureRequest.id == fr_id,
        FeatureRequest.client_id == current_client.id,
        FeatureRequest.project_id.in_(accessible) if accessible else FeatureRequest.project_id == None,
    ).first()
    if not fr:
        raise ValueError("FR no encontrada")
    if getattr(fr.status, "value", fr.status) not in {FeatureRequestStatus.new.value, FeatureRequestStatus.reviewing.value}:
        raise ValueError("Solo puedes editar solicitudes nuevas o en revisión")
    data = payload.model_dump(exclude_unset=True)
    target_project_id = data.pop("project_id", None)
    if target_project_id is not None:
        if accessible and target_project_id not in accessible:
            raise ValueError("No tienes acceso a ese proyecto")
        fr.project_id = target_project_id
    for key, value in data.items():
        setattr(fr, key, value)
    db.commit()
    db.refresh(fr)
    item = fr_out(fr)
    item["can_edit_by_client"] = True
    return item


def withdraw_feature_request(fr_id: str, reason: Optional[str], current_client, db: Session) -> dict:

    accessible = current_client.get_project_ids()
    fr = db.query(FeatureRequest).filter(
        FeatureRequest.id == fr_id,
        FeatureRequest.client_id == current_client.id,
        FeatureRequest.project_id.in_(accessible) if accessible else FeatureRequest.project_id == None,
    ).first()
    if not fr:
        raise ValueError("FR no encontrada")
    if getattr(fr.status, "value", fr.status) not in {FeatureRequestStatus.new.value, FeatureRequestStatus.reviewing.value}:
        raise ValueError("Solo puedes retirar solicitudes nuevas o en revisión")
    fr.status = FeatureRequestStatus.rejected
    fr.client_approved = False
    fr.client_rejection_reason = reason or "Retirada por el cliente desde el portal"
    fr.client_approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(fr)
    return fr_out(fr)


#: Estado de la solicitud → estado de la petición de cambio enlazada.
#: Auditoría 2026-09 (hallazgo 18): eran tres `elif` seguidos. Los estados que
#: no están aquí **no tocan** la petición de cambio, y eso es deliberado: una
#: solicitud en revisión no cambia nada aguas abajo.
_ESTADO_DE_CR_SEGUN_FR = {
    FeatureRequestStatus.in_development: ChangeRequestStatus.approved,
    FeatureRequestStatus.done: ChangeRequestStatus.implemented,
    FeatureRequestStatus.rejected: ChangeRequestStatus.rejected,
}


def _acotar_fr_a_la_organizacion(fr, current_user, db: Session) -> None:
    """Comprueba que la solicitud es de un proyecto de quien pregunta.

    Se responde «no encontrada» y no «prohibido»: un 403 confirmaría que esa
    solicitud existe en otra organización.
    """
    if not getattr(current_user, "organization_id", None):
        return
    if getattr(current_user, "is_superadmin", False):
        return
    proyecto = db.query(ProjectModel).filter(ProjectModel.id == fr.project_id).first()
    if not proyecto or proyecto.organization_id != current_user.organization_id:
        raise ValueError("FR no encontrada")


def _avisar_del_cambio_de_estado(fr, cr) -> None:
    """Notifica al cliente por WebSocket. Un fallo aquí no tumba la respuesta."""
    try:
        # `spawn` conserva la referencia (auditoría 2026-08, P2-15): sin ella el
        # recolector podía descartar la notificación antes de enviarse.
        spawn(publish_user_notification(str(fr.client_id), {
            "type": "cr_state_changed",
            "feature_request_id": fr.id,
            "change_request_id": getattr(fr, "change_request_id", None),
            "fr_status": fr.status,
            "cr_status": cr.status if cr else None,
            "title": fr.title,
            "ts": datetime.now(timezone.utc).isoformat(),
        }), name="portal-notif")
    except Exception as e:
        logger.warning(f"No se pudo enviar notificación WS: {e}")


def respond_to_fr(fr_id: str, payload, current_user, db: Session) -> dict:
    """Responde a una solicitud de funcionalidad del portal de cliente."""
    fr = db.query(FeatureRequest).filter(FeatureRequest.id == fr_id).first()
    if not fr:
        raise ValueError("FR no encontrada")
    _acotar_fr_a_la_organizacion(fr, current_user, db)

    # Presupuestar sin explicar el presupuesto deja al cliente con una cifra y
    # ningún motivo.
    if payload.status == "estimated" and not payload.pm_response:
        raise ValueError("pm_response es obligatorio para presupuestar una solicitud")

    for clave, valor in payload.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(fr, clave, valor)

    cr = None
    if fr.change_request_id:
        cr = db.query(ChangeRequest).filter(ChangeRequest.id == fr.change_request_id).first()
        if cr and fr.status in _ESTADO_DE_CR_SEGUN_FR:
            cr.status = _ESTADO_DE_CR_SEGUN_FR[fr.status]

    db.commit()
    db.refresh(fr)
    _avisar_del_cambio_de_estado(fr, cr)
    return fr_out(fr)


def _next_cr_code(project_id: str, db: Session) -> str:
    import re as _re
    max_cr = db.query(func.max(ChangeRequest.code)).filter(
        ChangeRequest.project_id == project_id
    ).scalar()
    if max_cr:
        _m = _re.search(r"(\d+)$", max_cr)
        next_num = (int(_m.group(1)) + 1) if _m else 1
    else:
        next_num = 1
    return f"CR-{next_num:03d}"


def _create_cr_from_fr(fr, db: Session):
    """Create a ChangeRequest mirroring a FeatureRequest and the matching approval request."""
    import uuid

    cr = ChangeRequest(
        id=str(uuid.uuid4()),
        code=_next_cr_code(fr.project_id, db),
        project_id=fr.project_id,
        title=fr.title,
        description=fr.description,
        justification=fr.business_justification,
        impact=ChangeRequestImpact[fr.priority] if fr.priority else ChangeRequestImpact.medium,
        cost_impact=fr.estimated_cost,
        schedule_impact_days=fr.estimated_delivery_weeks * 7 if fr.estimated_delivery_weeks else None,
        scope_impact=fr.affected_area,
        status=ChangeRequestStatus.submitted,
        submitted_at=datetime.now(timezone.utc),
    )
    db.add(cr)
    db.flush()
    fr.change_request_id = cr.id
    wf = find_default_workflow("change_request", db)
    if wf:
        db.add(ApprovalRequest(
            id=str(uuid.uuid4()),
            workflow_id=wf.id,
            entity_type="change_request",
            entity_id=cr.id,
            entity_summary=cr.title,
            requested_by=None,
            current_step=1,
            status="pending",
        ))
    return cr


def _apply_client_fr_approval(fr, db: Session) -> None:
    """Handle FR approval path: ensure CR exists and mark it approved."""
    fr.status = FeatureRequestStatus.approved
    if not fr.change_request_id:
        cr = _create_cr_from_fr(fr, db)
    else:
        cr = db.query(ChangeRequest).filter(ChangeRequest.id == fr.change_request_id).first()
    if cr:
        cr.status = ChangeRequestStatus.approved
        db.commit()


def _apply_client_fr_rejection(fr, db: Session) -> None:
    """Handle FR rejection path: mark FR rejected and linked CR if any."""
    fr.status = FeatureRequestStatus.rejected
    if fr.change_request_id:
        cr = db.query(ChangeRequest).filter(ChangeRequest.id == fr.change_request_id).first()
        if cr:
            cr.status = ChangeRequestStatus.rejected
            db.commit()


def client_decide_fr(fr_id: str, payload, current_client, db: Session) -> dict:
    accessible = current_client.get_project_ids()
    fr = db.query(FeatureRequest).filter(
        FeatureRequest.id == fr_id,
        FeatureRequest.project_id.in_(accessible) if accessible else FeatureRequest.project_id == None
    ).first()
    if not fr:
        raise ValueError("FR no encontrada")
    if fr.status != FeatureRequestStatus.estimated:
        raise ValueError("Solo se pueden aprobar FRs con estimación del equipo")
    fr.client_approved = payload.approved
    fr.client_approved_at = datetime.now(timezone.utc)
    fr.client_rejection_reason = payload.reason
    if payload.approved:
        _apply_client_fr_approval(fr, db)
    else:
        _apply_client_fr_rejection(fr, db)
    db.commit()
    return fr_out(fr)
