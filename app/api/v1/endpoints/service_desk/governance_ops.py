"""Service Desk governance operations: AI eval/drift and quality contract.

Auditoria 2026-08 (hallazgo 22). Las consultas de este fichero estan en
`services/service_desk/governance_compliance_service.py`, y dos de ellas
filtraban asi:

    q = db.query(SDAIEvaluationRun)
    if org_id:
        q = q.filter(SDAIEvaluationRun.organization_id == org_id)

Con un sujeto **sin** organizacion eso no lista «los que no tienen
organizacion»: lista los de TODOS los clientes. Es el mismo condicional que
aparecio en el resumen de costes de usuario, y la correccion es la misma: el
filtro no es condicional.

Los umbrales del semaforo de deriva (70 y 40) tambien estaban en duro aqui y
ahora se declaran con nombre en el servicio.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_any_manager
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.user import User
from app.services.service_desk import governance_compliance_service as svc
from app.core.constantes import MAX_TAMANO_DE_PAGINA

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


@router.get("/governance/ai/evaluations", summary="Listar evaluaciones offline de IA Service Desk")
def list_ai_evaluations(
    limit: int = Query(50, ge=1, le=MAX_TAMANO_DE_PAGINA),
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    items = svc.listar_evaluaciones(db, current_user, limit=limit)
    return APIListResponse.ok(items=[
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
    ])


@router.post("/governance/ai/evaluations", summary="Registrar evaluación offline de IA")
def create_ai_evaluation(
    payload: EvalRunIn,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    row = svc.registrar_evaluacion(db, current_user, {
        "model_name": payload.model_name,
        "task_type": payload.task_type,
        "dataset_name": payload.dataset_name,
        "score": payload.score,
        "metrics": payload.metrics,
        "notes": payload.notes,
    })
    return APIResponse.ok(data={"ok": True, "id": row.id})


@router.get("/governance/ai/drift", summary="Listar snapshots de deriva por tenant")
def list_ai_drift(
    model_name: str | None = Query(None),
    limit: int = Query(50, ge=1, le=MAX_TAMANO_DE_PAGINA),
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    items = svc.listar_deriva(
        db, current_user, model_name=model_name, limit=limit)
    return APIListResponse.ok(items=[
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
    ])


@router.post("/governance/ai/drift", summary="Registrar snapshot de deriva")
def create_ai_drift_snapshot(
    payload: DriftSnapshotIn,
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    row = svc.registrar_deriva(db, current_user, {
        "model_name": payload.model_name,
        "feature_set": payload.feature_set,
        "drift_score": payload.drift_score,
        "details": payload.details,
    })
    return APIResponse.ok(data={"ok": True, "id": row.id, "status": row.status})


@router.get("/governance/metrics/catalog", summary="Catálogo estándar de métricas operativas")
def get_metrics_catalog(current_user: User = Depends(get_current_user)):
    return APIListResponse.ok(items=_DEFAULT_METRIC_CATALOG)


@router.get("/governance/quality-contract", summary="Contrato de calidad por release")
def get_quality_contract(
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=svc.contrato_de_calidad(db, current_user))


@router.put("/governance/quality-contract", summary="Actualizar contrato de calidad por release")
def put_quality_contract(
    payload: dict = Body(...),
    db: Session = Depends(get_db), current_user: User = Depends(require_any_manager),
):
    svc.guardar_contrato_de_calidad(db, current_user, payload)
    return APIResponse.ok(data={"ok": True})
