"""Interruptor y tope diario de cada módulo de IA (Gobierno de IA → Módulos).

Revisión 2026-11. Sólo NexusAssist y NexusAgent comprobaban su interruptor: los
otros siete (Oracle, reuniones, contratos, base de conocimiento, portal, voz)
seguían funcionando apagados. Además los registros se guardaban con otro nombre
(`contecflowassist`…) y el tope diario y el uso por módulo no casaban nunca.

Uso en una ruta: `dependencies=[Depends(exigir_modulo_ia("voice"))]`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db


def comprobar_modulo(db: Session, organization_id: Optional[str], modulo: str, user_id: Optional[str] = None) -> None:
    """403 si el módulo está apagado para la empresa; 429 si el usuario pasó su tope diario."""
    from app.models.ai_chat import AIActionLog
    from app.services.governance_service import config_de_modulo
    config = config_de_modulo(db, organization_id, modulo)
    if config is None:
        from app.api.v1.endpoints.governance import APAGADOS_SIN_CONFIGURAR
        if modulo in APAGADOS_SIN_CONFIGURAR:
            raise HTTPException(403, f"El módulo de IA «{modulo}» no está activado en Gobierno de IA")
        return
    if not config.is_enabled:
        raise HTTPException(403, f"El módulo de IA «{modulo}» está desactivado en Gobierno de IA")
    if config.max_actions_per_day and user_id:
        desde = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        hechas = db.query(func.count(AIActionLog.id)).filter(
            AIActionLog.user_id == user_id, AIActionLog.module == modulo, AIActionLog.created_at >= desde,
        ).scalar() or 0
        if hechas >= config.max_actions_per_day:
            raise HTTPException(429, f"Has llegado al límite diario de {config.max_actions_per_day} acciones de «{modulo}»")


def exigir_modulo_ia(modulo: str):
    def _dependencia(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
        comprobar_modulo(db, getattr(current_user, "organization_id", None), modulo, current_user.id)
        return current_user
    return _dependencia
