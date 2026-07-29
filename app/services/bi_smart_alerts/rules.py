"""Alert rule CRUD for BI Smart Alerts."""
from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.user import User

from .constants import RULES_KEY, SUPPORTED_CONDITIONS, SUPPORTED_METRICS
from .custom_metrics import list_custom_metrics
from .persistence import _get_json, _iso_now, _set_json


def list_alert_rules(db: Session, *, organization_id: Optional[str]) -> list[dict[str, Any]]:
    return _get_json(db, RULES_KEY, organization_id, default=[])


def create_alert_rule(
    db: Session,
    *,
    organization_id: Optional[str],
    payload: dict[str, Any],
    current_user: User,
) -> dict[str, Any]:
    rules = list_alert_rules(db, organization_id=organization_id)
    metric = str(payload.get("metric_key", "")).strip()
    condition = str(payload.get("condition", "")).strip()
    customs = list_custom_metrics(db, organization_id=organization_id)
    valid_metrics = set(SUPPORTED_METRICS) | {c["key"] for c in customs}
    if metric not in valid_metrics:
        raise ValueError("unsupported_metric")
    if condition not in SUPPORTED_CONDITIONS:
        raise ValueError("unsupported_condition")

    threshold = payload.get("threshold")
    if condition in ("threshold_above", "threshold_below") and threshold is None:
        raise ValueError("threshold_required")

    row: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "name": str(payload.get("name", f"Alert {metric}")).strip() or f"Alert {metric}",
        "metric_key": metric,
        "condition": condition,
        "threshold": float(threshold) if threshold is not None else None,
        "trend_periods": int(payload.get("trend_periods", 3)),
        "severity": str(payload.get("severity", "warning")) if payload.get("severity") in ("info", "warning", "critical") else "warning",
        "cooldown_minutes": max(5, int(payload.get("cooldown_minutes", 60))),
        "enabled": bool(payload.get("enabled", True)),
        "correlated_metrics": list(payload.get("correlated_metrics") or []),
        "notification_channels": list(payload.get("notification_channels") or ["ui"]),
        "created_by": current_user.id,
        "created_at": _iso_now(),
        "last_triggered_at": None,
    }
    rules.append(row)
    _set_json(db, RULES_KEY, organization_id, rules, description="BI Smart Alert rules (JSON)")
    return row


def update_alert_rule(
    db: Session,
    *,
    organization_id: Optional[str],
    rule_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    rules = list_alert_rules(db, organization_id=organization_id)
    target = next((r for r in rules if r.get("id") == rule_id), None)
    if not target:
        raise ValueError("rule_not_found")
    for field in ("name", "threshold", "trend_periods", "severity", "cooldown_minutes", "enabled",
                  "correlated_metrics", "notification_channels"):
        if field in payload and payload[field] is not None:
            target[field] = payload[field]
    _set_json(db, RULES_KEY, organization_id, rules, description="BI Smart Alert rules (JSON)")
    return target


def delete_alert_rule(db: Session, *, organization_id: Optional[str], rule_id: str) -> bool:
    rules = list_alert_rules(db, organization_id=organization_id)
    new_rules = [r for r in rules if r.get("id") != rule_id]
    if len(new_rules) == len(rules):
        return False
    _set_json(db, RULES_KEY, organization_id, new_rules, description="BI Smart Alert rules (JSON)")
    return True
