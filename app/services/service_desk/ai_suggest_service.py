import logging
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.service_desk import KBArticle, KBStatus, Ticket
from app.models.service_desk import CannedResponse
from app.models.user import User


def _get_ticket_or_404(db: Session, ticket_id: str) -> Ticket:
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Ticket no encontrado")
    return ticket


def _compute_kb_matches(db: Session, query_text: str):
    kb_matches = []
    try:
        from app.services.semantic_classifier import _get_model, _cosine

        model, _ = _get_model()
        q_emb = model.encode([query_text], show_progress_bar=False)[0]
        if hasattr(q_emb, "tolist"):
            q_emb = q_emb.tolist()

        arts = db.query(KBArticle).filter(KBArticle.status == KBStatus.published).all()
        scored = []
        for article in arts:
            text = f"{article.title or ''}\n{article.summary or ''}\n{article.body or ''}".strip()
            if not text:
                continue
            a_emb = model.encode([text], show_progress_bar=False)[0]
            if hasattr(a_emb, "tolist"):
                a_emb = a_emb.tolist()
            sim = _cosine(q_emb, a_emb)
            scored.append((sim, article))
        scored.sort(key=lambda x: x[0], reverse=True)
        kb_matches = [
            {
                "id": a.id,
                "number": a.number,
                "title": a.title,
                "summary": a.summary,
                "score": round(float(s), 4),
            }
            for s, a in scored[:5]
            if s > 0
        ]
    except Exception:
        like = db.query(KBArticle).filter(
            KBArticle.status == KBStatus.published,
            or_(
                KBArticle.title.ilike(f"%{query_text[:80]}%"),
                KBArticle.body.ilike(f"%{query_text[:80]}%"),
            ),
        ).limit(5).all()
        kb_matches = [
            {
                "id": a.id,
                "number": a.number,
                "title": a.title,
                "summary": a.summary,
                "score": None,
            }
            for a in like
        ]
    return kb_matches


def _compute_canned_matches(db: Session, query_text: str):
    canned = db.query(CannedResponse).filter(CannedResponse.is_active == True).all()
    q_words = {w for w in query_text.lower().split() if len(w) >= 4}
    canned_scored = []
    for c in canned:
        text = f"{c.title or ''} {c.body or ''} {c.shortcut or ''}".lower()
        overlap = sum(1 for w in q_words if w in text)
        if overlap > 0:
            canned_scored.append((overlap, c))
    canned_scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {
            "id": c.id,
            "title": c.title,
            "body": c.body,
            "shortcut": c.shortcut,
            "score": s,
        }
        for s, c in canned_scored[:5]
    ]


def build_ai_ticket_suggestion(db: Session, ticket_id: str, payload: Optional[dict], current_user: User) -> dict:
    ticket = _get_ticket_or_404(db, ticket_id)

    req = payload or {}
    user_content = (req.get("content") or "").strip()
    query_text = user_content or f"{ticket.title}\n{ticket.description}"

    kb_matches = _compute_kb_matches(db, query_text)
    canned_matches = _compute_canned_matches(db, query_text)

    kb_context = "\n\n".join(
        [f"[{k['number']}] {k['title']}\n{k.get('summary') or ''}" for k in kb_matches]
    ) or "(sin artículos KB relevantes)"
    canned_context = "\n\n".join(
        [f"[{c['title']}] {c['body']}" for c in canned_matches]
    ) or "(sin respuestas rápidas relevantes)"

    system = (
        "Eres un agente senior de Service Desk ITIL. "
        "Redacta una respuesta al cliente en español, profesional, breve y accionable. "
        "No inventes hechos. Si faltan datos, pide información concreta."
    )
    messages = [
        {
            "role": "user",
            "content": (
                f"Ticket: {ticket.number}\\n"
                f"Título: {ticket.title}\\n"
                f"Descripción: {ticket.description}\\n\\n"
                f"Contenido adicional del agente: {user_content or '(ninguno)'}\\n\\n"
                f"Artículos KB similares:\\n{kb_context}\\n\\n"
                f"Canned responses sugeridas:\\n{canned_context}\\n\\n"
                "Devuélveme SOLO un borrador de respuesta listo para enviar al cliente."
            ),
        }
    ]

    try:
        from app.api.v1.endpoints.ai_providers import call_ai

        draft = call_ai(
            db,
            messages=messages,
            system=system,
            module="service_desk",
            user_id=current_user.id,
            max_tokens=500,
        )
    except Exception as exc:
        log = logging.getLogger(__name__)
        log.warning("AI suggest fallback for ticket %s: %s", ticket_id, exc)
        kb_hint = kb_matches[0]["title"] if kb_matches else "la base de conocimiento"
        draft = (
            "Gracias por contactar con soporte. Estamos revisando tu incidencia y ya hemos iniciado diagnóstico. "
            f"Como primer paso, vamos a contrastarlo con {kb_hint}. "
            "¿Podrías confirmarnos los pasos exactos para reproducirlo y, si es posible, adjuntar captura del error y hora aproximada?"
        )

    return {
        "ticket_id": ticket.id,
        "ticket_number": ticket.number,
        "draft": draft,
        "kb_matches": kb_matches,
        "canned_matches": canned_matches,
    }
