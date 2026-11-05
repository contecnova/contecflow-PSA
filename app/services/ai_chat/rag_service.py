"""
ai_rag_service — Knowledge base RAG (Retrieval-Augmented Generation).
Vector similarity search + keyword fallback for ContecflowAssist context.
"""
import logging
from sqlalchemy.orm import Session

_logger = logging.getLogger("v16_core")


def kb_rag_context(db: Session, message: str) -> str:
    """Contexto de la base de conocimiento para el prompt.

    Revisión 2026-11: buscaba en `ai_kb_articles`, que está vacía (medido: 0
    filas) mientras la base del Service Desk tiene los artículos de verdad.
    Ahora es la misma búsqueda que usa todo lo demás (`kb_calidad.contexto`).
    """
    try:
        from app.services.service_desk.kb_calidad import contexto
        return contexto(db, message, solo_publico=False)["prompt"]
    except Exception as kb_err:
        _logger.warning(f"KB RAG lookup failed: {kb_err}")
    return ""
