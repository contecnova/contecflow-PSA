"""
SOC Security Observability API — dashboard panels, detection workflow, incident management.

Endpoints:
  GET  /soc/overview                  — KPI tiles
  GET  /soc/events                    — paginated event stream
  GET  /soc/detections                — open/recent detections
  GET  /soc/detections/{id}           — detection detail
  PUT  /soc/detections/{id}/status    — SOC analyst workflow
  POST /soc/incidents                 — escalate to incident
  GET  /soc/incidents                 — incident list
  GET  /soc/incidents/{id}            — incident detail
  PATCH /soc/incidents/{id}/resolve   — close incident
  GET  /soc/login-anomalies           — anomaly feed
  PATCH /soc/login-anomalies/{id}/resolve — mark anomaly resolved
  GET  /soc/metrics/attack-indicators — top MITRE/IPs
  GET  /soc/metrics/mttd-mttr         — MTTD/MTTR trend
  GET  /soc/metrics/auth-heatmap      — failed-login heat data
  GET  /soc/metrics/top-ips           — top offending IPs
  GET  /soc/metrics/timeline          — event timeline (sparkline)
  POST /soc/events                    — manual event ingest (admin)
"""

from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_admin
from app.core.security import verify_admin_or_governance_role
from app.models.user import User
from app.models.security_observability import (
    IncidentStatus,
)
from datetime import timezone, timedelta
from datetime import datetime as _dt

from app.services.security_observability import (
    SecurityEventService, SecurityAnalyticsService, get_org_id as _org,
)
from app.core.responses import APIResponse, APIListResponse

router = APIRouter(prefix="/soc", tags=["Security Observability"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class EventOut(BaseModel):
    id: str
    category: str
    severity: str
    event_type: str
    ip_address: Optional[str] = None
    user_id: Optional[str] = None
    country: Optional[str] = None
    asn: Optional[str] = None
    is_vpn: bool = False
    is_tor: bool = False
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    detail: Optional[str] = None
    indicators: Optional[Dict[str, Any]] = None
    occurred_at: datetime
    ingested_at: datetime

    class Config:
        from_attributes = True


class DetectionOut(BaseModel):
    id: str
    title: str
    severity: str
    category: str
    kill_chain: Optional[str] = None
    mitre_id: Optional[str] = None
    mitre_tactic: Optional[str] = None
    user_id: Optional[str] = None
    ip_address: Optional[str] = None
    country: Optional[str] = None
    event_count: int = 0
    status: str
    assigned_to: Optional[str] = None
    first_seen_at: Optional[datetime] = None
    detected_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    evidence: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class IncidentOut(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    severity: str
    status: str
    lead_analyst: Optional[str] = None
    mttd_seconds: Optional[float] = None
    mttr_seconds: Optional[float] = None
    started_at: Optional[datetime] = None
    detected_at: Optional[datetime] = None
    contained_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    playbook_ref: Optional[str] = None
    root_cause: Optional[str] = None
    lessons_learned: Optional[str] = None

    class Config:
        from_attributes = True


class AnomalyOut(BaseModel):
    id: str
    user_id: Optional[str] = None
    anomaly_type: str
    severity: str
    ip_address: Optional[str] = None
    country: Optional[str] = None
    asn: Optional[str] = None
    detail: Optional[Dict[str, Any]] = None
    occurred_at: datetime
    is_resolved: bool = False

    class Config:
        from_attributes = True


# Request bodies

class DetectionStatusUpdate(BaseModel):
    status: str = Field(..., description="open|investigating|contained|resolved|false_positive")
    reason: Optional[str] = None


class CreateIncidentRequest(BaseModel):
    title: str
    description: Optional[str] = None
    severity: str = "high"
    detection_ids: List[str] = Field(default_factory=list)
    playbook_ref: Optional[str] = None


class ResolveIncidentRequest(BaseModel):
    root_cause: Optional[str] = None
    remediation: Optional[str] = None
    lessons_learned: Optional[str] = None


class ManualEventRequest(BaseModel):
    event_type: str
    category: str
    severity: str = "info"
    user_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    country: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    detail: Optional[str] = None
    raw_event: Optional[Dict[str, Any]] = None


# ── Helper —  resolve org_id from current user ─────────────────────────────

# _org delegated to security_observability.get_org_id (see import above)


# ── SOC Overview ──────────────────────────────────────────────────────────────

@router.get("/overview", summary="SOC KPI overview")
def soc_overview(
    hours: int = Query(24, ge=1, le=720),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns KPI tiles: event counts, auth failure rate, open detections/incidents, MTTD/MTTR."""
    svc = SecurityAnalyticsService(db=db, org_id=_org(current_user))
    return APIResponse.ok(data=svc.overview(hours=hours))


# ── Event stream ──────────────────────────────────────────────────────────────

@router.get("/events", summary="Paginated security event stream")
def list_events(
    category:   Optional[str] = Query(None),
    severity:   Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    user_id:    Optional[str] = Query(None),
    ip_address: Optional[str] = Query(None),
    hours:      int           = Query(24, ge=1, le=720),
    page:       int           = Query(1, ge=1),
    page_size:  int           = Query(50, ge=1, le=200),
    db: Session               = Depends(get_db),
    current_user: User        = Depends(get_current_user),
):
    since = _dt.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)
    svc = SecurityAnalyticsService(db=db, org_id=_org(current_user))
    total, items = svc.list_events_paginated(
        since=since, category=category, severity=severity, event_type=event_type,
        user_id=user_id, ip_address=ip_address, page=page, page_size=page_size,
    )
    return APIListResponse.ok(
        items=[EventOut.model_validate(e).model_dump() for e in items],
        total=total, page=page, page_size=page_size,
    )


# ── Detections ────────────────────────────────────────────────────────────────

@router.get("/detections", summary="List security detections")
def list_detections(
    status:   Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    hours:    int           = Query(168, ge=1, le=8760),
    page:     int           = Query(1, ge=1),
    page_size:int           = Query(50, ge=1, le=200),
    db: Session             = Depends(get_db),
    current_user: User      = Depends(get_current_user),
):
    since = _dt.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)
    svc = SecurityAnalyticsService(db=db, org_id=_org(current_user))
    total, items = svc.list_detections_paginated(
        since=since, status=status, severity=severity, page=page, page_size=page_size,
    )
    return APIListResponse.ok(
        items=[DetectionOut.model_validate(d).model_dump() for d in items],
        total=total, page=page, page_size=page_size,
    )


@router.get("/detections/{detection_id}", response_model=APIResponse[DetectionOut], summary="Detection detail")
def get_detection(
    detection_id: str,
    db: Session  = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = SecurityEventService(db=db, org_id=_org(current_user))
    det = svc.get_detection_by_id(detection_id)
    if not det:
        raise HTTPException(status_code=404, detail="Detection not found")
    return APIResponse.ok(data=DetectionOut.model_validate(det))


@router.put(
    "/detections/{detection_id}/status",
    response_model=APIResponse[DetectionOut],
    summary="Update detection status (SOC workflow)",
)
def update_detection_status(
    detection_id: str,
    body: DetectionStatusUpdate,
    db: Session  = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sensible: telemetria de seguridad
):
    allowed = {IncidentStatus.OPEN, IncidentStatus.INVESTIGATING,
               IncidentStatus.CONTAINED, IncidentStatus.RESOLVED, IncidentStatus.FALSE_POS}
    if body.status not in allowed:
        raise HTTPException(status_code=422, detail=f"Invalid status: {body.status}")

    svc = SecurityEventService(db=db, org_id=_org(current_user))
    try:
        det = svc.resolve_detection(
            detection_id=detection_id,
            analyst_id=str(current_user.id),
            status=body.status,
            reason=body.reason,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Detection not found")
    return APIResponse.ok(data=DetectionOut.model_validate(det))


# ── Incidents ─────────────────────────────────────────────────────────────────

@router.post(
    "/incidents",
    response_model=APIResponse[IncidentOut],
    status_code=status.HTTP_201_CREATED,
    summary="Escalate detections to a security incident",
)
def create_incident(
    body: CreateIncidentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sensible: telemetria de seguridad
):
    svc = SecurityEventService(db=db, org_id=_org(current_user))
    inc = svc.create_incident(
        title           = body.title,
        description     = body.description,
        severity        = body.severity,
        detection_ids   = body.detection_ids,
        lead_analyst_id = str(current_user.id),
        playbook_ref    = body.playbook_ref,
    )
    return APIResponse.ok(data=IncidentOut.model_validate(inc))


@router.get("/incidents", summary="List security incidents")
def list_incidents(
    status_filter: Optional[str] = Query(None, alias="status"),
    hours:     int  = Query(720, ge=1, le=8760),
    page:      int  = Query(1, ge=1),
    page_size: int  = Query(50, ge=1, le=200),
    db: Session     = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    since = _dt.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)
    svc = SecurityAnalyticsService(db=db, org_id=_org(current_user))
    total, items = svc.list_incidents_paginated(
        since=since, status_filter=status_filter, page=page, page_size=page_size,
    )
    return APIListResponse.ok(
        items=[IncidentOut.model_validate(i).model_dump() for i in items],
        total=total, page=page, page_size=page_size,
    )


@router.get("/incidents/{incident_id}", response_model=APIResponse[IncidentOut], summary="Incident detail")
def get_incident(
    incident_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = SecurityEventService(db=db, org_id=_org(current_user))
    inc = svc.get_incident_by_id(incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    return APIResponse.ok(data=IncidentOut.model_validate(inc))


@router.patch("/incidents/{incident_id}/resolve", response_model=APIResponse[IncidentOut], summary="Resolve incident")
def resolve_incident(
    incident_id: str,
    body: ResolveIncidentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sensible: telemetria de seguridad
):
    svc = SecurityEventService(db=db, org_id=_org(current_user))
    try:
        inc = svc.resolve_incident(
            incident_id = incident_id,
            analyst_id  = str(current_user.id),
            root_cause  = body.root_cause,
            remediation = body.remediation,
            lessons     = body.lessons_learned,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Incident not found")
    return APIResponse.ok(data=IncidentOut.model_validate(inc))


# ── Login Anomalies ───────────────────────────────────────────────────────────

@router.get("/login-anomalies", summary="Login anomaly feed")
def list_login_anomalies(
    anomaly_type:    Optional[str] = Query(None),
    severity:        Optional[str] = Query(None),
    unresolved_only: bool          = Query(True),
    hours:           int           = Query(24, ge=1, le=720),
    page:            int           = Query(1, ge=1),
    page_size:       int           = Query(50, ge=1, le=200),
    db: Session                    = Depends(get_db),
    current_user: User             = Depends(get_current_user),
):
    since = _dt.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)
    svc = SecurityAnalyticsService(db=db, org_id=_org(current_user))
    total, items = svc.list_login_anomalies_paginated(
        since=since, anomaly_type=anomaly_type, severity=severity,
        unresolved_only=unresolved_only, page=page, page_size=page_size,
    )
    return APIListResponse.ok(
        items=[AnomalyOut.model_validate(a).model_dump() for a in items],
        total=total, page=page, page_size=page_size,
    )


@router.patch(
    "/login-anomalies/{anomaly_id}/resolve",
    summary="Mark login anomaly as resolved",
)
def resolve_anomaly(
    anomaly_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sensible: telemetria de seguridad
):
    svc = SecurityEventService(db=db, org_id=_org(current_user))
    anomaly = svc.resolve_anomaly(anomaly_id)
    if not anomaly:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    return APIResponse.ok(data={"id": anomaly_id, "is_resolved": True})


# ── SOC Metrics ───────────────────────────────────────────────────────────────

@router.get("/metrics/attack-indicators", summary="Top attack indicators with MITRE mapping")
def attack_indicators(
    hours: int = Query(24, ge=1, le=720),
    limit: int = Query(15, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = SecurityAnalyticsService(db=db, org_id=_org(current_user))
    return APIListResponse.ok(items=svc.top_attack_indicators(hours=hours, limit=limit))


@router.get("/metrics/mttd-mttr", summary="MTTD/MTTR daily trend for KPI chart")
def mttd_mttr_trend(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = SecurityAnalyticsService(db=db, org_id=_org(current_user))
    return APIListResponse.ok(items=svc.mttd_mttr_trend(days=days))


@router.get("/metrics/auth-heatmap", summary="Authentication failure heat by hour and country")
def auth_heatmap(
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = SecurityAnalyticsService(db=db, org_id=_org(current_user))
    return APIListResponse.ok(items=svc.auth_failure_heatmap(days=days))


@router.get("/metrics/top-ips", summary="Top offending IPs")
def top_ips(
    hours: int = Query(24, ge=1, le=720),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = SecurityAnalyticsService(db=db, org_id=_org(current_user))
    return APIListResponse.ok(items=svc.top_offending_ips(hours=hours, limit=limit))


@router.get("/metrics/timeline", summary="Event timeline bucketed by time for sparkline charts")
def event_timeline(
    hours:          int = Query(24, ge=1, le=720),
    bucket_minutes: int = Query(60, ge=5, le=1440),
    db: Session         = Depends(get_db),
    current_user: User  = Depends(get_current_user),
):
    svc = SecurityAnalyticsService(db=db, org_id=_org(current_user))
    return APIListResponse.ok(items=svc.event_timeline(hours=hours, bucket_minutes=bucket_minutes))


# ── Manual event ingest (admin only) ─────────────────────────────────────────

@router.post(
    "/events",
    response_model=APIResponse[dict],
    status_code=status.HTTP_201_CREATED,
    summary="Manually ingest a security event (admin/integration)",
)
def ingest_event(
    body: ManualEventRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sensible: telemetria de seguridad
):
    verify_admin_or_governance_role(current_user)
    svc = SecurityEventService(db=db, org_id=_org(current_user))
    ev = svc.emit(
        event_type    = body.event_type,
        category      = body.category,
        severity      = body.severity,
        user_id       = body.user_id,
        ip_address    = body.ip_address,
        user_agent    = body.user_agent,
        country       = body.country,
        resource_type = body.resource_type,
        resource_id   = body.resource_id,
        detail        = body.detail,
        raw_event     = body.raw_event,
    )
    return APIResponse.ok(data={"id": ev.id, "occurred_at": ev.occurred_at.isoformat()})
