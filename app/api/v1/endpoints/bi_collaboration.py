"""BI Collaboration endpoints.

Collaboration and governance APIs for BI dashboards.
Designed as an orchestration layer over app.services.bi_collaboration_service.
"""
from __future__ import annotations

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.security import decode_token
from app.db.session import get_db
from app.db.session import SessionLocal
from app.models.user import User
from app.core.abac_enforce import enforce_abac
from app.services import bi_collaboration_service as svc

router = APIRouter()


class CommentCreateIn(BaseModel):
    dashboard_key: str = Field(..., min_length=1, max_length=120)
    widget_id: str = Field(..., min_length=1, max_length=120)
    message: str = Field(..., min_length=2, max_length=4000)


class GovernanceRulesPatchIn(BaseModel):
    olap_max_staleness_hours: Optional[float] = Field(None, ge=1, le=240)
    max_error_reports: Optional[int] = Field(None, ge=0, le=100)
    require_active_schedules: Optional[bool] = None


class SharedViewCreateIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    dashboard_key: str = Field(..., min_length=1, max_length=120)
    filters: dict = Field(default_factory=dict)


class SharedViewPatchIn(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=120)
    dashboard_key: Optional[str] = Field(None, min_length=1, max_length=120)
    filters: Optional[dict] = None
    active: Optional[bool] = None


class DashboardVersionCreateIn(BaseModel):
    config: dict = Field(..., description="Serialized dashboard configuration snapshot")
    change_log: Optional[str] = Field(None, max_length=500)


class DashboardShareIn(BaseModel):
    target_user_id: str = Field(..., min_length=1, max_length=120)
    target_user_name: str = Field(..., min_length=1, max_length=200)
    permission: str = Field(..., pattern="^(view|edit|admin)$")


class CachePolicyIn(BaseModel):
    critical_refresh_seconds: int = Field(..., ge=5, le=10)


@router.get("/bi/collaboration/comments", summary="Listar comentarios BI por dashboard/widget")
def list_bi_comments(
    dashboard_key: Optional[str] = Query(None),
    widget_id: Optional[str] = Query(None),
    include_resolved: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    items = svc.list_comments(
        db,
        organization_id=org_id,
        dashboard_key=dashboard_key,
        widget_id=widget_id,
        include_resolved=include_resolved,
    )
    return {
        "items": items,
        "count": len(items),
    }


@router.post("/bi/collaboration/comments", summary="Crear comentario BI")
def create_bi_comment(
    payload: CommentCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    comment = svc.create_comment(
        db,
        organization_id=org_id,
        dashboard_key=payload.dashboard_key,
        widget_id=payload.widget_id,
        message=payload.message,
        author=current_user,
    )
    return {"ok": True, "comment": comment}


@router.patch("/bi/collaboration/comments/{comment_id}/resolve", summary="Marcar comentario BI como resuelto")
def resolve_bi_comment(
    comment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        comment = svc.resolve_comment(
            db,
            organization_id=org_id,
            comment_id=comment_id,
            current_user=current_user,
        )
        return {"ok": True, "comment": comment}
    except ValueError:
        raise HTTPException(status_code=404, detail="Comentario no encontrado")


@router.get("/bi/governance/overview", summary="Overview de governance BI Collaboration")
def governance_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return svc.governance_overview(db, organization_id=org_id)


@router.get("/bi/governance/rules", summary="Leer reglas de governance BI Collaboration")
def governance_rules(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return svc.get_governance_rules(db, organization_id=org_id)


@router.patch("/bi/governance/rules", summary="Actualizar reglas de governance BI Collaboration")
def patch_governance_rules(
    payload: GovernanceRulesPatchIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    return svc.update_governance_rules(db, organization_id=org_id, payload=data)


@router.post("/bi/governance/run-checks", summary="Ejecutar checks de governance BI Collaboration")
def run_governance_checks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return svc.run_governance_checks(db, organization_id=org_id)


@router.get("/bi/governance/last-run", summary="Última ejecución de checks governance BI")
def last_governance_run(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return {"result": svc.get_last_governance_run(db, organization_id=org_id)}


@router.get("/bi/collaboration/shared-views", summary="Listar vistas compartidas BI")
def list_shared_views(
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    items = svc.list_shared_views(db, organization_id=org_id, only_active=not include_inactive)
    return {"items": items, "count": len(items)}


@router.post("/bi/collaboration/shared-views", summary="Crear vista compartida BI")
def create_shared_view(
    payload: SharedViewCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    item = svc.create_shared_view(
        db,
        organization_id=org_id,
        name=payload.name,
        dashboard_key=payload.dashboard_key,
        filters=payload.filters,
        created_by=current_user,
    )
    return {"ok": True, "view": item}


@router.patch("/bi/collaboration/shared-views/{view_id}", summary="Actualizar vista compartida BI")
def patch_shared_view(
    view_id: str,
    payload: SharedViewPatchIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        item = svc.patch_shared_view(
            db,
            organization_id=org_id,
            view_id=view_id,
            payload={k: v for k, v in payload.model_dump().items() if v is not None},
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Vista compartida no encontrada")
    return {"ok": True, "view": item}


# ── Dashboard versioning ───────────────────────────────────────────────────────

@router.get("/bi/collaboration/dashboards/{dashboard_key}/versions", summary="Historial de versiones de un dashboard BI")
def list_dashboard_versions(
    dashboard_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    items = svc.list_dashboard_versions(db, organization_id=org_id, dashboard_key=dashboard_key)
    return {"items": items, "count": len(items)}


@router.post("/bi/collaboration/dashboards/{dashboard_key}/versions", summary="Guardar versión de dashboard BI")
def create_dashboard_version(
    dashboard_key: str,
    payload: DashboardVersionCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    item = svc.create_dashboard_version(
        db,
        organization_id=org_id,
        dashboard_key=dashboard_key,
        config=payload.config,
        change_log=payload.change_log,
        current_user=current_user,
    )
    return {"ok": True, "version": item}


@router.post(
    "/bi/collaboration/dashboards/{dashboard_key}/versions/{version_id}/restore",
    summary="Restaurar versión anterior de dashboard BI",
)
def restore_dashboard_version(
    dashboard_key: str,
    version_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        item = svc.restore_dashboard_version(
            db,
            organization_id=org_id,
            dashboard_key=dashboard_key,
            version_id=version_id,
            current_user=current_user,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Versión no encontrada")
    return {"ok": True, "version": item}


# ── Dashboard Notifications ────────────────────────────────────────────────────

@router.get("/bi/collaboration/notifications", summary="Listar notificaciones de colaboración BI")
def list_notifications(
    dashboard_key: Optional[str] = Query(None),
    include_read: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    items = svc.list_notifications(
        db,
        organization_id=org_id,
        recipient_user_id=current_user.id,
        dashboard_key=dashboard_key,
        only_unread=not include_read,
    )
    return {"items": items, "count": len(items)}


@router.patch("/bi/collaboration/notifications/{notification_id}", summary="Marcar notificación como leída")
def mark_notification_read(
    notification_id: str,
    payload: Optional[dict] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        is_read = (payload or {}).get("is_read", True)
        item = svc.mark_notification_read(
            db,
            organization_id=org_id,
            notification_id=notification_id,
            recipient_user_id=current_user.id,
            is_read=is_read,
        )
        return {"ok": True, "notification": item}
    except ValueError:
        raise HTTPException(status_code=404, detail="Notificación no encontrada")


# ── Dashboard sharing ──────────────────────────────────────────────────────────

@router.get("/bi/collaboration/dashboards/{dashboard_key}/shares", summary="Listar accesos compartidos de dashboard BI")
def list_dashboard_shares(
    dashboard_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    items = svc.list_dashboard_shares(db, organization_id=org_id, dashboard_key=dashboard_key)
    return {"items": items, "count": len(items)}


@router.post("/bi/collaboration/dashboards/{dashboard_key}/shares", summary="Compartir dashboard BI con usuario")
def share_dashboard(
    dashboard_key: str,
    payload: DashboardShareIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    try:
        item = svc.share_dashboard(
            db,
            organization_id=org_id,
            dashboard_key=dashboard_key,
            target_user_id=payload.target_user_id,
            target_user_name=payload.target_user_name,
            permission=payload.permission,
            shared_by=current_user,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "share": item}


@router.delete(
    "/bi/collaboration/dashboards/{dashboard_key}/shares/{share_id}",
    summary="Revocar acceso compartido a dashboard BI",
)
def revoke_dashboard_share(
    dashboard_key: str,
    share_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enforce_abac(db, current_user, "bi_dashboard_share", share_id, action="delete")
    org_id = getattr(current_user, "organization_id", None)
    deleted = svc.revoke_dashboard_share(
        db, organization_id=org_id, dashboard_key=dashboard_key, share_id=share_id
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Acceso compartido no encontrado")
    return {"ok": True}


@router.get('/bi/collaboration/cache-policy', summary='Política de refresco BI (crítico 5-10s)')
def get_cache_policy(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, 'organization_id', None)
    return svc.get_cache_policy(db, organization_id=org_id)


@router.patch('/bi/collaboration/cache-policy', summary='Actualizar refresco crítico BI (5-10s)')
def patch_cache_policy(
    payload: CachePolicyIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, 'organization_id', None)
    return svc.update_cache_policy(
        db,
        organization_id=org_id,
        critical_refresh_seconds=payload.critical_refresh_seconds,
    )


@router.get('/bi/collaboration/dashboards/{dashboard_key}/updates/snapshot', summary='Snapshot de actualización de dashboard BI')
def dashboard_updates_snapshot(
    dashboard_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, 'organization_id', None)
    return svc.dashboard_update_snapshot(db, organization_id=org_id, dashboard_key=dashboard_key)


@router.websocket('/bi/collaboration/dashboards/{dashboard_key}/updates')
async def dashboard_updates_ws(websocket: WebSocket, dashboard_key: str, token: Optional[str] = Query(default=None)):
    if not token:
        await websocket.close(code=4001, reason='Token requerido')
        return

    if settings.ENVIRONMENT in {'production', 'staging'}:
        await websocket.close(code=4003, reason='Token en URL no permitido en production')
        return

    payload = decode_token(token)
    if not payload or payload.get('type') != 'access':
        await websocket.close(code=4001, reason='Token invalido')
        return

    user_id = payload.get('sub')
    if not user_id:
        await websocket.close(code=4001, reason='Token invalido')
        return

    await websocket.accept()

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            await websocket.close(code=4004, reason='Usuario no encontrado')
            return

        org_id = getattr(user, 'organization_id', None)
        policy = svc.get_cache_policy(db, organization_id=org_id)
        interval = int(policy.get('critical_refresh_seconds', 10))
        interval = max(5, min(10, interval))

        while True:
            snapshot = svc.dashboard_update_snapshot(
                db,
                organization_id=org_id,
                dashboard_key=dashboard_key,
            )
            await websocket.send_text(json.dumps(snapshot, ensure_ascii=False))
            await asyncio.sleep(interval)
    except WebSocketDisconnect:
        return
    finally:
        db.close()
