from pydantic import BaseModel

class SemConfigPatch(BaseModel):
    engine_mode: str | None = None
    threshold_ticket: float | None = None
    threshold_task: float | None = None
    threshold_expert_cache: float | None = None
    load_balance_weight: float | None = None
    threshold_critical: float | None = None
    threshold_high: float | None = None
    threshold_medium: float | None = None
    threshold_low: float | None = None
    history_decay_days: float | None = None
    auto_assign_tickets: bool | None = None
    auto_assign_tasks: bool | None = None
    local_model_name: str | None = None
