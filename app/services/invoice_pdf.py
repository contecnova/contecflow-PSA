"""
invoice_pdf.py — Generación de PDF de facturas con ReportLab

Genera un PDF de factura profesional con:
- Header con branding Contecflow
- Datos del cliente y emisor
- Tabla de líneas con descripción, cantidad, precio y total
- Resumen: subtotal, IVA, total
- Footer con número de factura, fecha y notas
"""
import io
from datetime import date, datetime
from typing import List, Optional
from app.core.config import settings
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable


def generate_invoice_pdf(
    invoice_number: str,
    issue_date,
    due_date,
    client_name: str,
    client_address: Optional[str],
    client_vat: Optional[str],
    client_email: Optional[str],
    lines: List[dict],
    subtotal: float,
    tax_rate: float,
    tax_amount: float,
    total: float,
    currency: Optional[str] = None,
    notes: Optional[str] = None,
    po_reference: Optional[str] = None,
    period_from=None,
    period_to=None,
    company_name: str = "Contecflow PSA",
    generated_by: str = "Contecflow",
) -> bytes:
    """
    Genera un PDF de factura y devuelve los bytes en formato PDF.
    """

    currency = currency or settings.DEFAULT_CURRENCY
    W, H = A4
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2.2*cm, rightMargin=2.2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )

    # ── Paleta Contecflow ────────────────────────────────────────────────────────
    ACCENT    = colors.HexColor("#00d4ff")
    SUCCESS   = colors.HexColor("#00e5a0")
    TEXT_MAIN = colors.HexColor("#1a1a2e")
    TEXT_GREY = colors.HexColor("#6b7280")
    HEADER_BG = colors.HexColor("#0f172a")
    ROW_ALT   = colors.HexColor("#f0f9ff")
    ROW_TOTAL = colors.HexColor("#e0faf5")

    styles = getSampleStyleSheet()

    def PS(name, **kw):
        return ParagraphStyle(name, parent=styles["Normal"], **kw)

    style_brand = PS("Brand", fontSize=16, fontName="Helvetica-Bold", textColor=ACCENT, spaceAfter=2)
    style_h1    = PS("H1",    fontSize=22, fontName="Helvetica-Bold", textColor=TEXT_MAIN, spaceAfter=4, leading=28)
    style_label = PS("Lbl",   fontSize=8,  fontName="Helvetica-Bold", textColor=TEXT_GREY, spaceAfter=1, textTransform="uppercase")
    style_body  = PS("Body",  fontSize=10, fontName="Helvetica",      textColor=TEXT_MAIN, spaceAfter=3, leading=14)
    style_small = PS("Small", fontSize=8,  fontName="Helvetica",      textColor=TEXT_GREY)
    PS("Right", fontSize=10, fontName="Helvetica-Bold", textColor=TEXT_MAIN, alignment=TA_RIGHT)
    style_note  = PS("Note",  fontSize=9,  fontName="Helvetica",      textColor=TEXT_GREY, leading=13)

    def fmt_money(v):
        cur_sym = {"EUR": "€", "USD": "$", "GBP": "£"}.get(currency, currency)
        return f"{v:,.2f} {cur_sym}"

    def fmt_date(d):
        if d is None: return "—"
        if isinstance(d, (date, datetime)):
            return d.strftime("%d/%m/%Y")
        return str(d)

    elements = []

    # ── Header: brand + invoice title ─────────────────────────────────────────
    header_data = [
        [Paragraph(company_name, style_brand), Paragraph("FACTURA", style_h1)],
    ]
    header_table = Table(header_data, colWidths=[9*cm, 8*cm])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN",  (1, 0), (1, 0),   "RIGHT"),
    ]))
    elements.append(header_table)
    elements.append(HRFlowable(width="100%", thickness=1.5, color=ACCENT, spaceAfter=10, spaceBefore=6))

    # ── Invoice metadata ──────────────────────────────────────────────────────
    meta_rows = [
        ("Nº Factura:", invoice_number),
        ("Fecha emisión:", fmt_date(issue_date)),
        ("Fecha vencimiento:", fmt_date(due_date)),
    ]
    if po_reference:
        meta_rows.append(("Referencia PO:", po_reference))
    if period_from or period_to:
        meta_rows.append(("Período:", f"{fmt_date(period_from)} — {fmt_date(period_to)}"))

    meta_data = [[Paragraph(k, style_label), Paragraph(v, style_body)] for k, v in meta_rows]
    meta_table = Table(meta_data, colWidths=[4.5*cm, 12.5*cm])
    meta_table.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 14))

    # ── Client block ──────────────────────────────────────────────────────────
    elements.append(Paragraph("DATOS DEL CLIENTE", style_label))
    elements.append(Paragraph(client_name or "—", PS("ClientName", fontSize=12, fontName="Helvetica-Bold", textColor=TEXT_MAIN, spaceAfter=2)))
    if client_address: elements.append(Paragraph(client_address, style_body))
    if client_vat:     elements.append(Paragraph(f"NIF/VAT: {client_vat}", style_small))
    if client_email:   elements.append(Paragraph(f"Email: {client_email}", style_small))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0"), spaceAfter=12, spaceBefore=12))

    # ── Lines table ───────────────────────────────────────────────────────────
    col_widths = [9.5*cm, 1.5*cm, 1.5*cm, 2*cm, 2.5*cm]
    table_header = [
        Paragraph("Descripción",   PS("TH", fontSize=9, fontName="Helvetica-Bold", textColor=colors.white)),
        Paragraph("Ud.",           PS("TH2", fontSize=9, fontName="Helvetica-Bold", textColor=colors.white, alignment=TA_CENTER)),
        Paragraph("Cant.",         PS("TH3", fontSize=9, fontName="Helvetica-Bold", textColor=colors.white, alignment=TA_RIGHT)),
        Paragraph("Precio/ud.",    PS("TH4", fontSize=9, fontName="Helvetica-Bold", textColor=colors.white, alignment=TA_RIGHT)),
        Paragraph("Importe",       PS("TH5", fontSize=9, fontName="Helvetica-Bold", textColor=colors.white, alignment=TA_RIGHT)),
    ]

    def mk_right(txt, fs=9, bold=False):
        fn = "Helvetica-Bold" if bold else "Helvetica"
        return Paragraph(str(txt), PS("R", fontSize=fs, fontName=fn, textColor=TEXT_MAIN, alignment=TA_RIGHT))
    def mk_center(txt):
        return Paragraph(str(txt), PS("C", fontSize=9, fontName="Helvetica", textColor=TEXT_GREY, alignment=TA_CENTER))

    table_rows = [table_header]
    for i, line in enumerate(lines):
        row = [
            Paragraph(str(line.get("description", "")), PS("LineDesc", fontSize=9, fontName="Helvetica", textColor=TEXT_MAIN, leading=13)),
            mk_center(str(line.get("unit", "h"))),
            mk_right(f"{line.get('quantity', 1):g}"),
            mk_right(fmt_money(line.get("unit_price", 0))),
            mk_right(fmt_money(line.get("amount", 0)), bold=True),
        ]
        table_rows.append(row)

    # Totals
    def total_row(label, value, bg=None, bold=False):
        lbl = Paragraph(label, PS("TLbl", fontSize=9, fontName="Helvetica-Bold" if bold else "Helvetica",
                                  textColor=TEXT_MAIN, alignment=TA_RIGHT))
        val = Paragraph(value, PS("TVal", fontSize=10 if bold else 9,
                                  fontName="Helvetica-Bold" if bold else "Helvetica",
                                  textColor=TEXT_MAIN, alignment=TA_RIGHT))
        return ["", "", "", lbl, val]

    table_rows.append(total_row("Subtotal:", fmt_money(subtotal)))
    table_rows.append(total_row(f"IVA ({tax_rate:.0f}%):", fmt_money(tax_amount)))
    table_rows.append(total_row("TOTAL:", fmt_money(total), bold=True))

    n_lines = len(lines)
    lines_table = Table(table_rows, colWidths=col_widths, repeatRows=1)

    row_styles = [
        ("BACKGROUND",    (0, 0), (-1, 0),  HEADER_BG),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
        ("ROWBACKGROUNDS",(0, 1), (-1, n_lines), [colors.white, ROW_ALT]),
        ("GRID",          (0, 0), (-1, n_lines), 0.3, colors.HexColor("#dee6ef")),
        ("LINEBELOW",     (0, 0), (-1, 0),  1, ACCENT),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        # Subtotal separator
        ("LINEABOVE",     (0, n_lines+1), (-1, n_lines+1), 0.8, TEXT_GREY),
        # Total row highlight
        ("BACKGROUND",    (0, n_lines+3), (-1, n_lines+3), ROW_TOTAL),
        ("LINEBELOW",     (0, n_lines+3), (-1, n_lines+3), 1.5, SUCCESS),
        ("FONTSIZE",      (0, n_lines+3), (-1, n_lines+3), 11),
        ("NOSPLIT",       (0, 0), (-1, -1)),
    ]
    lines_table.setStyle(TableStyle(row_styles))
    elements.append(lines_table)

    # ── Notes ─────────────────────────────────────────────────────────────────
    if notes:
        elements.append(Spacer(1, 16))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0"), spaceAfter=8))
        elements.append(Paragraph("NOTAS", style_label))
        elements.append(Paragraph(notes, style_note))

    # ── Footer ─────────────────────────────────────────────────────────────────
    elements.append(Spacer(1, 20))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=ACCENT, spaceAfter=6))
    elements.append(Paragraph(
        f"Generado por {generated_by} · {datetime.now().strftime('%d/%m/%Y %H:%M')} · {invoice_number}",
        PS("Footer", fontSize=7.5, fontName="Helvetica", textColor=TEXT_GREY, alignment=TA_CENTER)
    ))

    doc.build(elements)
    return buffer.getvalue()
