"""
settings_service — business logic extracted from app/api/v1/endpoints/settings.py
Covers: general settings, project types/statuses, task statuses,
        departments, holidays.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.settings import (
    AppSetting, CustomProjectType, CustomProjectStatus,
    CustomTaskStatus, Department, Holiday,
)
from app.core.config import settings as app_settings

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


# ── Runtime-flag groups exposed in the Settings UI ────────────────────────────
# Each entry: (key, type, label, group). Used by the generic endpoints below
# to render a typed form and to validate writes. Keep this in sync with
# docs/CONFIG_MIGRATION_INVENTORY.md as new groups are migrated.

RUNTIME_FLAG_GROUPS: dict[str, list[tuple[str, str, str]]] = {
    "sla": [
        ("SLA_P1_RESPONSE_HOURS", "float", "P1 Critical — response (h)"),
        ("SLA_P1_RESOLUTION_HOURS", "float", "P1 Critical — resolution (h)"),
        ("SLA_P2_RESPONSE_HOURS", "float", "P2 High — response (h)"),
        ("SLA_P2_RESOLUTION_HOURS", "float", "P2 High — resolution (h)"),
        ("SLA_P3_RESPONSE_HOURS", "float", "P3 Medium — response (h)"),
        ("SLA_P3_RESOLUTION_HOURS", "float", "P3 Medium — resolution (h)"),
        ("SLA_P4_RESPONSE_HOURS", "float", "P4 Low — response (h)"),
        ("SLA_P4_RESOLUTION_HOURS", "float", "P4 Low — resolution (h)"),
        ("SLA_BUSINESS_HOURS_ONLY", "bool", "Without policy — business hours only"),
        ("SLA_BUSINESS_START_HOUR", "int", "Without policy — workday start (0-23)"),
        ("SLA_BUSINESS_END_HOUR", "int", "Without policy — workday end (1-24)"),
        ("SLA_BUSINESS_DAYS", "str", "Without policy — workdays (ISO, 1=Mon … 7=Sun)"),
        ("SLA_PREDICTION_WARNING_PCT", "float", "At risk when this share of the SLA is used (0-1)"),
        ("SLA_PREDICTION_HOURS_CRITICAL", "int", "Prediction — hours window (critical)"),
        ("SLA_PREDICTION_HOURS_HIGH", "int", "Prediction — hours window (high)"),
        ("SLA_PREDICTION_HOURS_MEDIUM", "int", "Prediction — hours window (medium)"),
        ("SLA_PREDICTION_HOURS_LOW", "int", "Prediction — hours window (low)"),
        ("SLA_PREDICTION_SEVERITY_CRITICAL_H", "float", "Prediction — severity threshold (critical h)"),
        ("SLA_PREDICTION_SEVERITY_HIGH_H", "float", "Prediction — severity threshold (high h)"),
    ],
    "service_desk": [
        ("SD_NOTIFY_REQUESTER_ON_CREATE", "bool", "Email the requester when a ticket is created"),
        ("SD_NOTIFY_REQUESTER_ON_REPLY", "bool", "Email the requester on public agent replies"),
        ("SD_NOTIFY_REQUESTER_ON_RESOLVE", "bool", "Email the requester when the ticket is resolved"),
        ("SD_NOTIFY_AGENTS_BY_EMAIL", "bool", "Also email agents (they always get in-app alerts)"),
        ("SD_INBOUND_ADDRESS", "str", "Support address: identifies the organization and is the Reply-To"),
        ("SD_REOPEN_ON_REPLY", "bool", "Inbound — a reply reopens a resolved ticket"),
        ("SD_CHANNEL_TICKET_TYPE", "str", "Inbound — ticket type for new emails (incident, service_request, question)"),
        ("SD_MAIL_MAX_PER_RUN", "int", "Inbound — emails read per run"),
        ("SD_MAIL_MAX_ATTACHMENT_MB", "int", "Inbound — max attachment size (MB)"),
        ("SD_CAB_GROUP_ID", "str", "Changes — queue (group id) acting as the CAB"),
        ("SD_CAB_APPROVAL_RULE", "str", "Changes — CAB rule: majority, all or any"),
        ("SD_CHANGE_AUTO_APPROVE_MAX_RISK", "int", "Changes — standard changes up to this risk score self-approve"),
        ("SD_EVENT_SEVERITY_MAP", "str", "Monitoring — alert severity → ticket priority (JSON)"),
        ("SD_EVENT_AUTO_RESOLVE", "bool", "Monitoring — resolve the incident when the alert recovers, if untouched"),
        ("SD_ONCALL_PRIORITIES", "str", "On-call — priorities that page the on-call agent"),
        ("SD_ONCALL_SMS", "bool", "On-call — also page by SMS"),
        ("SD_KB_REQUIRE_REVIEW", "bool", "Knowledge — articles need a reviewer to be published"),
        ("SD_KB_REVIEWER_GROUP_ID", "str", "Knowledge — queue (group id) of reviewers; empty: admins"),
        ("SD_TIME_TO_TIMESHEET", "bool", "Time on tickets with a project goes to the agent's timesheet"),
        ("SD_ASSET_REFRESH_DAYS", "int", "Assets — days before an expiry that open a renewal ticket (0: off)"),
        ("SD_EVENT_MAX_ATTEMPTS", "int", "Event delivery — max attempts"),
        ("SD_EVENT_BATCH_SIZE", "int", "Event delivery — events per run"),
    ],
    "health": [
        ("HEALTH_NPS_LOOKBACK_DAYS", "int", "NPS lookback (days)"),
        ("HEALTH_TICKET_LOOKBACK_DAYS", "int", "Ticket lookback (days)"),
        ("HEALTH_DEFAULT_NO_DATA", "float", "Score when no data (0-100)"),
        ("HEALTH_PORTAL_BASE_SCORE", "float", "Portal base score"),
        ("HEALTH_PORTAL_SCORE_PER_SESSION", "float", "Score per portal session"),
        ("HEALTH_WEIGHT_NPS", "float", "Weight — NPS (0-1)"),
        ("HEALTH_WEIGHT_DELIVERY", "float", "Weight — Delivery (0-1)"),
        ("HEALTH_WEIGHT_BUDGET", "float", "Weight — Budget (0-1)"),
        ("HEALTH_WEIGHT_TICKETS", "float", "Weight — Tickets (0-1)"),
        ("HEALTH_WEIGHT_PORTAL", "float", "Weight — Portal (0-1)"),
        ("HEALTH_THRESHOLD_EXCELLENT", "float", "Threshold — Excellent"),
        ("HEALTH_THRESHOLD_GOOD", "float", "Threshold — Good"),
        ("HEALTH_THRESHOLD_AT_RISK", "float", "Threshold — At Risk"),
        ("PROJECT_HEALTH_WEIGHT_SCHEDULE", "float", "Project — Schedule weight"),
        ("PROJECT_HEALTH_WEIGHT_BUDGET", "float", "Project — Budget weight"),
        ("PROJECT_HEALTH_WEIGHT_QUALITY", "float", "Project — Quality weight"),
        ("PROJECT_HEALTH_WEIGHT_VELOCITY", "float", "Project — Velocity weight"),
        ("PROJECT_HEALTH_WEIGHT_CLIENT", "float", "Project — Client weight"),
        ("PROJECT_HEALTH_TRAFFIC_GREEN", "float", "Project traffic — Green ≥"),
        ("PROJECT_HEALTH_TRAFFIC_YELLOW", "float", "Project traffic — Yellow ≥"),
        ("PROJECT_HEALTH_BUDGET_RATIO_GOOD", "float", "Budget ratio — Good ≤"),
        ("PROJECT_HEALTH_BUDGET_RATIO_OK", "float", "Budget ratio — OK ≤"),
        ("PROJECT_HEALTH_BUDGET_RATIO_WARN", "float", "Budget ratio — Warn ≤"),
    ],
    "semantic": [
        ("SEM_THRESHOLD_EXPERT_CACHE", "float", "Expert cache threshold (0-1)"),
        ("SEM_THRESHOLD_CRITICAL", "float", "Critical similarity threshold"),
        ("SEM_THRESHOLD_HIGH", "float", "High similarity threshold"),
        ("SEM_THRESHOLD_MEDIUM", "float", "Medium similarity threshold"),
        ("SEM_THRESHOLD_LOW", "float", "Low similarity threshold"),
        ("SEM_WEIGHT_PROFILE", "float", "Profile-match weight (0-1)"),
        ("SEM_WEIGHT_HISTORY", "float", "History-match weight (0-1)"),
        ("SEM_TOP_K_HISTORY", "int", "Top-K history items"),
        ("SEM_MULTI_ROLE_FACTOR", "float", "Multi-role factor (0-1)"),
    ],
    "password_policy": [
        ("MIN_PASSWORD_LENGTH", "int", "Min length"),
        ("PASSWORD_REQUIRE_UPPERCASE", "bool", "Require uppercase"),
        ("PASSWORD_REQUIRE_LOWERCASE", "bool", "Require lowercase"),
        ("PASSWORD_REQUIRE_DIGIT", "bool", "Require digit"),
        ("PASSWORD_REQUIRE_SPECIAL", "bool", "Require special char"),
        ("LOGIN_MAX_ATTEMPTS", "int", "Max login attempts"),
        ("LOGIN_ATTEMPT_WINDOW_SECONDS", "int", "Attempt window (s)"),
        ("LOGIN_LOCKOUT_SECONDS", "int", "Lockout duration (s)"),
    ],
    "locale": [
        ("DEFAULT_TIMEZONE", "str", "Default timezone"),
        ("DEFAULT_LANGUAGE", "str", "Default language"),
        ("DEFAULT_CURRENCY", "str", "Default currency"),
        ("DEFAULT_TAX_RATE", "float", "Default tax rate (%)"),
        ("DEFAULT_WORKING_HOURS_PER_DAY", "float", "Working hours/day"),
        ("DEFAULT_WEEKLY_CAPACITY_HOURS", "float", "Weekly capacity (h)"),
        ("DEFAULT_VACATION_DAYS_PER_YEAR", "int", "Vacation days/year"),
        ("DEFAULT_IMPUTATION_LOCKOUT_DAYS", "int", "Imputation lockout (days)"),
        ("DEFAULT_PROJECT_TYPE", "str", "Default project type"),
        ("DEFAULT_BILLING_TYPE", "str", "Default billing type"),
    ],
    "tokens": [
        ("ACCESS_TOKEN_EXPIRE_MINUTES", "int", "Access token TTL (minutes)"),
        ("ACCESS_TOKEN_MAX_MINUTES", "int", "Access token max TTL (minutes)"),
        ("REFRESH_TOKEN_EXPIRE_DAYS", "int", "Refresh token TTL (days)"),
    ],
    "key_rotation": [
        ("KEY_ROTATION_ENABLED", "bool", "Auto rotation enabled"),
        ("JWT_KEY_ROTATION_DAYS", "int", "JWT key rotation (days)"),
        ("JWT_KEY_RETENTION_COUNT", "int", "JWT keys retained"),
        ("INTEGRATION_SECRET_ROTATION_DAYS", "int", "Integration secret rotation (days)"),
    ],
    "ai": [
        ("CONTECFLOW_AI_MODEL", "str", "Default AI model"),
        ("SEMANTIC_EMBEDDINGS_BACKEND", "str", "Embeddings backend"),
        ("OPENAI_STT_MODEL", "str", "OpenAI STT model"),
        ("AI_COST_ALERT_USD_PER_DAY", "float", "AI daily cost alert ($)"),
        ("STT_PROVIDER", "str", "Primary STT provider"),
        ("STT_FALLBACK_PROVIDERS", "str", "STT fallback providers (CSV)"),
        ("AZURE_SPEECH_REGION", "str", "Azure Speech region"),
        ("AZURE_STT_LANGUAGE", "str", "Azure STT language"),
        ("GOOGLE_STT_LANGUAGE", "str", "Google STT language"),
    ],
    "feature_flags": [
        ("M365_CALENDAR_SYNC_ENABLED", "bool", "M365 calendar sync"),
        ("M365_TEAMS_NOTIFICATIONS_ENABLED", "bool", "M365 Teams notifications"),
        ("EXCHANGE_RATES_AUTO_UPDATE", "bool", "Auto-update exchange rates"),
    ],
    "storage": [
        ("S3_URL_EXPIRATION_HOURS", "int", "S3 presigned URL TTL (h)"),
        ("MAX_FILE_SIZE_MB", "int", "Max upload size (MB)"),
    ],
    "security_network": [
        ("TRUST_PROXY_HEADERS", "bool", "Trust X-Forwarded-* headers"),
        ("TRUSTED_PROXY_CIDRS", "str", "Trusted proxy CIDRs (CSV)"),
    ],
    "ui_branding": [
        ("WEBAUTHN_RP_NAME", "str", "WebAuthn relying-party name (display)"),
        ("FRONTEND_EMBED_BASE_URL", "str", "BI embed base URL"),
        ("PROJECT_NAME", "str", "Product display name"),
    ],
    "observability": [
        ("METRICS_AUTH_TOKEN", "str", "/metrics Bearer token (clear to disable auth)"),
    ],
    "timeouts": [
        ("OUTBOUND_HTTP_TIMEOUT_SECONDS", "float", "Outbound HTTP timeout (seconds)"),
        ("OUTBOUND_AI_TIMEOUT_SECONDS", "float", "Outbound AI calls timeout (seconds)"),
    ],
}


def outbound_http_timeout(db=None, default: float = 10.0) -> float:
    """Return effective HTTP timeout for outbound calls (UI override → env → default).

    Provided as a one-liner helper so any callsite using
    ``httpx.Client(timeout=...)`` can swap the literal for
    ``outbound_http_timeout(db)`` and adopt the runtime flag without further
    refactor. When ``db`` is None it falls back to env.
    """
    if db is not None:
        try:
            v = get_runtime_float(db, "OUTBOUND_HTTP_TIMEOUT_SECONDS")
            if v is not None:
                return v
        except Exception:
            logger.debug("outbound_http_timeout: fallo best-effort ignorado", exc_info=True)
    return getattr(app_settings, "OUTBOUND_HTTP_TIMEOUT_SECONDS", default)


def outbound_ai_timeout(db=None, default: float = 30.0) -> float:
    """Return effective timeout for outbound AI/LLM calls."""
    if db is not None:
        try:
            v = get_runtime_float(db, "OUTBOUND_AI_TIMEOUT_SECONDS")
            if v is not None:
                return v
        except Exception:
            logger.debug("outbound_ai_timeout: fallo best-effort ignorado", exc_info=True)
    return getattr(app_settings, "OUTBOUND_AI_TIMEOUT_SECONDS", default)


def get_runtime_group(db: Session, group: str, org_id: Optional[str] = None) -> list[dict]:
    """Return the effective value of every setting in a UI-exposed group."""
    spec = RUNTIME_FLAG_GROUPS.get(group)
    if spec is None:
        raise ValueError(f"unknown runtime-flag group: {group}")
    getters = {"int": get_runtime_int, "float": get_runtime_float, "bool": get_runtime_bool, "str": get_runtime_str}
    out: list[dict] = []
    for key, type_, label in spec:
        value = getters[type_](db, key, org_id)
        out.append({"key": key, "type": type_, "label": label, "value": value})
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


DEFAULT_SETTINGS = {
    "company_name": ("Contecflow", "Nombre de la empresa"),
    "company_logo_url": ("", "URL del logotipo"),
    "currency": (app_settings.DEFAULT_CURRENCY, "Moneda principal"),
    "timezone": (app_settings.DEFAULT_TIMEZONE, "Zona horaria"),
    "language": (app_settings.DEFAULT_LANGUAGE, "Idioma de la interfaz"),
    "work_hours_per_day": (str(app_settings.DEFAULT_WORKING_HOURS_PER_DAY), "Horas laborales por día"),
    "work_days_per_week": ("5", "Días laborales por semana"),
    "budget_alert_threshold": ("90", "% presupuesto para alertas"),
    "overload_threshold": ("100", "% carga para alerta de sobrecarga"),
    "idle_timeout_enabled": ("false", "Cierre de sesión por inactividad (true/false)"),
    "idle_timeout_minutes": ("30", "Minutos de inactividad antes de cerrar sesión"),
}

DEFAULT_PROJECT_TYPES = [
    ("development", "Desarrollo", "#00d4ff"),
    ("maintenance", "Mantenimiento", "#ffb800"),
    ("rd", "I+D", "#7c3aed"),
    ("internal", "Interno", "#7a8aaa"),
    ("consulting", "Consultoría", "#00e5a0"),
]

DEFAULT_PROJECT_STATUSES = [
    ("planning", "Planificación", "#7a8aaa", True),
    ("active", "Activo", "#00d4ff", False),
    ("paused", "Pausado", "#ffb800", False),
    ("closed", "Cerrado", "#00e5a0", False),
    ("cancelled", "Cancelado", "#ff4757", False),
]

DEFAULT_TASK_STATUSES = [
    ("todo", "Pendiente", "#7a8aaa", True),
    ("in_progress", "En progreso", "#00d4ff", False),
    ("blocked", "Bloqueada", "#ff4757", False),
    ("in_review", "En revisión", "#ffb800", False),
    ("done", "Completada", "#00e5a0", False),
]


# ── General settings ──────────────────────────────────────────────────────────

def get_general_settings(db: Session) -> list:
    for key, (value, desc) in DEFAULT_SETTINGS.items():
        exists = db.query(AppSetting).filter(
            AppSetting.key == key, AppSetting.organization_id.is_(None)
        ).first()
        if not exists:
            db.add(AppSetting(key=key, value=value, description=desc, organization_id=None))
    db.commit()
    return db.query(AppSetting).order_by(AppSetting.key).all()


def update_setting(key: str, value: str, org_id: Optional[str], db: Session) -> AppSetting:
    setting = db.query(AppSetting).filter(
        AppSetting.key == key, AppSetting.organization_id == org_id
    ).first() if org_id else None
    if not setting:
        setting = db.query(AppSetting).filter(
            AppSetting.key == key, AppSetting.organization_id.is_(None)
        ).first()
    if not setting:
        setting = AppSetting(key=key, value=value, organization_id=org_id)
        db.add(setting)
    else:
        setting.value = value
    db.commit()
    db.refresh(setting)
    invalidate_cache(key)
    return setting


# ── Project types ─────────────────────────────────────────────────────────────

def get_project_types(db: Session) -> list:
    if db.query(CustomProjectType).count() == 0:
        for i, (value, label, color) in enumerate(DEFAULT_PROJECT_TYPES):
            db.add(CustomProjectType(value=value, label=label, color=color, sort_order=i))
        db.commit()
    return db.query(CustomProjectType).filter(
        CustomProjectType.is_active == True
    ).order_by(CustomProjectType.sort_order).all()


def create_project_type(payload_dict: dict, db: Session) -> CustomProjectType:
    if db.query(CustomProjectType).filter(
        CustomProjectType.value == payload_dict["value"],
        CustomProjectType.is_active == True
    ).first():
        raise ValueError("Ya existe un tipo con ese valor")
    item = CustomProjectType(**payload_dict)
    db.add(item); db.commit(); db.refresh(item)
    return item


def update_project_type(item_id: str, payload_dict: dict, db: Session) -> CustomProjectType:
    item = db.query(CustomProjectType).filter(CustomProjectType.id == item_id).first()
    if not item:
        raise ValueError("not_found")
    for k, v in payload_dict.items():
        setattr(item, k, v)
    db.commit(); db.refresh(item)
    return item


def delete_project_type(item_id: str, db: Session) -> dict:
    item = db.query(CustomProjectType).filter(CustomProjectType.id == item_id).first()
    if not item:
        raise ValueError("not_found")
    item.is_active = False
    db.commit()
    return {"ok": True}


# ── Project statuses ──────────────────────────────────────────────────────────

def get_project_statuses(db: Session) -> list:
    if db.query(CustomProjectStatus).count() == 0:
        for i, (value, label, color, is_default) in enumerate(DEFAULT_PROJECT_STATUSES):
            db.add(CustomProjectStatus(value=value, label=label, color=color, is_default=is_default, sort_order=i))
        db.commit()
    return db.query(CustomProjectStatus).filter(
        CustomProjectStatus.is_active == True
    ).order_by(CustomProjectStatus.sort_order).all()


def create_project_status(payload_dict: dict, db: Session) -> CustomProjectStatus:
    if db.query(CustomProjectStatus).filter(
        CustomProjectStatus.value == payload_dict["value"],
        CustomProjectStatus.is_active == True
    ).first():
        raise ValueError("Ya existe un estado con ese valor")
    item = CustomProjectStatus(**payload_dict)
    db.add(item); db.commit(); db.refresh(item)
    return item


def update_project_status(item_id: str, payload_dict: dict, db: Session) -> CustomProjectStatus:
    item = db.query(CustomProjectStatus).filter(CustomProjectStatus.id == item_id).first()
    if not item:
        raise ValueError("not_found")
    for k, v in payload_dict.items():
        setattr(item, k, v)
    db.commit(); db.refresh(item)
    return item


def delete_project_status(item_id: str, db: Session) -> dict:
    item = db.query(CustomProjectStatus).filter(CustomProjectStatus.id == item_id).first()
    if not item:
        raise ValueError("not_found")
    item.is_active = False
    db.commit()
    return {"ok": True}


# ── Task statuses ─────────────────────────────────────────────────────────────

def get_task_statuses(db: Session) -> list:
    if db.query(CustomTaskStatus).count() == 0:
        for i, (value, label, color, is_default) in enumerate(DEFAULT_TASK_STATUSES):
            db.add(CustomTaskStatus(value=value, label=label, color=color, is_default=is_default, sort_order=i))
        db.commit()
    return db.query(CustomTaskStatus).filter(
        CustomTaskStatus.is_active == True
    ).order_by(CustomTaskStatus.sort_order).all()


def create_task_status(payload_dict: dict, db: Session) -> CustomTaskStatus:
    if db.query(CustomTaskStatus).filter(
        CustomTaskStatus.value == payload_dict["value"],
        CustomTaskStatus.is_active == True
    ).first():
        raise ValueError("Ya existe un estado con ese valor")
    item = CustomTaskStatus(**payload_dict)
    db.add(item); db.commit(); db.refresh(item)
    return item


def update_task_status(item_id: str, payload_dict: dict, db: Session) -> CustomTaskStatus:
    item = db.query(CustomTaskStatus).filter(CustomTaskStatus.id == item_id).first()
    if not item:
        raise ValueError("not_found")
    for k, v in payload_dict.items():
        setattr(item, k, v)
    db.commit(); db.refresh(item)
    return item


def delete_task_status(item_id: str, db: Session) -> dict:
    item = db.query(CustomTaskStatus).filter(CustomTaskStatus.id == item_id).first()
    if not item:
        raise ValueError("not_found")
    item.is_active = False
    db.commit()
    return {"ok": True}


# ── Departments ───────────────────────────────────────────────────────────────

def get_departments(db: Session) -> list:
    return db.query(Department).filter(Department.is_active == True).order_by(Department.name).all()


def create_department(payload_dict: dict, db: Session) -> Department:
    if db.query(Department).filter(
        Department.name == payload_dict["name"],
        Department.is_active == True
    ).first():
        raise ValueError("Ya existe un departamento con ese nombre")
    item = Department(**payload_dict)
    db.add(item); db.commit(); db.refresh(item)
    return item


def update_department(item_id: str, payload_dict: dict, db: Session) -> Department:
    item = db.query(Department).filter(Department.id == item_id).first()
    if not item:
        raise ValueError("not_found")
    for k, v in payload_dict.items():
        setattr(item, k, v)
    db.commit(); db.refresh(item)
    return item


def delete_department(item_id: str, db: Session) -> dict:
    item = db.query(Department).filter(Department.id == item_id).first()
    if not item:
        raise ValueError("not_found")

    # Check for dependencies (will be automatically SET NULL per FK config)
    dependencies = _check_department_dependencies(item_id, db)

    item.is_active = False
    db.commit()

    if dependencies:
        return {"ok": True, "warning": "Dependencias limpiadas", "details": dependencies}
    return {"ok": True}


# ── Holidays ──────────────────────────────────────────────────────────────────

def get_holidays(db: Session) -> list:
    return db.query(Holiday).order_by(Holiday.date).all()


def create_holiday(payload_dict: dict, db: Session) -> Holiday:
    item = Holiday(**payload_dict)
    db.add(item); db.commit(); db.refresh(item)
    return item


def update_holiday(item_id: str, payload_dict: dict, db: Session) -> Holiday:
    item = db.query(Holiday).filter(Holiday.id == item_id).first()
    if not item:
        raise ValueError("not_found")
    for k, v in payload_dict.items():
        setattr(item, k, v)
    db.commit(); db.refresh(item)
    return item


def delete_holiday(item_id: str, db: Session) -> dict:
    item = db.query(Holiday).filter(Holiday.id == item_id).first()
    if not item:
        raise ValueError("not_found")
    db.delete(item); db.commit()
    return {"ok": True}


# ── Dependency validation before delete ────────────────────────────────────────

def _check_department_dependencies(department_id: str, db: Session) -> list[str]:
    """Check if department has active dependencies.

    Returns list of dependency descriptions if found, empty list otherwise.
    Dependencies are automatically SET NULL per FK config, but we validate
    for informational purposes.
    """
    from app.models.alm import ALMCostCenter, ALMAsset

    dependencies = []

    # Check Cost Centers with this department
    center_count = db.query(ALMCostCenter).filter(ALMCostCenter.department_id == department_id).count()
    if center_count > 0:
        dependencies.append(f"{center_count} Centro(s) de coste asignado(s)")

    # Check Assets with this department
    asset_count = db.query(ALMAsset).filter(ALMAsset.department_id == department_id).count()
    if asset_count > 0:
        dependencies.append(f"{asset_count} Activo(s) asignado(s)")

    return dependencies
