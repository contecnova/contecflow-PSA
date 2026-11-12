from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session

from app.models.settings import AppSetting
import logging

logger = logging.getLogger(__name__)


_DEFAULT_LAYOUTS = {
    "operation": {
        "widgets": [
            "my_queue_prioritized",
            "sla_at_risk",
            "mttr_trend",
            "major_incidents",
        ],
    },
    "manager": {
        "widgets": [
            "sla_compliance",
            "agent_performance",
            "backlog_by_priority",
            "csat_trend",
        ],
    },
    "executive": {
        "widgets": [
            "service_health",
            "monthly_volume",
            "cost_of_tickets",
            "risk_hotspots",
        ],
    },
}


def _key(role: str) -> str:
    return f"service_desk.dashboard_layout.{role}"


def get_layout(db: Session, organization_id: Optional[str], role: str) -> dict:
    setting = (
        db.query(AppSetting)
        .filter(AppSetting.organization_id == organization_id, AppSetting.key == _key(role))
        .first()
    )
    if not setting or not setting.value:
        return _DEFAULT_LAYOUTS.get(role, _DEFAULT_LAYOUTS["operation"])
    try:
        return json.loads(setting.value)
    except Exception:
        logger.debug("get_layout: excepcion ignorada", exc_info=True)
        return _DEFAULT_LAYOUTS.get(role, _DEFAULT_LAYOUTS["operation"])


def save_layout(db: Session, organization_id: Optional[str], role: str, layout: dict) -> dict:
    setting = (
        db.query(AppSetting)
        .filter(AppSetting.organization_id == organization_id, AppSetting.key == _key(role))
        .first()
    )
    if setting is None:
        setting = AppSetting(
            organization_id=organization_id,
            key=_key(role),
            value=json.dumps(layout),
            description=f"Service Desk dashboard layout for role {role}",
        )
        db.add(setting)
    else:
        setting.value = json.dumps(layout)
    db.flush()
    return layout
