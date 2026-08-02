"""Compatibility helpers for scheduled_reports reads.

Some local SQLite databases can be behind migrations and miss newer columns
(e.g. report_type). ORM entity loads would then fail with OperationalError.
This module reads only columns that actually exist in the table.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def summarize_scheduled_reports(db: Session) -> dict[str, Any]:
    """Return safe aggregates from scheduled_reports, tolerating schema drift."""
    try:
        pragma_rows = db.execute(text("PRAGMA table_info('scheduled_reports')")).fetchall()
    except Exception:
        return {
            "total": 0,
            "active": 0,
            "errored": 0,
            "with_slack": 0,
            "by_frequency": {},
        }

    columns = {row[1] for row in pragma_rows}
    if not columns:
        return {
            "total": 0,
            "active": 0,
            "errored": 0,
            "with_slack": 0,
            "by_frequency": {},
        }

    # Read only available columns to avoid selecting missing ones.
    select_cols = []
    for col in ("is_active", "last_status", "slack_webhook", "frequency"):
        if col in columns:
            select_cols.append(col)

    if not select_cols:
        # Table exists but none of the expected columns are available.
        return {
            "total": 0,
            "active": 0,
            "errored": 0,
            "with_slack": 0,
            "by_frequency": {},
        }

    query = f"SELECT {', '.join(select_cols)} FROM scheduled_reports"  # noqa: S608
    rows = db.execute(text(query)).fetchall()

    total = len(rows)
    active = 0
    errored = 0
    with_slack = 0
    by_frequency: dict[str, int] = defaultdict(int)

    for row in rows:
        data = dict(row._mapping)

        is_active_raw = data.get("is_active", 1)
        is_active = bool(is_active_raw)
        if is_active:
            active += 1

        if data.get("last_status") == "error":
            errored += 1

        if data.get("slack_webhook"):
            with_slack += 1

        freq = data.get("frequency") or "unknown"
        by_frequency[str(freq)] += 1

    return {
        "total": total,
        "active": active,
        "errored": errored,
        "with_slack": with_slack,
        "by_frequency": dict(by_frequency),
    }
