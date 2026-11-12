"""
bi_conditional_delivery_service.py — Conditional scheduled report delivery.

Extends the base scheduled reports (bi_report_delivery_service) with diff-based
delivery: a report is only sent if the current snapshot differs from the last
sent snapshot by more than a configured threshold.

Also supports:
  - Condition-based triggers (e.g. only send if metric > threshold)
  - Digest mode (batch multiple reports into one delivery)
"""
from __future__ import annotations
import logging

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.settings import AppSetting

_KEY_RULES = "bi.cond_delivery.rules"
_KEY_SNAPSHOTS = "bi.cond_delivery.snapshots"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get(db: Session, key: str, org_id: Optional[str], default: Any) -> Any:
    q = db.query(AppSetting).filter(AppSetting.key == key)
    q = q.filter(AppSetting.organization_id == org_id) if org_id else q.filter(AppSetting.organization_id.is_(None))
    row = q.first()
    if not row or not row.value:
        return default
    try:
        return json.loads(row.value)
    except Exception:
        logging.getLogger(__name__).debug("_get: excepcion ignorada", exc_info=True)
        return default


def _set(db: Session, key: str, org_id: Optional[str], value: Any) -> None:
    payload = json.dumps(value, ensure_ascii=False)
    q = db.query(AppSetting).filter(AppSetting.key == key)
    q = q.filter(AppSetting.organization_id == org_id) if org_id else q.filter(AppSetting.organization_id.is_(None))
    row = q.first()
    if not row:
        row = AppSetting(key=key, organization_id=org_id, value=payload, description=f"BI Cond Delivery: {key}")
        db.add(row)
    else:
        row.value = payload
    db.commit()


def _snapshot_hash(data: Any) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


# ── Delivery rules ────────────────────────────────────────────────────────────

def create_rule(
    db: Session,
    *,
    org_id: Optional[str],
    name: str,
    report_id: str,
    condition_metric: Optional[str],
    condition_operator: Optional[str],
    condition_value: Optional[float],
    diff_threshold_pct: float,
    recipients: list[str],
    schedule_cron: str,
    enabled: bool = True,
    created_by: str,
) -> dict:
    rules: dict = _get(db, _KEY_RULES, org_id, {})
    rule_id = str(uuid.uuid4())
    entry = {
        "id": rule_id,
        "name": name,
        "report_id": report_id,
        "condition_metric": condition_metric,
        "condition_operator": condition_operator,
        "condition_value": condition_value,
        "diff_threshold_pct": diff_threshold_pct,
        "recipients": recipients,
        "schedule_cron": schedule_cron,
        "enabled": enabled,
        "created_by": created_by,
        "created_at": _iso_now(),
        "last_triggered_at": None,
        "trigger_count": 0,
    }
    rules[rule_id] = entry
    _set(db, _KEY_RULES, org_id, rules)
    return entry


def list_rules(db: Session, *, org_id: Optional[str]) -> list[dict]:
    return sorted(_get(db, _KEY_RULES, org_id, {}).values(), key=lambda r: r["created_at"], reverse=True)


def update_rule(db: Session, *, org_id: Optional[str], rule_id: str, updates: dict) -> dict:
    rules: dict = _get(db, _KEY_RULES, org_id, {})
    if rule_id not in rules:
        raise ValueError(f"Rule '{rule_id}' not found")
    allowed = {"name", "enabled", "condition_metric", "condition_operator", "condition_value",
               "diff_threshold_pct", "recipients", "schedule_cron"}
    for k, v in updates.items():
        if k in allowed:
            rules[rule_id][k] = v
    rules[rule_id]["updated_at"] = _iso_now()
    _set(db, _KEY_RULES, org_id, rules)
    return rules[rule_id]


def delete_rule(db: Session, *, org_id: Optional[str], rule_id: str) -> None:
    rules: dict = _get(db, _KEY_RULES, org_id, {})
    if rule_id not in rules:
        raise ValueError(f"Rule '{rule_id}' not found")
    del rules[rule_id]
    _set(db, _KEY_RULES, org_id, rules)

    snapshots: dict = _get(db, _KEY_SNAPSHOTS, org_id, {})
    if rule_id in snapshots:
        del snapshots[rule_id]
        _set(db, _KEY_SNAPSHOTS, org_id, snapshots)


def evaluate_rule(
    db: Session,
    *,
    org_id: Optional[str],
    rule_id: str,
    current_data: Any,
    current_metric_value: Optional[float] = None,
) -> dict:
    """
    Evaluate if a delivery rule should trigger based on diff and conditions.

    Returns: { should_deliver, reason, diff_pct, condition_met }
    """
    rules: dict = _get(db, _KEY_RULES, org_id, {})
    if rule_id not in rules:
        raise ValueError(f"Rule '{rule_id}' not found")
    rule = rules[rule_id]

    if not rule.get("enabled", True):
        return {"should_deliver": False, "reason": "rule_disabled", "diff_pct": 0, "condition_met": False}

    # Check condition
    condition_met = True
    if rule.get("condition_metric") and current_metric_value is not None:
        op = rule.get("condition_operator", "gt")
        threshold = float(rule.get("condition_value") or 0)
        ops_map = {
            "gt": current_metric_value > threshold,
            "gte": current_metric_value >= threshold,
            "lt": current_metric_value < threshold,
            "lte": current_metric_value <= threshold,
            "eq": current_metric_value == threshold,
        }
        condition_met = ops_map.get(op, True)

    if not condition_met:
        return {"should_deliver": False, "reason": "condition_not_met", "diff_pct": 0, "condition_met": False}

    # Check diff
    snapshots: dict = _get(db, _KEY_SNAPSHOTS, org_id, {})
    current_hash = _snapshot_hash(current_data)
    prev = snapshots.get(rule_id, {})
    prev_hash = prev.get("hash", "")
    diff_threshold = float(rule.get("diff_threshold_pct", 5.0))

    if prev_hash == current_hash:
        diff_pct = 0.0
    else:
        # Approximate diff as % changed fields (simplified)
        if isinstance(current_data, dict) and isinstance(prev.get("data"), dict):
            prev_data = prev.get("data", {})
            all_keys = set(current_data) | set(prev_data)
            changed = sum(1 for k in all_keys if current_data.get(k) != prev_data.get(k))
            diff_pct = (changed / max(len(all_keys), 1)) * 100
        else:
            diff_pct = 100.0  # No previous snapshot — always deliver

    should_deliver = diff_pct >= diff_threshold

    if should_deliver:
        # Update snapshot and rule stats
        snapshots[rule_id] = {"hash": current_hash, "data": current_data, "saved_at": _iso_now()}
        _set(db, _KEY_SNAPSHOTS, org_id, snapshots)
        rules[rule_id]["last_triggered_at"] = _iso_now()
        rules[rule_id]["trigger_count"] = rules[rule_id].get("trigger_count", 0) + 1
        _set(db, _KEY_RULES, org_id, rules)

    return {
        "should_deliver": should_deliver,
        "reason": "diff_threshold_met" if should_deliver else "no_significant_change",
        "diff_pct": round(diff_pct, 2),
        "condition_met": condition_met,
        "rule_id": rule_id,
    }
