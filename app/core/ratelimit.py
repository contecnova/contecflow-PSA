"""
Centralised rate-limiter instance (slowapi).

Import `limiter` into any router file that needs per-endpoint limits:

    from app.core.ratelimit import limiter

    @router.post("/login")
    @limiter.limit("5/minute")
    def login(request: Request, ...):
        ...

The middleware is registered in app/main.py: `SlowAPIMiddleware` applies
`RATE_LIMIT_DEFAULT` to every route without its own `@limiter.limit`.
"""
import logging
from app.core.entorno import en_pruebas
import uuid
from slowapi import Limiter

_logger = logging.getLogger(__name__)


def _rate_limit_key(request):
    """Quién gasta la cuota: el usuario de la sesión o, sin sesión, la IP real.

    Revisión 2026-11. Antes era `get_remote_address`, la IP de la conexión: tras
    nginx, la del proxy, así que toda la empresa compartía una sola cuota; y
    por IP, una oficina detrás de una NAT también. Ahora cuenta por usuario
    autenticado (cookie o Bearer) y, si no lo hay, por la IP que dan
    `X-Forwarded-For`/`X-Real-IP` sólo cuando el salto es un proxy de confianza
    (`TRUST_PROXY_HEADERS`, `TRUSTED_PROXY_CIDRS`).

    En pruebas devuelve una clave por petición para que los límites no se
    compartan entre tests.
    """
    if en_pruebas():
        return str(uuid.uuid4())
    token = request.cookies.get("access_token") if hasattr(request, "cookies") else None
    if not token:
        cabecera = request.headers.get("authorization", "")
        token = cabecera[7:] if cabecera.lower().startswith("bearer ") else None
    if token:
        from app.core.security import decode_token
        try:
            datos = decode_token(token)
        except Exception:  # un token malo no da identidad: cuenta por IP
            _logger.debug("_rate_limit_key: excepcion ignorada", exc_info=True)
            datos = None
        if datos and datos.get("sub"):
            return f"u:{datos['sub']}"
    from app.core.network import extract_client_ip
    return f"ip:{extract_client_ip(request)}"


def _build_limiter() -> Limiter:
    """Build a Limiter backed by Redis when REDIS_URL is set (production),
    falling back to in-memory storage for local dev / testing.
    Using Redis ensures limits are shared across all uvicorn workers."""
    from app.core.config import settings  # lazy import to avoid circular dependency at startup
    is_local_dev = settings.ENVIRONMENT == "development" and not en_pruebas()

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
    if redis_url and not en_pruebas():
        redis_ok = _redis_reachable(redis_url)
        if redis_ok:
            return Limiter(
                key_func=_rate_limit_key,
                default_limits=[settings.RATE_LIMIT_DEFAULT],
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
        default_limits=[settings.RATE_LIMIT_DEFAULT],
    )


limiter = _build_limiter()
