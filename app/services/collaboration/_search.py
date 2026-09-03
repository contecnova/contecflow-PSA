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


# ── Filtros de la búsqueda SQL ───────────────────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 18). `_apply_filters` era complejidad 15: seis
# filtros booleanos en cadena de `if`, cada uno con su clausula. Los seis son
# ahora una tabla, y los que llevan resolucion —`in:` y `from:`— quedan aparte
# porque tienen un respaldo que los otros no.


def _filtros_booleanos():
    """Los filtros de bandera: `has:`, `is:` y el de tipo.

    Se construyen dentro de una funcion y no como constante de modulo porque
    necesitan los modelos, y esos se importan de forma diferida en este fichero.

    `has:mention` y `is:saved` usan subconsultas con `distinct()`: son
    relaciones uno-a-muchos y sin el `distinct` un mensaje con tres menciones
    saldria tres veces.
    """
    from app.models.collaboration import (
        CollaborationMention, CollaborationMessage as M, CollaborationSavedMessage,
    )

    return (
        ("has_attachment", lambda q, db: q.filter(M.has_attachments == True)),   # noqa: E712
        # `has:link` es una heuristica: busca «http» en el cuerpo. No detecta un
        # enlace escrito sin esquema, y eso es aceptable — el alternativa es
        # analizar cada mensaje al guardarlo.
        ("has_link", lambda q, db: q.filter(M.body.ilike("%http%"))),
        ("has_mention", lambda q, db: q.filter(
            M.id.in_(db.query(CollaborationMention.message_id).distinct()))),
        ("is_pinned", lambda q, db: q.filter(M.is_pinned == True)),             # noqa: E712
        ("is_saved", lambda q, db: q.filter(
            M.id.in_(db.query(CollaborationSavedMessage.message_id).distinct()))),
    )


def _acotar_por_conversacion(q, db, parsed, organization_id, conversation_ids):
    """`in:` manda sobre el filtro del panel, y sin respaldo si no resuelve.

    El `elif` es deliberado: si alguien escribe `in:general` y el nombre no
    existe, NO se cae al filtro de conversaciones del panel — la busqueda se
    hace sin acotar. Es discutible, pero es el comportamiento actual.
    """
    from app.models.collaboration import CollaborationMessage as M

    if parsed.in_target:
        cid = _resolve_in_target(db, parsed.in_target, organization_id)
        return q.filter(M.conversation_id == cid) if cid else q
    if conversation_ids:
        return q.filter(M.conversation_id.in_(conversation_ids))
    return q


def _acotar_por_autor(q, db, parsed, organization_id, author_user_id):
    """`from:` manda sobre el autor del panel, con la misma regla que `in:`."""
    from app.models.collaboration import CollaborationMessage as M

    if parsed.from_author:
        uid = _resolve_author(db, parsed.from_author, organization_id)
        return q.filter(M.user_id == uid) if uid else q
    if author_user_id:
        return q.filter(M.user_id == author_user_id)
    return q


def _apply_filters(q, db: Session, *, organization_id: str, parsed, conversation_ids, author_user_id, date_from, date_to):
    from app.models.collaboration import CollaborationMessage as M

    # El filtro de organizacion y el de borrados van SIEMPRE y van primero: son
    # el aislamiento entre clientes y la papelera, no opciones de busqueda.
    q = q.filter(M.organization_id == organization_id, M.status != "deleted")

    q = _acotar_por_conversacion(q, db, parsed, organization_id, conversation_ids)
    q = _acotar_por_autor(q, db, parsed, organization_id, author_user_id)

    # Las fechas escritas en la consulta mandan sobre las del panel.
    if parsed.after or date_from:
        q = q.filter(M.sent_at >= (parsed.after or date_from))
    if parsed.before or date_to:
        q = q.filter(M.sent_at <= (parsed.before or date_to))

    for campo, aplicar in _filtros_booleanos():
        if getattr(parsed, campo, None):
            q = aplicar(q, db)

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

    # ── Búsqueda en OpenSearch ───────────────────────────────────────────────
    #
    # Auditoria 2026-08 (hallazgo 18). Este `search` era complejidad 16: la
    # llamada de respaldo a SQL estaba escrita TRES VECES —sin cliente, con
    # consulta fallida, y la del padre— y los ocho filtros eran una cadena de
    # `if` que construia el mismo tipo de clausula.

    # Tope duro de resultados que se piden al indice, por encima de lo que pida
    # quien llama: una consulta sin limite contra un indice grande devuelve
    # megabytes que nadie va a leer.
    _MAX_RESULTADOS = 200

    def _por_sql(self, db, *, organization_id, query, conversation_ids,
                 author_user_id, date_from, date_to, limit) -> list[dict]:
        """Repliega a la busqueda SQL. Estaba escrito tres veces identico."""
        return self._fallback.search(
            db, organization_id=organization_id, query=query,
            conversation_ids=conversation_ids, author_user_id=author_user_id,
            date_from=date_from, date_to=date_to, limit=limit,
        )

    @staticmethod
    def _filtros(parsed, conversation_ids, author_user_id, date_from, date_to) -> list:
        """Las clausulas de filtro del indice, en el orden del original.

        Los operadores de la consulta (`in:`, `from:`, `has:`, `is:`) ya vienen
        resueltos en `parsed`; aqui solo se traducen a la sintaxis del indice.

        Las fechas del texto de la consulta MANDAN sobre los parametros: si
        alguien escribe `before:2026-01-01` y ademas el panel manda un rango,
        gana lo que ha escrito la persona.
        """
        filtros = []
        if conversation_ids:
            filtros.append({"terms": {"conversation_id": conversation_ids}})
        if author_user_id:
            filtros.append({"term": {"user_id": author_user_id}})
        if parsed.has_attachment:
            filtros.append({"term": {"has_attachments": True}})
        if parsed.is_pinned:
            filtros.append({"term": {"is_pinned": True}})
        if parsed.type_filter:
            filtros.append({"term": {"type": parsed.type_filter}})
        if parsed.before or date_to:
            filtros.append({"range": {"sent_at": {
                "lte": (parsed.before or date_to).isoformat()}}})
        if parsed.after or date_from:
            filtros.append({"range": {"sent_at": {
                "gte": (parsed.after or date_from).isoformat()}}})
        return filtros

    @staticmethod
    def _hit(h: dict) -> dict:
        """Un resultado del indice, con la forma que espera la interfaz."""
        src = h.get("_source", {})
        cuerpo = src.get("body") or ""
        return {
            "kind": "message", "id": h["_id"],
            # El titulo es mas corto que el fragmento a proposito: uno va en la
            # linea de resultado y el otro en la vista previa de debajo.
            "title": cuerpo[:80],
            "snippet": cuerpo[:240],
            "conversation_id": src.get("conversation_id"),
            "sent_at": src.get("sent_at"),
            "score": h.get("_score") or 1.0,
            "extra": {
                "user_id": src.get("user_id"),
                "type": src.get("type"),
                "has_attachments": src.get("has_attachments"),
            },
        }

    def search(self, db: Session, *, organization_id, query, conversation_ids=None, author_user_id=None, date_from=None, date_to=None, limit=50) -> list[dict]:
        respaldo = dict(
            organization_id=organization_id, query=query,
            conversation_ids=conversation_ids, author_user_id=author_user_id,
            date_from=date_from, date_to=date_to, limit=limit,
        )
        if not self.client:
            return self._por_sql(db, **respaldo)

        parsed = parse_query(query or "")
        # Los operadores `in:` y `from:` se resuelven igual que en los motores
        # SQL: el indice guarda identificadores, no nombres.
        if parsed.in_target:
            cid = _resolve_in_target(db, parsed.in_target, organization_id)
            if cid:
                conversation_ids = [cid]
        if parsed.from_author:
            uid = _resolve_author(db, parsed.from_author, organization_id)
            if uid:
                author_user_id = uid

        must = [{"match": {"body": parsed.text}}] if parsed.text else []
        body = {
            "size": min(limit, self._MAX_RESULTADOS),
            "query": {"bool": {
                # Sin texto se buscan TODOS los mensajes que pasen los filtros:
                # `in:general has:attachment` sin palabras es una consulta
                # legitima.
                "must": must or [{"match_all": {}}],
                "filter": self._filtros(
                    parsed, conversation_ids, author_user_id, date_from, date_to
                ),
            }},
            "sort": [{"sent_at": {"order": "desc"}}],
        }

        try:
            res = self.client.search(index=self._index_name(organization_id), body=body)
        except Exception as exc:
            # El indice caido no deja la busqueda sin funcionar: se repliega a
            # SQL, que da peores resultados pero da resultados.
            logger.warning("OpenSearch query failed: %s — fallback to SQL", exc)
            return self._por_sql(db, **respaldo)

        return [self._hit(h) for h in res["hits"]["hits"]]


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
