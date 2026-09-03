"""signature_pdf.py — Genera un PDF con certificado de firma digital.

Auditoria 2026-08 (hallazgo 32). Los colores estaban escritos en duro dieciseis
veces —cinco constantes locales y once `HexColor` intercalados—, asi que este
certificado, que es lo que recibe el cliente al firmar, salia con los colores de
la plataforma aunque el cliente tuviera su marca configurada.

Ahora la paleta viene de `_pdf_marca` y el llamador puede pasar la del tenant.
Los tres tintes propios de este documento —el gris de cuerpo, el sombreado de
filas y el fondo verdoso del sello— se quedan aqui como constantes con nombre:
no estan en la paleta compartida porque solo los usa este documento, y meterlos
alli para un unico llamador seria sobreajustarla.
"""
import io
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable

from app.services._pdf_marca import PALETA_POR_DEFECTO

#: Tintes propios de este documento; ver la nota de la cabecera.
_GRIS_DE_CUERPO = "#374151"
_SOMBREADO_DE_FILA = "#f9fafb"
_FONDO_DEL_SELLO = "#f0fdf9"
_FONDO_DE_EVIDENCIA = "#f8fafc"


def generate_signed_pdf(
    document_title: str,
    document_description: str,
    signer_name: str,
    signer_email: str,
    signer_job_title: str,
    project_name: str,
    signed_at: datetime,
    signature_ip: str = "",
    original_file_name: str = "",
    paleta=None,
) -> bytes:
    """
    Genera un PDF certificado de firma digital del documento.
    Incluye: datos del firmante, timestamp, IP y un hash de evidencia.
    """
    import hashlib

    # La resuelve el llamador con `marca_de_organizacion()`, que tiene el
    # `db` y el `organization_id`.
    paleta = paleta or PALETA_POR_DEFECTO

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            leftMargin=2.5*cm, rightMargin=2.5*cm,
                            topMargin=2.5*cm, bottomMargin=2.5*cm)

    ACCENT  = paleta.color("acento")
    GREEN   = paleta.color("exito")
    GREY    = paleta.color("texto_secundario")
    BORDER  = paleta.color("linea_separadora")
    BG_CERT = colors.HexColor(_FONDO_DEL_SELLO)
    # El gris va dentro de una etiqueta `<font color>` del marcado de
    # ReportLab, asi que hace falta el hexadecimal y no el objeto Color.
    GRIS_HEX = paleta.texto_secundario

    styles = getSampleStyleSheet()

    # Hash de evidencia (SHA256 de los datos clave)
    evidence_str = f"{document_title}|{signer_email}|{signed_at.isoformat()}|{signature_ip}"
    evidence_hash = hashlib.sha256(evidence_str.encode()).hexdigest()

    elements = []

    # ── Header ────────────────────────────────────────────────────────────────
    elements.append(Paragraph("Contecflow", ParagraphStyle("Brand",
        parent=styles["Normal"], fontSize=13, fontName="Helvetica-Bold",
        textColor=ACCENT, alignment=TA_CENTER, spaceAfter=4)))

    elements.append(Paragraph("CERTIFICADO DE FIRMA DIGITAL", ParagraphStyle("CertTitle",
        parent=styles["Title"], fontSize=20, fontName="Helvetica-Bold",
        textColor=paleta.color("texto_principal"), alignment=TA_CENTER, spaceAfter=4)))

    elements.append(Paragraph("Documento firmado electrónicamente", ParagraphStyle("Sub",
        parent=styles["Normal"], fontSize=11, textColor=GREY,
        alignment=TA_CENTER, spaceAfter=16)))

    elements.append(HRFlowable(width="100%", thickness=2, color=ACCENT, spaceAfter=20))

    # ── Estado de firma ────────────────────────────────────────────────────────
    status_table = Table([[
        Paragraph("✓", ParagraphStyle("Check", parent=styles["Normal"],
                  fontSize=28, fontName="Helvetica-Bold", textColor=GREEN, alignment=TA_CENTER)),
        Paragraph(
            f"<b>DOCUMENTO FIRMADO</b><br/>"
            f"<font color='{GRIS_HEX}' size='10'>"
            f"{signed_at.strftime('%d de %B de %Y a las %H:%M:%S')} UTC</font>",
            ParagraphStyle("StatusText", parent=styles["Normal"],
                          fontSize=14, fontName="Helvetica-Bold",
                          textColor=paleta.color("texto_principal")),
        )
    ]], colWidths=[2*cm, "80%"])
    status_table.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,-1), BG_CERT),
        ("BOX",         (0,0), (-1,-1), 1.5, GREEN),
        ("ROUNDEDCORNERS", [8]),
        ("PADDING",     (0,0), (-1,-1), 14),
        ("VALIGN",      (0,0), (-1,-1), "MIDDLE"),
    ]))
    elements.append(status_table)
    elements.append(Spacer(1, 20))

    # ── Datos del documento ────────────────────────────────────────────────────
    elements.append(Paragraph("Documento", ParagraphStyle("Section",
        parent=styles["Normal"], fontSize=11, fontName="Helvetica-Bold",
        textColor=colors.HexColor(_GRIS_DE_CUERPO), spaceAfter=8, spaceBefore=4)))

    doc_data = [
        ["Título",      document_title],
        ["Proyecto",    project_name],
        ["Descripción", document_description or "—"],
    ]
    if original_file_name:
        doc_data.append(["Archivo original", original_file_name])

    doc_table = Table(doc_data, colWidths=["25%", "75%"])
    doc_table.setStyle(TableStyle([
        ("FONTNAME",    (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME",    (1,0), (1,-1), "Helvetica"),
        ("FONTSIZE",    (0,0), (-1,-1), 10),
        ("TEXTCOLOR",   (0,0), (0,-1), GREY),
        ("TEXTCOLOR",   (1,0), (1,-1), paleta.color("texto_principal")),
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [colors.white, colors.HexColor(_SOMBREADO_DE_FILA)]),
        ("BOX",         (0,0), (-1,-1), 0.5, BORDER),
        ("INNERGRID",   (0,0), (-1,-1), 0.25, BORDER),
        ("PADDING",     (0,0), (-1,-1), 8),
    ]))
    elements.append(doc_table)
    elements.append(Spacer(1, 20))

    # ── Datos del firmante ────────────────────────────────────────────────────
    elements.append(Paragraph("Firmante", ParagraphStyle("Section2",
        parent=styles["Normal"], fontSize=11, fontName="Helvetica-Bold",
        textColor=colors.HexColor(_GRIS_DE_CUERPO), spaceAfter=8, spaceBefore=4)))

    signer_data = [
        ["Nombre",   signer_name],
        ["Email",    signer_email],
        ["Cargo",    signer_job_title or "—"],
        ["Fecha",    signed_at.strftime("%d/%m/%Y %H:%M:%S UTC")],
    ]
    if signature_ip:
        signer_data.append(["IP",  signature_ip])

    signer_table = Table(signer_data, colWidths=["25%", "75%"])
    signer_table.setStyle(TableStyle([
        ("FONTNAME",    (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME",    (1,0), (1,-1), "Helvetica"),
        ("FONTSIZE",    (0,0), (-1,-1), 10),
        ("TEXTCOLOR",   (0,0), (0,-1), GREY),
        ("TEXTCOLOR",   (1,0), (1,-1), paleta.color("texto_principal")),
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [colors.white, colors.HexColor(_SOMBREADO_DE_FILA)]),
        ("BOX",         (0,0), (-1,-1), 0.5, BORDER),
        ("INNERGRID",   (0,0), (-1,-1), 0.25, BORDER),
        ("PADDING",     (0,0), (-1,-1), 8),
    ]))
    elements.append(signer_table)
    elements.append(Spacer(1, 20))

    # ── Hash de evidencia ──────────────────────────────────────────────────────
    elements.append(HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceAfter=12))

    elements.append(Paragraph("Código de verificación (SHA-256)", ParagraphStyle("HashLabel",
        parent=styles["Normal"], fontSize=9, fontName="Helvetica-Bold",
        textColor=GREY, spaceAfter=4)))

    elements.append(Paragraph(
        f"<font name='Courier' size='8'>{evidence_hash[:32]}<br/>{evidence_hash[32:]}</font>",
        ParagraphStyle("Hash", parent=styles["Normal"],
                      fontSize=8, textColor=colors.HexColor(_GRIS_DE_CUERPO),
                      backColor=colors.HexColor(_FONDO_DE_EVIDENCIA), spaceAfter=12,
                      leftIndent=10, rightIndent=10, borderPad=6)
    ))

    elements.append(Paragraph(
        "Este certificado acredita que el documento fue revisado y aceptado electrónicamente "
        "por el firmante identificado. El código SHA-256 garantiza la integridad del registro.",
        ParagraphStyle("Disclaimer", parent=styles["Normal"],
                      fontSize=8, textColor=GREY, alignment=TA_CENTER)
    ))

    doc.build(elements)
    buffer.seek(0)
    return buffer.read()
