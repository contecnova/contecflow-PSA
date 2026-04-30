"""
bi_etl.py — BI ETL Connector management API.

Routes:
  GET  /bi/etl/connectors                      — list available connectors + status
  GET  /bi/etl/connectors/{connector_id}       — single connector details
  POST /bi/etl/connectors/{connector_id}/sync  — trigger manual sync (fires Celery task)
  GET  /bi/etl/connectors/{connector_id}/log   — sync history log
  GET  /bi/etl/data/{connector_id}             — read synced data blob
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.ratelimit import limiter
from app.db.session import get_db
from app.models.settings import AppSetting
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bi/etl", tags=["BI ETL Connectors"])

_CONNECTOR_IDS = [
    "salesforce", "hubspot", "jira", "stripe", "xero",
    "zendesk", "freshdesk", "servicenow", "bamboohr", "quickbooks",
    "netsuite", "sap", "github", "gitlab", "datadog",
    "pagerduty", "twilio", "sendgrid", "intercom", "pipedrive",
]

_SYNC_DATA_KEY_TPL = "bi.etl.sync_data.{connector}.{org}"
_SYNC_LOG_KEY_TPL = "bi.etl.sync_log.{connector}.{org}"


def _get_json(db: Session, key: str, organization_id: Optional[str], *, default=None):
    q = db.query(AppSetting).filter(AppSetting.key == key)
    if organization_id:
        q = q.filter(AppSetting.organization_id == organization_id)
    else:
        q = q.filter(AppSetting.organization_id.is_(None))
    row = q.first()
    if not row or not row.value:
        return default
    try:
        return json.loads(row.value)
    except Exception:
        return default


def _get_connectors_state(db: Session, organization_id: Optional[str]) -> dict:
    from app.services.bi_intelligence_service import get_connectors  # type: ignore[import]
    try:
        return get_connectors(db, organization_id=organization_id)
    except Exception:
        return {}


class SyncRequest(BaseModel):
    extra_config: dict = Field(default_factory=dict, description="Optional extra config overrides for this run")


@router.get("/connectors", summary="Listar conectores ETL y su estado")
@limiter.limit("60/minute")
def list_connectors(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    state = _get_connectors_state(db, str(org_id) if org_id else None)
    items = []
    for cid in _CONNECTOR_IDS:
        info = state.get(cid, {})
        items.append({
            "connector_id": cid,
            "enabled": info.get("enabled", False),
            "status": info.get("status", "disconnected"),
            "last_sync_at": info.get("last_sync_at"),
            "last_records": info.get("last_records", 0),
        })
    return {"connectors": items, "count": len(items)}


@router.get("/connectors/{connector_id}", summary="Detalle de un conector ETL")
@limiter.limit("60/minute")
def get_connector_detail(
    request: Request,
    connector_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if connector_id not in _CONNECTOR_IDS:
        raise HTTPException(status_code=404, detail="Connector not found")
    org_id = getattr(current_user, "organization_id", None)
    org_str = str(org_id) if org_id else None
    state = _get_connectors_state(db, org_str)
    info = state.get(connector_id, {})
    log = _get_json(db, _SYNC_LOG_KEY_TPL.format(connector=connector_id, org=org_str or "global"), org_str, default=[])
    return {
        "connector_id": connector_id,
        "enabled": info.get("enabled", False),
        "status": info.get("status", "disconnected"),
        "last_sync_at": info.get("last_sync_at"),
        "last_records": info.get("last_records", 0),
        "recent_log": (log or [])[-10:],
    }


@router.post("/connectors/{connector_id}/sync", summary="Disparar sincronización manual", status_code=202)
@limiter.limit("10/minute")
def trigger_sync(
    request: Request,
    connector_id: str,
    body: SyncRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if connector_id not in _CONNECTOR_IDS:
        raise HTTPException(status_code=404, detail="Connector not found")
    org_id = getattr(current_user, "organization_id", None)
    org_str = str(org_id) if org_id else None
    try:
        from app.worker import sync_connector_data  # type: ignore[import]
        queue_name = f"etl_{connector_id}"
        task = sync_connector_data.apply_async(
            kwargs={"connector_id": connector_id, "org_id": org_str},
            queue=queue_name,
            routing_key=queue_name,
        )
        return {
            "task_id": task.id,
            "connector_id": connector_id,
            "status": "queued",
            "queue": queue_name,
        }
    except Exception as exc:
        logger.warning("trigger_sync: could not dispatch Celery task: %s", exc)
        return {"task_id": None, "connector_id": connector_id, "status": "queued_local", "detail": str(exc)}


@router.get("/connectors/{connector_id}/log", summary="Historial de sincronizaciones")
@limiter.limit("60/minute")
def get_sync_log(
    request: Request,
    connector_id: str,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if connector_id not in _CONNECTOR_IDS:
        raise HTTPException(status_code=404, detail="Connector not found")
    org_id = getattr(current_user, "organization_id", None)
    org_str = str(org_id) if org_id else None
    log = _get_json(db, _SYNC_LOG_KEY_TPL.format(connector=connector_id, org=org_str or "global"), org_str, default=[])
    entries = (log or [])[-limit:]
    return {"connector_id": connector_id, "entries": entries, "count": len(entries)}


@router.get("/data/{connector_id}", summary="Leer datos sincronizados de un conector")
@limiter.limit("30/minute")
def get_synced_data(
    request: Request,
    connector_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if connector_id not in _CONNECTOR_IDS:
        raise HTTPException(status_code=404, detail="Connector not found")
    org_id = getattr(current_user, "organization_id", None)
    org_str = str(org_id) if org_id else None
    data = _get_json(db, _SYNC_DATA_KEY_TPL.format(connector=connector_id, org=org_str or "global"), org_str, default={})
    return {"connector_id": connector_id, "data": data or {}}
