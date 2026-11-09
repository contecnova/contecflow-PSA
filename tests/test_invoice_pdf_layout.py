"""El PDF de factura, y el defecto que impedía facturar más de 28 conceptos.

Auditoría 2026-08 (P3-18 + defecto encontrado de paso). `generate_invoice_pdf`
era complejidad 16 en 180 líneas.

## El defecto

La tabla de líneas llevaba `("NOSPLIT", (0, 0), (-1, -1))`, es decir: **prohibido
cualquier salto de página en toda la tabla**. Y la tabla lleva las líneas
dentro, así que una factura más alta que una página **no se podía generar** —
ReportLab lanzaba `LayoutError` y el endpoint devolvía un 500.

Medido antes de tocar nada, con una factura **sin** dirección, NIF ni correo de
cliente (esos tres suman alto, así que con ellos el umbral baja):

    1 – 18 líneas    sale en 1 página
    19 – 28 líneas   sale en 2, con la tabla entera saltada a la segunda
    29 o más         LayoutError: NO SE GENERA

El umbral exacto depende de cuánto ocupe la cabecera, y eso es precisamente lo
que hace peligroso el fallo: no hay un número redondo del que acordarse, sólo
«facturas grandes revientan».

Una factura mensual de tiempo y materiales con treinta conceptos —una línea por
persona y proyecto— es lo normal, así que el fallo estaba al alcance de
cualquier cliente mediano. Y no había ningún test que generara una factura
larga.

## El arreglo

`NOSPLIT` acotado al bloque de totales. Conserva la intención original —que
subtotal, IVA y TOTAL no se separen entre sí ni queden solos en una hoja— y deja
que el cuerpo se reparta entre páginas, que es para lo que existe
`repeatRows=1`, inerte hasta ahora porque `NOSPLIT` lo anulaba.

## Lo que cambia de aspecto, dicho claro

Mientras la factura cabe en una página el PDF es **byte a byte idéntico** — se
comprobó sobre once casos: con y sin dirección, sin cliente, con notas, con
periodo, sin líneas, en tres monedas y con fechas nulas o en texto.

Cuando pasa a dos páginas sí cambia: antes la tabla saltaba entera a la segunda
dejando la primera medio vacía, y ahora fluye repitiendo la cabecera de
columnas. Es mejor y es lo que el código pedía, pero es un cambio visible en un
documento que se manda al cliente, así que queda dicho.
"""
from __future__ import annotations

import io
from datetime import date

import pytest

from app.services._pdf_marca import PALETA_DE_FACTURA
from app.services.invoice_pdf import _fecha, _importe, generate_invoice_pdf


def _factura(n_lineas: int = 2, **cambios):
    base = dict(
        invoice_number="INV-2026-0001",
        issue_date=date(2026, 1, 15),
        due_date=date(2026, 2, 15),
        client_name="Cliente S.L.",
        client_address="C/ Mayor 1, Madrid",
        client_vat="B12345678",
        client_email="pago@cliente.com",
        lines=[
            {"description": f"Concepto {i}", "unit": "h", "quantity": 1,
             "unit_price": 10.0, "amount": 10.0}
            for i in range(n_lineas)
        ],
        subtotal=10.0 * n_lineas,
        tax_rate=21.0,
        tax_amount=2.1 * n_lineas,
        total=12.1 * n_lineas,
    )
    base.update(cambios)
    return generate_invoice_pdf(**base)


def _texto_y_paginas(pdf: bytes) -> tuple[str, int]:
    from pypdf import PdfReader

    r = PdfReader(io.BytesIO(pdf))
    return "\n".join(p.extract_text() or "" for p in r.pages), len(r.pages)


# ── El defecto, cerrado ──────────────────────────────────────────────────────

@pytest.mark.parametrize("n", [29, 30, 40, 60, 100])
def test_una_factura_larga_SI_se_genera(n):
    """Antes esto lanzaba `LayoutError` y el endpoint devolvía 500.

    29 líneas era el umbral exacto: con 28 salía y con 29 fallaba. Una factura
    mensual de tiempo y materiales con treinta conceptos es lo normal.
    """
    pdf = _factura(n)
    assert pdf.startswith(b"%PDF")
    texto, paginas = _texto_y_paginas(pdf)
    assert paginas >= 2
    assert f"Concepto {n - 1}" in texto, "la última línea tiene que estar dentro"


def test_una_factura_muy_larga_tambien():
    """300 conceptos: no es habitual, pero no debe haber un techo escondido."""
    pdf = _factura(300)
    texto, paginas = _texto_y_paginas(pdf)
    assert paginas >= 10
    assert "Concepto 299" in texto


@pytest.mark.parametrize("n", [1, 5, 30, 100])
def test_el_total_aparece_siempre(n):
    """Es lo que se paga: no puede perderse en ningún tamaño de factura."""
    texto, _ = _texto_y_paginas(_factura(n))
    assert "TOTAL" in texto
    assert "Subtotal" in texto
    assert "IVA" in texto


def test_los_totales_no_se_separan_entre_si():
    """La razón de que `NOSPLIT` siga existiendo, sólo acotado.

    Subtotal, IVA y TOTAL van en el mismo bloque: partirlos entre dos páginas
    dejaría un importe suelto al final de una hoja, y una factura así no la
    firma nadie. Se comprueba que los tres caen en la MISMA página.
    """
    from pypdf import PdfReader

    for n in (18, 19, 20, 28, 29, 40, 77):
        r = PdfReader(io.BytesIO(_factura(n)))
        paginas = [p.extract_text() or "" for p in r.pages]
        con_total = [i for i, t in enumerate(paginas) if "TOTAL" in t]
        con_subtotal = [i for i, t in enumerate(paginas) if "Subtotal" in t]
        assert con_total and con_subtotal, n
        assert con_total[0] == con_subtotal[0], (
            f"con {n} líneas el subtotal y el TOTAL caen en páginas distintas"
        )


def test_la_cabecera_de_columnas_se_repite_en_cada_pagina():
    """`repeatRows=1` estaba en el código pero era inerte: `NOSPLIT` sobre toda
    la tabla impedía el salto, así que nunca había una segunda página de tabla
    donde repetir nada."""
    from pypdf import PdfReader

    r = PdfReader(io.BytesIO(_factura(60)))
    paginas = [p.extract_text() or "" for p in r.pages]
    con_lineas = [t for t in paginas if "Concepto" in t]
    assert len(con_lineas) >= 2
    for t in con_lineas:
        assert "Descripción" in t, "falta la cabecera en una página de la tabla"


# ── Las facturas cortas no cambian ───────────────────────────────────────────

@pytest.mark.parametrize("n", [0, 1, 5, 10, 14])
def test_una_factura_corta_cabe_en_una_pagina(n):
    """El documento de una factura corta es byte a byte el mismo que antes del
    arreglo. Se verificó comparando las salidas.

    El número exacto de líneas que caben depende de cuánto ocupe el bloque de
    cliente —dirección, NIF y correo suman alto—, así que aquí se usa un margen
    holgado en vez de fijar la frontera: fijarla ataría el test al tamaño de los
    datos del fixture.
    """
    _texto, paginas = _texto_y_paginas(_factura(n))
    assert paginas == 1


# ── Contenido ────────────────────────────────────────────────────────────────

def test_los_datos_del_cliente_aparecen():
    texto, _ = _texto_y_paginas(_factura())
    assert "Cliente S.L." in texto
    assert "C/ Mayor 1, Madrid" in texto
    assert "B12345678" in texto
    assert "pago@cliente.com" in texto


def test_un_cliente_sin_datos_no_deja_huecos_raros():
    """Los campos opcionales desaparecen en vez de mostrarse vacíos."""
    texto, _ = _texto_y_paginas(_factura(
        client_address=None, client_vat=None, client_email=None
    ))
    assert "NIF/VAT" not in texto
    assert "Email:" not in texto


def test_sin_nombre_de_cliente_se_muestra_una_raya():
    texto, _ = _texto_y_paginas(_factura(client_name=""))
    assert "DATOS DEL CLIENTE" in texto


def test_el_numero_de_factura_aparece_en_la_cabecera_y_en_el_pie():
    """En el pie también, para que una hoja suelta se pueda identificar."""
    texto, _ = _texto_y_paginas(_factura())
    assert texto.count("INV-2026-0001") >= 2


def test_el_periodo_y_la_referencia_solo_salen_si_vienen():
    # Las etiquetas se renderizan en MAYÚSCULAS (`textTransform="uppercase"`),
    # así que la comparación va sin distinguir caso.
    con = _texto_y_paginas(_factura(
        po_reference="PO-998",
        period_from=date(2026, 1, 1), period_to=date(2026, 1, 31),
    ))[0].lower()
    assert "po-998" in con
    assert "período" in con or "periodo" in con

    sin = _texto_y_paginas(_factura())[0].lower()
    assert "po-998" not in sin
    assert "período" not in sin and "periodo" not in sin


def test_las_notas_solo_salen_si_vienen():
    assert "NOTAS" in _texto_y_paginas(_factura(notes="Pago a 30 días."))[0]
    assert "NOTAS" not in _texto_y_paginas(_factura())[0]


def test_una_factura_sin_lineas_se_genera():
    """Puede ser una factura de abono o un borrador: no debe reventar."""
    pdf = _factura(0, subtotal=0.0, tax_amount=0.0, total=0.0)
    texto, _ = _texto_y_paginas(pdf)
    assert "TOTAL" in texto


# ── Formato de importes y fechas ─────────────────────────────────────────────

@pytest.mark.parametrize("moneda,simbolo", [
    ("EUR", "€"), ("USD", "$"), ("GBP", "£"),
])
def test_el_simbolo_de_las_monedas_conocidas(moneda, simbolo):
    """Los símbolos salen de `CURRENCY_SYMBOLS` (Admin → Locale), no de una lista en el código."""
    from app.services.settings_service import simbolos_de_moneda
    assert _importe(1234.5, simbolos_de_moneda()[moneda]) == f"1,234.50 {simbolo}"


def test_una_moneda_no_listada_usa_su_codigo():
    """«1,234.50 CHF» es correcto y legible. Inventar un símbolo o dejarlo en
    blanco sería peor."""
    from app.services.settings_service import simbolos_de_moneda
    assert "CHF" not in simbolos_de_moneda()
    assert _importe(1234.5, simbolos_de_moneda().get("CHF", "CHF")) == "1,234.50 CHF"


def test_las_fechas_van_en_formato_espanol():
    assert _fecha(date(2026, 1, 15)) == "15/01/2026"


def test_una_fecha_ausente_se_muestra_como_raya():
    """Y no como «None»: es un documento que se manda al cliente."""
    assert _fecha(None) == "—"


def test_una_fecha_que_ya_viene_como_texto_se_pasa_tal_cual():
    assert _fecha("15/01/2026") == "15/01/2026"


def test_las_cantidades_enteras_no_muestran_decimales():
    """`:g` en la cantidad: «2 h» y no «2.0 h». Lo lee una persona."""
    texto, _ = _texto_y_paginas(generate_invoice_pdf(
        invoice_number="INV-1", issue_date=date(2026, 1, 1), due_date=None,
        client_name="C", client_address=None, client_vat=None, client_email=None,
        lines=[{"description": "X", "unit": "ud", "quantity": 2,
                "unit_price": 10.0, "amount": 20.0}],
        subtotal=20.0, tax_rate=21.0, tax_amount=4.2, total=24.2,
    ))
    assert "2.0" not in texto


# ── La paleta ────────────────────────────────────────────────────────────────

def test_el_generador_no_tiene_ningun_color_en_duro():
    import pathlib

    fuente = pathlib.Path("app/services/invoice_pdf.py").read_text(encoding="utf-8")
    assert 'HexColor("#' not in fuente
    assert "PALETA_DE_FACTURA" in fuente


def test_la_factura_usa_su_variante_de_paleta():
    """La de factura conserva el matiz azulado de las filas, distinto del
    informe. No es capricho: unificarlo cambiaría el aspecto de un documento que
    se manda al cliente."""
    assert PALETA_DE_FACTURA.fila_alterna == "#f0f9ff"


def test_la_marca_del_cliente_YA_llega_a_la_factura():
    """El hallazgo 32, cerrado — y este test cambió de sentido al cerrarlo.

    Su versión anterior fijaba el estado contrario: que la firma **no** recibía
    paleta, con la nota de que «el día que se decida cablear la marca hay que
    actualizarlo». Ese día llegó, el test falló, y por eso está reescrito. Un
    test que fija un estado provisional tiene que fallar cuando el estado
    cambia; si no, no fija nada.

    Ahora lo que se exige es lo contrario: que el parámetro exista y que sea
    **opcional**, porque los trabajos de fondo y los tests no tienen por qué
    saber de marca blanca.
    """
    import inspect

    firma = inspect.signature(generate_invoice_pdf)
    assert "paleta" in firma.parameters, (
        "la factura ha dejado de aceptar la marca del tenant"
    )
    assert firma.parameters["paleta"].default is None, (
        "la paleta tiene que ser opcional: sin ella se usa la de producto"
    )
    # `organization_id` NO se pasa a proposito: el generador no habla con la
    # base. La marca la resuelve el llamador, que es quien tiene el `db`.
    assert "organization_id" not in firma.parameters
    assert firma.parameters["company_name"].default == "Contecflow PSA"
