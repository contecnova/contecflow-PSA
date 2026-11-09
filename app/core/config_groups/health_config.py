"""
Customer and project health scoring weights and thresholds.

Referenced by:
  - app/services/health_service (customer health: NPS/tickets/portal)
  - app/services/project_health_service (project health traffic-light scoring)

NOTE: This is a *mixin* — see `app.core.config_groups` package docstring.
"""
from pydantic import Field


class HealthSettingsMixin:
    # ── Customer health score ─────────────────────────────────────────────────
    HEALTH_NPS_LOOKBACK_DAYS: int = Field(default=90, env="HEALTH_NPS_LOOKBACK_DAYS")
    HEALTH_TICKET_LOOKBACK_DAYS: int = Field(default=30, env="HEALTH_TICKET_LOOKBACK_DAYS")
    HEALTH_DEFAULT_NO_DATA: float = Field(default=70.0, env="HEALTH_DEFAULT_NO_DATA")
    HEALTH_PORTAL_BASE_SCORE: float = Field(default=30.0, env="HEALTH_PORTAL_BASE_SCORE")
    HEALTH_PORTAL_SCORE_PER_SESSION: float = Field(default=7.0, env="HEALTH_PORTAL_SCORE_PER_SESSION")
    HEALTH_WEIGHT_NPS: float = Field(default=0.40, env="HEALTH_WEIGHT_NPS")
    HEALTH_WEIGHT_DELIVERY: float = Field(default=0.20, env="HEALTH_WEIGHT_DELIVERY")
    HEALTH_WEIGHT_BUDGET: float = Field(default=0.15, env="HEALTH_WEIGHT_BUDGET")
    HEALTH_WEIGHT_TICKETS: float = Field(default=0.15, env="HEALTH_WEIGHT_TICKETS")
    HEALTH_WEIGHT_PORTAL: float = Field(default=0.10, env="HEALTH_WEIGHT_PORTAL")
    HEALTH_THRESHOLD_EXCELLENT: float = Field(default=80.0, env="HEALTH_THRESHOLD_EXCELLENT")
    HEALTH_THRESHOLD_GOOD: float = Field(default=60.0, env="HEALTH_THRESHOLD_GOOD")
    HEALTH_THRESHOLD_AT_RISK: float = Field(default=40.0, env="HEALTH_THRESHOLD_AT_RISK")

    # ── Project health score ──────────────────────────────────────────────────
    PROJECT_HEALTH_WEIGHT_SCHEDULE: float = Field(default=0.30, env="PROJECT_HEALTH_WEIGHT_SCHEDULE")
    PROJECT_HEALTH_WEIGHT_BUDGET: float = Field(default=0.25, env="PROJECT_HEALTH_WEIGHT_BUDGET")
    PROJECT_HEALTH_WEIGHT_QUALITY: float = Field(default=0.20, env="PROJECT_HEALTH_WEIGHT_QUALITY")
    PROJECT_HEALTH_WEIGHT_VELOCITY: float = Field(default=0.15, env="PROJECT_HEALTH_WEIGHT_VELOCITY")
    PROJECT_HEALTH_WEIGHT_CLIENT: float = Field(default=0.10, env="PROJECT_HEALTH_WEIGHT_CLIENT")
    PROJECT_HEALTH_TRAFFIC_GREEN: float = Field(default=70.0, env="PROJECT_HEALTH_TRAFFIC_GREEN")
    PROJECT_HEALTH_TRAFFIC_YELLOW: float = Field(default=45.0, env="PROJECT_HEALTH_TRAFFIC_YELLOW")
    PROJECT_HEALTH_BUDGET_RATIO_GOOD: float = Field(default=0.80, env="PROJECT_HEALTH_BUDGET_RATIO_GOOD")
    PROJECT_HEALTH_BUDGET_RATIO_OK: float = Field(default=1.00, env="PROJECT_HEALTH_BUDGET_RATIO_OK")
    PROJECT_HEALTH_BUDGET_RATIO_WARN: float = Field(default=1.20, env="PROJECT_HEALTH_BUDGET_RATIO_WARN")
    # Semáforo de los índices EVM (CPI, SPI; TCPI por su inverso). Revisión
    # 2026-11: estaban fijos en el servidor y en la pantalla, y el de TCPI al revés.
    EVM_INDEX_GREEN_MIN: float = Field(default=0.90, env="EVM_INDEX_GREEN_MIN")
    EVM_INDEX_RED_BELOW: float = Field(default=0.85, env="EVM_INDEX_RED_BELOW")
