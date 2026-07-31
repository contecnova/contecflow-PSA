"""M365 BI Embed endpoints — integración de dashboards BI en Teams y SharePoint.

Cierra el gap vs Power BI en integración Word/Excel/Teams/SharePoint:

  POST /m365/bi/teams/tab          — Genera config de pestaña Teams + registro via Graph
  POST /m365/bi/teams/card         — Publica card KPI Adaptive en canal de Teams
  GET  /m365/bi/sharepoint/webpart — Config iframe para SharePoint Embed web part
  POST /m365/bi/sharepoint/page    — Crea página SharePoint con BI incrustado
  GET  /m365/bi/export/excel       — Descarga .xlsx con histórico + forecast + anomalías
  GET  /m365/bi/export/word        — Descarga .rtf con resumen narrativo BI
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.responses import APIResponse
from app.db.session import get_db
from app.models.user import User
from app.services import m365_bi_embed_service as svc

router = APIRouter(tags=["M365 BI Embed"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class TeamsTabRequest(BaseModel):
    dashboard_id: str = Field(..., min_length=1, max_length=120)
    team_id: Optional[str] = Field(None, description="Teams team GUID — si se omite sólo devuelve la config")
    channel_id: Optional[str] = Field(None, description="Teams channel GUID")
    ttl_minutes: int = Field(480, ge=10, le=10080, description="Duración del embed token (min)")
    register_via_graph: bool = Field(
        False, description="Si True y team_id/channel_id están presentes, registra la pestaña via Graph API"
    )


class TeamsCardRequest(BaseModel):
    dashboard_id: str = Field(..., min_length=1, max_length=120)
    team_id: str = Field(..., description="Teams team GUID")
    channel_id: str = Field(..., description="Teams channel GUID")


class SharePointPageRequest(BaseModel):
    site_id: str = Field(..., description="SharePoint site ID (Graph format: siteHostname,siteId,webId)")
    page_title: str = Field(..., min_length=1, max_length=255)
    dashboard_id: str = Field(..., min_length=1, max_length=120)
    ttl_minutes: int = Field(1440, ge=60, le=43200)


# ── Teams Tab ─────────────────────────────────────────────────────────────────

@router.post(
    "/m365/bi/teams/tab",
    summary="Configurar pestaña Teams con dashboard BI de Contecflow",
)
def configure_teams_tab(
    payload: TeamsTabRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Genera la configuración de una pestaña Teams que embebe un dashboard BI.

    Si `register_via_graph=True` y se proporcionan `team_id` + `channel_id`,
    registra automáticamente la pestaña en el canal via Graph API
    (requiere permisos: `TeamsTab.ReadWriteForTeam.All`).

    Siempre devuelve `content_url`, `embed_token` y `tab_config` para
    configuración manual desde el botón + en Teams.
    """
    org_id = str(current_user.organization_id or "global")
    user_id = str(current_user.id)
    return svc.generate_teams_tab_config(
        db,
        dashboard_id=payload.dashboard_id,
        org_id=org_id,
        user_id=user_id,
        team_id=payload.team_id,
        channel_id=payload.channel_id,
        ttl_minutes=payload.ttl_minutes,
        register_via_graph=payload.register_via_graph,
    )


# ── Teams Adaptive Card ───────────────────────────────────────────────────────

@router.post(
    "/m365/bi/teams/card",
    summary="Publicar snapshot KPI como Adaptive Card en canal de Teams",
)
def post_teams_bi_card(
    payload: TeamsCardRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Publica un Adaptive Card 1.5 con KPIs del dashboard BI en el canal indicado.

    - Si Graph API está configurado usa `POST /teams/{teamId}/channels/{channelId}/messages`
      (requiere `ChannelMessage.Send` application permission).
    - Si no, hace fallback a `TEAMS_WEBHOOK_URL` con formato MessageCard.
    """
    org_id = str(current_user.organization_id or "global")
    user_id = str(current_user.id)
    return svc.post_bi_card_to_teams_channel(
        db,
        team_id=payload.team_id,
        channel_id=payload.channel_id,
        dashboard_id=payload.dashboard_id,
        org_id=org_id,
        user_id=user_id,
    )


# ── SharePoint web part config ────────────────────────────────────────────────

@router.get(
    "/m365/bi/sharepoint/webpart",
    summary="Obtener configuración de iframe para SharePoint Embed web part",
)
def get_sharepoint_webpart(
    dashboard_id: str = Query(..., min_length=1, max_length=120),
    ttl_minutes: int = Query(1440, ge=60, le=43200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Devuelve `iframe_html` listo para pegar en un Embed web part de SharePoint.

    El campo `embed_url` puede usarse directamente en el campo URL del web part.
    El token expira en `ttl_minutes` minutos — renovar antes de `expires_at`.
    """
    org_id = str(current_user.organization_id or "global")
    user_id = str(current_user.id)
    return svc.get_sharepoint_webpart_config(
        db,
        dashboard_id=dashboard_id,
        org_id=org_id,
        user_id=user_id,
        ttl_minutes=ttl_minutes,
    )


# ── SharePoint page creation ──────────────────────────────────────────────────

@router.post(
    "/m365/bi/sharepoint/page",
    summary="Crear página SharePoint con dashboard BI incrustado",
)
def create_sharepoint_bi_page(
    payload: SharePointPageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Crea (o actualiza) una página en SharePoint Online con el dashboard BI incrustado.

    Usa la Graph Pages API (`POST /sites/{siteId}/pages`).
    Requiere permisos Graph: `Sites.ReadWrite.All`.

    El `site_id` tiene formato Graph:
    `{hostname},{siteId},{webId}` — p.ej. `contoso.sharepoint.com,abc-123,def-456`
    o simplemente el GUID del site si el tenant está configurado.
    """
    org_id = str(current_user.organization_id or "global")
    user_id = str(current_user.id)
    return svc.create_sharepoint_page_with_bi(
        db,
        site_id=payload.site_id,
        page_title=payload.page_title,
        dashboard_id=payload.dashboard_id,
        org_id=org_id,
        user_id=user_id,
        ttl_minutes=payload.ttl_minutes,
    )


# ── Excel export ──────────────────────────────────────────────────────────────

@router.get(
    "/m365/bi/export/excel",
    summary="Exportar dashboard BI a Excel (.xlsx)",
    response_class=StreamingResponse,
)
def export_excel(
    dashboard_id: str = Query("executive", min_length=1, max_length=120),
    include_forecast: bool = Query(True),
    include_anomalies: bool = Query(True),
    include_overrun: bool = Query(True),
    upload_to_onedrive: bool = Query(False, description="Si True, sube el archivo a OneDrive del usuario"),
    user_upn: Optional[str] = Query(None, description="UPN del usuario en OneDrive (requerido si upload_to_onedrive=True)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Genera un workbook Excel con:
    - Hoja *Resumen*: histórico de revenue/coste/horas
    - Hoja *Forecast*: predicción de revenue mes a mes
    - Hoja *Anomalías*: meses atípicos detectados
    - Hoja *Overrun Predicciones*: proyectos en riesgo

    Si `upload_to_onedrive=True` sube el archivo a OneDrive y devuelve la URL
    de descarga en lugar del binario.
    """
    org_id = str(current_user.organization_id or "global") if current_user.organization_id else None
    buf = svc.export_dashboard_excel(
        db,
        dashboard_id=dashboard_id,
        org_id=org_id,
        include_forecast=include_forecast,
        include_anomalies=include_anomalies,
        include_overrun=include_overrun,
    )

    if upload_to_onedrive:
        if not user_upn:
            raise HTTPException(400, "user_upn requerido cuando upload_to_onedrive=True")
        file_bytes = buf.read()
        filename = f"contecflow-bi-{dashboard_id}.xlsx"
        return svc.upload_to_onedrive(file_bytes, filename=filename, user_upn=user_upn)

    filename = f"contecflow-bi-{dashboard_id}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Word export ───────────────────────────────────────────────────────────────

@router.get(
    "/m365/bi/export/word",
    summary="Exportar resumen narrativo BI a Word (.rtf)",
    response_class=StreamingResponse,
)
def export_word(
    dashboard_id: str = Query("executive", min_length=1, max_length=120),
    upload_to_onedrive: bool = Query(False),
    user_upn: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Genera un documento RTF (abre nativamente en Word/LibreOffice/Docs) con:
    - KPIs del último mes
    - Resumen narrativo del forecast de revenue
    - Anomalías detectadas
    - Proyectos en riesgo de overrun

    Si `upload_to_onedrive=True` sube el archivo a OneDrive y devuelve la URL.
    """
    org_id = str(current_user.organization_id or "global") if current_user.organization_id else None
    buf = svc.export_dashboard_word(db, dashboard_id=dashboard_id, org_id=org_id)

    if upload_to_onedrive:
        if not user_upn:
            raise HTTPException(400, "user_upn requerido cuando upload_to_onedrive=True")
        file_bytes = buf.read()
        filename = f"contecflow-bi-{dashboard_id}.rtf"
        return svc.upload_to_onedrive(file_bytes, filename=filename, user_upn=user_upn)

    filename = f"contecflow-bi-{dashboard_id}.rtf"
    return StreamingResponse(
        buf,
        media_type="application/rtf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Status ─────────────────────────────────────────────────────────────────────

@router.get(
    "/m365/bi/status",
    summary="Estado de la integración M365 BI Embed",
)
def m365_bi_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Devuelve qué capacidades están disponibles según la configuración actual."""
    from app.services.m365_service import m365_configured
    from app.core.config import settings as _s
    from app.services.m365_bi_embed_service import _frontend_base

    graph_ok = m365_configured()
    webhook_ok = bool(_s.TEAMS_WEBHOOK_URL)
    sp_site = getattr(_s, "SHAREPOINT_SITE_ID", None)
    frontend = _frontend_base(db, getattr(current_user, "organization_id", None))

    return APIResponse.ok(data={
        "graph_configured": graph_ok,
        "teams_webhook_configured": webhook_ok,
        "sharepoint_site_id_configured": bool(sp_site),
        "sharepoint_site_id": sp_site or None,
        "frontend_embed_base_url": frontend,
        "capabilities": {
            "teams_tab": True,
            "teams_card_graph": graph_ok,
            "teams_card_webhook": webhook_ok,
            "sharepoint_webpart_config": True,
            "sharepoint_page_creation": graph_ok,
            "excel_export": True,
            "word_export": True,
            "onedrive_upload": graph_ok,
        },
    })
