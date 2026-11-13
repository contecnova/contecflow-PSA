"""Generacion de PDF y cola de exportaciones.

Auditoria 2026-08 (hallazgo 22). Este codigo vivia en `mfa_service.py`, un
fichero de 1.435 lineas que contenia OCHO dominios sin relacion entre si —MFA,
organizaciones, Slack, presupuestos, planificacion asistida, escenarios, PDF y
tokens de BI— servidos ademas por un unico router llamado `mfa.py` con 38 rutas.

El reparto se pudo hacer mecanicamente porque los ocho dominios nunca estuvieron
acoplados, solo apilados: se comprobo por AST que no habia ni una llamada entre
grupos ni un solo ciclo. Los cuerpos se movieron verbatim.
"""

import io
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from app.models.project import Project
from app.models.task import Task
from app.models.mfa import (
    PDFExportJob,
)

_logger = logging.getLogger(__name__)


# ── Texto del usuario en el PDF (auditoria 2026-11 #28) ──────────────────────
# `Paragraph` de ReportLab interpreta un mini-HTML (`<font>`, `<a href>`,
# `<img src>`...). `company_name` llegaba del cuerpo de la peticion y el nombre
# del proyecto de la base, y se metian tal cual: `<img src="/etc/passwd">` o
# `<a href="javascript:...">` acababan en el documento, y un `<` suelto rompia
# la generacion. Todo texto ajeno va escapado.

def _texto(valor) -> str:
    from xml.sax.saxutils import escape
    return escape(str(valor if valor is not None else ""))


_COLOR_HEX = __import__("re").compile(r"^#[0-9A-Fa-f]{6}$")


def _color_seguro(valor: Optional[str], defecto: str = "#1C2833") -> str:
    return valor if isinstance(valor, str) and _COLOR_HEX.match(valor) else defecto


def _nombre_seguro(valor: Optional[str]) -> str:
    """Para nombres de fichero y el PDF minimo: solo letras, digitos, `_` y `-`."""
    import re
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(valor or ""))[:60] or "export"


def _pdf_de_factura(source_id: str, params: dict, db: Session) -> Optional[bytes]:
    """La factura sale del generador de facturas, no de un dibujo propio.

    Auditoria 2026-11 (hallazgo 23): aqui habia un segundo generador de
    factura —sin NIF, sin direccion, con `€` fijo— duplicando a `invoice_pdf`.
    """
    from app.models.billing_reports import Invoice
    from app.services import invoice_pdf
    from app.services._pdf_marca import PALETA_DE_FACTURA, marca_de_organizacion

    invoice = db.query(Invoice).filter(Invoice.id == source_id).first()
    if not invoice:
        return None
    marca = marca_de_organizacion(
        db, getattr(invoice, "organization_id", None), base=PALETA_DE_FACTURA,
        nombre_por_defecto=params.get("company_name") or "Contecflow",
    )
    return invoice_pdf.pdf_de_factura(db, invoice, company_name=marca.nombre, paleta=marca.paleta)


def generate_pdf(export_type: str, source_id: Optional[str], params: dict, db: Session) -> bytes:
    """Generate PDF using reportlab, or a minimal fallback if not installed."""
    if export_type == "invoice" and source_id:
        pdf = _pdf_de_factura(source_id, params, db)
        if pdf is not None:
            return pdf
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4,
                                rightMargin=20 * mm, leftMargin=20 * mm,
                                topMargin=20 * mm, bottomMargin=20 * mm)
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle("NexusTitle", parent=styles["Heading1"],
                                     fontSize=20, textColor=colors.HexColor("#1C2833"),
                                     spaceAfter=4)
        subtitle_style = ParagraphStyle("NexusSubtitle", parent=styles["Normal"],
                                        fontSize=10, textColor=colors.HexColor("#7F8C8D"),
                                        spaceAfter=12)
        section_style = ParagraphStyle("NexusSection", parent=styles["Heading2"],
                                       fontSize=13, textColor=colors.HexColor("#1A5276"),
                                       spaceBefore=12, spaceAfter=6)
        body_style = ParagraphStyle("NexusBody", parent=styles["Normal"],
                                    fontSize=9, textColor=colors.HexColor("#2C3E50"),
                                    leading=14)

        elements = []

        logo_b64 = params.get("logo_b64")  # noqa: F841
        company_name = params.get("company_name", "Contecflow")
        primary_color = _color_seguro(params.get("primary_color"))

        elements.append(Paragraph(f"<b>{_texto(company_name)}</b>", title_style))
        elements.append(HRFlowable(width="100%", thickness=2,
                                   color=colors.HexColor(primary_color), spaceAfter=8))

        now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
        elements.append(Paragraph(f"Generado: {now_str}", subtitle_style))

        if export_type == "project_summary" and source_id:
            project = db.query(Project).filter(Project.id == source_id).first()
            if project:
                from app.services.formato_regional import formatear_importe, simbolo_de_moneda
                elements.append(Paragraph(f"Resumen del proyecto: {_texto(project.name)}", section_style))
                data = [
                    ["Campo", "Valor"],
                    ["Código", project.code or "—"],
                    ["Cliente", project.client_name or "—"],
                    ["Estado", project.status or "—"],
                    ["Presupuesto", formatear_importe(project.budget_amount, simbolo_de_moneda(
                        db, project.organization_id, moneda=getattr(project, "currency", None)))
                     if project.budget_amount else "—"],
                    ["Inicio", str(project.start_date) if project.start_date else "—"],
                    ["Fin previsto", str(project.end_date_planned) if project.end_date_planned else "—"],
                ]
                tasks = db.query(Task).filter(Task.project_id == source_id).all()
                done = sum(1 for t in tasks if t.status == "done")
                data.append(["Tareas", f"{done}/{len(tasks)} completadas"])
                t = Table(data, colWidths=[60 * mm, 110 * mm])
                t.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(primary_color)),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                     [colors.HexColor("#F7F9FC"), colors.white]),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D0D7E0")),
                    ("PADDING", (0, 0), (-1, -1), 6),
                ]))
                elements.append(t)

        else:
            elements.append(Paragraph(f"Tipo: {_texto(export_type)}", section_style))
            elements.append(Paragraph("Exportación generada por Contecflow v15.", body_style))

        elements.append(Spacer(1, 15 * mm))
        elements.append(HRFlowable(width="100%", thickness=0.5,
                                   color=colors.HexColor("#D0D7E0")))
        elements.append(Paragraph(
            f"<font color='#95A5A6' size=8>Generado por Contecflow v15 · {now_str} · Documento confidencial</font>",
            body_style
        ))

        doc.build(elements)
        return buf.getvalue()

    except ImportError:
        content = f"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 120>>
stream
BT /F1 14 Tf 50 780 Td (Contecflow v15 - {_nombre_seguro(export_type)}) Tj 0 -25 Td /F1 10 Tf (Generado: {datetime.now().strftime('%d/%m/%Y')}) Tj ET
endstream
endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000266 00000 n
0000000438 00000 n
trailer<</Size 6/Root 1 0 R>>
startxref
521
%%EOF"""
        return content.encode()


def create_and_run_pdf_export(
    export_type: str, source_id: Optional[str], params: dict,
    requested_by: str, db: Session,
) -> tuple:
    """Create a PDF export job, generate the PDF, and return (bytes, filename).
    Raises ValueError on generation failure."""
    job = PDFExportJob(
        export_type=export_type,
        source_id=source_id,
        status="generating",
        params=json.dumps(params),
        requested_by=requested_by,
    )
    db.add(job); db.commit(); db.refresh(job)
    try:
        pdf_bytes = generate_pdf(export_type, source_id, params, db)
        job.status = "ready"
        job.file_size = len(pdf_bytes)
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        filename = (f"contecflow_{_nombre_seguro(export_type)}_{_nombre_seguro(source_id)}"
                    f"_{datetime.now().strftime('%Y%m%d')}.pdf")
        return pdf_bytes, filename
    except Exception as e:
        _logger.exception("PDF generation job failed (export_type=%s source_id=%s)", export_type, source_id)
        job.status = "failed"
        job.error = str(e)[:500]
        db.commit()
        raise ValueError(f"Error generando PDF: {e}")


def list_pdf_jobs(user_id: str, db: Session) -> list:
    jobs = db.query(PDFExportJob).filter(
        PDFExportJob.requested_by == user_id
    ).order_by(PDFExportJob.created_at.desc()).limit(50).all()
    return [{
        "id": j.id, "export_type": j.export_type,
        "source_id": j.source_id, "status": j.status,
        "file_size": j.file_size,
        "error": j.error,
        "created_at": str(j.created_at)[:16] if j.created_at else None,
        "completed_at": str(j.completed_at)[:16] if j.completed_at else None,
    } for j in jobs]
