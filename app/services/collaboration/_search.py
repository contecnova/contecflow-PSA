"""
Message search abstraction.

Backends:
  SimpleSqlSearch   — LIKE multi-término (SQLite-friendly)
  PgFtsSearch       — Postgres tsvector + GIN index
  OpenSearchSearch  — cluster OpenSearch (requiere paquete opensearch-py)

El backend se elige por COLLAB_SEARCH_BACKEND (auto|simple|pg|opensearch).

Soporta operadores avanzados (`from:`, `in:`, `before:`, `after:`, `has:`,
`is:`, `type:`) parseados en _search_query.parse().
"""
from __future__ import annotations

import logging
import os
from typing import Optional, Protocol

from sqlalchemy.orm import Session

from app.services.collaboration._search_query import parse as parse_query

logger = logging.getLogger(__name__)


class MessageSearch(Protocol):
    def index(self, db: Session, message_id: str) -> None: ...
    def remove(self, db: Session, message_id: str) -> None: ...
    def search(
        self, db: Session, *,
        organization_id: str,
        query: str,
        conversation_ids: Optional[list[str]] = None,
        author_user_id: Optional[str] = None,
        date_from=None,
        date_to=None,
        limit: int = 50,
    ) -> list[dict]: ...


def _resolve_in_target(db: Session, value: str, organization_id: str) -> Optional[str]:
    """Resuelve `in:<value>` a conversation_id (acepta uuid de conversación,
    slug de canal o nombre del canal)."""
    if not value:
        return None
    from app.models.collaboration import (
        CollaborationChannel, CollaborationConversation,
    )
    # ¿uuid de conversación?
    conv = db.query(CollaborationConversation).filter(CollaborationConversation.id == value).first()
    if conv:
        return conv.id
    val = value.lstrip("#")
    ch = db.query(CollaborationChannel).filter(
        CollaborationChannel.organization_id == organization_id,
    ).filter(
        (CollaborationChannel.slug == val) | (CollaborationChannel.name == value)
    ).first()
    return ch.conversation_id if ch else None


def _resolve_author(db: Session, value: str, organization_id: str) -> Optional[str]:
    """Resuelve `from:<value>` a user_id (acepta uuid, email, username)."""
    if not value:
        return None
    from app.models.user import User
    val = value.lstrip("@")
    u = db.query(User).filter(
        User.organization_id == organization_id,
    ).filter(
        (User.id == val) | (User.email == val) | (User.username == val)
    ).first()
    return u.id if u else None


def _apply_filters(q, db: Session, *, organization_id: str, parsed, conversation_ids, author_user_id, date_from, date_to):
    from app.models.collaboration import (
        CollaborationAttachment, CollaborationMention, CollaborationMessage as M,
        CollaborationPinnedMessage, CollaborationSavedMessage,
    )

    q = q.filter(M.organization_id == organization_id, M.status != "deleted")

    # Operator-driven filters
    if parsed.in_target:
        cid = _resolve_in_target(db, parsed.in_target, organization_id)
        if cid:
            q = q.filter(M.conversation_id == cid)
    elif conversation_ids:
        q = q.filter(M.conversation_id.in_(conversation_ids))

    if parsed.from_author:
        uid = _resolve_author(db, parsed.from_author, organization_id)
        if uid:
            q = q.filter(M.user_id == uid)
    elif author_user_id:
        q = q.filter(M.user_id == author_user_id)

    if parsed.after or date_from:
        q = q.filter(M.sent_at >= (parsed.after or date_from))
    if parsed.before or date_to:
        q = q.filter(M.sent_at <= (parsed.before or date_to))

    if parsed.has_attachment:
        q = q.filter(M.has_attachments == True)  # noqa: E712
    if parsed.has_link:
        q = q.filter(M.body.ilike("%http%"))
    if parsed.has_mention:
        q = q.filter(M.id.in_(db.query(CollaborationMention.message_id).distinct()))
    if parsed.is_pinned:
        q = q.filter(M.is_pinned == True)  # noqa: E712
    if parsed.is_saved:
        q = q.filter(M.id.in_(db.query(CollaborationSavedMessage.message_id).distinct()))
    if parsed.type_filter:
        q = q.filter(M.type == parsed.type_filter)
    return q


class SimpleSqlSearch:
    """LIKE-based search; works on SQLite + Postgres without extensions."""

    def index(self, db: Session, message_id: str) -> None: return None
    def remove(self, db: Session, message_id: str) -> None: return None

    def search(self, db: Session, *, organization_id, query, conversation_ids=None, author_user_id=None, date_from=None, date_to=None, limit=50) -> list[dict]:
        from app.models.collaboration import CollaborationMessage as M
        parsed = parse_query(query or "")
        q = db.query(M)
        q = _apply_filters(
            q, db, organization_id=organization_id, parsed=parsed,
            conversation_ids=conversation_ids, author_user_id=author_user_id,
            date_from=date_from, date_to=date_to,
        )
        if parsed.text:
            for term in parsed.text.split()[:5]:
                q = q.filter(M.body.ilike(f"%{term}%"))
        rows = q.order_by(M.sent_at.desc()).limit(limit).all()
        return [_serialize_hit(m, score=1.0) for m in rows]


class PgFtsSearch(SimpleSqlSearch):
    """Postgres tsvector + plainto_tsquery; cae a LIKE si la extensión falla."""

    def search(self, db: Session, *, organization_id, query, conversation_ids=None, author_user_id=None, date_from=None, date_to=None, limit=50) -> list[dict]:
        try:
            from sqlalchemy import text
            from app.models.collaboration import CollaborationMessage as M
            parsed = parse_query(query or "")
            q = db.query(M)
            q = _apply_filters(
                q, db, organization_id=organization_id, parsed=parsed,
                conversation_ids=conversation_ids, author_user_id=author_user_id,
                date_from=date_from, date_to=date_to,
            )
            if parsed.text:
                q = q.filter(text("to_tsvector('simple', coalesce(body, '')) @@ plainto_tsquery('simple', :q)").bindparams(q=parsed.text))
            rows = q.order_by(M.sent_at.desc()).limit(limit).all()
            return [_serialize_hit(m, score=1.0) for m in rows]
        except Exception as exc:
            logger.warning("Pg FTS unavailable, falling back to LIKE: %s", exc)
            return super().search(
                db, organization_id=organization_id, query=query,
                conversation_ids=conversation_ids, author_user_id=author_user_id,
                date_from=date_from, date_to=date_to, limit=limit,
            )


def _serialize_hit(m, *, score: float = 1.0) -> dict:
    return {
        "kind": "message",
        "id": m.id,
        "title": (m.body or "")[:80],
        "snippet": (m.body or "")[:240],
        "conversation_id": m.conversation_id,
        "sent_at": m.sent_at,
        "score": score,
        "extra": {"user_id": m.user_id, "type": m.type, "has_attachments": m.has_attachments},
    }


# ── OpenSearch backend ───────────────────────────────────────────────────────
class OpenSearchSearch:
    """Indexa en OpenSearch + busca con BM25 + filtros estructurados.

    Index: collaboration-messages-{organization_id}
    Doc:   {id, organization_id, conversation_id, user_id, body, sent_at,
            has_attachments, type, is_pinned, mentions, attachments_names}
    """
    INDEX_PREFIX = "collaboration-messages"

    def __init__(self):
        try:
            from opensearchpy import OpenSearch
            # env-driven: OpenSearch is an optional pluggable backend; config kept out
            # of Settings to avoid coupling core config to an optional dependency.
            url = os.environ.get("OPENSEARCH_URL", "http://localhost:9200")
            user = os.environ.get("OPENSEARCH_USER")
            pwd = os.environ.get("OPENSEARCH_PASSWORD")
            kwargs = {"hosts": [url], "timeout": 5}
            if user:
                kwargs["http_auth"] = (user, pwd)
            self.client = OpenSearch(**kwargs)
            self._fallback = SimpleSqlSearch()
        except Exception as exc:
            logger.warning("OpenSearch client init failed: %s — falling back", exc)
            self.client = None
            self._fallback = SimpleSqlSearch()

    def _index_name(self, organization_id: str) -> str:
        return f"{self.INDEX_PREFIX}-{organization_id}".replace(":", "-")

    def _ensure_index(self, organization_id: str):
        if not self.client:
            return
        name = self._index_name(organization_id)
        try:
            if not self.client.indices.exists(index=name):
                self.client.indices.create(index=name, body={
                    "mappings": {
                        "properties": {
                            "organization_id": {"type": "keyword"},
                            "conversation_id": {"type": "keyword"},
                            "user_id":         {"type": "keyword"},
                            "type":            {"type": "keyword"},
                            "is_pinned":       {"type": "boolean"},
                            "has_attachments": {"type": "boolean"},
                            "body":            {"type": "text"},
                            "sent_at":         {"type": "date"},
                            "attachments":     {"type": "text"},
                        }
                    }
                })
        except Exception as exc:
            logger.warning("ensure_index failed: %s", exc)

    def index(self, db: Session, message_id: str):
        if not self.client:
            return
        from app.models.collaboration import CollaborationAttachment, CollaborationMessage as M
        m = db.query(M).filter(M.id == message_id).first()
        if not m:
            return
        self._ensure_index(m.organization_id)
        att_names = [
            a.name for a in db.query(CollaborationAttachment).filter(CollaborationAttachment.message_id == message_id).all()
        ]
        try:
            self.client.index(
                index=self._index_name(m.organization_id),
                id=m.id,
                body={
                    "organization_id": m.organization_id,
                    "conversation_id": m.conversation_id,
                    "user_id":         m.user_id,
                    "type":            m.type,
                    "is_pinned":       m.is_pinned,
                    "has_attachments": m.has_attachments,
                    "body":            m.body or "",
                    "sent_at":         m.sent_at.isoformat() if m.sent_at else None,
                    "attachments":     " ".join(att_names),
                },
                refresh=False,
            )
        except Exception as exc:
            logger.warning("OpenSearch index failed: %s", exc)

    def remove(self, db: Session, message_id: str):
        if not self.client:
            return
        from app.models.collaboration import CollaborationMessage as M
        m = db.query(M).filter(M.id == message_id).first()
        if not m:
            return
        try:
            self.client.delete(index=self._index_name(m.organization_id), id=message_id, ignore=[404])
        except Exception as exc:
            logger.warning("OpenSearch remove failed: %s", exc)

    def search(self, db: Session, *, organization_id, query, conversation_ids=None, author_user_id=None, date_from=None, date_to=None, limit=50) -> list[dict]:
        if not self.client:
            return self._fallback.search(
                db, organization_id=organization_id, query=query,
                conversation_ids=conversation_ids, author_user_id=author_user_id,
                date_from=date_from, date_to=date_to, limit=limit,
            )
        parsed = parse_query(query or "")
        # Resolve in:/from: just like SQL backends
        if parsed.in_target:
            cid = _resolve_in_target(db, parsed.in_target, organization_id)
            if cid:
                conversation_ids = [cid]
        if parsed.from_author:
            uid = _resolve_author(db, parsed.from_author, organization_id)
            if uid:
                author_user_id = uid

        must = []
        if parsed.text:
            must.append({"match": {"body": parsed.text}})
        filters = []
        if conversation_ids:
            filters.append({"terms": {"conversation_id": conversation_ids}})
        if author_user_id:
            filters.append({"term": {"user_id": author_user_id}})
        if parsed.has_attachment:
            filters.append({"term": {"has_attachments": True}})
        if parsed.is_pinned:
            filters.append({"term": {"is_pinned": True}})
        if parsed.type_filter:
            filters.append({"term": {"type": parsed.type_filter}})
        if parsed.before or date_to:
            filters.append({"range": {"sent_at": {"lte": (parsed.before or date_to).isoformat()}}})
        if parsed.after or date_from:
            filters.append({"range": {"sent_at": {"gte": (parsed.after or date_from).isoformat()}}})

        body = {
            "size": min(limit, 200),
            "query": {"bool": {"must": must or [{"match_all": {}}], "filter": filters}},
            "sort": [{"sent_at": {"order": "desc"}}],
        }
        try:
            res = self.client.search(index=self._index_name(organization_id), body=body)
        except Exception as exc:
            logger.warning("OpenSearch query failed: %s — fallback to SQL", exc)
            return self._fallback.search(
                db, organization_id=organization_id, query=query,
                conversation_ids=conversation_ids, author_user_id=author_user_id,
                date_from=date_from, date_to=date_to, limit=limit,
            )
        hits = []
        for h in res["hits"]["hits"]:
            src = h.get("_source", {})
            hits.append({
                "kind": "message", "id": h["_id"],
                "title": (src.get("body") or "")[:80],
                "snippet": (src.get("body") or "")[:240],
                "conversation_id": src.get("conversation_id"),
                "sent_at": src.get("sent_at"),
                "score": h.get("_score") or 1.0,
                "extra": {"user_id": src.get("user_id"), "type": src.get("type"), "has_attachments": src.get("has_attachments")},
            })
        return hits


def _build_search() -> MessageSearch:
    backend = os.environ.get("COLLAB_SEARCH_BACKEND", "auto").lower()
    if backend == "pg":
        return PgFtsSearch()
    if backend == "opensearch":
        return OpenSearchSearch()
    if backend == "simple":
        return SimpleSqlSearch()
    db_url = os.environ.get("DATABASE_URL", "")
    if db_url.startswith("postgres"):
        return PgFtsSearch()
    return SimpleSqlSearch()


search_engine: MessageSearch = _build_search()
