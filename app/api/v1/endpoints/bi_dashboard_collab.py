"""
bi_dashboard_collab.py — Dashboard collaboration REST endpoints.

Routes:
  POST /bi/collab/comments              — add a comment on a dashboard/widget
  GET  /bi/collab/comments              — list comments
  PATCH /bi/collab/comments/{id}/resolve — resolve a comment
  POST /bi/collab/views                 — save a shared view snapshot
  GET  /bi/collab/views                 — list shared views
  POST /bi/collab/reactions             — toggle reaction emoji
  GET  /bi/collab/reactions             — get reactions for a target
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.ratelimit import limiter
from app.db.session import get_db
from app.models.user import User
from app.services import bi_dashboard_collab_service as svc

router = APIRouter()


class CommentIn(BaseModel):
    dashboard_id: str
    widget_id: Optional[str] = None
    text: str = Field(..., min_length=1, max_length=2000)
    mentions: list[str] = Field(default_factory=list)


class SharedViewIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    dashboard_id: str
    layout_state: dict = Field(default_factory=dict)
    filter_state: dict = Field(default_factory=dict)
    is_public: bool = False


class ReactionIn(BaseModel):
    target_id: str
    target_type: str = Field("comment", pattern="^(comment|widget|dashboard)$")
    emoji: str = Field(..., min_length=1, max_length=10)


class CommentReactionIn(BaseModel):
    emoji: str = Field(..., min_length=1, max_length=10)


@router.post("/bi/collab/comments", summary="Añadir comentario en dashboard/widget", status_code=201)
@limiter.limit("30/minute")
def add_comment(
    request: Request,
    body: CommentIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return svc.add_comment(
        db,
        org_id=org_id,
        dashboard_id=body.dashboard_id,
        widget_id=body.widget_id,
        author_user_id=current_user.id,
        author_name=getattr(current_user, "full_name", current_user.id),
        text=body.text,
        mentions=body.mentions,
    )


@router.get("/bi/collab/comments", summary="Listar comentarios de un dashboard")
@limiter.limit("60/minute")
def list_comments(
    request: Request,
    dashboard_id: Optional[str] = Query(None),
    widget_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    items = svc.list_comments(db, org_id=org_id, dashboard_id=dashboard_id, widget_id=widget_id)
    return {"items": items, "count": len(items)}


@router.patch("/bi/collab/comments/{comment_id}/resolve", summary="Resolver un comentario")
@limiter.limit("30/minute")
def resolve_comment(
    request: Request,
    comment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        return svc.resolve_comment(db, org_id=org_id, comment_id=comment_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/bi/collab/views", summary="Guardar vista compartida del dashboard", status_code=201)
@limiter.limit("20/minute")
def save_shared_view(
    request: Request,
    body: SharedViewIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return svc.save_shared_view(
        db,
        org_id=org_id,
        name=body.name,
        dashboard_id=body.dashboard_id,
        layout_state=body.layout_state,
        filter_state=body.filter_state,
        created_by=current_user.id,
        is_public=body.is_public,
    )


@router.get("/bi/collab/views", summary="Listar vistas compartidas")
@limiter.limit("60/minute")
def list_shared_views(
    request: Request,
    dashboard_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    items = svc.list_shared_views(db, org_id=org_id, dashboard_id=dashboard_id)
    return {"items": items, "count": len(items)}


@router.post("/bi/collab/reactions", summary="Toggle reaction emoji en elemento de dashboard")
@limiter.limit("60/minute")
def toggle_reaction(
    request: Request,
    body: ReactionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return svc.toggle_reaction(
        db,
        org_id=org_id,
        target_id=body.target_id,
        target_type=body.target_type,
        user_id=current_user.id,
        emoji=body.emoji,
    )


@router.post("/bi/collab/comments/{comment_id}/reactions", summary="Toggle reaction en comentario", status_code=201)
@limiter.limit("60/minute")
def toggle_comment_reaction(
    request: Request,
    comment_id: str,
    body: CommentReactionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return svc.toggle_reaction(
        db,
        org_id=org_id,
        target_id=comment_id,
        target_type="comment",
        user_id=current_user.id,
        emoji=body.emoji,
    )


@router.get("/bi/collab/reactions", summary="Obtener reacciones para un elemento")
@limiter.limit("60/minute")
def get_reactions(
    request: Request,
    target_id: str = Query(...),
    target_type: str = Query("comment"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    items = svc.get_reactions(db, org_id=org_id, target_id=target_id, target_type=target_type)
    return {"items": items}
