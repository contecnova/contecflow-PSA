"""BI Collaboration service orchestration.

Collaboration state (comments, versions, shares, notifications) is persisted
in relational tables. Governance and cache policy keep using AppSetting JSON
for now to preserve backward compatibility with existing runtime configs.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func, inspect
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.models.bi_collaboration import (
    DashboardComment,
    DashboardNotification,
    DashboardShare,
    DashboardVersion,
)
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


def _from_json_value(value: str, default: Any) -> Any:
    try:
        return json.loads(value)
    except Exception:
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
        return False


def _legacy_list_comments(
    db: Session,
    *,
    organization_id: Optional[str],
    dashboard_key: Optional[str] = None,
    widget_id: Optional[str] = None,
    include_resolved: bool = False,
) -> list[dict[str, Any]]:
    rows = _get_json(db, COMMENTS_KEY, organization_id, default=[])
    if not isinstance(rows, list):
        rows = []

    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if dashboard_key and row.get("dashboard_key") != dashboard_key:
            continue
        if widget_id and row.get("widget_id") != widget_id:
            continue
        if not include_resolved and bool(row.get("resolved", False)):
            continue
        out.append({
            "id": row.get("id") or str(uuid.uuid4()),
            "dashboard_key": row.get("dashboard_key"),
            "widget_id": row.get("widget_id"),
            "message": row.get("message") or "",
            "author_id": row.get("author_id"),
            "author_name": row.get("author_name"),
            "resolved": bool(row.get("resolved", False)),
            "resolved_at": row.get("resolved_at"),
            "resolved_by": row.get("resolved_by"),
            "created_at": row.get("created_at"),
        })

    out.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return out


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
    if not _table_exists(db, "dashboard_comments"):
        return _legacy_list_comments(
            db,
            organization_id=organization_id,
            dashboard_key=dashboard_key,
            widget_id=widget_id,
            include_resolved=include_resolved,
        )

    try:
        q = db.query(DashboardComment)
        if organization_id:
            q = q.filter(DashboardComment.organization_id == organization_id)
        else:
            q = q.filter(DashboardComment.organization_id.is_(None))
        if dashboard_key:
            q = q.filter(DashboardComment.dashboard_key == dashboard_key)
        if widget_id:
            q = q.filter(DashboardComment.widget_id == widget_id)
        if not include_resolved:
            q = q.filter(DashboardComment.resolved.is_(False))
        rows = q.order_by(DashboardComment.created_at.desc()).all()
        return [
            {
                "id": r.id,
                "dashboard_key": r.dashboard_key,
                "widget_id": r.widget_id,
                "message": r.message,
                "author_id": r.author_id,
                "author_name": r.author_name,
                "resolved": bool(r.resolved),
                "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
                "resolved_by": r.resolved_by,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    except (OperationalError, ProgrammingError) as exc:
        if not _is_missing_table_error(exc, "dashboard_comments"):
            raise
        return _legacy_list_comments(
            db,
            organization_id=organization_id,
            dashboard_key=dashboard_key,
            widget_id=widget_id,
            include_resolved=include_resolved,
        )


def create_comment(
    db: Session,
    *,
    organization_id: Optional[str],
    dashboard_key: str,
    widget_id: str,
    message: str,
    author: User,
) -> dict[str, Any]:
    if not _table_exists(db, "dashboard_comments"):
        legacy_rows = _get_json(db, COMMENTS_KEY, organization_id, default=[])
        if not isinstance(legacy_rows, list):
            legacy_rows = []
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
        legacy_rows.append(payload)
        _set_json(
            db,
            COMMENTS_KEY,
            organization_id,
            legacy_rows,
            description="BI Collaboration comments (legacy JSON fallback)",
        )
        return payload

    try:
        row = DashboardComment(
            organization_id=organization_id,
            dashboard_key=dashboard_key,
            widget_id=widget_id,
            message=message.strip(),
            author_id=author.id,
            author_name=author.full_name,
            resolved=False,
        )
        db.add(row)
        _emit_dashboard_notification(
            db,
            organization_id=organization_id,
            dashboard_key=dashboard_key,
            event_type="comment_created",
            payload={"widget_id": widget_id, "author_id": author.id, "message": row.message[:200]},
        )
        db.commit()
        return {
            "id": row.id,
            "dashboard_key": row.dashboard_key,
            "widget_id": row.widget_id,
            "message": row.message,
            "author_id": row.author_id,
            "author_name": row.author_name,
            "resolved": False,
            "resolved_at": None,
            "resolved_by": None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
    except (OperationalError, ProgrammingError) as exc:
        if not _is_missing_table_error(exc, "dashboard_comments"):
            raise
        db.rollback()
        legacy_rows = _get_json(db, COMMENTS_KEY, organization_id, default=[])
        if not isinstance(legacy_rows, list):
            legacy_rows = []
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
        legacy_rows.append(payload)
        _set_json(
            db,
            COMMENTS_KEY,
            organization_id,
            legacy_rows,
            description="BI Collaboration comments (legacy JSON fallback)",
        )
        return payload


def resolve_comment(
    db: Session,
    *,
    organization_id: Optional[str],
    comment_id: str,
    current_user: User,
) -> dict[str, Any]:
    if not _table_exists(db, "dashboard_comments"):
        legacy_rows = _get_json(db, COMMENTS_KEY, organization_id, default=[])
        if not isinstance(legacy_rows, list):
            legacy_rows = []
        now = _iso_now()
        for row in legacy_rows:
            if not isinstance(row, dict):
                continue
            if row.get("id") != comment_id:
                continue
            row["resolved"] = True
            row["resolved_at"] = now
            row["resolved_by"] = current_user.full_name
            _set_json(
                db,
                COMMENTS_KEY,
                organization_id,
                legacy_rows,
                description="BI Collaboration comments (legacy JSON fallback)",
            )
            return {
                "id": row.get("id"),
                "dashboard_key": row.get("dashboard_key"),
                "widget_id": row.get("widget_id"),
                "message": row.get("message") or "",
                "author_id": row.get("author_id"),
                "author_name": row.get("author_name"),
                "resolved": True,
                "resolved_at": row.get("resolved_at"),
                "resolved_by": row.get("resolved_by"),
                "created_at": row.get("created_at"),
            }
        raise ValueError("comment_not_found")

    try:
        q = db.query(DashboardComment).filter(DashboardComment.id == comment_id)
        if organization_id:
            q = q.filter(DashboardComment.organization_id == organization_id)
        else:
            q = q.filter(DashboardComment.organization_id.is_(None))
        row = q.first()
        if row is None:
            raise ValueError("comment_not_found")
        row.resolved = True
        row.resolved_at = datetime.now(timezone.utc)
        row.resolved_by = current_user.full_name
        _emit_dashboard_notification(
            db,
            organization_id=organization_id,
            dashboard_key=row.dashboard_key,
            event_type="comment_resolved",
            payload={"comment_id": row.id, "resolved_by": current_user.id},
        )
        db.commit()
        return {
            "id": row.id,
            "dashboard_key": row.dashboard_key,
            "widget_id": row.widget_id,
            "message": row.message,
            "author_id": row.author_id,
            "author_name": row.author_name,
            "resolved": bool(row.resolved),
            "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
            "resolved_by": row.resolved_by,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
    except (OperationalError, ProgrammingError) as exc:
        if not _is_missing_table_error(exc, "dashboard_comments"):
            raise
        db.rollback()
        legacy_rows = _get_json(db, COMMENTS_KEY, organization_id, default=[])
        if not isinstance(legacy_rows, list):
            legacy_rows = []
        now = _iso_now()
        for row in legacy_rows:
            if not isinstance(row, dict):
                continue
            if row.get("id") != comment_id:
                continue
            row["resolved"] = True
            row["resolved_at"] = now
            row["resolved_by"] = current_user.full_name
            _set_json(
                db,
                COMMENTS_KEY,
                organization_id,
                legacy_rows,
                description="BI Collaboration comments (legacy JSON fallback)",
            )
            return {
                "id": row.get("id"),
                "dashboard_key": row.get("dashboard_key"),
                "widget_id": row.get("widget_id"),
                "message": row.get("message") or "",
                "author_id": row.get("author_id"),
                "author_name": row.get("author_name"),
                "resolved": True,
                "resolved_at": row.get("resolved_at"),
                "resolved_by": row.get("resolved_by"),
                "created_at": row.get("created_at"),
            }
        raise ValueError("comment_not_found")


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
    q = db.query(DashboardVersion).filter(DashboardVersion.dashboard_key == dashboard_key)
    if organization_id:
        q = q.filter(DashboardVersion.organization_id == organization_id)
    else:
        q = q.filter(DashboardVersion.organization_id.is_(None))
    rows = q.order_by(DashboardVersion.version.desc()).all()
    return [
        {
            "id": r.id,
            "dashboard_key": r.dashboard_key,
            "version": int(r.version or 0),
            "config": _from_json_value(r.config or "{}", {}),
            "change_log": r.change_log,
            "created_by_id": r.created_by_id,
            "created_by_name": r.created_by_name,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


def create_dashboard_version(
    db: Session,
    *,
    organization_id: Optional[str],
    dashboard_key: str,
    config: dict[str, Any],
    change_log: Optional[str],
    current_user: User,
) -> dict[str, Any]:
    q = db.query(func.max(DashboardVersion.version)).filter(DashboardVersion.dashboard_key == dashboard_key)
    if organization_id:
        q = q.filter(DashboardVersion.organization_id == organization_id)
    else:
        q = q.filter(DashboardVersion.organization_id.is_(None))
    max_ver = q.scalar() or 0
    next_version = int(max_ver) + 1

    row = DashboardVersion(
        organization_id=organization_id,
        dashboard_key=dashboard_key,
        version=next_version,
        config=_to_json_value(config or {}),
        change_log=(change_log or "").strip() or f"Versión {next_version}",
        created_by_id=current_user.id,
        created_by_name=current_user.full_name,
    )
    db.add(row)
    _emit_dashboard_notification(
        db,
        organization_id=organization_id,
        dashboard_key=dashboard_key,
        event_type="version_created",
        payload={"version": next_version, "created_by": current_user.id},
    )

    db.flush()
    # Keep last 50 versions per dashboard+organization.
    trim_q = db.query(DashboardVersion).filter(DashboardVersion.dashboard_key == dashboard_key)
    if organization_id:
        trim_q = trim_q.filter(DashboardVersion.organization_id == organization_id)
    else:
        trim_q = trim_q.filter(DashboardVersion.organization_id.is_(None))
    stale = trim_q.order_by(DashboardVersion.version.desc()).offset(50).all()
    for old in stale:
        db.delete(old)
    db.commit()
    return {
        "id": row.id,
        "dashboard_key": row.dashboard_key,
        "version": row.version,
        "config": _from_json_value(row.config or "{}", {}),
        "change_log": row.change_log,
        "created_by_id": row.created_by_id,
        "created_by_name": row.created_by_name,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


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
    q = db.query(DashboardShare).filter(DashboardShare.dashboard_key == dashboard_key)
    if organization_id:
        q = q.filter(DashboardShare.organization_id == organization_id)
    else:
        q = q.filter(DashboardShare.organization_id.is_(None))
    rows = q.order_by(DashboardShare.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "dashboard_key": r.dashboard_key,
            "user_id": r.user_id,
            "user_name": r.user_name,
            "permission": r.permission,
            "shared_by_id": r.shared_by_id,
            "shared_by_name": r.shared_by_name,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]


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
    q = db.query(DashboardShare).filter(
        DashboardShare.dashboard_key == dashboard_key,
        DashboardShare.user_id == target_user_id,
    )
    if organization_id:
        q = q.filter(DashboardShare.organization_id == organization_id)
    else:
        q = q.filter(DashboardShare.organization_id.is_(None))
    row = q.first()
    now = datetime.now(timezone.utc)
    if row:
        row.permission = permission
        row.updated_at = now
        row.user_name = target_user_name
    else:
        row = DashboardShare(
            organization_id=organization_id,
            dashboard_key=dashboard_key,
            user_id=target_user_id,
            user_name=target_user_name,
            permission=permission,
            shared_by_id=shared_by.id,
            shared_by_name=shared_by.full_name,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    _emit_dashboard_notification(
        db,
        organization_id=organization_id,
        dashboard_key=dashboard_key,
        event_type="share_updated",
        payload={"user_id": target_user_id, "permission": permission, "shared_by": shared_by.id},
        recipient_user_id=target_user_id,
    )
    db.commit()
    return {
        "id": row.id,
        "dashboard_key": row.dashboard_key,
        "user_id": row.user_id,
        "user_name": row.user_name,
        "permission": row.permission,
        "shared_by_id": row.shared_by_id,
        "shared_by_name": row.shared_by_name,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def revoke_dashboard_share(
    db: Session,
    *,
    organization_id: Optional[str],
    dashboard_key: str,
    share_id: str,
) -> bool:
    q = db.query(DashboardShare).filter(
        DashboardShare.id == share_id,
        DashboardShare.dashboard_key == dashboard_key,
    )
    if organization_id:
        q = q.filter(DashboardShare.organization_id == organization_id)
    else:
        q = q.filter(DashboardShare.organization_id.is_(None))
    row = q.first()
    if row is None:
        return False
    target_user_id = row.user_id
    db.delete(row)
    _emit_dashboard_notification(
        db,
        organization_id=organization_id,
        dashboard_key=dashboard_key,
        event_type="share_revoked",
        payload={"share_id": share_id, "user_id": target_user_id},
        recipient_user_id=target_user_id,
    )
    db.commit()
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
