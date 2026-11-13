"""
Process, infrastructure and optional-backend switches.

Segunda auditoría 2026-11 (hallazgo 16): estas variables se leían con
`os.getenv`/`os.environ` repartidas por 36 ficheros (95 lecturas), sin tipo y sin aparecer en
`Settings`. Ahora viven aquí con el mismo nombre de variable de entorno y el
mismo valor por defecto. Las que siguen fuera de `Settings` están en la lista
blanca de `tests/test_auditoria_2026_11_config_2.py`, cada una con su motivo.

NOTE: This is a *mixin* — see `app.core.config_groups` package docstring.
"""
from typing import Optional

from pydantic import Field


class ProcesoSettingsMixin:
    # ── Schedulers ────────────────────────────────────────────────────────────
    ENABLE_APSCHEDULER: bool = Field(default=True, description="Run the in-process APScheduler.")
    ENABLE_CELERY_BEAT: bool = Field(default=False, description="Declares that Celery beat runs.")
    CELERY_BEAT: bool = Field(default=False, description="Legacy alias of ENABLE_CELERY_BEAT (either one on = beat).")
    FAIL_ON_DUAL_SCHEDULER: bool = Field(default=True, description="Refuse to boot with both schedulers on.")

    # ── Boot checks ───────────────────────────────────────────────────────────
    FAIL_ON_SCHEMA_DRIFT: Optional[bool] = Field(
        default=None, description="Abort boot on Alembic drift; unset = on in staging/production, off elsewhere.")
    EXPECTED_ALEMBIC_REVISION: str = Field(default="", description="Extra pinned Alembic revision checked at boot.")
    EXPOSE_API_DOCS: bool = Field(default=False, description="Expose Swagger/ReDoc/OpenAPI in production.")

    # ── Security switches (boot refuses some of them in staging/production) ──
    CSRF_DOUBLE_SUBMIT: bool = Field(default=False, description="Also require X-CSRF-Token == csrf_token cookie.")
    DISABLE_CSRF_MIDDLEWARE: bool = Field(default=False, description="Disable CSRF checks (refused in staging/production).")
    ENABLE_SUPERADMIN_BYPASS: bool = Field(default=False, description="Dev-only login bypass (development + SQLite only).")
    TENANT_AUTO_FILTER_GLOBAL: bool = Field(default=True, description="Global ORM tenant filter (read at import).")
    TENANT_AUTO_STAMP_ON_INSERT: bool = Field(default=True, description="Stamp organization_id on new rows (read at import).")

    # ── Internals and batch caps ─────────────────────────────────────────────
    REDIS_RECONNECT_BACKOFF_SECONDS: float = Field(default=30.0, description="Wait before retrying Redis after a failure.")
    PREDICTIVE_STATS_MAX_TICKETS: int = Field(default=200, description="Tickets analysed per predictive-stats request.")
    CHANGE_BATCH_SCORE_MAX: int = Field(default=100, description="Changes scored per CAB batch pass.")
    DUCKDB_PATH: str = Field(default="", description="OLAP DuckDB file; empty = /var/contecflow/olap.duckdb or a temp dir.")
    AI_MODELS_CATALOG_PATH: str = Field(default="", description="AI model/price catalogue JSON; empty = app/core/ai_models.json.")
    APP_DB_USER: str = Field(default="", description="Non-owner DB role created by `python -m app.db.rls`.")
    APP_DB_PASSWORD: str = Field(default="", description="Password of APP_DB_USER.")

    # ── Seed inputs ──────────────────────────────────────────────────────────
    SEED_USERS_DATA_PATH: str = Field(default="seed_users_data.json", description="Seed — users JSON.")
    SEED_CLIENTS_DATA_PATH: str = Field(default="seed_clients_data.json", description="Seed — clients JSON.")
    SEED_EMAIL_TEMPLATES_PATH: str = Field(default="seed_email_templates.json", description="Seed — email templates JSON.")
    SEED_API_KEY_DEMO: str = Field(default="nxpm_demo_integration_key_1234", description="Seed — demo API key (hashed on insert).")

    # ── Collaboration backends ───────────────────────────────────────────────
    UPLOADS_DIR: str = Field(default="uploads", description="Collaboration uploads root (distinct from UPLOAD_DIR).")
    COLLAB_SIGNED_MAX_ENTRIES: int = Field(default=20000, description="Max in-memory signed download tokens.")
    COLLAB_STORAGE_BACKEND: str = Field(default="local", description="local | s3 | minio.")
    COLLAB_S3_BUCKET: Optional[str] = Field(default=None, description="Collaboration S3 bucket.")
    COLLAB_S3_PREFIX: str = Field(default="collaboration/", description="Collaboration S3 key prefix.")
    COLLAB_S3_REGION: str = Field(default="eu-west-1", description="Collaboration S3 region.")
    COLLAB_S3_ENDPOINT: Optional[str] = Field(default=None, description="S3-compatible endpoint (MinIO, versitygw).")
    CLAMAV_ENABLED: bool = Field(default=False, description="Scan collaboration uploads with clamd.")
    CLAMAV_HOST: str = Field(default="localhost", description="clamd host.")
    CLAMAV_PORT: int = Field(default=3310, description="clamd port.")
    CLAMAV_SOCKET: Optional[str] = Field(default=None, description="clamd UNIX socket (wins over host/port).")
    CLAMAV_TIMEOUT: float = Field(default=30.0, description="clamd timeout (s).")
    COLLAB_SEARCH_BACKEND: str = Field(default="auto", description="auto | simple | pg | opensearch.")
    OPENSEARCH_URL: str = Field(default="http://localhost:9200", description="OpenSearch URL.")
    OPENSEARCH_USER: Optional[str] = Field(default=None, description="OpenSearch user.")
    OPENSEARCH_PASSWORD: Optional[str] = Field(default=None, description="OpenSearch password.")
    COLLAB_BUS_BACKEND: str = Field(default="memory", description="memory | redis | nats.")
    NATS_URL: str = Field(default="nats://localhost:4222", description="NATS URL for the nats bus.")
    COLLAB_QUEUE_WORKERS: int = Field(default=4, description="Collaboration in-process queue workers.")
    LIVEKIT_URL: str = Field(default="wss://livekit.local", description="LiveKit URL.")
    LIVEKIT_API_KEY: Optional[str] = Field(default=None, description="LiveKit API key.")
    LIVEKIT_API_SECRET: Optional[str] = Field(default=None, description="LiveKit API secret.")
    VAPID_CONTACT: str = Field(default="mailto:noreply@contecflow.local", description="Web push contact.")
    VAPID_PUBLIC_KEY: Optional[str] = Field(default=None, description="Web push public key.")
    VAPID_PRIVATE_KEY: Optional[str] = Field(default=None, description="Web push private key.")
    APP_PUBLIC_URL: str = Field(default="http://localhost:3000", description="Link base in the chat email digest.")

    # ── Collaboration OAuth providers (looked up by name from PROVIDERS) ─────
    MS365_TENANT_ID: str = Field(default="common", description="Microsoft 365 tenant for collaboration OAuth.")
    MS365_CLIENT_ID: Optional[str] = Field(default=None, description="Collaboration OAuth — Microsoft 365 client id.")
    MS365_CLIENT_SECRET: Optional[str] = Field(default=None, description="Collaboration OAuth — Microsoft 365 secret.")
    MS365_REDIRECT_URI: Optional[str] = Field(default=None, description="Collaboration OAuth — Microsoft 365 redirect.")
    JIRA_CLIENT_ID: Optional[str] = Field(default=None, description="Collaboration OAuth — Jira client id.")
    JIRA_CLIENT_SECRET: Optional[str] = Field(default=None, description="Collaboration OAuth — Jira secret.")
    JIRA_REDIRECT_URI: Optional[str] = Field(default=None, description="Collaboration OAuth — Jira redirect.")
    GITHUB_CLIENT_ID: Optional[str] = Field(default=None, description="Collaboration OAuth — GitHub client id.")
    GITHUB_CLIENT_SECRET: Optional[str] = Field(default=None, description="Collaboration OAuth — GitHub secret.")
    GITHUB_REDIRECT_URI: Optional[str] = Field(default=None, description="Collaboration OAuth — GitHub redirect.")
    GITLAB_CLIENT_ID: Optional[str] = Field(default=None, description="Collaboration OAuth — GitLab client id.")
    GITLAB_CLIENT_SECRET: Optional[str] = Field(default=None, description="Collaboration OAuth — GitLab secret.")
    GITLAB_REDIRECT_URI: Optional[str] = Field(default=None, description="Collaboration OAuth — GitLab redirect.")
    GOOGLE_CLIENT_ID: Optional[str] = Field(default=None, description="Collaboration OAuth — Google client id.")
    GOOGLE_CLIENT_SECRET: Optional[str] = Field(default=None, description="Collaboration OAuth — Google secret.")
    GOOGLE_REDIRECT_URI: Optional[str] = Field(default=None, description="Collaboration OAuth — Google redirect.")

    # ── Local Whisper STT ────────────────────────────────────────────────────
    WHISPER_LOCAL: bool = Field(default=False, description="Chat captions fall back to local whisper.")
    WHISPER_BIN: str = Field(default="whisper", description="whisper binary.")
    WHISPER_MODEL: str = Field(default="base", description="whisper model.")
    WHISPER_LOCAL_BIN: str = Field(default="", description="STT provider binary (wins over WHISPER_BIN).")
    WHISPER_LOCAL_MODEL: str = Field(default="", description="STT provider model (wins over WHISPER_MODEL).")
    WHISPER_LOCAL_LANGUAGE: str = Field(default="es", description="STT provider default language.")

    # ── Geo-IP of sign-ins (hallazgo 30) ─────────────────────────────────────
    GEOIP_LOOKUP_ENABLED: bool = Field(
        default=False, description="Send the public IP of each sign-in/refresh to GEOIP_LOOKUP_URL (off: privacy).")
    GEOIP_LOOKUP_URL: str = Field(default="https://ipapi.co/{ip}/json/", description="Geo-IP service; `{ip}` is replaced.")
    GEOIP_CACHE_TTL_SECONDS: int = Field(default=86400, description="Per-IP cache of geo-IP answers (s).")


#: Booleanos de este grupo: un valor vacío en el entorno (`X=`) vale su defecto
#: en lugar de tumbar el arranque, como pasaba con `os.getenv(...) == "1"`.
INTERRUPTORES_DE_PROCESO: tuple[str, ...] = (
    "ENABLE_APSCHEDULER", "ENABLE_CELERY_BEAT", "CELERY_BEAT", "FAIL_ON_DUAL_SCHEDULER",
    "FAIL_ON_SCHEMA_DRIFT", "EXPOSE_API_DOCS", "CSRF_DOUBLE_SUBMIT", "DISABLE_CSRF_MIDDLEWARE",
    "ENABLE_SUPERADMIN_BYPASS", "TENANT_AUTO_FILTER_GLOBAL", "TENANT_AUTO_STAMP_ON_INSERT",
    "CLAMAV_ENABLED", "WHISPER_LOCAL", "GEOIP_LOOKUP_ENABLED",
)
