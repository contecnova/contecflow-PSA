"""Estado efimero en Redis (con respaldo en memoria): estados SSO, intentos de login, peticiones y jti de restablecimiento.

Parte de `app.services.auth_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
import logging
import os
import threading
import time
from typing import Optional
import json as _json
from fastapi import Request
from app.core.config import settings

from app.services.auth_service._comun import logger


# ── Constants ─────────────────────────────────────────────────────────────────

SSO_STATE_TTL = 600  # seconds
SSO_KEY_PREFIX = "contecflow:sso_state:"

LOGIN_FAIL_PREFIX = "contecflow:login:fail:"
LOGIN_LOCK_PREFIX = "contecflow:login:lock:"

PASSWORD_RESET_TTL_SECONDS = 30 * 60
PASSWORD_RESET_REQUEST_WINDOW_SECONDS = 15 * 60
PASSWORD_RESET_REQUEST_MAX_PER_WINDOW = 5
PASSWORD_RESET_JTI_PREFIX = "contecflow:password_reset:jti:"  # noqa: S105

# In-memory fallback stores  ──────────────────────────────────────────────────
# (expiración, payload JSON) por estado. Antes sólo la expiración: no había
# dónde llevar el code_verifier de PKCE ni el nonce (auditoría 2026-08, P2-13).
_sso_states_fallback: dict[str, tuple[float, str]] = {}
_sso_states_lock = threading.Lock()
_redis_client = None
_redis_client_init = False
_login_fail_fallback: dict[str, dict[str, float]] = {}
_password_reset_req_fallback: dict[str, dict[str, float]] = {}
_password_reset_jti_fallback: dict[str, tuple[str, float]] = {}


# ── Redis / SSO state store ───────────────────────────────────────────────────

# Cuándo reintentar conectar a Redis tras un fallo (segundos).
#
# Multi-worker note: cada worker mantiene su propio circuit breaker en
# memoria. Mientras dura el backoff, el rate limiter degrada a in-memory
# por-worker (un atacante que rota IPs alcanzaría el límite por worker
# independientemente). Mantenemos el backoff corto para que cualquier flap
# transitorio de Redis se recupere automáticamente antes de comprometer
# la protección global.
_REDIS_RECONNECT_BACKOFF = float(os.getenv("REDIS_RECONNECT_BACKOFF_SECONDS", "30"))
# Última vez que intentamos crear el cliente (epoch seconds).
_redis_last_attempt_at: float = 0.0


def force_redis_reconnect() -> None:
    """Forzar reintento de conexión a Redis en la siguiente llamada.

    Útil para administración (endpoint admin / repl) cuando se sabe que
    Redis ha vuelto y no se quiere esperar al backoff. Es thread-safe en
    cuanto a corrupciones — la próxima llamada a get_sso_redis() volverá a
    crear el cliente bajo el bloqueo implícito de Python (GIL).
    """
    global _redis_client, _redis_client_init, _redis_last_attempt_at
    _redis_client = None
    _redis_client_init = False
    _redis_last_attempt_at = 0.0


def get_sso_redis():
    """Return a shared Redis client if Redis is reachable, else None.

    Si Redis estaba caído al primer intento, antes el cliente se quedaba
    cacheado como None para siempre. Ahora reintentamos cada
    `_REDIS_RECONNECT_BACKOFF` segundos para recuperarnos automáticamente
    tras una caída transitoria.
    """
    global _redis_client, _redis_client_init, _redis_last_attempt_at
    now = time.time()
    # Si el cliente está disponible, lo devolvemos directamente.
    if _redis_client_init and _redis_client is not None:
        return _redis_client
    # Si la última inicialización falló y aún no ha pasado el backoff,
    # devolvemos None sin volver a intentarlo (evita tormenta de reintentos).
    if _redis_client_init and _redis_client is None:
        if (now - _redis_last_attempt_at) < _REDIS_RECONNECT_BACKOFF:
            return None
    _redis_client_init = True
    _redis_last_attempt_at = now
    try:
        import redis as _redis_module
        r = _redis_module.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=2,
            socket_timeout=2,
            decode_responses=True,
        )
        r.ping()
        _redis_client = r
        logger.info("SSO state store: using Redis (%s)", (settings.REDIS_URL or "").split("@")[-1])
    except Exception as _e:
        if settings.ENVIRONMENT == "development" and os.getenv("TESTING") != "1":
            logger.info(
                "SSO state store: Redis unavailable in development (%s). Using in-memory fallback "
                "(reintento en %ss).",
                _e, int(_REDIS_RECONNECT_BACKOFF),
            )
        else:
            logger.warning(
                "SSO state store: Redis unavailable (%s). Falling back to in-memory — "
                "NOT SAFE for multi-worker deployments. Reintentando en %ss. Set REDIS_URL to fix.",
                _e, int(_REDIS_RECONNECT_BACKOFF),
            )
        _redis_client = None
    return _redis_client


def register_sso_state(state_raw: str, payload: Optional[dict] = None) -> None:
    """Guarda el estado OIDC y, opcionalmente, datos ligados a esa transacción.

    Auditoría 2026-08 (P2-13): antes el valor almacenado era la cadena "1", así
    que no había dónde llevar el `code_verifier` de PKCE ni el `nonce`. Ahora se
    guarda un JSON con lo que el callback necesita para verificarlos. El estado
    sigue siendo de un solo uso.
    """
    valor = _json.dumps(payload or {})
    r = get_sso_redis()
    if r is not None:
        try:
            r.setex(f"{SSO_KEY_PREFIX}{state_raw}", SSO_STATE_TTL, valor)
            return
        except Exception as _e:
            logging.getLogger(__name__).debug("register_sso_state: excepcion ignorada", exc_info=True)
            _redis_circuit_break(f"SSO setex: {_e}")
    with _sso_states_lock:
        now = time.time()
        expired = [k for k, v in _sso_states_fallback.items() if v[0] < now]
        for k in expired:
            del _sso_states_fallback[k]
        _sso_states_fallback[state_raw] = (now + SSO_STATE_TTL, valor)


def consume_sso_state(state_raw: str) -> bool:
    """True si el estado existía y no había expirado. Lo elimina (un solo uso)."""
    return consume_sso_state_payload(state_raw) is not None


def consume_sso_state_payload(state_raw: str) -> Optional[dict]:
    """Consume el estado y devuelve su payload, o None si no era válido.

    Atómico frente a replay: el estado se borra al leerlo, así que un segundo
    intento con el mismo `state` no encuentra nada.
    """
    r = get_sso_redis()
    if r is not None:
        try:
            # GETDEL es atómico: lee y borra en una sola operación, así que dos
            # callbacks simultáneos con el mismo state no pueden pasar los dos.
            raw = r.getdel(f"{SSO_KEY_PREFIX}{state_raw}")
            if raw is None:
                return None
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="ignore")
            try:
                return _json.loads(raw) if raw else {}
            except ValueError:
                return {}
        except Exception as _e:
            logging.getLogger(__name__).debug("consume_sso_state_payload: excepcion ignorada", exc_info=True)
            _redis_circuit_break(f"SSO getdel: {_e}")
    with _sso_states_lock:
        entry = _sso_states_fallback.pop(state_raw, None)
    if entry is None:
        return None
    expiry, valor = entry
    if time.time() >= expiry:
        return None
    try:
        return _json.loads(valor) if valor else {}
    except ValueError:
        return {}


# ── Login rate-limiting ───────────────────────────────────────────────────────

def login_bucket(username: str, request: Request) -> str:
    ip = request.client.host if request.client and request.client.host else "unknown"
    return f"{username.strip().lower()}|{ip}"


def login_lock_ttl(bucket: str) -> int:
    if settings.ENVIRONMENT == "development" and os.getenv("TESTING") != "1":
        return 0
    r = get_sso_redis()
    lock_key = f"{LOGIN_LOCK_PREFIX}{bucket}"
    if r is not None:
        try:
            ttl = r.ttl(lock_key)
            return int(ttl) if ttl and ttl > 0 else 0
        except Exception as exc:
            logging.getLogger(__name__).debug("login_lock_ttl: excepcion ignorada", exc_info=True)
            _redis_circuit_break(f"login lockout TTL read: {exc}")
    with _sso_states_lock:
        st = _login_fail_fallback.get(bucket)
        if not st:
            return 0
        lock_until = st.get("lock_until", 0)
        now = time.time()
        if lock_until > now:
            return int(lock_until - now)
        return 0


def _redis_circuit_break(reason: str) -> None:
    """Marcar el cliente como caído para que get_sso_redis() haga reintento
    según el backoff configurado. Aísla el coste de fallos intermitentes."""
    global _redis_client
    logger.warning("Redis op failed (%s) — entrando en circuit-break", reason)
    _redis_client = None  # _redis_client_init stays True; backoff aplica


def register_login_failure(bucket: str) -> int:
    """Register failed login and return lockout seconds if account got locked."""
    if settings.ENVIRONMENT == "development" and os.getenv("TESTING") != "1":
        return 0
    r = get_sso_redis()
    fail_key = f"{LOGIN_FAIL_PREFIX}{bucket}"
    lock_key = f"{LOGIN_LOCK_PREFIX}{bucket}"
    if r is not None:
        try:
            fails = int(r.incr(fail_key))
            if fails == 1:
                r.expire(fail_key, settings.LOGIN_ATTEMPT_WINDOW_SECONDS)
            if fails >= settings.LOGIN_MAX_ATTEMPTS:
                r.setex(lock_key, settings.LOGIN_LOCKOUT_SECONDS, "1")
                r.delete(fail_key)
                return settings.LOGIN_LOCKOUT_SECONDS
            return 0
        except Exception as exc:
            logging.getLogger(__name__).warning("register_login_failure: excepcion ignorada", exc_info=True)
            _redis_circuit_break(str(exc))

    now = time.time()
    with _sso_states_lock:
        state = _login_fail_fallback.get(bucket)
        if not state or state.get("window_until", 0) < now:
            state = {
                "count": 0,
                "window_until": now + settings.LOGIN_ATTEMPT_WINDOW_SECONDS,
                "lock_until": 0,
            }
        state["count"] = int(state.get("count", 0)) + 1
        if state["count"] >= settings.LOGIN_MAX_ATTEMPTS:
            state["count"] = 0
            state["lock_until"] = now + settings.LOGIN_LOCKOUT_SECONDS
            _login_fail_fallback[bucket] = state
            return settings.LOGIN_LOCKOUT_SECONDS
        _login_fail_fallback[bucket] = state
    return 0


def clear_login_failure(bucket: str) -> None:
    r = get_sso_redis()
    if r is not None:
        try:
            r.delete(f"{LOGIN_FAIL_PREFIX}{bucket}")
            r.delete(f"{LOGIN_LOCK_PREFIX}{bucket}")
            return
        except Exception as exc:
            logging.getLogger(__name__).warning("clear_login_failure: excepcion ignorada", exc_info=True)
            _redis_circuit_break(f"login lockout clear: {exc}")
    with _sso_states_lock:
        _login_fail_fallback.pop(bucket, None)


# ── Password reset rate-limiting ──────────────────────────────────────────────

def password_reset_bucket(identifier: str, request: Request) -> str:
    ip = request.client.host if request.client and request.client.host else "unknown"
    return f"{identifier.strip().lower()}|{ip}"


def register_password_reset_request(bucket: str) -> int:
    """Register password reset request and return lockout seconds if throttled."""
    now = time.time()
    with _sso_states_lock:
        st = _password_reset_req_fallback.get(bucket)
        if not st or st.get("window_until", 0) < now:
            st = {
                "count": 0,
                "window_until": now + PASSWORD_RESET_REQUEST_WINDOW_SECONDS,
            }
        st["count"] = int(st.get("count", 0)) + 1
        _password_reset_req_fallback[bucket] = st
        if st["count"] > PASSWORD_RESET_REQUEST_MAX_PER_WINDOW:
            return int(max(st["window_until"] - now, 1))
    return 0


def store_password_reset_jti(user_id: str, jti: str, ttl_seconds: int) -> None:
    r = get_sso_redis()
    key = f"{PASSWORD_RESET_JTI_PREFIX}{user_id}"
    if r is not None:
        try:
            r.setex(key, ttl_seconds, jti)
            return
        except Exception as exc:
            logger.warning("Redis setex failed for password reset jti: %s", exc)

    with _sso_states_lock:
        _password_reset_jti_fallback[user_id] = (jti, time.time() + ttl_seconds)


def is_current_password_reset_jti(user_id: str, jti: str) -> bool:
    r = get_sso_redis()
    key = f"{PASSWORD_RESET_JTI_PREFIX}{user_id}"
    if r is not None:
        try:
            stored = r.get(key)
            return bool(stored) and stored == jti
        except Exception as exc:
            logger.warning("Redis get failed for password reset jti: %s", exc)

    with _sso_states_lock:
        current = _password_reset_jti_fallback.get(user_id)
        if not current:
            return False
        current_jti, expires_at = current
        if expires_at <= time.time():
            _password_reset_jti_fallback.pop(user_id, None)
            return False
        return current_jti == jti


def consume_password_reset_token(user_id: str, jti: Optional[str]) -> None:
    if not user_id:
        return
    r = get_sso_redis()
    key = f"{PASSWORD_RESET_JTI_PREFIX}{user_id}"
    if r is not None:
        try:
            if jti:
                stored = r.get(key)
                if stored and stored == jti:
                    r.delete(key)
            else:
                r.delete(key)
            return
        except Exception as exc:
            logger.warning("Redis delete failed for password reset jti: %s", exc)

    with _sso_states_lock:
        if jti:
            current = _password_reset_jti_fallback.get(user_id)
            if current and current[0] == jti:
                _password_reset_jti_fallback.pop(user_id, None)
        else:
            _password_reset_jti_fallback.pop(user_id, None)
