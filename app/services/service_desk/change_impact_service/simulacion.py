"""Simulacion «que pasaria si» de un cambio y de su ventana propuesta.

Parte de `app.services.service_desk.change_impact_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.models.service_desk import ITSMChangeRequest, ChangeType, Ticket
from app.core.errores import ErrorDeDominio

from app.services.service_desk.change_impact_service.riesgo import (
    score_change_risk,
    suggest_maintenance_window,
)


# ══════════════════════════════════════════════════════════════════════════════
# What-If Simulation — pure computation, no DB writes
# ══════════════════════════════════════════════════════════════════════════════

#: Orden de los niveles de riesgo. Es una escala, y compararla por posición es
#: lo que distingue «subió» de «bajó»; alfabéticamente `critical < low`.
_ORDEN_DE_RIESGO = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def _cis_directos(change) -> list[str]:
    """Los CI declarados en el cambio. Un JSON roto se lee como «ninguno».

    Tragarse el error es deliberado: `affected_cis` es texto libre guardado por
    versiones anteriores, y un cambio con ese campo corrupto sigue siendo un
    cambio que se puede simular — con menos información, no con un 500.
    """
    try:
        if not change.affected_cis:
            return []
        crudo = json.loads(change.affected_cis)
        return crudo if isinstance(crudo, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _cambio_simulado(change, overrides: dict):
    """Un cambio **de mentira** con los overrides aplicados.

    Es un `SimpleNamespace` y no una entidad a propósito: esta función no
    persiste nada, y crear una entidad de SQLAlchemy —aunque no se guarde— la
    mete en la sesión y acaba escribiéndose en el siguiente `flush`.
    """
    from types import SimpleNamespace

    ids = _cis_directos(change)
    for cid in overrides.get("extra_ci_ids", []):
        if cid not in ids:
            ids.append(cid)
    a_quitar = set(overrides.get("remove_ci_ids", []))
    ids = [cid for cid in ids if cid not in a_quitar]

    tipo = change.change_type
    if "change_type" in overrides:
        try:
            tipo = ChangeType(overrides["change_type"])
        except ValueError:
            # Un tipo inválido no invalida la simulación entera: se ignora y se
            # conserva el original, que es lo que el usuario vería de todas
            # formas si no hubiera pedido cambiarlo.
            pass

    minutos = (
        int(overrides["downtime_minutes"]) if "downtime_minutes" in overrides
        else (change.downtime_minutes or 0)
    )
    return SimpleNamespace(
        change_type=tipo,
        risk=change.risk,
        affected_cis=json.dumps(ids),
        downtime_minutes=minutos,
    )


def _matriz_de_incidencias(db: Session, ci_ids: list[str]) -> list[list[int]]:
    """Incidencias de las últimas cuatro semanas por día de la semana y hora."""
    corte = datetime.now(tz=timezone.utc) - timedelta(days=28)
    q = db.query(Ticket.created_at).filter(
        Ticket.created_at >= corte,
        Ticket.ticket_type == "incident",
    )
    if ci_ids:
        q = q.filter(Ticket.ci_id.in_(ci_ids))

    freq: list[list[int]] = [[0] * 24 for _ in range(7)]
    for (ts,) in q.all():
        if ts:
            # Las filas guardadas antes de que las fechas llevaran zona se leen
            # como UTC; sin esto, `weekday()` de una naive mezcla husos.
            ts_utc = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts
            freq[ts_utc.weekday()][ts_utc.hour] += 1
    return freq


def _evaluar_ventana_propuesta(db: Session, overrides: dict, ci_ids: list[str],
                               ventana_optima: dict) -> dict:
    """Cuántas incidencias caen en la franja que pide quien llama, y si es peor.

    Se compara contra la óptima con un margen de 0,1 incidencias: sin margen,
    una diferencia de redondeo marcaría como «no óptima» una franja que lo es.
    """
    hora = max(0, min(23, int(overrides.get("scheduled_hour_utc", ventana_optima["hour_utc"]))))
    dia = max(0, min(6, int(overrides.get("scheduled_dow", ventana_optima["day_of_week"]))))

    freq = _matriz_de_incidencias(db, ci_ids)
    # La ventana de mantenimiento son cuatro horas; el `% 24` la deja cruzar la
    # medianoche sin salirse de la fila del día.
    total = sum(freq[dia][(hora + i) % 24] for i in range(4))
    media = total / 4

    dias = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    return {
        "day_of_week": dia,
        "hour_utc": hora,
        "window_label": f"{dias[dia]} {hora:02d}:00–{(hora + 4) % 24:02d}:00 UTC",
        "avg_incidents_in_window": round(media, 2),
        "vs_optimal_diff": round(media - ventana_optima["avg_incidents_in_window"], 2),
        "is_optimal": media <= ventana_optima["avg_incidents_in_window"] + 0.1,
    }


def _lado_del_informe(riesgo: dict, ci_ids: list[str], ventana: dict) -> dict:
    """Un lado de la comparación. Los dos tienen exactamente la misma forma."""
    return {
        "score": riesgo["score"],
        "risk_label": riesgo["risk_label"],
        "components": riesgo["components"],
        "ci_count_expanded": len(ci_ids),
        "window": ventana,
    }


def simulate_change_whatif(
    db: Session,
    change_id: str,
    overrides: dict,
) -> dict:
    """Simula el impacto de cambios hipotéticos sobre una petición de cambio.

    **No persiste nada.** Devuelve la comparación lado a lado del escenario
    original y el simulado: puntuación de riesgo, etiqueta, componentes y
    ventana de mantenimiento.

    Overrides admitidos (todos opcionales):
        downtime_minutes   (int)  : otra parada planificada
        change_type        (str)  : standard | normal | emergency
        extra_ci_ids       (list) : CI que se añaden al conjunto afectado
        remove_ci_ids      (list) : CI que se quitan
        scheduled_hour_utc (int)  : evalúa una hora concreta (0-23) para la ventana
        scheduled_dow      (int)  : evalúa un día de la semana (0=lunes)

    Auditoría 2026-09 (hallazgo 18): eran 159 líneas y complejidad 15, con la
    construcción del cambio falso, la matriz de incidencias y el montaje del
    informe mezclados. Cada pieza tiene ahora su nombre y se puede probar sola.
    """
    change = db.query(ITSMChangeRequest).filter(ITSMChangeRequest.id == change_id).first()
    if not change:
        raise ErrorDeDominio(404, f"Change {change_id} not found")

    riesgo_orig = score_change_risk(db, change)
    cis_orig = riesgo_orig["ci_ids_expanded"]
    ventana_orig = suggest_maintenance_window(db, change, cis_orig)

    simulado = _cambio_simulado(change, overrides)
    riesgo_sim = score_change_risk(db, simulado)  # type: ignore[arg-type]
    cis_sim = riesgo_sim["ci_ids_expanded"]
    ventana_sim = suggest_maintenance_window(db, change, cis_sim)

    salto = (_ORDEN_DE_RIESGO.get(riesgo_sim["risk_label"], 2)
             - _ORDEN_DE_RIESGO.get(riesgo_orig["risk_label"], 2))

    result: dict = {
        "change_id": change_id,
        "change_number": change.number,
        "original": _lado_del_informe(riesgo_orig, cis_orig, ventana_orig),
        "simulated": _lado_del_informe(riesgo_sim, cis_sim, ventana_sim),
        "delta": {
            "score_diff": riesgo_sim["score"] - riesgo_orig["score"],
            "risk_change": "escalated" if salto > 0 else "reduced" if salto < 0 else "unchanged",
            "ci_count_diff": len(cis_sim) - len(cis_orig),
            "window_changed": ventana_sim["window_label"] != ventana_orig["window_label"],
        },
        # Las listas de CI se devuelven tal cual y no filtradas: quien pidió la
        # simulación necesita ver qué pidió, no una versión resumida.
        "overrides_applied": dict(overrides),
    }

    if "scheduled_hour_utc" in overrides or "scheduled_dow" in overrides:
        result["proposed_window_evaluation"] = _evaluar_ventana_propuesta(
            db, overrides, cis_sim, ventana_sim,
        )
    return result
