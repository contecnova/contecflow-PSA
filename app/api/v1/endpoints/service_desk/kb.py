"""Service Desk — Knowledge Base subdomain router."""
from fastapi import APIRouter, Depends, Query, Header, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.core.deps import get_current_user, require_internal_user
from app.core.responses import APIListResponse, APIResponse
from app.models.user import User
from app.core.abac_enforce import enforce_abac
from app.services.service_desk.ticket_ops_service import commit_or_rollback as _commit_or_rollback
from app.schemas.service_desk import KBArticleIn, KBArticleUpdate
from app.services.service_desk.kb_service import (
    list_kb_articles_scoped, serialize_kb_articles,
    get_kb_article_and_increment_view, serialize_kb_article_detail,
    build_kb_article, get_scoped_kb_article_or_404, apply_kb_article_update,
    update_kb_helpful_vote, delete_kb_article as delete_kb_article_svc,
    list_kb_versions, serialize_kb_versions, rollback_kb_to_version,
)

router = APIRouter()


from app.services.service_desk.portal_auth_service import (  # noqa: E402
    Lector, get_portal_client_or_user as lector_de_la_kb,
)


@router.get("/kb", summary="Artículos de base de conocimiento")
def list_kb_articles(
    search: Optional[str] = None, category_id: Optional[str] = None,
    public_only: bool = False, status: Optional[str] = None,
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    response: Response = None,
    db: Session = Depends(get_db), authorization: Optional[str] = Header(None),
    lector: Lector = Depends(lector_de_la_kb),
):
    solo_publico = public_only or lector.solo_publico
    articles = list_kb_articles_scoped(
        db=db, search=search, category_id=category_id, public_only=solo_publico,
        page=page, page_size=page_size, response=response, authorization=authorization,
        status=status,
    )
    return APIListResponse.ok(items=serialize_kb_articles(articles, solo_publico), page=page, page_size=page_size)


@router.get("/kb/suggest", summary="Artículos que podrían resolver lo que se está escribiendo")
def sugerir_articulos(q: str = Query(..., min_length=1, max_length=500), db: Session = Depends(get_db),
                      lector: Lector = Depends(lector_de_la_kb)):
    """Va ANTES de `/kb/{article_id}`: si no, «suggest» se tomaria por un id."""
    from app.services.service_desk.kb_sugerencias import sugerir
    return APIListResponse.ok(items=sugerir(db, q, solo_publico=lector.solo_publico))


@router.post("/kb/{article_id}/deflected", summary="El artículo resolvió el problema sin abrir ticket")
def marcar_desvio(article_id: str, db: Session = Depends(get_db), lector: Lector = Depends(lector_de_la_kb)):
    from app.services.service_desk.kb_service import registrar_desvio
    registrar_desvio(db, article_id)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True})


class RevisionIn(BaseModel):
    publish: bool
    comment: Optional[str] = Field(None, max_length=4000)


@router.post("/kb/{article_id}/submit", summary="Enviar el artículo a revisión")
def enviar_a_revision(article_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
                      _rol: User = Depends(require_internal_user)):
    from app.services.service_desk.kb_service import enviar_a_revision as svc
    a = get_scoped_kb_article_or_404(db, current_user, article_id)
    svc(db, a, current_user)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True, "status": "in_review"})


@router.post("/kb/{article_id}/review", summary="Publicar o devolver un artículo en revisión")
def revisar(article_id: str, payload: RevisionIn, db: Session = Depends(get_db),
            current_user: User = Depends(get_current_user), _rol: User = Depends(require_internal_user)):
    from app.services.service_desk.kb_service import revisar as svc
    a = get_scoped_kb_article_or_404(db, current_user, article_id)
    svc(db, a, current_user, payload.publish, payload.comment)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True, "status": getattr(a.status, "value", a.status)})


@router.get("/kb/{article_id}", summary="Detalle de artículo KB")
def get_kb_article(article_id: str, db: Session = Depends(get_db), lector: Lector = Depends(lector_de_la_kb)):
    a = get_kb_article_and_increment_view(db, article_id, solo_publico=lector.solo_publico)
    _commit_or_rollback(db)
    return APIResponse.ok(data=serialize_kb_article_detail(a))


@router.post("/kb", summary="Crear artículo KB")
def create_kb_article(payload: KBArticleIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: dominio: los agentes escriben la base de conocimiento
):
    from app.services.service_desk.kb_service import exigir_que_pueda_publicar
    exigir_que_pueda_publicar(db, current_user, payload.status)
    a = build_kb_article(db, payload, current_user.id)
    _commit_or_rollback(db); db.refresh(a)
    return APIResponse.ok(data={"id": a.id, "number": a.number})


@router.patch("/kb/{article_id}", summary="Actualizar artículo KB")
def update_kb_article(article_id: str, payload: KBArticleUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: dominio: los agentes escriben la base de conocimiento
):
    from app.services.service_desk.kb_service import exigir_que_pueda_publicar
    a = get_scoped_kb_article_or_404(db, current_user, article_id)
    if payload.status:
        exigir_que_pueda_publicar(db, current_user, payload.status)
    apply_kb_article_update(db, a, payload, changed_by_user_id=current_user.id)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True})


@router.delete("/kb/{article_id}", summary="Eliminar artículo KB")
def delete_kb_article(article_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: dominio: los agentes escriben la base de conocimiento
):
    enforce_abac(db, current_user, "sd_kb_article", article_id, action="delete")
    delete_kb_article_svc(db, current_user, article_id)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True})


@router.post("/kb/{article_id}/helpful", summary="Marcar artículo como útil")
def mark_helpful(article_id: str, helpful: bool = True, db: Session = Depends(get_db),
                 lector: Lector = Depends(lector_de_la_kb)):
    update_kb_helpful_vote(db, article_id, helpful, solo_publico=lector.solo_publico)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True})


# NOTE: GET /known-errors is canonically served by problem_management.py (KEDB).
# Removed here to avoid duplicate routes.


@router.get("/kb/{article_id}/versions", summary="Historial de versiones de artículo KB")
def get_kb_versions(
    article_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ = get_scoped_kb_article_or_404(db, current_user, article_id)
    items = list_kb_versions(db, article_id)
    return APIListResponse.ok(items=serialize_kb_versions(items))


@router.post("/kb/{article_id}/rollback/{version}", summary="Rollback de artículo KB a versión previa")
def rollback_kb(
    article_id: str,
    version: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_internal_user),  # auditoria 2026-09: dominio: los agentes escriben la base de conocimiento
):
    article = get_scoped_kb_article_or_404(db, current_user, article_id)
    rollback_kb_to_version(db, article, version, changed_by_user_id=current_user.id)
    _commit_or_rollback(db)
    return APIResponse.ok(data={"ok": True, "article_id": article_id, "rolled_back_to": version})
