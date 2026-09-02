"""La paleta de marca de los documentos generados: un solo sitio.

Auditoría 2026-08 (hallazgo 18 y hallazgo nuevo). Los seis colores de marca
estaban escritos en duro **91 veces repartidas por 29 ficheros**, y cada
generador de PDF los redefinía como variables locales. Un cambio de marca
obligaba a tocarlos todos y a acertar en los 29.

Este módulo es la fuente de verdad para la capa de documentos. No pretende ser
la única del producto —el frontend tiene su propio sistema de tokens CSS— pero
sí la única del lado servidor.

## Lo que este módulo NO resuelve, y conviene saberlo

`OrgBranding` (`app/models/white_label.py`) define cinco colores **por
organización** y tiene pantalla para configurarlos. Sólo lo leen su propio
endpoint y el portal de cliente. Los generadores que producen lo que ve el
cliente final —facturas, informes, firma electrónica, campañas y correos— no lo
leen, y ninguno recibe siquiera el `organization_id`, así que no tienen por
dónde.

Resultado: un cliente configura su marca, la ve en la web, y **sus facturas
salen con los colores de Contecflow**.

Cablearlo es una funcionalidad y lleva una decisión de producto detrás —¿la
factura lleva la marca del tenant o la de la plataforma?—, así que no se ha
hecho aquí. Lo que sí queda listo es la condición previa: cuando se decida, hay
un solo sitio del que partir y `PALETA_POR_DEFECTO` documenta qué colores hay
que poder sustituir.
"""
from __future__ import annotations

from dataclasses import dataclass

from reportlab.lib import colors


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
)

# La variante de facturación: mismo azul de marca, filas con matiz azulado.
PALETA_DE_FACTURA = PaletaDeDocumento(
    **{
        **{c: getattr(PALETA_POR_DEFECTO, c) for c in PALETA_POR_DEFECTO.__slots__},
        "fila_alterna": "#f0f9ff",
        "borde_de_tabla": "#dee6ef",
    }
)
