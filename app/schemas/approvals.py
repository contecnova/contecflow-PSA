import json
import logging
from typing import Optional, Any, List

from pydantic import BaseModel, Field, ValidationError, field_validator


_logger = logging.getLogger(__name__)


# ── Audit #61: Pydantic validation for auto_approval_rules JSON-as-Text ────

class AutoApprovalRuleConditions(BaseModel):
    """Conditions evaluated by ``approval_engine._check_auto_approval``."""
    amount_lt: Optional[float] = None
    amount_gt: Optional[float] = None
    department: Optional[str] = None
    category: Optional[str] = None


class AutoApprovalRule(BaseModel):
    """Single rule inside ``ApprovalWorkflow.auto_approval_rules`` (JSON-as-Text).

    The model is intentionally permissive (``model_config.extra = "allow"``)
    so that future condition keys can be added in the engine without breaking
    historic rows.
    """
    action: str = "auto_approve"
    conditions: AutoApprovalRuleConditions = Field(
        default_factory=AutoApprovalRuleConditions
    )
    label: Optional[str] = None

    model_config = {"extra": "allow"}


def validate_auto_approval_rules(raw: Optional[str]) -> Optional[str]:
    """Validate and re-serialize ``auto_approval_rules`` JSON.

    - ``None`` / empty: returned unchanged.
    - Valid JSON list of rules: each rule is parsed through ``AutoApprovalRule``
      and re-emitted as JSON to guarantee a normalised payload.
    - Invalid JSON / wrong shape: raises ``ValueError`` so the caller can
      reject the request (write path).

    Read-side callers should prefer :func:`parse_auto_approval_rules` which
    falls back to the raw payload to preserve backward compatibility with
    rows persisted before this validator existed.
    """
    if not raw:
        return raw
    try:
        items = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"auto_approval_rules debe ser JSON válido: {exc}") from exc
    if not isinstance(items, list):
        raise ValueError("auto_approval_rules debe ser una lista de reglas.")
    validated = [AutoApprovalRule(**r).model_dump(exclude_none=True) for r in items]
    return json.dumps(validated)


def parse_auto_approval_rules(raw: Optional[str]) -> List[dict]:
    """Parse ``auto_approval_rules`` for read-side use with BC fallback."""
    if not raw:
        return []
    try:
        items = json.loads(raw)
    except (TypeError, ValueError):
        _logger.warning("auto_approval_rules JSON inválido, devolviendo lista vacía")
        return []
    if not isinstance(items, list):
        _logger.warning("auto_approval_rules no es una lista, devolviendo lista vacía")
        return []
    result: List[dict] = []
    for r in items:
        try:
            result.append(AutoApprovalRule(**r).model_dump(exclude_none=True))
        except (ValidationError, TypeError):
            _logger.warning("auto_approval_rule no validable, fallback al dict crudo")
            result.append(r if isinstance(r, dict) else {"raw": r})
    return result


class WorkflowIn(BaseModel):
    name: str
    description: Optional[str] = None
    entity_type: str
    is_default: bool = False
    trigger_conditions: Optional[str] = "{}"
    # v2 enterprise
    chain_on_approval_workflow_id: Optional[str] = None
    sla_block_on_breach: bool = False
    auto_approval_rules: Optional[str] = None

    @field_validator("auto_approval_rules", mode="before")
    @classmethod
    def _validate_auto_approval_rules(cls, v):
        # Empty/None passes through; non-empty must be JSON list of rules.
        if v is None or v == "":
            return v
        try:
            return validate_auto_approval_rules(v)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


class StepIn(BaseModel):
    step_order: int
    name: str
    approver_type: str
    approver_role: Optional[str] = None
    approver_user_id: Optional[str] = None
    approver_department: Optional[str] = None
    is_optional: bool = False
    timeout_hours: int = 72
    on_timeout: str = "escalate"
    escalate_to_user_id: Optional[str] = None
    # v2 enterprise
    approver_group_id: Optional[str] = None
    parallel_quorum: bool = False
    required_approvals: int = 1
    step_condition: Optional[str] = None
    requires_attachment: bool = False
    reminder_hours: Optional[int] = None

    @field_validator("approver_user_id", "escalate_to_user_id", "approver_group_id", mode="before")
    @classmethod
    def _empty_str_to_none(cls, v):
        return None if v == "" else v


class ApprovalRequestIn(BaseModel):
    workflow_id: Optional[str] = None
    entity_type: str
    entity_id: str
    entity_summary: Optional[str] = None
    context: Optional[Any] = None


class DecisionIn(BaseModel):
    decision: str
    note: Optional[str] = None
    delegate_to: Optional[str] = None
    attachment_url: Optional[str] = None
