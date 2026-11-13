"""Ajustes de ejecucion: lectura con cache y respaldo de entorno, escritura por ambito, timeouts y monedas.

Parte de `app.services.settings_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional
from sqlalchemy.orm import Session
from app.models.settings import AppSetting
from app.core.config import settings as app_settings

from app.services.settings_service._catalogo import RUNTIME_FLAG_GROUPS


logger = logging.getLogger("contecflow.settings")


# ── Typed runtime-flag accessors ──────────────────────────────────────────────
# These resolve a Settings UI value with org-level precedence over global, and
# fall back to the static env-backed `settings.<KEY>` when neither row exists.
# Reads are cached in-process for `_CACHE_TTL_SECONDS` to avoid hammering the
# DB on hot paths; writes through `update_setting` invalidate the cache key.
# Thread-safe via a single coarse lock — entries are tiny so contention is
# negligible compared to the network/DB cost of an uncached read.

_CACHE_TTL_SECONDS = 60.0
_cache: dict[tuple[str, Optional[str]], tuple[float, str]] = {}
_cache_lock = threading.Lock()

# Sentinel used by `get_runtime_*` to distinguish "no fallback supplied" from
# the perfectly valid value of `None`.
_MISSING = object()


def _read_raw(db: Session, key: str, org_id: Optional[str]) -> Optional[str]:
    """Resolve a setting key with org-then-global precedence. Cached for TTL."""
    cache_key = (key, org_id)
    now = time.time()
    with _cache_lock:
        entry = _cache.get(cache_key)
        if entry is not None and entry[0] > now:
            return entry[1]

    row = None
    if org_id:
        row = (
            db.query(AppSetting)
            .filter(AppSetting.key == key, AppSetting.organization_id == org_id)
            .first()
        )
    if row is None:
        row = (
            db.query(AppSetting)
            .filter(AppSetting.key == key, AppSetting.organization_id.is_(None))
            .first()
        )

    value = row.value if row is not None else None
    with _cache_lock:
        _cache[cache_key] = (now + _CACHE_TTL_SECONDS, value)
    return value


def _env_fallback(key: str) -> Any:
    """Return `settings.<KEY>` if defined, else _MISSING."""
    return getattr(app_settings, key, _MISSING)


def _invalidate_cache_local(key: Optional[str] = None) -> None:
    """In-process only. Called by the pub/sub subscriber after a remote write."""
    with _cache_lock:
        if key is None:
            _cache.clear()
            return
        for cache_key in list(_cache.keys()):
            if cache_key[0] == key:
                _cache.pop(cache_key, None)


def invalidate_cache(key: Optional[str] = None) -> None:
    """Clear cache entries locally AND broadcast to other workers via Redis pub/sub.

    Drops only matching key when given, else everything. Safe to call from
    anywhere — the pub/sub publish is best-effort and never raises.
    """
    _invalidate_cache_local(key)
    try:
        from app.core.settings_pubsub import publish_invalidation
        publish_invalidation("runtime", key)
    except Exception:
        logger.debug("invalidate_cache: fallo best-effort ignorado", exc_info=True)


def get_runtime_str(db: Session, key: str, org_id: Optional[str] = None, default: Any = _MISSING) -> Optional[str]:
    raw = _read_raw(db, key, org_id)
    if raw is not None:
        return raw
    env_val = _env_fallback(key)
    if env_val is not _MISSING:
        return None if env_val is None else str(env_val)
    if default is _MISSING:
        return None
    return None if default is None else str(default)


def get_runtime_int(db: Session, key: str, org_id: Optional[str] = None, default: Any = _MISSING) -> Optional[int]:
    raw = _read_raw(db, key, org_id)
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            logger.warning("Setting %s has non-int value %r; falling back", key, raw)
    env_val = _env_fallback(key)
    if env_val is not _MISSING and env_val is not None:
        return int(env_val)
    if default is _MISSING or default is None:
        return None
    return int(default)


def get_runtime_float(db: Session, key: str, org_id: Optional[str] = None, default: Any = _MISSING) -> Optional[float]:
    raw = _read_raw(db, key, org_id)
    if raw is not None:
        try:
            return float(raw)
        except (TypeError, ValueError):
            logger.warning("Setting %s has non-float value %r; falling back", key, raw)
    env_val = _env_fallback(key)
    if env_val is not _MISSING and env_val is not None:
        return float(env_val)
    if default is _MISSING or default is None:
        return None
    return float(default)


def get_runtime_bool(db: Session, key: str, org_id: Optional[str] = None, default: Any = _MISSING) -> Optional[bool]:
    raw = _read_raw(db, key, org_id)
    if raw is not None:
        return raw.strip().lower() in {"1", "true", "yes", "on", "y"}
    env_val = _env_fallback(key)
    if env_val is not _MISSING and env_val is not None:
        return bool(env_val)
    if default is _MISSING or default is None:
        return None
    return bool(default)


def get_runtime_namespace(db: Session, keys: dict[str, str], org_id: Optional[str] = None):
    """Bulk-load a set of runtime flags into a SimpleNamespace.

    ``keys`` maps setting-name → type ("int" | "float" | "bool" | "str").
    Returned object exposes each setting as an attribute so existing code that
    does ``s.HEALTH_WEIGHT_NPS`` keeps working after swapping
    ``s = settings`` for ``s = get_runtime_namespace(db, {...})``.
    """
    from types import SimpleNamespace
    fns = {"int": get_runtime_int, "float": get_runtime_float, "bool": get_runtime_bool, "str": get_runtime_str}
    values = {key: fns[type_](db, key, org_id) for key, type_ in keys.items()}
    return SimpleNamespace(**values)


def _espera_saliente(db, clave: str, default: Optional[float]) -> float:
    """Ajuste en vivo (fila global) → valor puesto por el operador (`.env`/entorno)
    → `default` del sitio de llamada → defecto de `Settings`.

    Auditoria 2026-11 (#38): antes `default` no servia (el campo de `Settings`
    siempre existe), y los sitios con 15 s esperaban 10. Asi cada llamada
    conserva su espera de siempre hasta que el operador fija el ajuste, y
    entonces manda el ajuste en todas.
    """
    if db is not None:
        try:
            raw = _read_raw(db, clave, None)
            if raw is not None:
                return float(raw)
        except Exception:
            logger.debug("%s: ajuste en vivo no disponible", clave, exc_info=True)
    if default is None or clave in app_settings.model_fields_set:
        return float(getattr(app_settings, clave))
    return float(default)


def outbound_http_timeout(db=None, default: Optional[float] = None) -> float:
    """Espera (s) de una llamada de red saliente (HTTP, SMTP, IMAP): `OUTBOUND_HTTP_TIMEOUT_SECONDS`.

    `default`: la espera de ese sitio mientras el operador no fije el ajuste.
    Sin `db` no se consulta el ajuste en vivo, solo el entorno.
    """
    return _espera_saliente(db, "OUTBOUND_HTTP_TIMEOUT_SECONDS", default)


def outbound_ai_timeout(db=None, default: Optional[float] = None) -> float:
    """Espera (s) de una llamada a un proveedor de IA (LLM, voz a texto): `OUTBOUND_AI_TIMEOUT_SECONDS`."""
    return _espera_saliente(db, "OUTBOUND_AI_TIMEOUT_SECONDS", default)


#: Ajustes de la plataforma: se leen en su fila global y sólo los cambia el
#: superadmin (revisión 2026-11). Un admin de empresa podía «cambiarlos» para su
#: empresa y no tenían efecto, porque nadie los lee por empresa. La guarda
#: `tests/test_ajustes_de_plataforma_2026_11.py` comprueba que toda clave leída
#: sólo en global está aquí (o se arregla su lectura).
AJUSTES_DE_PLATAFORMA = frozenset({
    # Tipos de cambio del BCE: una tabla global para toda la instalacion (2026-11)
    "EXCHANGE_RATES_AUTO_UPDATE",
    # Claves y firma de tokens
    "KEY_ROTATION_ENABLED", "JWT_KEY_ROTATION_DAYS", "JWT_KEY_RETENTION_COUNT", "INTEGRATION_SECRET_ROTATION_DAYS",
    "DEVELOPER_TOKEN_TTL_MINUTES", "PASSKEY_PASSWORDLESS_ENABLED", "REFRESH_TOKEN_EXPIRE_DAYS",
    # Red, métricas y tiempos de espera del servidor
    "TRUST_PROXY_HEADERS", "TRUSTED_PROXY_CIDRS", "METRICS_AUTH_TOKEN",
    "OUTBOUND_HTTP_TIMEOUT_SECONDS", "OUTBOUND_AI_TIMEOUT_SECONDS", "SSO_CLOCK_SKEW_SECONDS", "SSO_HTTP_TIMEOUT_SECONDS",
    # Empresas y suplantación
    "TENANT_DELETION_QUARANTINE_DAYS", "IMPERSONATION_ENABLED", "IMPERSONATION_MAX_MINUTES",
    # Colas de eventos de los trabajos de fondo
    "SD_EVENT_BATCH_SIZE", "SD_EVENT_MAX_ATTEMPTS", "AUTOMATIONS_EVENT_BATCH_SIZE",
    # Proveedores de IA y motor semántico (una configuración para toda la instalación)
    "AI_PROVIDER_ERROR_COOLDOWN_SECONDS", "SEMANTIC_EMBEDDINGS_BACKEND",
    "SEM_WEIGHT_PROFILE", "SEM_WEIGHT_HISTORY", "SEM_TOP_K_HISTORY", "SEM_MULTI_ROLE_FACTOR",
    # Nombre de la plataforma (respaldo cuando una empresa no tiene marca propia)
    "PROJECT_NAME",
})


def get_runtime_group(db: Session, group: str, org_id: Optional[str] = None) -> list[dict]:
    """Return the effective value of every setting in a UI-exposed group."""
    spec = RUNTIME_FLAG_GROUPS.get(group)
    if spec is None:
        raise ValueError(f"unknown runtime-flag group: {group}")
    getters = {"int": get_runtime_int, "float": get_runtime_float, "bool": get_runtime_bool, "str": get_runtime_str}
    out: list[dict] = []
    for key, type_, label in spec:
        value = getters[type_](db, key, org_id)
        out.append({"key": key, "type": type_, "label": label, "value": value,
                    "plataforma": key in AJUSTES_DE_PLATAFORMA})
    return out


def _upsert_setting_at_scope(db: Session, key: str, value: str, org_id: Optional[str]) -> AppSetting:
    """Strict per-scope upsert — never falls back to the global row.

    Unlike `update_setting` (which has fallback semantics for the legacy
    general-settings flow), this targets *exactly* the (key, org_id) row.
    Required for runtime-flag overrides where a per-org write must NOT mutate
    the global row.
    """
    query = db.query(AppSetting).filter(AppSetting.key == key)
    if org_id is None:
        row = query.filter(AppSetting.organization_id.is_(None)).first()
    else:
        row = query.filter(AppSetting.organization_id == org_id).first()
    if row is None:
        row = AppSetting(key=key, value=value, organization_id=org_id)
        db.add(row)
    else:
        row.value = value
    db.commit()
    db.refresh(row)
    return row


def set_runtime_value(
    db: Session,
    group: str,
    key: str,
    value: Any,
    org_id: Optional[str],
    *,
    actor_id: Optional[str] = None,
    actor_ip: Optional[str] = None,
    actor_ua: Optional[str] = None,
) -> dict:
    """Validate + persist + invalidate cache for a single runtime flag.

    Also records an audit-log entry (best effort) capturing actor and old/new
    values. None of the audit fields are required by callers, but passing them
    through from the endpoint produces a meaningful trail.
    """
    spec = RUNTIME_FLAG_GROUPS.get(group)
    if spec is None:
        raise ValueError(f"unknown runtime-flag group: {group}")
    entry = next((e for e in spec if e[0] == key), None)
    if entry is None:
        raise ValueError(f"key {key!r} is not part of group {group!r}")
    _, type_, _ = entry

    try:
        if type_ == "int":
            stored = str(int(value))
        elif type_ == "float":
            stored = str(float(value))
        elif type_ == "bool":
            stored = "true" if (value if isinstance(value, bool) else str(value).strip().lower() in {"1", "true", "yes", "on"}) else "false"
        else:
            stored = str(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid value for {key} (expected {type_}): {exc}") from exc

    # Capture old value pre-write for the audit trail. Runtime flags are
    # plaintext (no secrets), so is_secret=False always.
    pre_row = (
        db.query(AppSetting)
        .filter(AppSetting.key == key, AppSetting.organization_id == org_id if org_id is not None else AppSetting.organization_id.is_(None))
        .first()
    )
    old_value = pre_row.value if pre_row is not None else None

    updated = _upsert_setting_at_scope(db, key, stored, org_id)
    invalidate_cache(key)

    try:
        from app.services.settings_audit_service import record_change
        record_change(
            db,
            scope="runtime",
            key=key,
            is_secret=False,
            old_value=old_value,
            new_value=stored,
            actor_id=actor_id,
            actor_ip=actor_ip,
            actor_ua=actor_ua,
            organization_id=org_id,
        )
    except Exception:
        logger.debug("set_runtime_value: fallo best-effort ignorado", exc_info=True)

    return {"key": key, "value": updated.value, "organization_id": updated.organization_id}


def monedas(db: Session, org_id: Optional[str] = None) -> list[str]:
    """Las monedas de la empresa (`SUPPORTED_CURRENCIES`), con la de por defecto siempre incluida."""
    lista = [c.strip().upper() for c in str(get_runtime_str(db, "SUPPORTED_CURRENCIES", org_id) or "").split(",") if c.strip()]
    defecto = str(get_runtime_str(db, "DEFAULT_CURRENCY", org_id) or "").upper()
    if defecto and defecto not in lista:
        lista.insert(0, defecto)
    return lista


def simbolos_de_moneda(db: Optional[Session] = None, org_id: Optional[str] = None) -> dict[str, str]:
    crudo = get_runtime_str(db, "CURRENCY_SYMBOLS", org_id) if db is not None else app_settings.CURRENCY_SYMBOLS
    salida = {}
    for par in str(crudo or "").split(","):
        if ":" in par:
            k, v = par.split(":", 1)
            if k.strip() and v.strip():
                salida[k.strip().upper()] = v.strip()
    return salida
