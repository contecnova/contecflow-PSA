"""
Shared score → band scales (segunda auditoría 2026-11, hallazgo 17).

The functions that apply them live in `app.core.escalas`; each value is also a
live setting (Admin → Settings → `risk` / `service_desk`).

NOTE: This is a *mixin* — see `app.core.config_groups` package docstring.
"""
from pydantic import Field


class EscalasSettingsMixin:
    # Probabilidad predicha (0-1) de un mal resultado → nivel de riesgo.
    RISK_PROBABILITY_CRITICAL: float = Field(default=0.75, description="Predicted probability (0-1) — critical from.")
    RISK_PROBABILITY_HIGH: float = Field(default=0.50, description="Predicted probability (0-1) — high from.")
    RISK_PROBABILITY_MEDIUM: float = Field(default=0.25, description="Predicted probability (0-1) — medium from.")

    # Puntuación de correlación de alertas (0-1) → acción sugerida.
    ALERT_CORRELATION_PROBLEM_SCORE: float = Field(
        default=0.65, description="Alert correlation — suggest/create a problem from this score (and ≥3 tickets).")
    ALERT_CORRELATION_REVIEW_SCORE: float = Field(
        default=0.35, description="Alert correlation — suggest review from this score.")
