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

from app.services._pdf_marca import PALETA_POR_DEFECTO

logger = logging.getLogger(__name__)
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak,
)

# Auditoria 2026-08 (hallazgo 32). Los colores estaban en duro como constantes
# de MODULO, asi que ni siquiera se podian sustituir por llamada: el informe de
# campana de un cliente salia con los colores de la plataforma. Ahora vienen de
# `_pdf_marca` y `generate_campaign_pdf` acepta la paleta del tenant.
#
# `WARNING` y `MUTED_BG` se quedan aqui: son colores de ESTADO —aviso y
# «anonimizado»— y su significado no depende de la marca. Sustituirlos por un
# color de marca haria que un aviso no se leyera como aviso.
WARNING   = colors.HexColor("#f59e0b")
MUTED_BG  = colors.HexColor("#fef3c7")  # bg suave para anonimizados


def _is_rating(kind: str) -> bool:
    return kind in ("rating_5", "rating_10", "scale_likert")


def _colores(paleta):
    """Los cinco colores que usa este informe, en el orden en que se desempacan.

    Va aparte de `generate_campaign_pdf` a proposito: resolver el valor por
    defecto es una rama, y esa funcion ya esta en complejidad 13 —lo estaba
    antes de tocarla, comprobado con `git stash`—, asi que no se le anade una
    mas. Sacarla no la baja del umbral; es solo no empeorarla.

    `exito` no esta: la constante `SUCCESS` que habia en este modulo no la usaba
    nadie, asi que era codigo muerto y se ha retirado en vez de trasladarse.
    """
    p = paleta or PALETA_POR_DEFECTO
    return (p.color("acento"), p.color("texto_principal"),
            p.color("texto_secundario"), p.color("fondo_de_cabecera"),
            p.color("fila_alterna"))


#: Los cuatro grupos de evaluadores de una 360, con su etiqueta. El orden es el
#: del informe y no es alfabético: va de dentro afuera.
_GRUPOS_360 = (
    ("self", "Self"),
    ("manager", "Manager"),
    ("peer", "Pares"),
    ("upward", "Upward"),
)


def _estilo_de_tabla(HEADER_BG, ROW_ALT, TEXT_GREY, tamano: int) -> TableStyle:
    """El estilo compartido de las tablas del informe.

    Auditoría 2026-09 (hallazgo 18): las dos tablas de este PDF repetían las
    mismas ocho reglas de estilo con un solo valor distinto.
    """
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), tamano),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW_ALT]),
        ("GRID",       (0, 0), (-1, -1), 0.25, TEXT_GREY),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
    ])


def _lectura_de_la_brecha(propia, ajenas: list) -> str:
    """Qué dice la diferencia entre la autoevaluación y la del resto.

    Un punto de diferencia es el corte, y tiene sentido en una escala de 1 a 5:
    por debajo de eso es ruido de muestra pequeña.

    «Punto ciego» es puntuarse por encima de lo que le puntúan; «fortaleza no
    percibida», al revés. Los dos nombres son los del método, y por eso están
    escritos así y no como «alto» y «bajo».
    """
    if propia is None or not ajenas:
        return "—"
    diferencia = propia - sum(ajenas) / len(ajenas)
    if diferencia >= 1:
        return "Punto ciego"
    if diferencia <= -1:
        return "Fortaleza no percibida"
    return "Alineado"


def _tabla_de_grupos(groups: dict, colores_) -> Table:
    """Cuántas respuestas ha dado cada grupo y si va anonimizado."""
    HEADER_BG, ROW_ALT, TEXT_GREY = colores_
    filas = [["Grupo", "Respuestas", "Anonimizado"]]
    for clave, etiqueta in _GRUPOS_360:
        g = groups.get(clave) or {}
        filas.append([
            etiqueta, str(g.get("count", 0)), "Sí" if g.get("anonymized") else "No",
        ])
    t = Table(filas, colWidths=[6 * cm, 4 * cm, 4 * cm])
    estilo = _estilo_de_tabla(HEADER_BG, ROW_ALT, TEXT_GREY, 9)
    estilo.add("ALIGN", (1, 0), (-1, -1), "CENTER")
    estilo.add("LEFTPADDING", (0, 0), (-1, -1), 6)
    estilo.add("RIGHTPADDING", (0, 0), (-1, -1), 6)
    t.setStyle(estilo)
    return t


def _tabla_de_comparativa(rating_qs, comparacion: dict, style_body, colores_) -> Table:
    """Puntuación por pregunta y grupo, con la lectura de la brecha."""
    HEADER_BG, ROW_ALT, TEXT_GREY = colores_
    filas = [["Pregunta", "Self", "Manager", "Pares", "Upward", "Insight"]]
    for q in rating_qs:
        c = comparacion.get(q["key"], {})
        propia = c.get("self")
        ajenas = [c.get("manager"), c.get("peers"), c.get("upward")]
        filas.append([
            Paragraph(q["label"], style_body),
            f"{propia:.1f}" if propia is not None else "—",
            *[f"{v:.1f}" if v is not None else "—" for v in ajenas],
            _lectura_de_la_brecha(propia, [v for v in ajenas if v is not None]),
        ])
    t = Table(filas, colWidths=[6 * cm, 1.5 * cm, 1.8 * cm, 1.5 * cm, 1.8 * cm, 4.5 * cm])
    estilo = _estilo_de_tabla(HEADER_BG, ROW_ALT, TEXT_GREY, 8)
    estilo.add("ALIGN", (1, 1), (4, -1), "CENTER")
    t.setStyle(estilo)
    return t


def _bloque_de_comentarios(text_qs, groups: dict, threshold: int,
                           style_h2, style_body, style_meta, style_quote) -> list:
    """Los comentarios abiertos, respetando la anonimización.

    Un grupo anonimizado **se nombra igual**, con su motivo: esconder que
    existe haría pensar que nadie de ese grupo respondió, que es una conclusión
    distinta y falsa.
    """
    elementos = [PageBreak(), Paragraph("Comentarios cualitativos", style_h2)]
    for q in text_qs:
        elementos.append(Paragraph(f"<b>{q['label']}</b>", style_body))
        elementos.append(Spacer(1, 4))
        for clave, etiqueta in _GRUPOS_360:
            g = groups.get(clave) or {}
            anonimizado = g.get("anonymized", False)
            textos = (g.get("text_by_question", {}) or {}).get(q["key"], [])
            if not textos and not anonimizado:
                continue
            if anonimizado:
                elementos.append(Paragraph(
                    f"<i>{etiqueta}: oculto por anonimización "
                    f"(n={g.get('count', 0)} &lt; {threshold})</i>",
                    style_meta,
                ))
                continue
            elementos.append(Paragraph(f"<b>{etiqueta}:</b>", style_meta))
            elementos += [
                Paragraph(f"• {it.get('text', '')}", style_quote) for it in textos
            ]
        elementos.append(Spacer(1, 8))
    return elementos


def generate_campaign_pdf(dashboard: dict, paleta=None) -> bytes:
    """Recibe el dict producido por `aggregate_campaign` y genera el PDF."""
    ACCENT, TEXT_MAIN, TEXT_GREY, HEADER_BG, ROW_ALT = _colores(paleta)
    colores_ = (HEADER_BG, ROW_ALT, TEXT_GREY)

    buffer = io.BytesIO()
    camp = dashboard["campaign"]
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title=f"Evaluación 360° — {camp.get('subject_name', '')}",
    )

    styles = getSampleStyleSheet()
    style_title = ParagraphStyle("T", parent=styles["Title"], fontSize=22,
                                 fontName="Helvetica-Bold", textColor=TEXT_MAIN,
                                 spaceAfter=4, leading=28)
    style_h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=13,
                              fontName="Helvetica-Bold", textColor=ACCENT,
                              spaceBefore=12, spaceAfter=6)
    style_meta = ParagraphStyle("M", parent=styles["Normal"], fontSize=9,
                                textColor=TEXT_GREY, spaceAfter=2)
    style_body = ParagraphStyle("B", parent=styles["Normal"], fontSize=10,
                                textColor=TEXT_MAIN, leading=14)
    style_quote = ParagraphStyle("Q", parent=styles["Normal"], fontSize=9,
                                 textColor=TEXT_MAIN, leading=12,
                                 leftIndent=14, spaceAfter=4)

    questions = dashboard["questions"]
    groups = dashboard["groups"]
    threshold = dashboard.get("anonymity_threshold", 3)

    elements = [
        Paragraph(f"Evaluación 360° — {camp.get('subject_name', '')}", style_title),
        Paragraph(
            f"Generado el {datetime.now().strftime('%Y-%m-%d %H:%M')}<br/>"
            f"Estado: <b>{camp.get('status')}</b> · "
            f"Respuestas: <b>{dashboard['total_submitted']}/{dashboard['total_assigned']}</b> · "
            f"Umbral de anonimización: <b>{threshold}</b>",
            style_meta,
        ),
        HRFlowable(width="100%", color=ACCENT, thickness=1.5, spaceBefore=8, spaceAfter=12),
        Paragraph("Resumen por grupo de evaluadores", style_h2),
        _tabla_de_grupos(groups, colores_),
    ]

    rating_qs = [q for q in questions if _is_rating(q["kind"])]
    if rating_qs:
        elements.append(Paragraph("Comparativa por pregunta", style_h2))
        elements.append(_tabla_de_comparativa(
            rating_qs, dashboard.get("comparison", {}), style_body, colores_,
        ))

    text_qs = [q for q in questions if not _is_rating(q["kind"])]
    if text_qs:
        elements += _bloque_de_comentarios(
            text_qs, groups, threshold, style_h2, style_body, style_meta, style_quote,
        )

    elements += [
        Spacer(1, 12),
        HRFlowable(width="100%", color=TEXT_GREY, thickness=0.5),
        Paragraph(
            "Documento confidencial — solo para el subject, su manager y RR.HH.",
            style_meta,
        ),
    ]

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()
