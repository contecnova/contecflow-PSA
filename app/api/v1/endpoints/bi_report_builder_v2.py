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
from app.core.abac_enforce import enforce_abac
from app.services import bi_report_builder_v2_service as svc
from app.core.responses import APIListResponse, APIResponse

router = APIRouter()


class PresetCustomizeIn(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    columns: Optional[list[str]] = None
    group_by: Optional[str] = Field(None, max_length=80)
    sort_by: Optional[str] = Field(None, max_length=80)
    sort_direction: Optional[str] = Field(None, pattern="^(asc|desc)$")
    filters: Optional[dict[str, Any]] = None


class ControlledExecutionIn(BaseModel):
    limit: int = Field(1000, ge=1, le=10000)
    timeout_seconds: int = Field(8, ge=2, le=60)


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
        return APIResponse.ok(data={"categories": by_cat})
    presets = svc.list_presets(db, organization_id=org_id)
    if category:
        presets = [p for p in presets if p.get("category") == category]
    return APIListResponse.ok(items=presets, total=len(presets))


@router.get("/bi/reports/v2/presets/{preset_id}", summary="Detalle de preset BI v2")
def get_preset(
    preset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        return APIResponse.ok(data=svc.get_preset(db, organization_id=org_id, preset_id=preset_id))
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
        updated = svc.customize_preset(
            db,
            organization_id=org_id,
            preset_id=preset_id,
            payload=body.model_dump(exclude_none=True),
        )
        return APIResponse.ok(data=updated)
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
    enforce_abac(db, current_user, "bi_report_preset", preset_id, action="delete")
    org_id = getattr(current_user, "organization_id", None)
    try:
        return APIResponse.ok(data=svc.reset_preset_customization(db, organization_id=org_id, preset_id=preset_id))
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
        return APIResponse.ok(data=svc.preview_preset(db, organization_id=org_id, preset_id=preset_id, limit=limit))
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
        return APIResponse.ok(data=svc.export_preset_data(
            db,
            organization_id=org_id,
            preset_id=preset_id,
            export_format=format,
        ))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/bi/reports/v2/presets/{preset_id}/execute-controlled", summary="Ejecutar preset con control de timeout y degradación")
def execute_preset_controlled(
    preset_id: str,
    body: ControlledExecutionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        return APIResponse.ok(data=svc.execute_preset_with_controls(
            db,
            organization_id=org_id,
            preset_id=preset_id,
            limit=body.limit,
            timeout_seconds=body.timeout_seconds,
        ))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/bi/reports/v2/executions/{execution_id}", summary="Consultar progreso/resultado de ejecución controlada")
def get_controlled_execution(
    execution_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        return APIResponse.ok(data=svc.get_execution_status(db, organization_id=org_id, execution_id=execution_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/bi/reports/v2/categories", summary="Categorías de presets disponibles")
def list_categories(
    current_user: User = Depends(get_current_user),
):
    categories = sorted(set(p["category"] for p in svc.BASE_PRESETS))
    items = [{"name": c} for c in categories]
    return APIListResponse.ok(items=items, total=len(items))


# ── BI Phase 2: Component library ─────────────────────────────────────────────

@router.get("/bi/reports/v2/components", summary="Biblioteca de componentes de dashboard (drag-and-drop)")
def list_component_types(current_user: User = Depends(get_current_user)):
    _ = current_user
    items = svc.list_component_types()
    return APIListResponse.ok(items=items, total=len(items))


# ── BI Phase 2: Dashboard layout persistence ──────────────────────────────────

class DashboardLayoutSaveIn(BaseModel):
    components: list[dict[str, Any]] = Field(default_factory=list)
    grid_cols: int = Field(12, ge=4, le=24)


@router.get("/bi/reports/v2/layouts", summary="Listar layouts de dashboard guardados")
def list_dashboard_layouts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    items = svc.list_dashboard_layouts(db, organization_id=org_id)
    return APIListResponse.ok(items=items, total=len(items))


@router.get("/bi/reports/v2/layouts/{dashboard_key}", summary="Obtener layout de dashboard guardado")
def get_dashboard_layout(
    dashboard_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return APIResponse.ok(data=svc.get_dashboard_layout(db, organization_id=org_id, dashboard_key=dashboard_key))


@router.put("/bi/reports/v2/layouts/{dashboard_key}", summary="Guardar layout de dashboard (drag-and-drop)")
def save_dashboard_layout(
    dashboard_key: str,
    body: DashboardLayoutSaveIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return APIResponse.ok(data=svc.save_dashboard_layout(
        db,
        organization_id=org_id,
        dashboard_key=dashboard_key,
        components=body.components,
        grid_cols=body.grid_cols,
    ))


# ── BI Phase 2: Dashboard templates CRUD ─────────────────────────────────────

class TemplateCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field("", max_length=500)
    layout: list[dict[str, Any]] = Field(default_factory=list)
    preset_id: Optional[str] = Field(None, max_length=120)
    tags: list[str] = Field(default_factory=list)


class TemplateUpdateIn(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=500)
    layout: Optional[list[dict[str, Any]]] = None
    preset_id: Optional[str] = Field(None, max_length=120)
    tags: Optional[list[str]] = None


@router.get("/bi/reports/v2/templates", summary="Listar templates de dashboard")
def list_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    items = svc.list_templates(db, organization_id=org_id)
    return APIListResponse.ok(items=items, total=len(items))


@router.get("/bi/reports/v2/templates/{template_id}", summary="Detalle de template de dashboard")
def get_template(
    template_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        return APIResponse.ok(data=svc.get_template(db, organization_id=org_id, template_id=template_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/bi/reports/v2/templates", summary="Crear template de dashboard", status_code=201)
def create_template(
    body: TemplateCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return APIResponse.ok(data=svc.create_template(
        db,
        organization_id=org_id,
        name=body.name,
        description=body.description,
        layout=body.layout,
        preset_id=body.preset_id,
        tags=body.tags,
    ))


@router.put("/bi/reports/v2/templates/{template_id}", summary="Actualizar template de dashboard")
def update_template(
    template_id: str,
    body: TemplateUpdateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        return APIResponse.ok(data=svc.update_template(
            db,
            organization_id=org_id,
            template_id=template_id,
            payload=body.model_dump(exclude_none=True),
        ))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/bi/reports/v2/templates/{template_id}", summary="Eliminar template de dashboard", status_code=200)
def delete_template(
    template_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enforce_abac(db, current_user, "bi_report_template", template_id, action="delete")
    org_id = getattr(current_user, "organization_id", None)
    try:
        svc.delete_template(db, organization_id=org_id, template_id=template_id)
        return APIResponse.ok(data={"ok": True, "template_id": template_id})
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
