"""
report_pdf.py — Generación de PDF de informes con ReportLab
"""
import io
from datetime import datetime
from typing import List, Dict, Any, Optional
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable

from app.services._pdf_marca import PALETA_POR_DEFECTO


# ── PDF de informe ───────────────────────────────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 18 y hallazgo nuevo). `generate_report_pdf` era
# complejidad 18: una funcion de 190 lineas que montaba cabecera, filtros, KPI,
# tabla y pie en un solo ambito, con la paleta de marca redefinida como
# variables locales.
#
# La paleta viene ahora de `_pdf_marca`, que es el unico sitio del lado servidor
# donde estan esos colores. Estaban en duro 91 veces en 29 ficheros. Ver la
# cabecera de ese modulo para lo que eso significa respecto a la marca blanca:
# lo que el cliente configura NO llega a estos documentos.
#
# El color que estaba declarado y no se usaba (`SUCCESS`, con su `noqa: F841`)
# se ha retirado: un `noqa` sobre una variable muerta la deja ahi para siempre.

# Cuantas filas de datos entran en el PDF. El resto se resume en una nota al
# pie: un informe de 50.000 filas no es un PDF, es un CSV.
_MAX_FILAS = 100

# Cuantos caracteres cabe un valor de celda antes de recortarlo. Sin el tope,
# un campo de texto largo descuadra el ancho de columna y parte la tabla.
_MAX_CARACTERES_POR_CELDA = 40

# Cuantos KPI caben por fila del bloque de resumen.
_KPI_POR_FILA = 3


def _estilos_de_informe(paleta):
    """Los estilos de parrafo del informe, todos en un sitio."""
    styles = getSampleStyleSheet()
    principal = paleta.color("texto_principal")
    secundario = paleta.color("texto_secundario")
    return {
        "marca": ParagraphStyle(
            "Brand", parent=styles["Normal"], fontSize=14,
            fontName="Helvetica-Bold", textColor=paleta.color("acento"), spaceAfter=2,
        ),
        "titulo": ParagraphStyle(
            "NexusTitle", parent=styles["Title"], fontSize=22,
            fontName="Helvetica-Bold", textColor=principal, spaceAfter=4, leading=28,
        ),
        "subtitulo": ParagraphStyle(
            "NexusSubtitle", parent=styles["Normal"], fontSize=11,
            fontName="Helvetica", textColor=secundario, spaceAfter=2,
        ),
        "seccion": ParagraphStyle(
            "NexusSection", parent=styles["Heading2"], fontSize=13,
            fontName="Helvetica-Bold", textColor=principal,
            spaceBefore=16, spaceAfter=8, borderPad=4,
        ),
        "cuerpo": ParagraphStyle(
            "NexusBody", parent=styles["Normal"], fontSize=10,
            fontName="Helvetica", textColor=principal, spaceAfter=4, leading=15,
        ),
        "pequeno": ParagraphStyle(
            "NexusSmall", parent=styles["Normal"], fontSize=8,
            fontName="Helvetica", textColor=secundario,
        ),
        "cabecera_de_tabla": ParagraphStyle(
            "TH", parent=styles["Normal"], fontSize=9,
            fontName="Helvetica-Bold", textColor=colors.white, alignment=TA_LEFT,
        ),
        "celda": ParagraphStyle(
            "TD", parent=styles["Normal"], fontSize=8,
            fontName="Helvetica", textColor=principal,
        ),
        "pie": ParagraphStyle(
            "Footer", parent=styles["Normal"], fontSize=7,
            textColor=secundario, alignment=TA_CENTER,
        ),
    }


def _cabecera(title: str, metric_label: str, generated_by: str, est: dict, paleta) -> list:
    return [
        Paragraph("Contecflow", est["marca"]),
        Paragraph(title, est["titulo"]),
        Paragraph(metric_label, est["subtitulo"]),
        Paragraph(
            f"Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} · {generated_by}",
            est["pequeno"],
        ),
        HRFlowable(width="100%", thickness=1, color=paleta.color("acento"), spaceAfter=16),
    ]


def _bloque_de_filtros(filters: Optional[Dict], est: dict) -> list:
    """La linea de filtros aplicados, si hay alguno reconocido.

    Solo se muestran los tres que el informe conoce: un filtro que no este aqui
    no aparece en el PDF aunque se haya aplicado, y eso es deliberado — el
    listado es para el lector, no un volcado del payload.
    """
    if not filters:
        return []
    partes = []
    for clave, etiqueta in (("date_from", "Desde"), ("date_to", "Hasta"),
                            ("project", "Proyecto")):
        if filters.get(clave):
            partes.append(f"{etiqueta}: {filters[clave]}")
    if not partes:
        return []
    return [
        Paragraph("Filtros: " + " · ".join(partes), est["pequeno"]),
        Spacer(1, 8),
    ]


def _bloque_de_kpis(summary: Optional[Dict], est: dict, paleta) -> list:
    """El resumen en rejilla de tres columnas.

    La ultima fila se rellena con celdas vacias para que la rejilla no quede
    descuadrada cuando el numero de KPI no es multiplo de tres.
    """
    if not summary:
        return []

    filas = []
    fila = []
    for clave, valor in summary.items():
        etiqueta = clave.replace("_", " ").title()
        texto = f"{valor:,.2f}" if isinstance(valor, float) else str(valor)
        fila.append(Paragraph(f"<b>{etiqueta}</b><br/>{texto}", est["cuerpo"]))
        if len(fila) == _KPI_POR_FILA:
            filas.append(fila)
            fila = []
    if fila:
        while len(fila) < _KPI_POR_FILA:
            fila.append(Paragraph("", est["cuerpo"]))
        filas.append(fila)

    if not filas:
        return []

    separador = paleta.color("linea_separadora")
    tabla = Table(filas, colWidths=["33%", "33%", "34%"])
    tabla.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, separador),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, separador),
        ("BACKGROUND", (0, 0), (-1, -1), paleta.color("fila_alterna")),
        ("PADDING", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return [Paragraph("Resumen", est["seccion"]), tabla, Spacer(1, 16)]


def _celda(valor, est: dict) -> Paragraph:
    """Una celda de datos, con el valor recortado si no cabe."""
    texto = str(valor) if valor is not None else "—"
    if len(texto) > _MAX_CARACTERES_POR_CELDA:
        texto = texto[:_MAX_CARACTERES_POR_CELDA - 3] + "..."
    return Paragraph(texto, est["celda"])


def _bloque_de_tabla(data: List[Dict[str, Any]], est: dict, paleta) -> list:
    """La tabla de datos, con las columnas repartidas a lo ancho de la pagina."""
    if not data:
        return []

    headers = list(data[0].keys())
    etiquetas = [h.replace("_", " ").title() for h in headers]
    ancho_de_columna = (A4[0] - 4 * cm) / len(headers)

    filas = [[
        Paragraph(f"<b>{h}</b>", est["cabecera_de_tabla"]) for h in etiquetas
    ]]
    for fila in data[:_MAX_FILAS]:
        filas.append([_celda(fila.get(h, ""), est) for h in headers])

    tabla = Table(filas, colWidths=[ancho_de_columna] * len(headers), repeatRows=1)
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), paleta.color("fondo_de_cabecera")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, paleta.color("fila_alterna")]),
        ("BOX", (0, 0), (-1, -1), 0.5, paleta.color("borde_de_tabla")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, paleta.color("linea_separadora")),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
    ]))

    salida = [Paragraph("Datos del informe", est["seccion"]), tabla]
    if len(data) > _MAX_FILAS:
        # La nota no es cosmetica: sin ella el lector creeria que el informe
        # esta completo y tomaria decisiones sobre 100 de 50.000 registros.
        salida += [
            Spacer(1, 8),
            Paragraph(
                f"* Se muestran los primeros {_MAX_FILAS} de {len(data)} "
                f"registros totales.",
                est["pequeno"],
            ),
        ]
    return salida


def _pie(est: dict, paleta) -> list:
    return [
        Spacer(1, 20),
        HRFlowable(width="100%", thickness=0.5, color=paleta.color("linea_separadora")),
        Paragraph(
            f"Contecflow · Informe generado automáticamente · "
            f"{datetime.now().strftime('%Y')}",
            est["pie"],
        ),
    ]


def generate_report_pdf(
    title: str,
    metric_label: str,
    data: List[Dict[str, Any]],
    summary: Optional[Dict] = None,
    filters: Optional[Dict] = None,
    generated_by: str = "Contecflow",
) -> bytes:
    """
    Genera un PDF de informe y devuelve los bytes.
    """
    paleta = PALETA_POR_DEFECTO
    est = _estilos_de_informe(paleta)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
    )

    elements = (
        _cabecera(title, metric_label, generated_by, est, paleta)
        + _bloque_de_filtros(filters, est)
        + _bloque_de_kpis(summary, est, paleta)
        + _bloque_de_tabla(data, est, paleta)
        + _pie(est, paleta)
    )

    doc.build(elements)
    buffer.seek(0)
    return buffer.read()
