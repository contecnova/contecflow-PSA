"""
BI Export endpoints — Excel avanzado + PowerPoint con charts
=============================================================
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.responses import APIResponse
from app.models.user import User
from app.services import bi_export_service as svc
from app.core.constantes import NOMBRE_DEL_PRODUCTO

router = APIRouter(prefix="/bi/export", tags=["BI Export"])


@router.get("/excel", summary="Descargar dashboard como Excel avanzado (.xlsx)")
def download_excel(
    period_days: int = Query(180, ge=7, le=1825),
    title: str = Query(f"Informe BI {NOMBRE_DEL_PRODUCTO}"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Genera y descarga un archivo Excel con:
    - Tabla de KPIs con estilo nombrado
    - Hoja de datos mensuales con tabla, fórmulas SUM/AVERAGE
    - Gráficos de barras (ingresos) y línea (SLA) embebidos
    """
    org_id = str(current_user.organization_id or "global")
    xlsx_bytes = svc.export_dashboard_excel(db, org_id, period_days=period_days, report_title=title)
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="bi_report_{org_id}.xlsx"'},
    )


@router.get("/pptx", summary="Descargar dashboard como PowerPoint (.pptx)")
def download_pptx(
    period_days: int = Query(180, ge=7, le=1825),
    title: str = Query(f"Informe BI {NOMBRE_DEL_PRODUCTO}"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Genera y descarga una presentación PowerPoint con:
    - Diapositiva de portada
    - Resumen de KPIs
    - Gráficos de barras/columnas/línea con datos reales
    """
    org_id = str(current_user.organization_id or "global")
    pptx_bytes = svc.export_dashboard_pptx(db, org_id, period_days=period_days, report_title=title)
    return Response(
        content=pptx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="bi_report_{org_id}.pptx"'},
    )


@router.get("/formats", summary="Listar formatos de exportación disponibles")
def list_export_formats(
    current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data={
        "formats": [
            {
                "id": "excel",
                "name": "Excel avanzado",
                "extension": "xlsx",
                "description": "Tablas nombradas, fórmulas, gráficos embebidos",
                "endpoint": "/bi/export/excel",
            },
            {
                "id": "pptx",
                "name": "PowerPoint",
                "extension": "pptx",
                "description": "Presentación con KPIs y charts de barras/línea",
                "endpoint": "/bi/export/pptx",
            },
        ]
    })
