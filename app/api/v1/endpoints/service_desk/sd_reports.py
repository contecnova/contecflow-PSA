"""
SD Advanced Reporting Endpoints
=================================
POST /sd/reports/run           — execute drill-down report
GET  /sd/reports/types         — available report types
GET  /sd/reports/presets       — get saved report presets
POST /sd/reports/presets       — save a report preset
POST /sd/reports/export        — export to Excel
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from typing import Optional

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.services.service_desk.sd_reporting_service import (
    build_drilldown_report,
    export_report_excel,
    get_report_presets,
    save_report_preset,
    _REPORT_TYPES,
)

router = APIRouter(prefix="/sd/reports", tags=["sd-reports"])


@router.get("/types", summary="Available report types")
def list_report_types(_: User = Depends(get_current_user)):
    return {"report_types": _REPORT_TYPES}


@router.post("/run", summary="Execute drill-down report")
def run_report(
    body: dict,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return build_drilldown_report(
        db=db,
        report_type=body.get("report_type", "ticket_volume"),
        filters=body.get("filters", {}),
        date_from=body.get("date_from"),
        date_to=body.get("date_to"),
        group_by=body.get("group_by", "day"),
        page=int(body.get("page", 1)),
        page_size=int(body.get("page_size", 100)),
    )


@router.get("/presets", summary="Get saved report presets")
def get_presets(
    org_id: str = Query(...),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return {"presets": get_report_presets(db, org_id)}


@router.post("/presets", summary="Save a report preset")
def create_preset(
    body: dict,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    org_id = body.get("org_id", "default")
    return save_report_preset(db, org_id, body)


@router.post("/export", summary="Export report to Excel")
def export_report(
    body: dict,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    data = export_report_excel(
        db=db,
        report_type=body.get("report_type", "ticket_volume"),
        filters=body.get("filters", {}),
        date_from=body.get("date_from"),
        date_to=body.get("date_to"),
        group_by=body.get("group_by", "day"),
    )
    filename = f"sd_report_{body.get('report_type', 'report')}.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
