from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SemConfigPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine_mode: str | None = None
    embeddings_backend: str | None = None
    threshold_ticket: float | None = Field(default=None, ge=0.0, le=1.0)
    threshold_task: float | None = Field(default=None, ge=0.0, le=1.0)
    threshold_expert_cache: float | None = Field(default=None, ge=0.0, le=1.0)
    load_balance_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    threshold_critical: float | None = Field(default=None, ge=0.0, le=1.0)
    threshold_high: float | None = Field(default=None, ge=0.0, le=1.0)
    threshold_medium: float | None = Field(default=None, ge=0.0, le=1.0)
    threshold_low: float | None = Field(default=None, ge=0.0, le=1.0)
    history_decay_days: float | None = Field(default=None, gt=0.0, le=3650.0)
    auto_assign_tickets: bool | None = None
    auto_assign_tasks: bool | None = None
    local_model_name: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("engine_mode")
    @classmethod
    def normalize_engine_mode(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return value.strip().lower()

    @field_validator("embeddings_backend")
    @classmethod
    def normalize_embeddings_backend(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip().lower()
        if normalized not in {"tfidf", "transformer"}:
            raise ValueError("embeddings_backend must be 'tfidf' or 'transformer'")
        return normalized

    @model_validator(mode="after")
    def validate_threshold_order(self):
        # PATCH requests are commonly partial; validate order only for pairs
        # explicitly provided together in the same payload.
        if (
            self.threshold_critical is not None
            and self.threshold_high is not None
            and self.threshold_critical < self.threshold_high
        ):
            raise ValueError("threshold_critical must be >= threshold_high")

        if (
            self.threshold_high is not None
            and self.threshold_medium is not None
            and self.threshold_high < self.threshold_medium
        ):
            raise ValueError("threshold_high must be >= threshold_medium")

        if (
            self.threshold_medium is not None
            and self.threshold_low is not None
            and self.threshold_medium < self.threshold_low
        ):
            raise ValueError("threshold_medium must be >= threshold_low")
        return self
