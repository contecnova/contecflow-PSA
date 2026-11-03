from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin_or_pm
from app.models.user import User
from app.core.config import settings
from app.api.v1.endpoints import profitability as profitability_v1
from app.services.profitability_service import get_fx_rate
from app.core import timeutil

router = APIRouter(prefix="/profitability", tags=["Rentabilidad v2"])


def _normalize_project_revenues(projects: list, db: Session, org_currency: str) -> list:
    """Convert billing_revenue (and derived margin fields) to org base currency for each project."""
    fx_cache: dict = {}
    today = timeutil.today()
    for proj in projects:
        project_currency = proj.get("project_currency") or org_currency
        if project_currency == org_currency:
            continue
        billing_rev = proj.get("billing_revenue") or 0
        if not billing_rev:
            continue
        fx = get_fx_rate(db, project_currency, org_currency, today, _cache=fx_cache)
        proj["billing_revenue"] = round(billing_rev * fx, 2)
        gross_margin = proj["billing_revenue"] - (proj.get("internal_cost") or 0)
        proj["gross_margin"] = round(gross_margin, 2)
        proj["margin_pct"] = (
            round(gross_margin / proj["billing_revenue"] * 100, 1)
            if proj["billing_revenue"] > 0
            else 0
        )
    return projects


@router.get(
    "/summary",
    summary="Rentabilidad de portfolio (v2)",
    description=(
        "Costes internos y revenues de facturación normalizados a `base_currency` "
        "mediante tipos de cambio históricos. El margen bruto es comparable entre "
        "proyectos con divisas distintas."
    ),
)
def get_profitability_summary_v2(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_pm),
    response: Response = None,
):
    _resp = profitability_v1.get_profitability_summary(
        status=status,
        db=db,
        current_user=current_user,
    )
    # v1 ahora devuelve el envelope canónico APIResponse; desenvolvemos el payload.
    data = _resp.data if hasattr(_resp, "data") else _resp
    org_currency = settings.DEFAULT_CURRENCY
    projects = _normalize_project_revenues(data.get("projects", []), db, org_currency)

    # Recompute portfolio totals after revenue normalisation
    total_revenue = sum(p.get("billing_revenue") or 0 for p in projects)
    total_cost = sum(p.get("internal_cost") or 0 for p in projects)
    total_margin = total_revenue - total_cost

    if response is not None:
        response.headers["x-api-version"] = "2"

    return {
        "api_version": "v2",
        "base_currency": org_currency,
        "revenue_normalized": True,
        "projects": sorted(projects, key=lambda x: x.get("gross_margin") or 0),
        "portfolio": {
            "total_revenue": round(total_revenue, 2),
            "total_cost": round(total_cost, 2),
            "total_margin": round(total_margin, 2),
            "margin_pct": round(total_margin / total_revenue * 100, 1) if total_revenue > 0 else 0,
            "project_count": len(projects),
            "billable_projects": sum(1 for p in projects if p.get("is_billable")),
        },
    }


@router.get(
    "/{project_id}",
    summary="Rentabilidad detallada de proyecto (v2)",
    description=(
        "Costes internos y revenue normalizado a `base_currency`. "
        "El margen bruto refleja la rentabilidad real sin mezcla de divisas."
    ),
)
def get_project_profitability_v2(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = profitability_v1.get_project_profitability(
        project_id=project_id,
        db=db,
        current_user=current_user,
    )
    org_currency = settings.DEFAULT_CURRENCY
    project_currency = data.get("project_currency") or org_currency
    if project_currency != org_currency:
        billing_rev = data.get("billing_revenue") or 0
        if billing_rev:
            fx = get_fx_rate(db, project_currency, org_currency, timeutil.today())
            data["billing_revenue"] = round(billing_rev * fx, 2)
            gross_margin = data["billing_revenue"] - (data.get("internal_cost") or 0)
            data["gross_margin"] = round(gross_margin, 2)
            data["margin_pct"] = (
                round(gross_margin / data["billing_revenue"] * 100, 1)
                if data["billing_revenue"] > 0
                else 0
            )
    data["api_version"] = "v2"
    data["base_currency"] = org_currency
    data["revenue_normalized"] = True
    return data
