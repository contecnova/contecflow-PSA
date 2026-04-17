import secrets
from pydantic_settings import BaseSettings
from pydantic import Field, ValidationInfo, field_validator
from typing import List, Optional


class Settings(BaseSettings):
    PROJECT_NAME: str = Field(default="Clarive", env="PROJECT_NAME")
    VERSION: str = Field(default="23.9.3", env="VERSION")
    API_V1_STR: str = Field(default="/api/v1", env="API_V1_STR")
    API_V2_STR: str = Field(default="/api/v2", env="API_V2_STR")
    ENVIRONMENT: str = Field(default="development", env="ENVIRONMENT")
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")  # DEBUG|INFO|WARNING|ERROR|CRITICAL

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

    DATABASE_URL: str = Field(..., env="DATABASE_URL")

    # Defaults for project pipeline etc.
    DEFAULT_PROJECT_TYPE: str = Field(default="consulting", env="DEFAULT_PROJECT_TYPE")
    DEFAULT_BILLING_TYPE: str = Field(default="time_material", env="DEFAULT_BILLING_TYPE")

    # Orígenes permitidos (ALLOWED_ORIGINS, no CORS_ORIGINS)
    ALLOWED_ORIGINS: List[str] = Field(default_factory=lambda: [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ], env="ALLOWED_ORIGINS")

    SUPERADMIN_EMAIL: str = Field(..., env="SUPERADMIN_EMAIL")
    SUPERADMIN_PASSWORD: str = Field(..., env="SUPERADMIN_PASSWORD")

    CLIENT_PORTAL_SECRET: str = Field(..., env="CLIENT_PORTAL_SECRET")
    SCIM_BEARER_TOKEN: str = Field(default="", env="SCIM_BEARER_TOKEN")
    WEBHOOK_SECRET: str = Field(default="", env="WEBHOOK_SECRET")
    # Secret token for inbound email webhook (Mailgun/SendGrid/Postmark relay)
    # Set this to a long random string and configure your email relay to send it
    # as the X-Clarive-Email-Secret header on every inbound parse callback.
    INBOUND_EMAIL_SECRET: str = Field(default="", env="INBOUND_EMAIL_SECRET")
    TRUST_PROXY_HEADERS: bool = Field(default=False, env="TRUST_PROXY_HEADERS")
    TRUSTED_PROXY_CIDRS: str = Field(default="127.0.0.1/32,::1/128", env="TRUSTED_PROXY_CIDRS")

    # ── Git integration (GitHub/GitLab webhook secrets) ───────────────────────
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
    WEBAUTHN_RP_NAME: str = Field(default="Clarive PSA", env="WEBAUTHN_RP_NAME")
    WEBAUTHN_ORIGIN: str = Field(default="http://localhost:5173", env="WEBAUTHN_ORIGIN")

    # ── AI providers (opcionales) ─────────────────────────────────────────────
    # Fallback API keys — used only when no provider is configured in the database.
    # Prefer configuring providers via the AI Providers admin panel in the UI.
    ANTHROPIC_API_KEY: str = Field(default="", env="ANTHROPIC_API_KEY")
    ANTHROPIC_API_URL: str = Field(default="https://api.anthropic.com/v1", env="ANTHROPIC_API_URL")
    ANTHROPIC_DOCS_URL: str = Field(default="https://www.anthropic.com/docs", env="ANTHROPIC_DOCS_URL")
    OPENAI_API_URL: str = Field(default="https://api.openai.com/v1", env="OPENAI_API_URL")
    OPENAI_DOCS_URL: str = Field(default="https://platform.openai.com/docs", env="OPENAI_DOCS_URL")
    GEMINI_API_URL: str = Field(default="https://generativelanguage.googleapis.com/v1beta", env="GEMINI_API_URL")  # v1beta soporta todos los modelos Gemini 2.x
    GEMINI_DOCS_URL: str = Field(default="https://developers.google.com/ai", env="GEMINI_DOCS_URL")
    DEEPSEEK_API_URL: str = Field(default="https://api.deepseek.com/v1", env="DEEPSEEK_API_URL")
    DEEPSEEK_DOCS_URL: str = Field(default="https://docs.deepseek.ai", env="DEEPSEEK_DOCS_URL")
    GROQ_API_URL: str = Field(default="https://api.groq.com/openai/v1", env="GROQ_API_URL")
    GROQ_DOCS_URL: str = Field(default="https://docs.groq.com", env="GROQ_DOCS_URL")
    MISTRAL_API_URL: str = Field(default="https://api.mistral.ai/v1", env="MISTRAL_API_URL")
    MISTRAL_DOCS_URL: str = Field(default="https://docs.mistral.ai", env="MISTRAL_DOCS_URL")
    OLLAMA_BASE_URL: str = Field(default="http://localhost:11434", env="OLLAMA_BASE_URL")
    OLLAMA_DOCS_URL: str = Field(default="https://ollama.com/docs", env="OLLAMA_DOCS_URL")
    # AZURE_OPENAI_API_URL must be set to your resource endpoint (e.g. https://<resource>.openai.azure.com/openai)
    AZURE_OPENAI_API_URL: str = Field(default="", env="AZURE_OPENAI_API_URL")
    AZURE_OPENAI_DOCS_URL: str = Field(default="https://oai.azure.com", env="AZURE_OPENAI_DOCS_URL")

    # Modelo IA de fallback (usado cuando no hay proveedor configurado en BD)
    NEXUS_AI_MODEL: str = Field(default="claude-haiku-4-5", env="NEXUS_AI_MODEL")
    # Semantic classifier backend: keep HTTP API lean by default.
    # "tfidf" avoids loading heavy torch/transformers dependencies in API pods.
    SEMANTIC_EMBEDDINGS_BACKEND: str = Field(default="tfidf", env="SEMANTIC_EMBEDDINGS_BACKEND")

    # ── Contabilidad (opcionales) ─────────────────────────────────────────────
    XERO_API_BASE: str = Field(default="https://api.xero.com/api.xro/2.0", env="XERO_API_BASE")
    QB_API_BASE: str = Field(default="https://quickbooks.api.intuit.com/v3/company", env="QB_API_BASE")

    # ── URLs ──────────────────────────────────────────────────────────────────
    BASE_URL: str = Field(default="http://localhost:8000", env="BASE_URL")
    FRONTEND_URL: str = Field(default="http://localhost:5173", env="FRONTEND_URL")
    BACKEND_URL: str = Field(default="http://localhost:8000", env="BACKEND_URL")

    # ── Storage ───────────────────────────────────────────────────────────────
    PDF_STORAGE_PATH: str = Field(default="./storage/pdfs", env="PDF_STORAGE_PATH")

    # ── AWS S3 for Document Manager ────────────────────────────────────────────
    AWS_S3_BUCKET: str = Field(default="nexuspm-documents", env="AWS_S3_BUCKET")
    AWS_REGION: str = Field(default="eu-west-1", env="AWS_REGION")
    AWS_ACCESS_KEY: Optional[str] = Field(default=None, env="AWS_ACCESS_KEY")
    AWS_SECRET_KEY: Optional[str] = Field(default=None, env="AWS_SECRET_KEY")
    S3_URL_EXPIRATION_HOURS: int = Field(default=24, env="S3_URL_EXPIRATION_HOURS")
    MAX_FILE_SIZE_MB: int = Field(default=100, env="MAX_FILE_SIZE_MB")

    # ── Notifications ──────────────────────────────────────────────────────
    SLACK_WEBHOOK_URL: Optional[str] = Field(default=None, env="SLACK_WEBHOOK_URL")
    NOTIFICATION_EMAIL_FROM: str = Field(default="alerts@nexuspm.local", env="NOTIFICATION_EMAIL_FROM")

    # ── Imputation Lockout ─────────────────────────────────────────────────
    DEFAULT_IMPUTATION_LOCKOUT_DAYS: int = Field(default=14, env="DEFAULT_IMPUTATION_LOCKOUT_DAYS")

    # ── Locale / Internationalisation ─────────────────────────────────────────
    DEFAULT_TIMEZONE: str = Field(default="Europe/Madrid", env="DEFAULT_TIMEZONE")
    DEFAULT_LANGUAGE: str = Field(default="es", env="DEFAULT_LANGUAGE")
    DEFAULT_CURRENCY: str = Field(default="EUR", env="DEFAULT_CURRENCY")

    # ── Business rules ────────────────────────────────────────────────────────
    DEFAULT_TAX_RATE: float = Field(default=21.0, env="DEFAULT_TAX_RATE")
    MIN_PASSWORD_LENGTH: int = Field(default=8, env="MIN_PASSWORD_LENGTH")
    PASSWORD_REQUIRE_UPPERCASE: bool = Field(default=True, env="PASSWORD_REQUIRE_UPPERCASE")
    PASSWORD_REQUIRE_LOWERCASE: bool = Field(default=True, env="PASSWORD_REQUIRE_LOWERCASE")
    PASSWORD_REQUIRE_DIGIT: bool = Field(default=True, env="PASSWORD_REQUIRE_DIGIT")
    PASSWORD_REQUIRE_SPECIAL: bool = Field(default=True, env="PASSWORD_REQUIRE_SPECIAL")
    LOGIN_MAX_ATTEMPTS: int = Field(default=5, env="LOGIN_MAX_ATTEMPTS")
    LOGIN_ATTEMPT_WINDOW_SECONDS: int = Field(default=900, env="LOGIN_ATTEMPT_WINDOW_SECONDS")
    LOGIN_LOCKOUT_SECONDS: int = Field(default=900, env="LOGIN_LOCKOUT_SECONDS")
    DEFAULT_USER_PASSWORD: str = Field(default_factory=lambda: secrets.token_urlsafe(16), env="DEFAULT_USER_PASSWORD")
    DEFAULT_WORKING_HOURS_PER_DAY: float = Field(default=8.0, env="DEFAULT_WORKING_HOURS_PER_DAY")
    DEFAULT_WEEKLY_CAPACITY_HOURS: float = Field(default=40.0, env="DEFAULT_WEEKLY_CAPACITY_HOURS")
    DEFAULT_VACATION_DAYS_PER_YEAR: int = Field(default=23, env="DEFAULT_VACATION_DAYS_PER_YEAR")

    # ── SLA defaults (hours) ──────────────────────────────────────────────────
    SLA_P1_RESPONSE_HOURS: float = Field(default=1.0, env="SLA_P1_RESPONSE_HOURS")
    SLA_P1_RESOLUTION_HOURS: float = Field(default=4.0, env="SLA_P1_RESOLUTION_HOURS")
    SLA_P2_RESPONSE_HOURS: float = Field(default=4.0, env="SLA_P2_RESPONSE_HOURS")
    SLA_P2_RESOLUTION_HOURS: float = Field(default=8.0, env="SLA_P2_RESOLUTION_HOURS")
    SLA_P3_RESPONSE_HOURS: float = Field(default=8.0, env="SLA_P3_RESPONSE_HOURS")
    SLA_P3_RESOLUTION_HOURS: float = Field(default=24.0, env="SLA_P3_RESOLUTION_HOURS")
    SLA_P4_RESPONSE_HOURS: float = Field(default=24.0, env="SLA_P4_RESPONSE_HOURS")
    SLA_P4_RESOLUTION_HOURS: float = Field(default=72.0, env="SLA_P4_RESOLUTION_HOURS")

    # ── Redis (Celery broker + KPI cache) ────────────────────────────────────
    REDIS_URL: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")
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

    # ── SMTP (outbound email) ─────────────────────────────────────────────────
    SMTP_HOST: str = Field(default="", env="SMTP_HOST")
    SMTP_USER: str = Field(default="", env="SMTP_USER")
    SMTP_PORT: int = Field(default=587, env="SMTP_PORT")
    SMTP_PASS: str = Field(default="", env="SMTP_PASS")
    SMTP_FROM: str = Field(default="", env="SMTP_FROM")

    # ── OpenAI (fallback key — prefer DB-configured provider) ────────────────
    OPENAI_API_KEY: str = Field(default="", env="OPENAI_API_KEY")

    # ── Slack integration ─────────────────────────────────────────────────────
    SLACK_API_BASE: str = Field(default="https://slack.com/api", env="SLACK_API_BASE")
    SLACK_SIGNING_SECRET: str = Field(default="", env="SLACK_SIGNING_SECRET")

    # ── Teams Bot ─────────────────────────────────────────────────────────────
    TEAMS_BOT_APP_ID: str = Field(default="", env="TEAMS_BOT_APP_ID")

    # ── QR code service (MFA provisioning) ───────────────────────────────────
    GOOGLE_CHART_URL: str = Field(
        default="https://chart.googleapis.com/chart", env="GOOGLE_CHART_URL"
    )

    # ── AI cost alerting ──────────────────────────────────────────────────────
    AI_COST_ALERT_USD_PER_DAY: float = Field(default=10.0, env="AI_COST_ALERT_USD_PER_DAY")

    # ── Stripe payment gateway (v23.8) ────────────────────────────────────────
    STRIPE_SECRET_KEY:        Optional[str] = Field(default=None, env="STRIPE_SECRET_KEY")
    STRIPE_PUBLISHABLE_KEY:   Optional[str] = Field(default=None, env="STRIPE_PUBLISHABLE_KEY")
    STRIPE_WEBHOOK_SECRET:    Optional[str] = Field(default=None, env="STRIPE_WEBHOOK_SECRET")

    # ── Exchange rates (v23.8) ────────────────────────────────────────────────
    OPEN_EXCHANGE_RATES_APP_ID: Optional[str] = Field(default=None, env="OPEN_EXCHANGE_RATES_APP_ID")
    EXCHANGE_RATES_AUTO_UPDATE: bool = Field(default=False, env="EXCHANGE_RATES_AUTO_UPDATE")

    class Config:
        env_file = ".env"
        extra = "ignore"

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_must_be_strong(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long")
        insecure = {"clarive-secret-key-change-in-production-min32chars!!", "REPLACE_ME", "change-me"}
        if v in insecure or v.startswith("REPLACE_ME") or v.upper().startswith("CHANGE_ME"):
            raise ValueError("SECRET_KEY must be changed from the default value before running")
        return v

    @field_validator("ENVIRONMENT")
    @classmethod
    def environment_must_be_valid(cls, v: str) -> str:
        valid = {"development", "test", "staging", "production"}
        if v not in valid:
            raise ValueError(f"ENVIRONMENT must be one of {valid}, got '{v}'")
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


settings = Settings()
