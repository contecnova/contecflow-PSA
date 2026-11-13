from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.settings import AppSetting
from app.models.service_desk import Ticket, TicketStatus
from app.models.user import User
from app.services import bi_intelligence_service
from app.services.service_desk import predictive_analytics_service
import logging

logger = logging.getLogger(__name__)

ITSM_META_KEY = "predictive.retraining.itsm.meta"
BI_META_KEY = "predictive.retraining.bi.meta"
LAST_EVAL_KEY = "predictive.retraining.last_eval"


def _iso_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _parse_dt(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        logger.warning("No se pudo parsear datetime ISO: %r", raw)
        return None


def _setting_row(db: Session, key: str, organization_id: Optional[str]) -> Optional[AppSetting]:
    q = db.query(AppSetting).filter(AppSetting.key == key)
    if organization_id:
        q = q.filter(AppSetting.organization_id == organization_id)
    else:
        q = q.filter(AppSetting.organization_id.is_(None))
    return q.first()


def _get_json(db: Session, key: str, organization_id: Optional[str], default: dict | None = None) -> dict:
    row = _setting_row(db, key, organization_id)
    if not row or not row.value:
        return default or {}
    try:
        payload = json.loads(row.value)
    except Exception:
        logger.warning("Fallo parseando JSON de AppSetting key=%s; usando default", key)
        return default or {}
    return payload if isinstance(payload, dict) else (default or {})


def _set_json(db: Session, key: str, organization_id: Optional[str], value: dict, description: str) -> None:
    row = _setting_row(db, key, organization_id)
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if not row:
        db.add(AppSetting(key=key, organization_id=organization_id, value=payload, description=description))
    else:
        row.value = payload
        if not row.description:
            row.description = description
    db.flush()


def _org_user_ids(db: Session, organization_id: Optional[str]) -> list[str]:
    if not organization_id:
        return []
    rows = db.query(User.id).filter(User.organization_id == organization_id).all()
    return [str(r[0]) for r in rows]


#: Severidad predicha → palabras que la confirman en la prioridad real. Las
#: prioridades del ticket vienen con nombres distintos según de dónde salgan
#: (`p3_medium`, `normal`), así que se compara por contención y no por
#: igualdad. Auditoría 2026-09 (hallazgo 18): eran cuatro `elif` con la misma
#: forma dentro del bucle.
_SEVERIDAD_ACIERTA_CON: dict[str, tuple[str, ...]] = {
    "critical": ("critical",),
    "high": ("high",),
    "medium": ("medium", "normal"),
    "low": ("low",),
}


def _acierta_la_severidad(predicha: str, prioridad: str) -> bool:
    """Si la severidad predicha se corresponde con la prioridad real."""
    return any(p in prioridad for p in _SEVERIDAD_ACIERTA_CON.get(predicha, ()))


def _medir_predicciones(tickets) -> tuple[int, float, int, int]:
    """Recorre los tickets y devuelve `(evaluados, suma_error, aciertos, total)`.

    Dos medidas independientes sobre el mismo recorrido: el error absoluto del
    tiempo de resolución, y el acierto de la severidad. Un ticket puede
    contribuir a una y no a la otra.
    """
    evaluados = aciertos = total_severidad = 0
    suma_error = 0.0

    for t in tickets:
        previsto = getattr(t, "predicted_resolution_minutes", None)
        real = getattr(t, "resolution_minutes", None)
        # `real > 0` descarta los cerrados al instante, que no miden nada.
        if previsto is not None and real is not None and float(real) > 0:
            suma_error += abs(float(previsto) - float(real))
            evaluados += 1

        severidad = (getattr(t, "predicted_severity", None) or "").lower()
        prioridad = str(
            getattr(getattr(t, "priority", None), "value", getattr(t, "priority", ""))
        ).lower()
        if severidad and prioridad:
            total_severidad += 1
            if _acierta_la_severidad(severidad, prioridad):
                aciertos += 1

    return evaluados, suma_error, aciertos, total_severidad


def _estado_del_modelo(evaluados: int, mae, acierto) -> str:
    """Si el modelo está sano, necesita atención, o no hay datos para decirlo.

    Menos de diez muestras es «no se sabe» disfrazado de «atención»: se dice
    aparte con `insufficient_data` cuando no hay ninguna.
    """
    if evaluados == 0:
        return "insufficient_data"
    if evaluados < 10 or (mae is not None and mae > 360) or (acierto is not None and acierto < 0.45):
        return "attention"
    return "healthy"


def evaluate_itsm_model_health(
    db: Session, *, organization_id: Optional[str], lookback_days: int = 30,
) -> dict[str, Any]:
    """Cómo de bien está acertando el modelo predictivo de ITSM.

    Sólo mira tickets ya cerrados con predicción hecha: son los únicos donde se
    puede comparar lo previsto con lo que pasó.
    """
    corte = datetime.now(tz=timezone.utc) - timedelta(days=max(1, lookback_days))
    q = db.query(Ticket).filter(
        Ticket.status.in_([TicketStatus.resolved.value, TicketStatus.closed.value]),
        Ticket.prediction_generated_at.isnot(None),
        Ticket.prediction_generated_at >= corte,
    )
    usuarios = _org_user_ids(db, organization_id)
    if usuarios:
        q = q.filter(
            Ticket.requester_user_id.in_(usuarios)
            | Ticket.assigned_to_user_id.in_(usuarios)
            | Ticket.created_by_user_id.in_(usuarios)
        )

    tickets = q.all()
    evaluados, suma_error, aciertos, total_severidad = _medir_predicciones(tickets)

    mae = round(suma_error / evaluados, 2) if evaluados else None
    acierto = round(aciertos / total_severidad, 4) if total_severidad else None

    # La puntuación baja con el error —topado en 0,7 para que un error enorme no
    # borre la contribución de la severidad— y con los fallos de severidad.
    puntuacion = 1.0
    if mae is not None:
        puntuacion -= min(0.7, mae / 1200.0)
    if acierto is not None:
        puntuacion -= (1.0 - acierto) * 0.3

    return {
        "model": "itsm_predictive",
        "organization_id": organization_id,
        "lookback_days": lookback_days,
        "samples": len(tickets),
        "evaluated_resolution": evaluados,
        "mae_minutes": mae,
        "severity_accuracy": acierto,
        "score": round(max(0.0, min(1.0, puntuacion)), 4),
        "status": _estado_del_modelo(evaluados, mae, acierto),
        "evaluated_at": _iso_now(),
    }


def evaluate_bi_model_health(db: Session, *, organization_id: Optional[str]) -> dict[str, Any]:
    forecast = bi_intelligence_service.ml_forecast_prophet(
        db,
        organization_id=organization_id,
        metric_key="revenue",
        periods=2,
        frequency="MS",
    )
    overrun = bi_intelligence_service.ml_predict_project_overrun_lgbm(db, organization_id=organization_id)

    forecast_engine = str(forecast.get("engine", "unknown"))
    overrun_engine = str(overrun.get("engine", "unknown"))
    history_months = int(forecast.get("history_months", 0) or 0)

    # Check whether optional ML libraries are installed.
    # A fallback due to a missing library is an infrastructure issue, not a model quality issue.
    # Penalise lightly (-0.10) instead of heavily (-0.35) so the score reflects
    # model quality rather than deployment completeness.
    prophet_available = True
    try:
        import prophet  # noqa: F401
    except (ImportError, OSError):
        prophet_available = False

    lgbm_available = True
    try:
        import lightgbm  # noqa: F401
    except (ImportError, OSError):
        lgbm_available = False

    score = 1.0
    if "fallback" in forecast_engine:
        # Heavy penalty only if Prophet IS installed but still falling back (data problem).
        # Light penalty if it is a pure library-availability issue.
        score -= 0.10 if not prophet_available else 0.35
    if "heuristic" in overrun_engine:
        score -= 0.10 if not lgbm_available else 0.35
    score = round(max(0.0, min(1.0, score)), 4)

    # Forecasting quality is not meaningful with too little history.
    if history_months < 6:
        status = "insufficient_data"
    else:
        status = "healthy" if score >= 0.65 else "attention"

    return {
        "model": "bi_predictive",
        "organization_id": organization_id,
        "forecast_engine": forecast_engine,
        "overrun_engine": overrun_engine,
        "history_months": history_months,
        "forecast_library_available": prophet_available,
        "overrun_library_available": lgbm_available,
        "score": score,
        "status": status,
        "evaluated_at": _iso_now(),
    }


def _should_retrain(meta: dict, evaluation: dict, *, max_age_days: int, attention_status: str = "attention") -> bool:
    last_retrained = _parse_dt(meta.get("last_retrained_at"))
    stale = True
    if last_retrained is not None:
        stale = last_retrained < (datetime.now(tz=timezone.utc) - timedelta(days=max_age_days))
    return stale or evaluation.get("status") == attention_status


def evaluar_y_reentrenar_organizacion(db: Session, org_id) -> dict[str, Any]:
    """Evalua los modelos de una organizacion y reentrena los que lo necesitan.

    Segunda auditoria 2026-11 (#33): el worker la llama una vez por
    organizacion con su contexto de tenant publicado.
    """
    itsm_eval = evaluate_itsm_model_health(db, organization_id=org_id)
    bi_eval = evaluate_bi_model_health(db, organization_id=org_id)

    itsm_meta = _get_json(db, ITSM_META_KEY, org_id, default={})
    bi_meta = _get_json(db, BI_META_KEY, org_id, default={})

    itsm_trigger = _should_retrain(itsm_meta, itsm_eval, max_age_days=7)
    bi_trigger = _should_retrain(bi_meta, bi_eval, max_age_days=14)

    if itsm_trigger:
        baseline = predictive_analytics_service.recompute_predictive_baselines(db, organization_id=org_id)
        itsm_meta = {
            "last_retrained_at": _iso_now(),
            "reason": "attention_or_stale",
            "baseline_samples": baseline.get("samples", 0),
        }
        _set_json(db, ITSM_META_KEY, org_id, itsm_meta, "ITSM predictive retraining metadata")

    if bi_trigger:
        bi_intelligence_service.ml_detect_anomalies_multivariate(db, organization_id=org_id)
        bi_intelligence_service.ml_predict_project_overrun_lgbm(db, organization_id=org_id)
        bi_meta = {
            "last_retrained_at": _iso_now(),
            "reason": "attention_or_stale",
            "forecast_engine": bi_eval.get("forecast_engine"),
            "overrun_engine": bi_eval.get("overrun_engine"),
        }
        _set_json(db, BI_META_KEY, org_id, bi_meta, "BI predictive retraining metadata")

    return {
        "organization_id": org_id,
        "itsm": {"evaluation": itsm_eval, "triggered": itsm_trigger},
        "bi": {"evaluation": bi_eval, "triggered": bi_trigger},
    }


def guardar_resumen_de_evaluacion(db: Session, resultados: list[dict]) -> dict[str, Any]:
    """Resumen global del ciclo (`LAST_EVAL_KEY`, lo lee la observabilidad)."""
    summary = {
        "evaluated_at": _iso_now(),
        "organizations": len(resultados),
        "itsm_retrained": sum(1 for r in resultados if r["itsm"]["triggered"]),
        "bi_retrained": sum(1 for r in resultados if r["bi"]["triggered"]),
        "results": resultados,
    }
    _set_json(db, LAST_EVAL_KEY, None, summary, "Predictive evaluation cycle summary")
    db.commit()
    return summary


def run_periodic_evaluation_and_retraining(db: Session) -> dict[str, Any]:
    """Todas las organizaciones en la misma sesion (uso manual desde la API y pruebas)."""
    orgs = [r[0] for r in db.query(User.organization_id).filter(User.organization_id.isnot(None)).distinct().all()]
    if not orgs:
        orgs = [None]
    return guardar_resumen_de_evaluacion(db, [evaluar_y_reentrenar_organizacion(db, o) for o in orgs])
