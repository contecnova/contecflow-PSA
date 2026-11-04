import json
import logging
from typing import Optional, Any, List

from pydantic import BaseModel, Field, ValidationError, field_validator


_logger = logging.getLogger(__name__)


# ── Audit #61: Pydantic validation for auto_approval_rules JSON-as-Text ────

class AutoApprovalRuleConditions(BaseModel):
    """Conditions evaluated by ``approval_engine._check_auto_approval``."""
    amount_lt: Optional[float] = Field(None, description="Importe debe ser menor que este umbral")
    amount_gt: Optional[float] = Field(None, description="Importe debe ser mayor que este umbral")
    department: Optional[str] = Field(None, description="Departamento al que se aplica la regla")
    category: Optional[str] = Field(None, description="Categoría a la que se aplica la regla")


class AutoApprovalRule(BaseModel):
    """Single rule inside ``ApprovalWorkflow.auto_approval_rules`` (JSON-as-Text).

    The model is intentionally permissive (``model_config.extra = "allow"``)
    so that future condition keys can be added in the engine without breaking
    historic rows.
    """
    action: str = Field("auto_approve", description="Acción a ejecutar cuando se cumplen las condiciones")
    conditions: AutoApprovalRuleConditions = Field(
        default_factory=AutoApprovalRuleConditions,
        description="Conjunto de condiciones evaluadas para la regla",
    )
    label: Optional[str] = Field(None, description="Etiqueta descriptiva de la regla")

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
    name: str = Field(..., description="Nombre del workflow de aprobación")
    description: Optional[str] = Field(None, description="Descripción detallada del workflow")
    entity_type: str = Field(..., description="Tipo de entidad sobre la que aplica el workflow")
    is_default: bool = Field(False, description="Indica si es el workflow por defecto para el tipo de entidad")
    trigger_conditions: Optional[str] = Field("{}", description="Condiciones JSON que activan el workflow")
    # v2 enterprise
    chain_on_approval_workflow_id: Optional[str] = Field(None, description="Workflow encadenado a ejecutar tras la aprobación")
    sla_block_on_breach: bool = Field(False, description="Bloquea la entidad si se incumple el SLA")
    auto_approval_rules: Optional[str] = Field(None, description="Reglas JSON de auto-aprobación")

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
    step_order: int = Field(..., description="Orden secuencial del paso dentro del workflow")
    name: str = Field(..., description="Nombre descriptivo del paso de aprobación")
    approver_type: str = Field(..., description="Tipo de aprobador (user, role, group, department)")
    approver_role: Optional[str] = Field(None, description="Rol del aprobador si aplica")
    approver_user_id: Optional[str] = Field(None, description="ID del usuario aprobador específico")
    approver_department: Optional[str] = Field(None, description="Departamento aprobador si aplica")
    is_optional: bool = Field(False, description="Indica si el paso puede omitirse")
    timeout_hours: int = Field(72, description="Horas hasta que se considera vencido el paso")
    on_timeout: str = Field("escalate", description="Acción al vencer el SLA (escalate, auto_approve, reject)")
    escalate_to_user_id: Optional[str] = Field(None, description="Usuario al que se escala en caso de timeout")
    # v2 enterprise
    approver_group_id: Optional[str] = Field(None, description="ID del grupo de aprobadores")
    parallel_quorum: bool = Field(False, description="Aprobación paralela con quorum requerido")
    required_approvals: int = Field(1, description="Número de aprobaciones requeridas para avanzar")
    step_condition: Optional[str] = Field(None, description="Condición JSON que debe cumplirse para activar el paso")
    requires_attachment: bool = Field(False, description="Indica si la decisión requiere adjuntar evidencia")
    reminder_hours: Optional[int] = Field(None, description="Horas tras las que se envía recordatorio")

    @field_validator("approver_user_id", "escalate_to_user_id", "approver_group_id", mode="before")
    @classmethod
    def _empty_str_to_none(cls, v):
        return None if v == "" else v

    @field_validator("on_timeout", mode="before")
    @classmethod
    def _accion_de_caducidad(cls, v):
        # Auditoria 2026-11: se guardaba cualquier texto, y `auto_reject` (el que
        # documentaba este campo) no lo reconocia el job: nunca actuaba.
        v = {"auto_reject": "reject"}.get(v, v)
        if v not in ("escalate", "auto_approve", "reject"):
            raise ValueError("on_timeout debe ser escalate, auto_approve o reject")
        return v


class ApprovalRequestIn(BaseModel):
    workflow_id: Optional[str] = Field(None, description="ID del workflow a ejecutar (opcional si hay default)")
    entity_type: str = Field(..., description="Tipo de entidad para la que se solicita aprobación")
    entity_id: str = Field(..., description="ID de la entidad sometida a aprobación")
    entity_summary: Optional[str] = Field(None, description="Resumen legible de la entidad para el aprobador")
    context: Optional[Any] = Field(None, description="Contexto adicional usado por las reglas de auto-aprobación")


class DecisionIn(BaseModel):
    decision: str = Field(..., description="Decisión del aprobador (approve, reject, delegate)")
    note: Optional[str] = Field(None, description="Comentario o justificación de la decisión")
    delegate_to: Optional[str] = Field(None, description="ID del usuario al que se delega la decisión")
    attachment_url: Optional[str] = Field(None, description="URL del documento adjunto como evidencia")
