"""Reglas de gobierno de paneles, comprobaciones y politica de cache.

Parte de `app.services.bi_collaboration_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional
from sqlalchemy.orm import Session
from app.services.analytics_service import METRIC_CACHE_TTL
from app.services.scheduled_reports_compat import summarize_scheduled_reports

from app.services.bi_collaboration_service._comun import (
    CACHE_POLICY_KEY,
    LAST_RUN_KEY,
    RULES_KEY,
    _get_json,
    _iso_now,
    _set_json,
    logger,
)
from app.services.bi_collaboration_service.comentarios import list_comments


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
        logger.warning("Error importando DUCKDB_PATH desde olap.etl", exc_info=True)
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
