

from fastapi import status, Body, APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional, Dict
import logging
import csv
import io
# Auditoría 2026-08 (hallazgo 22). Antes era `v238_service`, un módulo nombrado
# por número de versión con seis dominios dentro. La analítica ad-hoc tiene ahora
# su propio módulo.
from app.services import adhoc_analytics_service, analytics_service
from app.core.deps import get_db, get_current_user, require_any_manager
from app.core.responses import APIListResponse, APIResponse
from app.models.user import User
from pydantic import BaseModel
from app.core import timeutil



# Unificar todos los endpoints bajo un solo router
router = APIRouter(prefix="/analytics", tags=["analytics"])
logger = logging.getLogger(__name__)

# ENDPOINTS BI/Analytics: Adhoc, Drilldown, Cross-filter
@router.post("/adhoc", summary="Adhoc analytics query", status_code=status.HTTP_200_OK)
def adhoc_analytics(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Auditoría 2026-08 (P1-9). Aquí había un
    # `if hasattr(v238_service, "run_analytics_adhoc")` — y esa función NO
    # EXISTE: la implementación real se llama `run_adhoc_query`. El hasattr daba
    # False siempre, así que este endpoint devolvía SIEMPRE
    # {"results": [], "total_rows": 0} con un 200, sin error ni log. Los tests
    # pasaban porque sólo comprobaban que las claves existieran, no que hubiera
    # datos. La llamada además tenía el orden de argumentos equivocado y omitía
    # `limit`, así que tampoco habría funcionado si el nombre hubiese acertado.
    #
    # Se llama directo, sin hasattr: si algún día se renombra, queremos un
    # ImportError al arrancar y no un endpoint que miente en silencio.
    try:
        metric = payload.get("metric")
        dimensions = payload.get("dimensions", [])
        result = adhoc_analytics_service.run_adhoc_query(
            metric=metric,
            dimensions=dimensions,
            filters=payload.get("filters", {}) or {},
            date_from=payload.get("date_from"),
            date_to=payload.get("date_to"),
            limit=payload.get("limit", 100),
            db=db,
        )
        return APIResponse.ok(data=result)
    except HTTPException:
        raise
    except ValueError as e:
        return JSONResponse(status_code=400, content={"detail": f"Error de datos: {str(e)}"})
    except Exception as e:
        logger.error("Error inesperado en analytics_adhoc: %s", e, exc_info=True)
        return JSONResponse(status_code=500, content={"detail": "Error interno al ejecutar la consulta."})

@router.get("/drilldown", summary="Analytics drilldown", status_code=status.HTTP_200_OK)
def analytics_drilldown(
    metric: str,
    dimension: str,
    value: str,
    page: int = 1,
    page_size: int = 100,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Auditoría 2026-08 (hallazgo 22). Aquí había un
    # `if hasattr(v238_service, "run_analytics_drilldown")`. Es el mismo patrón
    # que dejó muerto el endpoint /analytics/adhoc (P1-9): si la función se
    # renombra o se mueve, el hasattr da False y el endpoint responde 200 con
    # filas vacías, sin error ni registro. Se llama directo para que un renombrado
    # falle en voz alta.
    try:
        result = adhoc_analytics_service.run_analytics_drilldown(
            metric, dimension, value, date_from, date_to, page, page_size, db
        )
        if result:
            return APIResponse.ok(data=result)
        return APIResponse.ok(data={"metric": metric, "dimension": dimension, "value": value, "rows": [], "page": page, "page_size": page_size})
    except ValueError as e:
        return JSONResponse(status_code=400, content={"detail": f"Error de datos: {str(e)}"})
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error inesperado en analytics_drilldown: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"detail": f"Error interno: {str(e)}"})

@router.post("/cross-filter", summary="Analytics cross-filter", status_code=status.HTTP_200_OK)
def analytics_cross_filter(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Mismo caso que el drilldown: fuera el `hasattr`, llamada directa.
    try:
        result = adhoc_analytics_service.run_analytics_cross_filter(payload, db)
        if result:
            return APIResponse.ok(data=result)
        return APIResponse.ok(data={"active_filters": payload.get("active_filters", {}), "results": {}})
    except ValueError as e:
        return JSONResponse(status_code=400, content={"detail": f"Error de datos: {str(e)}"})
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error inesperado en analytics_cross_filter: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"detail": f"Error interno: {str(e)}"})


# ── Response Models ───────────────────────────────────────────────────────

class DailySummary(BaseModel):
    """Daily imputation summary."""
    date: date
    total_hours: float
    billable_hours: float
    approved_hours: float
    num_entries: int


class WeeklySummary(BaseModel):
    """Weekly imputation summary."""
    week_iso: str
    total_hours: float
    billable_hours: float
    approved_hours: float
    num_entries: int


class MonthlySummary(BaseModel):
    """Monthly imputation summary."""
    year_month: str
    total_hours: float
    billable_hours: float
    approved_hours: float
    num_entries: int


class ImputationStats(BaseModel):
    """Overall imputation statistics."""
    period: str
    avg_hours_per_day: float
    avg_billable_pct: float
    total_cost: float
    daily: List[DailySummary]
    weekly: List[WeeklySummary]
    monthly: List[MonthlySummary]


class DocumentStats(BaseModel):
    """Document statistics."""
    total_documents: int
    by_category: Dict[str, int]
    by_status: Dict[str, int]
    avg_versions_per_document: float
    total_storage_mb: float


class ResourceForecast(BaseModel):
    """Advanced resource forecast."""
    user_id: str
    user_name: str
    forecast_weeks: int
    avg_load_pct: float
    peak_load_week: str
    peak_load_pct: float
    risk_level: str  # low | medium | high


# ── Imputation Analytics ───────────────────────────────────────────────────

@router.get("/imputations", response_model=APIResponse[ImputationStats], summary="Get imputation statistics")
def get_imputation_analytics(
    user_id: Optional[str] = None,
    period: str = Query("monthly", pattern="^(daily|weekly|monthly)$"),
    days_back: int = Query(90, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get imputation analytics for user or team."""
    # Permission: employees see only their own, managers see their projects, admins see all
    query_user_id = user_id if user_id and current_user.role in ["admin", "pm"] else current_user.id

    cutoff_date = timeutil.today() - timedelta(days=days_back)

    imputations = analytics_service.get_imputations_for_analytics(db, query_user_id, cutoff_date)

    if not imputations:
        return APIResponse.ok(data=ImputationStats(
            period=period,
            avg_hours_per_day=0,
            avg_billable_pct=0,
            total_cost=0,
            daily=[],
            weekly=[],
            monthly=[],
        ))

    # Daily summaries
    daily_dict = {}
    for imp in imputations:
        key = str(imp.date)
        if key not in daily_dict:
            daily_dict[key] = {"date": imp.date, "hours": 0, "billable": 0, "approved": 0, "count": 0}
        daily_dict[key]["hours"] += imp.hours
        daily_dict[key]["billable"] += imp.hours if imp.is_billable else 0
        daily_dict[key]["approved"] += imp.hours if imp.is_approved else 0
        daily_dict[key]["count"] += 1

    daily = [
        DailySummary(
            date=v["date"],
            total_hours=v["hours"],
            billable_hours=v["billable"],
            approved_hours=v["approved"],
            num_entries=v["count"],
        )
        for v in sorted(daily_dict.values(), key=lambda x: x["date"])
    ]

    # Weekly summaries
    weekly_dict = {}
    for imp in imputations:
        iso = imp.date.isocalendar()
        key = f"{iso[0]}-W{iso[1]:02d}"
        if key not in weekly_dict:
            weekly_dict[key] = {"week": key, "hours": 0, "billable": 0, "approved": 0, "count": 0}
        weekly_dict[key]["hours"] += imp.hours
        weekly_dict[key]["billable"] += imp.hours if imp.is_billable else 0
        weekly_dict[key]["approved"] += imp.hours if imp.is_approved else 0
        weekly_dict[key]["count"] += 1

    weekly = [
        WeeklySummary(
            week_iso=v["week"],
            total_hours=v["hours"],
            billable_hours=v["billable"],
            approved_hours=v["approved"],
            num_entries=v["count"],
        )
        for v in sorted(weekly_dict.values(), key=lambda x: x["week"])
    ]

    # Monthly summaries
    monthly_dict = {}
    for imp in imputations:
        key = imp.date.strftime("%Y-%m")
        if key not in monthly_dict:
            monthly_dict[key] = {"month": key, "hours": 0, "billable": 0, "approved": 0, "count": 0}
        monthly_dict[key]["hours"] += imp.hours
        monthly_dict[key]["billable"] += imp.hours if imp.is_billable else 0
        monthly_dict[key]["approved"] += imp.hours if imp.is_approved else 0
        monthly_dict[key]["count"] += 1

    monthly = [
        MonthlySummary(
            year_month=v["month"],
            total_hours=v["hours"],
            billable_hours=v["billable"],
            approved_hours=v["approved"],
            num_entries=v["count"],
        )
        for v in sorted(monthly_dict.values(), key=lambda x: x["month"])
    ]

    total_hours = sum(i.hours for i in imputations)
    avg_hours_per_day = total_hours / max(1, len(daily))
    avg_billable_pct = (sum(i.hours for i in imputations if i.is_billable) / total_hours * 100) if total_hours > 0 else 0
    total_cost = sum(i.cost_amount or 0 for i in imputations)

    return APIResponse.ok(data=ImputationStats(
        period=period,
        avg_hours_per_day=round(avg_hours_per_day, 2),
        avg_billable_pct=round(avg_billable_pct, 1),
        total_cost=round(total_cost, 2),
        daily=daily,
        weekly=weekly,
        monthly=monthly,
    ))


# ── Document Analytics ─────────────────────────────────────────────────────

@router.get("/documents", response_model=APIResponse[DocumentStats], summary="Get document statistics")
def get_document_analytics(
    days_back: int = Query(90, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """Get document management statistics."""
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)

    docs = analytics_service.get_documents_for_analytics(db, cutoff_date)

    # By category
    category_counts = {}
    for doc in docs:
        cat = doc.category.value
        category_counts[cat] = category_counts.get(cat, 0) + 1

    # By status
    status_counts = {}
    for doc in docs:
        status = doc.approval_status.value
        status_counts[status] = status_counts.get(status, 0) + 1

    # Versions per document
    total_versions = sum(len(doc.versions) for doc in docs)
    avg_versions = total_versions / len(docs) if docs else 0

    # Storage estimate (sum of all version sizes)
    total_size_mb = sum(
        sum(v.file_size or 0 for v in doc.versions) / 1024 / 1024
        for doc in docs
    )

    return APIResponse.ok(data=DocumentStats(
        total_documents=len(docs),
        by_category=category_counts,
        by_status=status_counts,
        avg_versions_per_document=round(avg_versions, 2),
        total_storage_mb=round(total_size_mb, 2),
    ))


# ── Advanced Resource Forecast ─────────────────────────────────────────────

@router.get("/resources/forecast-advanced", response_model=APIListResponse[ResourceForecast], summary="Advanced resource forecast")
def get_advanced_forecast(
    weeks_ahead: int = Query(12, ge=1, le=52),
    include_risk_assessment: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """Get advanced forecast with risk assessment."""
    users = analytics_service.get_active_users(db)
    forecasts = []

    for user in users:
        # Get snapshots for next N weeks
        snapshots = analytics_service.get_resource_snapshots_for_user(db, user.id, weeks_ahead)

        if not snapshots:
            continue

        loads = [s.utilization_pct or 0 for s in snapshots]
        avg_load = sum(loads) / len(loads) if loads else 0
        peak_load = max(loads) if loads else 0
        peak_week = snapshots[loads.index(peak_load)].week_iso if loads else ""

        # Risk assessment
        if avg_load > 100:
            risk = "high"
        elif avg_load > 80:
            risk = "medium"
        else:
            risk = "low"

        forecasts.append(
            ResourceForecast(
                user_id=user.id,
                user_name=user.full_name,
                forecast_weeks=len(snapshots),
                avg_load_pct=round(avg_load, 1),
                peak_load_week=peak_week,
                peak_load_pct=round(peak_load, 1),
                risk_level=risk,
            )
        )

    items = sorted(forecasts, key=lambda x: x.avg_load_pct, reverse=True)
    return APIListResponse.ok(items=items, total=len(items))


# ── Export Endpoints ───────────────────────────────────────────────────────

@router.get("/exports/imputations-csv", summary="Export imputations to CSV")
def export_imputations_csv(
    user_id: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export imputations to CSV."""
    query_user_id = user_id if user_id and current_user.role in ["admin"] else current_user.id

    imputations = analytics_service.get_imputations_for_export(db, query_user_id, date_from, date_to)

    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Date", "Project", "Task", "Hours", "Billable", "Approved",
        "Hourly Rate", "Cost", "Description"
    ])

    for imp in imputations:
        writer.writerow([
            imp.date,
            imp.project.name if imp.project else "",
            # Auditoria 2026-08: aqui habia `imp.task.name`, y `Task` no tiene
            # esa columna — se llama `title`. Reventaba con `AttributeError`,
            # asi que **el export de imputaciones a CSV fallaba** en cuanto una
            # imputacion tenia tarea asociada (que es el caso normal).
            #
            # Este no lo encuentra `audit_instance_attrs.py`: `imp` viene de una
            # llamada a un servicio, y ahi el detector no infiere el tipo. Es
            # exactamente el limite que su cabecera declara, y salio al mirar
            # este endpoint por otra razon.
            imp.task.title if imp.task else "",
            imp.hours,
            "Yes" if imp.is_billable else "No",
            "Yes" if imp.is_approved else "No",
            imp.hourly_rate_snapshot or "",
            imp.cost_amount or "",
            imp.description or "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=imputations.csv"},
    )


@router.get("/exports/projects-csv", summary="Export projects to CSV")
def export_projects_csv(
    include_costs: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """Auditoria 2026-08 (hallazgo 37): este export **no existia**.

    `ExportsPage` tiene un boton «descargar proyectos» que llamaba a
    `POST /integrations/export/projects`, una ruta que no esta en ningun router.
    El export de *recursos* que si existe no sirve: exporta instantaneas de
    utilizacion por persona y semana, no proyectos.

    El ambito sale de `scope_projects_query`, el mismo que usa el listado de
    proyectos, asi que aqui no se inventa una consulta: un gestor exporta lo que
    ya puede ver en pantalla. La consulta vive en
    `project_service.proyectos_para_exportar` y no aqui, porque la primera
    version la escribio en linea y **el guardian del hallazgo 22 la cazó**.

    `include_costs` sale del formulario de esa pantalla. Los importes son datos
    sensibles, asi que **es opcional y por defecto no van**.
    """
    from app.services.project_service import proyectos_para_exportar

    proyectos = proyectos_para_exportar(db, current_user)

    cabecera = [
        "Code", "Name", "Client", "Type", "Status",
        "Start", "Planned End", "PM",
    ]
    if include_costs:
        cabecera += ["Budget", "Contract Amount", "Currency"]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(cabecera)

    for p in proyectos:
        fila = [
            p.code,
            p.name,
            p.client_name or "",
            str(getattr(p, "project_type", "") or ""),
            str(getattr(p, "status", "") or ""),
            p.start_date or "",
            p.end_date_planned or "",
            p.project_manager.full_name if p.project_manager else "",
        ]
        if include_costs:
            fila += [
                p.budget_amount if p.budget_amount is not None else "",
                p.contract_amount if p.contract_amount is not None else "",
                p.currency or "",
            ]
        writer.writerow(fila)

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=projects.csv"},
    )


@router.get("/exports/resources-csv", summary="Export resource data to CSV")
def export_resources_csv(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """Export resource utilization data to CSV."""
    snapshots = analytics_service.get_all_resource_snapshots(db)

    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "User", "Week", "Planned Hours", "Actual Hours", "Billable Hours",
        "Utilization %", "Billable %"
    ])

    for snapshot in snapshots:
        writer.writerow([
            snapshot.user.full_name if snapshot.user else "",
            snapshot.week_iso,
            snapshot.planned_hours,
            snapshot.actual_hours,
            snapshot.billable_hours,
            snapshot.utilization_pct or "",
            snapshot.billable_pct or "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=resources.csv"},
    )


# ── BI Storytelling / Ask-the-Data / OLAP ───────────────────────────────────
# NOTE: /narrative, /ask and /olap/* live in analytics.py (canonical). They were
# duplicated here historically; removed to avoid duplicate route registration.
