"""`.env.example` sincronizado con `Settings` (segunda auditoría 2026-11, #23).

Faltaban variables que un operador necesita (METRICS_AUTH_TOKEN, STRIPE_*,
GEOIP_*, SLACK_SIGNING_SECRET, TRUST_PROXY_HEADERS…) y el comentario de Adobe
Sign remitía a una ADOBE_SIGN_CLIENT_ID «de abajo» que no existía. Estos tests
obligan a decidir, para cada campo nuevo de Settings, si va en el ejemplo o es
un ajuste fino que se queda fuera, y a que todo secreto esté documentado.
"""
from __future__ import annotations

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[1]
EJEMPLO = (REPO / ".env.example").read_text(encoding="utf-8")
#: Declaradas, activas (`VAR=`) o comentadas (`# VAR=`).
DECLARADAS = set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]*)=", EJEMPLO, re.M))
ACTIVAS = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", EJEMPLO, re.M))

_SECRETO = re.compile(r"(SECRET|PASSWORD|_PASS|_TOKEN|_KEY|_KEY_ID|DSN)$")

#: Familias de ajustes finos con defecto razonable (la mayoría, editables en
#: Settings → Config. dinámica). El pie de `.env.example` dice lo mismo.
_FAMILIAS_FUERA = (
    "HEALTH_", "PROJECT_HEALTH_", "EVM_", "RISK_", "SEM_", "SLA_", "AUTOMATIONS_",
    "NOTIFICATIONS_", "BPMN_", "LESSONS_", "BUDGET_", "COMPLIANCE_", "SD_", "KEDB_",
    "ASK_DATA_", "AI_", "BI_", "CONECTOR_", "CONTECMIND_", "CONTECINTELLIGENCE_",
    "COLLAB_", "LOGIN_", "PASSWORD_REQUIRE_", "ALERT_CORRELATION_", "ORG_DEFAULT_",
    "SEED_", "WHISPER_", "POLICY_",
)

#: Fuera a propósito, uno a uno.
_FUERA = {
    # Constantes de la aplicación.
    "PROJECT_NAME", "VERSION", "API_V1_STR",
    # Interruptores de desarrollo y pruebas: no deben llegar a producción.
    "ENABLE_SUPERADMIN_BYPASS", "DISABLE_CSRF_MIDDLEWARE",
    # Políticas de seguridad con defecto seguro, editables en la aplicación.
    "BCRYPT_ROUNDS", "IMPERSONATION_ENABLED", "PASSKEY_PASSWORDLESS_ENABLED",
    "JWT_KEY_RETENTION_COUNT", "JWT_KEY_ROTATION_DAYS", "KEY_ROTATION_ENABLED",
    "KEY_ROTATION_RUN_HOUR", "INTEGRATION_SECRET_ROTATION_DAYS", "RETENTION_MIN_DAYS",
    "TENANT_DELETION_QUARANTINE_DAYS", "WS_TICKET_TTL_SECONDS", "DEVELOPER_TOKEN_TTL_MINUTES",
    "SSO_CLOCK_SKEW_SECONDS", "SSO_RATE_LIMIT", "RATE_LIMIT_REQUIRE_REDIS_IN_PRODUCTION",
    "MCP_WRITE_MODE", "APPROVAL_EMAIL_LINK_HOURS", "DOCUMENT_CHECKOUT_HOURS",
    "REDIS_RECONNECT_BACKOFF_SECONDS", "WEBAUTHN_RP_NAME",
    # Reglas de negocio con defecto (moneda, gastos, costes, escenarios).
    "CURRENCY_SYMBOLS", "SUPPORTED_CURRENCIES", "EXPENSE_MANAGER_ROLES", "EXPENSE_MILEAGE_RATE",
    "DEFAULT_EMPLOYER_COST_PCT", "DEFAULT_PRODUCTIVE_HOURS_YEAR", "DEFAULT_SIMULATION_HOURLY_RATE",
    "SCENARIO_CAPACITY_ROLES", "COUNTRY_EMPLOYER_COSTS_PATH",
    # Endpoints públicos fijos de proveedores y su ajuste fino.
    "MICROSOFT_GRAPH_BASE", "SLACK_API_BASE", "TEAMS_BOT_ALLOWED_SERVICE_HOSTS",
    "TEAMS_BOT_TOKEN_SCOPE", "TEAMS_BOT_TOKEN_URL", "TEAMS_KB_ANSWERS_ENABLED",
    "M365_CALENDAR_SYNC_ENABLED", "M365_TEAMS_NOTIFICATIONS_ENABLED", "SHAREPOINT_SITE_ID",
    "FRONTEND_EMBED_BASE_URL",
    # Voz y semántica: modelos e idiomas con defecto.
    "OPENAI_STT_MODEL", "AZURE_STT_LANGUAGE", "GOOGLE_STT_LANGUAGE", "STT_FALLBACK_PROVIDERS",
    "EMBEDDING_MODEL_NAME", "SEMANTIC_EMBEDDINGS_BACKEND",
    # Proceso y despliegue que fijan setup.sh/compose o tienen defecto correcto.
    "CELERY_BEAT", "CELERY_AGENT_TASK_SOFT_TIME_LIMIT", "CELERY_AGENT_TASK_TIME_LIMIT",
    "EXPECTED_ALEMBIC_REVISION", "FAIL_ON_SCHEMA_DRIFT", "DUCKDB_PATH", "UPLOADS_DIR",
    # Por organización: se declara en la aplicación (docs/DESPLIEGUE.md, Twilio).
    "TWILIO_PHONE_NUMBERS",
}


def _nombres_de_entorno(nombre, campo) -> list[str]:
    alias = getattr(campo.validation_alias, "choices", None)
    return [a for a in alias if isinstance(a, str)] if alias else [nombre]


def _campos():
    from app.core.config import Settings

    return [(n, _nombres_de_entorno(n, c)) for n, c in Settings.model_fields.items()]


def _fuera(nombre: str) -> bool:
    return (nombre in _FUERA or nombre.startswith(_FAMILIAS_FUERA) or "_TIMEOUT" in nombre
            or "_MAX_" in nombre or nombre.endswith("_DOCS_URL"))


def test_cada_campo_de_settings_esta_en_el_ejemplo_o_fuera_a_proposito():
    sin_decidir = [n for n, envs in _campos() if not DECLARADAS & set(envs) and not _fuera(n)]
    assert not sin_decidir, (
        f"Campos de Settings sin declarar en .env.example ni excluidos en este test: {sin_decidir}. "
        "Añádelos al ejemplo (con un comentario) o, si son ajustes finos, a _FUERA con su motivo.")


def test_todo_secreto_de_settings_esta_en_el_ejemplo():
    sin_declarar = [n for n, envs in _campos() if _SECRETO.search(n) and not DECLARADAS & set(envs)]
    assert not sin_declarar, f"Secretos que el operador no ve en .env.example: {sin_declarar}"


def test_lo_que_pide_la_auditoria_esta_declarado():
    for nombre in ("METRICS_AUTH_TOKEN", "STRIPE_SECRET_KEY", "STRIPE_PUBLISHABLE_KEY",
                   "STRIPE_WEBHOOK_SECRET", "GEOIP_LOOKUP_ENABLED", "GEOIP_LOOKUP_URL",
                   "GEOIP_CACHE_TTL_SECONDS", "PROMETHEUS_MULTIPROC_DIR", "SLACK_SIGNING_SECRET",
                   "TRUST_PROXY_HEADERS", "TRUSTED_PROXY_CIDRS", "ADOBE_SIGN_CLIENT_ID"):
        assert nombre in DECLARADAS, nombre


def test_prometheus_multiproc_dir_no_va_activa():
    """prometheus_client entra en modo multiproceso con que la variable EXISTA;
    vacía en el .env (que compose pasa a worker y beat) rompería sus métricas."""
    assert "PROMETHEUS_MULTIPROC_DIR" not in ACTIVAS


def test_ninguna_variable_activa_del_ejemplo_esta_huerfana():
    """Toda `VAR=` activa la lee Settings, compose, setup.sh o el frontend (VITE_)."""
    compose = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
    setup = (REPO / "setup.sh").read_text(encoding="utf-8")
    de_settings = {e for _, envs in _campos() for e in envs}
    huerfanas = [v for v in ACTIVAS
                 if v not in de_settings and "${" + v not in compose and v not in setup
                 and not v.startswith("VITE_")]
    assert not huerfanas, f"Variables de .env.example que no lee nadie: {huerfanas}"
