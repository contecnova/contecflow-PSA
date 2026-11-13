"""Escalas compartidas: de una puntuación a una banda (segunda auditoría 2026-11, hallazgo 17).

Medido antes: seis escalas distintas de «número → nivel» repartidas por seis
servicios, dos de ellas para el mismo número (la probabilidad predicha de que un
proyecto o un ticket salga mal) con cortes distintos (0,70/0,50/0,30 en
`ml_trainer`, 0,75/0,50/0,25 en `predictive_analytics_service`, >0,75/>0,5 con
suelo «medium» en `ai_modules`, 0,7/0,4 sin «medium» en `bi_intelligence`), y
un mismo fichero (`alert_correlation_service`) que sugería «crear problema» a
partir de 0,70 en una pasada y de 0,65 en la siguiente.

Aquí hay una escala por **concepto**, con nombre:

* `nivel_por_probabilidad` — probabilidad predicha (0-1) de un mal resultado →
  critical/high/medium/low. Ajustable en vivo (`risk`: RISK_PROBABILITY_*).
* `accion_por_correlacion` — puntuación de correlación de alertas (0-1) →
  create_problem/review/monitor. Ajustable en vivo (`service_desk`:
  ALERT_CORRELATION_*).
* `nivel_de_riesgo_de_cambio` — la puntuación aditiva de la simulación de
  despliegue de un cambio. **No** es una probabilidad: sus pesos (0,4 por ser de
  emergencia, 0,3 por más de mil usuarios...) están calibrados contra estos
  cortes, así que se queda con los suyos.
* `nivel_de_abandono` — probabilidad de baja de un cliente. Escala de tres
  niveles sin «critical»; el resumen cuenta los «high». Se queda con los suyos.

Lo que **no** está aquí, a propósito, porque es otro concepto: similitudes
(coseno de la KB, autorresolución), tasas (fallos de cambios, incumplimientos),
la salud de un modelo reentrenado, la puntuación de riesgo de proyecto 0-100
(`RISK_LEVEL_*`, ya ajustable) y la de sesión 0-100 (`session_security`).
"""
from __future__ import annotations

import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

#: De más grave a menos.
NIVELES = ("critical", "high", "medium", "low")


def _umbral(clave: str, db=None, org_id: Optional[str] = None) -> float:
    """El valor en vivo de la empresa (si hay `db`) o el de `Settings`."""
    if db is not None:
        try:
            from app.services.settings_service import get_runtime_float
            valor = get_runtime_float(db, clave, org_id)
            if valor is not None:
                return float(valor)
        except Exception:
            logger.debug("escalas: no se pudo leer %s en vivo", clave, exc_info=True)
    return float(getattr(settings, clave))


def _por_bandas(valor: float, bandas, por_defecto: str) -> str:
    for umbral, etiqueta in bandas:
        if valor >= umbral:
            return etiqueta
    return por_defecto


# ── Probabilidad predicha → nivel ─────────────────────────────────────────────

def bandas_de_probabilidad(db=None, org_id: Optional[str] = None) -> tuple[tuple[float, str], ...]:
    return (
        (_umbral("RISK_PROBABILITY_CRITICAL", db, org_id), "critical"),
        (_umbral("RISK_PROBABILITY_HIGH", db, org_id), "high"),
        (_umbral("RISK_PROBABILITY_MEDIUM", db, org_id), "medium"),
    )


def nivel_por_probabilidad(probabilidad: float, *, db=None, org_id: Optional[str] = None,
                           suelo: str = "low") -> str:
    """critical/high/medium/low según RISK_PROBABILITY_* (≥, de más grave a menos).

    `suelo` es el nivel mínimo que devuelve: los avisos del oráculo nunca bajan
    de «medium» porque sólo se emiten cuando ya hay algo que mirar.
    """
    nivel = _por_bandas(float(probabilidad or 0.0), bandas_de_probabilidad(db, org_id), "low")
    if NIVELES.index(nivel) > NIVELES.index(suelo):
        return suelo
    return nivel


# ── Correlación de alertas → acción ───────────────────────────────────────────

#: Un grupo con menos tickets no justifica abrir un problema por sí solo.
TAMANO_MINIMO_PARA_PROBLEMA = 3


def accion_por_correlacion(puntuacion: float, tamano: int, *, db=None,
                           org_id: Optional[str] = None) -> str:
    """create_problem (≥ ALERT_CORRELATION_PROBLEM_SCORE y ≥3 tickets), review o monitor."""
    if (puntuacion >= _umbral("ALERT_CORRELATION_PROBLEM_SCORE", db, org_id)
            and tamano >= TAMANO_MINIMO_PARA_PROBLEMA):
        return "create_problem"
    if puntuacion >= _umbral("ALERT_CORRELATION_REVIEW_SCORE", db, org_id):
        return "review"
    return "monitor"


# ── Simulación de despliegue de un cambio (escala propia) ─────────────────────

BANDAS_DE_RIESGO_DE_CAMBIO: tuple[tuple[float, str], ...] = (
    (0.7, "critical"), (0.4, "high"), (0.2, "medium"),
)
#: Desde aquí: script de vuelta atrás obligatorio y ventana nocturna.
CAMBIO_UMBRAL_VUELTA_ATRAS = 0.4
#: Desde aquí: se recomienda una fase canario.
CAMBIO_UMBRAL_CANARIO = 0.3


def nivel_de_riesgo_de_cambio(puntuacion: float) -> str:
    return _por_bandas(puntuacion, BANDAS_DE_RIESGO_DE_CAMBIO, "low")


# ── Probabilidad de baja de un cliente (escala propia) ────────────────────────

BANDAS_DE_ABANDONO: tuple[tuple[float, str], ...] = ((0.6, "high"), (0.3, "medium"))


def nivel_de_abandono(probabilidad: float) -> str:
    return _por_bandas(probabilidad, BANDAS_DE_ABANDONO, "low")
