"""BI Collaboration service orchestration.

Provides a lightweight collaboration + governance layer for BI dashboards
without introducing new tables. Data is persisted in AppSetting JSON blobs,
scoped by organization for multi-tenant isolation.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.settings import AppSetting
from app.models.user import User
from app.services.analytics_service import METRIC_CACHE_TTL
from app.services.scheduled_reports_compat import summarize_scheduled_reports

COMMENTS_KEY = "bi.phase1.comments"
RULES_KEY = "bi.phase1.governance.rules"
LAST_RUN_KEY = "bi.phase1.governance.last_run"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_json_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


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


def list_comments(
    db: Session,
    *,
    organization_id: Optional[str],
    dashboard_key: Optional[str] = None,
    widget_id: Optional[str] = None,
    include_resolved: bool = False,
) -> list[dict[str, Any]]:
    comments = _get_json(db, COMMENTS_KEY, organization_id, default=[])
    out: list[dict[str, Any]] = []
    for item in comments:
        if dashboard_key and item.get("dashboard_key") != dashboard_key:
            continue
        if widget_id and item.get("widget_id") != widget_id:
            continue
        if not include_resolved and item.get("resolved"):
            continue
        out.append(item)
    out.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return out


def create_comment(
    db: Session,
    *,
    organization_id: Optional[str],
    dashboard_key: str,
    widget_id: str,
    message: str,
    author: User,
) -> dict[str, Any]:
    comments = _get_json(db, COMMENTS_KEY, organization_id, default=[])
    payload = {
        "id": str(uuid.uuid4()),
        "dashboard_key": dashboard_key,
        "widget_id": widget_id,
        "message": message.strip(),
        "author_id": author.id,
        "author_name": author.full_name,
        "resolved": False,
        "resolved_at": None,
        "resolved_by": None,
        "created_at": _iso_now(),
    }
    comments.append(payload)
    _set_json(
        db,
        COMMENTS_KEY,
        organization_id,
        comments,
        description="BI Collaboration collaboration comments (JSON)",
    )
    return payload


def resolve_comment(
    db: Session,
    *,
    organization_id: Optional[str],
    comment_id: str,
    current_user: User,
) -> dict[str, Any]:
    comments = _get_json(db, COMMENTS_KEY, organization_id, default=[])
    target: Optional[dict[str, Any]] = None
    for item in comments:
        if item.get("id") == comment_id:
            item["resolved"] = True
            item["resolved_at"] = _iso_now()
            item["resolved_by"] = current_user.full_name
            target = item
            break
    if target is None:
        raise ValueError("comment_not_found")
    _set_json(
        db,
        COMMENTS_KEY,
        organization_id,
        comments,
        description="BI Collaboration collaboration comments (JSON)",
    )
    return target


def default_governance_rules() -> dict[str, Any]:
    return {
        "olap_max_staleness_hours": 26,
        "max_error_reports": 0,
        "require_active_schedules": True,
    }


def get_governance_rules(db: Session, *, organization_id: Optional[str]) -> dict[str, Any]:
    return _get_json(db, RULES_KEY, organization_id, default=default_governance_rules())


def update_governance_rules(
    db: Session,
    *,
    organization_id: Optional[str],
    payload: dict[str, Any],
) -> dict[str, Any]:
    merged = {**default_governance_rules(), **(payload or {})}
    _set_json(
        db,
        RULES_KEY,
        organization_id,
        merged,
        description="BI Collaboration governance rules (JSON)",
    )
    return merged


def governance_overview(db: Session, *, organization_id: Optional[str]) -> dict[str, Any]:
    try:
        from app.services.olap.etl import DUCKDB_PATH
    except Exception:
        DUCKDB_PATH = ""

    duckdb_exists = bool(DUCKDB_PATH and os.path.exists(DUCKDB_PATH))
    staleness_hours: Optional[float] = None
    if duckdb_exists:
        mtime = datetime.fromtimestamp(os.path.getmtime(DUCKDB_PATH), tz=timezone.utc)
        staleness_hours = round((datetime.now(timezone.utc) - mtime).total_seconds() / 3600.0, 2)

    report_stats = summarize_scheduled_reports(db)
    active_scheduled_reports = int(report_stats.get("active", 0))
    error_scheduled_reports = int(report_stats.get("errored", 0))

    unresolved_comments = len(
        list_comments(db, organization_id=organization_id, include_resolved=False)
    )

    ttl_stats = {
        "metric_count": len(METRIC_CACHE_TTL),
        "default_ttl_seconds": 300,
        "min_ttl_seconds": min(METRIC_CACHE_TTL.values()) if METRIC_CACHE_TTL else 300,
        "max_ttl_seconds": max(METRIC_CACHE_TTL.values()) if METRIC_CACHE_TTL else 300,
    }

    return {
        "timestamp": _iso_now(),
        "olap": {
            "path": DUCKDB_PATH,
            "available": duckdb_exists,
            "staleness_hours": staleness_hours,
        },
        "scheduled_reports": {
            "active": active_scheduled_reports,
            "error": error_scheduled_reports,
        },
        "collaboration": {
            "unresolved_comments": unresolved_comments,
        },
        "cache_policy": ttl_stats,
    }


def run_governance_checks(db: Session, *, organization_id: Optional[str]) -> dict[str, Any]:
    rules = get_governance_rules(db, organization_id=organization_id)
    overview = governance_overview(db, organization_id=organization_id)

    findings: list[dict[str, Any]] = []

    olap_info = overview["olap"]
    if not olap_info.get("available"):
        findings.append({
            "code": "OLAP_UNAVAILABLE",
            "severity": "critical",
            "message": "DuckDB OLAP no disponible",
        })
    else:
        staleness_hours = olap_info.get("staleness_hours")
        max_staleness = float(rules.get("olap_max_staleness_hours", 26))
        if staleness_hours is not None and staleness_hours > max_staleness:
            findings.append({
                "code": "OLAP_STALE",
                "severity": "warning",
                "message": f"OLAP stale ({staleness_hours}h > {max_staleness}h)",
            })

    reports = overview["scheduled_reports"]
    max_error_reports = int(rules.get("max_error_reports", 0))
    if int(reports.get("error", 0)) > max_error_reports:
        findings.append({
            "code": "SCHEDULED_REPORT_ERRORS",
            "severity": "warning",
            "message": "Hay informes programados en error",
        })

    require_active = bool(rules.get("require_active_schedules", True))
    if require_active and int(reports.get("active", 0)) == 0:
        findings.append({
            "code": "NO_ACTIVE_SCHEDULES",
            "severity": "warning",
            "message": "No hay informes programados activos",
        })

    status = "ok" if not findings else "attention"
    result = {
        "timestamp": _iso_now(),
        "status": status,
        "finding_count": len(findings),
        "findings": findings,
        "overview": overview,
        "rules": rules,
    }

    _set_json(
        db,
        LAST_RUN_KEY,
        organization_id,
        result,
        description="BI Collaboration governance latest run (JSON)",
    )
    return result


def get_last_governance_run(db: Session, *, organization_id: Optional[str]) -> dict[str, Any] | None:
    return _get_json(db, LAST_RUN_KEY, organization_id, default=None)
