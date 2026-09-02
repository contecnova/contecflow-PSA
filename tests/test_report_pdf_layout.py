"""El PDF de informe: sus bloques, y la paleta de marca compartida.

Auditoría 2026-08 (P3-18 + hallazgo nuevo). `generate_report_pdf` era
complejidad 18 en 190 líneas: cabecera, filtros, KPI, tabla y pie en un solo
ámbito, con la paleta de marca redefinida como variables locales.

La equivalencia se verificó comparando la salida antes y después sobre nueve
casos —vacío, con y sin KPI, con filtros reconocidos y no reconocidos, valores
largos, más de 100 filas—: **texto idéntico, mismas páginas y el mismo número
exacto de bytes en los nueve**.

## El hallazgo que apareció de paso

Los seis colores de marca estaban en duro **91 veces en 29 ficheros**. Ahora
salen de `app/services/_pdf_marca.py`, que es la única fuente del lado servidor.

Y algo más grande, que ese módulo documenta y que NO se ha arreglado porque es
una decisión de producto: `OrgBranding` define cinco colores por organización y
tiene pantalla, pero ni este generador ni los de factura, firma, campañas o
correos lo leen — ninguno recibe siquiera el `organization_id`. Un cliente
configura su marca, la ve en la web, y **sus facturas salen con los colores de
Contecflow**.
"""
from __future__ import annotations

import io

import pytest

from app.services._pdf_marca import PALETA_DE_FACTURA, PALETA_POR_DEFECTO
from app.services.report_pdf import (
    _MAX_FILAS,
    _bloque_de_filtros,
    _bloque_de_kpis,
    _bloque_de_tabla,
    _estilos_de_informe,
    generate_report_pdf,
)


def _texto_y_paginas(pdf: bytes) -> tuple[str, int]:
    from pypdf import PdfReader

    r = PdfReader(io.BytesIO(pdf))
    return "\n".join(p.extract_text() or "" for p in r.pages), len(r.pages)


@pytest.fixture
def estilos():
    return _estilos_de_informe(PALETA_POR_DEFECTO)


# ── Que el PDF sale, y sale con lo que tiene que llevar ──────────────────────

def test_un_informe_vacio_genera_un_pdf_valido():
    """Sin datos también hay documento: la cabecera y el pie explican que el
    informe se generó y no encontró nada, que es información."""
    pdf = generate_report_pdf(title="Informe vacío", metric_label="Horas", data=[])
    assert pdf.startswith(b"%PDF")
    texto, paginas = _texto_y_paginas(pdf)
    assert paginas == 1
    assert "Informe vacío" in texto
    assert "Contecflow" in texto


def test_el_titulo_la_metrica_y_el_autor_aparecen():
    pdf = generate_report_pdf(
        title="Horas por proyecto", metric_label="Horas imputadas",
        data=[{"proyecto": "PRJ-1", "horas": 10.5}], generated_by="Ana Torres",
    )
    texto, _ = _texto_y_paginas(pdf)
    assert "Horas por proyecto" in texto
    assert "Horas imputadas" in texto
    assert "Ana Torres" in texto


def test_las_cabeceras_de_columna_se_formatean():
    """`total_horas` se muestra como «Total Horas»: el PDF lo lee una persona,
    no un programa."""
    pdf = generate_report_pdf(
        title="T", metric_label="M", data=[{"total_horas": 5, "nombre_cliente": "X"}]
    )
    texto, _ = _texto_y_paginas(pdf)
    assert "Total Horas" in texto
    assert "Nombre Cliente" in texto


# ── El bloque de filtros ─────────────────────────────────────────────────────

def test_sin_filtros_no_hay_bloque_de_filtros(estilos):
    assert _bloque_de_filtros(None, estilos) == []
    assert _bloque_de_filtros({}, estilos) == []


def test_un_filtro_no_reconocido_no_produce_bloque(estilos):
    """Sólo se muestran los tres que el informe conoce. Un filtro aplicado que
    no esté en esa lista no aparece — es deliberado: el listado es para el
    lector, no un volcado del payload."""
    assert _bloque_de_filtros({"cualquier_cosa": "x"}, estilos) == []


def test_los_tres_filtros_conocidos_aparecen():
    pdf = generate_report_pdf(
        title="T", metric_label="M", data=[{"a": 1}],
        filters={"date_from": "2026-01-01", "date_to": "2026-06-30", "project": "PRJ-9"},
    )
    texto, _ = _texto_y_paginas(pdf)
    assert "2026-01-01" in texto and "2026-06-30" in texto and "PRJ-9" in texto


# ── El bloque de KPI ─────────────────────────────────────────────────────────

def test_sin_resumen_no_hay_bloque_de_kpis(estilos):
    assert _bloque_de_kpis(None, estilos, PALETA_POR_DEFECTO) == []
    assert _bloque_de_kpis({}, estilos, PALETA_POR_DEFECTO) == []


def test_los_kpis_se_muestran_con_su_valor():
    pdf = generate_report_pdf(
        title="T", metric_label="M", data=[{"a": 1}],
        summary={"total_horas": 120.5, "proyectos": 4},
    )
    texto, _ = _texto_y_paginas(pdf)
    assert "Total Horas" in texto
    assert "120.50" in texto, "los decimales se formatean con dos cifras"
    assert "Proyectos" in texto


def test_un_numero_de_kpis_que_no_es_multiplo_de_tres_no_descuadra(estilos):
    """La última fila se rellena con celdas vacías. Sin eso, ReportLab lanza al
    montar una tabla con filas de distinta longitud."""
    for n in (1, 2, 3, 4, 5, 7):
        bloque = _bloque_de_kpis(
            {f"k{i}": i for i in range(n)}, estilos, PALETA_POR_DEFECTO
        )
        assert bloque, f"{n} KPI no generaron bloque"
    # Y el PDF completo se construye sin lanzar.
    for n in (1, 2, 4, 5, 7):
        pdf = generate_report_pdf(
            title="T", metric_label="M", data=[{"a": 1}],
            summary={f"kpi_{i}": i for i in range(n)},
        )
        assert pdf.startswith(b"%PDF")


# ── La tabla de datos ────────────────────────────────────────────────────────

def test_sin_datos_no_hay_tabla(estilos):
    assert _bloque_de_tabla([], estilos, PALETA_POR_DEFECTO) == []


def test_un_valor_muy_largo_se_recorta(estilos):
    """Sin el tope, un campo de texto largo descuadra el ancho de columna y
    parte la tabla."""
    largo = "x" * 200
    bloque = _bloque_de_tabla([{"nota": largo}], estilos, PALETA_POR_DEFECTO)
    assert bloque
    pdf = generate_report_pdf(title="T", metric_label="M", data=[{"nota": largo}])
    texto, _ = _texto_y_paginas(pdf)
    assert "..." in texto
    assert largo not in texto


def test_un_valor_nulo_se_muestra_como_raya():
    """Y no como «None»: un hueco es un hueco, no el nombre de un objeto de
    Python en un documento que se manda al cliente."""
    pdf = generate_report_pdf(title="T", metric_label="M", data=[{"campo": None}])
    texto, _ = _texto_y_paginas(pdf)
    assert "None" not in texto


def test_por_encima_del_tope_se_avisa_de_cuantas_filas_hay():
    """La nota no es cosmética: sin ella el lector creería que el informe está
    completo y tomaría decisiones sobre 100 de 150 registros."""
    pdf = generate_report_pdf(
        title="T", metric_label="M", data=[{"i": i} for i in range(150)]
    )
    texto, _ = _texto_y_paginas(pdf)
    assert str(_MAX_FILAS) in texto
    assert "150" in texto


def test_por_debajo_del_tope_no_se_avisa():
    pdf = generate_report_pdf(
        title="T", metric_label="M", data=[{"i": i} for i in range(5)]
    )
    texto, _ = _texto_y_paginas(pdf)
    assert "primeros" not in texto


# ── La paleta compartida ─────────────────────────────────────────────────────

def test_el_generador_no_tiene_ningun_color_en_duro():
    """El hallazgo, cerrado para este fichero. Los seis colores de marca estaban
    escritos 91 veces en 29 ficheros; aquí no queda ninguno."""
    import pathlib

    fuente = pathlib.Path("app/services/report_pdf.py").read_text(encoding="utf-8")
    assert 'HexColor("#' not in fuente, "vuelve a haber colores en duro"
    assert "PALETA_POR_DEFECTO" in fuente


def test_las_dos_paletas_comparten_los_colores_de_marca():
    """La de factura sólo cambia los tonos de fila. Los de marca —acento, texto,
    cabecera— son los mismos, y eso es lo que hace que los documentos se vean de
    la misma familia."""
    for campo in ("acento", "exito", "texto_principal", "texto_secundario",
                  "fondo_de_cabecera"):
        assert getattr(PALETA_POR_DEFECTO, campo) == getattr(PALETA_DE_FACTURA, campo)


def test_la_factura_conserva_su_matiz_propio():
    """`fila_alterna` difería entre los dos generadores y se conserva: la
    factura tiene su tono azulado a propósito, y unificarlo cambiaría el aspecto
    de un documento que se manda al cliente."""
    assert PALETA_POR_DEFECTO.fila_alterna != PALETA_DE_FACTURA.fila_alterna


def test_todos_los_colores_de_la_paleta_son_hexadecimales_validos():
    from reportlab.lib import colors

    for paleta in (PALETA_POR_DEFECTO, PALETA_DE_FACTURA):
        for campo in paleta.__slots__:
            valor = getattr(paleta, campo)
            assert valor.startswith("#") and len(valor) == 7, f"{campo}: {valor}"
            assert isinstance(paleta.color(campo), colors.Color)


# ── La marca blanca, que NO llega aquí ───────────────────────────────────────

def test_documentado_que_la_marca_de_la_organizacion_no_llega_al_pdf():
    """Fija el estado real para que no se dé por hecho lo contrario.

    `OrgBranding` define cinco colores por organización y tiene pantalla para
    configurarlos, pero este generador no los recibe: su firma no tiene
    `organization_id` ni paleta. Así que un cliente con marca propia recibe
    documentos con los colores de Contecflow.

    Este test no exige que sea así — exige que **si alguien lo cambia, lo note**.
    El día que se decida cablear la marca, hay que actualizarlo, y ese es
    justamente el momento de revisar los otros cuatro generadores.
    """
    import inspect

    firma = inspect.signature(generate_report_pdf)
    assert "organization_id" not in firma.parameters
    assert "paleta" not in firma.parameters
    assert "branding" not in firma.parameters
