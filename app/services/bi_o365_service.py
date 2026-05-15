"""
bi_o365_service.py — Office 365 productivity data → BI analytics.

Pulls O365 usage reports from Microsoft Graph and stores them as BI datasets:
  - Teams activity (messages, meetings, calls)
  - SharePoint usage (active sites, files, storage)
  - OneDrive usage
  - Email activity (send/receive counts)
  - User adoption metrics

All data stored as AppSetting JSON blobs (no new DB tables).
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.settings import AppSetting

logger = logging.getLogger(__name__)

_CONFIG_KEY = "bi.o365.config"
_DATA_KEY_TPL = "bi.o365.data.{report}"
_SYNC_LOG_KEY = "bi.o365.sync_log"

_SUPPORTED_REPORTS = [
    "teams_activity",
    "sharepoint_activity",
    "onedrive_activity",
    "email_activity",
    "user_adoption",
]

_DEFAULT_CONFIG: Dict[str, Any] = {
    "tenant_id": "",
    "client_id": "",
    "enabled": True,
    "client_secret_ref": "o365_client_secret",  # key in secrets vault (not stored here)
    "sync_period": "D7",  # D7 | D30 | D90 | D180
    "enabled_reports": _SUPPORTED_REPORTS,
    "last_sync_at": None,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_json(db: Session, key: str, org_id: Optional[str], *, default=None):
    q = db.query(AppSetting).filter(AppSetting.key == key)
    if org_id:
        q = q.filter(AppSetting.organization_id == org_id)
    else:
        q = q.filter(AppSetting.organization_id.is_(None))
    row = q.first()
    if not row or not row.value:
        return default
    try:
        return json.loads(row.value)
    except Exception:
        logger.warning("Failed to decode O365 AppSetting JSON key=%s org=%s", key, org_id, exc_info=True)
        return default


def _set_json(db: Session, key: str, org_id: Optional[str], value: Any, desc: str = "") -> None:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    q = db.query(AppSetting).filter(AppSetting.key == key)
    if org_id:
        q = q.filter(AppSetting.organization_id == org_id)
    else:
        q = q.filter(AppSetting.organization_id.is_(None))
    row = q.first()
    if not row:
        row = AppSetting(key=key, organization_id=org_id, description=desc, value=payload)
        db.add(row)
    else:
        row.value = payload
    db.commit()


# ── Microsoft Graph helpers ───────────────────────────────────────────────────

def _get_graph_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    """Obtain an OAuth2 token from Microsoft Identity (client credentials flow)."""
    try:
        import httpx
        url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
        }
        with httpx.Client(timeout=15) as client:
            resp = client.post(url, data=data)
            resp.raise_for_status()
            return resp.json()["access_token"]
    except Exception as exc:
        logger.warning("_get_graph_token failed: %s", exc)
        raise


def _fetch_graph_report(token: str, report_name: str, period: str) -> List[Dict[str, Any]]:
    """Fetch a usage report from Microsoft Graph Reports API."""
    _GRAPH_REPORT_MAP = {
        "teams_activity": f"getTeamsUserActivityUserDetail(period='{period}')",
        "sharepoint_activity": f"getSharePointActivityUserDetail(period='{period}')",
        "onedrive_activity": f"getOneDriveActivityUserDetail(period='{period}')",
        "email_activity": f"getEmailActivityUserDetail(period='{period}')",
        "user_adoption": f"getOffice365ActiveUserDetail(period='{period}')",
    }
    path = _GRAPH_REPORT_MAP.get(report_name)
    if not path:
        return []
    try:
        import httpx, csv, io
        url = f"https://graph.microsoft.com/v1.0/reports/{path}"
        headers = {"Authorization": f"Bearer {token}"}
        with httpx.Client(timeout=30) as client:
            resp = client.get(url, headers=headers, follow_redirects=True)
            resp.raise_for_status()
            # Graph reports return CSV
            reader = csv.DictReader(io.StringIO(resp.text))
            return [dict(row) for row in reader]
    except Exception as exc:
        logger.warning("_fetch_graph_report %s failed: %s", report_name, exc)
        return []


# ── Public API ────────────────────────────────────────────────────────────────

def get_config(db: Session, org_id: Optional[str]) -> Dict[str, Any]:
    cfg = _get_json(db, _CONFIG_KEY, org_id, default={}) or {}
    # Never expose secret
    merged = {**_DEFAULT_CONFIG, **cfg}
    merged.pop("client_secret_ref", None)
    merged.pop("client_secret", None)
    return merged


def save_config(db: Session, org_id: Optional[str], updates: Dict[str, Any]) -> Dict[str, Any]:
    cfg = _get_json(db, _CONFIG_KEY, org_id, default=_DEFAULT_CONFIG) or _DEFAULT_CONFIG
    # Keep client_secret internally for runtime sync compatibility; never expose it.
    if "client_secret" in updates and not updates.get("client_secret"):
        updates.pop("client_secret", None)
    cfg.update(updates)
    _set_json(db, _CONFIG_KEY, org_id, cfg, "O365 BI connector configuration")
    return get_config(db, org_id)


def run_sync(
    db: Session,
    org_id: Optional[str],
    reports: Optional[List[str]] = None,
    *,
    client_secret: Optional[str] = None,
) -> Dict[str, Any]:
    """Pull O365 usage data and store to BI blobs. Returns sync summary."""
    cfg = _get_json(db, _CONFIG_KEY, org_id, default=_DEFAULT_CONFIG) or _DEFAULT_CONFIG
    if not cfg.get("enabled", True):
        return {"ok": False, "error": "connector_disabled", "synced": []}

    tenant_id = cfg.get("tenant_id", "")
    client_id = cfg.get("client_id", "")
    period = cfg.get("sync_period", "D7")

    if not tenant_id or not client_id:
        return {"ok": False, "error": "tenant_id / client_id not configured", "synced": []}

    target_reports = reports or cfg.get("enabled_reports", _SUPPORTED_REPORTS)
    results = []

    try:
        secret = client_secret or cfg.get("client_secret") or ""
        if not secret:
            return {"ok": False, "error": "client_secret required for sync", "synced": []}
        token = _get_graph_token(tenant_id, client_id, secret)
    except Exception as exc:
        logger.exception("O365 Graph auth failed for tenant=%s client=%s", tenant_id, client_id)
        return {"ok": False, "error": f"Authentication failed: {exc}", "synced": []}

    for report_name in target_reports:
        try:
            rows = _fetch_graph_report(token, report_name, period)
            key = _DATA_KEY_TPL.format(report=report_name)
            _set_json(db, key, org_id, {"rows": rows, "fetched_at": _now_iso(), "count": len(rows)}, f"O365 {report_name} data")
            results.append({"report": report_name, "ok": True, "records": len(rows)})
        except Exception as exc:
            logger.exception("O365 report sync failed for report=%s org=%s", report_name, org_id)
            results.append({"report": report_name, "ok": False, "error": str(exc)})

    # Update last_sync_at
    cfg["last_sync_at"] = _now_iso()
    _set_json(db, _CONFIG_KEY, org_id, cfg, "O365 BI connector configuration")

    # Append to sync log
    log = _get_json(db, _SYNC_LOG_KEY, org_id, default=[]) or []
    log.append({"run_id": str(uuid.uuid4()), "ts": _now_iso(), "results": results})
    if len(log) > 50:
        log = log[-50:]
    _set_json(db, _SYNC_LOG_KEY, org_id, log, "O365 sync log")

    return {"ok": True, "synced": results, "period": period}


def get_report_data(db: Session, org_id: Optional[str], report_name: str) -> Dict[str, Any]:
    if report_name not in _SUPPORTED_REPORTS:
        raise ValueError(f"Unknown report: {report_name!r}")
    key = _DATA_KEY_TPL.format(report=report_name)
    data = _get_json(db, key, org_id, default={}) or {}
    return {
        "report": report_name,
        "rows": data.get("rows", []),
        "count": data.get("count", 0),
        "fetched_at": data.get("fetched_at"),
    }


def get_sync_log(db: Session, org_id: Optional[str], limit: int = 20) -> List[Dict[str, Any]]:
    log = _get_json(db, _SYNC_LOG_KEY, org_id, default=[]) or []
    return log[-limit:]


def get_adoption_summary(db: Session, org_id: Optional[str]) -> Dict[str, Any]:
    """Return aggregated adoption metrics from user_adoption report data."""
    data = get_report_data(db, org_id, "user_adoption")
    rows = data.get("rows", [])
    if not rows:
        return {"active_users": 0, "products": {}, "note": "No data synced yet"}
    active_users = sum(1 for r in rows if r.get("Has Any Product", "") == "True")
    products = ["Exchange", "OneDrive", "SharePoint", "Skype For Business", "Yammer", "Teams"]
    product_counts = {}
    for prod in products:
        key = f"Is Licensed For {prod}"
        product_counts[prod] = sum(1 for r in rows if r.get(key, "") == "True")
    return {
        "total_users": len(rows),
        "active_users": active_users,
        "adoption_rate": round(active_users / len(rows) * 100, 1) if rows else 0,
        "by_product": product_counts,
        "fetched_at": data.get("fetched_at"),
    }
