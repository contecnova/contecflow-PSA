"""report_pdf_service.py — Generación de PDFs BI con datos OLAP.

Tipos de informe:
  executive_summary  — KPIs top-level + narrativa IA
  utilization        — utilización por usuario
  pipeline           — funnel de pipeline comercial
  portfolio          — salud del portfolio de proyectos
  custom             — métrica analytics clásica (compatibilidad con report_pdf.py)

Punto de entrada:
  build_report_pdf(report, db) -> bytes
"""
from __future__ import annotations

import io
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ── ReportLab palette ─────────────────────────────────────────────────────────
try:
    from reportlab.lib import colors as _rl_colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable,
    )
    _REPORTLAB = True
except ImportError:
    _REPORTLAB = False
    logger.warning("reportlab not installed — PDF generation will return placeholder bytes")

# Auditoria 2026-08 (hallazgo 32). Estos nueve colores eran una CUARTA paleta
# divergente del repo, ademas de las tres que la auditoria ya habia contado — y
# este generador produce los informes programados que se envian POR CORREO al
# cliente final, asi que salian con los colores de la plataforma aunque el
# cliente tuviera marca propia.
#
# Los tres que llevan marca —acento, fondo de cabecera y el texto sobre ese
# fondo— vienen ahora de la marca de la organizacion y viajan dentro del
# diccionario `styles`, que TODOS los ayudantes reciben ya: asi no hace falta
# pasar la paleta por catorce firmas.
#
# Los neutros y los de ESTADO se quedan aqui, y por dos razones distintas: los
# grises de este documento difieren en un pelo de los de la paleta compartida
# (`#1e293b` frente a `#1a1a2e`) y unificarlos cambiaria el aspecto de un
# documento que se manda al cliente; y `SUCCESS`, `WARNING` y `DANGER` son
# estado, no marca — un aviso pintado con el color de marca deja de leerse como
# aviso.
ACCENT    = "#4f8ef7"
SUCCESS   = "#22c55e"
WARNING   = "#f59e0b"
DANGER    = "#ef4444"
TEXT_MAIN = "#1e293b"
TEXT_GREY = "#64748b"
ROW_ALT   = "#f8fafc"
ROW_EVEN  = "#ffffff"


def _rl(hex_color: str):
    return _rl_colors.HexColor(hex_color)


# ── Data fetchers ─────────────────────────────────────────────────────────────

def _fetch_executive_data(org_id: Optional[str]) -> dict:
    try:
        from app.services.olap.query_engine import get_kpi_summary
        return get_kpi_summary(org_id)
    except Exception as exc:
        logger.warning("executive data fetch failed: %s", exc)
        return {}


def _fetch_utilization_data(org_id: Optional[str]) -> list:
    try:
        from app.services.olap.query_engine import get_utilization_by_user
        return get_utilization_by_user(org_id)
    except Exception as exc:
        logger.warning("utilization data fetch failed: %s", exc)
        return []


def _fetch_pipeline_data(org_id: Optional[str]) -> list:
    try:
        from app.services.olap.query_engine import get_pipeline_funnel
        return get_pipeline_funnel(org_id)
    except Exception as exc:
        logger.warning("pipeline data fetch failed: %s", exc)
        return []


def _fetch_portfolio_data(org_id: Optional[str]) -> list:
    try:
        from app.services.olap.query_engine import get_portfolio_health
        return get_portfolio_health(org_id)
    except Exception as exc:
        logger.warning("portfolio data fetch failed: %s", exc)
        return []


def _fetch_narrative(org_id: Optional[str], lang: Optional[str] = None) -> str:
    try:
        from app.services.bi_storytelling import generate_narrative
        result = generate_narrative(org_id=org_id, lang=lang)
        return result.get("narrative", "")
    except Exception as exc:
        logger.warning("narrative fetch failed: %s", exc)
        return ""


# ── PDF builders ──────────────────────────────────────────────────────────────

def _make_doc(buffer) -> "SimpleDocTemplate":
    return SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.8 * cm, rightMargin=1.8 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
    )


def _make_styles(paleta=None):
    """Los estilos del informe.

    Las tres claves con guion bajo son los colores de marca de la organizacion;
    van aqui porque `styles` ya llega a todos los ayudantes.
    """
    from app.services._pdf_marca import PALETA_POR_DEFECTO

    p = paleta or PALETA_POR_DEFECTO
    styles = getSampleStyleSheet()
    return {
        "_acento": _rl(p.acento),
        "_cabecera_fondo": _rl(p.fondo_de_cabecera),
        "_cabecera_texto": _rl(p.texto_sobre_cabecera),
        "title": ParagraphStyle(
            "RPTitle", parent=styles["Title"],
            fontSize=20, fontName="Helvetica-Bold",
            textColor=_rl(TEXT_MAIN), spaceAfter=4, leading=26,
        ),
        "subtitle": ParagraphStyle(
            "RPSub", parent=styles["Normal"],
            fontSize=10, textColor=_rl(TEXT_GREY), spaceAfter=2,
        ),
        "section": ParagraphStyle(
            "RPSection", parent=styles["Normal"],
            fontSize=12, fontName="Helvetica-Bold",
            textColor=_rl(p.acento), spaceBefore=16, spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "RPBody", parent=styles["Normal"],
            fontSize=9, textColor=_rl(TEXT_MAIN), leading=14,
        ),
        "narrative": ParagraphStyle(
            "RPNarrative", parent=styles["Normal"],
            fontSize=9, textColor=_rl(TEXT_MAIN), leading=15,
            leftIndent=8, rightIndent=8,
        ),
        "caption": ParagraphStyle(
            "RPCaption", parent=styles["Normal"],
            fontSize=8, textColor=_rl(TEXT_GREY),
        ),
    }


def _header_block(title: str, subtitle: str, styles: dict) -> list:
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    return [
        Paragraph(title, styles["title"]),
        Paragraph(f"{subtitle} · Generado: {now_str}", styles["subtitle"]),
        HRFlowable(width="100%", thickness=1.5, color=styles["_acento"],
                   spaceAfter=12),
    ]


def _kpi_table(kpis: dict, styles: dict, simbolo: Optional[str] = None) -> list:
    from app.services.formato_regional import formatear_importe, simbolo_de_moneda
    simbolo = simbolo or simbolo_de_moneda()

    def _fmt(v, suffix=""):
        if v is None:
            return "—"
        if isinstance(v, float):
            return f"{v:,.1f}{suffix}"
        return f"{v}{suffix}"

    rows = [
        ["KPI", "Valor"],
        ["Proyectos activos", _fmt(kpis.get("active_projects"))],
        ["Horas imputadas (mes)", _fmt(kpis.get("hours_mtd"), "h")],
        ["Coste mes", formatear_importe(kpis.get('cost_mtd') or 0, simbolo)],
        ["Facturabilidad", _fmt(kpis.get("billability_pct"), "%")],
        ["Pipeline ponderado", formatear_importe(kpis.get('pipeline_weighted') or 0, simbolo)],
        ["Oportunidades abiertas", _fmt(kpis.get("open_opps"))],
        ["Revenue ganado (YTD)", formatear_importe(kpis.get('won_revenue') or 0, simbolo)],
        ["Margen medio (%)", _fmt(kpis.get("avg_margin_pct"), "%")],
        ["Proyectos riesgo alto", _fmt(kpis.get("high_risk_projects"))],
    ]
    tbl = Table(rows, colWidths=[9 * cm, 6 * cm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), styles["_cabecera_fondo"]),
        ("TEXTCOLOR", (0, 0), (-1, 0), styles["_cabecera_texto"]),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_rl(ROW_EVEN), _rl(ROW_ALT)]),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("TEXTCOLOR", (0, 1), (0, -1), _rl(TEXT_GREY)),
        ("TEXTCOLOR", (1, 1), (1, -1), _rl(TEXT_MAIN)),
        ("FONTNAME", (1, 1), (1, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, _rl_colors.lightgrey),
        ("ROWPADDING", (0, 0), (-1, -1), 5),
    ]))
    return [Paragraph("KPIs del período", styles["section"]), tbl]


def _utilization_table(rows_data: list, styles: dict) -> list:
    if not rows_data:
        return [Paragraph("Sin datos de utilización en OLAP.", styles["body"])]

    header = ["Usuario", "Departamento", "Horas", "Capacidad", "Utilización %"]
    rows = [header]
    for r in rows_data[:30]:
        util = r.get("utilization_pct") or 0
        rows.append([
            r.get("full_name", "—"),
            r.get("department") or "—",
            f"{r.get('logged_hours', 0):.1f}h",
            f"{r.get('monthly_capacity', 0):.1f}h",
            f"{util:.1f}%",
        ])

    col_w = [5 * cm, 3.5 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm]
    tbl = Table(rows, colWidths=col_w)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), styles["_cabecera_fondo"]),
        ("TEXTCOLOR", (0, 0), (-1, 0), styles["_cabecera_texto"]),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_rl(ROW_EVEN), _rl(ROW_ALT)]),
        ("GRID", (0, 0), (-1, -1), 0.4, _rl_colors.lightgrey),
        ("ROWPADDING", (0, 0), (-1, -1), 4),
        ("ALIGN", (2, 0), (-1, -1), "CENTER"),
    ]))
    return [Paragraph("Utilización por usuario", styles["section"]), tbl]


def _pipeline_table(rows_data: list, styles: dict, simbolo: Optional[str] = None) -> list:
    from app.services.formato_regional import formatear_importe, simbolo_de_moneda
    simbolo = simbolo or simbolo_de_moneda()
    if not rows_data:
        return [Paragraph("Sin datos de pipeline en OLAP.", styles["body"])]

    header = ["Etapa", "Oportunidades", "Revenue esperado", "Revenue ponderado", "Prob. media", "Días medios"]
    rows = [header]
    for r in rows_data:
        rows.append([
            r.get("stage", "—").capitalize(),
            str(r.get("count", 0)),
            formatear_importe(r.get('total_revenue') or 0, simbolo),
            formatear_importe(r.get('weighted_revenue') or 0, simbolo),
            f"{r.get('avg_probability', 0):.1f}%",
            str(r.get("avg_days") or "—"),
        ])

    col_w = [2.8 * cm, 2.5 * cm, 3.2 * cm, 3.2 * cm, 2.2 * cm, 2.1 * cm]
    tbl = Table(rows, colWidths=col_w)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), styles["_cabecera_fondo"]),
        ("TEXTCOLOR", (0, 0), (-1, 0), styles["_cabecera_texto"]),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_rl(ROW_EVEN), _rl(ROW_ALT)]),
        ("GRID", (0, 0), (-1, -1), 0.4, _rl_colors.lightgrey),
        ("ROWPADDING", (0, 0), (-1, -1), 4),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
    ]))
    return [Paragraph("Funnel de pipeline", styles["section"]), tbl]


def _portfolio_table(rows_data: list, styles: dict) -> list:
    if not rows_data:
        return [Paragraph("Sin datos de portfolio en OLAP.", styles["body"])]

    header = ["Proyecto", "Estado", "Margen %", "Completado %", "Riesgo"]
    rows = [header]
    for r in rows_data[:20]:
        rows.append([
            f"{r.get('code', '')} {r.get('name', '—')}"[:40],
            (r.get("status") or "—").capitalize(),
            f"{r.get('margin_pct', 0):.1f}%",
            f"{r.get('completion_pct', 0):.1f}%",
            (r.get("risk_level") or "—").capitalize(),
        ])

    col_w = [6.5 * cm, 2.5 * cm, 2.2 * cm, 2.8 * cm, 2 * cm]
    tbl = Table(rows, colWidths=col_w)

    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), styles["_cabecera_fondo"]),
        ("TEXTCOLOR", (0, 0), (-1, 0), styles["_cabecera_texto"]),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_rl(ROW_EVEN), _rl(ROW_ALT)]),
        ("GRID", (0, 0), (-1, -1), 0.4, _rl_colors.lightgrey),
        ("ROWPADDING", (0, 0), (-1, -1), 4),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
    ]
    # Color margin_pct column
    for i, r in enumerate(rows_data[:20], start=1):
        pct = r.get("margin_pct", 0) or 0
        color = SUCCESS if pct >= 25 else (WARNING if pct >= 10 else DANGER)
        style_cmds.append(("TEXTCOLOR", (2, i), (2, i), _rl(color)))
        style_cmds.append(("FONTNAME", (2, i), (2, i), "Helvetica-Bold"))

    tbl.setStyle(TableStyle(style_cmds))
    return [Paragraph("Salud del portfolio", styles["section"]), tbl]


def _narrative_block(narrative_text: str, styles: dict) -> list:
    if not narrative_text:
        return []
    # Strip markdown bold markers for plain PDF text
    import re
    clean = re.sub(r"\*\*(.+?)\*\*", r"\1", narrative_text)
    clean = re.sub(r"\*(.+?)\*", r"\1", clean)
    paragraphs = [p.strip() for p in clean.split("\n\n") if p.strip()]
    elements = [Paragraph("Resumen ejecutivo IA", styles["section"])]
    for p in paragraphs:
        elements.append(Paragraph(p.replace("\n", "<br/>"), styles["narrative"]))
        elements.append(Spacer(1, 4))
    return elements


# ── Main entry point ──────────────────────────────────────────────────────────

def datos_de_la_metrica(report, db, org_id) -> tuple:
    """(filas, resumen, filtros) de la métrica del informe, como en /analytics/query.

    El periodo sale de `filters_json` (`date_from`, `date_to`) o, sin él, el
    mismo por defecto que la pantalla; `top_n`, el mismo también (20).
    """
    import json
    from app.services.analytics_service import parse_date_range
    from app.services.metrics import METRICS_REGISTRY
    try:
        filtros = json.loads(getattr(report, "filters_json", "{}") or "{}")
    except ValueError:
        filtros = {}
    manejador = METRICS_REGISTRY.get(report.metric or "")
    if manejador is None:
        raise ValueError(f"Métrica desconocida: {report.metric}")
    d_from, d_to = parse_date_range(filtros.get("date_from"), filtros.get("date_to"))
    resultado = manejador(db=db, d_from=d_from, d_to=d_to, top_n=int(filtros.get("top_n") or 20),
                          project_id=filtros.get("project_id"), department=filtros.get("department"),
                          project_ids=None, user_id=None, client_id=filtros.get("client_id"),
                          group_by=filtros.get("group_by"), organization_id=org_id)
    filas = resultado[0] if isinstance(resultado, tuple) else resultado
    filas = list(filas or [])
    valores = [f.get("value") for f in filas if isinstance(f.get("value"), (int, float))]
    resumen = {"Periodo": f"{d_from} — {d_to}", "Filas": len(filas)}
    if valores:
        resumen["Total"] = round(sum(valores), 2)
    return filas, resumen, {**filtros, "date_from": str(d_from), "date_to": str(d_to)}


def build_report_pdf(report, db, org_id: Optional[str] = None) -> bytes:
    """Generate a BI PDF for the given ScheduledReport row.

    Falls back to the legacy report_pdf.generate_report_pdf for 'custom' type
    when OLAP is unavailable.
    """
    if not _REPORTLAB:
        # Never hand back a corrupt 1-byte "PDF"; fail loudly so the caller
        # surfaces a real error instead of delivering an unreadable file.
        raise RuntimeError(
            "PDF generation requires the 'reportlab' package, which is not installed."
        )

    report_type = getattr(report, "report_type", None) or "custom"
    include_narrative = getattr(report, "include_narrative", False)

    # La marca del tenant. `org_id` ya estaba en la firma —se usaba solo para
    # traer los datos— asi que no hace falta cambiarla. Auditoria 2026-08, #32.
    from app.services._pdf_marca import PALETA_POR_DEFECTO, marca_de_organizacion
    marca = marca_de_organizacion(db, org_id, base=PALETA_POR_DEFECTO)

    buffer = io.BytesIO()
    doc = _make_doc(buffer)
    styles = _make_styles(marca.paleta)
    from app.services.formato_regional import simbolo_de_moneda
    simbolo = simbolo_de_moneda(db, org_id)
    story = []

    # ── Header ────────────────────────────────────────────────────────────────
    type_labels = {
        "executive_summary": "Resumen Ejecutivo",
        "utilization": "Informe de Utilización",
        "pipeline": "Informe de Pipeline Comercial",
        "portfolio": "Informe de Portfolio de Proyectos",
        "custom": "Informe Personalizado",
    }
    subtitle = type_labels.get(report_type, "Informe")
    story += _header_block(report.name, subtitle, styles)

    # ── Narrative (optional, any report type) ─────────────────────────────────
    if include_narrative:
        narrative = _fetch_narrative(org_id)
        story += _narrative_block(narrative, styles)
        story.append(Spacer(1, 8))

    # ── Content by type ───────────────────────────────────────────────────────
    if report_type == "executive_summary":
        kpis = _fetch_executive_data(org_id)
        story += _kpi_table(kpis, styles, simbolo)
        story.append(Spacer(1, 12))
        pipeline_data = _fetch_pipeline_data(org_id)
        story += _pipeline_table(pipeline_data, styles, simbolo)

    elif report_type == "utilization":
        util_data = _fetch_utilization_data(org_id)
        story += _utilization_table(util_data, styles)

    elif report_type == "pipeline":
        pipeline_data = _fetch_pipeline_data(org_id)
        story += _pipeline_table(pipeline_data, styles, simbolo)

    elif report_type == "portfolio":
        portfolio_data = _fetch_portfolio_data(org_id)
        story += _portfolio_table(portfolio_data, styles)

    else:
        # Una métrica de la pantalla de Informes. Revisión 2026-11: se llamaba
        # al generador con `data=[]` y el PDF salía siempre vacío; ahora la
        # métrica se calcula con el mismo registro que usa la pantalla.
        from app.services.report_pdf import generate_report_pdf as _legacy_pdf
        filas, resumen, filtros = datos_de_la_metrica(report, db, org_id)
        return _legacy_pdf(
            paleta=marca.paleta,
            title=report.name,
            metric_label=(report.metric or "custom").replace("_", " ").title(),
            data=filas,
            summary=resumen,
            filters=filtros,
        )

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=_rl(_rl_colors.lightgrey.hexval())))
    story.append(Paragraph(
        f"Generado automáticamente por ContecFlow · {datetime.now().strftime('%d/%m/%Y %H:%M UTC')}",
        styles["caption"],
    ))

    doc.build(story)
    return buffer.getvalue()
