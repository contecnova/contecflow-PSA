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

from app.core.deps import get_current_user, requiere_capacidad
from app.core.ratelimit import limiter
from app.core.responses import APIResponse
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
from app.core.codigos_de_error import error_http, desde_valor

router = APIRouter(prefix="/bi/o365", tags=["BI Office 365"])


class O365ConfigUpdate(BaseModel):
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = Field(None, max_length=500, description="Se guarda cifrado; vacío = no cambia")
    enabled: Optional[bool] = None
    sync_period: Optional[str] = Field(None, pattern=r"^D(7|30|90|180)$")
    enabled_reports: Optional[List[str]] = None


class SyncRequest(BaseModel):
    reports: Optional[List[str]] = None


@router.get("/config", summary="Configuración del conector O365 BI")
@limiter.limit("60/minute")
def o365_get_config(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("bi.administrar")),
):
    org_id = getattr(current_user, "organization_id", None)
    return APIResponse.ok(data=get_config(db, str(org_id) if org_id else None))


@router.put("/config", summary="Actualizar configuración del conector O365")
@limiter.limit("20/minute")
def o365_save_config(
    request: Request,
    body: O365ConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(requiere_capacidad("bi.administrar")),  # auditoria 2026-09: sensible: credenciales de Microsoft 365
):
    org_id = getattr(current_user, "organization_id", None)
    org = str(org_id) if org_id else None
    datos = body.model_dump(exclude_none=True)
    # 19-11-2026 (la configuración pasa a Configuración → Integraciones →
    # Informes de Microsoft 365): el cambio de credenciales queda en la
    # auditoría; antes no dejaba rastro. `get_config` nunca devuelve el secreto
    # (solo `secret_puesto`), y del secreto nuevo solo se anota que cambió.
    from app.services.audit import auditar_y_confirmar
    antes = get_config(db, org)
    try:
        despues = save_config(db, org, datos)
    except ValueError as exc:
        raise desde_valor(400, exc)
    auditar_y_confirmar(db, current_user, "UPDATE", "bi_o365_config", org,
                        old_values=antes, new_values=despues,
                        metadata={"secreto_cambiado": bool((datos.get("client_secret") or "").strip())})
    return APIResponse.ok(data=despues)


@router.post("/sync", summary="Sincronizar datos de uso O365 desde Graph API")
@limiter.limit("10/minute")
def o365_sync(
    request: Request,
    body: Optional[SyncRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(requiere_capacidad("bi.administrar")),  # auditoria 2026-09: sensible: credenciales de Microsoft 365
):
    """Corre en la petición y devuelve el resultado real de cada informe.

    Antes respondía 202 «queued» aunque ya hubiera terminado, y «ok» aunque
    Graph hubiera rechazado todos los informes.
    """
    org_id = getattr(current_user, "organization_id", None)
    return APIResponse.ok(data=run_sync(db, str(org_id) if org_id else None,
                                        reports=(body.reports if body else None)))


@router.get("/reports/{report_name}", summary="Datos de un informe O365 específico")
@limiter.limit("30/minute")
def o365_report_data(
    request: Request,
    report_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("bi.administrar")),
):
    if report_name not in _SUPPORTED_REPORTS:
        raise error_http(404, "campo_no_valido_opciones", detail=f"Report '{report_name}' not supported. Available: {_SUPPORTED_REPORTS}", campo="report", valor=report_name, opciones=_SUPPORTED_REPORTS)
    org_id = getattr(current_user, "organization_id", None)
    return APIResponse.ok(data=get_report_data(db, str(org_id) if org_id else None, report_name))


@router.get("/adoption", summary="Resumen de adopción de productos O365")
@limiter.limit("30/minute")
def o365_adoption(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("bi.administrar")),
):
    org_id = getattr(current_user, "organization_id", None)
    return APIResponse.ok(data=get_adoption_summary(db, str(org_id) if org_id else None))


@router.get("/sync-log", summary="Historial de sincronizaciones O365")
@limiter.limit("60/minute")
def o365_sync_log(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("bi.administrar")),
):
    org_id = getattr(current_user, "organization_id", None)
    log = get_sync_log(db, str(org_id) if org_id else None, limit=limit)
    return APIResponse.ok(data={"entries": log, "count": len(log)})
