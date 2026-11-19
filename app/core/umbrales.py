"""Umbrales de semáforo: una definición por MÉTRICA (19-11-2026).

Medido antes: la misma métrica tenía cortes distintos según la pantalla o el
servicio. Presupuesto consumido a 70/90, 75/90, 85/100, >80 o >90; carga de
recursos a 85/100, 80 o 60/85/100; cumplimiento de SLA a 70/90, 75/90 u 80/95;
y servicios que ignoraban su propio ajuste (salud de proyecto a 70/45 fijo
frente a `PROJECT_HEALTH_TRAFFIC_*`, CPI a 0,8/0,95 frente a `EVM_INDEX_*`,
riesgo de cambio a 75/55/30 frente a `RISK_LEVEL_*` 75/50/25).

Ahora:

* `METRICAS`: cada métrica con sus dos ajustes (aviso y crítico), su sentido
  (si más es peor o menos es peor) y si el corte incluye el valor.
* `tono_de(metrica, valor, db=..., org_id=...)` → ``"success"``,
  ``"warning"`` o ``"danger"`` con los ajustes de la empresa (los mismos
  nombres de tono que el frontend: `frontend/src/utils/umbrales.ts`,
  `tonoDe`).
* `umbrales_de_empresa(db, org_id)` → lo que lee el frontend por
  `/settings/org-defaults` (campo ``umbrales``) y `useUmbrales()`.
* `validar_umbral(clave, valor, otro)` → lo usa `set_runtime_value` para que
  aviso y crítico queden en su rango y en orden.

Regla de los cortes (la que usaban casi todas las pantallas):

* «más es peor» (presupuesto, carga…): crítico si ``valor > critico``, aviso
  si ``valor > aviso`` (con ``inclusivo``: ``>=``; riesgo y aprobaciones,
  cuyo ajuste dice «desde»);
* «menos es peor» (SLA, OKR, NPS, margen, salud, EVM…): crítico si
  ``valor < critico``, aviso si ``valor < aviso`` (bueno «desde» aviso; con
  ``inclusivo``, ``<=``: días que faltan para un vencimiento).

Lo que NO está aquí, a propósito: las escalas de probabilidad y correlación
(`app.core.escalas`) y las heurísticas de puntuación (pesos de un modelo de
abandono o de burnout, notas A-F del informe de cumplimiento), que no son un
semáforo sobre una métrica.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

TONOS = ("success", "warning", "danger")


@dataclass(frozen=True)
class Metrica:
    aviso: str
    critico: str
    #: True: más es peor (presupuesto, carga). False: menos es peor (SLA, NPS).
    mayor_peor: bool
    #: Rango válido de los dos umbrales.
    minimo: float = 0.0
    maximo: float = 1000.0
    #: El corte incluye el valor: ``>=`` si más es peor, ``<=`` si menos es peor.
    inclusivo: bool = False


METRICAS: dict[str, Metrica] = {
    "presupuesto": Metrica("UMBRAL_PRESUPUESTO_AVISO_PCT", "UMBRAL_PRESUPUESTO_CRITICO_PCT", True),
    "carga": Metrica("UMBRAL_CARGA_AVISO_PCT", "UMBRAL_CARGA_CRITICO_PCT", True),
    "sla": Metrica("UMBRAL_SLA_AVISO_PCT", "UMBRAL_SLA_CRITICO_PCT", False, maximo=100.0),
    "okr": Metrica("UMBRAL_OKR_AVISO_PCT", "UMBRAL_OKR_CRITICO_PCT", False),
    "nps": Metrica("UMBRAL_NPS_AVISO", "UMBRAL_NPS_CRITICO", False, minimo=-100.0, maximo=100.0),
    "margen": Metrica("UMBRAL_MARGEN_AVISO_PCT", "UMBRAL_MARGEN_CRITICO_PCT", False, minimo=-1000.0, maximo=100.0),
    "sprint_completitud": Metrica("UMBRAL_SPRINT_COMPLETITUD_AVISO_PCT", "UMBRAL_SPRINT_COMPLETITUD_CRITICO_PCT", False),
    "sprint_velocidad": Metrica("UMBRAL_SPRINT_VELOCIDAD_AVISO_PCT", "UMBRAL_SPRINT_VELOCIDAD_CRITICO_PCT", False),
    "aprobacion_riesgo_sla": Metrica("UMBRAL_APROBACION_RIESGO_SLA_AVISO_PCT", "UMBRAL_APROBACION_RIESGO_SLA_CRITICO_PCT",
                                     True, maximo=100.0, inclusivo=True),
    "aprobacion_rechazo": Metrica("UMBRAL_APROBACION_RECHAZO_AVISO_PCT", "UMBRAL_APROBACION_RECHAZO_CRITICO_PCT",
                                  True, maximo=100.0, inclusivo=True),
    "vencimiento": Metrica("UMBRAL_VENCIMIENTO_AVISO_DIAS", "UMBRAL_VENCIMIENTO_CRITICO_DIAS", False, maximo=3650.0,
                           inclusivo=True),
    # Ajustes que ya existían: se reutilizan, no se duplican.
    "riesgo": Metrica("RISK_LEVEL_HIGH", "RISK_LEVEL_CRITICAL", True, maximo=100.0, inclusivo=True),
    "salud_proyecto": Metrica("PROJECT_HEALTH_TRAFFIC_GREEN", "PROJECT_HEALTH_TRAFFIC_YELLOW", False, maximo=100.0),
    "salud_cliente": Metrica("HEALTH_THRESHOLD_GOOD", "HEALTH_THRESHOLD_AT_RISK", False, maximo=100.0),
    "evm": Metrica("EVM_INDEX_GREEN_MIN", "EVM_INDEX_RED_BELOW", False, maximo=10.0),
}

#: Umbrales sueltos (un solo corte), también por empresa.
SUELTOS = (
    "UMBRAL_SOBRECARGA_HORAS_SEMANA", "UMBRAL_APROBACION_PENDIENTES_CRITICO", "UMBRAL_APROBACION_DECISION_HORAS",
    "UMBRAL_VENCIMIENTO_HORIZONTE_DIAS", "UMBRAL_HITOS_HORIZONTE_DIAS", "UMBRAL_HITOS_INMINENTE_DIAS",
    "RESOURCE_UNDERUSE_PCT",
)

#: Clave → (métrica, papel) para validar al guardar.
_PAPEL: dict[str, tuple[str, str]] = {}
for _nombre, _m in METRICAS.items():
    _PAPEL[_m.aviso] = (_nombre, "aviso")
    _PAPEL[_m.critico] = (_nombre, "critico")


def _valor(clave: str, db=None, org_id: Optional[str] = None) -> float:
    """El ajuste de la empresa (si hay `db`) o el de `Settings`."""
    if db is not None:
        try:
            from app.services.settings_service import get_runtime_float
            v = get_runtime_float(db, clave, org_id)
            if v is not None:
                return float(v)
        except Exception:
            logger.debug("umbrales: no se pudo leer %s en vivo", clave, exc_info=True)
    return float(getattr(settings, clave))


def _org(db, org_id: Optional[str], registro: Any) -> Optional[str]:
    if db is None:
        return org_id
    from app.services.settings_service.por_empresa import empresa_de
    return empresa_de(db, registro, org_id)


def umbral(clave: str, db=None, org_id: Optional[str] = None, *, registro: Any = None) -> float:
    """Un umbral suelto (`SUELTOS`) de la empresa."""
    return _valor(clave, db, _org(db, org_id, registro))


def cortes(metrica: str, db=None, org_id: Optional[str] = None, *, registro: Any = None) -> tuple[float, float]:
    """(aviso, crítico) de `metrica` para la empresa."""
    m = METRICAS[metrica]
    org = _org(db, org_id, registro)
    return _valor(m.aviso, db, org), _valor(m.critico, db, org)


def tono_con(metrica: str, valor: Optional[float], aviso: float, critico: float) -> Optional[str]:
    """El tono de `valor` con unos cortes ya leídos (puro, sin base de datos)."""
    if valor is None:
        return None
    m = METRICAS[metrica]
    v = float(valor)
    if m.mayor_peor:
        if (v >= critico) if m.inclusivo else (v > critico):
            return "danger"
        if (v >= aviso) if m.inclusivo else (v > aviso):
            return "warning"
        return "success"
    if (v <= critico) if m.inclusivo else (v < critico):
        return "danger"
    if (v <= aviso) if m.inclusivo else (v < aviso):
        return "warning"
    return "success"


def tono_de(metrica: str, valor: Optional[float], db=None, org_id: Optional[str] = None, *,
            registro: Any = None) -> Optional[str]:
    """``success``/``warning``/``danger`` de `valor` con los umbrales de la empresa.

    `None` si no hay valor. Sin `db`, los de `Settings` (entorno).
    """
    if valor is None:
        return None
    aviso, critico = cortes(metrica, db, org_id, registro=registro)
    return tono_con(metrica, valor, aviso, critico)


#: Nombres de tono que usan algunos servicios.
SEMAFORO = {"success": "green", "warning": "yellow", "danger": "red"}
SALUD = {"success": "ok", "warning": "warning", "danger": "critical"}


def estado_de_carga(pct: float, db=None, org_id: Optional[str] = None, *, registro: Any = None,
                    libre: str = "under") -> str:
    """overloaded / high / ok / `libre` de una carga (% de capacidad).

    overloaded y high: `UMBRAL_CARGA_*`; por debajo de `RESOURCE_UNDERUSE_PCT`,
    `libre` («under», o «free» en reservas).
    """
    tono = tono_de("carga", pct, db, org_id, registro=registro)
    if tono == "danger":
        return "overloaded"
    if tono == "warning":
        return "high"
    if float(pct or 0) < umbral("RESOURCE_UNDERUSE_PCT", db, org_id, registro=registro):
        return libre
    return "ok"


def nivel_de_riesgo(puntuacion: Optional[float], db=None, org_id: Optional[str] = None, *,
                    registro: Any = None) -> Optional[str]:
    """critical/high/medium/low de una puntuación de riesgo 0-100 (`RISK_LEVEL_*`, «desde»)."""
    if puntuacion is None:
        return None
    org = _org(db, org_id, registro)
    v = float(puntuacion)
    for clave, nivel in (("RISK_LEVEL_CRITICAL", "critical"), ("RISK_LEVEL_HIGH", "high"),
                         ("RISK_LEVEL_MEDIUM", "medium")):
        if v >= _valor(clave, db, org):
            return nivel
    return "low"


def umbrales_de_empresa(db, org_id: Optional[str]) -> dict:
    """Todo lo que necesita el frontend: ``{metrica: {aviso, critico, mayor_peor, inclusivo}, ...}``
    y los sueltos con su clave."""
    salida: dict = {}
    for nombre, m in METRICAS.items():
        salida[nombre] = {"aviso": _valor(m.aviso, db, org_id), "critico": _valor(m.critico, db, org_id),
                          "mayor_peor": m.mayor_peor, "inclusivo": m.inclusivo}
    salida["sueltos"] = {clave: _valor(clave, db, org_id) for clave in SUELTOS}
    return salida


def validar_umbral(clave: str, valor: float, otro: Optional[float]) -> None:
    """ValueError si `valor` está fuera del rango de su métrica o desordena el par.

    `otro` es el valor vigente del otro umbral del par (aviso ↔ crítico).
    «Más es peor»: aviso ≤ crítico. «Menos es peor»: aviso ≥ crítico.
    """
    from app.core.codigos_de_error import ErrorConCodigo
    if clave in SUELTOS:
        if valor < 0:
            raise ErrorConCodigo("ajuste_valor_no_valido", detail=f"invalid value for {clave}: {valor} (must be ≥ 0)",
                                 clave=clave, esperado="≥ 0")
        return
    if clave not in _PAPEL:
        return
    nombre, papel = _PAPEL[clave]
    m = METRICAS[nombre]
    if not (m.minimo <= valor <= m.maximo):
        raise ErrorConCodigo("ajuste_valor_no_valido",
                             detail=f"invalid value for {clave}: {valor} (expected {m.minimo:g}..{m.maximo:g})",
                             clave=clave, esperado=f"{m.minimo:g}..{m.maximo:g}")
    if otro is None:
        return
    aviso, critico = (valor, otro) if papel == "aviso" else (otro, valor)
    en_orden = aviso <= critico if m.mayor_peor else aviso >= critico
    if not en_orden:
        regla = "warning ≤ critical" if m.mayor_peor else "warning ≥ critical"
        raise ErrorConCodigo("ajuste_valor_no_valido",
                             detail=f"invalid value for {clave}: {valor} ({nombre}: {regla}; the other is {otro:g})",
                             clave=clave, esperado=regla)


def otro_del_par(clave: str) -> Optional[str]:
    """La otra clave del par aviso/crítico de `clave` (None si no es de un par)."""
    if clave not in _PAPEL:
        return None
    nombre, papel = _PAPEL[clave]
    m = METRICAS[nombre]
    return m.critico if papel == "aviso" else m.aviso
