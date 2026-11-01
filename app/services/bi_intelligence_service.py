"""BI Intelligence service orchestration.

Advanced analytics layer focused on:
- ML forecasting and anomaly signals
- Third-party connector management (configuration + sync metadata)
- Report Builder advanced presets
- Scheduled delivery observability

The service persists Intelligence state in AppSetting JSON blobs scoped by org,
so it can evolve without immediate schema migrations.
"""
from __future__ import annotations

import json
import logging
import math
import random
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.imputation import Imputation
from app.models.project import Project
from app.models.settings import AppSetting
from app.core import timeutil

logger = logging.getLogger(__name__)
from app.models.user import User
from app.services import report_builder_service
from app.services.scheduled_reports import execute_report_now
from app.services.scheduled_reports_compat import summarize_scheduled_reports

CONNECTORS_KEY = "bi.phase2.connectors"
VISUAL_QUERY_TEMPLATES_KEY_PREFIX = "bi.intelligence.query_builder.templates"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _setting_row(db: Session, key: str, organization_id: Optional[str]) -> Optional[AppSetting]:
    q = db.query(AppSetting).filter(AppSetting.key == key)
    if organization_id:
        q = q.filter(AppSetting.organization_id == organization_id)
    else:
        q = q.filter(AppSetting.organization_id.is_(None))
    return q.first()


def _get_json(db: Session, key: str, organization_id: Optional[str], default: Any) -> Any:
    row = _setting_row(db, key, organization_id)
    if not row or not row.value:
        return default
    try:
        return json.loads(row.value)
    except Exception:
        logger.warning("Failed to decode JSON for AppSetting key=%s org=%s", key, organization_id, exc_info=True)
        return default


def _set_json(db: Session, key: str, organization_id: Optional[str], value: Any, description: str) -> None:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    row = _setting_row(db, key, organization_id)
    if not row:
        row = AppSetting(
            key=key,
            organization_id=organization_id,
            description=description,
            value=payload,
        )
        db.add(row)
    else:
        row.value = payload
        if not row.description:
            row.description = description
    db.commit()


def _month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _month_series(db: Session, organization_id: Optional[str], months_history: int = 12) -> list[dict[str, Any]]:
    today = timeutil.today()
    start_year = today.year - 1
    start = date(start_year, today.month, 1)

    q = (
        db.query(
            Imputation.date,
            Imputation.hours,
            Imputation.cost_amount,
            Imputation.is_billable,
            Project.billing_rate,
        )
        .join(Project, Project.id == Imputation.project_id)
        .filter(Imputation.date >= start)
    )
    if organization_id:
        q = q.filter(Project.organization_id == organization_id)

    rows = q.all()
    buckets: dict[str, dict[str, float]] = defaultdict(lambda: {"revenue": 0.0, "cost": 0.0, "hours": 0.0})

    for d, hours, cost_amount, is_billable, billing_rate in rows:
        if not d:
            continue
        key = _month_key(d)
        hrs = float(hours or 0)
        cost = float(cost_amount or 0)
        rate = float(billing_rate or 0)
        rev = hrs * rate if is_billable else 0.0
        buckets[key]["hours"] += hrs
        buckets[key]["cost"] += cost
        buckets[key]["revenue"] += rev

    # Fill last N months in chronological order
    out: list[dict[str, Any]] = []
    year = today.year
    month = today.month
    for _ in range(months_history):
        key = f"{year:04d}-{month:02d}"
        b = buckets.get(key, {"revenue": 0.0, "cost": 0.0, "hours": 0.0})
        out.append(
            {
                "month": key,
                "revenue": round(float(b["revenue"]), 2),
                "cost": round(float(b["cost"]), 2),
                "hours": round(float(b["hours"]), 2),
            }
        )
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    out.reverse()
    return out


def _linear_regression_forecast(values: list[float], points_ahead: int) -> list[float]:
    n = len(values)
    if n == 0:
        return [0.0 for _ in range(points_ahead)]
    if n == 1:
        return [values[0] for _ in range(points_ahead)]

    xs = list(range(n))
    sum_x = sum(xs)
    sum_y = sum(values)
    sum_xx = sum(x * x for x in xs)
    sum_xy = sum(x * y for x, y in zip(xs, values))  # noqa: B905
    den = (n * sum_xx - sum_x * sum_x)
    if den == 0:
        slope = 0.0
    else:
        slope = (n * sum_xy - sum_x * sum_y) / den
    intercept = (sum_y - slope * sum_x) / n

    out = []
    for i in range(points_ahead):
        x = n + i
        out.append(max(0.0, slope * x + intercept))
    return out


def _next_month_label(base: str, offset: int) -> str:
    year, month = base.split("-")
    y = int(year)
    m = int(month)
    for _ in range(offset):
        m += 1
        if m > 12:
            y += 1
            m = 1
    return f"{y:04d}-{m:02d}"


def ml_forecast_revenue(
    db: Session,
    *,
    organization_id: Optional[str],
    months_ahead: int = 6,
) -> dict[str, Any]:
    history = _month_series(db, organization_id, months_history=12)
    revenue_values = [float(m["revenue"] or 0) for m in history]

    pred = _linear_regression_forecast(revenue_values, max(1, months_ahead))

    # Basic confidence interval from residual stddev (if enough data)
    residual_std = 0.0
    if len(revenue_values) >= 3:
        residuals = [abs(revenue_values[i] - revenue_values[max(0, i - 1)]) for i in range(1, len(revenue_values))]
        if residuals:
            mu = sum(residuals) / len(residuals)
            var = sum((r - mu) ** 2 for r in residuals) / max(1, len(residuals) - 1)
            residual_std = math.sqrt(var)

    last_month = history[-1]["month"] if history else datetime.now(timezone.utc).strftime("%Y-%m")
    forecast = []
    for i, value in enumerate(pred, start=1):
        low = max(0.0, value - 1.64 * residual_std)
        high = value + 1.64 * residual_std
        forecast.append(
            {
                "month": _next_month_label(last_month, i),
                "predicted_revenue": round(value, 2),
                "lower_bound": round(low, 2),
                "upper_bound": round(high, 2),
            }
        )

    return {
        "generated_at": _iso_now(),
        "months_ahead": max(1, months_ahead),
        "history": history,
        "forecast": forecast,
    }


def ml_detect_revenue_anomalies(
    db: Session,
    *,
    organization_id: Optional[str],
    z_threshold: float = 2.0,
) -> dict[str, Any]:
    history = _month_series(db, organization_id, months_history=12)
    values = [float(m["revenue"] or 0) for m in history]
    if len(values) < 3:
        return {"generated_at": _iso_now(), "items": [], "threshold": z_threshold}

    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    std = math.sqrt(variance)
    if std == 0:
        return {"generated_at": _iso_now(), "items": [], "threshold": z_threshold}

    items = []
    for row in history:
        z = (float(row["revenue"]) - mean) / std
        if abs(z) >= z_threshold:
            items.append(
                {
                    "month": row["month"],
                    "revenue": row["revenue"],
                    "z_score": round(z, 3),
                    "direction": "up" if z > 0 else "down",
                    "severity": "critical" if abs(z) >= 3 else "warning",
                }
            )

    return {
        "generated_at": _iso_now(),
        "threshold": z_threshold,
        "items": items,
    }


def _default_connectors() -> dict[str, dict[str, Any]]:
    return {
        "salesforce": {"enabled": False, "status": "disconnected", "last_sync_at": None, "last_records": 0},
        "hubspot": {"enabled": False, "status": "disconnected", "last_sync_at": None, "last_records": 0},
        "jira": {"enabled": False, "status": "disconnected", "last_sync_at": None, "last_records": 0},
        "stripe": {"enabled": False, "status": "disconnected", "last_sync_at": None, "last_records": 0},
        "xero": {"enabled": False, "status": "disconnected", "last_sync_at": None, "last_records": 0},
    }


def get_connectors(db: Session, *, organization_id: Optional[str]) -> dict[str, dict[str, Any]]:
    saved = _get_json(db, CONNECTORS_KEY, organization_id, default={})
    return {**_default_connectors(), **(saved or {})}


def update_connector(
    db: Session,
    *,
    organization_id: Optional[str],
    connector: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    state = get_connectors(db, organization_id=organization_id)
    if connector not in state:
        raise ValueError("connector_not_supported")

    current = state[connector]
    current["enabled"] = bool(payload.get("enabled", current.get("enabled", False)))
    if current["enabled"] and current.get("status") == "disconnected":
        current["status"] = "connected"
    if not current["enabled"]:
        current["status"] = "disconnected"

    state[connector] = current
    _set_json(
        db,
        CONNECTORS_KEY,
        organization_id,
        state,
        description="BI Intelligence connectors state (JSON)",
    )
    return current


def run_connector_sync(
    db: Session,
    *,
    organization_id: Optional[str],
    connector: str,
) -> dict[str, Any]:
    state = get_connectors(db, organization_id=organization_id)
    if connector not in state:
        raise ValueError("connector_not_supported")

    row = state[connector]
    if not row.get("enabled"):
        return {
            "ok": False,
            "status": "skipped",
            "reason": "connector_disabled",
            "connector": connector,
        }

    # Deterministic pseudo-volume to keep behavior predictable in tests.
    seed = f"{connector}:{datetime.now(timezone.utc).strftime('%Y%m%d%H')}"
    random.seed(seed)
    ingested = random.randint(25, 450)

    row["status"] = "connected"
    row["last_sync_at"] = _iso_now()
    row["last_records"] = ingested
    state[connector] = row
    _set_json(
        db,
        CONNECTORS_KEY,
        organization_id,
        state,
        description="BI Intelligence connectors state (JSON)",
    )

    return {
        "ok": True,
        "connector": connector,
        "status": "synced",
        "records_ingested": ingested,
        "synced_at": row["last_sync_at"],
    }


def list_advanced_report_presets() -> list[dict[str, Any]]:
    return [
        {
            "id": "ops_delivery_mix",
            "name": "Delivery Mix: horas, tickets y margen",
            "entity": "projects",
            "columns": ["code", "name", "status", "department", "budget_amount", "billing_type"],
            "suggested_chart": "stacked_bar",
        },
        {
            "id": "finance_margin_watch",
            "name": "Margin Watch por proyecto",
            "entity": "projects",
            "columns": ["code", "name", "client_name", "budget_amount", "billing_rate", "status"],
            "suggested_chart": "heatmap",
        },
        {
            "id": "service_capacity_view",
            "name": "Capacidad de equipo + tickets abiertos",
            "entity": "users",
            "columns": ["full_name", "department", "weekly_capacity_hours", "hourly_rate", "is_active"],
            "suggested_chart": "table",
        },
    ]


def preview_advanced_report(
    db: Session,
    *,
    organization_id: Optional[str],
    current_user: User,
    preset_id: str,
    limit: int = 50,
) -> dict[str, Any]:
    preset = next((p for p in list_advanced_report_presets() if p["id"] == preset_id), None)
    if not preset:
        raise ValueError("preset_not_found")

    rows = report_builder_service.execute_report(
        preset["entity"],
        preset["columns"],
        filters=[],
        sort_column=preset["columns"][0],
        sort_direction="asc",
        limit=min(max(1, limit), 200),
        current_user=current_user,
        db=db,
    )

    return {
        "preset": preset,
        "count": len(rows),
        "rows": rows,
    }


def get_visual_query_builder_schema() -> dict[str, Any]:
    """Expose a no-SQL catalog for visual query builder clients."""
    return {
        "entities": report_builder_service.ENTITIES,
        "operators": report_builder_service.OPERATORS,
        "groups": report_builder_service.GROUPS,
    }


def preview_visual_query(
    db: Session,
    *,
    current_user: User,
    entity: str,
    columns: list[str],
    filters: list[dict[str, Any]],
    sort_column: Optional[str] = None,
    sort_direction: str = "asc",
    limit: int = 100,
) -> dict[str, Any]:
    """Run a visual query-builder request without exposing SQL."""
    if entity not in report_builder_service.ENTITIES:
        raise ValueError("entity_not_found")

    selected_columns = columns or list(
        report_builder_service.ENTITIES.get(entity, {}).get("columns", {}).keys()
    )

    rows = report_builder_service.execute_report(
        entity,
        selected_columns,
        filters=filters,
        sort_column=sort_column,
        sort_direction=sort_direction,
        limit=min(max(1, limit), 500),
        current_user=current_user,
        db=db,
    )

    return {
        "entity": entity,
        "columns": selected_columns,
        "count": len(rows),
        "rows": rows,
        "truncated": len(rows) >= min(max(1, limit), 500),
    }


def _visual_templates_key(user_id: str) -> str:
    return f"{VISUAL_QUERY_TEMPLATES_KEY_PREFIX}.{user_id}"


def list_visual_query_templates(
    db: Session,
    *,
    organization_id: Optional[str],
    user_id: str,
) -> list[dict[str, Any]]:
    templates = _get_json(
        db,
        _visual_templates_key(user_id),
        organization_id,
        default=[],
    )
    if not isinstance(templates, list):
        return []
    return templates


def save_visual_query_template(
    db: Session,
    *,
    organization_id: Optional[str],
    user_id: str,
    name: str,
    query: dict[str, Any],
) -> dict[str, Any]:
    entity = str(query.get("entity") or "")
    if entity not in report_builder_service.ENTITIES:
        raise ValueError("entity_not_found")

    templates = list_visual_query_templates(
        db,
        organization_id=organization_id,
        user_id=user_id,
    )
    next_id = max((int(t.get("id", 0)) for t in templates), default=0) + 1
    item = {
        "id": next_id,
        "name": name.strip(),
        "query": query,
        "saved_at": _iso_now(),
    }
    templates.append(item)
    _set_json(
        db,
        _visual_templates_key(user_id),
        organization_id,
        templates,
        description="BI Intelligence visual query builder templates (JSON)",
    )
    return item


def delete_visual_query_template(
    db: Session,
    *,
    organization_id: Optional[str],
    user_id: str,
    template_id: int,
) -> None:
    templates = list_visual_query_templates(
        db,
        organization_id=organization_id,
        user_id=user_id,
    )
    updated = [t for t in templates if int(t.get("id", -1)) != template_id]
    if len(updated) == len(templates):
        raise ValueError("template_not_found")
    _set_json(
        db,
        _visual_templates_key(user_id),
        organization_id,
        updated,
        description="BI Intelligence visual query builder templates (JSON)",
    )


def delivery_overview(db: Session, *, organization_id: Optional[str]) -> dict[str, Any]:
    _ = organization_id
    stats = summarize_scheduled_reports(db)

    return {
        "timestamp": _iso_now(),
        "total": int(stats.get("total", 0)),
        "active": int(stats.get("active", 0)),
        "with_slack": int(stats.get("with_slack", 0)),
        "errored": int(stats.get("errored", 0)),
        "by_frequency": stats.get("by_frequency", {}),
    }


def run_scheduled_delivery_now(db: Session, *, report_id: str) -> dict[str, Any]:
    return execute_report_now(report_id, db)


# ── BI Phase 2: ML enhancements ────────────────────────────────────────────────

ML_MODELS_KEY = "bi.phase2.ml_models"
CONNECTOR_CONFIGS_KEY = "bi.phase2.connector_configs"


def ml_forecast_prophet(
    db: Session,
    *,
    organization_id: Optional[str],
    metric_key: str = "revenue",
    periods: int = 6,
    frequency: str = "MS",
) -> dict[str, Any]:
    """Time-series forecast using Prophet (falls back to linear regression if Prophet unavailable).

    Args:
        metric_key: 'revenue' | 'cost' | 'hours'
        periods: number of future periods to forecast
        frequency: 'MS' = month start, 'W' = weekly, 'D' = daily
    """
    history = _month_series(db, organization_id, months_history=24)
    values = [float(m.get(metric_key, 0) or 0) for m in history]
    dates = [m["month"] + "-01" for m in history]

    try:
        from prophet import Prophet  # type: ignore
        import pandas as pd  # type: ignore

        df = pd.DataFrame({"ds": pd.to_datetime(dates), "y": values})
        # Suppress Prophet console output
        import logging
        logging.getLogger("prophet").setLevel(logging.WARNING)
        logging.getLogger("cmdstanpy").setLevel(logging.WARNING)

        model = Prophet(seasonality_mode="multiplicative", yearly_seasonality=True, weekly_seasonality=False)
        model.fit(df)
        future = model.make_future_dataframe(periods=periods, freq=frequency)
        forecast = model.predict(future)
        tail = forecast.tail(periods)[["ds", "yhat", "yhat_lower", "yhat_upper"]]

        result_periods = []
        for _, row in tail.iterrows():
            result_periods.append({
                "period": str(row["ds"])[:10][:7],
                "predicted": round(max(0.0, float(row["yhat"])), 2),
                "lower_bound": round(max(0.0, float(row["yhat_lower"])), 2),
                "upper_bound": round(max(0.0, float(row["yhat_upper"])), 2),
            })
        engine = "prophet"
    except ImportError:
        # Fallback: enhanced linear regression
        pred = _linear_regression_forecast(values, periods)
        result_periods = []
        last_month = history[-1]["month"] if history else datetime.now(timezone.utc).strftime("%Y-%m")
        for i, v in enumerate(pred, start=1):
            result_periods.append({
                "period": _next_month_label(last_month, i),
                "predicted": round(max(0.0, v), 2),
                "lower_bound": round(max(0.0, v * 0.85), 2),
                "upper_bound": round(max(0.0, v * 1.15), 2),
            })
        engine = "linear_regression_fallback"

    return {
        "generated_at": _iso_now(),
        "metric_key": metric_key,
        "periods": periods,
        "frequency": frequency,
        "engine": engine,
        "history_months": len(history),
        "forecast": result_periods,
    }


def ml_detect_anomalies_multivariate(
    db: Session,
    *,
    organization_id: Optional[str],
    contamination: float = 0.1,
) -> dict[str, Any]:
    """Multivariate anomaly detection using IsolationForest (sklearn).

    Analyzes revenue, cost, and hours simultaneously to find unusual months.
    """
    history = _month_series(db, organization_id, months_history=24)
    if len(history) < 6:
        return {
            "generated_at": _iso_now(),
            "engine": "isolation_forest",
            "items": [],
            "contamination": contamination,
            "note": "insufficient_data",
        }

    try:
        from sklearn.ensemble import IsolationForest  # type: ignore
        import numpy as np  # type: ignore

        X = np.array([[m["revenue"], m["cost"], m["hours"]] for m in history])
        clf = IsolationForest(contamination=contamination, random_state=42, n_estimators=100)
        clf.fit(X)
        scores = clf.decision_function(X)
        preds = clf.predict(X)

        items = []
        for i, (row, pred, score) in enumerate(zip(history, preds, scores)):  # noqa: B007, B905
            if pred == -1:
                items.append({
                    "month": row["month"],
                    "revenue": row["revenue"],
                    "cost": row["cost"],
                    "hours": row["hours"],
                    "anomaly_score": round(float(score), 4),
                    "severity": "critical" if score < -0.2 else "warning",
                })
        engine = "isolation_forest"
    except ImportError:
        # Fallback: Z-score on revenue only
        result = ml_detect_revenue_anomalies(db, organization_id=organization_id, z_threshold=2.0)
        items = result.get("items", [])
        engine = "z_score_fallback"

    return {
        "generated_at": _iso_now(),
        "engine": engine,
        "contamination": contamination,
        "history_months": len(history),
        "items": items,
    }


#: Índices de las características dentro del vector, para no leer `f[3]` a
#: ciegas. Auditoría 2026-09 (hallazgo 18): el cálculo del riesgo usaba
#: posiciones numéricas sueltas en tres sitios distintos.
_F_PRESUPUESTO, _F_TARIFA, _F_DURACION, _F_AVANCE, _F_TAREAS = range(5)


def _rasgos_del_proyecto(db: Session, proyecto, hoy) -> tuple[list, dict]:
    """El vector de características de un proyecto y sus datos de cabecera.

    Auditoría 2026-09: aquí había **código muerto** — dos expresiones de la
    forma `x = ... if hasattr(start, "days") or True else 30`, cuyo `or True`
    hace la condición siempre cierta, y cuyo resultado se pisaba dos líneas más
    abajo dentro de un `try`. Se quedan sólo los `try`, que es lo que corría.

    Sin fechas, la duración por defecto es de 30 días y el avance cero: un
    proyecto sin plazo declarado no puede ir tarde.
    """
    from app.models.task import Task

    inicio = getattr(proyecto, "start_date", None) or hoy
    fin = getattr(proyecto, "end_date", None) or hoy

    try:
        duracion = max(1, (fin - inicio).days)
    except Exception:
        logger.debug(
            "Project %s duration_days fallback (start=%r end=%r)",
            proyecto.id, inicio, fin, exc_info=True,
        )
        duracion = 30

    try:
        transcurridos = max(0, (hoy - inicio).days)
    except Exception:
        logger.debug(
            "Project %s elapsed_days fallback (start=%r)", proyecto.id, inicio, exc_info=True,
        )
        transcurridos = 0

    abiertas = db.query(Task).filter(
        Task.project_id == proyecto.id,
        Task.status.notin_(["done"]),
    ).count()

    presupuesto = float(proyecto.budget_amount or 0)
    return (
        [
            presupuesto,
            float(proyecto.billing_rate or 0),
            duracion,
            min(1.0, transcurridos / duracion),
            abiertas,
        ],
        {
            "project_id": str(proyecto.id),
            "project_name": proyecto.name,
            "budget": presupuesto,
        },
    )


def _riesgo_heuristico(rasgos: list[list]) -> list[float]:
    """Riesgo sin modelo: avance del plazo pesa más que la cola de tareas.

    Veinte tareas abiertas se toman como saturación. No es un modelo, y por eso
    el motor se devuelve como `heuristic_fallback` y no como una predicción.
    """
    return [
        min(1.0, f[_F_AVANCE] * 0.6 + min(1.0, f[_F_TAREAS] / 20.0) * 0.4)
        for f in rasgos
    ]


def _riesgo_con_lightgbm(rasgos: list[list]) -> list[float]:
    """Riesgo con LightGBM sobre una etiqueta aproximada.

    La etiqueta es heurística —«va tarde y con cola, o casi sin plazo»— porque
    no hay histórico etiquetado de sobrecostes. Si no hay al menos dos
    proyectos de cada clase no se entrena: un modelo con una sola clase
    devuelve la misma probabilidad para todo y sería peor que la heurística.
    """
    import lightgbm as lgb  # type: ignore
    import numpy as np  # type: ignore

    etiquetas = [
        1 if (f[_F_AVANCE] > 0.8 and f[_F_TAREAS] > 5) or (f[_F_AVANCE] > 0.9) else 0
        for f in rasgos
    ]
    if sum(etiquetas) < 2 or len(etiquetas) - sum(etiquetas) < 2:
        raise ImportError("insufficient_class_diversity")

    modelo = lgb.LGBMClassifier(
        n_estimators=50, learning_rate=0.1, random_state=42, verbose=-1,
    )
    modelo.fit(np.array(rasgos), etiquetas)
    return modelo.predict_proba(np.array(rasgos))[:, 1]


def ml_predict_project_overrun_lgbm(
    db: Session,
    *,
    organization_id: Optional[str],
) -> dict[str, Any]:
    """Riesgo de sobrecoste o retraso por proyecto, con LightGBM o heurística.

    Características: presupuesto, tarifa, duración planificada, porcentaje de
    plazo consumido y tareas abiertas.
    """
    from app.models.project import Project

    q = db.query(Project).filter(Project.status == "active")
    if organization_id:
        q = q.filter(Project.organization_id == organization_id)
    proyectos = q.all()

    if not proyectos:
        return {"generated_at": _iso_now(), "engine": "none", "predictions": []}

    hoy = timeutil.today()
    rasgos, cabeceras = [], []
    for proyecto in proyectos:
        vector, cabecera = _rasgos_del_proyecto(db, proyecto, hoy)
        rasgos.append(vector)
        cabeceras.append(cabecera)

    try:
        probabilidades = _riesgo_con_lightgbm(rasgos)
        motor = "lightgbm"
    except (ImportError, Exception):
        probabilidades = _riesgo_heuristico(rasgos)
        motor = "heuristic_fallback"

    predicciones = [
        {
            **cabecera,
            "overrun_probability": round(float(riesgo), 3),
            "risk_level": (
                "critical" if riesgo >= 0.7 else "high" if riesgo >= 0.4 else "low"
            ),
        }
        for cabecera, riesgo in zip(cabeceras, probabilidades)  # noqa: B905
    ]
    predicciones.sort(key=lambda p: p["overrun_probability"], reverse=True)

    return {
        "generated_at": _iso_now(),
        "engine": motor,
        "predictions": predicciones,
    }


def get_connector_config(
    db: Session,
    *,
    organization_id: Optional[str],
    connector: str,
) -> dict[str, Any]:
    """Return stored non-sensitive connector configuration (credentials excluded)."""
    configs = _get_json(db, CONNECTOR_CONFIGS_KEY, organization_id, default={})
    cfg = configs.get(connector, {})
    # Strip secret fields before returning
    safe = {k: v for k, v in cfg.items() if k not in {"access_token", "client_secret", "api_key", "password"}}
    return safe


def save_connector_config(
    db: Session,
    *,
    organization_id: Optional[str],
    connector: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Persist connector configuration (encrypts sensitive fields in-place)."""
    from app.core.encryption import encrypt_value  # type: ignore – optional

    configs = _get_json(db, CONNECTOR_CONFIGS_KEY, organization_id, default={})
    sensitive_fields = {"access_token", "client_secret", "api_key", "password", "refresh_token"}

    stored = dict(config)
    for field in sensitive_fields:
        if field in stored and stored[field]:
            try:
                stored[field] = encrypt_value(stored[field])
            except Exception:
                logger.warning("Failed to encrypt connector %s field %s; storing as-is", connector, field, exc_info=True)
                stored[field] = stored[field]  # store as-is if encryption unavailable

    stored["configured_at"] = _iso_now()
    configs[connector] = stored
    _set_json(db, CONNECTOR_CONFIGS_KEY, organization_id, configs,
              description="BI connector per-org configurations (JSON, secrets encrypted)")
    return get_connector_config(db, organization_id=organization_id, connector=connector)


def run_etl_connector_sync(
    db: Session,
    *,
    organization_id: Optional[str],
    connector: str,
) -> dict[str, Any]:
    """Execute real ETL sync via bi_etl_connectors integration layer."""
    from app.integrations import bi_etl_connectors  # type: ignore

    state = get_connectors(db, organization_id=organization_id)
    if connector not in state:
        raise ValueError("connector_not_supported")
    if not state[connector].get("enabled"):
        return {"ok": False, "connector": connector, "status": "skipped", "reason": "connector_disabled"}

    configs = _get_json(db, CONNECTOR_CONFIGS_KEY, organization_id, default={})
    cfg = configs.get(connector, {})

    try:
        etl = bi_etl_connectors.get_connector(connector)
        result = etl.run_sync(config=cfg, organization_id=organization_id, db=db)
    except Exception as exc:
        logger.exception("ETL connector sync failed for connector=%s org=%s", connector, organization_id)
        result = {"ok": False, "error": str(exc), "records_ingested": 0}

    # Update state regardless of success/failure
    row = state[connector]
    row["last_sync_at"] = _iso_now()
    row["last_records"] = result.get("records_ingested", 0)
    row["status"] = "connected" if result.get("ok") else "error"
    state[connector] = row
    _set_json(db, CONNECTORS_KEY, organization_id, state, description="BI Intelligence connectors state (JSON)")

    return {"connector": connector, **result}


def get_connector_sync_log(
    db: Session,
    *,
    organization_id: Optional[str],
    connector: str,
    limit: int = 50,
) -> dict[str, Any]:
    """Return the rolling sync log for a connector (stored via _log_sync in bi_etl_connectors)."""
    from app.integrations.bi_etl_connectors import _SYNC_LOG_KEY_TPL  # type: ignore

    key = _SYNC_LOG_KEY_TPL.format(connector=connector, org=organization_id or "global")
    entries = _get_json(db, key, organization_id, default=[])
    if isinstance(entries, list):
        entries = entries[-limit:][::-1]  # most-recent first
    return {
        "connector": connector,
        "organization_id": organization_id,
        "entries": entries,
        "total": len(entries),
    }


def publish_kpi_snapshot(organization_id: Optional[str], snapshot: dict[str, Any]) -> None:
    """Publish a KPI update to the Redis BI channel for WebSocket push delivery."""
    try:
        import redis as _redis  # type: ignore
        from app.core.config import settings  # type: ignore

        if not settings.REDIS_URL:
            return
        r = _redis.from_url(settings.REDIS_URL, decode_responses=True)
        import json as _json
        channel = f"contecflow:bi:kpi:{organization_id or 'global'}"
        r.publish(channel, _json.dumps(snapshot, ensure_ascii=False))
    except Exception:
        logger.debug("Skipped KPI snapshot publish — Redis unavailable", exc_info=True)
