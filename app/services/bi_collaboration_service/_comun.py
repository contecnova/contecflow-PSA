"""Claves de ajuste, JSON en ajustes, reloj y aviso de cambios en un panel.

Parte de `app.services.bi_collaboration_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import inspect
from app.models.bi_collaboration import DashboardNotification
from app.models.settings import AppSetting


logger = logging.getLogger("app.services.bi_collaboration_service")

COMMENTS_KEY = "bi.phase1.comments"
RULES_KEY = "bi.phase1.governance.rules"
LAST_RUN_KEY = "bi.phase1.governance.last_run"
SHARED_VIEWS_KEY = "bi.phase3.shared_views"
VERSIONS_KEY_PREFIX = "bi.collab.versions."
SHARES_KEY_PREFIX = "bi.collab.shares."
CACHE_POLICY_KEY = "bi.collab.cache.policy"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_json_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _from_json_value(value: str, default: Any) -> Any:
    try:
        return json.loads(value)
    except Exception:
        logger.warning("Error parseando JSON en BI collaboration setting", exc_info=True)
        return default


def _is_missing_table_error(exc: Exception, table_name: str) -> bool:
    message = str(exc).lower()
    return f"no such table: {table_name}" in message


def _table_exists(db: Session, table_name: str) -> bool:
    """Return True when the underlying DB has table_name available."""
    try:
        bind = db.get_bind()
        return table_name in inspect(bind).get_table_names()
    except Exception:
        logger.warning("Error inspeccionando existencia de tabla %s", table_name, exc_info=True)
        return False


def _emit_dashboard_notification(
    db: Session,
    *,
    organization_id: Optional[str],
    dashboard_key: str,
    event_type: str,
    payload: dict[str, Any],
    recipient_user_id: Optional[str] = None,
) -> None:
    db.add(
        DashboardNotification(
            organization_id=organization_id,
            dashboard_key=dashboard_key,
            event_type=event_type,
            recipient_user_id=recipient_user_id,
            payload_json=_to_json_value(payload),
        )
    )


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
        logger.warning("Error parseando JSON de AppSetting key=%s organization_id=%s", key, organization_id, exc_info=True)
        return default


def _set_json(db: Session, key: str, organization_id: Optional[str], value: Any, description: str) -> None:
    row = _setting_row(db, key, organization_id)
    if not row:
        row = AppSetting(
            key=key,
            organization_id=organization_id,
            description=description,
            value=_to_json_value(value),
        )
        db.add(row)
    else:
        row.value = _to_json_value(value)
        if not row.description:
            row.description = description
    db.commit()
