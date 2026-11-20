"""
Valores de negocio que estaban fijos en pantallas y servicios (19-11-2026).

Cada uno es un ajuste por empresa (`RUNTIME_FLAG_GROUPS`), se valida al
guardarlo (`app/services/settings_service/valores_de_negocio.py`) y se lee con
la empresa del registro o de la sesión. El valor por defecto es el que estaba
escrito en el código, para no cambiar el comportamiento:

- rampa canaria de un plan de despliegue `1,5,25,50,100` y duraciones
  30/45/60 min (antes en `ChangeRolloutPanel.tsx`);
- 24 meses de retención propuestos al crear una política del chat (antes en
  `ChatAdminPage.tsx` y en `RetentionPolicyIn`);
- máximo de 60 días de vacaciones asignados por persona y año (antes sólo en
  el `max="60"` de Configuración → Vacaciones; el servidor no lo comprobaba);
- plazos de los recordatorios y de los ciclos atascados de evaluaciones de
  desempeño (antes constantes de `perf_reminder_service.py`).

NOTE: This is a *mixin* — see `app.core.config_groups` package docstring.
"""
from pydantic import Field


class ValoresDeNegocioSettingsMixin:
    # ── Cambios: plan de despliegue canario ───────────────────────────────────
    CHANGE_CANARY_RAMP_PCT: str = Field(
        default="1,5,25,50,100",
        description="Canary rollout — % of users per phase (CSV, increasing, ends in 100).")
    CHANGE_CANARY_FIRST_MINUTES: int = Field(default=30, description="Canary rollout — minutes of the first phase.")
    CHANGE_CANARY_STEP_MINUTES: int = Field(default=45, description="Canary rollout — minutes of each middle phase.")
    CHANGE_CANARY_LAST_MINUTES: int = Field(default=60, description="Canary rollout — minutes of the last phase (100 %).")

    # ── Chat: retención propuesta al crear una política ──────────────────────
    CHAT_RETENTION_PROPOSED_MONTHS: int = Field(
        default=24, description="Chat — retention (months) proposed for a new policy; never above the company maximum.")

    # ── Vacaciones ───────────────────────────────────────────────────────────
    VACATION_MAX_DAYS_ENTITLED: int = Field(
        default=60, description="Vacation — maximum days that can be assigned to a person for a year.")

    # ── Evaluaciones de desempeño ────────────────────────────────────────────
    PERF_REMINDER_WINDOW_DAYS: int = Field(
        default=7, description="Performance reviews — remind reviewers when the cycle closes within N days.")
    PERF_REMINDER_UNDATED_CYCLE_DAYS: int = Field(
        default=30, description="Performance reviews — a cycle without end date is reminded after N days active.")
    PERF_STALLED_CYCLE_DAYS: int = Field(
        default=45, description="Performance reviews — a cycle active for more than N days with low completion is stalled.")
    PERF_STALLED_COMPLETION_PCT: float = Field(
        default=50.0, description="Performance reviews — completion (%) below which an overdue or old cycle is stalled.")
