"""Scheduler entrypoints for alert-related background jobs."""

import logging

from app.db.session import SessionLocal
from app.services.alert_service import run_alert_engine

logger = logging.getLogger(__name__)


def run_alert_engine_job() -> None:
    """Run alert engine using a fresh DB session per execution."""
    db = SessionLocal()
    try:
        result = run_alert_engine(db)
        logger.info("Scheduled alert engine finished: %s", result)
    except Exception:
        logger.exception("Scheduled alert engine failed")
        raise
    finally:
        db.close()
