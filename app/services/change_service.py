from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.models.resources import ChangeRequest, ChangeRequestStatus
from app.services.numbering import next_numbered_code
import logging
from app.core.codigos_de_error import ErrorConCodigo

logger = logging.getLogger(__name__)


def _next_code(db: Session) -> str:
    return next_numbered_code(db, "change_request", prefix="CR", padding=3)


#: M74 (auditoría 22-11-2026): ciclo de una solicitud de cambio de proyecto
#: (estándar PMBOK de control integrado de cambios): borrador → enviada → en
#: revisión → aprobada/rechazada; solo una aprobada se implanta; rechazada o
#: implantada son finales (rechazada puede volver a borrador para rehacerla).
TRANSICIONES = {
    "draft": {"submitted"},
    "submitted": {"under_review", "approved", "rejected", "draft"},
    "under_review": {"approved", "rejected"},
    "approved": {"implemented"},
    "rejected": {"draft"},
    "implemented": set(),
}


def _pasar(cr: ChangeRequest, nuevo) -> None:
    from app.core.codigos_de_error import error
    actual = getattr(cr.status, "value", cr.status) or "draft"
    destino = getattr(nuevo, "value", nuevo)
    if destino not in TRANSICIONES.get(actual, set()):
        raise error(409, "cambio_transicion_no_valida", desde=actual, hasta=destino)
    cr.status = nuevo


def _hoy():
    """Las columnas de fecha de la CR son `Date` (M74: antes se les daba un `datetime`)."""
    from app.core import timeutil
    return timeutil.today()


def get_all_pending(db: Session) -> list[ChangeRequest]:
    # M74: solo las de la empresa de la sesión (antes sin filtro explícito).
    from app.models.project import Project
    org = (getattr(db, "info", {}) or {}).get("organization_id")
    q = db.query(ChangeRequest)
    if org and not (db.info or {}).get("is_superadmin"):
        q = q.join(Project, Project.id == ChangeRequest.project_id).filter(Project.organization_id == org)
    return (
        q
        .options(
            joinedload(ChangeRequest.requester),
            joinedload(ChangeRequest.project),
        )
        .filter(ChangeRequest.status.in_(["submitted", "under_review"]))
        .filter(ChangeRequest.is_active == True)
        .order_by(ChangeRequest.created_at.desc())
        .all()
    )


def list_by_project(
    db: Session,
    project_id: str,
    status: Optional[str] = None,
) -> list[ChangeRequest]:
    q = (
        db.query(ChangeRequest)
        .options(
            joinedload(ChangeRequest.requester),
            joinedload(ChangeRequest.approver_user),
        )
        .filter(ChangeRequest.project_id == project_id)
        .filter(ChangeRequest.is_active == True)
    )
    if status:
        q = q.filter(ChangeRequest.status == status)
    return q.order_by(ChangeRequest.created_at.desc()).all()


def create_change_request(
    db: Session,
    project_id: str,
    requested_by: str,
    **fields,
) -> ChangeRequest:
    cr = ChangeRequest(
        project_id=project_id,
        code=_next_code(db),
        requested_by=requested_by,
        **fields,
    )
    db.add(cr)
    db.commit()
    db.refresh(cr)
    return cr


def get_by_id(db: Session, cr_id: str, project_id: Optional[str] = None) -> Optional[ChangeRequest]:
    q = db.query(ChangeRequest).filter(ChangeRequest.id == cr_id, ChangeRequest.is_active == True)
    if project_id is not None:
        q = q.filter(ChangeRequest.project_id == project_id)
    return q.first()


def update_change_request(db: Session, cr: ChangeRequest, **fields) -> ChangeRequest:
    # M74: el estado no se cambia por aquí (va por enviar/revisar/implantar).
    nuevo = fields.pop("status", None)
    if nuevo is not None and getattr(nuevo, "value", nuevo) != getattr(cr.status, "value", cr.status):
        _pasar(cr, nuevo)
    for k, v in fields.items():
        setattr(cr, k, v)
    db.commit()
    db.refresh(cr)
    return cr


def submit_change_request(db: Session, cr: ChangeRequest) -> ChangeRequest:
    _pasar(cr, ChangeRequestStatus.submitted)
    cr.submitted_at = _hoy()
    # Auditoria 2026-11: con flujo por defecto, a la bandeja de aprobaciones.
    # M74 (auditoría 22-11-2026): la solicitud de aprobación se abre en la MISMA
    # transacción (antes se confirmaba el envío y, si abrirla fallaba, la CR
    # quedaba «enviada» sin nadie que la aprobara).
    from app.services.approval_engine import fuentes
    solicitante = cr.requested_by or getattr(db.info.get("current_user"), "id", None)
    if solicitante:
        fuentes.abrir(db, "change_request", cr.id, f"{cr.code} — {cr.title}", solicitante,
                      {"cost_impact": cr.cost_impact or 0, "schedule_impact_days": cr.schedule_impact_days or 0,
                       "impact": getattr(cr.impact, "value", cr.impact), "project_id": cr.project_id})
    db.commit()
    return cr


def review_change_request(
    db: Session,
    cr: ChangeRequest,
    approved: bool,
    reviewer_id: str,
    resolution_notes: Optional[str] = None,
) -> ChangeRequest:
    _pasar(cr, ChangeRequestStatus.approved if approved else ChangeRequestStatus.rejected)
    cr.reviewed_by = reviewer_id
    cr.approved_by = reviewer_id if approved else None
    cr.approved_at = _hoy() if approved else None
    cr.resolution_notes = resolution_notes
    from app.services.approval_engine import fuentes
    fuentes.cerrar(db, "change_request", cr.id, "approved" if approved else "rejected",
                   resolution_notes or "Revisado en Cambios")
    if not approved:
        _rechazar_solicitud_del_portal(db, cr, resolution_notes)
    db.commit()
    return cr


def _rechazar_solicitud_del_portal(db: Session, cr: ChangeRequest, nota: Optional[str]) -> None:
    """La CR de una solicitud del portal rechazada por el equipo rechaza la solicitud (22-11-2026).

    La decisión del cliente (`client_approved`) se conserva: son dos decisiones
    distintas, cada una con su actor. La nota va como respuesta del equipo.
    """
    from app.models.client_portal import FeatureRequest, FeatureRequestStatus
    for fr in db.query(FeatureRequest).filter(FeatureRequest.change_request_id == cr.id).all():
        if getattr(fr.status, "value", fr.status) not in ("done", "rejected"):
            fr.status = FeatureRequestStatus.rejected
            if nota:
                fr.pm_response = nota


def implement_change_request(db: Session, cr: ChangeRequest) -> ChangeRequest:
    _pasar(cr, ChangeRequestStatus.implemented)
    cr.implemented_at = _hoy()
    db.commit()
    return cr


def delete_change_request(db: Session, cr: ChangeRequest) -> None:
    if cr.status in [ChangeRequestStatus.approved, ChangeRequestStatus.implemented]:
        raise ErrorConCodigo("cr_no_eliminable")
    cr.is_active = False
    db.commit()
