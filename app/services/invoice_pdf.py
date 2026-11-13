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

from app.services._pdf_marca import PALETA_DE_FACTURA
from app.core.constantes import NOMBRE_DEL_PRODUCTO, NOMBRE_COMPLETO_DEL_PRODUCTO


# ── PDF de factura ───────────────────────────────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 18 y hallazgo 32). `generate_invoice_pdf` era
# complejidad 16: cabecera, metadatos, cliente, lineas, totales, notas y pie en
# un solo ambito de 180 lineas, con la paleta de marca redefinida como variables
# locales.
#
# La paleta viene ahora de `_pdf_marca` — un solo sitio, con la variante de
# factura que conserva su matiz azulado en las filas. Ver la cabecera de ese
# modulo: la marca que el cliente configura NO llega a este documento, y esta
# factura es justo lo que recibe el cliente de nuestro cliente.
#
# Dos cosas muertas retiradas: `W, H = A4` (nunca se usaban) y una llamada a
# `PS("Right", ...)` que construia un estilo y lo tiraba.

def _importe(valor, etiqueta: str) -> str:
    """Importe con la etiqueta de la moneda (su símbolo de `CURRENCY_SYMBOLS`, o su código: «1.234,00 CHF»)."""
    return f"{valor:,.2f} {etiqueta}"


def _fecha(d) -> str:
    """Fecha en formato español, o una raya si no hay.

    La raya y no «None»: es un documento que se manda al cliente.
    """
    if d is None:
        return "—"
    if isinstance(d, (date, datetime)):
        return d.strftime("%d/%m/%Y")
    return str(d)


def _estilos_de_factura(paleta):
    """Los estilos del documento. `PS` acorta la construccion repetida."""
    hoja = getSampleStyleSheet()
    principal = paleta.color("texto_principal")
    secundario = paleta.color("texto_secundario")

    def PS(name, **kw):
        return ParagraphStyle(name, parent=hoja["Normal"], **kw)

    return {
        "PS": PS,
        "marca": PS("Brand", fontSize=16, fontName="Helvetica-Bold",
                    textColor=paleta.color("acento"), spaceAfter=2),
        "h1": PS("H1", fontSize=22, fontName="Helvetica-Bold",
                 textColor=principal, spaceAfter=4, leading=28),
        "etiqueta": PS("Lbl", fontSize=8, fontName="Helvetica-Bold",
                       textColor=secundario, spaceAfter=1, textTransform="uppercase"),
        "cuerpo": PS("Body", fontSize=10, fontName="Helvetica",
                     textColor=principal, spaceAfter=3, leading=14),
        "pequeno": PS("Small", fontSize=8, fontName="Helvetica", textColor=secundario),
        "nota": PS("Note", fontSize=9, fontName="Helvetica",
                   textColor=secundario, leading=13),
        "nombre_cliente": PS("ClientName", fontSize=12, fontName="Helvetica-Bold",
                             textColor=principal, spaceAfter=2),
        "pie": PS("Footer", fontSize=7.5, fontName="Helvetica",
                  textColor=secundario, alignment=TA_CENTER),
    }


def _cabecera_de_factura(company_name: str, est: dict, paleta) -> list:
    tabla = Table(
        [[Paragraph(company_name, est["marca"]), Paragraph("FACTURA", est["h1"])]],
        colWidths=[9 * cm, 8 * cm],
    )
    tabla.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    return [
        tabla,
        HRFlowable(width="100%", thickness=1.5, color=paleta.color("acento"),
                   spaceAfter=10, spaceBefore=6),
    ]


def _metadatos(invoice_number, issue_date, due_date, po_reference,
               period_from, period_to, est: dict) -> list:
    """Los datos identificativos. Los opcionales solo aparecen si vienen."""
    filas = [
        ("Nº Factura:", invoice_number),
        ("Fecha emisión:", _fecha(issue_date)),
        ("Fecha vencimiento:", _fecha(due_date)),
    ]
    if po_reference:
        filas.append(("Referencia PO:", po_reference))
    if period_from or period_to:
        filas.append(("Período:", f"{_fecha(period_from)} — {_fecha(period_to)}"))

    tabla = Table(
        [[Paragraph(k, est["etiqueta"]), Paragraph(v, est["cuerpo"])] for k, v in filas],
        colWidths=[4.5 * cm, 12.5 * cm],
    )
    tabla.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return [tabla, Spacer(1, 14)]


def _bloque_de_cliente(client_name, client_address, client_vat, client_email,
                       est: dict, paleta) -> list:
    salida = [
        Paragraph("DATOS DEL CLIENTE", est["etiqueta"]),
        Paragraph(client_name or "—", est["nombre_cliente"]),
    ]
    if client_address:
        salida.append(Paragraph(client_address, est["cuerpo"]))
    if client_vat:
        salida.append(Paragraph(f"NIF/VAT: {client_vat}", est["pequeno"]))
    if client_email:
        salida.append(Paragraph(f"Email: {client_email}", est["pequeno"]))
    salida.append(HRFlowable(
        width="100%", thickness=0.5, color=paleta.color("linea_separadora"),
        spaceAfter=12, spaceBefore=12,
    ))
    return salida


def _tabla_de_lineas(lines: list, currency: str, subtotal, tax_rate, tax_amount,
                     total, est: dict, paleta) -> list:
    """Las lineas de la factura y sus totales, en una sola tabla.

    Van juntas a proposito: los totales tienen que quedar pegados a las lineas
    que suman, y `NOSPLIT` impide que un salto de pagina los separe — una
    factura con el total en una hoja aparte es una factura que nadie firma.
    """
    PS = est["PS"]
    principal = paleta.color("texto_principal")
    secundario = paleta.color("texto_secundario")

    def cabecera(texto, alineacion=None):
        kw = {"fontSize": 9, "fontName": "Helvetica-Bold",
              "textColor": paleta.color("texto_sobre_cabecera")}
        if alineacion is not None:
            kw["alignment"] = alineacion
        return Paragraph(texto, PS("TH", **kw))

    def derecha(texto, fs=9, negrita=False):
        return Paragraph(str(texto), PS(
            "R", fontSize=fs,
            fontName="Helvetica-Bold" if negrita else "Helvetica",
            textColor=principal, alignment=TA_RIGHT,
        ))

    def centrado(texto):
        return Paragraph(str(texto), PS(
            "C", fontSize=9, fontName="Helvetica",
            textColor=secundario, alignment=TA_CENTER,
        ))

    filas = [[
        cabecera("Descripción"),
        cabecera("Ud.", TA_CENTER),
        cabecera("Cant.", TA_RIGHT),
        cabecera("Precio/ud.", TA_RIGHT),
        cabecera("Importe", TA_RIGHT),
    ]]

    for line in lines:
        filas.append([
            Paragraph(str(line.get("description", "")), PS(
                "LineDesc", fontSize=9, fontName="Helvetica",
                textColor=principal, leading=13,
            )),
            centrado(str(line.get("unit", "h"))),
            # `:g` quita los decimales sobrantes: «2» y no «2.0».
            derecha(f"{line.get('quantity', 1):g}"),
            derecha(_importe(line.get("unit_price", 0), currency)),
            derecha(_importe(line.get("amount", 0), currency), negrita=True),
        ])

    def fila_de_total(etiqueta, valor, negrita=False):
        # Las tres primeras celdas van vacias para que el total quede alineado
        # bajo la columna de importes.
        return ["", "", "", Paragraph(etiqueta, PS(
            "TLbl", fontSize=9,
            fontName="Helvetica-Bold" if negrita else "Helvetica",
            textColor=principal, alignment=TA_RIGHT,
        )), Paragraph(valor, PS(
            "TVal", fontSize=10 if negrita else 9,
            fontName="Helvetica-Bold" if negrita else "Helvetica",
            textColor=principal, alignment=TA_RIGHT,
        ))]

    filas.append(fila_de_total("Subtotal:", _importe(subtotal, currency)))
    filas.append(fila_de_total(f"IVA ({tax_rate:.0f}%):", _importe(tax_amount, currency)))
    filas.append(fila_de_total("TOTAL:", _importe(total, currency), negrita=True))

    n = len(lines)
    tabla = Table(filas, colWidths=[9.5 * cm, 1.5 * cm, 1.5 * cm, 2 * cm, 2.5 * cm],
                  repeatRows=1)
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), paleta.color("fondo_de_cabecera")),
        ("TEXTCOLOR", (0, 0), (-1, 0), paleta.color("texto_sobre_cabecera")),
        ("ROWBACKGROUNDS", (0, 1), (-1, n), [colors.white, paleta.color("fila_alterna")]),
        ("GRID", (0, 0), (-1, n), 0.3, paleta.color("borde_de_tabla")),
        ("LINEBELOW", (0, 0), (-1, 0), 1, paleta.color("acento")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        # Separador antes del subtotal.
        ("LINEABOVE", (0, n + 1), (-1, n + 1), 0.8, secundario),
        # La fila del TOTAL, destacada.
        ("BACKGROUND", (0, n + 3), (-1, n + 3), paleta.color("fila_de_total")),
        ("LINEBELOW", (0, n + 3), (-1, n + 3), 1.5, paleta.color("exito")),
        ("FONTSIZE", (0, n + 3), (-1, n + 3), 11),
        # NOSPLIT SOLO sobre el bloque de totales, no sobre la tabla entera.
        #
        # Antes era `(0, 0), (-1, -1)`, es decir: prohibido cualquier salto de
        # pagina en la tabla. Y como la tabla lleva las lineas dentro, eso
        # significaba que una factura mas alta que una pagina NO SE PODIA
        # GENERAR: ReportLab lanzaba `LayoutError` y el endpoint devolvia un
        # 500. Medido: hasta 29 lineas salia, con 30 fallaba.
        #
        # Una factura mensual de tiempo y materiales con treinta conceptos —una
        # linea por persona y proyecto— es lo normal, asi que el fallo estaba al
        # alcance de cualquier cliente mediano.
        #
        # Acotarlo al bloque de totales conserva la intencion original —que el
        # subtotal, el IVA y el TOTAL no se separen entre si ni queden solos en
        # una hoja— y deja que el cuerpo de lineas se reparta entre paginas,
        # que es para lo que existe `repeatRows=1`.
        ("NOSPLIT", (0, n + 1), (-1, n + 3)),
    ]))
    return [tabla]


def _bloque_de_notas(notes, est: dict, paleta) -> list:
    if not notes:
        return []
    return [
        Spacer(1, 16),
        HRFlowable(width="100%", thickness=0.5,
                   color=paleta.color("linea_separadora"), spaceAfter=8),
        Paragraph("NOTAS", est["etiqueta"]),
        Paragraph(notes, est["nota"]),
    ]


def _pie_de_factura(generated_by: str, invoice_number: str, est: dict, paleta) -> list:
    return [
        Spacer(1, 20),
        HRFlowable(width="100%", thickness=0.5, color=paleta.color("acento"), spaceAfter=6),
        Paragraph(
            f"Generado por {generated_by} · "
            f"{datetime.now().strftime('%d/%m/%Y %H:%M')} · {invoice_number}",
            est["pie"],
        ),
    ]


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
    company_name: str = NOMBRE_COMPLETO_DEL_PRODUCTO,
    generated_by: str = NOMBRE_DEL_PRODUCTO,
    paleta=None,
    simbolo: Optional[str] = None,
) -> bytes:
    """
    Genera un PDF de factura y devuelve los bytes en formato PDF.
    """
    currency = currency or settings.DEFAULT_CURRENCY
    # El símbolo lo resuelve quien llama con el ajuste de su empresa
    # (`settings_service.simbolos_de_moneda(db, org)`); sin él, el ajuste global.
    if simbolo is None:
        from app.services.settings_service import simbolos_de_moneda
        simbolo = simbolos_de_moneda().get(str(currency).upper(), currency)
    # `paleta` la resuelve el llamador con `marca_de_organizacion()`, que es
    # quien tiene el `db` y el `organization_id`. Sin ella se usa la de
    # producto: los trabajos de fondo y los tests no tienen por que saber de
    # marca blanca.
    paleta = paleta or PALETA_DE_FACTURA
    est = _estilos_de_factura(paleta)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
    )

    elements = (
        _cabecera_de_factura(company_name, est, paleta)
        + _metadatos(invoice_number, issue_date, due_date, po_reference,
                     period_from, period_to, est)
        + _bloque_de_cliente(client_name, client_address, client_vat,
                             client_email, est, paleta)
        + _tabla_de_lineas(lines, simbolo, subtotal, tax_rate, tax_amount,
                           total, est, paleta)
        + _bloque_de_notas(notes, est, paleta)
        + _pie_de_factura(generated_by, invoice_number, est, paleta)
    )

    doc.build(elements)
    return buffer.getvalue()


def pdf_de_factura(db, inv, lineas=None, *, org_id=None, company_name: str = NOMBRE_COMPLETO_DEL_PRODUCTO,
                   paleta=None, generated_by: str = NOMBRE_DEL_PRODUCTO) -> bytes:
    """El PDF de una `Invoice` guardada: la unica traduccion fila → `generate_invoice_pdf`.

    Auditoria 2026-11 (hallazgo 23). La misma traduccion (lineas, moneda y su
    simbolo, datos fiscales) estaba copiada en `GET /invoices/{id}/pdf` y en
    `GET /billing-reports/invoices/{id}/pdf`, y `POST /pdf/export` con
    `export_type=invoice` tenia ademas su propio dibujo de factura, sin NIF ni
    direccion y con `€` fijo. Los tres pasan ahora por aqui.
    """
    from app.services.formato_regional import simbolo_de_moneda

    if lineas is None:
        lineas = sorted(inv.lines or [], key=lambda x: (x.order or 0))
    moneda = (getattr(inv, "currency", None) or settings.DEFAULT_CURRENCY).upper()
    org = org_id if org_id is not None else getattr(inv, "organization_id", None)
    return generate_invoice_pdf(
        simbolo=simbolo_de_moneda(db, org, moneda=moneda),
        invoice_number=inv.number,
        issue_date=inv.issue_date,
        due_date=inv.due_date,
        client_name=inv.client_name or "",
        client_address=inv.client_address,
        client_vat=inv.client_vat,
        client_email=inv.client_email,
        lines=[
            {
                "description": ln.description,
                "unit": ln.unit,
                "quantity": ln.quantity,
                "unit_price": ln.unit_price,
                "amount": ln.amount,
                "discount_pct": ln.discount_pct,
            }
            for ln in lineas
        ],
        subtotal=inv.subtotal or 0,
        tax_rate=inv.tax_rate or 0,
        tax_amount=inv.tax_amount or 0,
        total=inv.total or 0,
        currency=inv.currency or settings.DEFAULT_CURRENCY,
        notes=inv.notes,
        po_reference=inv.po_reference,
        period_from=inv.period_from,
        period_to=inv.period_to,
        company_name=company_name,
        paleta=paleta,
        generated_by=generated_by,
    )
