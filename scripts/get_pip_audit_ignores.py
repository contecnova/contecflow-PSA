#!/usr/bin/env python3
"""Emit pip-audit --ignore-vuln args from active exceptions registry."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path


FILE_PATH = Path("security/vulnerability-exceptions.json")


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def main() -> int:
    if not FILE_PATH.exists():
        print("")
        return 0

    payload = json.loads(FILE_PATH.read_text(encoding="utf-8"))
    items = payload.get("exceptions", [])
    today = date.today()

    ignores: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("tool") != "pip-audit":
            continue
        vuln_id = str(item.get("id", "")).strip()
        exp = str(item.get("expires_on", "")).strip()
        if not vuln_id or not exp:
            continue
        try:
            if _parse_date(exp) >= today:
                ignores.append(f"--ignore-vuln {vuln_id}")
        except Exception:
            continue

    print(" ".join(ignores))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
