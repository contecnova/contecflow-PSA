from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Response
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.core.security import decode_token
from app.models.service_desk import KBArticle, KBStatus, Ticket
from app.models.user import User
from app.services.pagination_service import paginate_query
from app.services.service_desk.scoping import scope_kb_query
from app.services.sla_service import next_kb_number as _next_kb_number


def list_kb_articles_scoped(
    db: Session,
    search: Optional[str],
    category_id: Optional[str],
    public_only: bool,
    page: int,
    page_size: int,
    response: Optional[Response],
    authorization: Optional[str],
):
    q = db.query(KBArticle).options(joinedload(KBArticle.author)).filter(KBArticle.status == KBStatus.published)
    if public_only:
        q = q.filter(KBArticle.is_public == True)
    if category_id:
        q = q.filter(KBArticle.category_id == category_id)
    if search:
        q = q.filter(or_(
            KBArticle.title.ilike(f"%{search}%"),
            KBArticle.body.ilike(f"%{search}%"),
            KBArticle.tags.ilike(f"%{search}%"),
        ))

    if not public_only and authorization and authorization.startswith("Bearer "):
        bearer = authorization.removeprefix("Bearer ").strip()
        payload = decode_token(bearer)
        if payload and payload.get("type") == "access":
            uid = payload.get("sub")
            user = db.query(User).filter(User.id == uid, User.is_active == True).first()
            if user:
                q = scope_kb_query(q, db, user)

    articles, _, _ = paginate_query(
        q.order_by(KBArticle.helpful_count.desc(), KBArticle.created_at.desc()),
        page,
        page_size,
        response,
    )
    return articles


def serialize_kb_articles(articles: list[KBArticle], public_only: bool) -> list[dict]:
    return [{
        "id": a.id,
        "number": a.number,
        "title": a.title,
        "summary": a.summary,
        "body": a.body if not public_only else None,
        "tags": a.tags,
        "is_public": a.is_public,
        "view_count": a.view_count,
        "helpful_count": a.helpful_count,
        "author_name": a.author.full_name if a.author else None,
        "published_at": str(a.published_at)[:10] if a.published_at else None,
    } for a in articles]


def get_kb_article_and_increment_view(db: Session, article_id: str) -> KBArticle:
    article = db.query(KBArticle).filter(KBArticle.id == article_id).first()
    if not article:
        raise HTTPException(404)
    article.view_count = (article.view_count or 0) + 1
    return article


def serialize_kb_article_detail(article: KBArticle) -> dict:
    return {
        "id": article.id,
        "number": article.number,
        "title": article.title,
        "body": article.body,
        "summary": article.summary,
        "tags": article.tags,
        "view_count": article.view_count,
        "helpful_count": article.helpful_count,
    }


def build_kb_article(db: Session, payload, author_id: str) -> KBArticle:
    article = KBArticle(number=_next_kb_number(db), author_id=author_id, **payload.model_dump())
    if payload.status == "published":
        article.published_at = datetime.now(timezone.utc)
    return article


def get_scoped_kb_article_or_404(db: Session, current_user: User, article_id: str) -> KBArticle:
    article = scope_kb_query(db.query(KBArticle), db, current_user).filter(KBArticle.id == article_id).first()
    if not article:
        raise HTTPException(404)
    return article


def apply_kb_article_update(article: KBArticle, payload) -> None:
    for key, value in payload.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(article, key, value)
    if payload.status == "published" and not article.published_at:
        article.published_at = datetime.now(timezone.utc)


def update_kb_helpful_vote(db: Session, article_id: str, helpful: bool) -> None:
    article = db.query(KBArticle).filter(KBArticle.id == article_id).first()
    if not article:
        raise HTTPException(404)
    if helpful:
        article.helpful_count = (article.helpful_count or 0) + 1
    else:
        article.not_helpful_count = (article.not_helpful_count or 0) + 1


def create_kb_from_ticket(db: Session, ticket_id: str, title: str, author_id: str) -> KBArticle:
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(404)
    if not ticket.resolution:
        raise HTTPException(400, "El ticket no tiene resolución")

    article = KBArticle(
        number=_next_kb_number(db),
        title=title,
        body=f"**Síntoma**\n{ticket.description}\n\n**Solución**\n{ticket.resolution}",
        summary=ticket.title[:200],
        author_id=author_id,
        created_from_ticket_id=ticket_id,
        status=KBStatus.draft,
    )
    db.add(article)
    db.flush()
    ticket.kb_article_id = article.id
    return article
