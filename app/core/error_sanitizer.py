"""Helpers to avoid leaking sensitive internals in HTTP error payloads."""

from __future__ import annotations

import re
from typing import Any

_SENSITIVE_DETAIL_RE = re.compile(
    r"traceback|stack\s*trace|sqlalchemy|psycopg|sqlite|internal\s+error|"
    r"secret|token|password|api[_-]?key|exception|line\s+\d+",
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
    - Replaces potentially sensitive string details with status-based generic text.
    - Always sanitizes 5xx details.
    """
    if status_code >= 500:
        return _default_message(status_code)

    if isinstance(detail, (dict, list)):
        return detail

    text = str(detail) if detail is not None else ""
    if not text:
        return _default_message(status_code)

    if _SENSITIVE_DETAIL_RE.search(text):
        return _default_message(status_code)

    return detail
