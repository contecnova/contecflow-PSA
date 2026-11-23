"""Análisis de una reunión: resumen, decisiones, riesgos, preguntas abiertas y acciones.

Reutiliza el map-reduce de `ai_modules._base` (el mismo del asistente de
siempre) sobre el texto `[mm:ss] Hablante: texto`. Antes de analizar:
- con consentimiento exigido y respuestas pendientes, la reunión queda en
  `esperando_consentimiento` y no se manda nada a la IA;
- los segmentos de quien dijo «no» ya están tachados (`servicio.consentir`).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.services.reuniones.eventos import cambiar_estado, evento

logger = logging.getLogger(__name__)

TACHADO = "[sin consentimiento]"

_SISTEMA = ("Eres un asistente experto en analizar reuniones de trabajo. Analiza la transcripción "
            "(cada línea: [marca de tiempo] Hablante: texto) y extrae lo importante.")
_PREFIJO = "Analiza esta transcripción de reunión:"
_SUFIJO = """Con el análisis anterior, genera el informe final.

Responde SOLO con JSON:
{
  "title": "...",
  "summary": "...",
  "decisions": ["..."],
  "risks": ["..."],
  "open_questions": ["..."],
  "actions": [{"description": "...", "assignee_name": "nombre tal como se dijo o null",
               "due_date": "AAAA-MM-DD si se puede deducir, si no null",
               "due_date_text": "la fecha tal como se dijo o null"}]
}"""


def _json_del_modelo(texto: str) -> Optional[dict]:
    from app.services.ai_modules.meetings import _json_del_modelo as leer
    return leer(texto)


def _fecha(valor) -> Optional[datetime]:
    if not valor or not isinstance(valor, str):
        return None
    try:
        return datetime.fromisoformat(valor.strip()[:10])
    except ValueError:
        return None


def _responsable(db: Session, reunion, nombre: Optional[str], actor):
    """Primero un participante con usuario cuyo nombre casa; si no, por nombre en la empresa."""
    if not nombre:
        return None
    bajo = nombre.strip().lower()
    for p in reunion.participantes:
        if p.user_id and p.name and (bajo in p.name.lower() or p.name.lower() in bajo):
            return p.user_id
    from app.models.user import User
    from app.db.session import _miembros_de
    q = db.query(User).filter(User.full_name.ilike(f"%{nombre.strip()}%"), User.is_active.is_(True))
    if reunion.organization_id:
        q = q.filter(_miembros_de(User, reunion.organization_id))
    usuario = q.first()
    return usuario.id if usuario else None


def detectar_idioma(texto: str) -> Optional[str]:
    try:
        from app.services.traduccion.idiomas import detectar_si_seguro
        return detectar_si_seguro(texto[:4000], 0.5)
    except Exception:  # noqa: BLE001 - sin detector, sin idioma
        logger.debug("detectar_idioma: excepcion ignorada", exc_info=True)
        return None


def texto_para_analizar(reunion) -> str:
    from app.services.reuniones.transcripcion import a_texto
    segmentos = [s for s in reunion.segmentos if (s.text or "").strip() and s.text != TACHADO]
    if segmentos:
        return a_texto(segmentos)
    return reunion.transcript or ""


def analizar(db: Session, reunion, actor=None) -> None:
    """Analiza y guarda. Deja el estado en `lista`, `esperando_consentimiento` o `error`. No confirma."""
    from app.models.ai_chat import AIMeetingAction
    from app.services.ai_modules._base import log_action, map_reduce_analysis
    from app.services.reuniones.consultas import consentimiento_completo
    from app.services.reuniones import config as cfg_mod

    if reunion.consent_required and not consentimiento_completo(reunion):
        cambiar_estado(db, reunion, "esperando_consentimiento", actor)
        return
    texto = texto_para_analizar(reunion)
    if not texto.strip():
        cambiar_estado(db, reunion, "error", actor, error_code="reuniones_sin_transcripcion")
        return
    cambiar_estado(db, reunion, "procesando", actor)
    if not reunion.original_language:
        reunion.original_language = detectar_idioma(texto)
    if not reunion.transcript:
        reunion.transcript = texto[:50000]

    from app.services.formato_regional import instruccion_de_idioma_para
    sistema = _SISTEMA + " " + instruccion_de_idioma_para(
        db, user_id=getattr(actor, "id", None) or reunion.created_by, org_id=reunion.organization_id)
    t0 = time.time()
    try:
        crudo = map_reduce_analysis(texto, map_system=sistema, map_user_prefix=_PREFIJO,
                                    reduce_system=sistema, reduce_user_suffix=_SUFIJO, db=db,
                                    module="meeting_assistant",
                                    user_id=getattr(actor, "id", None) or reunion.created_by,
                                    map_tokens=1500, reduce_tokens=2500)
        datos = _json_del_modelo(crudo) or {}
    except Exception as exc:  # noqa: BLE001 - la IA caída deja la reunión en error, no tumba la petición
        logger.warning("reuniones: análisis fallido de %s: %s", reunion.id, exc)
        cambiar_estado(db, reunion, "error", actor, error_code="ia_no_disponible")
        return

    if datos.get("title") and (not reunion.title or reunion.title.startswith("Reunión ")):
        reunion.title = str(datos["title"])[:255]
    reunion.summary = datos.get("summary") or reunion.summary
    reunion.decisions = json.dumps(list(datos.get("decisions") or []), ensure_ascii=False)
    reunion.risks_mentioned = json.dumps(list(datos.get("risks") or []), ensure_ascii=False)
    reunion.open_questions = json.dumps(list(datos.get("open_questions") or []), ensure_ascii=False)
    # Reprocesar: se rehacen las acciones que aún no se convirtieron en nada.
    for a in list(reunion.actions):
        if not a.is_created and not a.ticket_id:
            reunion.actions.remove(a)
    for a in datos.get("actions") or []:
        if not isinstance(a, dict) or not (a.get("description") or "").strip():
            continue
        reunion.actions.append(AIMeetingAction(
            organization_id=reunion.organization_id, description=str(a["description"])[:4000],
            assignee_name=(a.get("assignee_name") or None),
            assignee_id=_responsable(db, reunion, a.get("assignee_name"), actor),
            due_date=_fecha(a.get("due_date")), due_date_text=(a.get("due_date_text") or None)))
    # Las traducciones guardadas ya no valen.
    for t in list(reunion.traducciones):
        reunion.traducciones.remove(t)

    if cfg_mod.leer(db, reunion.organization_id)["linking"]["auto"]:
        from app.services.reuniones.vinculacion import vincular
        vincular(db, reunion)

    cambiar_estado(db, reunion, "lista", actor)
    evento(db, reunion, "analyzed", actor, {"actions": len(reunion.actions)})
    log_action(db, getattr(actor, "id", None) or reunion.created_by, "meeting_assistant", "analyze",
               f"meeting={reunion.id} chars={len(texto)}", (reunion.summary or "")[:300],
               latency=int((time.time() - t0) * 1000))
