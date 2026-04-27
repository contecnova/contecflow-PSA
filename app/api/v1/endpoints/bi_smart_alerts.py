"""BI Smart Alerts endpoints.

Alert rule management and evaluation engine for BI dashboards.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services import bi_smart_alerts_service as svc

router = APIRouter()


class AlertRuleIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    metric_key: str = Field(..., min_length=1, max_length=80)
    condition: str = Field(..., min_length=1, max_length=40)
    threshold: Optional[float] = None
    trend_periods: int = Field(3, ge=2, le=24)
    severity: str = Field("warning", pattern="^(info|warning|critical)$")
    cooldown_minutes: int = Field(60, ge=5, le=10080)
    enabled: bool = True
    correlated_metrics: list[str] = Field(default_factory=list)
    notification_channels: list[str] = Field(default_factory=lambda: ["ui"])


class AlertRulePatchIn(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=200)
    threshold: Optional[float] = None
    trend_periods: Optional[int] = Field(None, ge=2, le=24)
    severity: Optional[str] = None
    cooldown_minutes: Optional[int] = Field(None, ge=5, le=10080)
    enabled: Optional[bool] = None
    correlated_metrics: Optional[list[str]] = None
    notification_channels: Optional[list[str]] = None


@router.get("/bi/alerts/supported-metrics", summary="Métricas soportadas por el motor de alertas")
def get_supported_metrics(
    current_user: User = Depends(get_current_user),
):
    return {
        "metrics": [
            {"key": k, "label": v}
            for k, v in svc.SUPPORTED_METRICS.items()
        ],
        "conditions": svc.SUPPORTED_CONDITIONS,
    }


@router.get("/bi/alerts/rules", summary="Listar reglas de alertas BI")
def list_alert_rules(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    rules = svc.list_alert_rules(db, organization_id=org_id)
    return {"items": rules, "count": len(rules)}


@router.post("/bi/alerts/rules", summary="Crear nueva regla de alerta BI", status_code=201)
def create_alert_rule(
    body: AlertRuleIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        rule = svc.create_alert_rule(
            db,
            organization_id=org_id,
            payload=body.model_dump(),
            current_user=current_user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return rule


@router.patch("/bi/alerts/rules/{rule_id}", summary="Actualizar regla de alerta BI")
def update_alert_rule(
    rule_id: str,
    body: AlertRulePatchIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        rule = svc.update_alert_rule(
            db,
            organization_id=org_id,
            rule_id=rule_id,
            payload=body.model_dump(exclude_none=True),
        )
    except ValueError as exc:
        code = 404 if str(exc) == "rule_not_found" else 422
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return rule


@router.delete("/bi/alerts/rules/{rule_id}", summary="Eliminar regla de alerta BI", status_code=204)
def delete_alert_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    deleted = svc.delete_alert_rule(db, organization_id=org_id, rule_id=rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="rule_not_found")


@router.post("/bi/alerts/evaluate", summary="Evaluar todas las reglas de alerta activas")
def evaluate_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return svc.evaluate_alerts(db, organization_id=org_id)


@router.get("/bi/alerts/history", summary="Historial de alertas BI disparadas")
def get_alert_history(
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    log = svc.get_alert_log(db, organization_id=org_id, limit=limit)
    return {"items": log, "count": len(log)}


@router.post("/bi/alerts/history/{alert_id}/acknowledge", summary="Marcar alerta como reconocida")
def acknowledge_alert(
    alert_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        entry = svc.acknowledge_alert(
            db,
            organization_id=org_id,
            alert_id=alert_id,
            current_user=current_user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return entry


@router.post("/bi/alerts/seed-defaults", summary="Inicializar reglas de alerta por defecto")
def seed_default_rules(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    svc.seed_default_rules_if_empty(db, organization_id=org_id)
    return {"ok": True}
