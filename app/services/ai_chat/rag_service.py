"""
ai_rag_service — Knowledge base RAG (Retrieval-Augmented Generation).
Vector similarity search + keyword fallback for ContecflowAssist context.
"""
import json
import logging
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.ai_chat import AIKBArticle

_logger = logging.getLogger("v16_core")


def _to_embedding_list(raw_embedding) -> list:
    """Normalize embedding output from different backends to a plain list[float]."""
    if raw_embedding is None:
        return []
    if hasattr(raw_embedding, "tolist"):
        return raw_embedding.tolist()
    if isinstance(raw_embedding, list):
        return raw_embedding
    try:
        return list(raw_embedding)
    except Exception:
        return []


def kb_rag_context(db: Session, message: str) -> str:
    """
    RAG lookup in the KB for ContecflowAssist.
    Tries vector similarity first; falls back to keyword LIKE search.
    Returns a formatted string to append to the system prompt, or "".
    """
    try:
        from app.services.semantic_classifier import _get_model, _cosine
        model, _ = _get_model()
        if hasattr(model, "encode"):
            encoded = model.encode([message], show_progress_bar=False)
        else:
            encoded = model.encode([message])
        q_emb = _to_embedding_list(encoded[0] if encoded else None)
        if not q_emb:
            return ""

        candidates = db.query(AIKBArticle).filter(
            AIKBArticle.is_published == True,
            AIKBArticle.embedding.isnot(None),
        ).all()

        if candidates:
            scored = sorted(
                [(float(_cosine(q_emb, json.loads(a.embedding))), a) for a in candidates
                 if a.embedding],
                key=lambda x: x[0], reverse=True,
            )
            top = [a for _, a in scored[:3] if _ > 0.25]
            if top:
                return "\n\nARTÍCULOS RELEVANTES DE LA BASE DE CONOCIMIENTO:\n" + "\n".join(
                    f"- [{a.title}]: {(a.content or '')[:350]}" for a in top
                )

        keywords = [w for w in message.split() if len(w) > 3][:5]
        if keywords:
            kb_q = db.query(AIKBArticle).filter(
                AIKBArticle.is_published == True,
                or_(
                    *[AIKBArticle.title.ilike(f"%{w}%") for w in keywords],
                    *[AIKBArticle.content.ilike(f"%{w}%") for w in keywords[:3]],
                )
            ).limit(3).all()
            if kb_q:
                return "\n\nARTÍCULOS RELEVANTES DE LA BASE DE CONOCIMIENTO:\n" + "\n".join(
                    f"- [{a.title}]: {(a.content or '')[:350]}" for a in kb_q
                )
    except Exception as kb_err:
        _logger.warning(f"KB RAG lookup failed: {kb_err}")
    return ""
