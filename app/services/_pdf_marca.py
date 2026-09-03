"""La paleta de marca de los documentos generados: un solo sitio.

Auditoría 2026-08 (hallazgo 18 y hallazgo nuevo). Los seis colores de marca
estaban escritos en duro **91 veces repartidas por 29 ficheros**, y cada
generador de PDF los redefinía como variables locales. Un cambio de marca
obligaba a tocarlos todos y a acertar en los 29.

Este módulo es la fuente de verdad para la capa de documentos. No pretende ser
la única del producto —el frontend tiene su propio sistema de tokens CSS— pero
sí la única del lado servidor.

## La marca del cliente

`OrgBranding` (`app/models/white_label.py`) define cinco colores y un nombre por
organización. **Ya llegan a los documentos**: `marca_de_organizacion()` los
resuelve y los generadores los aceptan. La decisión de producto fue que el
documento lleva la marca del tenant, no la de la plataforma.

Lo que no se sustituye, y por qué, está en la nota de `marca_de_organizacion`:
mapear los cinco colores uno a uno rompe el documento.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from reportlab.lib import colors

_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PaletaDeDocumento:
    """Los colores que usa un documento generado.

    Se guardan como cadenas hexadecimales y no como objetos de ReportLab para
    que la paleta se pueda leer de la base o de la configuración sin acoplarla a
    la librería de PDF. `color()` hace la conversión.
    """

    acento: str
    exito: str
    texto_principal: str
    texto_secundario: str
    fondo_de_cabecera: str
    fila_alterna: str
    fila_de_total: str
    linea_separadora: str
    borde_de_tabla: str
    #: El texto que va ENCIMA de `fondo_de_cabecera`. Antes iba fijo en
    #: `colors.white` dentro de cada generador, lo que hacia imposible que una
    #: marca clara tuviera cabecera legible. Ver `_texto_legible_sobre`.
    texto_sobre_cabecera: str

    def color(self, nombre: str):
        """El color de ReportLab para uno de los campos de la paleta."""
        return colors.HexColor(getattr(self, nombre))


# La paleta de Contecflow. Los valores son los que ya estaban en los
# generadores; no se ha cambiado ninguno.
#
# `fila_alterna` y `fila_de_total` diferían entre el generador de informes y el
# de facturas —`#f8fafc` frente a `#f0f9ff`— y esa diferencia se conserva
# pasándolas por parámetro: la factura tiene su propio matiz azulado a
# propósito, y unificarlo cambiaría el aspecto de un documento que se manda al
# cliente.
PALETA_POR_DEFECTO = PaletaDeDocumento(
    acento="#00d4ff",
    exito="#00e5a0",
    texto_principal="#1a1a2e",
    texto_secundario="#6b7280",
    fondo_de_cabecera="#0f172a",
    fila_alterna="#f8fafc",
    fila_de_total="#e0faf5",
    linea_separadora="#e2e8f0",
    borde_de_tabla="#cbd5e1",
    texto_sobre_cabecera="#ffffff",
)

# La variante de facturación: mismo azul de marca, filas con matiz azulado.
PALETA_DE_FACTURA = PaletaDeDocumento(
    **{
        **{c: getattr(PALETA_POR_DEFECTO, c) for c in PALETA_POR_DEFECTO.__slots__},
        "fila_alterna": "#f0f9ff",
        "borde_de_tabla": "#dee6ef",
    }
)


# ── La marca del cliente en sus documentos ───────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 32). `OrgBranding` define cinco colores por
# organizacion y tiene pantalla, y ninguno llegaba a los documentos: el cliente
# configuraba su marca, la veia en la web, y sus facturas salian con los colores
# de Contecflow. Decision de producto tomada: **la factura lleva la marca del
# tenant**, no la de la plataforma.
#
# ## Por que NO se mapean los cinco colores
#
# Mapear los cinco uno a uno rompe el documento, y de dos formas concretas:
#
#   · `text_color` vale `#f8fafc` por defecto —texto CLARO, porque en la web va
#     sobre el fondo oscuro de la aplicacion—. Puesto en `texto_principal`
#     produce **texto blanco sobre papel blanco**: una factura ilegible que se
#     genera sin error;
#   · `secondary_color` es un tono saturado. Puesto en `fila_alterna` o
#     `fila_de_total`, que son tintes muy claros detras del texto de la tabla,
#     deja los importes ilegibles.
#
# Asi que se sustituye **solo lo que tiene significado inequivoco en un
# documento** —la banda de cabecera de la tabla, el acento y el texto sobre esa
# banda— y los tintes se quedan neutros. Un tinte neutro funciona debajo de
# cualquier tono de marca; uno saturado no funciona debajo de nada.
#
# ## Legibilidad: por que basta con elegir el texto y NO hay que tocar el fondo
#
# Nadie valida en la pantalla de marca que el texto se lea sobre el fondo, asi
# que hay que garantizarlo aqui. La pregunta es si basta con elegir el color del
# texto o hay que ajustar tambien el color de marca, y tiene respuesta cerrada.
#
# El contraste WCAG depende SOLO de la luminancia relativa, no del tono. Con
# blanco y negro puros como candidatos, el peor caso esta donde los dos empatan:
#
#     1,05 / (L + 0,05) = (L + 0,05) / 0,05
#     (L + 0,05)^2 = 0,0525   ->   L = 0,1791
#     contraste = 1,05 / 0,2291 = **4,58**
#
# Es decir: **para cualquier fondo, blanco o negro dan al menos 4,58**, por
# encima del 4,5 de WCAG AA. No hay ningun color de marca para el que haga falta
# oscurecer el fondo, y hay un test que lo recorre entero para comprobarlo.
#
# El detalle que si importa: los candidatos tienen que ser blanco y negro
# PUROS. Con un "casi negro" tipo `#111111` el minimo baja a 4,35 y aparece una
# banda de tonos medios sin solucion. Escrito aqui porque un cambio que parece
# cosmetico —suavizar el negro— rompe la garantia.


def _hex_valido(valor: str | None) -> str | None:
    """El color como `#rrggbb`, o `None` si no se puede interpretar.

    El campo es `String(20)` y lo rellena una persona por pantalla, asi que
    puede llegar `#fff`, `rgb(1,2,3)`, `azul` o vacio. Nada de eso puede tumbar
    la generacion de una factura: lo que no se entiende se ignora y se usa el
    color por defecto.
    """
    if not isinstance(valor, str):
        return None
    v = valor.strip().lstrip("#")
    _HEX = "0123456789abcdefABCDEF"
    if len(v) == 3 and all(c in _HEX for c in v):
        v = "".join(c * 2 for c in v)          # #fff -> #ffffff
    if len(v) != 6 or not all(c in _HEX for c in v):
        return None
    return "#" + v.lower()


def _luminancia(hexa: str) -> float:
    """Luminancia relativa WCAG de un `#rrggbb`."""
    def lineal(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (lineal(int(hexa[i:i + 2], 16) / 255) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contraste(uno: str, otro: str) -> float:
    """La razón de contraste WCAG entre dos colores. 1 es nada, 21 el máximo."""
    a, b = _luminancia(uno), _luminancia(otro)
    claro, oscuro = max(a, b), min(a, b)
    return (claro + 0.05) / (oscuro + 0.05)


#: El mínimo de WCAG AA para texto normal. Por debajo hay gente que no lo lee, y
#: una factura la lee cualquiera.
CONTRASTE_MINIMO = 4.5

#: Los dos candidatos de texto. PUROS, no «casi»: ver la nota de la cabecera —
#: con `#111111` el mínimo garantizado baja de 4,58 a 4,35 y deja de cumplirse.
_BLANCO = "#ffffff"
_NEGRO = "#000000"


def _texto_legible_sobre(fondo: str, preferido: str | None) -> str:
    """El color de texto que de verdad se lee sobre `fondo`.

    Se respeta `preferido` cuando cumple el mínimo —el cliente eligió ese color
    y hay que honrarlo si funciona— y si no, blanco o negro, el que más
    contraste dé. Nunca devuelve algo por debajo de 4,5: la nota de la cabecera
    demuestra que siempre hay una opción con 4,58 o más.

    No se avisa por log a propósito: esto se evalúa en cada documento generado y
    llenaría el registro. Quien configura la marca lo ve en el resultado.
    """
    if preferido and _contraste(preferido, fondo) >= CONTRASTE_MINIMO:
        return preferido
    return max((_BLANCO, _NEGRO), key=lambda c: _contraste(c, fondo))


@dataclass(frozen=True, slots=True)
class MarcaDeDocumento:
    """Lo que un generador necesita saber de la marca del cliente.

    Colores y nombre juntos porque salen de la misma fila: resolverlos por
    separado serían dos consultas por documento.
    """

    paleta: PaletaDeDocumento
    nombre: str


def marca_de_organizacion(db, organization_id, *, base=None,
                          nombre_por_defecto: str = "") -> MarcaDeDocumento:
    """La marca con la que hay que dibujar un documento de esa organización.

    Sustituye **sólo** los tres colores con significado inequívoco en un
    documento y deja neutros los tintes de tabla — la nota de arriba explica por
    qué mapear los cinco rompe el documento.

    Degrada en todos los escenarios en que puede faltar información, porque
    emitir la factura importa más que emitirla con la marca correcta:

      · sin `organization_id` (trabajos de fondo, superadministrador) → base;
      · sin fila de `OrgBranding` (organización que nunca la configuró) → base;
      · con la consulta fallando → base, avisando por log;
      · con un color ilegible o mal escrito → el campo por defecto de base,
        **campo a campo**: un `accent_color` mal escrito no tira el
        `primary_color` que sí estaba bien.

    **El logotipo NO se trae, y es deliberado.** `OrgBranding.logo_url` es una
    URL que escribe el cliente; descargarla al generar el PDF sería una petición
    saliente a un destino que él controla —SSRF— y metería su latencia y sus
    caídas en la ruta de emitir una factura. Traerlo bien necesita lista blanca
    de destinos, tiempo de espera, caché y un tamaño máximo: es su propia pieza,
    no una línea aquí.
    """
    from dataclasses import replace

    if base is None:
        base = PALETA_POR_DEFECTO
    marca_vacia = MarcaDeDocumento(paleta=base, nombre=nombre_por_defecto)

    if not organization_id:
        return marca_vacia

    try:
        from app.models.white_label import OrgBranding
        fila = (db.query(OrgBranding)
                  .filter(OrgBranding.organization_id == organization_id)
                  .first())
    except Exception:
        # Un fallo al leer la marca no puede impedir emitir una factura.
        _logger.warning(
            "no se pudo leer la marca de la organizacion %s; se usa la paleta "
            "por defecto", organization_id, exc_info=True,
        )
        return marca_vacia

    if fila is None:
        return marca_vacia

    cabecera = _hex_valido(fila.primary_color) or base.fondo_de_cabecera
    nombre = (fila.app_name or "").strip() or nombre_por_defecto
    return MarcaDeDocumento(
        paleta=replace(
            base,
            fondo_de_cabecera=cabecera,
            acento=_hex_valido(fila.accent_color) or base.acento,
            texto_sobre_cabecera=_texto_legible_sobre(
                cabecera, _hex_valido(fila.text_color)
            ),
        ),
        nombre=nombre,
    )
