"""ai_modules.kb — extracted from the former ai_modules_service god-file."""

from __future__ import annotations
import json
import logging

from sqlalchemy.orm import Session

from app.models.ai_chat import (
    AIKBArticle,
)
from app.models.service_desk import Ticket
from sqlalchemy import or_

_log = logging.getLogger(__name__)


from app.services.ai_modules._base import (
    call_ai_unified, compute_kb_embedding, log_action, kb_vector_search,
)

def list_kb(db: Session, published_only: bool = False, category=None):
    q = db.query(AIKBArticle)
    if published_only: q = q.filter(AIKBArticle.is_published == True)
    if category:       q = q.filter(AIKBArticle.category == category)
    articles = q.order_by(AIKBArticle.created_at.desc()).limit(100).all()
    return [{
        "id": a.id, "title": a.title, "category": a.category,
        "tags": json.loads(a.tags or "[]"),
        "view_count": a.view_count, "helpful_votes": a.helpful_votes,
        "is_published": a.is_published, "is_ai_generated": a.is_ai_generated,
        "source_ticket_id": a.source_ticket_id,
        "created_at": str(a.created_at)[:10],
    } for a in articles]

def generate_kb_from_ticket(db: Session, ticket_id: str, current_user) -> dict:
    import re

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise ValueError("not_found")

    title   = f"Cómo resolver: {ticket.title}"
    content = ""
    tags    = []

    try:
        prompt = f"""Crea un artículo de base de conocimiento profesional basado en este ticket de soporte resuelto.

Título del ticket: {ticket.title}
Descripción: {ticket.description or 'Sin descripción'}
Categoría: {ticket.ticket_type or 'General'}
Prioridad: {ticket.priority or 'medium'}

Responde SOLO con JSON:
{{
  "title": "Cómo [resolver/configurar/solucionar] ...",
  "content": "## Síntoma\\n...\\n## Causa\\n...\\n## Solución\\n...\\n## Pasos\\n1. ...\\n## Verificación\\n...",
  "tags": ["tag1", "tag2"],
  "category": "..."
}}"""
        text = call_ai_unified(
            db, [{"role": "user", "content": prompt}],
            module="knowledge_base", user_id=current_user.id, max_tokens=1500
        )
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                _cleaned = re.sub(r",\s*([}\]])", r"\1", match.group())
                data = json.loads(_cleaned)
            title   = data.get("title", title)
            content = data.get("content", "")
            tags    = data.get("tags", [])
    except Exception as e:
        _log.exception("KB article generation failed for title=%s", title)
        content = f"Error generando artículo: {str(e)[:100]}"

    article = AIKBArticle(
        source_ticket_id=ticket_id, title=title, content=content,
        tags=json.dumps(tags), category=ticket.ticket_type or "General",
        is_ai_generated=True, is_published=False,
    )
    db.add(article)
    log_action(db, current_user.id, "knowledge_base", "generate_from_ticket",
               f"ticket={ticket_id}", f"title={title}")
    db.commit(); db.refresh(article)
    compute_kb_embedding(db, article.id, title + " " + (content or ""))
    return {"article_id": article.id, "title": article.title, "is_published": article.is_published}

def search_kb(db: Session, query: str) -> list:

    articles = kb_vector_search(db, query, limit=10)
    if not articles:
        articles = db.query(AIKBArticle).filter(
            AIKBArticle.is_published == True,
            or_(
                AIKBArticle.title.ilike(f"%{query}%"),
                AIKBArticle.content.ilike(f"%{query}%"),
            )
        ).limit(10).all()

    for a in articles:
        a.view_count = (a.view_count or 0) + 1
    db.commit()

    return [{
        "id": a.id, "title": a.title, "category": a.category,
        "content_preview": a.content[:300] if a.content else "",
        "tags": json.loads(a.tags or "[]"),
    } for a in articles]

def rebuild_kb_embeddings(db: Session) -> dict:
    articles = db.query(AIKBArticle).all()
    # Auditoria 2026-11: contaba como «rehecho» aunque fallaran todos.
    rehechos = fallidos = 0
    for a in articles:
        if compute_kb_embedding(db, a.id, (a.title or "") + " " + (a.content or "")):
            rehechos += 1
        else:
            fallidos += 1
    return {"rebuilt": rehechos, "failed": fallidos}

def update_kb(db: Session, article_id: str, payload: dict, current_user) -> dict:
    article = db.query(AIKBArticle).filter(AIKBArticle.id == article_id).first()
    if not article:
        raise ValueError("not_found")
    for field in ["title", "content", "category", "is_published"]:
        if field in payload: setattr(article, field, payload[field])
    if "tags" in payload: article.tags = json.dumps(payload["tags"])
    if payload.get("is_published"): article.reviewed_by = current_user.id
    db.commit()
    if "title" in payload or "content" in payload:
        compute_kb_embedding(db, article.id, article.title + " " + (article.content or ""))
    return {"ok": True}
