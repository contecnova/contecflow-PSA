from pydantic_settings import BaseSettings
from pydantic import Field, ValidationInfo, field_validator
from typing import List, Optional

from app.core.config_groups import (
    AISettingsMixin,
    SLASettingsMixin,
    HealthSettingsMixin,
    SemanticSettingsMixin,
)


class Settings(
    AISettingsMixin,
    SLASettingsMixin,
    HealthSettingsMixin,
    SemanticSettingsMixin,
    BaseSettings,
):
    """
    Application settings.

    Domain-specific knobs (AI providers, SLA hours, health weights, semantic
    thresholds) live in mixin classes under `app.core.config_groups`. Everything
    that needs validators or is genuinely cross-cutting (security, secrets,
    URLs, infra) stays here.
    """

    # ── Project / API / Environment ──────────────────────────────────────────
    PROJECT_NAME: str = Field(default="Contecflow", env="PROJECT_NAME")
    VERSION: str = Field(default="23.9.3", env="VERSION")
    API_V1_STR: str = Field(default="/api/v1", env="API_V1_STR")
    API_V2_STR: str = Field(default="/api/v2", env="API_V2_STR")
    ENVIRONMENT: str = Field(default="development", env="ENVIRONMENT")
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")  # DEBUG|INFO|WARNING|ERROR|CRITICAL

    # ── Auth / Tokens ────────────────────────────────────────────────────────
    SECRET_KEY: str = Field(..., env="SECRET_KEY")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=15, env="ACCESS_TOKEN_EXPIRE_MINUTES")
    ACCESS_TOKEN_MAX_MINUTES: int = Field(default=30, env="ACCESS_TOKEN_MAX_MINUTES")
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30, env="REFRESH_TOKEN_EXPIRE_DAYS")

    # ── Key Management / Rotation ────────────────────────────────────────────
    KEY_ROTATION_ENABLED: bool = Field(default=True, env="KEY_ROTATION_ENABLED")
    JWT_KEY_ROTATION_DAYS: int = Field(default=30, env="JWT_KEY_ROTATION_DAYS")
    JWT_KEY_RETENTION_COUNT: int = Field(default=3, env="JWT_KEY_RETENTION_COUNT")
    INTEGRATION_SECRET_ROTATION_DAYS: int = Field(default=60, env="INTEGRATION_SECRET_ROTATION_DAYS")
    KEY_ROTATION_RUN_HOUR_UTC: int = Field(default=2, env="KEY_ROTATION_RUN_HOUR_UTC")

    # Optional KMS/HSM envelope mode (AWS KMS).
    KMS_PROVIDER: str = Field(default="", env="KMS_PROVIDER")  # "aws" to enable
    AWS_KMS_KEY_ID: str = Field(default="", env="AWS_KMS_KEY_ID")
    AWS_KMS_REGION: str = Field(default="", env="AWS_KMS_REGION")

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str = Field(..., env="DATABASE_URL")

    # ── Project pipeline defaults ────────────────────────────────────────────
    DEFAULT_PROJECT_TYPE: str = Field(default="consulting", env="DEFAULT_PROJECT_TYPE")
    DEFAULT_BILLING_TYPE: str = Field(default="time_material", env="DEFAULT_BILLING_TYPE")

    # ── CORS / Allowed origins (ALLOWED_ORIGINS, no CORS_ORIGINS) ───────────
    ALLOWED_ORIGINS: List[str] = Field(default_factory=lambda: [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ], env="ALLOWED_ORIGINS")

    # ── Bootstrap credentials & operational secrets ──────────────────────────
    SUPERADMIN_EMAIL: str = Field(..., env="SUPERADMIN_EMAIL")
    SUPERADMIN_PASSWORD: str = Field(..., env="SUPERADMIN_PASSWORD")

    CLIENT_PORTAL_SECRET: str = Field(..., env="CLIENT_PORTAL_SECRET")
    SCIM_BEARER_TOKEN: str = Field(default="", env="SCIM_BEARER_TOKEN")
    WEBHOOK_SECRET: str = Field(default="", env="WEBHOOK_SECRET")
    # Secret token for inbound email webhook (Mailgun/SendGrid/Postmark relay)
    # Set this to a long random string and configure your email relay to send it
    # as the X-Contecflow-Email-Secret header on every inbound parse callback.
    INBOUND_EMAIL_SECRET: str = Field(default="", env="INBOUND_EMAIL_SECRET")
    TRUST_PROXY_HEADERS: bool = Field(default=False, env="TRUST_PROXY_HEADERS")
    TRUSTED_PROXY_CIDRS: str = Field(default="127.0.0.1/32,::1/128", env="TRUSTED_PROXY_CIDRS")

    # ── Git integration (GitHub/GitLab webhook secrets) ───────────────────────
    # When non-empty, webhook requests are verified with HMAC-SHA256 (GitHub) or
    # token comparison (GitLab). When empty, all webhook requests are REJECTED.
    # Configure these in staging/production to receive git events securely.
    GITHUB_WEBHOOK_SECRET: str = Field(default="", env="GITHUB_WEBHOOK_SECRET")
    GITLAB_WEBHOOK_SECRET: str = Field(default="", env="GITLAB_WEBHOOK_SECRET")

    # ── E-Signature providers ─────────────────────────────────────────────────
    DOCUSIGN_INTEGRATION_KEY:  str = Field(default="", env="DOCUSIGN_INTEGRATION_KEY")
    DOCUSIGN_SECRET_KEY:       str = Field(default="", env="DOCUSIGN_SECRET_KEY")
    DOCUSIGN_ACCOUNT_ID:       str = Field(default="", env="DOCUSIGN_ACCOUNT_ID")
    DOCUSIGN_BASE_URL:         str = Field(default="", env="DOCUSIGN_BASE_URL")
    ADOBE_SIGN_CLIENT_ID:      str = Field(default="", env="ADOBE_SIGN_CLIENT_ID")
    ADOBE_SIGN_CLIENT_SECRET:  str = Field(default="", env="ADOBE_SIGN_CLIENT_SECRET")
    ADOBE_SIGN_BASE_URL:       str = Field(default="https://api.na1.adobesign.com/api/rest/v6", env="ADOBE_SIGN_BASE_URL")

    # ── SSO OAuth endpoints ───────────────────────────────────────────────────
    MICROSOFT_OAUTH_BASE: str = Field(
        default="https://login.microsoftonline.com", env="MICROSOFT_OAUTH_BASE"
    )
    GOOGLE_OAUTH_BASE: str = Field(
        default="https://accounts.google.com", env="GOOGLE_OAUTH_BASE"
    )
    GOOGLE_TOKEN_URL: str = Field(
        default="https://oauth2.googleapis.com/token", env="GOOGLE_TOKEN_URL"
    )

    # ── WebAuthn / Passkeys (FIDO2) ─────────────────────────────────────────
    WEBAUTHN_RP_ID: str = Field(default="localhost", env="WEBAUTHN_RP_ID")
    WEBAUTHN_RP_NAME: str = Field(default="Contecflow PSA", env="WEBAUTHN_RP_NAME")
    WEBAUTHN_ORIGIN: str = Field(default="http://localhost:5173", env="WEBAUTHN_ORIGIN")

    # NOTE: AI providers, models and cost alerts live in AISettingsMixin
    # (app/core/config_groups/ai_config.py).

    # ── Contabilidad (opcionales) ─────────────────────────────────────────────
    XERO_API_BASE: str = Field(default="https://api.xero.com/api.xro/2.0", env="XERO_API_BASE")
    QB_API_BASE: str = Field(default="https://quickbooks.api.intuit.com/v3/company", env="QB_API_BASE")

    # ── URLs ──────────────────────────────────────────────────────────────────
    BASE_URL: str = Field(default="http://localhost:8000", env="BASE_URL")

    # ── OpenTelemetry distributed tracing ───────────────────────────────────
    OTEL_ENABLED: bool = Field(default=False, env="OTEL_ENABLED")
    OTEL_SERVICE_NAME: str = Field(default="contecflow-api", env="OTEL_SERVICE_NAME")
    OTEL_EXPORTER_OTLP_ENDPOINT: str = Field(default="", env="OTEL_EXPORTER_OTLP_ENDPOINT")
    OTEL_EXPORTER_OTLP_HEADERS: str = Field(default="", env="OTEL_EXPORTER_OTLP_HEADERS")
    FRONTEND_URL: str = Field(default="http://localhost:5173", env="FRONTEND_URL")
    BACKEND_URL: str = Field(default="http://localhost:8000", env="BACKEND_URL")

    # ── Storage ───────────────────────────────────────────────────────────────
    PDF_STORAGE_PATH: str = Field(default="./storage/pdfs", env="PDF_STORAGE_PATH")

    # ── AWS S3 for Document Manager ────────────────────────────────────────────
    AWS_S3_BUCKET: str = Field(default="contecflow-documents", env="AWS_S3_BUCKET")
    AWS_REGION: str = Field(default="eu-west-1", env="AWS_REGION")
    AWS_ACCESS_KEY: Optional[str] = Field(default=None, env="AWS_ACCESS_KEY")
    AWS_SECRET_KEY: Optional[str] = Field(default=None, env="AWS_SECRET_KEY")
    S3_URL_EXPIRATION_HOURS: int = Field(default=24, env="S3_URL_EXPIRATION_HOURS")
    MAX_FILE_SIZE_MB: int = Field(default=100, env="MAX_FILE_SIZE_MB")

    # ── Notifications ──────────────────────────────────────────────────────
    SLACK_WEBHOOK_URL: Optional[str] = Field(default=None, env="SLACK_WEBHOOK_URL")
    NOTIFICATION_EMAIL_FROM: str = Field(default="alerts@contecflow.local", env="NOTIFICATION_EMAIL_FROM")

    # ── Imputation Lockout ─────────────────────────────────────────────────
    DEFAULT_IMPUTATION_LOCKOUT_DAYS: int = Field(default=14, env="DEFAULT_IMPUTATION_LOCKOUT_DAYS")

    # ── Locale / Internationalisation ─────────────────────────────────────────
    DEFAULT_TIMEZONE: str = Field(default="Europe/Madrid", env="DEFAULT_TIMEZONE")
    DEFAULT_LANGUAGE: str = Field(default="es", env="DEFAULT_LANGUAGE")
    DEFAULT_CURRENCY: str = Field(default="EUR", env="DEFAULT_CURRENCY")

    # ── Business rules ────────────────────────────────────────────────────────
    DEFAULT_TAX_RATE: float = Field(default=21.0, env="DEFAULT_TAX_RATE")
    MIN_PASSWORD_LENGTH: int = Field(default=8, env="MIN_PASSWORD_LENGTH")
    # bcrypt cost factor: 12 = default razonable en dev; 14+ recomendado en prod.
    # Cada incremento duplica el coste de hashing.
    BCRYPT_ROUNDS: int = Field(default=12, env="BCRYPT_ROUNDS")
    PASSWORD_REQUIRE_UPPERCASE: bool = Field(default=True, env="PASSWORD_REQUIRE_UPPERCASE")
    PASSWORD_REQUIRE_LOWERCASE: bool = Field(default=True, env="PASSWORD_REQUIRE_LOWERCASE")
    PASSWORD_REQUIRE_DIGIT: bool = Field(default=True, env="PASSWORD_REQUIRE_DIGIT")
    PASSWORD_REQUIRE_SPECIAL: bool = Field(default=True, env="PASSWORD_REQUIRE_SPECIAL")
    LOGIN_MAX_ATTEMPTS: int = Field(default=5, env="LOGIN_MAX_ATTEMPTS")
    LOGIN_ATTEMPT_WINDOW_SECONDS: int = Field(default=900, env="LOGIN_ATTEMPT_WINDOW_SECONDS")
    LOGIN_LOCKOUT_SECONDS: int = Field(default=900, env="LOGIN_LOCKOUT_SECONDS")
    DEFAULT_USER_PASSWORD: str = Field(..., env="DEFAULT_USER_PASSWORD")
    DEFAULT_WORKING_HOURS_PER_DAY: float = Field(default=8.0, env="DEFAULT_WORKING_HOURS_PER_DAY")
    DEFAULT_WEEKLY_CAPACITY_HOURS: float = Field(default=40.0, env="DEFAULT_WEEKLY_CAPACITY_HOURS")
    DEFAULT_VACATION_DAYS_PER_YEAR: int = Field(default=23, env="DEFAULT_VACATION_DAYS_PER_YEAR")

    # NOTE: SLA defaults & breach prediction live in SLASettingsMixin
    # (app/core/config_groups/sla_config.py).

    # ── Redis (Celery broker + KPI cache) ────────────────────────────────────
    REDIS_URL: Optional[str] = Field(default=None, env="REDIS_URL")
    RATE_LIMIT_REQUIRE_REDIS_IN_PRODUCTION: bool = Field(
        default=True,
        env="RATE_LIMIT_REQUIRE_REDIS_IN_PRODUCTION",
    )

    # ── Sentry (error tracking) ───────────────────────────────────────────────
    SENTRY_DSN: Optional[str] = Field(default=None, env="SENTRY_DSN")
    SENTRY_ENVIRONMENT: str = Field(default="development", env="SENTRY_ENVIRONMENT")

    # ── Microsoft 365 / Azure AD (deep integration) ────────────────────────────
    # Required for Graph API access (Calendar sync + Teams notifications)
    AZURE_TENANT_ID:     Optional[str] = Field(default=None, env="AZURE_TENANT_ID")
    AZURE_CLIENT_ID:     Optional[str] = Field(default=None, env="AZURE_CLIENT_ID")
    AZURE_CLIENT_SECRET: Optional[str] = Field(default=None, env="AZURE_CLIENT_SECRET")
    # Comma-separated UPNs of users who grant delegated calendar access.
    # For app-only Graph, only AZURE_TENANT_ID+CLIENT_ID+CLIENT_SECRET are needed.
    M365_CALENDAR_SYNC_ENABLED: bool = Field(default=False, env="M365_CALENDAR_SYNC_ENABLED")
    M365_TEAMS_NOTIFICATIONS_ENABLED: bool = Field(default=False, env="M365_TEAMS_NOTIFICATIONS_ENABLED")
    # Incoming Teams webhook for outbound notifications
    TEAMS_WEBHOOK_URL: Optional[str] = Field(default=None, env="TEAMS_WEBHOOK_URL")
    # BI embed in Teams / SharePoint
    SHAREPOINT_SITE_ID: Optional[str] = Field(default=None, env="SHAREPOINT_SITE_ID")
    # Base URL used to build embed iframe URLs (defaults to FRONTEND_URL)
    FRONTEND_EMBED_BASE_URL: str = Field(default="", env="FRONTEND_EMBED_BASE_URL")

    # ── SMTP (outbound email) ─────────────────────────────────────────────────
    SMTP_HOST: str = Field(default="", env="SMTP_HOST")
    SMTP_USER: str = Field(default="", env="SMTP_USER")
    SMTP_PORT: int = Field(default=587, env="SMTP_PORT")
    SMTP_PASS: str = Field(default="", env="SMTP_PASS")
    SMTP_FROM: str = Field(default="", env="SMTP_FROM")

    # NOTE: OpenAI fallback key & STT models live in AISettingsMixin.

    # ── STT (Speech-to-Text) provider — Item #51 ─────────────────────────────
    # Provider primario: openai | azure | google | whisper_local
    STT_PROVIDER: str = Field(default="openai", env="STT_PROVIDER")
    # Fallbacks (CSV ordenado) — se intentan si el primario falla
    STT_FALLBACK_PROVIDERS: str = Field(default="", env="STT_FALLBACK_PROVIDERS")
    # Azure Speech-to-Text
    AZURE_SPEECH_KEY: str = Field(default="", env="AZURE_SPEECH_KEY")
    AZURE_SPEECH_REGION: str = Field(default="westeurope", env="AZURE_SPEECH_REGION")
    AZURE_STT_LANGUAGE: str = Field(default="es-ES", env="AZURE_STT_LANGUAGE")
    # Google Cloud Speech-to-Text (API key auth — service account no soportado por simplicidad)
    GOOGLE_STT_API_KEY: str = Field(default="", env="GOOGLE_STT_API_KEY")
    GOOGLE_STT_LANGUAGE: str = Field(default="es-ES", env="GOOGLE_STT_LANGUAGE")

    # ── Slack integration ─────────────────────────────────────────────────────
    SLACK_API_BASE: str = Field(default="https://slack.com/api", env="SLACK_API_BASE")
    SLACK_SIGNING_SECRET: str = Field(default="", env="SLACK_SIGNING_SECRET")

    # ── Teams Bot ─────────────────────────────────────────────────────────────
    TEAMS_BOT_APP_ID: str = Field(default="", env="TEAMS_BOT_APP_ID")

    # ── QR code service (MFA provisioning) ───────────────────────────────────
    GOOGLE_CHART_URL: str = Field(
        default="https://chart.googleapis.com/chart", env="GOOGLE_CHART_URL"
    )

    # NOTE: AI cost alerting lives in AISettingsMixin.

    # ── Stripe payment gateway (v23.8) ────────────────────────────────────────
    STRIPE_SECRET_KEY:        Optional[str] = Field(default=None, env="STRIPE_SECRET_KEY")
    STRIPE_PUBLISHABLE_KEY:   Optional[str] = Field(default=None, env="STRIPE_PUBLISHABLE_KEY")
    STRIPE_WEBHOOK_SECRET:    Optional[str] = Field(default=None, env="STRIPE_WEBHOOK_SECRET")

    # ── Exchange rates (v23.8) ────────────────────────────────────────────────
    OPEN_EXCHANGE_RATES_APP_ID: Optional[str] = Field(default=None, env="OPEN_EXCHANGE_RATES_APP_ID")
    EXCHANGE_RATES_AUTO_UPDATE: bool = Field(default=False, env="EXCHANGE_RATES_AUTO_UPDATE")

    # ── Rate limiting ─────────────────────────────────────────────────────────
    RATE_LIMIT_DEFAULT: str = Field(default="200/minute", env="RATE_LIMIT_DEFAULT")

    # ── Celery task timeouts ──────────────────────────────────────────────────
    CELERY_AGENT_TASK_TIME_LIMIT: int = Field(default=300, env="CELERY_AGENT_TASK_TIME_LIMIT")
    CELERY_AGENT_TASK_SOFT_TIME_LIMIT: int = Field(default=280, env="CELERY_AGENT_TASK_SOFT_TIME_LIMIT")

    # ── Outbound HTTP timeouts ───────────────────────────────────────────────
    # Default timeout (seg) para llamadas HTTP a APIs externas (Slack, Jira,
    # webhooks, eSign, etc.). Antes hardcoded a 10.0 en >15 archivos.
    OUTBOUND_HTTP_TIMEOUT_SECONDS: float = Field(default=10.0, env="OUTBOUND_HTTP_TIMEOUT_SECONDS")
    # Timeout más largo para llamadas a proveedores de IA (modelos LLM,
    # transcripción) donde la latencia es naturalmente mayor.
    OUTBOUND_AI_TIMEOUT_SECONDS: float = Field(default=30.0, env="OUTBOUND_AI_TIMEOUT_SECONDS")

    # NOTE: customer & project health weights/thresholds live in HealthSettingsMixin
    # (app/core/config_groups/health_config.py).
    # NOTE: semantic classifier thresholds live in SemanticSettingsMixin
    # (app/core/config_groups/semantic_config.py).

    class Config:
        env_file = ".env"
        extra = "ignore"

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_must_be_strong(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long")
        insecure = {"contecflow-secret-key-change-in-production-min32chars!!", "REPLACE_ME", "change-me"}
        if v in insecure or v.startswith("REPLACE_ME") or v.upper().startswith("CHANGE_ME"):
            raise ValueError("SECRET_KEY must be changed from the default value before running")
        # Heurística simple de entropía: rechazar valores con baja variedad
        # de caracteres (típico de secrets generados a mano como "aaaa...").
        # Un secret hex/base64 generado con `secrets.token_hex` debería tener
        # al menos 10 caracteres únicos en sus primeros 32 bytes.
        unique_chars = len(set(v[:64]))
        if unique_chars < 10:
            raise ValueError(
                f"SECRET_KEY entropy is too low (only {unique_chars} unique chars). "
                "Generate with: python -c 'import secrets; print(secrets.token_hex(32))'"
            )
        # Rechazar patrones obvios: secuencias repetidas o todos iguales.
        if len(set(v)) == 1:
            raise ValueError("SECRET_KEY cannot be a single repeated character")
        return v

    @field_validator("ENVIRONMENT")
    @classmethod
    def environment_must_be_valid(cls, v: str) -> str:
        valid = {"development", "test", "staging", "production"}
        if v not in valid:
            raise ValueError(f"ENVIRONMENT must be one of {valid}, got '{v}'")
        return v

    @field_validator("DEFAULT_USER_PASSWORD")
    @classmethod
    def default_user_password_must_not_be_placeholder(cls, v: str, info: ValidationInfo) -> str:
        if v.upper().startswith("CHANGE_ME"):
            raise ValueError(
                "DEFAULT_USER_PASSWORD still has a placeholder value. "
                "Set a real password in .env or run ./setup.sh before seeding."
            )
        environment = info.data.get("ENVIRONMENT", "development")
        # En staging/production exigir password fuerte; en test mantener el
        # default conocido para que las suites no fallen, pero no permitirlo
        # más allá de development/test.
        if environment in {"staging", "production"} and v == "contecflow2024!":
            raise ValueError(
                "DEFAULT_USER_PASSWORD must be changed from the default value in "
                f"{environment}. Set a strong password in your .env file."
            )
        return v

    @field_validator("WEBHOOK_SECRET", "INBOUND_EMAIL_SECRET")
    @classmethod
    def operational_secrets_must_be_configured(cls, v: str, info: ValidationInfo) -> str:
        environment = info.data.get("ENVIRONMENT", "development")
        if environment in {"staging", "production"} and not (v or "").strip():
            raise ValueError(f"{info.field_name} must be configured in {environment}")
        if (v or "").strip() and len(v.strip()) < 24:
            raise ValueError(f"{info.field_name} must be at least 24 characters long")
        return v

    # ── URL/Origin validators (rechazar localhost/wildcard en producción) ────
    @staticmethod
    def _looks_like_localhost(url: str) -> bool:
        u = (url or "").lower()
        return (
            "localhost" in u
            or "127.0.0.1" in u
            or "0.0.0.0" in u
            or u.startswith("http://[::1]")
        )

    @field_validator("ALLOWED_ORIGINS")
    @classmethod
    def allowed_origins_must_be_explicit_in_prod(cls, v: List[str], info: ValidationInfo) -> List[str]:
        environment = info.data.get("ENVIRONMENT", "development")
        if environment in {"staging", "production"}:
            if not v:
                raise ValueError("ALLOWED_ORIGINS must be configured in staging/production")
            if "*" in v:
                raise ValueError(
                    "ALLOWED_ORIGINS cannot contain '*' with allow_credentials=True — "
                    "list explicit origins instead"
                )
            bad = [o for o in v if cls._looks_like_localhost(o)]
            if bad:
                raise ValueError(
                    f"ALLOWED_ORIGINS contains localhost values in {environment}: {bad}. "
                    "Configure real origins via ALLOWED_ORIGINS env var."
                )
        return v

    @field_validator("FRONTEND_URL", "BACKEND_URL", "BASE_URL", "WEBAUTHN_ORIGIN")
    @classmethod
    def url_must_not_be_localhost_in_prod(cls, v: str, info: ValidationInfo) -> str:
        environment = info.data.get("ENVIRONMENT", "development")
        if environment in {"staging", "production"} and cls._looks_like_localhost(v):
            raise ValueError(
                f"{info.field_name} must not point to localhost in {environment} "
                f"(got {v!r}). Set a real public URL in your .env."
            )
        return v

    @field_validator("WEBAUTHN_RP_ID")
    @classmethod
    def webauthn_rp_id_must_not_be_localhost_in_prod(cls, v: str, info: ValidationInfo) -> str:
        environment = info.data.get("ENVIRONMENT", "development")
        if environment in {"staging", "production"} and v.lower() in {"localhost", "127.0.0.1"}:
            raise ValueError(
                f"WEBAUTHN_RP_ID must be a real domain in {environment} (got {v!r})."
            )
        return v


settings = Settings()
