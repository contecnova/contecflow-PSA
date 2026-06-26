"""Helpers to avoid leaking sensitive internals in HTTP error payloads."""

from __future__ import annotations

import re
from typing import Any

# Match *leak signatures*, not security vocabulary. A controlled 4xx/5xx message
# like "csrf token mismatch", "secret not configured" or "Slack delivery failed"
# is safe to surface; what must never leak is raw exception text, stack traces,
# SQL driver internals, object reprs, or a secret/key followed by its value.
_SENSITIVE_DETAIL_RE = re.compile(
    r"traceback|stack\s*trace|sqlalchemy|psycopg|sqlite3|"
    r"internal\s+server\s+error|"
    r"\bat\s+line\s+\d+|"
    r"<[A-Za-z_][\w.]*\s+object\s+at\s+0x|"               # repr: <Foo object at 0x...>
    r"(secret|token|password|api[_-]?key|bearer)\s*[=:]\s*\S",  # secret WITH a value
    re.IGNORECASE,
)


def _default_message(status_code: int) -> str:
    if status_code == 400:
        return "Invalid request"
    if status_code == 401:
        return "Unauthorized"
    if status_code == 403:
        return "Access denied"
    if status_code == 404:
        return "Resource not found"
    if status_code == 409:
        return "Conflict"
    if status_code == 422:
        return "Validation error"
    if status_code >= 500:
        return "Internal Server Error"
    return "Request could not be processed"


def sanitize_http_detail(status_code: int, detail: Any) -> Any:
    """Return a safe detail payload for responses.

    - Keeps structured validation payloads (422 list/dict) unchanged.
    - Replaces details that match a leak signature with status-based generic text.
    - Applies the same rule to every status: unhandled exceptions are already
      genericised upstream by ExceptionHandlerMiddleware, so an explicitly-raised
      HTTPException (even a 5xx like 502/503) carries a developer-authored message
      that is safe to surface unless it itself looks like a leak.
    """
    if isinstance(detail, (dict, list)):
        return detail

    text = str(detail) if detail is not None else ""
    if not text:
        return _default_message(status_code)

    if _SENSITIVE_DETAIL_RE.search(text):
        return _default_message(status_code)

    return detail
