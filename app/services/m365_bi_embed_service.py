"""M365 BI Embed Service — cierra el gap vs Power BI en integración Word/Excel/Teams/SharePoint.

Capacidades:
  - Teams Tab: genera configuración de pestaña con embed token + registra via Graph API
  - Teams Adaptive Card: snapshot KPI en card rich directamente en un canal de Teams
  - SharePoint Webpart: config de iframe embed para añadir en cualquier página SP
  - SharePoint Page: crea/actualiza una página SP con BI incrustado via Graph Pages API
  - Excel export: genera .xlsx en memoria con sheets de forecast, anomalías y overrun
  - Word export: genera .docx (via openpyxl-XML) o .rtf con resumen narrativo BI

Todas las llamadas a Graph API son no-bloqueantes cuando se usan funciones async,
y con fallback sync para operaciones de larga duración.
"""
from __future__ import annotations

import io
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.m365_service import (
    GRAPH_BASE,
    get_graph_token_sync,
    graph_post_sync,
    require_m365,
    m365_configured,
)
from app.services import bi_intelligence_service as bi_svc
from app.services.bi_embed_service import create_embed_token

logger = logging.getLogger(__name__)

_FRONTEND_BASE = getattr(settings, "FRONTEND_EMBED_BASE_URL", settings.FRONTEND_URL or "")


# ── Dashboard snapshot ────────────────────────────────────────────────────────

def get_dashboard_snapshot(
    db: Session,
    *,
    organization_id: Optional[str],
    dashboard_id: str = "executive",
) -> dict[str, Any]:
    """Fetch a compact KPI snapshot for *dashboard_id* from BI services.

    Used to populate Teams cards and Word/Excel exports.
    """
    forecast = bi_svc.ml_forecast_revenue(db, organization_id=organization_id, months_ahead=3)
    anomalies = bi_svc.ml_detect_revenue_anomalies(db, organization_id=organization_id, z_threshold=2.0)
    overrun = bi_svc.ml_predict_project_overrun_lgbm(db, organization_id=organization_id)

    history = forecast.get("history") or []
    latest = history[-1] if history else {}

    return {
        "dashboard_id": dashboard_id,
        "organization_id": organization_id,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "latest_month": latest.get("month"),
        "latest_revenue": latest.get("revenue"),
        "latest_cost": latest.get("cost"),
        "latest_hours": latest.get("hours"),
        "forecast_3m": [
            {"month": f["month"], "predicted": f["predicted_revenue"]}
            for f in (forecast.get("forecast") or [])[:3]
        ],
        "anomaly_count": len(anomalies.get("items") or []),
        "anomalies": (anomalies.get("items") or [])[:3],
        "overrun_engine": overrun.get("engine"),
        "overrun_predictions": (overrun.get("predictions") or [])[:5],
    }


# ── Teams Tab ─────────────────────────────────────────────────────────────────

def generate_teams_tab_config(
    db: Session,
    *,
    dashboard_id: str,
    org_id: str,
    user_id: str,
    team_id: Optional[str] = None,
    channel_id: Optional[str] = None,
    ttl_minutes: int = 480,
    register_via_graph: bool = False,
) -> dict[str, Any]:
    """Generate a Teams Tab configuration for embedding a Contecflow BI dashboard.

    If *team_id* and *channel_id* are provided AND *register_via_graph* is True,
    registers the tab in the Teams channel via Graph API.
    Returns the tab configuration manifest + embed URL.
    """
    token_data = create_embed_token(db, org_id, user_id, dashboard_id, ["read"], ttl_minutes)
    embed_token = token_data["token"]
    content_url = (
        f"{_FRONTEND_BASE}/embed/bi?dashboard_id={dashboard_id}"
        f"&token={embed_token}&org={org_id}"
    )
    website_url = f"{_FRONTEND_BASE}/bi/dashboards/{dashboard_id}"
    entity_id = f"contecflow-bi-{org_id}-{dashboard_id}"

    tab_config = {
        "entityId": entity_id,
        "contentUrl": content_url,
        "websiteUrl": website_url,
        "suggestedDisplayName": f"Contecflow BI – {dashboard_id.replace('-', ' ').title()}",
        "removeUrl": None,
    }

    result: dict[str, Any] = {
        "dashboard_id": dashboard_id,
        "embed_token": embed_token,
        "expires_at": token_data["expires_at"],
        "content_url": content_url,
        "website_url": website_url,
        "tab_config": tab_config,
        "graph_registered": False,
    }

    if register_via_graph and team_id and channel_id:
        require_m365()
        try:
            graph_payload = {
                "displayName": tab_config["suggestedDisplayName"],
                "teamsApp@odata.bind": (
                    f"{GRAPH_BASE}/appCatalogs/teamsApps/com.microsoft.teamspace.tab.web"
                ),
                "configuration": {
                    "entityId": entity_id,
                    "contentUrl": content_url,
                    "websiteUrl": website_url,
                    "removeUrl": None,
                },
            }
            tab = graph_post_sync(
                f"/teams/{team_id}/channels/{channel_id}/tabs",
                graph_payload,
            )
            result["graph_registered"] = True
            result["teams_tab_id"] = tab.get("id")
            result["teams_tab_web_url"] = tab.get("webUrl")
        except Exception as exc:
            logger.warning("Teams Tab Graph registration failed: %s", exc)
            result["graph_error"] = str(exc)

    return result


# ── Teams Adaptive Card ───────────────────────────────────────────────────────

def _build_adaptive_card(snapshot: dict[str, Any], dashboard_id: str, deep_link: str) -> dict:
    """Build an Adaptive Card 1.5 with BI KPI data."""
    body: list[dict] = [
        {
            "type": "TextBlock",
            "text": f"📊 Contecflow BI – {dashboard_id.replace('-', ' ').title()}",
            "weight": "Bolder",
            "size": "Medium",
            "wrap": True,
        },
        {
            "type": "TextBlock",
            "text": f"Generado: {snapshot.get('generated_at', '')[:19].replace('T', ' ')} UTC",
            "size": "Small",
            "isSubtle": True,
        },
    ]

    # Latest metrics fact set
    facts = []
    if snapshot.get("latest_month"):
        facts.append({"title": "Mes", "value": snapshot["latest_month"]})
    if snapshot.get("latest_revenue") is not None:
        facts.append({"title": "Revenue", "value": f"{snapshot['latest_revenue']:,.0f}"})
    if snapshot.get("latest_cost") is not None:
        facts.append({"title": "Coste", "value": f"{snapshot['latest_cost']:,.0f}"})
    if snapshot.get("latest_hours") is not None:
        facts.append({"title": "Horas", "value": f"{snapshot['latest_hours']:,.0f}"})
    if snapshot.get("anomaly_count") is not None:
        facts.append({"title": "Anomalías", "value": str(snapshot["anomaly_count"])})
    if facts:
        body.append({"type": "FactSet", "facts": facts})

    # Forecast mini-table
    forecast_3m = snapshot.get("forecast_3m") or []
    if forecast_3m:
        cols = [
            {"type": "Column", "width": "stretch", "items": [{"type": "TextBlock", "text": "**Mes**", "wrap": False}]},
            {"type": "Column", "width": "stretch", "items": [{"type": "TextBlock", "text": "**Previsto**", "wrap": False}]},
        ]
        for row in forecast_3m:
            cols[0]["items"].append({"type": "TextBlock", "text": row.get("month", ""), "size": "Small", "wrap": False})  # type: ignore[attr-defined]
            cols[1]["items"].append({"type": "TextBlock", "text": f"{row.get('predicted', 0):,.0f}", "size": "Small", "wrap": False})  # type: ignore[attr-defined]
        body.append({"type": "ColumnSet", "columns": cols})

    card = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": body,
        "actions": [
            {
                "type": "Action.OpenUrl",
                "title": "Ver dashboard completo",
                "url": deep_link,
            }
        ],
    }
    return card


def post_bi_card_to_teams_channel(
    db: Session,
    *,
    team_id: str,
    channel_id: str,
    dashboard_id: str,
    org_id: str,
    user_id: str,
) -> dict[str, Any]:
    """Post an Adaptive Card with BI KPI data to a Teams channel via Graph API.

    Requires Graph permission: ChannelMessage.Send (application).
    Falls back to incoming webhook (TEAMS_WEBHOOK_URL) if Graph is not available.
    """
    snapshot = get_dashboard_snapshot(db, organization_id=org_id, dashboard_id=dashboard_id)
    deep_link = f"{_FRONTEND_BASE}/bi/dashboards/{dashboard_id}"
    card = _build_adaptive_card(snapshot, dashboard_id, deep_link)

    if m365_configured():
        token = get_graph_token_sync()
        message_payload = {
            "body": {
                "contentType": "html",
                "content": f'<attachment id="bi-card"></attachment>',
            },
            "attachments": [
                {
                    "id": "bi-card",
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "contentUrl": None,
                    "content": json.dumps(card),
                    "name": f"Contecflow BI – {dashboard_id}",
                    "thumbnailUrl": None,
                }
            ],
        }
        try:
            with httpx.Client(timeout=20) as client:
                resp = client.post(
                    f"{GRAPH_BASE}/teams/{team_id}/channels/{channel_id}/messages",
                    json=message_payload,
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                )
            resp.raise_for_status()
            data = resp.json()
            return {
                "channel": "graph",
                "message_id": data.get("id"),
                "etag": data.get("etag"),
                "web_url": data.get("webUrl"),
                "snapshot": snapshot,
            }
        except httpx.HTTPStatusError as exc:
            logger.warning("Graph Teams message failed (%s), falling back to webhook: %s", exc.response.status_code, exc)

    # Webhook fallback (MessageCard format)
    webhook_url = settings.TEAMS_WEBHOOK_URL
    if not webhook_url:
        raise HTTPException(503, "M365 Graph no configurado y TEAMS_WEBHOOK_URL no está definido")

    sections: list[dict] = []
    latest = snapshot.get("latest_month")
    if latest:
        sections.append({
            "activityTitle": f"KPIs – {latest}",
            "facts": [
                {"name": "Revenue", "value": f"{snapshot.get('latest_revenue', 0):,.0f}"},
                {"name": "Coste", "value": f"{snapshot.get('latest_cost', 0):,.0f}"},
                {"name": "Horas", "value": f"{snapshot.get('latest_hours', 0):,.0f}"},
                {"name": "Anomalías", "value": str(snapshot.get("anomaly_count", 0))},
            ],
            "markdown": True,
        })
    card_fallback = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": "0078D4",
        "summary": f"Contecflow BI – {dashboard_id}",
        "sections": sections,
        "potentialAction": [
            {
                "@type": "OpenUri",
                "name": "Ver dashboard",
                "targets": [{"os": "default", "uri": deep_link}],
            }
        ],
    }
    with httpx.Client(timeout=15) as client:
        resp = client.post(webhook_url, json=card_fallback)
    if resp.status_code not in (200, 202):
        raise HTTPException(502, f"Teams webhook error: {resp.text}")

    return {"channel": "webhook", "snapshot": snapshot}


# ── SharePoint webpart config ─────────────────────────────────────────────────

def get_sharepoint_webpart_config(
    db: Session,
    *,
    dashboard_id: str,
    org_id: str,
    user_id: str,
    ttl_minutes: int = 1440,
) -> dict[str, Any]:
    """Return the iframe config block for embedding a BI dashboard in a SharePoint web part.

    The caller pastes the `iframe_html` into a SharePoint Embed web part.
    For automation, use `create_sharepoint_page_with_bi` instead.
    """
    token_data = create_embed_token(db, org_id, user_id, dashboard_id, ["read"], ttl_minutes)
    embed_url = (
        f"{_FRONTEND_BASE}/embed/bi?dashboard_id={dashboard_id}"
        f"&token={token_data['token']}&org={org_id}"
    )
    iframe_html = (
        f'<iframe src="{embed_url}" '
        f'width="100%" height="600" frameborder="0" allowfullscreen '
        f'title="Contecflow BI – {dashboard_id}"></iframe>'
    )
    return {
        "dashboard_id": dashboard_id,
        "embed_url": embed_url,
        "expires_at": token_data["expires_at"],
        "iframe_html": iframe_html,
        "webpart_type": "Embed",
        "instructions": (
            "En SharePoint: Editar página → Añadir web part → Embed → "
            "pegar `iframe_html` en el campo HTML. "
            "Renovar el token antes de `expires_at`."
        ),
    }


def create_sharepoint_page_with_bi(
    db: Session,
    *,
    site_id: str,
    page_title: str,
    dashboard_id: str,
    org_id: str,
    user_id: str,
    ttl_minutes: int = 1440,
) -> dict[str, Any]:
    """Create (or update) a SharePoint page embedding the BI dashboard via Graph Sites API.

    Requires Graph permissions: Sites.ReadWrite.All.
    """
    require_m365()

    embed_cfg = get_sharepoint_webpart_config(
        db,
        dashboard_id=dashboard_id,
        org_id=org_id,
        user_id=user_id,
        ttl_minutes=ttl_minutes,
    )
    embed_url = embed_cfg["embed_url"]

    page_payload = {
        "@odata.type": "#microsoft.graph.sitePage",
        "name": f"contecflow-bi-{dashboard_id}.aspx",
        "title": page_title,
        "pageLayout": "article",
        "canvasLayout": {
            "horizontalSections": [
                {
                    "layout": "oneColumn",
                    "id": "1",
                    "emphasis": "none",
                    "columns": [
                        {
                            "id": "1",
                            "width": 12,
                            "webparts": [
                                {
                                    "id": "d1d91016-032f-456d-98a4-721247c305e8",
                                    "innerHtml": embed_cfg["iframe_html"],
                                }
                            ],
                        }
                    ],
                }
            ]
        },
    }

    token = get_graph_token_sync()
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{GRAPH_BASE}/sites/{site_id}/pages",
                json=page_payload,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
        resp.raise_for_status()
        data = resp.json()
        return {
            "created": True,
            "page_id": data.get("id"),
            "page_name": data.get("name"),
            "web_url": data.get("webUrl"),
            "embed_url": embed_url,
            "expires_at": embed_cfg["expires_at"],
        }
    # intentional: chained re-raise preserves context
    except httpx.HTTPStatusError as exc:
        raise HTTPException(exc.response.status_code, f"Graph Sites API error: {exc.response.text}") from exc


# ── Excel export ──────────────────────────────────────────────────────────────

def export_dashboard_excel(
    db: Session,
    *,
    dashboard_id: str,
    org_id: Optional[str],
    include_forecast: bool = True,
    include_anomalies: bool = True,
    include_overrun: bool = True,
) -> io.BytesIO:
    """Generate an Excel workbook (.xlsx) with BI data for the given dashboard.

    Sheets generated:
      - Summary      — latest KPIs
      - Forecast     — monthly revenue forecast
      - Anomalies    — detected anomaly months
      - Overrun      — project overrun predictions (if available)

    Returns an in-memory BytesIO — caller sends as StreamingResponse.
    """
    try:
        from openpyxl import Workbook  # type: ignore
        from openpyxl.styles import Font, PatternFill, Alignment  # type: ignore
        from openpyxl.utils import get_column_letter  # type: ignore
    except ImportError as exc:
        raise HTTPException(500, "openpyxl no instalado") from exc

    wb = Workbook()
    now_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # ── Header style helpers ──────────────────────────────────────────────────
    HEADER_FONT = Font(bold=True, color="FFFFFF")
    HEADER_FILL = PatternFill("solid", fgColor="0078D4")
    CENTER = Alignment(horizontal="center")

    def _header_row(ws, cols: list[str]) -> None:
        ws.append(cols)
        for cell in ws[ws.max_row]:
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
            cell.alignment = CENTER

    def _autofit(ws) -> None:
        for col_cells in ws.columns:
            length = max((len(str(c.value or "")) for c in col_cells), default=8)
            ws.column_dimensions[get_column_letter(col_cells[0].column)].width = min(length + 4, 40)

    # ── Summary sheet ─────────────────────────────────────────────────────────
    ws_sum = wb.active
    ws_sum.title = "Resumen"
    ws_sum.append(["Contecflow BI – Dashboard Export"])
    ws_sum["A1"].font = Font(bold=True, size=14)
    ws_sum.append([f"Dashboard: {dashboard_id}"])
    ws_sum.append([f"Organización: {org_id or 'global'}"])
    ws_sum.append([f"Generado: {now_str}"])
    ws_sum.append([])

    forecast_data = bi_svc.ml_forecast_revenue(db, organization_id=org_id, months_ahead=6)
    history = forecast_data.get("history") or []

    _header_row(ws_sum, ["Mes", "Revenue", "Coste", "Horas"])
    for row in history:
        ws_sum.append([row.get("month"), row.get("revenue"), row.get("cost"), row.get("hours")])
    _autofit(ws_sum)

    # ── Forecast sheet ────────────────────────────────────────────────────────
    if include_forecast:
        ws_fc = wb.create_sheet("Forecast")
        _header_row(ws_fc, ["Mes", "Revenue Previsto", "Banda Inferior", "Banda Superior"])
        for row in forecast_data.get("forecast") or []:
            ws_fc.append([
                row.get("month"),
                row.get("predicted_revenue"),
                row.get("lower_bound"),
                row.get("upper_bound"),
            ])
        _autofit(ws_fc)

    # ── Anomalies sheet ───────────────────────────────────────────────────────
    if include_anomalies:
        ws_an = wb.create_sheet("Anomalías")
        anomaly_data = bi_svc.ml_detect_revenue_anomalies(db, organization_id=org_id, z_threshold=2.0)
        _header_row(ws_an, ["Mes", "Revenue", "Z-Score", "Dirección", "Severidad"])
        for item in anomaly_data.get("items") or []:
            ws_an.append([
                item.get("month"),
                item.get("revenue"),
                item.get("z_score"),
                item.get("direction"),
                item.get("severity"),
            ])
        _autofit(ws_an)

    # ── Overrun sheet ─────────────────────────────────────────────────────────
    if include_overrun:
        ws_ov = wb.create_sheet("Overrun Predicciones")
        overrun_data = bi_svc.ml_predict_project_overrun_lgbm(db, organization_id=org_id)
        _header_row(ws_ov, ["Proyecto", "Probabilidad Overrun", "Nivel Riesgo"])
        for pred in (overrun_data.get("predictions") or []):
            ws_ov.append([
                pred.get("project_name") or pred.get("project_id"),
                pred.get("overrun_probability"),
                pred.get("risk_level"),
            ])
        if not (overrun_data.get("predictions") or []):
            ws_ov.append(["(sin datos de proyectos suficientes)", None, None])
        _autofit(ws_ov)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# ── Word (RTF) export ─────────────────────────────────────────────────────────

def _rtf_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
            .replace("{", "\\{")
            .replace("}", "\\}")
    )


def export_dashboard_word(
    db: Session,
    *,
    dashboard_id: str,
    org_id: Optional[str],
) -> io.BytesIO:
    """Generate a Word-compatible RTF document with a BI dashboard narrative summary.

    Uses RTF format (no external deps required). Word, LibreOffice and
    Google Docs can all open .rtf natively.
    """
    now_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    snapshot = get_dashboard_snapshot(db, organization_id=org_id, dashboard_id=dashboard_id)

    lines: list[str] = []

    def h1(text: str) -> None:
        lines.append(rf"{{\pard\sb360\sa120\b\fs32 {_rtf_escape(text)}\par}}")

    def h2(text: str) -> None:
        lines.append(rf"{{\pard\sb240\sa80\b\fs28 {_rtf_escape(text)}\par}}")

    def p(text: str) -> None:
        lines.append(rf"{{\pard\sb80\sa80\fs24 {_rtf_escape(text)}\par}}")

    def kv(key: str, value: str) -> None:
        lines.append(rf"{{\pard\sb40\sa40\fs24 {{\b {_rtf_escape(key)}:}} {_rtf_escape(value)}\par}}")

    h1(f"Contecflow BI – {dashboard_id.replace('-', ' ').title()}")
    p(f"Generado: {now_str}")
    if org_id:
        p(f"Organización: {org_id}")

    h2("KPIs Actuales")
    if snapshot.get("latest_month"):
        kv("Mes", snapshot["latest_month"])
    if snapshot.get("latest_revenue") is not None:
        kv("Revenue", f"{snapshot['latest_revenue']:,.2f}")
    if snapshot.get("latest_cost") is not None:
        kv("Coste", f"{snapshot['latest_cost']:,.2f}")
    if snapshot.get("latest_hours") is not None:
        kv("Horas", f"{snapshot['latest_hours']:,.0f}")

    h2("Forecast Revenue (próximos 3 meses)")
    for row in snapshot.get("forecast_3m") or []:
        kv(row.get("month", ""), f"{row.get('predicted', 0):,.2f}")

    h2("Anomalías Detectadas")
    anomalies = snapshot.get("anomalies") or []
    if anomalies:
        for an in anomalies:
            p(
                f"{an.get('month')} – Revenue: {an.get('revenue', 0):,.0f} "
                f"(Z={an.get('z_score', 0):.2f}, {an.get('direction', '')}, {an.get('severity', '')})"
            )
    else:
        p("No se detectaron anomalías en el período analizado.")

    h2("Proyectos en Riesgo de Overrun")
    overruns = snapshot.get("overrun_predictions") or []
    if overruns:
        for ov in overruns:
            name = ov.get("project_name") or ov.get("project_id") or "–"
            prob = ov.get("overrun_probability") or 0
            risk = ov.get("risk_level") or "–"
            p(f"{name}: {prob:.0%} probabilidad de overrun ({risk})")
    else:
        p("Sin predicciones de overrun disponibles.")

    rtf_body = "\n".join(lines)
    rtf_content = (
        r"{\rtf1\ansi\deff0"
        r"{\fonttbl{\f0\froman\fcharset0 Times New Roman;}{\f1\fswiss\fcharset0 Calibri;}}"
        r"{\colortbl;\red0\green0\blue0;\red0\green120\blue212;}"
        r"\f1\widowctrl\hyphauto"
        "\n"
        + rtf_body
        + "\n}"
    )

    buf = io.BytesIO(rtf_content.encode("latin-1", errors="replace"))
    buf.seek(0)
    return buf


# ── OneDrive upload helper ────────────────────────────────────────────────────

def upload_to_onedrive(
    file_bytes: bytes,
    *,
    filename: str,
    user_upn: Optional[str] = None,
    folder_path: str = "Contecflow BI Exports",
) -> dict[str, Any]:
    """Upload *file_bytes* to the user's OneDrive via Graph API.

    Returns the drive item with webUrl for sharing.
    Requires Files.ReadWrite.All (app) or Files.ReadWrite (delegated).
    """
    require_m365()
    token = get_graph_token_sync()
    # Use /me/drive for delegated or /users/{upn}/drive for app-only
    drive_base = f"/users/{user_upn}/drive" if user_upn else "/me/drive"
    upload_path = f"{drive_base}/root:/{folder_path}/{filename}:/content"

    with httpx.Client(timeout=60) as client:
        resp = client.put(
            f"{GRAPH_BASE}{upload_path}",
            content=file_bytes,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/octet-stream",
            },
        )
    if resp.status_code not in (200, 201):
        raise HTTPException(resp.status_code, f"OneDrive upload error: {resp.text}")
    data = resp.json()
    return {
        "item_id": data.get("id"),
        "web_url": data.get("webUrl"),
        "name": data.get("name"),
        "size": data.get("size"),
    }
