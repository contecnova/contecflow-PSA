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
SHARED_VIEWS_KEY = "bi.phase3.shared_views"
VERSIONS_KEY_PREFIX = "bi.collab.versions."
SHARES_KEY_PREFIX = "bi.collab.shares."
CACHE_POLICY_KEY = "bi.collab.cache.policy"

SHARE_PERMISSIONS = {"view", "edit", "admin"}


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


def list_shared_views(
    db: Session,
    *,
    organization_id: Optional[str],
    only_active: bool = True,
) -> list[dict[str, Any]]:
    views = _get_json(db, SHARED_VIEWS_KEY, organization_id, default=[])
    if only_active:
        views = [v for v in views if v.get("active", True)]
    views.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return views


def create_shared_view(
    db: Session,
    *,
    organization_id: Optional[str],
    name: str,
    dashboard_key: str,
    filters: dict[str, Any] | None,
    created_by: User,
) -> dict[str, Any]:
    views = _get_json(db, SHARED_VIEWS_KEY, organization_id, default=[])
    payload = {
        "id": str(uuid.uuid4()),
        "name": name.strip(),
        "dashboard_key": dashboard_key,
        "filters": filters or {},
        "active": True,
        "created_at": _iso_now(),
        "created_by_id": created_by.id,
        "created_by_name": created_by.full_name,
    }
    views.append(payload)
    _set_json(
        db,
        SHARED_VIEWS_KEY,
        organization_id,
        views,
        description="BI Collaboration shared dashboard views (JSON)",
    )
    return payload


def patch_shared_view(
    db: Session,
    *,
    organization_id: Optional[str],
    view_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    views = _get_json(db, SHARED_VIEWS_KEY, organization_id, default=[])
    target = None
    for v in views:
        if v.get("id") == view_id:
            target = v
            break
    if target is None:
        raise ValueError("shared_view_not_found")

    if "name" in payload and payload["name"] is not None:
        target["name"] = str(payload["name"]).strip()
    if "dashboard_key" in payload and payload["dashboard_key"] is not None:
        target["dashboard_key"] = str(payload["dashboard_key"])
    if "filters" in payload and payload["filters"] is not None:
        target["filters"] = payload["filters"]
    if "active" in payload and payload["active"] is not None:
        target["active"] = bool(payload["active"])

    _set_json(
        db,
        SHARED_VIEWS_KEY,
        organization_id,
        views,
        description="BI Collaboration shared dashboard views (JSON)",
    )
    return target


# ── Dashboard Versioning ───────────────────────────────────────────────────────

def _versions_key(dashboard_key: str) -> str:
    return f"{VERSIONS_KEY_PREFIX}{dashboard_key}"


def list_dashboard_versions(
    db: Session,
    *,
    organization_id: Optional[str],
    dashboard_key: str,
) -> list[dict[str, Any]]:
    return _get_json(db, _versions_key(dashboard_key), organization_id, default=[])


def create_dashboard_version(
    db: Session,
    *,
    organization_id: Optional[str],
    dashboard_key: str,
    config: dict[str, Any],
    change_log: Optional[str],
    current_user: User,
) -> dict[str, Any]:
    versions = list_dashboard_versions(db, organization_id=organization_id, dashboard_key=dashboard_key)
    next_version = (max((v.get("version", 0) for v in versions), default=0) + 1)
    row: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "dashboard_key": dashboard_key,
        "version": next_version,
        "config": config,
        "change_log": (change_log or "").strip() or f"Versión {next_version}",
        "created_by_id": current_user.id,
        "created_by_name": current_user.full_name,
        "created_at": _iso_now(),
    }
    versions.append(row)
    # Keep last 50 versions
    versions = versions[-50:]
    _set_json(
        db,
        _versions_key(dashboard_key),
        organization_id,
        versions,
        description=f"BI dashboard versions for {dashboard_key}",
    )
    return row


def restore_dashboard_version(
    db: Session,
    *,
    organization_id: Optional[str],
    dashboard_key: str,
    version_id: str,
    current_user: User,
) -> dict[str, Any]:
    """Restore a previous version by creating a new version with the old config."""
    versions = list_dashboard_versions(db, organization_id=organization_id, dashboard_key=dashboard_key)
    target = next((v for v in versions if v.get("id") == version_id), None)
    if not target:
        raise ValueError("version_not_found")
    return create_dashboard_version(
        db,
        organization_id=organization_id,
        dashboard_key=dashboard_key,
        config=target["config"],
        change_log=f"Restaurado desde v{target['version']}",
        current_user=current_user,
    )


# ── Dashboard Sharing ─────────────────────────────────────────────────────────

def _shares_key(dashboard_key: str) -> str:
    return f"{SHARES_KEY_PREFIX}{dashboard_key}"


def list_dashboard_shares(
    db: Session,
    *,
    organization_id: Optional[str],
    dashboard_key: str,
) -> list[dict[str, Any]]:
    return _get_json(db, _shares_key(dashboard_key), organization_id, default=[])


def share_dashboard(
    db: Session,
    *,
    organization_id: Optional[str],
    dashboard_key: str,
    target_user_id: str,
    target_user_name: str,
    permission: str,
    shared_by: User,
) -> dict[str, Any]:
    if permission not in SHARE_PERMISSIONS:
        raise ValueError("invalid_permission")
    shares = list_dashboard_shares(db, organization_id=organization_id, dashboard_key=dashboard_key)
    # Upsert: if the user already has access, update their permission
    existing = next((s for s in shares if s.get("user_id") == target_user_id), None)
    now = _iso_now()
    if existing:
        existing["permission"] = permission
        existing["updated_at"] = now
        existing["updated_by_id"] = shared_by.id
        row = existing
    else:
        row = {
            "id": str(uuid.uuid4()),
            "dashboard_key": dashboard_key,
            "user_id": target_user_id,
            "user_name": target_user_name,
            "permission": permission,
            "shared_by_id": shared_by.id,
            "shared_by_name": shared_by.full_name,
            "created_at": now,
            "updated_at": now,
        }
        shares.append(row)
    _set_json(
        db,
        _shares_key(dashboard_key),
        organization_id,
        shares,
        description=f"BI dashboard sharing for {dashboard_key}",
    )
    return row


def revoke_dashboard_share(
    db: Session,
    *,
    organization_id: Optional[str],
    dashboard_key: str,
    share_id: str,
) -> bool:
    shares = list_dashboard_shares(db, organization_id=organization_id, dashboard_key=dashboard_key)
    new_shares = [s for s in shares if s.get("id") != share_id]
    if len(new_shares) == len(shares):
        return False
    _set_json(
        db,
        _shares_key(dashboard_key),
        organization_id,
        new_shares,
        description=f"BI dashboard sharing for {dashboard_key}",
    )
    return True


def get_cache_policy(db: Session, *, organization_id: Optional[str]) -> dict[str, Any]:
    default_policy = {
        "critical_refresh_seconds": 10,
        "normal_refresh_seconds": 60,
        "max_refresh_seconds": 300,
    }
    row = _get_json(db, CACHE_POLICY_KEY, organization_id, default={})
    return {**default_policy, **(row or {})}


def update_cache_policy(
    db: Session,
    *,
    organization_id: Optional[str],
    critical_refresh_seconds: Optional[int] = None,
) -> dict[str, Any]:
    policy = get_cache_policy(db, organization_id=organization_id)
    if critical_refresh_seconds is not None:
        policy["critical_refresh_seconds"] = max(5, min(10, int(critical_refresh_seconds)))
    _set_json(
        db,
        CACHE_POLICY_KEY,
        organization_id,
        policy,
        description="BI collaboration cache and realtime policy",
    )
    return policy


def dashboard_update_snapshot(
    db: Session,
    *,
    organization_id: Optional[str],
    dashboard_key: str,
) -> dict[str, Any]:
    versions = list_dashboard_versions(db, organization_id=organization_id, dashboard_key=dashboard_key)
    comments = list_comments(
        db,
        organization_id=organization_id,
        dashboard_key=dashboard_key,
        include_resolved=False,
    )
    shares = list_dashboard_shares(db, organization_id=organization_id, dashboard_key=dashboard_key)

    latest_version = max((v.get("version", 0) for v in versions), default=0)
    return {
        "type": "bi_dashboard_update",
        "dashboard_key": dashboard_key,
        "timestamp": _iso_now(),
        "latest_version": latest_version,
        "version_count": len(versions),
        "comment_count": len(comments),
        "share_count": len(shares),
        "recent_comments": comments[:5],
    }
