"""
bi_anomaly_service.py — Anomaly detection using IsolationForest (sklearn).

When scikit-learn is not available, falls back to a Z-score approach.
LightGBM churn prediction is also provided in this module.

Anomaly detection:
  - IsolationForest for univariate and multivariate time series
  - Z-score fallback when sklearn unavailable

Churn prediction:
  - LightGBM binary classifier for client churn risk
  - Feature engineering from usage metrics
"""
from __future__ import annotations

import math
import random
from typing import Any

from app.core.escalas import nivel_de_abandono

# ── Graceful sklearn import ────────────────────────────────────────────────────
try:
    from sklearn.ensemble import IsolationForest as _IsolationForest  # type: ignore
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False

# ── Graceful LightGBM import ──────────────────────────────────────────────────
try:
    import lightgbm as lgb  # type: ignore
    _LGBM_AVAILABLE = True
except (ImportError, OSError):
    _LGBM_AVAILABLE = False


_CHURN_MODEL: Any | None = None
_CHURN_BASELINE: dict[str, float] = {}
_CHURN_SCALE: dict[str, float] = {}


# ── Anomaly detection ─────────────────────────────────────────────────────────

def _zscore_anomalies(values: list[float], threshold: float = 2.5) -> list[bool]:
    n = len(values)
    mean = sum(values) / n
    std = math.sqrt(sum((v - mean) ** 2 for v in values) / n) or 1
    return [abs(v - mean) / std > threshold for v in values]


def detect_anomalies(
    *,
    values: list[float],
    contamination: Any = "auto",
    method: str = "auto",
) -> dict[str, Any]:
    """
    Detect anomalies in a univariate time series.

    Returns:
        {
            method_used, anomaly_indices, anomaly_scores, is_anomaly,
            sklearn_available, total_points, anomaly_count
        }
    """
    if len(values) < 4:
        from app.core.codigos_de_error import ErrorConCodigo
        raise ErrorConCodigo("anomalias_datos_insuficientes", detail="At least 4 data points required for anomaly detection")
    # Baja (auditoría 22-11-2026): por defecto `contamination="auto"` (umbral
    # del propio Isolation Forest, Liu et al.); con 0,1 fijo SIEMPRE marcaba el
    # 10 % de los puntos como anómalos, hubiera anomalías o no. Una cifra
    # explícita sigue valiendo (acotada a 0,01-0,5).
    if contamination != "auto":
        contamination = max(0.01, min(0.5, float(contamination)))

    if _SKLEARN_AVAILABLE and method in ("auto", "isolation_forest"):
        X = [[v] for v in values]
        clf = _IsolationForest(contamination=contamination, random_state=42, n_estimators=100)
        clf.fit(X)
        scores = clf.decision_function(X)
        labels = clf.predict(X)
        is_anomaly = [bool(l == -1) for l in labels]
        method_used = "isolation_forest"
    else:
        is_anomaly = _zscore_anomalies(values)
        scores = [0.0] * len(values)
        method_used = "zscore"

    anomaly_indices = [i for i, flag in enumerate(is_anomaly) if flag]

    return {
        "method_used": method_used,
        "sklearn_available": _SKLEARN_AVAILABLE,
        "total_points": len(values),
        "anomaly_count": len(anomaly_indices),
        "anomaly_indices": anomaly_indices,
        "anomaly_scores": [round(float(s), 4) for s in scores],
        "is_anomaly": is_anomaly,
    }


# ── LightGBM churn prediction ─────────────────────────────────────────────────

# Feature schema for churn:
#   tickets_last_30d, response_time_avg_h, nps_score, contract_renewal_days,
#   support_escalations, last_login_days_ago, active_projects

CHURN_FEATURES = [
    "tickets_last_30d",
    "response_time_avg_h",
    "nps_score",
    "contract_renewal_days",
    "support_escalations",
    "last_login_days_ago",
    "active_projects",
]

# Simple rule-based scoring when LightGBM is not available
def _rule_based_churn(features: dict[str, float]) -> float:
    score = 0.0
    if features.get("nps_score", 7) < 5:
        score += 0.3
    if features.get("tickets_last_30d", 0) > 10:
        score += 0.2
    if features.get("support_escalations", 0) > 2:
        score += 0.15
    if features.get("last_login_days_ago", 0) > 30:
        score += 0.2
    if features.get("contract_renewal_days", 90) < 30:
        score += 0.15
    return min(1.0, score)


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def _prepare_churn_model() -> tuple[Any | None, str]:
    """Auditoría 22-11-2026 (A62): no hay modelo entrenado.

    Antes se entrenaba un LightGBM con 1.400 filas SINTÉTICAS (`random.Random(42)`)
    derivadas de una heurística fija y se presentaba como «lightgbm_synthetic»:
    probabilidades con aspecto de ML sin ninguna base real. No hay histórico de
    bajas de clientes con sus variables en el tiempo para entrenar uno de verdad,
    así que la predicción es la HEURÍSTICA transparente (`_rule_based_churn`)
    sobre los datos reales de cada cliente, y así se rotula (`rule_based`).
    """
    return None, "rule_based"


def _top_churn_factors(features: dict[str, float], model: Any | None) -> list[str]:
    if not model:
        candidates = [
            "support_escalations",
            "last_login_days_ago",
            "tickets_last_30d",
            "response_time_avg_h",
        ]
        out = [k for k in candidates if float(features.get(k, 0)) > 0]
        return out[:3]

    importances = [float(v) for v in getattr(model, "feature_importances_", [1.0] * len(CHURN_FEATURES))]
    scored: list[tuple[float, str]] = []
    for i, feature in enumerate(CHURN_FEATURES):
        value = float(features.get(feature, 0.0))
        base = float(_CHURN_BASELINE.get(feature, 0.0))
        sigma = float(_CHURN_SCALE.get(feature, 1.0))
        deviation = abs((value - base) / sigma)
        scored.append((deviation * max(1.0, importances[i]), feature))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [name for _, name in scored[:3]]


def predict_churn(
    *,
    clients: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Predict churn probability for a list of clients.

    Each client dict should contain the CHURN_FEATURES keys.
    Returns per-client risk and an aggregate summary.
    """
    model, method_used = _prepare_churn_model()
    results = []
    for client in clients:
        feat = {k: float(client.get(k, 0)) for k in CHURN_FEATURES}
        if model is not None:
            vector = [feat[k] for k in CHURN_FEATURES]
            prob = float(model.predict_proba([vector])[0][1])
        else:
            prob = _rule_based_churn(feat)

        risk_level = nivel_de_abandono(prob)
        results.append({
            "client_id": client.get("client_id", "unknown"),
            "client_name": client.get("client_name", ""),
            "churn_probability": round(prob, 4),
            "risk_level": risk_level,
            "top_factors": _top_churn_factors(feat, model),
        })

    high_risk = [r for r in results if r["risk_level"] == "high"]
    return {
        "method_used": method_used if results else "rule_based",
        "lgbm_available": _LGBM_AVAILABLE,
        "total_clients": len(results),
        "high_risk_count": len(high_risk),
        "medium_risk_count": sum(1 for r in results if r["risk_level"] == "medium"),
        "low_risk_count": sum(1 for r in results if r["risk_level"] == "low"),
        "clients": results,
    }
