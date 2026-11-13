import json
from typing import Optional
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.service_desk import (
    StatusPageComponent,
    StatusPageComponentStatus,
    StatusPageIncident,
)
from app.schemas.service_desk import StatusComponentIn, StatusIncidentIn, StatusIncidentUpdateIn
import logging
from app.core.errores import ErrorDeDominio

logger = logging.getLogger(__name__)


def organizacion_de_la_pagina(db: Session, slug: Optional[str]) -> Optional[str]:
    """La organizacion de una pagina de estado publica, por su slug.

    Auditoria 2026-11: la pagina publica mezclaba los componentes de TODAS las
    organizaciones (es anonima: no hay filtro de tenant). Ahora va por
    organizacion: `?org=<slug>`. Sin slug solo se sirve si hay una sola.
    """
    from app.models.mfa import Organization

    if slug:
        org = db.query(Organization).filter(Organization.slug == slug, Organization.is_active == True).first()  # noqa: E712
        if org is None:
            raise ErrorDeDominio(404, "Página de estado no encontrada")
        return org.id
    ids = [r[0] for r in db.query(Organization.id).limit(2).all()]
    if len(ids) == 1:
        return ids[0]
    raise ErrorDeDominio(422, "Indica la organización: ?org=<slug>")


from app.services.service_desk.pagina_de_estado_publica import idioma_de  # noqa: E402


def build_public_status_page_payload(db: Session, org_id: Optional[str] = None) -> dict:
    q = db.query(StatusPageComponent).filter(StatusPageComponent.is_public == True)  # noqa: E712
    if org_id is not None:
        q = q.filter(StatusPageComponent.organization_id == org_id)
    components = q.order_by(StatusPageComponent.sort_order, StatusPageComponent.name).all()

    status_severity = {
        "operational": 0,
        "degraded_performance": 1,
        "partial_outage": 2,
        "major_outage": 3,
        "maintenance": 4,
    }
    worst = "operational"
    for component in components:
        if status_severity.get(component.status, 0) > status_severity.get(worst, 0):
            worst = component.status

    # N+1 eliminado (auditoría 2026-08 §7): antes se lanzaba una consulta de
    # incidencias POR COMPONENTE. Este endpoint es público y sin autenticar
    # (GET /api/v1/sd/status-page), así que cualquiera podía multiplicar la carga de
    # base de datos por el número de componentes con una sola petición.
    incidents_by_component: dict[str, list] = {}
    if components:
        rows = db.query(StatusPageIncident).filter(
            StatusPageIncident.component_id.in_([c.id for c in components]),
            StatusPageIncident.resolved_at == None,
        ).all()
        for row in rows:
            incidents_by_component.setdefault(row.component_id, []).append(row)

    groups = {}
    for component in components:
        group_name = component.group_name or "General"
        if group_name not in groups:
            groups[group_name] = []

        active_incidents = incidents_by_component.get(component.id, [])

        groups[group_name].append(
            {
                "id": component.id,
                "name": component.name,
                "description": component.description,
                "status": component.status,
                "uptime_30d_pct": component.uptime_30d_pct,
                "active_incidents": [
                    {
                        "id": incident.id,
                        "title": incident.title,
                        "status": incident.status,
                        "impact": incident.impact,
                        "started_at": incident.started_at.isoformat() if incident.started_at else None,
                    }
                    for incident in active_incidents
                ],
            }
        )

    return {
        "overall_status": worst,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "groups": groups,
        "idioma": idioma_de(db, org_id),
    }


def list_status_components(db: Session):
    return db.query(StatusPageComponent).order_by(
        StatusPageComponent.sort_order,
        StatusPageComponent.name,
    ).all()


def list_status_components_payload(db: Session) -> list[dict]:
    components = list_status_components(db)
    return [serialize_status_component(component) for component in components]


def serialize_status_component(component: StatusPageComponent) -> dict:
    return {
        "id": component.id,
        "name": component.name,
        "description": component.description,
        "group_name": component.group_name,
        "sort_order": component.sort_order,
        "status": component.status,
        "is_public": component.is_public,
        "ci_id": component.ci_id,
        "uptime_30d_pct": component.uptime_30d_pct,
    }


def validate_component_status(status: str) -> None:
    try:
        StatusPageComponentStatus(status)
    except ValueError:
        raise ErrorDeDominio(400, f"Invalid status: {status}")


def build_status_component(payload: StatusComponentIn) -> StatusPageComponent:
    return StatusPageComponent(**payload.model_dump())


def create_status_component_record(db, payload: StatusComponentIn) -> StatusPageComponent:
    validate_component_status(payload.status)
    c = build_status_component(payload)
    db.add(c)
    return c


def get_status_component_or_404(db: Session, component_id: str) -> StatusPageComponent:
    component = db.query(StatusPageComponent).filter(StatusPageComponent.id == component_id).first()
    if not component:
        raise ErrorDeDominio(404)
    return component


def apply_status_component_update(component: StatusPageComponent, payload: StatusComponentIn) -> None:
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(component, key, value)


def update_status_component_record(db: Session, component_id: str, payload: StatusComponentIn) -> StatusPageComponent:
    component = get_status_component_or_404(db, component_id)
    apply_status_component_update(component, payload)
    return component


def delete_status_component(db: Session, component_id: str) -> None:
    c = get_status_component_or_404(db, component_id)
    db.delete(c)


def build_status_incident(component_id: str, payload: StatusIncidentIn) -> StatusPageIncident:
    now = datetime.now(timezone.utc)
    initial_update = [
        {
            "time": now.isoformat(),
            "status": payload.status,
            "message": payload.update_message or "Investigating",
        }
    ]
    return StatusPageIncident(
        component_id=component_id,
        title=payload.title,
        status=payload.status,
        impact=payload.impact,
        ticket_id=payload.ticket_id,
        updates=json.dumps(initial_update),
    )


def create_status_incident_record(db: Session, component_id: str, payload: StatusIncidentIn) -> StatusPageIncident:
    component = get_status_component_or_404(db, component_id)
    incident = build_status_incident(component_id, payload)
    component.status = payload.impact
    db.add(incident)
    return incident


def get_status_incident_or_404(db: Session, incident_id: str) -> StatusPageIncident:
    incident = db.query(StatusPageIncident).filter(StatusPageIncident.id == incident_id).first()
    if not incident:
        raise ErrorDeDominio(404)
    return incident


def add_incident_update(incident: StatusPageIncident, payload: StatusIncidentUpdateIn) -> int:
    updates = json.loads(incident.updates or "[]")
    updates.append(
        {
            "time": datetime.now(timezone.utc).isoformat(),
            "status": payload.status,
            "message": payload.message,
        }
    )
    incident.updates = json.dumps(updates)
    incident.status = payload.status
    return len(updates)


def resolve_incident_if_needed(db: Session, incident: StatusPageIncident, status: str) -> None:
    if status != "resolved":
        return

    incident.resolved_at = datetime.now(timezone.utc)
    component = db.query(StatusPageComponent).filter(
        StatusPageComponent.id == incident.component_id
    ).first()
    if component:
        component.status = "operational"


def add_status_incident_update_record(db: Session, incident_id: str, payload: StatusIncidentUpdateIn) -> int:
    incident = get_status_incident_or_404(db, incident_id)
    updates_count = add_incident_update(incident, payload)
    resolve_incident_if_needed(db, incident, payload.status)
    return updates_count


def enlace_publico(db: Session, org_id: Optional[str]) -> dict:
    """La direccion de la pagina publica de la organizacion (va por su slug)."""
    from app.core.config import settings
    from app.models.mfa import Organization

    org = db.get(Organization, org_id) if org_id else None
    if org is None:
        return {"slug": None, "url": None}
    base = settings.BASE_URL.rstrip("/")
    return {"slug": org.slug, "url": f"{base}/status?org={org.slug}",
            "embed": f'<script src="{base}/status/embed.js" data-org="{org.slug}"></script>'}
