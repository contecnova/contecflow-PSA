"""
ai_governance_service — AI governance configuration and audit logging.
Controls enablement, rate limiting, and role-based access to AI modules.
"""
import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.ai_chat import AIActionLog, AIGovernanceConfig

_logger = logging.getLogger("v16_core")


def get_governance_config(db: Session) -> list:
    """Get all governance configurations, creating defaults if needed."""
    DEFAULT_MODULES = [
        "contecflowassist", "contecflowagent", "contecfloworacle",
        "meeting_assistant", "contract_intelligence", "knowledge_base", "voice",
    ]
    configs = db.query(AIGovernanceConfig).all()
    existing = {c.module for c in configs}
    for mod in DEFAULT_MODULES:
        if mod not in existing:
            db.add(AIGovernanceConfig(module=mod, is_enabled=True))
    db.commit()
    configs = db.query(AIGovernanceConfig).all()
    return [{
        "id": c.id, "module": c.module, "is_enabled": c.is_enabled,
        "requires_approval_for": json.loads(c.requires_approval_for or "[]"),
        "max_actions_per_day": c.max_actions_per_day,
        "allowed_roles": json.loads(c.allowed_roles or '["admin","pm"]'),
        "model_override": c.model_override,
    } for c in configs]


def update_governance_config(db: Session, module: str, payload: dict, user_id: str) -> dict:
    """Update governance configuration for a module."""
    config = db.query(AIGovernanceConfig).filter(AIGovernanceConfig.module == module).first()
    if not config:
        config = AIGovernanceConfig(module=module)
        db.add(config)
    for field in ["is_enabled", "max_actions_per_day", "model_override"]:
        if field in payload:
            setattr(config, field, payload[field])
    if "requires_approval_for" in payload:
        config.requires_approval_for = json.dumps(payload["requires_approval_for"])
    if "allowed_roles" in payload:
        config.allowed_roles = json.dumps(payload["allowed_roles"])
    config.updated_by = user_id
    db.commit()
    return {"ok": True}


def get_governance_logs(db: Session, module=None, status=None, days: int = 7, limit: int = 100) -> list:
    """Retrieve governance audit logs, optionally filtered by module/status/timeframe."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    q = db.query(AIActionLog).filter(AIActionLog.created_at >= since)
    if module:
        q = q.filter(AIActionLog.module == module)
    if status:
        q = q.filter(AIActionLog.status == status)
    logs = q.order_by(AIActionLog.created_at.desc()).limit(limit).all()
    return [{
        "id": l.id, "module": l.module, "action_type": l.action_type,
        "user_id": l.user_id,
        "input_summary": l.input_summary, "output_summary": l.output_summary,
        "tokens_used": l.tokens_used, "latency_ms": l.latency_ms,
        "status": l.status,
        "created_at": str(l.created_at)[:16],
    } for l in logs]


def get_governance_stats(db: Session, days: int = 30) -> dict:
    """Get governance statistics: API calls, token usage, costs, success rates."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    logs = db.query(AIActionLog).filter(AIActionLog.created_at >= since).all()

    by_module = {}
    for l in logs:
        if l.module not in by_module:
            by_module[l.module] = {"calls": 0, "tokens": 0, "errors": 0, "avg_latency": 0}
        by_module[l.module]["calls"] += 1
        by_module[l.module]["tokens"] += l.tokens_used or 0
        if l.status == "failed":
            by_module[l.module]["errors"] += 1
        by_module[l.module]["avg_latency"] += l.latency_ms or 0

    for m in by_module:
        calls = by_module[m]["calls"]
        if calls > 0:
            by_module[m]["avg_latency"] = round(by_module[m]["avg_latency"] / calls)

    total_tokens = sum(l.tokens_used or 0 for l in logs)
    est_cost_usd = round(total_tokens / 1_000_000 * 0.25, 4)

    return {
        "period_days": days,
        "total_calls": len(logs),
        "total_tokens": total_tokens,
        "estimated_cost_usd": est_cost_usd,
        "success_rate_pct": round(
            sum(1 for l in logs if l.status == "success") / max(len(logs), 1) * 100, 1
        ),
        "by_module": by_module,
    }
