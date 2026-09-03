"""La marca del cliente en los documentos que genera el sistema.

Auditoría 2026-08 (hallazgo 32). `OrgBranding` define cinco colores y un nombre
por organización y tiene pantalla para configurarlos, y **nada de eso llegaba a
los documentos**: el cliente configuraba su marca, la veía en la web, y sus
facturas salían con los colores y el nombre de Contecflow. Instancia del patrón
de la auditoría — un control escrito, con pantalla, conectado a nada.

Decisión de producto tomada: **el documento lleva la marca del tenant.**

## Por qué NO se mapean los cinco colores, y esto es lo que fijan los tests

Mapear los cinco uno a uno **rompe el documento**, de dos formas concretas:

| Color | Por defecto | Si se mapeara a… | Qué saldría |
|---|---|---|---|
| `text_color` | `#f8fafc` (claro, va sobre el fondo oscuro de la web) | `texto_principal` | **texto blanco sobre papel blanco**: factura ilegible, generada sin error |
| `secondary_color` | `#8b5cf6` (violeta saturado) | `fila_alterna` / `fila_de_total` | importes ilegibles sobre un tinte saturado |

Se sustituye **sólo lo que tiene significado inequívoco en un documento** —la
banda de cabecera de la tabla, el acento y el texto sobre esa banda— y los
tintes se quedan neutros. Un tinte neutro funciona debajo de cualquier tono de
marca; uno saturado no funciona debajo de nada.

## La legibilidad está demostrada, no probada a ojo

El contraste WCAG depende sólo de la luminancia relativa. Con blanco y negro
**puros** como candidatos, el peor caso está donde empatan: L = 0,1791, con
contraste **4,58** — por encima del 4,5 de AA. Así que para cualquier color de
marca hay siempre un texto legible y **no hace falta tocar el color del
cliente**. El test `test_el_suelo_de_contraste...` recorre los 256 grises para
comprobarlo, y `test_un_casi_negro_romperia_la_garantia` fija el detalle que lo
sostiene: si alguien «suaviza» el negro a `#111111`, el suelo baja a 4,35 y
aparece una banda de tonos medios sin solución.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services._pdf_marca import (
    CONTRASTE_MINIMO,
    PALETA_DE_FACTURA,
    PALETA_POR_DEFECTO,
    _contraste,
    _hex_valido,
    _texto_legible_sobre,
    marca_de_organizacion,
)


def _fila(**kw):
    m = MagicMock()
    m.app_name = kw.get("app_name", "Acme Ingeniería")
    m.primary_color = kw.get("primary_color", "#c0392b")
    m.secondary_color = kw.get("secondary_color", "#8b5cf6")
    m.accent_color = kw.get("accent_color", "#16a085")
    m.background_color = kw.get("background_color", "#0f172a")
    m.text_color = kw.get("text_color", "#f8fafc")
    return m


def _db_con(fila):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = fila
    return db


def _marca(fila, **kw):
    kw.setdefault("base", PALETA_DE_FACTURA)
    kw.setdefault("nombre_por_defecto", "Contecflow PSA")
    return marca_de_organizacion(_db_con(fila), "org-1", **kw)


# ── El color que escribe una persona en una pantalla ────────────────────────

@pytest.mark.parametrize("entrada,esperado", [
    ("#C0392B", "#c0392b"),
    ("c0392b", "#c0392b"),       # sin almohadilla
    ("  #c0392b  ", "#c0392b"),  # con espacios
    ("#FFF", "#ffffff"),         # tres dígitos se expanden
    ("#abc", "#aabbcc"),
])
def test_un_color_se_interpreta_aunque_venga_escrito_de_varias_formas(entrada, esperado):
    assert _hex_valido(entrada) == esperado


@pytest.mark.parametrize("basura", [
    None, "", "   ", "azul", "rgb(1,2,3)", "#12345", "#1234567", "#gggggg",
    "var(--primary)", 12345, [], "#", "0x00ff00",
])
def test_un_color_que_no_se_entiende_no_tumba_la_factura(basura):
    """El campo es `String(20)` y lo rellena una persona por pantalla. Nada de
    lo que escriba puede impedir emitir una factura: lo que no se entiende se
    ignora y se usa el color por defecto."""
    assert _hex_valido(basura) is None


# ── El contraste, calibrado ─────────────────────────────────────────────────

def test_el_contraste_de_blanco_sobre_negro_es_el_maximo():
    """21:1 es el máximo teórico de WCAG. Calibra el cálculo: si esto no diera
    21, toda la garantía estaría mal escalada."""
    assert _contraste("#ffffff", "#000000") == pytest.approx(21.0, abs=0.05)


def test_el_contraste_de_un_color_consigo_mismo_es_uno():
    assert _contraste("#c0392b", "#c0392b") == pytest.approx(1.0)


def test_el_contraste_es_simetrico():
    """Lo pide la definición: no depende de cuál se pase como fondo."""
    assert _contraste("#ffffff", "#c0392b") == pytest.approx(
        _contraste("#c0392b", "#ffffff"))


def test_EL_SUELO_DE_CONTRASTE_esta_por_encima_del_minimo_para_TODO_fondo():
    """La demostración, comprobada por barrido.

    El contraste depende sólo de la luminancia, así que el peor caso sobre todos
    los colores posibles es el peor caso sobre los grises. Se recorren los 256 y
    se comprueba que en ninguno el mejor texto baja del mínimo.
    """
    peor, peor_valor = None, 99.0
    for v in range(256):
        fondo = "#%02x%02x%02x" % (v, v, v)
        elegido = _texto_legible_sobre(fondo, None)
        c = _contraste(elegido, fondo)
        if c < peor_valor:
            peor, peor_valor = fondo, c
    assert peor_valor >= CONTRASTE_MINIMO, (
        "el fondo %s se queda en %.3f, por debajo de %.1f" % (peor, peor_valor,
                                                              CONTRASTE_MINIMO)
    )
    # El peor caso teórico está en 4,58; si el barrido diera mucho más, sería
    # que el cálculo no está midiendo lo que se cree.
    assert peor_valor < 5.0, (
        "el peor caso ha salido %.3f, demasiado alto: el cálculo no está "
        "encontrando el punto de empate entre blanco y negro" % peor_valor
    )


@pytest.mark.parametrize("fondo", ["#777777", "#787878", "#797979",
                                   "#7a7a7a", "#7b7b7b"])
def test_un_casi_negro_romperia_la_garantia(fondo):
    """El detalle que sostiene todo lo anterior, con la banda exacta.

    Son **cinco** fondos —de `#777777` a `#7b7b7b`— en los que el blanco y un
    «casi negro» tipo `#111111` **fallan los dos**, y sólo el negro puro cumple.
    Suavizar el negro parece cosmético y en esa banda deja la cabecera por
    debajo de AA, así que queda fijado con números: si alguien lo cambia, estos
    cinco casos fallan y dicen por qué.
    """
    assert _contraste("#ffffff", fondo) < CONTRASTE_MINIMO
    assert _contraste("#111111", fondo) < CONTRASTE_MINIMO
    assert _contraste("#000000", fondo) >= CONTRASTE_MINIMO
    # Y la guarda real elige, en efecto, el que cumple.
    assert _texto_legible_sobre(fondo, None) == "#000000"


def test_se_respeta_el_color_de_texto_del_cliente_si_se_lee():
    """El cliente eligió ese color: si funciona, se honra."""
    assert _contraste("#f8fafc", "#c0392b") >= CONTRASTE_MINIMO
    assert _texto_legible_sobre("#c0392b", "#f8fafc") == "#f8fafc"


def test_EL_CASO_QUE_IMPORTA_cabecera_clara_con_texto_claro():
    """El cliente pone amarillo de cabecera y blanco de texto.

    Sin guarda queda una cabecera ilegible en cada factura que emite, y nada
    falla. Con guarda se cambia a negro, que sí se lee.
    """
    elegido = _texto_legible_sobre("#ffe066", "#ffffff")
    assert elegido != "#ffffff"
    assert _contraste(elegido, "#ffe066") >= CONTRASTE_MINIMO


def test_con_cabecera_oscura_y_texto_oscuro_se_pasa_a_blanco():
    """El mismo problema por el otro lado."""
    elegido = _texto_legible_sobre("#111133", "#000000")
    assert _contraste(elegido, "#111133") >= CONTRASTE_MINIMO


# ── La marca de una organización ────────────────────────────────────────────

def test_la_marca_del_cliente_pinta_la_cabecera_el_acento_y_el_nombre():
    m = _marca(_fila(primary_color="#c0392b", accent_color="#16a085",
                     app_name="Acme Ingeniería"))
    assert m.paleta.fondo_de_cabecera == "#c0392b"
    assert m.paleta.acento == "#16a085"
    assert m.nombre == "Acme Ingeniería"


def test_EL_HALLAZGO_los_tintes_de_tabla_se_quedan_neutros():
    """`secondary_color` es un tono saturado. Puesto en un tinte de tabla —que
    va detrás del texto de los importes— los deja ilegibles. Que NO se mapee es
    la decisión, y este test la fija: si alguien lo cablea, falla aquí."""
    m = _marca(_fila(secondary_color="#8b5cf6"))
    assert m.paleta.fila_alterna == PALETA_DE_FACTURA.fila_alterna
    assert m.paleta.fila_de_total == PALETA_DE_FACTURA.fila_de_total
    assert m.paleta.borde_de_tabla == PALETA_DE_FACTURA.borde_de_tabla


def test_EL_HALLAZGO_el_texto_del_cuerpo_no_se_toca():
    """`text_color` vale `#f8fafc` por defecto porque en la web va sobre fondo
    oscuro. Mapearlo a `texto_principal` daría texto blanco sobre papel blanco:
    una factura ilegible que se genera sin error."""
    m = _marca(_fila(text_color="#f8fafc"))
    assert m.paleta.texto_principal == PALETA_DE_FACTURA.texto_principal
    assert m.paleta.texto_secundario == PALETA_DE_FACTURA.texto_secundario
    assert _contraste(m.paleta.texto_principal, "#ffffff") >= CONTRASTE_MINIMO, (
        "el texto del cuerpo ha dejado de leerse sobre papel blanco"
    )


def test_el_texto_de_la_cabecera_se_calcula_contra_la_cabecera_del_cliente():
    """Amarillo de cabecera y blanco de texto: el texto se cambia."""
    m = _marca(_fila(primary_color="#ffe066", text_color="#ffffff"))
    assert m.paleta.fondo_de_cabecera == "#ffe066"
    assert _contraste(m.paleta.texto_sobre_cabecera, "#ffe066") >= CONTRASTE_MINIMO


def test_el_color_de_marca_del_cliente_no_se_modifica():
    """No se oscurece ni se ajusta: la demostración del suelo de contraste dice
    que no hace falta, y cambiarle el color a un cliente sin necesidad sería
    peor que dejarlo."""
    for color in ("#c0392b", "#757575", "#ffe066", "#000000", "#ffffff",
                  "#16a085", "#8b5cf6"):
        m = _marca(_fila(primary_color=color))
        assert m.paleta.fondo_de_cabecera == color, (
            "se ha alterado el color de marca %s" % color
        )


# ── Las cuatro formas de degradar ───────────────────────────────────────────

def test_sin_organizacion_se_usa_la_base():
    """Trabajos de fondo y superadministrador no traen organización."""
    for vacio in (None, "", 0):
        m = marca_de_organizacion(MagicMock(), vacio, base=PALETA_DE_FACTURA,
                                  nombre_por_defecto="Contecflow PSA")
        assert m.paleta is PALETA_DE_FACTURA
        assert m.nombre == "Contecflow PSA"


def test_una_organizacion_sin_marca_configurada_usa_la_base():
    m = _marca(None)
    assert m.paleta is PALETA_DE_FACTURA
    assert m.nombre == "Contecflow PSA"


def test_si_la_consulta_de_marca_falla_se_emite_la_factura_igual():
    """Emitir la factura importa más que emitirla con la marca correcta."""
    db = MagicMock()
    db.query.side_effect = RuntimeError("la base ha fallado")
    m = marca_de_organizacion(db, "org-1", base=PALETA_DE_FACTURA,
                              nombre_por_defecto="Contecflow PSA")
    assert m.paleta is PALETA_DE_FACTURA
    assert m.nombre == "Contecflow PSA"


def test_una_marca_con_colores_ilegibles_cae_campo_a_campo():
    """Degrada por campo, no en bloque: un `accent_color` mal escrito no debe
    tirar también el `primary_color` que sí estaba bien."""
    m = _marca(_fila(primary_color="#c0392b", accent_color="verde-lima"))
    assert m.paleta.fondo_de_cabecera == "#c0392b", "el color válido se ha perdido"
    assert m.paleta.acento == PALETA_DE_FACTURA.acento


@pytest.mark.parametrize("nombre", [None, "", "   "])
def test_un_nombre_vacio_cae_al_por_defecto(nombre):
    """Un documento sin nombre de empresa en la cabecera no es aceptable."""
    m = _marca(_fila(app_name=nombre))
    assert m.nombre == "Contecflow PSA"


def test_la_base_por_defecto_es_la_paleta_de_producto():
    m = marca_de_organizacion(_db_con(None), "org-1")
    assert m.paleta is PALETA_POR_DEFECTO


# ── Inmutabilidad: varios documentos a la vez ───────────────────────────────

def test_la_paleta_sigue_siendo_inmutable():
    """Es un `frozen dataclass` a propósito: dos documentos generados a la vez
    no pueden pisarse la paleta."""
    m = _marca(_fila())
    #  es la de dataclasses; con `slots` puede llegar como
    # `AttributeError`, asi que se aceptan las dos y no un `Exception` ciego.
    from dataclasses import FrozenInstanceError
    with pytest.raises((FrozenInstanceError, AttributeError)):
        m.paleta.acento = "#000000"


def test_aplicar_la_marca_no_muta_la_paleta_base():
    """`replace()` devuelve una copia. Si mutara la base, la primera factura de
    un cliente le cambiaría la marca a todos los siguientes — y sólo se notaría
    en producción, con varios tenants."""
    antes = (PALETA_DE_FACTURA.fondo_de_cabecera, PALETA_DE_FACTURA.acento,
             PALETA_DE_FACTURA.texto_sobre_cabecera)
    _marca(_fila(primary_color="#c0392b", accent_color="#16a085"))
    assert (PALETA_DE_FACTURA.fondo_de_cabecera, PALETA_DE_FACTURA.acento,
            PALETA_DE_FACTURA.texto_sobre_cabecera) == antes


def test_dos_organizaciones_seguidas_no_se_contaminan():
    """El caso multi-tenant, que es donde esto se rompería de verdad."""
    a = _marca(_fila(primary_color="#c0392b", app_name="Acme"))
    b = _marca(_fila(primary_color="#1565c0", app_name="Beta"))
    assert (a.paleta.fondo_de_cabecera, a.nombre) == ("#c0392b", "Acme")
    assert (b.paleta.fondo_de_cabecera, b.nombre) == ("#1565c0", "Beta")


def test_una_sola_consulta_por_documento():
    """Colores y nombre salen de la misma fila. Resolverlos por separado serían
    dos consultas por cada documento que se genera."""
    db = _db_con(_fila())
    marca_de_organizacion(db, "org-1", base=PALETA_DE_FACTURA)
    assert db.query.call_count == 1
