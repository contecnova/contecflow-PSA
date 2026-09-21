"""
bi_conditional_delivery.py — Conditional report delivery endpoints.

Routes:
  GET  /bi/delivery/rules              — list conditional delivery rules
  POST /bi/delivery/rules              — create a new rule
  PATCH /bi/delivery/rules/{id}        — update a rule
  POST /bi/delivery/rules/{id}/evaluate — evaluate if rule should trigger
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.abac_enforce import enforce_abac
from app.core.deps import get_current_user, require_internal_user
from app.core.ratelimit import limiter
from app.core.responses import APIResponse
from app.db.session import get_db
from app.models.user import User
from app.services import bi_conditional_delivery_service as svc

router = APIRouter()


class DeliveryRuleIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    report_id: str
    condition_type: Optional[str] = None
    condition_metric: Optional[str] = None
    condition_operator: Optional[str] = Field(None, pattern="^(gt|gte|lt|lte|eq)$")
    condition_value: Optional[float] = None
    threshold_pct: Optional[float] = Field(None, ge=0, le=100)
    diff_threshold_pct: float = Field(5.0, ge=0, le=100)
    recipients: list[str] = Field(default_factory=list)
    schedule: Optional[str] = None
    schedule_cron: str = Field("0 8 * * 1", description="Cron expression")
    enabled: bool = True


class DeliveryRulePatchIn(BaseModel):
    name: Optional[str] = None
    enabled: Optional[bool] = None
    condition_metric: Optional[str] = None
    condition_operator: Optional[str] = None
    condition_value: Optional[float] = None
    diff_threshold_pct: Optional[float] = Field(None, ge=0, le=100)
    recipients: Optional[list[str]] = None
    schedule_cron: Optional[str] = None


class EvaluateRuleIn(BaseModel):
    current_data: Any = Field(default_factory=dict)
    current_metric_value: Optional[float] = None


@router.get("/bi/delivery/rules", summary="Listar reglas de entrega condicional")
@limiter.limit("60/minute")
def list_rules(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    items = svc.list_rules(db, org_id=org_id)
    return APIResponse.ok(data={"items": items, "count": len(items)})


@router.post("/bi/delivery/rules", summary="Crear regla de entrega condicional", status_code=201)
@limiter.limit("20/minute")
def create_rule(
    request: Request,
    body: DeliveryRuleIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: dominio: analitica interna
):
    org_id = getattr(current_user, "organization_id", None)
    diff_threshold_pct = body.diff_threshold_pct
    if body.threshold_pct is not None:
        diff_threshold_pct = body.threshold_pct

    condition_operator = body.condition_operator
    condition_value = body.condition_value
    if body.condition_type == "always":
        condition_operator = None
        condition_value = None

    return APIResponse.ok(data=svc.create_rule(
        db,
        org_id=org_id,
        name=body.name,
        report_id=body.report_id,
        condition_metric=body.condition_metric,
        condition_operator=condition_operator,
        condition_value=condition_value,
        diff_threshold_pct=diff_threshold_pct,
        recipients=body.recipients,
        schedule_cron=body.schedule or body.schedule_cron,
        enabled=body.enabled,
        created_by=current_user.id,
    ))


@router.patch("/bi/delivery/rules/{rule_id}", summary="Actualizar regla de entrega")
@limiter.limit("20/minute")
def update_rule(
    request: Request,
    rule_id: str,
    body: DeliveryRulePatchIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: dominio: analitica interna
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        return APIResponse.ok(data=svc.update_rule(db, org_id=org_id, rule_id=rule_id, updates=body.model_dump(exclude_none=True)))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/bi/delivery/rules/{rule_id}", summary="Eliminar regla de entrega", status_code=204)
@limiter.limit("20/minute")
def delete_rule(
    request: Request,
    rule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: dominio: analitica interna
):
    enforce_abac(db, current_user, "bi_delivery_rule", rule_id, action="delete")
    org_id = getattr(current_user, "organization_id", None)
    try:
        svc.delete_rule(db, org_id=org_id, rule_id=rule_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/bi/delivery/rules/{rule_id}/evaluate", summary="Evaluar si la regla debe dispararse")
@limiter.limit("20/minute")
def evaluate_rule(
    request: Request,
    rule_id: str,
    body: Optional[EvaluateRuleIn] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: dominio: analitica interna
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        payload = body or EvaluateRuleIn()
        return APIResponse.ok(data=svc.evaluate_rule(
            db,
            org_id=org_id,
            rule_id=rule_id,
            current_data=payload.current_data,
            current_metric_value=payload.current_metric_value,
        ))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
