"""Textos de los planes de un cambio, en el idioma de quien los lee (19-11-2026).

Los planes (vuelta atras, pruebas, comunicaciones) y el informe de impacto se
guardan como JSON en `AppSetting` (y el informe tambien en
`sd_change_requests.impact_analysis_json`). Antes cada texto se guardaba ya
escrito en castellano (o ingles) y asi lo veia todo el mundo.

Ahora cada entrada guarda, ademas del texto pintado en el idioma de quien lo
genero (para quien lea el JSON en crudo), sus textos por clave en `_textos`:

    {"action": "Detener el despliegue...",
     "_textos": {"action": {"clave": "cambio.vuelta.1", "params": {}}}}

Al leerlo (`pintar_datos`), cada campo de `_textos` se vuelve a pintar en el
idioma de quien mira y `_textos` no sale. Un parametro puede ser a su vez un
texto por clave (la ventana, el nivel de riesgo): se pinta en el mismo idioma.
Los planes guardados antes de este cambio no tienen `_textos`: se traducen al
leer si la empresa tiene la traduccion activa y, si no, salen tal cual; en
los dos casos la pantalla ofrece regenerarlos (`traducir_anterior`, abajo).
Sin migracion: todo cabe en el JSON que ya se guardaba.
"""
from __future__ import annotations

from typing import Any, Optional

from app.services.textos_de_salida import texto

CAMPO = "_textos"


def diferido(clave: str, **params: Any) -> dict:
    """Un texto por clave, para pintarlo luego en el idioma de quien lo lea."""
    return {"clave": clave, "params": params}


def _es_diferido(valor: Any) -> bool:
    return isinstance(valor, dict) and "clave" in valor and set(valor) <= {"clave", "params"}


def pintar(valor: Any, idioma: Optional[str]) -> Any:
    """El texto de un `diferido` en `idioma` (con sus parametros pintados); lo demas, tal cual."""
    if not _es_diferido(valor):
        return valor
    params = {k: pintar(v, idioma) for k, v in (valor.get("params") or {}).items()}
    return texto(valor["clave"], idioma, **params)


def con_textos(entrada: dict, idioma: Optional[str], **textos: dict) -> dict:
    """`entrada` con cada campo de `textos` pintado en `idioma` y anotado en `_textos`."""
    for campo, dif in textos.items():
        entrada[campo] = pintar(dif, idioma)
    entrada.setdefault(CAMPO, {}).update(textos)
    return entrada


def pintar_datos(datos: Any, idioma: Optional[str]) -> Any:
    """Copia de `datos` con los campos de cada `_textos` pintados en `idioma` y sin `_textos`."""
    if isinstance(datos, list):
        return [pintar_datos(x, idioma) for x in datos]
    if not isinstance(datos, dict):
        return datos
    salida = {k: pintar_datos(v, idioma) for k, v in datos.items() if k != CAMPO}
    for campo, dif in (datos.get(CAMPO) or {}).items():
        salida[campo] = pintar(dif, idioma)
    return salida


# ── Planes guardados antes del 19-11-2026 (sin `_textos`) ───────────────────
#
# Salen en el idioma en que se generaron. Al leerlos:
#
# - si la empresa tiene la traducción activa en el canal `ticket`
#   (`TRANSLATION_ENABLED`, `TRANSLATION_CHANNELS`), sus textos se traducen al
#   idioma de quien mira con el servicio de traducción (cache por empresa, tope
#   de gasto de IA); los códigos (`window_label`, `audience`, `phase`...) no;
# - si no (desactivada, sin proveedor, tope agotado, fallo), salen tal cual.
#
# En los dos casos la respuesta lleva `textos_anteriores` con el estado
# (`translated`, `same_language`, `unavailable`, `disabled`, `not_translated`) y
# el motivo, y la pantalla ofrece «Regenerar en el idioma actual» (vuelve a
# generar el plan con el botón de siempre; desde entonces ya lleva claves).

#: Campos con texto para leer en los planes antiguos. El resto son códigos o números.
CAMPOS_DE_TEXTO = frozenset({
    "action", "responsible", "description", "expected_result", "channel", "subject",
    "message_template", "summary",
})
CLAVE_DE_ANTERIORES = "textos_anteriores"
CANAL_DE_TRADUCCION = "ticket"


def tiene_textos(datos: Any) -> bool:
    """¿Lleva el plan (o algo dentro) sus textos por clave?"""
    if isinstance(datos, list):
        return any(tiene_textos(x) for x in datos)
    if not isinstance(datos, dict):
        return False
    return CAMPO in datos or any(tiene_textos(v) for v in datos.values())


def _recoger(datos: Any, sitios: list) -> None:
    if isinstance(datos, list):
        for x in datos:
            _recoger(x, sitios)
    elif isinstance(datos, dict):
        for k, v in datos.items():
            if k in CAMPOS_DE_TEXTO and isinstance(v, str) and v.strip():
                sitios.append((datos, k))
            else:
                _recoger(v, sitios)


def traducir_anterior(db, datos: dict, idioma: Optional[str], org_id: Optional[str],
                      user_id: Optional[str] = None) -> dict:
    """Un plan sin `_textos`, con sus textos traducidos a `idioma` si se puede.

    Nunca falla: si el servicio de traducción no está o falla, el plan sale tal
    cual. Devuelve `datos` (modificado) con `textos_anteriores`.
    """
    sitios: list = []
    _recoger(datos, sitios)
    estado, motivo = "not_translated", None
    if sitios and org_id and idioma:
        try:
            from app.services.traduccion.servicio import TRADUCIDO, traducir
            resultados = traducir(db, org_id, [d[k] for d, k in sitios], idioma,
                                  canal=CANAL_DE_TRADUCCION, user_id=user_id)
            traducidos = 0
            for (d, k), r in zip(sitios, resultados):
                if r.estado == TRADUCIDO and r.texto:
                    d[k] = r.texto
                    traducidos += 1
            primero = resultados[0] if resultados else None
            estado = TRADUCIDO if traducidos else (primero.estado if primero else estado)
            motivo = None if traducidos else (primero.motivo if primero else None)
        except Exception:  # el plan se enseña igual; la traducción es una ayuda
            import logging
            logging.getLogger(__name__).warning("traducir_anterior: sin traducción", exc_info=True)
            estado, motivo = "unavailable", "error"
    datos[CLAVE_DE_ANTERIORES] = {"status": estado, "reason": motivo, "regenerable": True}
    return datos


def ventana_diferida(ventana: Optional[dict]) -> Any:
    """La ventana de mantenimiento como texto por clave (dia de la semana y horas UTC).

    `window_label` sigue en ingles: es la etiqueta que la interfaz interpreta
    (`useVentana`), no un texto para leer.
    """
    if not ventana or ventana.get("day_of_week") is None or ventana.get("hour_utc") is None:
        return diferido("cambio.ventana_pendiente")
    hora = int(ventana["hour_utc"])
    return diferido("cambio.ventana", dia=diferido(f"cambio.dia.{int(ventana['day_of_week']) % 7}"),
                    desde=f"{hora:02d}:00", hasta=f"{(hora + 4) % 24:02d}:00")


def riesgo_diferido(etiqueta: Optional[str]) -> Any:
    """El nivel de riesgo (`low`...`critical`) como texto por clave."""
    if etiqueta in ("low", "medium", "high", "critical"):
        return diferido(f"cambio.riesgo.{etiqueta}")
    return etiqueta or ""


def idioma_de(db, user_id: Optional[str] = None, org_id: Optional[str] = None,
              idioma: Optional[str] = None) -> str:
    """El idioma en que se pinta: el pedido, el de la persona o el de la empresa."""
    from app.services import formato_regional
    return formato_regional.idioma_de_salida(db, user_id=user_id, org_id=org_id, preferido=idioma)
