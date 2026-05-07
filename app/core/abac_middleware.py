"""
ABACMiddleware — global opt-in ABAC enforcement layer.

The middleware checks every incoming request against ABAC_ROUTE_REGISTRY.
Routes whose path starts with a registered prefix are verified using the
same enforce_abac() helper used by individual endpoints.  All other routes
pass through untouched so that endpoint-level guards or RBAC handle them.

Requirements / assumptions:
- The authentication middleware (or dependency) that populates
  `request.state.user` must run BEFORE this middleware in the stack.
  If request.state.user is not set the check is skipped (the normal
  auth layer will reject unauthenticated requests separately).
- A database session is obtained via a short-lived connection; we reuse
  the same SessionLocal used elsewhere in the app.
"""
from __future__ import annotations

import logging
from typing import Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.abac_registry import ABAC_ROUTE_REGISTRY

logger = logging.getLogger("contecflow.abac.middleware")


def _resolve_registry_entry(path: str) -> tuple[str, str] | None:
    """Return the (resource_type, action) for the longest matching prefix, or None."""
    best: tuple[str, str] | None = None
    best_len = -1
    for prefix, entry in ABAC_ROUTE_REGISTRY.items():
        if path == prefix or path.startswith(prefix + "/") or path.startswith(prefix + "?"):
            if len(prefix) > best_len:
                best = entry
                best_len = len(prefix)
    return best


class ABACMiddleware(BaseHTTPMiddleware):
    """
    Starlette/FastAPI middleware that applies ABAC checks for registered routes.

    Usage — add to the app AFTER the authentication middleware so that
    request.state.user is already populated::

        app.add_middleware(ABACMiddleware)
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable):
        path = request.url.path

        registry_entry = _resolve_registry_entry(path)

        if registry_entry is not None:
            user = getattr(request.state, "user", None)

            if user is not None:
                resource_type, action = registry_entry
                try:
                    # Import here to avoid circular imports at module load time.
                    from app.db.session import SessionLocal
                    from app.core.abac_enforce import enforce_abac

                    db = SessionLocal()
                    try:
                        enforce_abac(db, user, resource_type, resource_id=None, action=action)
                    finally:
                        db.close()

                except Exception as exc:
                    # enforce_abac raises HTTPException(403) on denial; we
                    # translate that to a JSON response here since we are in
                    # middleware context (outside normal FastAPI exception handling).
                    from fastapi import HTTPException

                    if isinstance(exc, HTTPException):
                        logger.info(
                            "ABAC middleware denied access: user=%s path=%s resource=%s action=%s",
                            getattr(user, "id", "?"),
                            path,
                            resource_type,
                            action,
                        )
                        return JSONResponse(
                            status_code=exc.status_code,
                            content={"detail": exc.detail},
                        )
                    # Unexpected error — log and deny (fail-closed).
                    logger.error(
                        "ABAC middleware unexpected error for path=%s: %s",
                        path,
                        exc,
                        exc_info=True,
                    )
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Access temporarily unavailable — please try again"},
                    )

        return await call_next(request)
