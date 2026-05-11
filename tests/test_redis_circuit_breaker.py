"""Tests para el circuit breaker de Redis en auth_service.

Verifica:
  1. Cuando Redis falla en una operación, se entra en circuit-break.
  2. Durante la ventana de backoff, get_sso_redis() devuelve None sin
     reintentar (no hay tormenta de reintentos).
  3. Pasada la ventana, vuelve a reintentar conectar.
  4. force_redis_reconnect() limpia el estado y permite reintento inmediato.
  5. El rate-limiter de login degrada a in-memory cuando Redis está caído.
"""
import time
from unittest.mock import patch, MagicMock

import pytest

from app.services import auth_service as svc


@pytest.fixture(autouse=True)
def reset_breaker():
    """Limpia el estado del circuit breaker antes y después de cada test."""
    svc.force_redis_reconnect()
    yield
    svc.force_redis_reconnect()


def test_circuit_break_marks_client_dead():
    """Inicialmente _redis_client=None tras reset; tras circuit_break sigue None
    pero _redis_client_init queda True para que aplique el backoff."""
    assert svc._redis_client is None
    assert svc._redis_client_init is False

    svc._redis_circuit_break("smoke")
    assert svc._redis_client is None


def test_get_sso_redis_returns_none_within_backoff_without_retry(monkeypatch):
    """Si ya falló y aún no pasó el backoff, NO intenta conectar de nuevo
    (no log spam, no socket attempts)."""
    # Simulamos: cliente caído, último intento hace 1 segundo
    svc._redis_client = None
    svc._redis_client_init = True
    svc._redis_last_attempt_at = time.time() - 1.0

    # Si volviera a intentar, redis.from_url sería llamado. Lo mockeamos para
    # detectar la llamada.
    call_count = {"n": 0}

    class FakeRedisModule:
        @staticmethod
        def from_url(*a, **kw):
            call_count["n"] += 1
            return MagicMock()

    with patch.dict("sys.modules", {"redis": FakeRedisModule}):
        result = svc.get_sso_redis()
    assert result is None
    assert call_count["n"] == 0  # no se llamó from_url — backoff respetado


def test_get_sso_redis_retries_after_backoff(monkeypatch):
    """Pasada la ventana de backoff, sí se intenta conectar de nuevo."""
    svc._redis_client = None
    svc._redis_client_init = True
    # Simulamos que el último intento fue hace _REDIS_RECONNECT_BACKOFF + 5 s
    svc._redis_last_attempt_at = time.time() - (svc._REDIS_RECONNECT_BACKOFF + 5.0)

    call_count = {"n": 0}
    fake_client = MagicMock()
    fake_client.ping.return_value = True

    class FakeRedisModule:
        @staticmethod
        def from_url(*a, **kw):
            call_count["n"] += 1
            return fake_client

    with patch.dict("sys.modules", {"redis": FakeRedisModule}):
        result = svc.get_sso_redis()
    assert call_count["n"] == 1  # SÍ reintentó tras backoff
    assert result is fake_client  # conexión nueva establecida


def test_force_redis_reconnect_clears_state_immediately(monkeypatch):
    """force_redis_reconnect() resetea breaker sin esperar backoff."""
    svc._redis_client = None
    svc._redis_client_init = True
    svc._redis_last_attempt_at = time.time()  # acabado de fallar

    # Sin force_reconnect, get_sso_redis devolvería None sin intentar
    with patch.dict("sys.modules", {"redis": MagicMock()}):
        assert svc.get_sso_redis() is None

    svc.force_redis_reconnect()
    assert svc._redis_client is None
    assert svc._redis_client_init is False

    # Tras force, sí intenta de nuevo
    fake_client = MagicMock()
    fake_client.ping.return_value = True

    class FakeRedisModule:
        @staticmethod
        def from_url(*a, **kw):
            return fake_client

    with patch.dict("sys.modules", {"redis": FakeRedisModule}):
        result = svc.get_sso_redis()
    assert result is fake_client


def test_login_rate_limit_falls_back_to_inmemory_when_redis_down(monkeypatch):
    """Con Redis caído, register_login_failure usa el fallback in-memory
    y devuelve el lockout cuando se alcanza el umbral."""
    # Forzamos Redis "caído"
    svc._redis_client = None
    svc._redis_client_init = True
    svc._redis_last_attempt_at = time.time()  # dentro de backoff → no reintenta

    # Ignorar el cortocircuito de dev mode
    from app.core.config import settings as _settings
    monkeypatch.setattr(_settings, "ENVIRONMENT", "production", raising=False)
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setattr(_settings, "LOGIN_MAX_ATTEMPTS", 3, raising=False)
    monkeypatch.setattr(_settings, "LOGIN_LOCKOUT_SECONDS", 120, raising=False)
    monkeypatch.setattr(_settings, "LOGIN_ATTEMPT_WINDOW_SECONDS", 300, raising=False)

    # Limpiar fallback in-memory para empezar de cero
    svc._login_fail_fallback.clear()

    bucket = "test_user|127.0.0.1"
    assert svc.register_login_failure(bucket) == 0
    assert svc.register_login_failure(bucket) == 0
    lockout = svc.register_login_failure(bucket)
    assert lockout == 120  # tercer fallo dispara lockout

    # Y el TTL del bloqueo es legible aún con Redis caído
    ttl = svc.login_lock_ttl(bucket)
    assert 0 < ttl <= 120

    # clear_login_failure también funciona contra el fallback
    svc.clear_login_failure(bucket)
    assert svc.login_lock_ttl(bucket) == 0


def test_circuit_break_triggers_on_redis_exception(monkeypatch):
    """Cuando una operación Redis lanza, se entra en circuit-break y la
    siguiente llamada NO reintenta (sino que devuelve None inmediatamente)."""
    fake_client = MagicMock()
    fake_client.ping.return_value = True
    fake_client.incr.side_effect = RuntimeError("simulated redis outage")

    # Inyectamos un cliente "vivo" inicialmente
    svc._redis_client = fake_client
    svc._redis_client_init = True

    from app.core.config import settings as _settings
    monkeypatch.setattr(_settings, "ENVIRONMENT", "production", raising=False)
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setattr(_settings, "LOGIN_MAX_ATTEMPTS", 5, raising=False)
    monkeypatch.setattr(_settings, "LOGIN_LOCKOUT_SECONDS", 60, raising=False)
    monkeypatch.setattr(_settings, "LOGIN_ATTEMPT_WINDOW_SECONDS", 300, raising=False)

    svc._login_fail_fallback.clear()
    # Esta llamada hará r.incr() que lanza → activa el circuit breaker
    result = svc.register_login_failure("test_bucket|1.2.3.4")
    # Debería haber caído al fallback in-memory tras el except
    assert result == 0  # primer fallo, sin lockout aún
    assert svc._redis_client is None  # cliente marcado como muerto
    assert svc._redis_client_init is True  # backoff activo
