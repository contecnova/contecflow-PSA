"""Licencias y hardware — fase 2: uso real (16-11-2026). Se leen en vivo por
empresa (grupo `licencias_uso` del catálogo de ajustes); estos son los valores
por defecto."""
from pydantic import Field


class ALMUsoSettingsMixin:
    ALM_USAGE_IDLE_DAYS: int = Field(
        default=60, env="ALM_USAGE_IDLE_DAYS",
        description="Licence usage — without use for more than N days: «no use»")
    ALM_USAGE_UNDERUSED_DAYS: int = Field(
        default=30, env="ALM_USAGE_UNDERUSED_DAYS",
        description="Licence usage — without use for more than N days (and up to the «no use» limit): «underused»")
    ALM_USAGE_MIN_ACTIVE_DAYS: int = Field(
        default=4, env="ALM_USAGE_MIN_ACTIVE_DAYS",
        description="Licence usage — when the source gives frequency, fewer active days than this in its period: «underused»")
    ALM_USAGE_STALE_DATA_DAYS: int = Field(
        default=7, env="ALM_USAGE_STALE_DATA_DAYS",
        description="Licence usage — evidence read more than N days ago is out of date (shown, never used to reclaim)")
    ALM_USAGE_SYNC_INTERVAL_HOURS: int = Field(
        default=24, env="ALM_USAGE_SYNC_INTERVAL_HOURS",
        description="Licence usage — scheduled sync reads each active source every N hours")
    ALM_USAGE_MAX_PAGES: int = Field(
        default=200, env="ALM_USAGE_MAX_PAGES",
        description="Licence usage — maximum pages a connector reads per call (protects against runaway paging)")
    ALM_USAGE_REPORT_PERIOD_DAYS: int = Field(
        default=30, env="ALM_USAGE_REPORT_PERIOD_DAYS",
        description="Licence usage — period of the usage reports and logs read (Microsoft 365 accepts 7, 30, 90 or 180)")
    ALM_USAGE_INTUNE_MAX_APPS: int = Field(
        default=500, env="ALM_USAGE_INTUNE_MAX_APPS",
        description="Licence usage — Intune: detected apps whose devices are read per sync")
    ALM_USAGE_SYNC_LOG_RETENTION_DAYS: int = Field(
        default=180, env="ALM_USAGE_SYNC_LOG_RETENTION_DAYS",
        description="Licence usage — sync records older than N days are deleted")
    ALM_USAGE_CREATE_ASSETS: bool = Field(
        default=True, env="ALM_USAGE_CREATE_ASSETS",
        description="Licence usage — an inventoried device that is not an asset yet is created as an asset")
    ALM_RECLAIM_GRACE_DAYS: int = Field(
        default=30, env="ALM_RECLAIM_GRACE_DAYS",
        description="Reclaim — an assignment younger than N days is never reclaimed")
    ALM_RECLAIM_KEEP_DAYS: int = Field(
        default=90, env="ALM_RECLAIM_KEEP_DAYS",
        description="Reclaim — when the holder says they still need it, they are left alone for N days")
    ALM_RIGHTSIZING_WINDOW_DAYS: int = Field(
        default=90, env="ALM_RIGHTSIZING_WINDOW_DAYS",
        description="Right-sizing — a service counts as used if it was used within the last N days")
    ALM_UNMANAGED_LOOKBACK_DAYS: int = Field(
        default=365, env="ALM_UNMANAGED_LOOKBACK_DAYS",
        description="Unmanaged software — software expenses of the last N days are analysed")
    ALM_UNMANAGED_MIN_OCCURRENCES: int = Field(
        default=2, env="ALM_UNMANAGED_MIN_OCCURRENCES",
        description="Unmanaged software — appearances needed to propose it (expenses, users or devices)")

    # Bases de las API de Google que leen las fuentes de uso (solo entorno; no son ajustes de empresa).
    GOOGLE_ADMIN_API_BASE: str = Field(
        default="https://admin.googleapis.com", env="GOOGLE_ADMIN_API_BASE",
        description="Licence usage — Google Admin SDK base URL (Directory and Reports)")
    GOOGLE_LICENSING_API_BASE: str = Field(
        default="https://licensing.googleapis.com", env="GOOGLE_LICENSING_API_BASE",
        description="Licence usage — Google Enterprise License Manager base URL")
