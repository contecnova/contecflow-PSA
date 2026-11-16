"""El servicio de traduccion: un solo camino para todo lo que se traduce.

`traducir(db, org_id, textos, destino, canal=...)` devuelve, por texto, un
`Resultado` con su estado:

- `translated`: traducido (de la cache o del proveedor).
- `same_language`: ya estaba en el idioma destino (o vacio): nada que hacer.
- `unavailable`: no se pudo; `motivo` dice por que (`budget_exhausted`,
  `provider_not_configured`, `provider_error`, `timeout`, `unsupported_language`...).
  Quien llama muestra el original con el aviso.
- `disabled`: la empresa (o ese canal) no traduce. Nada sale de la aplicacion.

Pasos: habilitado por empresa y canal -> idioma de origen (el dado, el del
mensaje o la deteccion local si es segura) -> cache por (texto, origen,
destino, glosario) -> tope de gasto de IA de la empresa -> proveedor por lotes
(`TRANSLATION_MAX_BATCH_CHARS`) -> cache y registro de uso. Un fallo del
proveedor no rompe a quien llama: todo el lote queda `unavailable` (nunca una
mezcla de traducido y a medias dentro del mismo texto).
"""
from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.services.traduccion import ajustes
from app.services.traduccion import cache as _cache
from app.services.traduccion import glosario as _glosario
from app.services.traduccion.idiomas import detectar_si_seguro, normalizar
from app.services.traduccion.proveedores import ErrorDeTraduccion, proveedor_de

logger = logging.getLogger(__name__)

TRADUCIDO, MISMO_IDIOMA, NO_DISPONIBLE, DESACTIVADA = "translated", "same_language", "unavailable", "disabled"


@dataclass
class Resultado:
    estado: str
    destino: str
    texto: Optional[str] = None
    origen: Optional[str] = None
    proveedor: Optional[str] = None
    motivo: Optional[str] = None
    desde_cache: bool = False

    def como_dict(self) -> dict:
        d = asdict(self)
        return {"status": d["estado"], "target_language": d["destino"], "text": d["texto"],
                "source_language": d["origen"], "provider": d["proveedor"], "reason": d["motivo"],
                "cached": d["desde_cache"]}


def _todos(n: int, **kw) -> list[Resultado]:
    return [Resultado(**kw) for _ in range(n)]


def _lotes(indices: list[int], textos: list[str], maximo: int) -> list[list[int]]:
    lotes, actual, cuenta = [], [], 0
    for i in indices:
        largo = len(textos[i])
        if actual and cuenta + largo > maximo:
            lotes.append(actual)
            actual, cuenta = [], 0
        actual.append(i)
        cuenta += largo
    if actual:
        lotes.append(actual)
    return lotes


def _registrar_uso_externo(db: Session, org_id: str, proveedor: str, caracteres: int, user_id: Optional[str],
                           latencia_ms: int, error: Optional[str]) -> None:
    """DeepL y Azure no pasan por `call_ai`: su uso (y su coste, si la empresa
    fija el precio) se apunta igual en `AIUsageLog`, que es lo que suma el tope."""
    from app.services.ai_provider_service import _registrar_uso
    from app.services.traduccion.proveedores.ia import MODULO_DE_IA
    coste = caracteres / 1_000_000 * ajustes.coste_por_millon(db, org_id) if error is None else 0.0
    _registrar_uso(db, None, {"model": proveedor, "tokens_in": caracteres, "tokens_out": 0, "cost_usd": coste},
                   user_id=user_id, module=MODULO_DE_IA, latency=latencia_ms, error_msg=error,
                   organization_id=org_id)


def traducir(db: Session, org_id: Optional[str], textos: list[str], destino: str, *, canal: str,
             origen: Optional[str] = None, origenes: Optional[list[Optional[str]]] = None,
             user_id: Optional[str] = None, proveedor: Optional[str] = None) -> list[Resultado]:
    """Traduce `textos` a `destino`. Nunca lanza por el proveedor: degrada a `unavailable`."""
    n = len(textos)
    destino_n = normalizar(destino)
    if not n:
        return []
    if not destino_n:
        return _todos(n, estado=NO_DISPONIBLE, destino=destino or "", motivo="unsupported_language")
    if not ajustes.habilitada_en(db, org_id, canal):
        return _todos(n, estado=DESACTIVADA, destino=destino_n,
                      motivo="disabled" if not ajustes.habilitada(db, org_id) else "channel_disabled")

    minima = ajustes.confianza_minima(db, org_id)
    resultados: list[Optional[Resultado]] = [None] * n
    fuentes: list[Optional[str]] = []
    for i, texto in enumerate(textos):
        dado = normalizar((origenes or [None] * n)[i]) or normalizar(origen)
        fuente = dado or detectar_si_seguro(texto, minima)
        fuentes.append(fuente)
        if not (texto or "").strip() or fuente == destino_n:
            resultados[i] = Resultado(MISMO_IDIOMA, destino_n, texto, fuente or destino_n)

    terminos = _glosario.activos(db, org_id)
    glosarios = {i: _glosario.relevantes(terminos, textos[i], destino_n) for i in range(n) if resultados[i] is None}
    claves = {i: _cache.clave(textos[i], fuentes[i], destino_n, _glosario.huella(glosarios[i])) for i in glosarios}
    en_cache = _cache.buscar(db, org_id, list(claves.values()))
    for i, k in claves.items():
        fila = en_cache.get(k)
        if fila is not None:
            fuente = fila.source_language or fuentes[i]
            estado = MISMO_IDIOMA if fuente == destino_n else TRADUCIDO
            texto = textos[i] if estado == MISMO_IDIOMA else fila.translated_text
            resultados[i] = Resultado(estado, destino_n, texto, fuente, fila.provider, desde_cache=True)

    pendientes = [i for i in range(n) if resultados[i] is None]
    if pendientes:
        _traducir_pendientes(db, org_id, textos, destino_n, pendientes, fuentes, glosarios, claves, resultados,
                             user_id=user_id, proveedor=proveedor or ajustes.proveedor(db, org_id))
    # La cache se confirma con la transaccion de quien llama (no se confirma
    # aqui nada que no sea nuestro). Ojo: `call_ai` si confirma su registro de uso.
    db.flush()
    return [r for r in resultados if r is not None]


def _traducir_pendientes(db, org_id, textos, destino, pendientes, fuentes, glosarios, claves, resultados, *,
                         user_id, proveedor):
    from app.services.ai_provider_service import PresupuestoDeIAAgotado, _exigir_presupuesto

    def _falla(indices, motivo):
        for i in indices:
            resultados[i] = Resultado(NO_DISPONIBLE, destino, None, fuentes[i], proveedor, motivo)

    try:
        _exigir_presupuesto(db, org_id)
        prov = proveedor_de(db, org_id, proveedor, user_id)
    except PresupuestoDeIAAgotado:
        return _falla(pendientes, "budget_exhausted")
    except ErrorDeTraduccion as e:
        return _falla(pendientes, e.codigo)
    if not prov.admite(destino):
        return _falla(pendientes, "unsupported_language")

    # Por origen: un lote no mezcla un origen dado con «detectalo».
    por_origen: dict[Optional[str], list[int]] = {}
    for i in pendientes:
        por_origen.setdefault(fuentes[i], []).append(i)
    maximo = ajustes.max_caracteres_por_lote(db, org_id)
    for fuente, indices in por_origen.items():
        for lote in _lotes(indices, textos, maximo):
            inicio = time.time()
            caracteres = sum(len(textos[i]) for i in lote)
            try:
                if prov.nombre != "ai":
                    _exigir_presupuesto(db, org_id)
                salida = prov.traducir([textos[i] for i in lote], destino, fuente, [glosarios[i] for i in lote])
            except PresupuestoDeIAAgotado:
                _falla(lote, "budget_exhausted")
                continue
            except ErrorDeTraduccion as e:
                logger.warning("traduccion: %s fallo (%s)", prov.nombre, e)
                if prov.nombre != "ai":
                    _registrar_uso_externo(db, org_id, prov.nombre, caracteres, user_id,
                                           int((time.time() - inicio) * 1000), e.codigo)
                _falla(lote, e.codigo)
                continue
            except Exception:
                logger.exception("traduccion: error inesperado del proveedor %s", prov.nombre)
                _falla(lote, "provider_error")
                continue
            if prov.nombre != "ai":
                _registrar_uso_externo(db, org_id, prov.nombre, caracteres, user_id,
                                       int((time.time() - inicio) * 1000), None)
            for i, t in zip(lote, salida):
                origen_real = t.origen or fuente
                if origen_real == destino:
                    resultados[i] = Resultado(MISMO_IDIOMA, destino, textos[i], origen_real, prov.nombre)
                else:
                    resultados[i] = Resultado(TRADUCIDO, destino, t.texto, origen_real, prov.nombre)
                _cache.guardar(db, org_id, claves[i], origen_real, destino,
                               t.texto if origen_real != destino else textos[i], prov.nombre, len(textos[i]))


def traducir_uno(db: Session, org_id: Optional[str], texto: str, destino: str, *, canal: str,
                 origen: Optional[str] = None, user_id: Optional[str] = None) -> Resultado:
    return traducir(db, org_id, [texto], destino, canal=canal, origen=origen, user_id=user_id)[0]


def traducir_texto(db: Session, org_id: Optional[str], texto: str, destino: str, *, canal: str,
                   origen: Optional[str] = None, user_id: Optional[str] = None) -> Resultado:
    """Un texto suelto (editor, chat interno) y se confirma la cache."""
    r = traducir_uno(db, org_id, texto, destino, canal=canal, origen=origen, user_id=user_id)
    db.commit()
    return r


def probar(db: Session, org_id: str, proveedor: str, destino: str, texto: str) -> dict:
    """Prueba de la pantalla de administracion: llama al proveedor sin cache ni canal."""
    destino_n = normalizar(destino)
    if not destino_n:
        return {"ok": False, "reason": "unsupported_language"}
    try:
        prov = proveedor_de(db, org_id, proveedor)
        if not prov.admite(destino_n):
            return {"ok": False, "reason": "unsupported_language"}
        salida = prov.traducir([texto], destino_n, None, [[]])
    except ErrorDeTraduccion as e:
        return {"ok": False, "reason": e.codigo}
    except Exception:
        logger.exception("traduccion: prueba del proveedor %s", proveedor)
        return {"ok": False, "reason": "provider_error"}
    finally:
        db.commit()
    return {"ok": True, "text": salida[0].texto, "source_language": salida[0].origen, "provider": proveedor}
