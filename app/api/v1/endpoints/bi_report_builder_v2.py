"""BI Report Builder v2 endpoints.

Advanced report builder with 15+ configurable presets,
per-org customization, and export capabilities.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services import bi_report_builder_v2_service as svc

router = APIRouter()


class PresetCustomizeIn(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    columns: Optional[list[str]] = None
    group_by: Optional[str] = Field(None, max_length=80)
    sort_by: Optional[str] = Field(None, max_length=80)
    sort_direction: Optional[str] = Field(None, pattern="^(asc|desc)$")
    filters: Optional[dict[str, Any]] = None


@router.get("/bi/reports/v2/presets", summary="Catálogo completo de presets BI v2")
def list_presets(
    category: Optional[str] = Query(None, description="Filtrar por categoría"),
    grouped: bool = Query(False, description="Agrupar por categoría"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    if grouped:
        by_cat = svc.list_presets_by_category(db, organization_id=org_id)
        if category:
            by_cat = {k: v for k, v in by_cat.items() if k == category}
        return {"categories": by_cat}
    presets = svc.list_presets(db, organization_id=org_id)
    if category:
        presets = [p for p in presets if p.get("category") == category]
    return {"items": presets, "count": len(presets)}


@router.get("/bi/reports/v2/presets/{preset_id}", summary="Detalle de preset BI v2")
def get_preset(
    preset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        return svc.get_preset(db, organization_id=org_id, preset_id=preset_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/bi/reports/v2/presets/{preset_id}/customize", summary="Personalizar preset a nivel de organización")
def customize_preset(
    preset_id: str,
    body: PresetCustomizeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        return svc.customize_preset(
            db,
            organization_id=org_id,
            preset_id=preset_id,
            payload=body.model_dump(exclude_none=True),
        )
    except ValueError as exc:
        code = 404 if "not_found" in str(exc) else 422
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.delete(
    "/bi/reports/v2/presets/{preset_id}/customize",
    summary="Restaurar preset a configuración de fábrica",
    status_code=200,
)
def reset_preset_customization(
    preset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        return svc.reset_preset_customization(db, organization_id=org_id, preset_id=preset_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/bi/reports/v2/presets/{preset_id}/preview", summary="Preview de datos del preset")
def preview_preset(
    preset_id: str,
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        return svc.preview_preset(db, organization_id=org_id, preset_id=preset_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/bi/reports/v2/presets/{preset_id}/export", summary="Exportar datos del preset (JSON/CSV)")
def export_preset(
    preset_id: str,
    format: str = Query("json", pattern="^(json|csv|xlsx)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        return svc.export_preset_data(
            db,
            organization_id=org_id,
            preset_id=preset_id,
            export_format=format,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/bi/reports/v2/categories", summary="Categorías de presets disponibles")
def list_categories(
    current_user: User = Depends(get_current_user),
):
    categories = sorted(set(p["category"] for p in svc.BASE_PRESETS))
    return {"items": categories}
