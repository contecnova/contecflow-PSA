"""Tenant-aware traffic control helpers.

Stores lightweight counters in AppSetting JSON to enforce
per-tenant/per-scope rate limits without schema migrations.
"""

from __future__ import annotations
import logging

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.settings import AppSetting


def _bucket_now(window_seconds: int) -> int:
    now_ts = int(datetime.now(timezone.utc).timestamp())
    return now_ts - (now_ts % max(window_seconds, 1))


def _key(scope: str, tenant_id: Optional[str], subject: str) -> str:
    tenant = tenant_id or "global"
    return f"traffic.ctrl.{scope}.{tenant}.{subject}"


def consume_quota(
    db: Session,
    *,
    scope: str,
    tenant_id: Optional[str],
    subject: str,
    limit: int,
    window_seconds: int = 60,
) -> dict:
    """Consume one unit from a per-scope quota.

    Returns: {allowed, retry_after, remaining, limit, count, window_start}
    """
    app_key = _key(scope, tenant_id, subject)
    current_bucket = _bucket_now(window_seconds)

    row = db.query(AppSetting).filter(AppSetting.key == app_key).first()
    if row and row.value:
        try:
            payload = json.loads(row.value)
        except Exception:
            logging.getLogger(__name__).debug("consume_quota: excepcion ignorada", exc_info=True)
            payload = {"window_start": current_bucket, "count": 0}
    else:
        payload = {"window_start": current_bucket, "count": 0}

    window_start = int(payload.get("window_start") or current_bucket)
    count = int(payload.get("count") or 0)

    if window_start != current_bucket:
        window_start = current_bucket
        count = 0

    allowed = count < max(limit, 1)
    if allowed:
        count += 1
        payload = {"window_start": window_start, "count": count}
        serialized = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        if not row:
            row = AppSetting(
                key=app_key,
                organization_id=tenant_id,
                description=f"Traffic counter for {scope}:{subject}",
                value=serialized,
            )
            db.add(row)
        else:
            row.value = serialized
        db.commit()

    now_ts = int(datetime.now(timezone.utc).timestamp())
    retry_after = max(0, (window_start + window_seconds) - now_ts)

    return {
        "allowed": allowed,
        "retry_after": retry_after,
        "remaining": max(0, limit - count),
        "limit": limit,
        "count": count,
        "window_start": window_start,
    }
