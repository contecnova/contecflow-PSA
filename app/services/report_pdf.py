"""
report_pdf.py — Generación de PDF de informes con ReportLab
"""
import io
from datetime import datetime
from typing import List, Dict, Any, Optional


def generate_report_pdf(
    title: str,
    metric_label: str,
    data: List[Dict[str, Any]],
    summary: Optional[Dict] = None,
    filters: Optional[Dict] = None,
    generated_by: str = "Clarive",
) -> bytes:
    """
    Genera un PDF de informe y devuelve los bytes.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable
    )
    from reportlab.lib.enums import TA_LEFT, TA_CENTER

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )

    # ── Paleta de colores Clarive ──────────────────────────────────────────────
    ACCENT    = colors.HexColor("#00d4ff")
    SUCCESS   = colors.HexColor("#00e5a0")  # noqa: F841
    TEXT_MAIN = colors.HexColor("#1a1a2e")
    TEXT_GREY = colors.HexColor("#6b7280")
    HEADER_BG = colors.HexColor("#0f172a")
    ROW_ALT   = colors.HexColor("#f8fafc")

    styles = getSampleStyleSheet()

    style_title = ParagraphStyle(
        "NexusTitle",
        parent=styles["Title"],
        fontSize=22, fontName="Helvetica-Bold",
        textColor=TEXT_MAIN, spaceAfter=4, leading=28,
    )
    style_subtitle = ParagraphStyle(
        "NexusSubtitle",
        parent=styles["Normal"],
        fontSize=11, fontName="Helvetica",
        textColor=TEXT_GREY, spaceAfter=2,
    )
    style_section = ParagraphStyle(
        "NexusSection",
        parent=styles["Heading2"],
        fontSize=13, fontName="Helvetica-Bold",
        textColor=TEXT_MAIN, spaceBefore=16, spaceAfter=8,
        borderPad=4,
    )
    style_body = ParagraphStyle(
        "NexusBody",
        parent=styles["Normal"],
        fontSize=10, fontName="Helvetica",
        textColor=TEXT_MAIN, spaceAfter=4, leading=15,
    )
    style_small = ParagraphStyle(
        "NexusSmall",
        parent=styles["Normal"],
        fontSize=8, fontName="Helvetica",
        textColor=TEXT_GREY,
    )

    elements = []

    # ── Header ─────────────────────────────────────────────────────────────────
    elements.append(Paragraph("Clarive", ParagraphStyle(
        "Brand", parent=styles["Normal"],
        fontSize=14, fontName="Helvetica-Bold",
        textColor=ACCENT, spaceAfter=2,
    )))
    elements.append(Paragraph(title, style_title))
    elements.append(Paragraph(metric_label, style_subtitle))
    elements.append(Paragraph(
        f"Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} · {generated_by}",
        style_small
    ))
    elements.append(HRFlowable(width="100%", thickness=1, color=ACCENT, spaceAfter=16))

    # ── Filtros aplicados ──────────────────────────────────────────────────────
    if filters:
        filter_parts = []
        if filters.get("date_from"): filter_parts.append(f"Desde: {filters['date_from']}")
        if filters.get("date_to"):   filter_parts.append(f"Hasta: {filters['date_to']}")
        if filters.get("project"):   filter_parts.append(f"Proyecto: {filters['project']}")
        if filter_parts:
            elements.append(Paragraph("Filtros: " + " · ".join(filter_parts), style_small))
            elements.append(Spacer(1, 8))

    # ── Resumen KPIs ───────────────────────────────────────────────────────────
    if summary:
        elements.append(Paragraph("Resumen", style_section))
        kpi_data = []
        row = []
        for key, val in summary.items():
            label = key.replace("_", " ").title()
            value = f"{val:,.2f}" if isinstance(val, float) else str(val)
            row.append(Paragraph(f"<b>{label}</b><br/>{value}", style_body))
            if len(row) == 3:
                kpi_data.append(row)
                row = []
        if row:
            while len(row) < 3:
                row.append(Paragraph("", style_body))
            kpi_data.append(row)

        if kpi_data:
            kpi_table = Table(kpi_data, colWidths=["33%", "33%", "34%"])
            kpi_table.setStyle(TableStyle([
                ("BOX",         (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
                ("INNERGRID",   (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
                ("BACKGROUND",  (0,0), (-1,-1), ROW_ALT),
                ("PADDING",     (0,0), (-1,-1), 10),
                ("VALIGN",      (0,0), (-1,-1), "MIDDLE"),
            ]))
            elements.append(kpi_table)
            elements.append(Spacer(1, 16))

    # ── Tabla de datos ─────────────────────────────────────────────────────────
    if data:
        elements.append(Paragraph("Datos del informe", style_section))

        # Cabeceras
        if data:
            headers = list(data[0].keys())
            col_labels = [h.replace("_", " ").title() for h in headers]

            # Calcular anchos de columna
            page_width = A4[0] - 4*cm
            col_width = page_width / len(headers)
            col_widths = [col_width] * len(headers)

            # Construir tabla
            table_data = [[Paragraph(f"<b>{h}</b>", ParagraphStyle(
                "TH", parent=styles["Normal"],
                fontSize=9, fontName="Helvetica-Bold",
                textColor=colors.white, alignment=TA_LEFT
            )) for h in col_labels]]

            for i, row in enumerate(data[:100]):  # máximo 100 filas
                row_data = []
                for h in headers:
                    val = row.get(h, "")
                    val_str = str(val) if val is not None else "—"
                    # Truncar valores muy largos
                    if len(val_str) > 40:
                        val_str = val_str[:37] + "..."
                    row_data.append(Paragraph(val_str, ParagraphStyle(
                        "TD", parent=styles["Normal"],
                        fontSize=8, fontName="Helvetica",
                        textColor=TEXT_MAIN,
                    )))
                table_data.append(row_data)

            data_table = Table(table_data, colWidths=col_widths, repeatRows=1)
            data_table.setStyle(TableStyle([
                ("BACKGROUND",  (0,0), (-1,0),  HEADER_BG),
                ("TEXTCOLOR",   (0,0), (-1,0),  colors.white),
                ("FONTNAME",    (0,0), (-1,0),  "Helvetica-Bold"),
                ("FONTSIZE",    (0,0), (-1,0),  9),
                ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, ROW_ALT]),
                ("BOX",         (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
                ("INNERGRID",   (0,0), (-1,-1), 0.25, colors.HexColor("#e2e8f0")),
                ("PADDING",     (0,0), (-1,-1), 6),
                ("VALIGN",      (0,0), (-1,-1), "TOP"),
                ("TOPPADDING",  (0,0), (-1,0),  8),
                ("BOTTOMPADDING",(0,0), (-1,0), 8),
            ]))
            elements.append(data_table)

            if len(data) > 100:
                elements.append(Spacer(1, 8))
                elements.append(Paragraph(
                    f"* Se muestran los primeros 100 de {len(data)} registros totales.",
                    style_small
                ))

    # ── Footer ─────────────────────────────────────────────────────────────────
    elements.append(Spacer(1, 20))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0")))
    elements.append(Paragraph(
        f"Clarive · Informe generado automáticamente · {datetime.now().strftime('%Y')}",
        ParagraphStyle("Footer", parent=styles["Normal"],
                       fontSize=7, textColor=TEXT_GREY, alignment=TA_CENTER)
    ))

    doc.build(elements)
    buffer.seek(0)
    return buffer.read()
