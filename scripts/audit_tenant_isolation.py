#!/usr/bin/env python3
"""Quick static audit for tenant isolation patterns in app/services.

Flags candidate lines where a query is created without obvious scoping helpers.
This is conservative and intended as a review aid, not a strict proof.
"""

from __future__ import annotations

from pathlib import Path
import argparse
import re

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ROOT / "app" / "services"

QUERY_RE = re.compile(r"\bdb\.query\(")
SAFE_HINTS = (
    "organization_id",
    "_scoped(",
    "_scope_",
    "org_id",
    "is_superadmin",
    "tenant",
)


def _normalize_identifier(rel: Path, src: str) -> str:
    normalized_src = re.sub(r"\s+", " ", src.strip())
    return f"{rel}:{normalized_src}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Static tenant isolation audit")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero exit code when candidate lines are found.",
    )
    parser.add_argument(
        "--baseline",
        default=str((ROOT / "scripts" / "tenant_audit_baseline.txt").resolve()),
        help="Path to baseline file with known findings.",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Write current findings into baseline file and exit 0.",
    )
    args = parser.parse_args()

    total_queries = 0
    flagged: list[tuple[Path, int, str]] = []

    for path in SERVICES.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        for i, line in enumerate(lines, start=1):
            if not QUERY_RE.search(line):
                continue
            total_queries += 1
            window = "\n".join(lines[max(0, i - 3): min(len(lines), i + 3)])
            if not any(hint in window for hint in SAFE_HINTS):
                flagged.append((path.relative_to(ROOT), i, line.strip()))

    identifiers = [_normalize_identifier(rel, src) for rel, _, src in flagged]

    if args.write_baseline:
        baseline_path = Path(args.baseline)
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text("\n".join(sorted(identifiers)) + "\n", encoding="utf-8")
        print(f"[tenant-audit] baseline written: {baseline_path}")
        print(f"[tenant-audit] baseline entries: {len(identifiers)}")
        return 0

    print(f"[tenant-audit] total queries scanned: {total_queries}")
    print(f"[tenant-audit] candidates to review: {len(flagged)}")
    for rel, line_no, src in flagged[:200]:
        print(f"- {rel}:{line_no}: {src}")

    if flagged:
        if args.strict:
            baseline_path = Path(args.baseline)
            baseline_entries: set[str] = set()
            if baseline_path.exists():
                baseline_entries = {
                    line.strip() for line in baseline_path.read_text(encoding="utf-8").splitlines() if line.strip()
                }
            new_entries = sorted(set(identifiers) - baseline_entries)
            print(f"[tenant-audit] baseline entries: {len(baseline_entries)}")
            print(f"[tenant-audit] new entries: {len(new_entries)}")
            for item in new_entries[:200]:
                print(f"+ {item}")
            if new_entries:
                print("[tenant-audit] STRICT FAIL: new unreviewed tenant findings detected.")
                return 1

        print("[tenant-audit] REVIEW REQUIRED: found query sites without obvious tenant hint.")
        return 0

    print("[tenant-audit] OK: no obvious unscoped query sites found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
