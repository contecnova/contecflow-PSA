"""Naive-UTC time helpers (drop-in for the deprecated datetime.utcnow())."""
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC 'now' — identical semantics to the deprecated datetime.utcnow()."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
