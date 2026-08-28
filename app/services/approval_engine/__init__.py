"""approval_engine package — split from the former 1827-LOC god-file."""
# Barrel/re-export module: every import below exists to re-export a symbol from a
# submodule so that `from app.services.approval_engine import X` keeps working.
# ruff: noqa: F401
from app.services.approval_engine._base import *  # noqa: F403
from app.services.approval_engine.workflows import *  # noqa: F403
from app.services.approval_engine.requests import *  # noqa: F403
from app.services.approval_engine.timeouts import *  # noqa: F403
from app.services.approval_engine.analytics import *  # noqa: F403
from app.services.approval_engine.groups import *  # noqa: F403
from app.services.approval_engine._base import _is_authorized, _parse_trigger_conditions, _matches_conditions, _load_workflows_by_ids, _record_sod_violation, _notify_requester_approved, _apply_entity_final_decision
from app.services.approval_engine.workflows import _resolve_step_approver_preview
from app.services.approval_engine.requests import _load_request_and_workflow_for_decision, _validate_decision_authorization, _record_decision_row, _apply_rejected_decision, _apply_delegated_decision, _quorum_satisfied, _apply_approved_decision, _emit_decision_event, _check_auto_approval, _first_active_step, _step_condition_met, _trigger_chained_workflow
from app.services.approval_engine.timeouts import _handle_timeout_escalate, _handle_timeout_auto_approve, _handle_timeout_reject, _log_timeout_audit_event, _step_is_expired
from app.services.approval_engine.analytics import _empty_bottleneck_row, _stamp_bottleneck_row, _aggregate_bottleneck_decisions, _aggregate_bottleneck_pending, _compute_bottleneck_item, _compute_weekly_trend, _compute_top_workflows, _compute_bottleneck_recommendations, _load_bottleneck_requests, _empty_approver_load_row, _aggregate_decisions_per_user, _resolve_pending_responsible_user, _aggregate_pending_per_user, _build_approver_load_item
from app.services.approval_engine._base import logger, _FINANCIAL_ENTITY_TYPES, _WORKFLOW_TEMPLATES
