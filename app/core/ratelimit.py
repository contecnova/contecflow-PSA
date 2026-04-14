"""
Centralised rate-limiter instance (slowapi).

Import `limiter` into any router file that needs per-endpoint limits:

    from app.core.ratelimit import limiter

    @router.post("/login")
    @limiter.limit("5/minute")
    def login(request: Request, ...):
        ...

The middleware is registered in app/main.py.
"""
import logging
import os
import uuid
from slowapi import Limiter
from slowapi.util import get_remote_address

_logger = logging.getLogger(__name__)


def _rate_limit_key(request):
    """In test environments return a unique key per request so rate limits
    are never shared between tests. In production use the remote IP."""
    if os.getenv("TESTING") == "1":
        return str(uuid.uuid4())
    return get_remote_address(request)


def _build_limiter() -> Limiter:
    """Build a Limiter backed by Redis when REDIS_URL is set (production),
    falling back to in-memory storage for local dev / testing.
    Using Redis ensures limits are shared across all uvicorn workers."""
    from app.core.config import settings  # lazy import to avoid circular dependency at startup
    redis_url = settings.REDIS_URL
    if redis_url and os.getenv("TESTING") != "1":
        try:
            return Limiter(
                key_func=_rate_limit_key,
                default_limits=["200/minute"],
                storage_uri=redis_url,
            )
        except Exception as _e:
            if (
                settings.ENVIRONMENT == "production"
                and settings.RATE_LIMIT_REQUIRE_REDIS_IN_PRODUCTION
            ):
                raise RuntimeError(
                    "Rate limiter backend is not available. Redis is required in production "
                    "(set RATE_LIMIT_REQUIRE_REDIS_IN_PRODUCTION=0 to override)."
                ) from _e
            _logger.warning(
                "Rate limiter: Redis unavailable (%s) — falling back to in-memory storage. "
                "Limits will NOT be shared across workers.",
                _e,
            )
    return Limiter(
        key_func=_rate_limit_key,
        default_limits=["200/minute"],
    )


limiter = _build_limiter()
