"""BI Collaboration endpoints.

Collaboration and governance APIs for BI dashboards.
Designed as an orchestration layer over app.services.bi_collaboration_service.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services import bi_collaboration_service as svc

router = APIRouter()


class CommentCreateIn(BaseModel):
    dashboard_key: str = Field(..., min_length=1, max_length=120)
    widget_id: str = Field(..., min_length=1, max_length=120)
    message: str = Field(..., min_length=2, max_length=4000)


class GovernanceRulesPatchIn(BaseModel):
    olap_max_staleness_hours: Optional[float] = Field(None, ge=1, le=240)
    max_error_reports: Optional[int] = Field(None, ge=0, le=100)
    require_active_schedules: Optional[bool] = None


@router.get("/bi/collaboration/comments", summary="Listar comentarios BI por dashboard/widget")
def list_bi_comments(
    dashboard_key: Optional[str] = Query(None),
    widget_id: Optional[str] = Query(None),
    include_resolved: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return {
        "items": svc.list_comments(
            db,
            organization_id=org_id,
            dashboard_key=dashboard_key,
            widget_id=widget_id,
            include_resolved=include_resolved,
        )
    }


@router.post("/bi/collaboration/comments", summary="Crear comentario BI")
def create_bi_comment(
    payload: CommentCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    comment = svc.create_comment(
        db,
        organization_id=org_id,
        dashboard_key=payload.dashboard_key,
        widget_id=payload.widget_id,
        message=payload.message,
        author=current_user,
    )
    return {"ok": True, "comment": comment}


@router.patch("/bi/collaboration/comments/{comment_id}/resolve", summary="Marcar comentario BI como resuelto")
def resolve_bi_comment(
    comment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        comment = svc.resolve_comment(
            db,
            organization_id=org_id,
            comment_id=comment_id,
            current_user=current_user,
        )
        return {"ok": True, "comment": comment}
    except ValueError:
        raise HTTPException(status_code=404, detail="Comentario no encontrado")


@router.get("/bi/governance/overview", summary="Overview de governance BI Collaboration")
def governance_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return svc.governance_overview(db, organization_id=org_id)


@router.get("/bi/governance/rules", summary="Leer reglas de governance BI Collaboration")
def governance_rules(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return svc.get_governance_rules(db, organization_id=org_id)


@router.patch("/bi/governance/rules", summary="Actualizar reglas de governance BI Collaboration")
def patch_governance_rules(
    payload: GovernanceRulesPatchIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    return svc.update_governance_rules(db, organization_id=org_id, payload=data)


@router.post("/bi/governance/run-checks", summary="Ejecutar checks de governance BI Collaboration")
def run_governance_checks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return svc.run_governance_checks(db, organization_id=org_id)


@router.get("/bi/governance/last-run", summary="Última ejecución de checks governance BI")
def last_governance_run(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return {"result": svc.get_last_governance_run(db, organization_id=org_id)}
