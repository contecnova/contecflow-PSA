"""Valores de negocio que eran fijos: validación al guardarlos y lectura por empresa (19-11-2026).

Antes estaban escritos en pantallas y servicios (ver
`app/core/config_groups/valores_de_negocio_config.py`). Ahora son ajustes por
empresa del registro en vivo (`RUNTIME_FLAG_GROUPS`):

| Clave | Grupo | Por defecto | Validación |
|---|---|---|---|
| `CHANGE_CANARY_RAMP_PCT` | service_desk | `1,5,25,50,100` | 2-10 enteros 1-100, estrictamente crecientes, el último 100 |
| `CHANGE_CANARY_FIRST_MINUTES` | service_desk | 30 | 5-1440 |
| `CHANGE_CANARY_STEP_MINUTES` | service_desk | 45 | 5-1440 |
| `CHANGE_CANARY_LAST_MINUTES` | service_desk | 60 | 5-1440 |
| `CHAT_RETENTION_PROPOSED_MONTHS` | audit | 24 | 1-120; ≥ `RETENTION_MIN_DAYS` (en meses de 30 días); ≤ tope de la empresa en el chat |
| `VACATION_MAX_DAYS_ENTITLED` | locale | 60 | 1-366; ≥ `DEFAULT_VACATION_DAYS_PER_YEAR` |
| `PERF_REMINDER_WINDOW_DAYS` | automations | 7 | 1-90 |
| `PERF_REMINDER_UNDATED_CYCLE_DAYS` | automations | 30 | 1-365 |
| `PERF_STALLED_CYCLE_DAYS` | automations | 45 | 1-365 |
| `PERF_STALLED_COMPLETION_PCT` | automations | 50 | 0-100 |

`set_runtime_value` llama a `validar` antes de guardar (y deja la entrada de
auditoría de siempre, `settings_audit_service.record_change`). Un error sale
con el código `ajuste_valor_no_valido` (clave y lo que se espera), el mismo
que los demás ajustes. La pantalla de despliegues, la de retención del chat y
la de vacaciones leen los valores de `GET /settings/org-defaults`
(`propuestas`), que no es sólo para administradores.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Optional

from app.core.codigos_de_error import ErrorConCodigo
from app.services.settings_service.por_empresa import ajuste_de_empresa

logger = logging.getLogger("contecflow.settings")

#: Clave -> (mínimo, máximo) de los ajustes numéricos.
RANGOS: dict[str, tuple[float, float]] = {
    # Mínimo 5: lo que acepta una fase al crear el plan (`RolloutPhaseIn.duration_minutes`, ge=5).
    "CHANGE_CANARY_FIRST_MINUTES": (5, 1440),
    "CHANGE_CANARY_STEP_MINUTES": (5, 1440),
    "CHANGE_CANARY_LAST_MINUTES": (5, 1440),
    "CHAT_RETENTION_PROPOSED_MONTHS": (1, 120),
    "VACATION_MAX_DAYS_ENTITLED": (1, 366),
    "PERF_REMINDER_WINDOW_DAYS": (1, 90),
    "PERF_REMINDER_UNDATED_CYCLE_DAYS": (1, 365),
    "PERF_STALLED_CYCLE_DAYS": (1, 365),
    "PERF_STALLED_COMPLETION_PCT": (0, 100),
}

#: Fases de la rampa canaria: como mucho 10 (las que deja elegir la pantalla).
RAMPA_MIN_FASES = 2
RAMPA_MAX_FASES = 10

#: Todas las claves que se validan aquí (`DEFAULT_VACATION_DAYS_PER_YEAR` se
#: comprueba contra el máximo para que el par no quede desordenado).
VALIDADOS = frozenset(RANGOS) | {"CHANGE_CANARY_RAMP_PCT", "DEFAULT_VACATION_DAYS_PER_YEAR"}


def _no_valido(clave: str, valor: Any, esperado: str) -> ErrorConCodigo:
    return ErrorConCodigo("ajuste_valor_no_valido", detail=f"invalid value for {clave}: {valor!r} (expected {esperado})",
                          clave=clave, esperado=esperado)


def parsear_rampa(texto: str) -> list[int]:
    """'1, 5,25,50,100' -> [1, 5, 25, 50, 100]. ErrorConCodigo si no es una rampa válida."""
    esperado = f"{RAMPA_MIN_FASES}-{RAMPA_MAX_FASES} integers 1-100, increasing, ending in 100"
    try:
        rampa = [int(p.strip()) for p in str(texto or "").split(",") if p.strip()]
    except (TypeError, ValueError) as exc:
        raise _no_valido("CHANGE_CANARY_RAMP_PCT", texto, esperado) from exc
    if not (RAMPA_MIN_FASES <= len(rampa) <= RAMPA_MAX_FASES):
        raise _no_valido("CHANGE_CANARY_RAMP_PCT", texto, esperado)
    if any(not (1 <= p <= 100) for p in rampa) or rampa[-1] != 100:
        raise _no_valido("CHANGE_CANARY_RAMP_PCT", texto, esperado)
    if any(b <= a for a, b in zip(rampa, rampa[1:])):
        raise _no_valido("CHANGE_CANARY_RAMP_PCT", texto, esperado)
    return rampa


def meses_minimos_de_retencion(db, org_id: Optional[str]) -> int:
    """`RETENTION_MIN_DAYS` de la empresa en meses de 30 días (los del barrido del chat), redondeando arriba."""
    from app.core.config import settings
    from app.services.collaboration.compliance import DIAS_POR_MES
    from app.services.settings_service.runtime import get_runtime_int
    dias = get_runtime_int(db, "RETENTION_MIN_DAYS", org_id) if db is not None else None
    return max(1, math.ceil(int(dias if dias is not None else settings.RETENTION_MIN_DAYS) / DIAS_POR_MES))


def _tope_de_retencion_del_chat(db, org_id: Optional[str]) -> Optional[int]:
    """`max_months` de la empresa en el chat; sin empresa (fila global), sin tope propio."""
    if db is None or not org_id:
        return None
    from app.services.collaboration.compliance import get_retention_settings
    return int(get_retention_settings(db, org_id)["max_months"])


def validar(db, clave: str, guardado: str, org_id: Optional[str]) -> str:
    """El valor normalizado que se guarda, o ErrorConCodigo si no vale."""
    from app.services.settings_service.runtime import get_runtime_int

    if clave == "CHANGE_CANARY_RAMP_PCT":
        return ",".join(str(p) for p in parsear_rampa(guardado))

    if clave == "DEFAULT_VACATION_DAYS_PER_YEAR":
        tope = get_runtime_int(db, "VACATION_MAX_DAYS_ENTITLED", org_id)
        if tope is not None and float(guardado) > tope:
            raise _no_valido(clave, guardado, f"≤ VACATION_MAX_DAYS_ENTITLED ({tope})")
        return guardado

    minimo, maximo = RANGOS[clave]
    valor = float(guardado)
    if not (minimo <= valor <= maximo):
        raise _no_valido(clave, guardado, f"{minimo:g}..{maximo:g}")

    if clave == "CHAT_RETENTION_PROPOSED_MONTHS":
        meses_min = meses_minimos_de_retencion(db, org_id)
        if valor < meses_min:
            raise _no_valido(clave, guardado, f"≥ {meses_min} (RETENTION_MIN_DAYS)")
        tope = _tope_de_retencion_del_chat(db, org_id)
        if tope is not None and valor > tope:
            raise _no_valido(clave, guardado, f"≤ {tope} (chat retention maximum)")
    elif clave == "VACATION_MAX_DAYS_ENTITLED":
        por_defecto = get_runtime_int(db, "DEFAULT_VACATION_DAYS_PER_YEAR", org_id)
        if por_defecto is not None and valor < por_defecto:
            raise _no_valido(clave, guardado, f"≥ DEFAULT_VACATION_DAYS_PER_YEAR ({por_defecto})")
    return guardado


# ── Lectura por empresa ─────────────────────────────────────────────────────

def rampa_canaria(db, org_id: Optional[str] = None, *, registro: Any = None) -> list[int]:
    """La rampa de la empresa; si la fila guardada no vale (escrita a mano), la de por defecto."""
    from app.core.config import settings
    try:
        return parsear_rampa(ajuste_de_empresa(db, "CHANGE_CANARY_RAMP_PCT", org_id, registro=registro))
    except ValueError:
        logger.warning("CHANGE_CANARY_RAMP_PCT no válido; uso el de por defecto")
        return parsear_rampa(settings.CHANGE_CANARY_RAMP_PCT)


def _entero_en_rango(db, clave: str, org_id: Optional[str], registro: Any) -> int:
    """Un ajuste entero de RANGOS, recortado a su rango (una fila escrita a mano no lo rompe)."""
    minimo, maximo = RANGOS[clave]
    valor = ajuste_de_empresa(db, clave, org_id, registro=registro)
    return int(min(max(int(valor), minimo), maximo))


def minutos_canarios(db, org_id: Optional[str] = None, *, registro: Any = None) -> dict[str, int]:
    """Minutos de la primera fase, de cada intermedia y de la última."""
    return {
        "first": _entero_en_rango(db, "CHANGE_CANARY_FIRST_MINUTES", org_id, registro),
        "step": _entero_en_rango(db, "CHANGE_CANARY_STEP_MINUTES", org_id, registro),
        "last": _entero_en_rango(db, "CHANGE_CANARY_LAST_MINUTES", org_id, registro),
    }


def retencion_propuesta_del_chat(db, org_id: Optional[str] = None) -> int:
    """Meses que se proponen al crear una política del chat, dentro del mínimo y del tope de la empresa."""
    meses = _entero_en_rango(db, "CHAT_RETENTION_PROPOSED_MONTHS", org_id, None)
    meses = max(meses, meses_minimos_de_retencion(db, org_id))
    tope = _tope_de_retencion_del_chat(db, org_id)
    return min(meses, tope) if tope is not None else meses


def maximo_de_dias_de_vacaciones(db, org_id: Optional[str] = None, *, registro: Any = None) -> int:
    """Días de vacaciones que se pueden asignar como mucho a una persona en un año."""
    return _entero_en_rango(db, "VACATION_MAX_DAYS_ENTITLED", org_id, registro)


def plazos_de_evaluaciones(db, org_id: Optional[str] = None, *, registro: Any = None) -> dict[str, float]:
    """Plazos de recordatorios y de ciclos atascados de evaluaciones de desempeño."""
    pct = float(ajuste_de_empresa(db, "PERF_STALLED_COMPLETION_PCT", org_id, registro=registro))
    return {
        "ventana_dias": _entero_en_rango(db, "PERF_REMINDER_WINDOW_DAYS", org_id, registro),
        "sin_cierre_dias": _entero_en_rango(db, "PERF_REMINDER_UNDATED_CYCLE_DAYS", org_id, registro),
        "atascado_dias": _entero_en_rango(db, "PERF_STALLED_CYCLE_DAYS", org_id, registro),
        "atascado_pct": min(max(pct, 0.0), 100.0),
    }


def propuestas_de_formulario(db, org_id: Optional[str]) -> dict:
    """Lo que leen las pantallas en `GET /settings/org-defaults` (`propuestas`)."""
    return {
        "change_canary_ramp_pct": rampa_canaria(db, org_id),
        "change_canary_minutes": minutos_canarios(db, org_id),
        "chat_retention_proposed_months": retencion_propuesta_del_chat(db, org_id),
        "vacation_max_days_entitled": maximo_de_dias_de_vacaciones(db, org_id),
    }
