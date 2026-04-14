"""
Additional Analytics and Export Endpoints.
Statistics, summaries, and bulk downloads.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional, Dict
import logging
import csv
import io
from fastapi.responses import StreamingResponse

from app.core.deps import get_db, get_current_user, require_any_manager
from app.models.user import User
from app.models.imputation import Imputation
from app.models.documents import Document
from app.models.resources import ResourceUtilizationSnapshot
from pydantic import BaseModel

router = APIRouter(prefix="/analytics", tags=["analytics"])
logger = logging.getLogger(__name__)


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

@router.get("/imputations", response_model=ImputationStats, summary="Get imputation statistics")
def get_imputation_analytics(
    user_id: Optional[str] = None,
    period: str = Query("monthly", pattern="^(daily|weekly|monthly)$"),
    days_back: int = Query(90, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get imputation analytics for user or team."""
    # Permission: employees see only their own, managers see their projects, admins see all
    query_user_id = user_id if user_id and current_user.role.value in ["admin", "pm"] else current_user.id

    cutoff_date = date.today() - timedelta(days=days_back)

    imputations = db.query(Imputation).filter(
        and_(
            Imputation.user_id == query_user_id,
            Imputation.date >= cutoff_date,
        )
    ).all()

    if not imputations:
        return ImputationStats(
            period=period,
            avg_hours_per_day=0,
            avg_billable_pct=0,
            total_cost=0,
            daily=[],
            weekly=[],
            monthly=[],
        )

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

    return ImputationStats(
        period=period,
        avg_hours_per_day=round(avg_hours_per_day, 2),
        avg_billable_pct=round(avg_billable_pct, 1),
        total_cost=round(total_cost, 2),
        daily=daily,
        weekly=weekly,
        monthly=monthly,
    )


# ── Document Analytics ─────────────────────────────────────────────────────

@router.get("/documents", response_model=DocumentStats, summary="Get document statistics")
def get_document_analytics(
    days_back: int = Query(90, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """Get document management statistics."""
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)

    docs = db.query(Document).filter(
        Document.created_at >= cutoff_date,
        Document.is_archived == False,
    ).all()

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

    return DocumentStats(
        total_documents=len(docs),
        by_category=category_counts,
        by_status=status_counts,
        avg_versions_per_document=round(avg_versions, 2),
        total_storage_mb=round(total_size_mb, 2),
    )


# ── Advanced Resource Forecast ─────────────────────────────────────────────

@router.get("/resources/forecast-advanced", response_model=List[ResourceForecast], summary="Advanced resource forecast")
def get_advanced_forecast(
    weeks_ahead: int = Query(12, ge=1, le=52),
    include_risk_assessment: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """Get advanced forecast with risk assessment."""
    users = db.query(User).filter(User.is_active == True).all()
    forecasts = []

    for user in users:
        # Get snapshots for next N weeks
        snapshots = db.query(ResourceUtilizationSnapshot).filter(
            ResourceUtilizationSnapshot.user_id == user.id,
        ).order_by(ResourceUtilizationSnapshot.week_iso).limit(weeks_ahead).all()

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

    return sorted(forecasts, key=lambda x: x.avg_load_pct, reverse=True)


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
    query_user_id = user_id if user_id and current_user.role.value in ["admin"] else current_user.id

    q = db.query(Imputation).filter(Imputation.user_id == query_user_id)
    if date_from:
        q = q.filter(Imputation.date >= date_from)
    if date_to:
        q = q.filter(Imputation.date <= date_to)

    imputations = q.order_by(Imputation.date.desc()).all()

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
            imp.task.name if imp.task else "",
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


@router.get("/exports/resources-csv", summary="Export resource data to CSV")
def export_resources_csv(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    """Export resource utilization data to CSV."""
    snapshots = db.query(ResourceUtilizationSnapshot).order_by(
        ResourceUtilizationSnapshot.week_iso.desc()
    ).all()

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
