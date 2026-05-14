"""
SLA priority-based response/resolution defaults and breach prediction thresholds.

Referenced by:
  - app/services/sla_service (SLA computation per priority)
  - app/services/sla_prediction_service (breach prediction)

NOTE: This is a *mixin* — see `app.core.config_groups` package docstring.
"""
from pydantic import Field


class SLASettingsMixin:
    # ── SLA defaults (hours) ──────────────────────────────────────────────────
    SLA_P1_RESPONSE_HOURS: float = Field(default=1.0, env="SLA_P1_RESPONSE_HOURS")
    SLA_P1_RESOLUTION_HOURS: float = Field(default=4.0, env="SLA_P1_RESOLUTION_HOURS")
    SLA_P2_RESPONSE_HOURS: float = Field(default=4.0, env="SLA_P2_RESPONSE_HOURS")
    SLA_P2_RESOLUTION_HOURS: float = Field(default=8.0, env="SLA_P2_RESOLUTION_HOURS")
    SLA_P3_RESPONSE_HOURS: float = Field(default=8.0, env="SLA_P3_RESPONSE_HOURS")
    SLA_P3_RESOLUTION_HOURS: float = Field(default=24.0, env="SLA_P3_RESOLUTION_HOURS")
    SLA_P4_RESPONSE_HOURS: float = Field(default=24.0, env="SLA_P4_RESPONSE_HOURS")
    SLA_P4_RESOLUTION_HOURS: float = Field(default=72.0, env="SLA_P4_RESOLUTION_HOURS")

    # ── SLA breach prediction thresholds ─────────────────────────────────────
    SLA_PREDICTION_HOURS_CRITICAL: int = Field(default=4, env="SLA_PREDICTION_HOURS_CRITICAL")
    SLA_PREDICTION_HOURS_HIGH: int = Field(default=8, env="SLA_PREDICTION_HOURS_HIGH")
    SLA_PREDICTION_HOURS_MEDIUM: int = Field(default=24, env="SLA_PREDICTION_HOURS_MEDIUM")
    SLA_PREDICTION_HOURS_LOW: int = Field(default=72, env="SLA_PREDICTION_HOURS_LOW")
    SLA_PREDICTION_WARNING_PCT: float = Field(default=0.70, env="SLA_PREDICTION_WARNING_PCT")
    SLA_PREDICTION_SEVERITY_CRITICAL_H: float = Field(default=1.0, env="SLA_PREDICTION_SEVERITY_CRITICAL_H")
    SLA_PREDICTION_SEVERITY_HIGH_H: float = Field(default=4.0, env="SLA_PREDICTION_SEVERITY_HIGH_H")
