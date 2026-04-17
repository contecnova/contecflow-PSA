from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin
from app.models.user import User
from app.core.config import settings
from app.api.v1.endpoints import profitability as profitability_v1

router = APIRouter(prefix="/profitability", tags=["Rentabilidad v2"])


@router.get(
    "/summary",
    summary="Rentabilidad de portfolio (v2)",
    description=(
        "Devuelve el mismo cálculo de rentabilidad que v1. "
        "Los costes internos están normalizados a `base_currency` mediante tipos de cambio históricos. "
        "Los ingresos de facturación se expresan en la divisa del proyecto y NO están convertidos a `base_currency`."
    ),
)
def get_profitability_summary_v2(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    data = profitability_v1.get_profitability_summary(
        status=status,
        db=db,
        current_user=current_user,
    )
    return {
        "api_version": "v2",
        "base_currency": settings.DEFAULT_CURRENCY,
        "projects": data.get("projects", []),
        "portfolio": data.get("portfolio", {}),
    }


@router.get(
    "/{project_id}",
    summary="Rentabilidad detallada de proyecto (v2)",
    description=(
        "Devuelve el mismo cálculo de rentabilidad que v1. "
        "Los costes internos están normalizados a `base_currency` mediante tipos de cambio históricos. "
        "Los ingresos de facturación se expresan en la divisa del proyecto y NO están convertidos a `base_currency`."
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
    data["api_version"] = "v2"
    data["base_currency"] = settings.DEFAULT_CURRENCY
    return data
