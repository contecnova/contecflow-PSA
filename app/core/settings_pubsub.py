"""Redis pub/sub for cross-worker settings cache invalidation.

Why this exists: ``app/services/settings_service.py`` and
``app/services/integration_credentials_service.py`` keep an in-process cache
with a 60-second TTL. When admin PUTs a setting via /api/v1/settings/runtime/...
only the FastAPI worker that handled the request invalidates locally; the other
workers keep serving the stale value until their TTL expires. With Redis
configured (``REDIS_URL``), this module:

  - **Publishes** ``{scope, key}`` to channel ``CHANNEL`` on every write.
  - **Subscribes** from a daemon thread on app startup and invalidates the
    in-process cache of the matching service on every received message.

Graceful degradation: if Redis is unavailable or ``REDIS_URL`` is not set, both
publish and subscribe become no-ops and the system falls back to the existing
TTL-only behaviour. No exceptions leak to callers.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Optional

from app.core.config import settings

logger = logging.getLogger("contecflow.settings.pubsub")

CHANNEL = "contecflow:settings:invalidate"

_pub_client = None
_pub_lock = threading.Lock()
_sub_thread: Optional[threading.Thread] = None
_sub_stop = threading.Event()
# Identify this process so we can ignore our own publishes — otherwise the
# worker that just wrote the value would invalidate its own cache twice (once
# inline from the service, once from the subscription loop). Harmless but
# noisy in logs and wastes a DB round-trip.
_INSTANCE_ID = f"{id(object()):x}-{int(time.time() * 1000)}"


def _get_publisher():
    """Lazy-construct a Redis client for publishing. None if Redis is disabled."""
    global _pub_client
    if not settings.REDIS_URL:
        return None
    with _pub_lock:
        if _pub_client is not None:
            return _pub_client
        try:
            import redis  # type: ignore

            _pub_client = redis.from_url(
                settings.REDIS_URL,
                socket_connect_timeout=1,
                socket_timeout=1,
                decode_responses=True,
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("settings pub/sub disabled (publisher init failed): %s", exc)
            _pub_client = None
        return _pub_client


def publish_invalidation(scope: str, key: Optional[str]) -> None:
    """Notify other workers that a (scope, key) cache entry must be dropped.

    ``scope`` is either ``"runtime"`` (app_settings table) or ``"integration"``
    (per-provider credentials). ``key`` is the setting key for ``runtime``, or
    the provider name for ``integration``. ``None`` means "invalidate all".
    """
    client = _get_publisher()
    if client is None:
        return
    payload = json.dumps({"scope": scope, "key": key, "src": _INSTANCE_ID})
    try:
        client.publish(CHANNEL, payload)
    except Exception as exc:
        logger.warning("settings pub/sub publish failed (scope=%s key=%s): %s", scope, key, exc)


def _cerrar_en_silencio(*recursos) -> None:
    """Cierra lo que se le pase, sin dejar que un fallo al cerrar tape otro.

    Auditoría 2026-09 (hallazgo 18): eran dos `try/except` idénticos en el
    `finally`, uno por recurso. Un error al cerrar es ruido: lo que importaba
    ya pasó antes.
    """
    for recurso in recursos:
        if recurso is None:
            continue
        try:
            recurso.close()
        except Exception:
            logger.debug("_subscriber_loop: fallo best-effort ignorado", exc_info=True)


def _escuchar_canal(client, pubsub) -> None:
    """Aplica las invalidaciones que lleguen por el canal, hasta que se pare."""
    pubsub.subscribe(CHANNEL)
    logger.info("settings pub/sub subscriber connected (channel=%s)", CHANNEL)
    for mensaje in pubsub.listen():
        if _sub_stop.is_set():
            return
        if mensaje and mensaje.get("type") == "message":
            _dispatch_invalidation(mensaje.get("data"))


def _subscriber_loop() -> None:
    """Cuerpo del hilo demonio: se suscribe a CHANNEL y aplica invalidaciones.

    Reconecta con espera exponencial hasta 30 s. La espera se hace sobre el
    evento de parada y no con `sleep`, para que apagar el proceso no tenga que
    esperar al siguiente reintento.
    """
    try:
        import redis  # type: ignore
    except Exception:  # pragma: no cover
        logger.debug("_subscriber_loop: excepcion ignorada", exc_info=True)
        return

    espera = 1.0
    while not _sub_stop.is_set():
        client = pubsub = None
        try:
            client = redis.from_url(
                settings.REDIS_URL,
                socket_connect_timeout=2,
                # La escucha es bloqueante: un tiempo de lectura la cortaría en
                # cada pausa sin tráfico.
                socket_timeout=None,
                decode_responses=True,
            )
            pubsub = client.pubsub(ignore_subscribe_messages=True)
            espera = 1.0
            _escuchar_canal(client, pubsub)
        except Exception as exc:
            if _sub_stop.is_set():
                return
            logger.warning("settings pub/sub subscriber error (retry %.0fs): %s", espera, exc)
            _sub_stop.wait(espera)
            espera = min(espera * 2, 30.0)
        finally:
            _cerrar_en_silencio(pubsub, client)


def _dispatch_invalidation(raw_payload) -> None:
    try:
        data = json.loads(raw_payload) if isinstance(raw_payload, str) else raw_payload
        if not isinstance(data, dict):
            return
        if data.get("src") == _INSTANCE_ID:
            return  # echo of our own write — already invalidated in-process
        scope = data.get("scope")
        key = data.get("key")
        if scope == "runtime":
            from app.services import settings_service as _ss
            _ss._invalidate_cache_local(key)
        elif scope == "integration":
            from app.services import integration_credentials_service as _ic
            _ic._invalidate_cache_local(key)
    except Exception as exc:
        logger.warning("settings pub/sub dispatch failed: %s", exc)


def start_subscriber() -> bool:
    """Start the daemon listener. Returns True on success, False if disabled."""
    global _sub_thread
    if not settings.REDIS_URL:
        return False
    if _sub_thread is not None and _sub_thread.is_alive():
        return True
    _sub_stop.clear()
    _sub_thread = threading.Thread(
        target=_subscriber_loop, name="settings-pubsub-sub", daemon=True
    )
    _sub_thread.start()
    return True


def stop_subscriber(timeout: float = 2.0) -> None:
    """Signal the subscriber thread to exit (called on shutdown)."""
    _sub_stop.set()
    if _sub_thread is not None and _sub_thread.is_alive():
        _sub_thread.join(timeout=timeout)


__all__ = ["publish_invalidation", "start_subscriber", "stop_subscriber"]
