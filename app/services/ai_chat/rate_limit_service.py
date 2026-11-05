"""
ai_rate_limit_service — Rate limiting and governance checks for AI modules.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.ai_chat import AIActionLog, AIGovernanceConfig

_logger = logging.getLogger("v16_core")


def check_rate_limit(db: Session, user_id: str, module: str) -> Optional[str]:
    """Return an error string if the user has exceeded today's action limit, else None."""
    try:
        from app.models.user import User
        from app.services.governance_service import config_de_modulo
        usuario = db.get(User, user_id)
        config = config_de_modulo(db, getattr(usuario, "organization_id", None), module)
        if not config:
            return None
        if not config.is_enabled:
            return f"El módulo '{module}' está deshabilitado por el administrador."
        if config.max_actions_per_day:
            today_start = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            count = db.query(func.count(AIActionLog.id)).filter(
                AIActionLog.user_id == user_id,
                AIActionLog.module == module,
                AIActionLog.created_at >= today_start,
            ).scalar() or 0
            if count >= config.max_actions_per_day:
                return (
                    f"Has alcanzado el límite diario de {config.max_actions_per_day} "
                    f"acciones para '{module}'. Vuelve mañana o contacta con el administrador."
                )
    except Exception as exc:
        _logger.warning(f"Rate-limit check failed for module '{module}': {exc}")
    return None
