"""Service Desk governance operations: AI eval/drift and quality contract."""
from __future__ import annotations

import json

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_any_manager
from app.db.session import get_db
from app.models.service_desk_ai_governance import SDAIEvaluationRun, SDAIDriftSnapshot
from app.models.settings import AppSetting
from app.models.user import User

router = APIRouter()


_DEFAULT_METRIC_CATALOG = [
    {"id": "mttr_minutes", "name": "MTTR", "domain": "service_desk"},
    {"id": "sla_compliance_pct", "name": "SLA Compliance %", "domain": "service_desk"},
    {"id": "fcr_pct", "name": "First Contact Resolution %", "domain": "service_desk"},
    {"id": "csat_avg", "name": "CSAT promedio", "domain": "service_desk"},
    {"id": "queue_risk_index", "name": "Índice de riesgo de cola", "domain": "service_desk"},
]


class EvalRunIn(BaseModel):
    model_name: str
    task_type: str
    dataset_name: str | None = None
    score: str | None = None
    metrics: dict | None = None
    notes: str | None = None


class DriftSnapshotIn(BaseModel):
    model_name: str
    feature_set: str = "default"
    drift_score: int
    details: dict | None = None


def _quality_key() -> str:
    return "service_desk.quality_contract.v1"


@router.get("/governance/ai/evaluations", summary="Listar evaluaciones offline de IA Service Desk")
def list_ai_evaluations(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    org_id = getattr(current_user, "organization_id", None)
    q = db.query(SDAIEvaluationRun)
    if org_id:
        q = q.filter(SDAIEvaluationRun.organization_id == org_id)
    items = q.order_by(SDAIEvaluationRun.created_at.desc()).limit(limit).all()
    return [
        {
            "id": x.id,
            "model_name": x.model_name,
            "task_type": x.task_type,
            "dataset_name": x.dataset_name,
            "status": x.status,
            "score": x.score,
            "metrics": json.loads(x.metrics_json or "{}"),
            "created_at": x.created_at,
        }
        for x in items
    ]


@router.post("/governance/ai/evaluations", summary="Registrar evaluación offline de IA")
def create_ai_evaluation(
    payload: EvalRunIn,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    org_id = getattr(current_user, "organization_id", None)
    row = SDAIEvaluationRun(
        organization_id=org_id,
        model_name=payload.model_name,
        task_type=payload.task_type,
        dataset_name=payload.dataset_name,
        score=payload.score,
        metrics_json=json.dumps(payload.metrics or {}),
        notes=payload.notes,
        created_by_user_id=current_user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"ok": True, "id": row.id}


@router.get("/governance/ai/drift", summary="Listar snapshots de deriva por tenant")
def list_ai_drift(
    model_name: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    org_id = getattr(current_user, "organization_id", None)
    q = db.query(SDAIDriftSnapshot)
    if org_id:
        q = q.filter(SDAIDriftSnapshot.organization_id == org_id)
    if model_name:
        q = q.filter(SDAIDriftSnapshot.model_name == model_name)
    items = q.order_by(SDAIDriftSnapshot.measured_at.desc()).limit(limit).all()
    return [
        {
            "id": x.id,
            "model_name": x.model_name,
            "feature_set": x.feature_set,
            "drift_score": x.drift_score,
            "status": x.status,
            "details": json.loads(x.details_json or "{}"),
            "measured_at": x.measured_at,
        }
        for x in items
    ]


@router.post("/governance/ai/drift", summary="Registrar snapshot de deriva")
def create_ai_drift_snapshot(
    payload: DriftSnapshotIn,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    org_id = getattr(current_user, "organization_id", None)
    status = "ok"
    if payload.drift_score >= 70:
        status = "critical"
    elif payload.drift_score >= 40:
        status = "warning"

    row = SDAIDriftSnapshot(
        organization_id=org_id,
        model_name=payload.model_name,
        feature_set=payload.feature_set,
        drift_score=payload.drift_score,
        status=status,
        details_json=json.dumps(payload.details or {}),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"ok": True, "id": row.id, "status": status}


@router.get("/governance/metrics/catalog", summary="Catálogo estándar de métricas operativas")
def get_metrics_catalog(current_user: User = Depends(get_current_user)):
    return {"items": _DEFAULT_METRIC_CATALOG}


@router.get("/governance/quality-contract", summary="Contrato de calidad por release")
def get_quality_contract(
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    org_id = getattr(current_user, "organization_id", None)
    row = db.query(AppSetting).filter(AppSetting.organization_id == org_id, AppSetting.key == _quality_key()).first()
    if not row or not row.value:
        return {
            "minimum_tests_pass_rate": 0.98,
            "max_p1_open": 0,
            "max_regression_bugs": 3,
            "required_checks": ["unit", "integration", "e2e_critical", "security_scan"],
        }
    try:
        return json.loads(row.value)
    except Exception:
        return {"raw": row.value}


@router.put("/governance/quality-contract", summary="Actualizar contrato de calidad por release")
def put_quality_contract(
    payload: dict = Body(...),
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    org_id = getattr(current_user, "organization_id", None)
    row = db.query(AppSetting).filter(AppSetting.organization_id == org_id, AppSetting.key == _quality_key()).first()
    if not row:
        row = AppSetting(
            organization_id=org_id,
            key=_quality_key(),
            value=json.dumps(payload),
            description="Service Desk quality contract",
        )
        db.add(row)
    else:
        row.value = json.dumps(payload)
    db.commit()
    return {"ok": True}
