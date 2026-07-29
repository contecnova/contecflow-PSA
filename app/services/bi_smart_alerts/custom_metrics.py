"""Custom metrics CRUD for BI Smart Alerts."""
from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.user import User

from .constants import CUSTOM_METRICS_KEY, SUPPORTED_METRICS
from .persistence import _get_json, _iso_now, _set_json


def list_custom_metrics(db: Session, *, organization_id: Optional[str]) -> list[dict[str, Any]]:
    return _get_json(db, CUSTOM_METRICS_KEY, organization_id, default=[])


def create_custom_metric(
    db: Session,
    *,
    organization_id: Optional[str],
    payload: dict[str, Any],
    current_user: User,
) -> dict[str, Any]:
    customs = list_custom_metrics(db, organization_id=organization_id)
    label = str(payload.get("label", "")).strip()
    if not label:
        raise ValueError("label_required")
    operand_a = str(payload.get("operand_a", "")).strip()
    if operand_a not in SUPPORTED_METRICS:
        raise ValueError("invalid_operand_a")
    operator = str(payload.get("operator", "+"))
    if operator not in ("+", "-", "*", "/"):
        raise ValueError("invalid_operator")
    b_type = str(payload.get("operand_b_type", "constant"))
    operand_b = payload.get("operand_b", "0")
    if b_type == "metric" and str(operand_b) not in SUPPORTED_METRICS:
        raise ValueError("invalid_operand_b_metric")

    key = "custom_" + str(uuid.uuid4()).replace("-", "")[:8]
    row: dict[str, Any] = {
        "key": key,
        "label": label,
        "description": str(payload.get("description", "")),
        "formula": {
            "operand_a": operand_a,
            "operator": operator,
            "operand_b_type": b_type,
            "operand_b": str(operand_b),
            "scale": float(payload.get("scale", 1) or 1),
        },
        "created_at": _iso_now(),
        "created_by": current_user.id,
    }
    customs.append(row)
    _set_json(db, CUSTOM_METRICS_KEY, organization_id, customs, description="BI Custom Metrics (JSON)")
    return row


def delete_custom_metric(db: Session, *, organization_id: Optional[str], key: str) -> bool:
    customs = list_custom_metrics(db, organization_id=organization_id)
    new_customs = [c for c in customs if c.get("key") != key]
    if len(new_customs) == len(customs):
        return False
    _set_json(db, CUSTOM_METRICS_KEY, organization_id, new_customs, description="BI Custom Metrics (JSON)")
    return True
