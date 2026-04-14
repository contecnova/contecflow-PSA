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
    is_local_dev = settings.ENVIRONMENT == "development" and os.getenv("TESTING") != "1"

    def _redis_reachable(url: str) -> bool:
        try:
            import redis

            client = redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)
            client.ping()
            return True
        except Exception as _e:
            if is_local_dev:
                _logger.info("Rate limiter: Redis ping failed in development (%s)", _e)
            else:
                _logger.warning("Rate limiter: Redis ping failed (%s)", _e)
            return False

    redis_url = settings.REDIS_URL
    if redis_url and os.getenv("TESTING") != "1":
        redis_ok = _redis_reachable(redis_url)
        if redis_ok:
            return Limiter(
                key_func=_rate_limit_key,
                default_limits=["200/minute"],
                storage_uri=redis_url,
            )
        if (
            settings.ENVIRONMENT == "production"
            and settings.RATE_LIMIT_REQUIRE_REDIS_IN_PRODUCTION
        ):
            raise RuntimeError(
                "Rate limiter backend is not available. Redis is required in production "
                "(set RATE_LIMIT_REQUIRE_REDIS_IN_PRODUCTION=0 to override)."
            )
        if is_local_dev:
            _logger.info(
                "Rate limiter: Redis unavailable in development — using in-memory storage."
            )
        else:
            _logger.warning(
                "Rate limiter: Redis unavailable — falling back to in-memory storage. "
                "Limits will NOT be shared across workers."
            )
    return Limiter(
        key_func=_rate_limit_key,
        default_limits=["200/minute"],
    )


limiter = _build_limiter()
