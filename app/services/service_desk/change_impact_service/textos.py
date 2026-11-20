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
leer si la empresa tiene la traduccion activa; si no, con su IA si la tiene y
la deja usar (20-11-2026); si no hay ninguna, salen tal cual. En todos los
casos la pantalla ofrece regenerarlos (`traducir_anterior`, abajo).
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
# - si el canal no está activo pero la empresa tiene IA (proveedor y módulo
#   `change_management` permitido), se traducen con la IA (20-11-2026, abajo);
# - si no hay ni una ni otra (o tope agotado, fallo), salen tal cual.
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
                      user_id: Optional[str] = None, clave_del_plan: Optional[str] = None) -> dict:
    """Un plan sin `_textos`, con sus textos traducidos a `idioma` si se puede.

    Nunca falla: si el servicio de traducción no está o falla, el plan sale tal
    cual. Devuelve `datos` (modificado) con `textos_anteriores`.

    20-11-2026: si la empresa no tiene la traducción activa en el canal
    `ticket` pero sí IA (proveedor configurado y el módulo `change_management`
    permitido), se traduce con la IA (`_traducir_con_ia`); `clave_del_plan`
    (`sd.change.rollback.<id>`...) separa su cache por plan e idioma.
    """
    sitios: list = []
    _recoger(datos, sitios)
    estado, motivo = "not_translated", None
    extra: dict = {}
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
        if estado == "disabled":
            # Sin traducción en el canal: la IA de la empresa, si la hay y la deja usar.
            estado, motivo, extra = _traducir_con_ia(db, sitios, idioma, org_id, user_id, clave_del_plan,
                                                     estado, motivo)
    datos[CLAVE_DE_ANTERIORES] = {"status": estado, "reason": motivo, "regenerable": True, **extra}
    return datos


# ── Planes antiguos con la IA de la empresa (20-11-2026) ────────────────────
#
# Solo cuando el canal `ticket` del servicio de traducción NO está activo. Pasos:
#
# 1. Cache por plan e idioma (`translation_cache` de la empresa, proveedor
#    `ai`, clave = plan + idioma + huella de los textos): un plan ya traducido a
#    ese idioma no vuelve a la IA; si el plan se regenera, la huella cambia. La
#    purga de la cache (`TRANSLATION_CACHE_RETENTION_DAYS`) también la limpia.
# 2. Módulo de IA `change_management` permitido (`comprobar_modulo`: apagado ->
#    no se usa; tope diario por usuario -> `modulo_ia_limite_diario`).
# 3. Proveedor configurado (el de la empresa, uno global, el del `.env` o la
#    credencial de Anthropic): sin él no se llama ni se apunta nada.
# 4. Si el texto ya está en el idioma de quien mira (detección local segura),
#    no se llama.
# 5. `call_ai` (módulo `change_management`): gobernanza, registro de uso y tope
#    diario de gasto de la empresa; agotado -> `ia_presupuesto_diario_agotado`
#    con su `params` en `textos_anteriores` (`code`, `params`). Cada traducción
#    apunta una acción en `AIActionLog` (cuenta para el tope diario del módulo).
#
# Si la IA no está (módulo apagado o sin proveedor) se queda el estado del
# servicio de traducción (`disabled`) y `ai_reason` dice por qué no hubo IA.

MODULO_DE_IA = "change_management"
_PROVEEDOR_EN_CACHE = "ai"


def _clave_de_cache(clave_del_plan: Optional[str], destino: str, originales: list) -> str:
    import hashlib
    import json
    crudo = json.dumps(["change_plan", clave_del_plan or "", destino, originales], ensure_ascii=False)
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()


def _aplicar(sitios: list, traducidos: list) -> None:
    for (d, k), t in zip(sitios, traducidos):
        if isinstance(t, str) and t.strip():
            d[k] = t


def _hay_proveedor(db, org_id: str) -> bool:
    from app.services import ai_provider_service as ia
    try:
        return bool(ia.get_default_provider(db, is_superadmin=False, organization_id=org_id)
                    or ia.proveedor_de_credencial(db, org_id))
    except Exception:
        import logging
        logging.getLogger(__name__).warning("traducir_anterior: no se pudo leer el proveedor de IA", exc_info=True)
        return False


def _traducir_con_ia(db, sitios: list, idioma: str, org_id: str, user_id: Optional[str],
                     clave_del_plan: Optional[str], estado: str, motivo: Optional[str]) -> tuple:
    """(estado, motivo, extra) tras intentar la IA. Nunca lanza."""
    import json
    import logging
    from app.services.traduccion import ajustes
    from app.services.traduccion import cache as _cache
    from app.services.traduccion.idiomas import IDIOMAS, detectar_si_seguro, normalizar

    log = logging.getLogger(__name__)
    destino = normalizar(idioma)
    if not destino or destino not in IDIOMAS:
        return estado, motivo, {"ai_reason": "unsupported_language"}
    originales = [d[k] for d, k in sitios]
    clave = _clave_de_cache(clave_del_plan, destino, originales)
    try:
        fila = _cache.buscar(db, org_id, [clave]).get(clave)
        if fila is not None:
            traducidos = json.loads(fila.translated_text)
            if isinstance(traducidos, list) and len(traducidos) == len(originales):
                _aplicar(sitios, traducidos)
                db.commit()  # aciertos de la cache
                return "translated", None, {"via": "ai", "cached": True}
    except Exception:
        log.warning("traducir_anterior: cache de IA ilegible", exc_info=True)
        db.rollback()

    from app.core.errores import ErrorDeDominio
    from app.core.modulos_ia import comprobar_modulo
    try:
        comprobar_modulo(db, org_id, MODULO_DE_IA, user_id)
    except ErrorDeDominio as e:
        if e.status_code == 429:  # tope diario del módulo para este usuario
            return "unavailable", "ai_module_daily_limit", {"via": "ai", "code": e.code, "params": e.params or {}}
        return estado, motivo, {"ai_reason": "ai_module_disabled", "code": e.code}
    if not _hay_proveedor(db, org_id):
        return estado, motivo, {"ai_reason": "provider_not_configured"}

    detectado = detectar_si_seguro("\n".join(originales), ajustes.confianza_minima(db, org_id))
    if detectado == destino:
        return "same_language", None, {"via": "ai"}

    from app.services import ai_provider_service as ia
    from app.services.traduccion.proveedores.ia import _leer, instrucciones
    from app.services.traduccion.proveedores.base import ErrorDeTraduccion
    mensajes = [{"role": "user", "content": json.dumps({"items": originales}, ensure_ascii=False)}]
    try:
        respuesta = ia.call_ai(db, mensajes, system=instrucciones(destino, None, []), module=MODULO_DE_IA,
                               user_id=user_id, organization_id=org_id,
                               max_tokens=ajustes.max_tokens_ia(db, org_id))
    except ia.PresupuestoDeIAAgotado as exc:
        return "unavailable", "budget_exhausted", {"via": "ai", "code": exc.codigo, "params": exc.params}
    except Exception:
        log.warning("traducir_anterior: la IA falló", exc_info=True)
        return "unavailable", "provider_error", {"via": "ai"}
    if ia.es_aviso_de_ia(respuesta):
        sin = respuesta == ia.AVISO_SIN_PROVEEDOR
        if sin:
            return estado, motivo, {"ai_reason": "provider_not_configured"}
        return "unavailable", "provider_error", {"via": "ai"}
    try:
        traducidos = [t.texto for t in _leer(respuesta, len(originales))]
    except ErrorDeTraduccion as e:
        return "unavailable", e.codigo, {"via": "ai"}
    _aplicar(sitios, traducidos)
    try:
        from app.services.ai_modules._base import log_action
        _cache.guardar(db, org_id, clave, None, destino, json.dumps(traducidos, ensure_ascii=False),
                       _PROVEEDOR_EN_CACHE, sum(len(t) for t in originales))
        if user_id:
            log_action(db, user_id, MODULO_DE_IA, "translate_old_change_plan",
                       input_s=clave_del_plan or "", output_s=destino, entities=[clave_del_plan] if clave_del_plan else [])
        db.commit()
    except Exception:  # la traducción ya está hecha; solo se pierde la cache
        log.warning("traducir_anterior: no se pudo guardar la cache de IA", exc_info=True)
        db.rollback()
    return "translated", None, {"via": "ai", "cached": False}


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
