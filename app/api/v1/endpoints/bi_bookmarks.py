"""BI Bookmarks endpoints.

Save and restore named dashboard states (period, tab, filters, widget config).
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services import bi_bookmarks_service as svc

router = APIRouter()


class BookmarkCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=500)
    period_days: int = Field(30, ge=1, le=1825)
    active_tab: Optional[str] = Field(None, max_length=80)
    filters: Optional[dict[str, Any]] = None
    widget_states: Optional[dict[str, Any]] = None
    chart_types: Optional[dict[str, str]] = None
    shared: bool = False


class BookmarkPatchIn(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=500)
    period_days: Optional[int] = Field(None, ge=1, le=1825)
    active_tab: Optional[str] = Field(None, max_length=80)
    filters: Optional[dict[str, Any]] = None
    widget_states: Optional[dict[str, Any]] = None
    chart_types: Optional[dict[str, str]] = None
    shared: Optional[bool] = None


@router.get("/bi/bookmarks", summary="Listar bookmarks de dashboard BI")
def list_bookmarks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    items = svc.list_bookmarks(db, organization_id=org_id, user_id=current_user.id)
    return {"items": items, "count": len(items)}


@router.post("/bi/bookmarks", summary="Guardar estado actual del dashboard como bookmark", status_code=201)
def create_bookmark(
    body: BookmarkCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        bookmark = svc.create_bookmark(
            db,
            organization_id=org_id,
            payload=body.model_dump(),
            current_user=current_user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return bookmark


@router.get("/bi/bookmarks/{bookmark_id}", summary="Obtener bookmark por ID")
def get_bookmark(
    bookmark_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        bookmark = svc.get_bookmark(
            db,
            organization_id=org_id,
            bookmark_id=bookmark_id,
            current_user=current_user,
        )
    except ValueError as exc:
        code = 404 if "not_found" in str(exc) else 403
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return bookmark


@router.patch("/bi/bookmarks/{bookmark_id}", summary="Actualizar bookmark")
def update_bookmark(
    bookmark_id: str,
    body: BookmarkPatchIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        bookmark = svc.update_bookmark(
            db,
            organization_id=org_id,
            bookmark_id=bookmark_id,
            payload=body.model_dump(exclude_none=True),
            current_user=current_user,
        )
    except ValueError as exc:
        code = 404 if "not_found" in str(exc) else 403
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return bookmark


@router.delete("/bi/bookmarks/{bookmark_id}", summary="Eliminar bookmark", status_code=204)
def delete_bookmark(
    bookmark_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        deleted = svc.delete_bookmark(
            db,
            organization_id=org_id,
            bookmark_id=bookmark_id,
            current_user=current_user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="bookmark_not_found")
