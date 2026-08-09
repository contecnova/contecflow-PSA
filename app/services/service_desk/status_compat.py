from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)


LEGACY_TICKET_STATUS_MAP = {
    "waiting_client": "pending_client",
    "pending_change": "pending_third",
}


def normalize_ticket_status(status: Optional[str]) -> Optional[str]:
    if status is None:
        return None
    normalized = str(status)
    return LEGACY_TICKET_STATUS_MAP.get(normalized, normalized)


def sanitize_legacy_ticket_statuses(db: Session) -> int:
    """Replace legacy ticket statuses in DB with canonical values.

    Uses raw SQL so it can repair rows even when ORM Enum decoding would fail.
    Casts the status column to text in the WHERE clause so PostgreSQL does not
    validate the legacy string against the current enum type before we fix it.
    """
    updated_rows = 0
    for legacy, canonical in LEGACY_TICKET_STATUS_MAP.items():
        try:
            result = db.execute(
                text("UPDATE sd_tickets SET status = :canonical WHERE status::text = :legacy"),
                {"canonical": canonical, "legacy": legacy},
            )
            updated_rows += int(result.rowcount or 0)
        except Exception:
            logger.debug("sanitize_legacy_ticket_statuses: skipped %s (no rows or already clean)", legacy)

    if updated_rows:
        db.commit()
    return updated_rows
