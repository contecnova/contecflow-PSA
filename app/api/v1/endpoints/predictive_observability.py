"""Predictive Model Observability endpoints.

Expose evaluation health and retraining metadata for ITSM and BI predictive models.
Admin-only — returns per-org state from AppSetting store.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.responses import APIResponse
from app.db.session import get_db
from app.models.user import User, UserRole
from app.services.predictive_retraining_service import (
    ITSM_META_KEY,
    BI_META_KEY,
    LAST_EVAL_KEY,
    _get_json,
    evaluate_itsm_model_health,
    evaluate_bi_model_health,
    run_periodic_evaluation_and_retraining,
)

router = APIRouter()

_STATUS_RANK = {
    "healthy": 0,
    "attention": 1,
    "insufficient_data": 2,
}


def _require_admin(current_user: User = Depends(get_current_user)) -> User:
    if getattr(current_user, "role", None) != UserRole.admin:
        raise HTTPException(status_code=403, detail="admin_required")
    return current_user


def _resolve_org_id(current_user: User, override: Optional[str], db: Session) -> Optional[str]:
    """Resolve effective org_id: superadmin can override, others stuck a su propia org.

    - Sin override: usa la org del usuario.
    - Con override: solo superadmin puede usarlo, y debe corresponder a una
      organización existente. Cualquier otro caso → 403.
    """
    user_org = getattr(current_user, "organization_id", None)
    if override is None:
        return user_org
    is_superadmin = bool(getattr(current_user, "is_superadmin", False))
    if not is_superadmin and override != user_org:
        raise HTTPException(status_code=403, detail="cross_org_access_denied")
    # Validar que la organización existe para evitar enumeración de IDs.
    # `Organization` vive en `app.models.mfa`, no en `enterprise`. Con la ruta
    # mal, esta comprobacion —que existe para evitar enumeracion de IDs—
    # lanzaba ImportError en vez de validar. Auditoria 2026-08.
    from app.core.tenancy import organizacion_existe

    if not organizacion_existe(db, override):
        raise HTTPException(status_code=404, detail="organization_not_found")
    return override


def _ultima_evaluacion_para(resumen: dict, current_user: User, org_id: Optional[str]) -> dict:
    """El resumen del ultimo ciclo tal como lo puede ver quien pregunta.

    Revision multitenant 2026-11b: el resumen es una fila GLOBAL con el
    resultado de CADA empresa (id, muestras, error, acierto) y cuantas empresas
    hay. Un administrador de empresa veia los de todas; ahora solo el suyo.
    """
    if getattr(current_user, "is_superadmin", False) or not isinstance(resumen, dict):
        return resumen
    propios = [r for r in resumen.get("results") or []
               if isinstance(r, dict) and org_id and r.get("organization_id") == org_id]
    salida = {k: v for k, v in resumen.items() if k == "evaluated_at"}
    salida["results"] = propios
    if propios:
        salida["itsm_retrained"] = sum(1 for r in propios if (r.get("itsm") or {}).get("triggered"))
        salida["bi_retrained"] = sum(1 for r in propios if (r.get("bi") or {}).get("triggered"))
    return salida


@router.get(
    "/bi/predictive/observability/status",
    summary="Estado de salud de los modelos predictivos (ITSM + BI)",
    tags=["Predictive Observability"],
)
def predictive_observability_status(
    organization_id: Optional[str] = Query(None, description="Filtrar por organización (admin override — sólo superadmin)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_admin),
):
    """Return the latest evaluation cycle summary plus per-org retraining metadata.

    - `last_eval`: last `run_periodic_evaluation_and_retraining` execution summary.
    - `itsm_meta`: ITSM model retraining state for the org.
    - `bi_meta`: BI model retraining state for the org.
    """
    org_id: Optional[str] = _resolve_org_id(current_user, organization_id, db)

    last_eval = _ultima_evaluacion_para(_get_json(db, LAST_EVAL_KEY, None, default={}), current_user, org_id)
    itsm_meta = _get_json(db, ITSM_META_KEY, org_id, default={})
    bi_meta = _get_json(db, BI_META_KEY, org_id, default={})

    return APIResponse.ok(data={
        "organization_id": org_id,
        "last_eval": last_eval,
        "itsm_meta": itsm_meta,
        "bi_meta": bi_meta,
    })


@router.get(
    "/bi/predictive/observability/health",
    summary="Evaluación de salud en tiempo real de los modelos predictivos",
    tags=["Predictive Observability"],
)
def predictive_observability_health(
    organization_id: Optional[str] = Query(None, description="Override sólo permitido para superadmin"),
    lookback_days: int = Query(30, ge=1, le=180),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_admin),
):
    """Run and return a fresh health evaluation (read-only, no retraining)."""
    org_id: Optional[str] = _resolve_org_id(current_user, organization_id, db)

    itsm_eval = evaluate_itsm_model_health(db, organization_id=org_id, lookback_days=lookback_days)
    bi_eval = evaluate_bi_model_health(db, organization_id=org_id)

    overall_score = round((itsm_eval.get("score", 0) + bi_eval.get("score", 0)) / 2, 4)
    statuses = [str(itsm_eval.get("status", "healthy")), str(bi_eval.get("status", "healthy"))]
    overall_status = max(statuses, key=lambda s: _STATUS_RANK.get(s, 0))

    return APIResponse.ok(data={
        "organization_id": org_id,
        "overall_score": overall_score,
        "overall_status": overall_status,
        "status_rank": _STATUS_RANK,
        "itsm": itsm_eval,
        "bi": bi_eval,
    })


@router.post(
    "/bi/predictive/observability/trigger-retrain",
    summary="Forzar ciclo de evaluación y retraining (admin)",
    tags=["Predictive Observability"],
)
def predictive_trigger_retrain(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_admin),
):
    """Manually trigger the full evaluation + conditional retraining cycle.

    Uses the same logic as the Celery beat task but executed synchronously.

    Revision multitenant 2026-11b: el administrador de una empresa evalua solo
    la suya y no reescribe el resumen global de la plataforma (antes recorria
    las empresas de los usuarios que ve —con pertenencias, tambien otras— y
    machacaba `LAST_EVAL_KEY` con su resultado).
    """
    if not getattr(current_user, "is_superadmin", False):
        from app.services.predictive_retraining_service import evaluar_y_reentrenar_organizacion
        result = evaluar_y_reentrenar_organizacion(db, getattr(current_user, "organization_id", None))
        db.commit()
        return APIResponse.ok(data=result)
    result = run_periodic_evaluation_and_retraining(db)
    return APIResponse.ok(data=result)
