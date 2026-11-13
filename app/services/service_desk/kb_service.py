from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.core.security import decode_token
from app.models.service_desk import KBArticle, KBArticleVersion, KBStatus, Ticket
from app.models.user import User
from app.services.pagination_service import ConCabeceras, paginate_query
from app.services.service_desk.scoping import scope_kb_query
from app.services.sla_service import next_kb_number as _next_kb_number
import logging
from app.core.errores import ErrorDeDominio

logger = logging.getLogger(__name__)


def list_kb_articles_scoped(
    db: Session,
    search: Optional[str],
    category_id: Optional[str],
    public_only: bool,
    page: int,
    page_size: int,
    response: Optional[ConCabeceras],
    authorization: Optional[str],
    status: Optional[str] = None,
):
    """Articulos para el portal (publicados y publicos) o para los agentes.

    Auditoria 2026-11: tambien a los agentes se les daban solo los publicados,
    asi que un articulo «despublicado» o en revision desaparecia de su lista.
    Ahora ven todos menos los archivados, o el estado que pidan.
    """
    q = db.query(KBArticle).options(joinedload(KBArticle.author))
    if public_only:
        q = q.filter(KBArticle.status == KBStatus.published, KBArticle.is_public == True)  # noqa: E712
    elif status:
        q = q.filter(KBArticle.status == status)
    else:
        q = q.filter(KBArticle.status != KBStatus.archived)
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
    salida = []
    for a in articles:
        datos = {
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
        }
        if not public_only:
            # Sin `status` la pantalla no sabia si un articulo estaba publicado.
            datos.update({
                "status": getattr(a.status, "value", a.status),
                "not_helpful_count": a.not_helpful_count,
                "deflection_count": a.deflection_count or 0,
                "review_comment": a.review_comment,
                "author_id": a.author_id,
            })
        salida.append(datos)
    return salida


def _articulo_visible(db: Session, article_id: str, solo_publico: bool) -> KBArticle:
    """El articulo si quien lee puede verlo: un cliente solo lo publicado y publico."""
    q = db.query(KBArticle).filter(KBArticle.id == article_id)
    if solo_publico:
        q = q.filter(KBArticle.status == KBStatus.published, KBArticle.is_public == True)  # noqa: E712
    article = q.first()
    if not article:
        raise ErrorDeDominio(404)
    return article


def get_kb_article_and_increment_view(db: Session, article_id: str, solo_publico: bool = False) -> KBArticle:
    article = _articulo_visible(db, article_id, solo_publico)
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
    from app.services.service_desk.kb_sugerencias import refrescar_vector

    article = KBArticle(number=_next_kb_number(db), author_id=author_id, **payload.model_dump())
    db.add(article)
    db.flush()
    if payload.status == "published":
        article.published_at = datetime.now(timezone.utc)
        refrescar_vector(article, db=db)
    _snapshot_kb_version(db, article, author_id, change_note="initial version")
    return article


def get_scoped_kb_article_or_404(db: Session, current_user: User, article_id: str) -> KBArticle:
    article = scope_kb_query(db.query(KBArticle), db, current_user).filter(KBArticle.id == article_id).first()
    if not article:
        raise ErrorDeDominio(404)
    return article


def delete_kb_article(db: Session, current_user, article_id: str) -> None:
    a = get_scoped_kb_article_or_404(db, current_user, article_id)
    db.delete(a)


def apply_kb_article_update(
    db: Session,
    article: KBArticle,
    payload,
    changed_by_user_id: Optional[str] = None,
    change_note: Optional[str] = None,
) -> None:

    before = {
        "title": article.title,
        "body": article.body,
        "summary": article.summary,
        "tags": article.tags,
        "status": article.status,
    }
    for key, value in payload.model_dump(exclude_unset=True, exclude_none=True).items():
        if key in {"change_note", "changed_by_user_id"}:
            continue
        setattr(article, key, value)
    if payload.status == "published" and not article.published_at:
        article.published_at = datetime.now(timezone.utc)

    after = {
        "title": article.title,
        "body": article.body,
        "summary": article.summary,
        "tags": article.tags,
        "status": article.status,
    }
    if before != after and getattr(article.status, "value", article.status) == KBStatus.published.value:
        from app.services.service_desk.kb_sugerencias import refrescar_vector
        refrescar_vector(article, db=db)
    if before != after:
        _snapshot_kb_version(
            db=db,
            article=article,
            changed_by_user_id=changed_by_user_id,
            change_note=change_note or "content update",
        )


def update_kb_helpful_vote(db: Session, article_id: str, helpful: bool, solo_publico: bool = False) -> None:
    article = _articulo_visible(db, article_id, solo_publico)
    if helpful:
        article.helpful_count = (article.helpful_count or 0) + 1
    else:
        article.not_helpful_count = (article.not_helpful_count or 0) + 1


def create_kb_from_ticket(db: Session, ticket_id: str, title: str, author_id: str) -> KBArticle:
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise ErrorDeDominio(404)
    if not ticket.resolution:
        raise ErrorDeDominio(400, "El ticket no tiene resolución")

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
    _snapshot_kb_version(db, article, author_id, change_note="created from ticket")
    ticket.kb_article_id = article.id
    return article


def _snapshot_kb_version(
    db: Session,
    article: KBArticle,
    changed_by_user_id: Optional[str],
    change_note: Optional[str] = None,
) -> KBArticleVersion:
    latest = (
        db.query(KBArticleVersion)
        .filter(KBArticleVersion.article_id == article.id)
        .order_by(KBArticleVersion.version.desc())
        .first()
    )
    next_version = (latest.version if latest else 0) + 1

    ver = KBArticleVersion(
        article_id=article.id,
        version=next_version,
        title=article.title,
        body=article.body,
        summary=article.summary,
        tags=article.tags,
        status=article.status,
        change_note=change_note,
        changed_by_user_id=changed_by_user_id,
    )
    db.add(ver)
    db.flush()
    return ver


def list_kb_versions(db: Session, article_id: str) -> list[KBArticleVersion]:
    return (
        db.query(KBArticleVersion)
        .filter(KBArticleVersion.article_id == article_id)
        .order_by(KBArticleVersion.version.desc())
        .all()
    )


def serialize_kb_versions(items: list[KBArticleVersion]) -> list[dict]:
    return [
        {
            "id": v.id,
            "article_id": v.article_id,
            "version": v.version,
            "title": v.title,
            "summary": v.summary,
            "tags": v.tags,
            "status": v.status,
            "change_note": v.change_note,
            "changed_by_user_id": v.changed_by_user_id,
            "created_at": v.created_at,
        }
        for v in items
    ]


def rollback_kb_to_version(
    db: Session,
    article: KBArticle,
    version: int,
    changed_by_user_id: Optional[str],
) -> None:
    target = (
        db.query(KBArticleVersion)
        .filter(
            KBArticleVersion.article_id == article.id,
            KBArticleVersion.version == version,
        )
        .first()
    )
    if not target:
        raise ErrorDeDominio(404, "KB version not found")

    article.title = target.title
    article.body = target.body
    article.summary = target.summary
    article.tags = target.tags
    article.status = target.status
    if article.status == KBStatus.published and not article.published_at:
        article.published_at = datetime.now(timezone.utc)

    _snapshot_kb_version(
        db,
        article,
        changed_by_user_id,
        change_note=f"rollback to v{version}",
    )


# ── Revision y publicacion ───────────────────────────────────────────────────
#
# Auditoria 2026-11: `reviewer_id` existia y no habia flujo; cualquiera
# publicaba. Con `SD_KB_REQUIRE_REVIEW`, el autor envia a revision y publica un
# revisor: un miembro de la cola `SD_KB_REVIEWER_GROUP_ID` o un administrador.

def puede_publicar(db: Session, user: User) -> bool:
    from app.models.service_desk import AgentGroupMember
    from app.services import settings_service as _ss

    org = user.organization_id
    if not _ss.get_runtime_bool(db, "SD_KB_REQUIRE_REVIEW", org):
        return True
    if user.is_superadmin or getattr(user.role, "value", user.role) == "admin":
        return True
    grupo = _ss.get_runtime_str(db, "SD_KB_REVIEWER_GROUP_ID", org)
    return bool(grupo) and db.query(AgentGroupMember.id).filter(
        AgentGroupMember.group_id == grupo, AgentGroupMember.user_id == user.id).first() is not None


def exigir_que_pueda_publicar(db: Session, user: User, nuevo_estado) -> None:
    if getattr(nuevo_estado, "value", nuevo_estado) == KBStatus.published.value and not puede_publicar(db, user):
        raise ErrorDeDominio(403, "Este artículo necesita revisión: envíalo a revisar")


def revisores(db: Session, user: User) -> list[str]:
    from app.models.service_desk import AgentGroupMember
    from app.models.user import UserRole
    from app.services import settings_service as _ss

    grupo = _ss.get_runtime_str(db, "SD_KB_REVIEWER_GROUP_ID", user.organization_id)
    if grupo:
        return [r[0] for r in db.query(AgentGroupMember.user_id).filter(AgentGroupMember.group_id == grupo).all()]
    return [r[0] for r in db.query(User.id).filter(User.role == UserRole.admin, User.is_active == True).all()]  # noqa: E712


def enviar_a_revision(db: Session, article: KBArticle, user: User) -> None:
    from app.services.notifications import notify_user

    if article.status not in (KBStatus.draft, KBStatus.draft.value):
        raise ErrorDeDominio(409, "Solo se envía a revisión un borrador")
    article.status = KBStatus.in_review
    article.review_comment = None
    for uid in revisores(db, user):
        if uid != user.id:
            notify_user(db, uid, "approval_requested", f"Revisar {article.number}: {article.title}"[:255],
                        "Un artículo de la base de conocimiento espera tu revisión.",
                        resource="kb", resource_id=article.id, action_url="/service-desk")


def revisar(db: Session, article: KBArticle, user: User, publicar: bool, comentario: Optional[str]) -> None:
    from app.services.notifications import notify_user
    from app.services.service_desk.kb_sugerencias import refrescar_vector

    if article.status not in (KBStatus.in_review, KBStatus.in_review.value):
        raise ErrorDeDominio(409, "El artículo no está en revisión")
    if not puede_publicar(db, user):
        raise ErrorDeDominio(403, "Solo un revisor puede publicar")
    if not publicar and not (comentario or "").strip():
        raise ErrorDeDominio(422, "Devolver un artículo pide decir qué cambiar")
    article.reviewer_id = user.id
    article.review_comment = (comentario or "").strip() or None
    if publicar:
        article.status = KBStatus.published
        article.published_at = article.published_at or datetime.now(timezone.utc)
        refrescar_vector(article, db=db)
    else:
        article.status = KBStatus.draft
    if article.author_id and article.author_id != user.id:
        notify_user(db, article.author_id, "system",
                    f"{article.number} {'publicado' if publicar else 'devuelto'}: {article.title}"[:255],
                    article.review_comment, resource="kb", resource_id=article.id, action_url="/service-desk")


def registrar_desvio(db: Session, article_id: str) -> None:
    """Un cliente dijo que el articulo le resolvio el problema sin abrir ticket."""
    article = _articulo_visible(db, article_id, solo_publico=True)
    article.deflection_count = (article.deflection_count or 0) + 1
    article.helpful_count = (article.helpful_count or 0) + 1
