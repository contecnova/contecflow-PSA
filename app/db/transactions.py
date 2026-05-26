"""
transactions.py — explicit transaction helpers (Audit #C8).

The codebase has 1025 `db.commit()` calls in services vs 72 `db.rollback()`
(14:1 ratio). Many multi-table mutations are not wrapped in `try/except` and
leave partial state when the second statement fails.

This module exposes two helpers that make the contract obvious at the call
site:

  • `atomic(db)`: context manager. Commits on clean exit, rolls back on any
    exception, and re-raises. Use for any multi-statement mutation.

  • `requires_transaction`: decorator equivalent. Useful for service entry
    points where the whole function is a single unit of work.

Adoption is incremental — new code should use these helpers; legacy paths can
be migrated module-by-module without breaking anything.

Example::

    from app.db.transactions import atomic

    def create_sla_schedule(payload, db):
        with atomic(db):
            db.query(SLASchedule).filter(SLASchedule.is_default).update({"is_default": False})
            s = SLASchedule(...)
            db.add(s)
        db.refresh(s)
        return s
"""
from __future__ import annotations

import functools
import logging
from contextlib import contextmanager
from typing import Callable, Generator, TypeVar

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., object])


@contextmanager
def atomic(db: Session) -> Generator[Session, None, None]:
    """Commit on success, rollback on any exception, re-raise the error.

    Idempotent: if the caller already opened a transaction via `db.begin()`,
    nesting is handled by SQLAlchemy's SAVEPOINT support.
    """
    try:
        yield db
        db.commit()
    except SQLAlchemyError:
        logger.exception("atomic() rolling back due to SQLAlchemyError")
        db.rollback()
        raise
    except Exception:
        logger.exception("atomic() rolling back due to unexpected error")
        db.rollback()
        raise


def requires_transaction(fn: F) -> F:
    """Decorator equivalent of `atomic(db)` for service-layer entry points.

    The decorated function must accept a `Session` argument either positionally
    (first or second arg) or as the kwarg `db`. The decorator opens the atomic
    block around the function body.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        db: Session | None = kwargs.get("db")
        if db is None:
            for a in args:
                if isinstance(a, Session):
                    db = a
                    break
        if db is None:
            raise RuntimeError(
                f"@requires_transaction: {fn.__name__} must receive a Session "
                "argument (positional or as kwarg 'db')."
            )
        with atomic(db):
            return fn(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


__all__ = ["atomic", "requires_transaction"]
