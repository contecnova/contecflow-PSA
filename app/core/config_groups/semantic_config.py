"""
Semantic classifier fallback thresholds (override via SemConfig in DB).

Referenced by:
  - app/services/semantic_classifier (escalation threshold / weights)

NOTE: This is a *mixin* — see `app.core.config_groups` package docstring.
"""
from pydantic import Field


class SemanticSettingsMixin:
    # ── Semantic classifier fallback defaults (override via SemConfig in DB) ──
    SEM_THRESHOLD_EXPERT_CACHE: float = Field(default=0.92, env="SEM_THRESHOLD_EXPERT_CACHE")
    SEM_THRESHOLD_CRITICAL: float = Field(default=0.90, env="SEM_THRESHOLD_CRITICAL")
    SEM_THRESHOLD_HIGH: float = Field(default=0.72, env="SEM_THRESHOLD_HIGH")
    SEM_THRESHOLD_MEDIUM: float = Field(default=0.58, env="SEM_THRESHOLD_MEDIUM")
    SEM_THRESHOLD_LOW: float = Field(default=0.45, env="SEM_THRESHOLD_LOW")
    SEM_WEIGHT_PROFILE: float = Field(default=0.40, env="SEM_WEIGHT_PROFILE")
    SEM_WEIGHT_HISTORY: float = Field(default=0.60, env="SEM_WEIGHT_HISTORY")
    SEM_TOP_K_HISTORY: int = Field(default=3, env="SEM_TOP_K_HISTORY")
    SEM_MULTI_ROLE_FACTOR: float = Field(default=0.70, env="SEM_MULTI_ROLE_FACTOR")
