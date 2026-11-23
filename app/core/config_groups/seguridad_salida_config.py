"""
Seguridad transversal de entrada y salida (auditoría 22-11-2026, arreglos del 23-11-2026).

- Límite global del cuerpo de las peticiones (01 M4): `app/core/limite_de_cuerpo.py`.
- Credenciales de plataforma en el discovery de la CMDB (02 A18):
  `app/services/cmdb/discovery.py`.
- Contraseña de Redis (01 M5): `app/core/redis_url.py`, docker-compose y setup.

Documentado en docs/seguridad/entrada_y_salida.md.

NOTE: This is a *mixin* — see `app.core.config_groups` package docstring.
"""
from typing import Optional

from pydantic import Field


class SeguridadSalidaSettingsMixin:
    MAX_REQUEST_BODY_MB: int = Field(
        default=110,
        description="Hard cap (MB) on any request body, checked by Content-Length and by counting streamed bytes "
                    "(413 above it). Keep it >= MAX_FILE_SIZE_MB plus form overhead; nginx has its own "
                    "client_max_body_size. 0 disables the check.")
    CMDB_DISCOVERY_ALLOW_PLATFORM_CREDENTIALS: bool = Field(
        default=False,
        description="Let CMDB discovery fall back to the SERVER's own cloud credentials (boto3 default chain, "
                    "in-cluster/local kubeconfig, DefaultAzureCredential, GCP ADC or a service-account file on "
                    "disk). Off: every provider must carry explicit credentials (confused-deputy guard).")
    JWT_KEYRING_CACHE_SECONDS: int = Field(
        default=60,
        description="How long each process caches the JWT key ring before re-reading it, so a rotation done by "
                    "another process (Celery) reaches the web workers; an unknown `kid` also forces a reload. "
                    "0 = cache until restart.")
    MIGRATION_BACKUP_MODE: str = Field(
        default="destructive",
        description="Backup before `scripts/migrar.py` applies migrations (setup.bat/setup.sh): `destructive` "
                    "(only if a pending revision drops/deletes data), `always` (any pending revision) or `off`. "
                    "SQLite: file copy; PostgreSQL: pg_dump if on PATH, otherwise a warning.")
    MIGRATION_BACKUP_DIR: str = Field(
        default="backups",
        description="Folder (relative to the project root) for the pre-migration backups. They hold personal data: "
                    "same access control and retention as the database.")
    REDIS_PASSWORD: Optional[str] = Field(
        default=None,
        description="Redis password (requirepass). Injected into REDIS_URL / CELERY_* URLs that carry no "
                    "credentials; docker-compose passes it to redis-server.")
    M365_PLATFORM_CREDENTIALS_ENABLED: bool = Field(
        default=False,
        description="Let a company WITHOUT its own 'Microsoft 365 / Graph' credential use the platform's "
                    "AZURE_TENANT_ID/AZURE_CLIENT_ID/AZURE_CLIENT_SECRET (audit 2026-11-22, 03 A-MP3). Off: "
                    "each company must store its own Azure app in Integrations; an application token of "
                    "the platform app reaches every mailbox, team and site of ITS tenant, so turn it on "
                    "only for a single-company install or when that tenant is the operator's own.")
    SMTP_TLS_VERIFY: bool = Field(
        default=True,
        description="Verify the SMTP server certificate and host name on SMTP_SSL (465) and STARTTLS "
                    "(audit 2026-11-22, 03 medium m-p). Turn off only for an internal relay with a "
                    "self-signed certificate; with it off a man in the middle can read the mail and the password.")
