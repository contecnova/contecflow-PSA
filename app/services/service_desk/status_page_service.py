import json
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.service_desk import (
    StatusPageComponent,
    StatusPageComponentStatus,
    StatusPageIncident,
)
from app.schemas.service_desk import StatusComponentIn, StatusIncidentIn, StatusIncidentUpdateIn


def build_public_status_page_payload(db: Session) -> dict:
    components = db.query(StatusPageComponent).filter(
        StatusPageComponent.is_public == True
    ).order_by(StatusPageComponent.sort_order, StatusPageComponent.name).all()

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

    groups = {}
    for component in components:
        group_name = component.group_name or "General"
        if group_name not in groups:
            groups[group_name] = []

        active_incidents = db.query(StatusPageIncident).filter(
            StatusPageIncident.component_id == component.id,
            StatusPageIncident.resolved_at == None,
        ).all()

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
    }


def build_status_page_embed_script() -> str:
    return """
(function(){
    var scriptTag = document.currentScript;
    var api = (scriptTag && scriptTag.getAttribute('data-api')) || window.location.origin;
    var targetId = (scriptTag && scriptTag.getAttribute('data-target')) || 'clarive-status-page';
    var mount = document.getElementById(targetId);
    if(!mount){
        mount = document.createElement('div');
        mount.id = targetId;
        document.body.appendChild(mount);
    }
    fetch(api + '/api/v1/sd/status-page')
        .then(function(r){ return r.json(); })
        .then(function(data){
            var html = '<div style="font-family:system-ui,sans-serif;border:1px solid #d0d7de;border-radius:8px;padding:12px;max-width:760px">'
                + '<div style="font-weight:700;margin-bottom:8px">Service Status: ' + (data.overall_status || 'operational') + '</div>';
            Object.keys(data.groups || {}).forEach(function(g){
                html += '<div style="margin-top:8px"><div style="font-weight:600">' + g + '</div>';
                (data.groups[g] || []).forEach(function(c){
                    html += '<div style="display:flex;justify-content:space-between;font-size:13px;padding:4px 0">'
                        + '<span>' + c.name + '</span><span>' + c.status + '</span></div>';
                });
                html += '</div>';
            });
            html += '</div>';
            mount.innerHTML = html;
        })
        .catch(function(){ mount.innerHTML = '<div>Unable to load status page</div>'; });
})();
""".strip()


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
        raise HTTPException(400, f"Invalid status: {status}")


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
        raise HTTPException(404)
    return component


def apply_status_component_update(component: StatusPageComponent, payload: StatusComponentIn) -> None:
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(component, key, value)


def update_status_component_record(db: Session, component_id: str, payload: StatusComponentIn) -> StatusPageComponent:
    component = get_status_component_or_404(db, component_id)
    apply_status_component_update(component, payload)
    return component


def get_status_component_for_delete(db: Session, component_id: str) -> StatusPageComponent:
    return get_status_component_or_404(db, component_id)


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
        raise HTTPException(404)
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
