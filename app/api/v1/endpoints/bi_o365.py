"""
bi_o365.py — Office 365 BI analytics endpoints.

Routes:
  GET  /bi/o365/config                — O365 connector configuration
  PUT  /bi/o365/config                — update O365 connector configuration
  POST /bi/o365/sync                  — trigger manual data sync
  GET  /bi/o365/reports/{report}      — get data for a specific report
  GET  /bi/o365/adoption              — aggregated adoption summary
  GET  /bi/o365/sync-log              — sync history
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.ratelimit import limiter
from app.db.session import get_db
from app.models.user import User
from app.services.bi_o365_service import (
    get_config,
    save_config,
    run_sync,
    get_report_data,
    get_sync_log,
    get_adoption_summary,
    _SUPPORTED_REPORTS,
)

router = APIRouter(prefix="/bi/o365", tags=["BI Office 365"])


class O365ConfigUpdate(BaseModel):
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    sync_period: Optional[str] = Field(None, pattern=r"^D(7|30|90|180)$")
    enabled_reports: Optional[List[str]] = None


class SyncRequest(BaseModel):
    client_secret: str = Field(..., description="Azure AD client secret (sent only during sync, never persisted)")
    reports: Optional[List[str]] = None


@router.get("/config", summary="Configuración del conector O365 BI")
@limiter.limit("60/minute")
def o365_get_config(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return get_config(db, str(org_id) if org_id else None)


@router.put("/config", summary="Actualizar configuración del conector O365")
@limiter.limit("20/minute")
def o365_save_config(
    request: Request,
    body: O365ConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return save_config(db, str(org_id) if org_id else None, body.model_dump(exclude_none=True))


@router.post("/sync", summary="Sincronizar datos de uso O365 desde Graph API", status_code=202)
@limiter.limit("10/minute")
def o365_sync(
    request: Request,
    body: Optional[SyncRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    payload = body or SyncRequest(client_secret="", reports=None)
    result = run_sync(
        db,
        str(org_id) if org_id else None,
        reports=payload.reports,
        client_secret=payload.client_secret,
    )
    if not result.get("ok"):
        return {
            "status": "error",
            "queued": False,
            "detail": result.get("error", "Sync failed"),
            **result,
        }
    return {
        "status": "queued",
        "queued": True,
        **result,
    }


@router.get("/reports/{report_name}", summary="Datos de un informe O365 específico")
@limiter.limit("30/minute")
def o365_report_data(
    request: Request,
    report_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if report_name not in _SUPPORTED_REPORTS:
        raise HTTPException(status_code=404, detail=f"Report '{report_name}' not supported. Available: {_SUPPORTED_REPORTS}")
    org_id = getattr(current_user, "organization_id", None)
    return get_report_data(db, str(org_id) if org_id else None, report_name)


@router.get("/adoption", summary="Resumen de adopción de productos O365")
@limiter.limit("30/minute")
def o365_adoption(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return get_adoption_summary(db, str(org_id) if org_id else None)


@router.get("/sync-log", summary="Historial de sincronizaciones O365")
@limiter.limit("60/minute")
def o365_sync_log(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    log = get_sync_log(db, str(org_id) if org_id else None, limit=limit)
    return {"entries": log, "count": len(log)}
