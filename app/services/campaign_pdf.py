"""Generación del PDF del dashboard 360° de una campaña.

Toma el resultado de `aggregate_campaign(...)` y produce un PDF formateado
con resumen, comparativa por pregunta y comentarios cualitativos respetando
el umbral de anonimización.
"""
from __future__ import annotations
import io
import logging
from datetime import datetime

from reportlab.lib import colors

logger = logging.getLogger(__name__)
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak,
)

ACCENT    = colors.HexColor("#00d4ff")
SUCCESS   = colors.HexColor("#00e5a0")
WARNING   = colors.HexColor("#f59e0b")
TEXT_MAIN = colors.HexColor("#1a1a2e")
TEXT_GREY = colors.HexColor("#6b7280")
HEADER_BG = colors.HexColor("#0f172a")
ROW_ALT   = colors.HexColor("#f8fafc")
MUTED_BG  = colors.HexColor("#fef3c7")  # bg suave para anonimizados


def _is_rating(kind: str) -> bool:
    return kind in ("rating_5", "rating_10", "scale_likert")


def generate_campaign_pdf(dashboard: dict) -> bytes:
    """Recibe el dict producido por `aggregate_campaign` y genera el PDF."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title=f"Evaluación 360° — {dashboard['campaign'].get('subject_name', '')}",
    )
    styles = getSampleStyleSheet()
    style_title = ParagraphStyle("T", parent=styles["Title"],
        fontSize=22, fontName="Helvetica-Bold", textColor=TEXT_MAIN,
        spaceAfter=4, leading=28)
    style_h2 = ParagraphStyle("H2", parent=styles["Heading2"],
        fontSize=13, fontName="Helvetica-Bold", textColor=ACCENT,
        spaceBefore=12, spaceAfter=6)
    style_meta = ParagraphStyle("M", parent=styles["Normal"],
        fontSize=9, textColor=TEXT_GREY, spaceAfter=2)
    style_body = ParagraphStyle("B", parent=styles["Normal"],
        fontSize=10, textColor=TEXT_MAIN, leading=14)
    style_quote = ParagraphStyle("Q", parent=styles["Normal"],
        fontSize=9, textColor=TEXT_MAIN, leading=12,
        leftIndent=14, spaceAfter=4)

    elements = []
    camp = dashboard["campaign"]
    questions = dashboard["questions"]
    groups = dashboard["groups"]
    threshold = dashboard.get("anonymity_threshold", 3)

    # ── Cabecera ────────────────────────────────────────────────────────────
    elements.append(Paragraph(
        f"Evaluación 360° — {camp.get('subject_name', '')}", style_title,
    ))
    elements.append(Paragraph(
        f"Generado el {datetime.now().strftime('%Y-%m-%d %H:%M')}<br/>"
        f"Estado: <b>{camp.get('status')}</b> · "
        f"Respuestas: <b>{dashboard['total_submitted']}/{dashboard['total_assigned']}</b> · "
        f"Umbral de anonimización: <b>{threshold}</b>",
        style_meta,
    ))
    elements.append(HRFlowable(width="100%", color=ACCENT, thickness=1.5,
                               spaceBefore=8, spaceAfter=12))

    # ── Resumen por grupo ───────────────────────────────────────────────────
    elements.append(Paragraph("Resumen por grupo de evaluadores", style_h2))
    group_rows = [["Grupo", "Respuestas", "Anonimizado"]]
    label_map = {"self": "Self", "manager": "Manager", "peer": "Pares", "upward": "Upward"}
    for gtype in ("self", "manager", "peer", "upward"):
        g = groups.get(gtype, {"count": 0, "anonymized": False})
        group_rows.append([
            label_map[gtype], str(g.get("count", 0)),
            "Sí" if g.get("anonymized") else "No",
        ])
    t = Table(group_rows, colWidths=[6*cm, 4*cm, 4*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 9),
        ("ALIGN",      (1, 0), (-1, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW_ALT]),
        ("GRID",       (0, 0), (-1, -1), 0.25, TEXT_GREY),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(t)

    # ── Comparativa por pregunta de rating ──────────────────────────────────
    rating_qs = [q for q in questions if _is_rating(q["kind"])]
    if rating_qs:
        elements.append(Paragraph("Comparativa por pregunta", style_h2))
        cmp = dashboard.get("comparison", {})
        rows = [["Pregunta", "Self", "Manager", "Pares", "Upward", "Insight"]]
        for q in rating_qs:
            c = cmp.get(q["key"], {})
            self_v   = c.get("self")
            mgr_v    = c.get("manager")
            peers_v  = c.get("peers")
            up_v     = c.get("upward")
            others = [v for v in (mgr_v, peers_v, up_v) if v is not None]
            insight = "—"
            if self_v is not None and others:
                others_avg = sum(others) / len(others)
                diff = self_v - others_avg
                if diff >= 1:
                    insight = "Punto ciego"
                elif diff <= -1:
                    insight = "Fortaleza no percibida"
                else:
                    insight = "Alineado"
            rows.append([
                Paragraph(q["label"], style_body),
                f"{self_v:.1f}" if self_v   is not None else "—",
                f"{mgr_v:.1f}"  if mgr_v    is not None else "—",
                f"{peers_v:.1f}" if peers_v is not None else "—",
                f"{up_v:.1f}"   if up_v     is not None else "—",
                insight,
            ])
        t = Table(rows, colWidths=[6*cm, 1.5*cm, 1.8*cm, 1.5*cm, 1.8*cm, 4.5*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",   (0, 0), (-1, -1), 8),
            ("ALIGN",      (1, 1), (4, -1), "CENTER"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW_ALT]),
            ("GRID",       (0, 0), (-1, -1), 0.25, TEXT_GREY),
            ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ]))
        elements.append(t)

    # ── Comentarios cualitativos (respetando anonimización) ─────────────────
    text_qs = [q for q in questions if not _is_rating(q["kind"])]
    if text_qs:
        elements.append(PageBreak())
        elements.append(Paragraph("Comentarios cualitativos", style_h2))
        for q in text_qs:
            elements.append(Paragraph(f"<b>{q['label']}</b>", style_body))
            elements.append(Spacer(1, 4))
            for gtype in ("self", "manager", "peer", "upward"):
                g = groups.get(gtype) or {}
                anonymized = g.get("anonymized", False)
                texts = (g.get("text_by_question", {}) or {}).get(q["key"], [])
                # Sólo mostramos algo si hay contenido o queremos marcar el grupo
                if not texts and not anonymized:
                    continue
                label = label_map.get(gtype, gtype)
                if anonymized:
                    elements.append(Paragraph(
                        f"<i>{label}: oculto por anonimización (n={g.get('count', 0)} &lt; {threshold})</i>",
                        style_meta,
                    ))
                else:
                    elements.append(Paragraph(f"<b>{label}:</b>", style_meta))
                    for it in texts:
                        elements.append(Paragraph(f"• {it.get('text', '')}", style_quote))
            elements.append(Spacer(1, 8))

    elements.append(Spacer(1, 12))
    elements.append(HRFlowable(width="100%", color=TEXT_GREY, thickness=0.5))
    elements.append(Paragraph(
        "Documento confidencial — solo para el subject, su manager y RR.HH.",
        style_meta,
    ))

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()
