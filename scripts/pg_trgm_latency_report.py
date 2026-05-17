#!/usr/bin/env python3
"""Collect p95/p99 latency metrics for LIKE/ILIKE queries from pg_stat_statements.

Usage:
  DATABASE_URL=postgresql+psycopg://user:pass@host/db \
    venv/bin/python scripts/pg_trgm_latency_report.py --window-minutes 120
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

from sqlalchemy import create_engine, text


REPORT_SQL = text(
    """
    SELECT
      queryid,
      calls,
      round(total_exec_time::numeric, 3) AS total_exec_ms,
      round(mean_exec_time::numeric, 3) AS mean_exec_ms,
      round(min_exec_time::numeric, 3) AS min_exec_ms,
      round(max_exec_time::numeric, 3) AS max_exec_ms,
      round(stddev_exec_time::numeric, 3) AS stddev_exec_ms,
      left(regexp_replace(query, E'\\s+', ' ', 'g'), 240) AS sample_query
    FROM pg_stat_statements
    WHERE (
      lower(query) LIKE '% like %' OR
      lower(query) LIKE '% ilike %'
    )
    ORDER BY mean_exec_time DESC
    LIMIT :limit
    """
)

RESET_SQL = text("SELECT pg_stat_statements_reset()")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate pg_trgm latency report")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"), help="PostgreSQL SQLAlchemy URL")
    parser.add_argument("--limit", type=int, default=50, help="Max statements in report")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset pg_stat_statements before measuring (use carefully in prod)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.database_url:
        raise SystemExit("DATABASE_URL or --database-url is required")

    engine = create_engine(args.database_url)
    with engine.begin() as conn:
        if args.reset:
            conn.execute(RESET_SQL)

        rows = [dict(r._mapping) for r in conn.execute(REPORT_SQL, {"limit": args.limit}).fetchall()]

    result = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "count": len(rows),
        "statements": rows,
    }
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
