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


def _idioma(db: Session, usuario) -> str:
    from app.services.formato_regional import idioma_de_salida
    return idioma_de_salida(db, user_id=getattr(usuario, "id", None),
                            org_id=getattr(usuario, "organization_id", None))


#: Causa del corte -> código de error traducible (`app/core/codigos_de_error.py`,
#: `err_srv.*` en es/en/zh). 19-11-2026: antes un 429 genérico `ia_uso_no_permitido`
#: para todo. El tope de gasto de la empresa va aparte (`PresupuestoDeIAAgotado`,
#: `ia_presupuesto_diario_agotado`).
CODIGO_MODULO_DESACTIVADO = "ia_modulo_desactivado"
CODIGO_LIMITE_DIARIO = "ia_limite_diario"


def limite_de_uso(db: Session, user_id: str, module: str) -> Optional[tuple[str, dict, str]]:
    """`(codigo, params, texto)` si el usuario no puede usar `module` ahora, o None.

    - `ia_modulo_desactivado` (`modulo`): el módulo está apagado en Gobierno de IA;
    - `ia_limite_diario` (`n`, `modulo`): ha llegado a su tope diario de acciones.

    El texto sale en el idioma del usuario (`ia.modulo_deshabilitado`,
    `ia.limite_diario` de `textos_de_salida`), para quien no traduce el código
    (MCP, registros). Un fallo al comprobarlo no corta (como antes).
    """
    from app.services.textos_de_salida import texto
    try:
        from app.models.user import User
        from app.services.governance_service import config_de_modulo
        usuario = db.get(User, user_id)
        config = config_de_modulo(db, getattr(usuario, "organization_id", None), module)
        if not config:
            return None
        if not config.is_enabled:
            return (CODIGO_MODULO_DESACTIVADO, {"modulo": module},
                    texto("ia.modulo_deshabilitado", _idioma(db, usuario), modulo=module))
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
                datos = {"n": config.max_actions_per_day, "modulo": module}
                return (CODIGO_LIMITE_DIARIO, datos,
                        texto("ia.limite_diario", _idioma(db, usuario), **datos))
    except Exception as exc:
        _logger.warning(f"Rate-limit check failed for module '{module}': {exc}")
    return None


def check_rate_limit(db: Session, user_id: str, module: str) -> Optional[str]:
    """Return an error string if the user has exceeded today's action limit, else None.

    19-11-2026: el texto sale en el idioma del usuario; el código de la causa,
    en `limite_de_uso`.
    """
    limite = limite_de_uso(db, user_id, module)
    return limite[2] if limite else None
