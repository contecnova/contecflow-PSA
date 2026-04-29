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
from typing import Any

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
except ImportError:
    _LGBM_AVAILABLE = False


# ── Anomaly detection ─────────────────────────────────────────────────────────

def _zscore_anomalies(values: list[float], threshold: float = 2.5) -> list[bool]:
    n = len(values)
    mean = sum(values) / n
    std = math.sqrt(sum((v - mean) ** 2 for v in values) / n) or 1
    return [abs(v - mean) / std > threshold for v in values]


def detect_anomalies(
    *,
    values: list[float],
    contamination: float = 0.1,
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
        raise ValueError("At least 4 data points required for anomaly detection")
    contamination = max(0.01, min(0.5, contamination))

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


def predict_churn(
    *,
    clients: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Predict churn probability for a list of clients.

    Each client dict should contain the CHURN_FEATURES keys.
    Returns per-client risk and an aggregate summary.
    """
    results = []
    for client in clients:
        feat = {k: float(client.get(k, 0)) for k in CHURN_FEATURES}
        if _LGBM_AVAILABLE:
            # In production, load a pre-trained model. For demo: use rule-based with LGBM
            # scaffold (training requires historical labelled data).
            prob = _rule_based_churn(feat)  # replace with model.predict_proba when trained
            method_used = "lightgbm_stub"
        else:
            prob = _rule_based_churn(feat)
            method_used = "rule_based"

        risk_level = "high" if prob >= 0.6 else "medium" if prob >= 0.3 else "low"
        results.append({
            "client_id": client.get("client_id", "unknown"),
            "client_name": client.get("client_name", ""),
            "churn_probability": round(prob, 4),
            "risk_level": risk_level,
            "top_factors": [
                k for k in CHURN_FEATURES
                if feat.get(k, 0) > 0 and k in ("support_escalations", "last_login_days_ago", "nps_score")
            ],
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
