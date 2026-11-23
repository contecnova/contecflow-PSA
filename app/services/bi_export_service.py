"""
BI Export Service — Excel avanzado + PowerPoint con charts
=============================================================
Genera informes descargables con:
- Excel: tablas nombradas, fórmulas (SUM/AVERAGE), formato condicional, charts integrados
- PowerPoint: diapositivas de portada, KPIs, gráficos de barras/línea con python-pptx

Dependencias:
  openpyxl==3.1.2  (ya en requirements.txt)
  python-pptx>=1.0.2  (nuevo en requirements.txt)
  pandas==2.2.3    (nuevo en requirements.txt)
"""
from __future__ import annotations

import io
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from app.core.celdas_seguras import fila_segura, neutralizar_formula
from app.core.constantes import NOMBRE_DEL_PRODUCTO
from app.core.codigos_de_error import error

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _texto_del_periodo(periodo=None, period_days: int | None = None, idioma: str | None = None) -> str:
    """«desde – hasta» del periodo pedido (o «últimos N días», legado).

    18-11-2026: fechas en el formato de `idioma` (antes `%d/%m/%Y` fijo).
    """
    from app.services.formato_regional import formatear_fecha
    from app.services.textos_de_salida import texto
    if periodo is not None:
        return f"{formatear_fecha(periodo.fecha_desde, idioma)} – {formatear_fecha(periodo.fecha_hasta, idioma)}"
    return texto("bi.ultimos_dias", idioma, n=period_days or 180)


def _periodo_de_dias(period_days: int):
    """Compatibilidad: ``period_days`` como periodo mensual hasta ahora."""
    from app.core.periodo import SOLO_MES, resolver_periodo
    return resolver_periodo(dias=period_days or 180, admitidas=SOLO_MES, serie=False)


def _get_kpi_data(db: Session, org_id: str, period_days: int = 180, periodo=None) -> dict:
    """Cifras del periodo, por mes, calculadas de la base.

    Periodo libre (16-11-2026). Antes se leía una instantánea
    ``bi.etl.sync_data.internal.<org>`` que ningún conector escribe y, sin
    ella, se exportaban **cifras de demostración** (seis meses inventados); el
    periodo solo cambiaba la etiqueta. Ahora todo sale del periodo pedido:

    * ingresos: suma de ``Invoice.total`` por ``issue_date`` (sin borradores ni
      anuladas);
    * tickets: creados en el periodo; SLA = (tickets − incumplidos) / tickets
      de cada mes (``None`` si ese mes no hubo tickets: no es un 0 %);
    * resolución media: horas entre creación y resolución de los tickets del
      periodo ya resueltos;
    * proyectos activos: los que están activos ahora (es un estado, no un
      acumulado del periodo).

    La empresa la pone el filtro automático de la sesión (no se repite aquí).
    Tramos mensuales con la agrupación común (``expresion_de_bucket``).
    """
    from sqlalchemy import func

    from app.core.periodo import expresion_de_bucket, filtro_de_periodo
    from app.models.billing_reports import Invoice, InvoiceStatus
    from app.models.project import Project, ProjectStatus
    from app.models.service_desk import Ticket
    from app.models.service_desk._enums import ESTADOS_DE_TICKET_RESUELTOS

    p = periodo if periodo is not None else _periodo_de_dias(period_days)
    claves = p.claves()

    mes_factura = expresion_de_bucket(db, Invoice.issue_date, p).label("clave")
    ingresos = dict(
        db.query(mes_factura, func.sum(Invoice.total))
        .filter(filtro_de_periodo(Invoice.issue_date, p),
                Invoice.status.notin_([InvoiceStatus.draft, InvoiceStatus.cancelled]))
        .group_by(mes_factura).all()
    )

    tickets_por_mes = {k: 0 for k in claves}
    incumplidos_por_mes = {k: 0 for k in claves}
    horas_de_resolucion = []
    for creado, resuelto, estado, sla in (
        db.query(Ticket.created_at, Ticket.resolved_at, Ticket.status, Ticket.sla_resolution_status)
        .filter(filtro_de_periodo(Ticket.created_at, p)).all()
    ):
        k = p.clave(creado)
        if k not in tickets_por_mes:
            continue
        tickets_por_mes[k] += 1
        if getattr(sla, "value", sla) == "breached":
            incumplidos_por_mes[k] += 1
        valor_estado = getattr(estado, "value", estado)
        if valor_estado in ESTADOS_DE_TICKET_RESUELTOS and resuelto and creado:
            r = resuelto if resuelto.tzinfo else resuelto.replace(tzinfo=timezone.utc)
            c = creado if creado.tzinfo else creado.replace(tzinfo=timezone.utc)
            horas_de_resolucion.append((r - c).total_seconds() / 3600)

    revenue = [round(float(ingresos.get(k) or 0), 2) for k in claves]
    tickets = [tickets_por_mes[k] for k in claves]
    sla = [round((tickets_por_mes[k] - incumplidos_por_mes[k]) / tickets_por_mes[k], 4) if tickets_por_mes[k] else None
           for k in claves]
    abiertos = db.query(func.count(Project.id)).filter(Project.status == ProjectStatus.active).scalar() or 0
    return {
        "labels": [f"{k[5:7]}/{k[:4]}" for k in claves],
        "revenue": revenue,
        "tickets": tickets,
        "sla_compliance": sla,
        "open_projects": int(abiertos),
        "total_revenue_period": round(sum(revenue), 2),
        "avg_resolution_hours": round(sum(horas_de_resolucion) / len(horas_de_resolucion), 1) if horas_de_resolucion else 0,
    }


def _sla_medio(sla: list):
    """Media de los meses con tickets (los meses sin tickets no son un 0 %)."""
    medidos = [v for v in sla if v is not None]
    return sum(medidos) / len(medidos) if medidos else None


def _pct(v):
    return round(v * 100, 1) if v is not None else None


# ── Excel Export ──────────────────────────────────────────────────────────────

def _openpyxl_bi():
    """Los nombres de openpyxl que hace falta aquí, o un 500 con motivo."""
    try:
        import openpyxl
        from openpyxl.chart import BarChart, LineChart, Reference
        from openpyxl.styles import Font, PatternFill
        from openpyxl.worksheet.table import Table, TableStyleInfo
    except ImportError as exc:
        raise error(500, "dependencia_no_instalada", detail=f"openpyxl no instalado: {exc}", paquete="openpyxl") from exc
    return openpyxl, BarChart, LineChart, Reference, Font, PatternFill, Table, TableStyleInfo


def _cabecera_con_estilo(ws, fila: int) -> None:
    """Pinta una fila como cabecera de tabla.

    Auditoría 2026-09 (hallazgo 18): las tres hojas de este libro repetían
    estas cuatro líneas.
    """
    _, _, _, _, Font, PatternFill, _, _ = _openpyxl_bi()
    for celda in ws[fila]:
        celda.fill = PatternFill(start_color="1565C0", end_color="1565C0", fill_type="solid")
        celda.font = Font(color="FFFFFF", bold=True)


def _hoja_de_resumen(wb, data: dict, *, report_title: str, texto_periodo: str,
                     tickets: list, sla: list, simbolo: str = "¤"):
    """La hoja de KPIs, con su tabla con nombre."""
    _, _, _, _, Font, _, Table, TableStyleInfo = _openpyxl_bi()

    ws = wb.active
    ws.title = "Resumen"
    ws["A1"] = neutralizar_formula(report_title)
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = f"Período: {texto_periodo}  |  Generado: {_utcnow()[:10]}"
    ws["A2"].font = Font(italic=True, size=10)
    ws.append([])
    ws.append(["KPI", "Valor"])
    _cabecera_con_estilo(ws, 4)

    filas = [
        [f"Ingresos totales ({simbolo})", data.get("total_revenue_period", 0)],
        ["Tickets gestionados", sum(tickets) if tickets else 0],
        # «N/A» y no 0: sin medidas de SLA no hay cumplimiento del 0 %, hay
        # ausencia de dato.
        ["Cumplimiento SLA promedio", f"{_sla_medio(sla) * 100:.1f}%" if _sla_medio(sla) is not None else "N/A"],
        ["Proyectos activos", data.get("open_projects", 0)],
        ["Resolución media (h)", data.get("avg_resolution_hours", 0)],
    ]
    for fila in filas:
        ws.append(fila_segura(fila))

    tabla = Table(displayName="TablaKPIs", ref=f"A4:B{4 + len(filas)}")
    tabla.tableStyleInfo = TableStyleInfo(name="TableStyleMedium9", showRowStripes=True)
    ws.add_table(tabla)
    ws.column_dimensions["A"].width = 35
    ws.column_dimensions["B"].width = 20
    return ws


def _graficos_mensuales(ws, n: int, simbolo: str = "¤") -> None:
    """Barras de ingresos y línea de cumplimiento de SLA sobre la hoja mensual."""
    _, BarChart, LineChart, Reference, _, _, _, _ = _openpyxl_bi()

    categorias = Reference(ws, min_col=1, min_row=2, max_row=n + 1)

    barras = BarChart()
    barras.type = "col"
    barras.title = "Ingresos Mensuales"
    barras.y_axis.title = simbolo
    barras.x_axis.title = "Mes"
    barras.add_data(Reference(ws, min_col=2, min_row=1, max_row=n + 1), titles_from_data=True)
    barras.set_categories(categorias)
    barras.shape = 4
    ws.add_chart(barras, "F2")

    linea = LineChart()
    linea.title = "Cumplimiento SLA (%)"
    linea.add_data(Reference(ws, min_col=4, min_row=1, max_row=n + 1), titles_from_data=True)
    linea.set_categories(categorias)
    ws.add_chart(linea, "F20")


def _hoja_mensual(wb, labels: list, revenue: list, tickets: list, sla: list, simbolo: str = "¤") -> int:
    """La hoja de datos mensuales, con totales por fórmula y sus gráficos.

    Los totales se escriben como **fórmulas de Excel** y no como números: quien
    abra el libro y edite una fila ve el total actualizarse, que es lo que
    espera de una hoja de cálculo.
    """
    _, _, _, _, Font, _, Table, TableStyleInfo = _openpyxl_bi()

    ws = wb.create_sheet("Datos Mensuales")
    ws.append(["Mes", f"Ingresos ({simbolo})", "Tickets", "SLA (%)"])
    _cabecera_con_estilo(ws, 1)

    n = min(len(labels), len(revenue), len(tickets), len(sla))
    for i in range(n):
        ws.append(fila_segura([labels[i], revenue[i], tickets[i], _pct(sla[i])]))

    total = n + 2
    ws[f"A{total}"] = "TOTAL"
    ws[f"A{total}"].font = Font(bold=True)
    ws[f"B{total}"] = f"=SUM(B2:B{n + 1})"
    ws[f"C{total}"] = f"=SUM(C2:C{n + 1})"
    # El SLA se promedia, no se suma: sumar porcentajes no significa nada.
    ws[f"D{total}"] = f"=AVERAGE(D2:D{n + 1})"

    if n > 0:
        tabla = Table(displayName="TablaIngresosMensuales", ref=f"A1:D{n + 1}")
        tabla.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
        ws.add_table(tabla)
        _graficos_mensuales(ws, n, simbolo)

    for col in ("A", "B", "C", "D"):
        ws.column_dimensions[col].width = 18
    return n


def export_dashboard_excel(
    db: Session,
    org_id: str,
    period_days: int = 180,
    periodo=None,
    report_title: str = f"Informe BI {NOMBRE_DEL_PRODUCTO}",
) -> bytes:
    """Libro de Excel con tablas con nombre, fórmulas y gráficos.

    Devuelve los bytes del `.xlsx`.
    """
    openpyxl, *_ = _openpyxl_bi()

    if periodo is not None:
        period_days = periodo.dias_enteros
    from app.services.formato_regional import idioma_de_salida
    texto_periodo = _texto_del_periodo(periodo, period_days, idioma_de_salida(db, org_id=org_id))
    data = _get_kpi_data(db, org_id, period_days, periodo=periodo)
    labels = data.get("labels", [])
    revenue = data.get("revenue", [])
    tickets = data.get("tickets", [])
    sla = data.get("sla_compliance", [])

    from app.services.formato_regional import simbolo_de_moneda
    simbolo = simbolo_de_moneda(db, org_id)
    wb = openpyxl.Workbook()
    _hoja_de_resumen(
        wb, data, report_title=report_title, texto_periodo=texto_periodo,
        tickets=tickets, sla=sla, simbolo=simbolo,
    )
    n = _hoja_mensual(wb, labels, revenue, tickets, sla, simbolo)

    ws_sla = wb.create_sheet("Tickets SLA")
    ws_sla.append(["Mes", "Tickets", "SLA (%)"])
    _cabecera_con_estilo(ws_sla, 1)
    for i in range(n):
        ws_sla.append(fila_segura([labels[i], tickets[i], _pct(sla[i])]))

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


# ── PowerPoint Export ─────────────────────────────────────────────────────────

def export_dashboard_pptx(
    db: Session,
    org_id: str,
    period_days: int = 180,
    periodo=None,
    report_title: str = f"Informe BI {NOMBRE_DEL_PRODUCTO}",
) -> bytes:
    """Generate a PowerPoint presentation with KPI slides and embedded charts.

    Returns raw bytes of the .pptx file.
    """
    try:
        from pptx import Presentation
        from pptx.chart.data import ChartData
        from pptx.dml.color import RGBColor
        from pptx.enum.chart import XL_CHART_TYPE
        from pptx.util import Inches, Pt
    except ImportError as exc:
        raise error(500, "dependencia_no_instalada", detail=f"python-pptx no instalado: {exc}", paquete="python-pptx") from exc

    if periodo is not None:
        period_days = periodo.dias_enteros
    from app.services.formato_regional import idioma_de_salida
    texto_periodo = _texto_del_periodo(periodo, period_days, idioma_de_salida(db, org_id=org_id))
    data = _get_kpi_data(db, org_id, period_days, periodo=periodo)
    labels = data.get("labels", [])
    revenue = data.get("revenue", [])
    tickets = data.get("tickets", [])
    sla = data.get("sla_compliance", [])
    from app.services.formato_regional import formatear_importe, simbolo_de_moneda
    simbolo = simbolo_de_moneda(db, org_id)

    prs = Presentation()
    prs.slide_width = Inches(13.33)
    prs.slide_height = Inches(7.5)

    blank_layout = prs.slide_layouts[6]  # blank
    title_layout = prs.slide_layouts[0]  # title slide

    # ── Slide 1: Title ────────────────────────────────────────────────────────
    slide = prs.slides.add_slide(title_layout)
    title_tf = slide.shapes.title
    subtitle_tf = slide.placeholders[1]
    title_tf.text = report_title
    subtitle_tf.text = f"Período: {texto_periodo}  |  {_utcnow()[:10]}"

    # ── Slide 2: KPI summary ──────────────────────────────────────────────────
    slide2 = prs.slides.add_slide(blank_layout)
    txBox = slide2.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(12), Inches(1))
    tf = txBox.text_frame
    tf.text = "KPIs Clave"
    tf.paragraphs[0].runs[0].font.size = Pt(28)
    tf.paragraphs[0].runs[0].font.bold = True

    kpis = [
        ("Ingresos totales", formatear_importe(data.get('total_revenue_period', 0), simbolo)),
        ("Proyectos activos", str(data.get("open_projects", 0))),
        ("Resolución media", f"{data.get('avg_resolution_hours', 0):.1f} h"),
        ("Cumpl. SLA prom.", f"{_sla_medio(sla) * 100:.1f}%" if _sla_medio(sla) is not None else "N/A"),
    ]
    x_pos = Inches(0.5)
    for label, value in kpis:
        tb = slide2.shapes.add_textbox(x_pos, Inches(1.8), Inches(2.8), Inches(1.8))
        frame = tb.text_frame
        frame.word_wrap = True
        p1 = frame.paragraphs[0]
        p1.text = value
        p1.runs[0].font.size = Pt(24)
        p1.runs[0].font.bold = True
        p1.runs[0].font.color.rgb = RGBColor(0x15, 0x65, 0xC0)
        frame.add_paragraph().text = label
        x_pos += Inches(3.1)

    # ── Slide 3: Revenue bar chart ────────────────────────────────────────────
    if labels and revenue:
        slide3 = prs.slides.add_slide(blank_layout)
        txBox3 = slide3.shapes.add_textbox(Inches(0.5), Inches(0.2), Inches(12), Inches(0.7))
        txBox3.text_frame.text = "Ingresos Mensuales"
        txBox3.text_frame.paragraphs[0].runs[0].font.size = Pt(22)
        txBox3.text_frame.paragraphs[0].runs[0].font.bold = True

        chart_data = ChartData()
        chart_data.categories = labels[:len(revenue)]
        chart_data.add_series(f"Ingresos ({simbolo})", revenue[:len(labels)])
        chart = slide3.shapes.add_chart(
            XL_CHART_TYPE.COLUMN_CLUSTERED,
            Inches(0.5), Inches(1.0), Inches(12.0), Inches(5.8),
            chart_data,
        ).chart
        chart.has_title = True
        chart.chart_title.text_frame.text = f"Ingresos por Mes ({simbolo})"

    # ── Slide 4: SLA line chart ───────────────────────────────────────────────
    if labels and any(v is not None for v in sla):
        slide4 = prs.slides.add_slide(blank_layout)
        txBox4 = slide4.shapes.add_textbox(Inches(0.5), Inches(0.2), Inches(12), Inches(0.7))
        txBox4.text_frame.text = "Cumplimiento SLA Mensual"
        txBox4.text_frame.paragraphs[0].runs[0].font.size = Pt(22)
        txBox4.text_frame.paragraphs[0].runs[0].font.bold = True

        sla_chart_data = ChartData()
        sla_chart_data.categories = labels[:len(sla)]
        sla_chart_data.add_series("SLA (%)", [_pct(v) for v in sla[:len(labels)]])
        chart4 = slide4.shapes.add_chart(
            XL_CHART_TYPE.LINE,
            Inches(0.5), Inches(1.0), Inches(12.0), Inches(5.8),
            sla_chart_data,
        ).chart
        chart4.has_title = True
        chart4.chart_title.text_frame.text = "Cumplimiento SLA (%)"

    # ── Slide 5: Ticket volume ────────────────────────────────────────────────
    if labels and tickets:
        slide5 = prs.slides.add_slide(blank_layout)
        txBox5 = slide5.shapes.add_textbox(Inches(0.5), Inches(0.2), Inches(12), Inches(0.7))
        txBox5.text_frame.text = "Volumen de Tickets"
        txBox5.text_frame.paragraphs[0].runs[0].font.size = Pt(22)
        txBox5.text_frame.paragraphs[0].runs[0].font.bold = True

        tickets_data = ChartData()
        tickets_data.categories = labels[:len(tickets)]
        tickets_data.add_series("Tickets", tickets[:len(labels)])
        chart5 = slide5.shapes.add_chart(
            XL_CHART_TYPE.BAR_CLUSTERED,
            Inches(0.5), Inches(1.0), Inches(12.0), Inches(5.8),
            tickets_data,
        ).chart
        chart5.has_title = True
        chart5.chart_title.text_frame.text = "Tickets Gestionados por Mes"

    buf = io.BytesIO()
    prs.save(buf)
    buf.seek(0)
    return buf.read()
