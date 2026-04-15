from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin
from app.models.user import User
from app.api.v1.endpoints import profitability as profitability_v1

router = APIRouter(prefix="/profitability", tags=["Rentabilidad v2"])


@router.get("/summary", summary="Rentabilidad de portfolio (v2)")
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
        "currency_normalized": True,
        "projects": data.get("projects", []),
        "portfolio": data.get("portfolio", {}),
    }


@router.get("/{project_id}", summary="Rentabilidad detallada de proyecto (v2)")
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
    data["currency_normalized"] = True
    return data
