"""ai_modules.predictions — extracted from the former ai_modules_service god-file."""

from __future__ import annotations
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.ai_chat import (
    AIPrediction,
)
from app.models.project import Project
from dataclasses import dataclass

_log = logging.getLogger(__name__)


# ── Predicción de sobrecoste y retraso ───────────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 18). `predict_overrun_ml` era complejidad 20 y es
# un modelo de puntuacion puro: trece reglas de umbral escritas como cadenas de
# `elif`, cada una sumando pesos a dos marcadores y anadiendo una senal.
#
# Escrito asi, los pesos del modelo estaban repartidos por veinte lineas de
# codigo y no se podian leer de un vistazo ni comparar entre si. Ahora son una
# tabla: cambiar la calibracion es editar numeros, no reescribir ramas.
#
# **Los numeros y los textos son los del original, sin tocar ni uno.** El nombre
# de la funcion dice «ml» pero no hay aprendizaje: son umbrales fijados a mano,
# y su docstring ya lo decia («heuristic ensemble»).


@dataclass(frozen=True, slots=True)
class _Regla:
    """Una regla del modelo: su umbral, lo que suma y como se reporta.

    `peso_reportado` se guarda aparte de las dos sumas porque en el original NO
    siempre coincide con ellas. En las reglas de tipo «both» se reportaba el
    peso de una de las dos dimensiones y no la suma:

      · tareas vencidas > 40 %  ->  suma 0,25 a calendario y 0,10 a coste,
                                    y reporta 0,25 (el de calendario)
      · equipo sobrecargado     ->  suma 0,15 a coste y 0,20 a calendario,
                                    y reporta 0,15 (el de COSTE)

    Es incoherente entre las dos, pero es lo que se muestra en la interfaz y se
    conserva tal cual: cambiarlo alteraria los pesos que ve quien usa el panel.
    """

    umbral: float
    texto: str
    suma_coste: float
    suma_calendario: float
    peso_reportado: float
    tipo: str          # "cost" | "schedule" | "both"


def _dos_decimales(v) -> float:
    return round(v, 2)


def _un_decimal(v) -> float:
    return round(v, 1)


def _porcentaje_de_ratio(v) -> str:
    return f"{v * 100:.0f}%"


def _porcentaje(v) -> str:
    return f"{v:.0f}%"


# Reglas de «menor que»: se evalua en orden y gana la primera que cumple, igual
# que la cadena de `elif` original.
_REGLAS_POR_DEBAJO = {
    "cpi": (_dos_decimales, (
        _Regla(0.70, "CPI crítico", 0.45, 0.0, 0.45, "cost"),
        _Regla(0.85, "CPI bajo", 0.25, 0.0, 0.25, "cost"),
        _Regla(1.00, "CPI ligeramente bajo", 0.10, 0.0, 0.10, "cost"),
    )),
    "spi": (_dos_decimales, (
        _Regla(0.65, "SPI crítico (muy retrasado)", 0.0, 0.5, 0.5, "schedule"),
        _Regla(0.80, "SPI bajo", 0.0, 0.3, 0.3, "schedule"),
        _Regla(0.95, "SPI moderadamente bajo", 0.0, 0.15, 0.15, "schedule"),
    )),
}

# Reglas de «mayor que».
_REGLAS_POR_ENCIMA = {
    "burn_delta": (_un_decimal, (
        _Regla(20, "Quema de presupuesto avanzada vs tiempo", 0.3, 0.0, 0.3, "cost"),
        _Regla(10, "Quema de presupuesto algo elevada", 0.15, 0.0, 0.15, "cost"),
    )),
    "completion_gap": (_un_decimal, (
        _Regla(25, "Tareas retrasadas respecto al avance temporal", 0.0, 0.35, 0.35, "schedule"),
        _Regla(10, "Leve retraso en finalización de tareas", 0.0, 0.15, 0.15, "schedule"),
    )),
    "overdue_task_ratio": (_porcentaje_de_ratio, (
        _Regla(0.4, "Alto porcentaje de tareas vencidas", 0.1, 0.25, 0.25, "both"),
        _Regla(0.2, "Tareas vencidas moderadas", 0.0, 0.1, 0.1, "schedule"),
    )),
    "team_load_pct": (_porcentaje, (
        _Regla(110, "Equipo sobrecargado (burnout risk)", 0.15, 0.2, 0.15, "both"),
    )),
}

# Tope de probabilidad. No llega a 1,0 a proposito: el modelo son heuristicas,
# y presentar «100 % de probabilidad de sobrecoste» seria afirmar mas de lo que
# sabe.
_PROBABILIDAD_MAXIMA = 0.97

# Cuantas senales hacen falta para cada nivel de confianza.
_SENALES_PARA_CONFIANZA_ALTA = 4
_SENALES_PARA_CONFIANZA_MEDIA = 2

# Recomendaciones, en orden de evaluacion. La primera cuya condicion se cumple
# es la que se devuelve.
_RECOMENDACIONES = (
    (lambda c, s: c > 0.6 and s > 0.6,
     "Revisión ejecutiva urgente: alto riesgo de sobrecosto y retraso. "
     "Considera replanning o recorte de alcance."),
    (lambda c, s: c > 0.5,
     "Revisar coste: CPI bajo indica gasto mayor que lo planificado. "
     "Optimiza asignaciones."),
    (lambda c, s: s > 0.5,
     "Revisar cronograma: SPI bajo y tareas vencidas. Considera aumentar "
     "capacidad o reducir alcance."),
    (lambda c, s: c + s < 0.3,
     "Proyecto dentro de parámetros normales. Mantén el seguimiento semanal."),
)
_RECOMENDACION_POR_DEFECTO = (
    "Señales de alerta moderadas. Monitorea KPIs semana a semana."
)


def _aplicar_reglas(valores: dict) -> tuple[float, float, list]:
    """Evalua las trece reglas. Devuelve (coste, calendario, señales).

    Por cada metrica se toma SOLO la primera regla que cumple, igual que la
    cadena de `elif` original: los umbrales de una misma metrica son niveles de
    gravedad, no sumandos.
    """
    coste = 0.0
    calendario = 0.0
    senales = []

    for familia, comparar in (
        (_REGLAS_POR_DEBAJO, lambda v, u: v < u),
        (_REGLAS_POR_ENCIMA, lambda v, u: v > u),
    ):
        for metrica, (formato, reglas) in familia.items():
            valor = valores[metrica]
            for regla in reglas:
                if comparar(valor, regla.umbral):
                    coste += regla.suma_coste
                    calendario += regla.suma_calendario
                    senales.append({
                        "signal": regla.texto,
                        "value": formato(valor),
                        "weight": regla.peso_reportado,
                        "type": regla.tipo,
                    })
                    break

    return coste, calendario, senales


def _recomendacion(cost_prob: float, sched_prob: float) -> str:
    for cumple, texto in _RECOMENDACIONES:
        if cumple(cost_prob, sched_prob):
            return texto
    return _RECOMENDACION_POR_DEFECTO


def predict_overrun_ml(
    cpi: float, spi: float,
    budget_used_pct: float, elapsed_pct: float,
    task_completion_pct: float,
    overdue_task_ratio: float,
    team_load_pct: float,
) -> dict:
    """
    Heuristic ensemble model for overrun prediction.
    Returns probabilities, magnitudes, confidence, signals, and recommendation.
    """
    cost_score, sched_score, signals = _aplicar_reglas({
        "cpi": cpi,
        "spi": spi,
        # Cuanto mas rapido se gasta el presupuesto que pasa el tiempo.
        "burn_delta": budget_used_pct - elapsed_pct,
        # Cuanto se retrasan las tareas respecto al tiempo consumido.
        "completion_gap": elapsed_pct - task_completion_pct,
        "overdue_task_ratio": overdue_task_ratio,
        "team_load_pct": team_load_pct,
    })

    cost_prob = min(round(cost_score, 2), _PROBABILIDAD_MAXIMA)
    sched_prob = min(round(sched_score, 2), _PROBABILIDAD_MAXIMA)

    # Magnitudes: cuanto se pasaria si el rendimiento actual se mantiene. Solo
    # tienen sentido con el indice por debajo de 1 (y por encima de 0, que es
    # el caso de un proyecto sin coste o sin calendario todavia).
    cost_overrun_pct = 0.0
    if 0 < cpi < 1:
        cost_overrun_pct = round((1 / cpi - 1) * 100 * budget_used_pct / 100, 1)

    sched_overrun_days = 0
    if 0 < spi < 1:
        # Los 30 dias son el horizonte de referencia del modelo, no la duracion
        # del proyecto: el resultado es «dias de retraso por mes de trabajo».
        sched_overrun_days = max(0, int((1 / spi - 1) * 30))

    n_signals = len(signals)
    if n_signals >= _SENALES_PARA_CONFIANZA_ALTA:
        confidence = "high"
    elif n_signals >= _SENALES_PARA_CONFIANZA_MEDIA:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "cost_overrun_prob":     cost_prob,
        "schedule_overrun_prob": sched_prob,
        "cost_overrun_pct":      cost_overrun_pct,
        "schedule_overrun_days": sched_overrun_days,
        "confidence":            confidence,
        "signals":               signals,
        "recommendation":        _recomendacion(cost_prob, sched_prob),
    }


def list_predictions(db: Session, severity=None, prediction_type=None, only_unacked: bool = True):
    q = db.query(AIPrediction)
    if severity:        q = q.filter(AIPrediction.severity == severity)
    if prediction_type: q = q.filter(AIPrediction.prediction_type == prediction_type)
    if only_unacked:    q = q.filter(AIPrediction.is_acknowledged == False)
    preds = q.order_by(AIPrediction.created_at.desc()).limit(50).all()
    return [{
        "id": p.id, "type": p.prediction_type, "severity": p.severity,
        "title": p.title, "explanation": p.explanation,
        "recommended_action": p.recommended_action,
        "probability": p.probability, "entity_type": p.entity_type,
        "entity_id": p.entity_id, "created_at": str(p.created_at)[:16],
        "methodology": "rules_based",
    } for p in preds]

def acknowledge_prediction(db: Session, pred_id: str, user_id: str) -> dict:
    pred = db.query(AIPrediction).filter(AIPrediction.id == pred_id).first()
    if not pred:
        raise ValueError("not_found")
    pred.is_acknowledged = True
    pred.acknowledged_by = user_id
    pred.acknowledged_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}

def get_overrun_prediction_data(db: Session, project_id: str) -> dict:
    """Build overrun-prediction payload reutilizando ``extract_project_features``.

    Item #56: antes este código duplicaba el cálculo CPI/SPI con otras
    constantes (no usaba ``AI_REVENUE_HOURLY_RATE_FALLBACK``, no respetaba
    ``cost_amount`` correctamente). Ahora delegamos en la fuente canónica
    de features ML y solo añadimos ``project`` ORM object como conveniencia.
    """
    from app.services.ml_features import extract_project_features

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("not_found")

    feats = extract_project_features(db, project_id)
    if feats is None:
        raise ValueError("no_tasks")

    return {
        "project": project,
        "cpi": feats["cpi"],
        "spi": feats["spi"],
        "budget_used_pct": feats["budget_used_pct"],
        "elapsed_pct": feats["elapsed_pct"],
        "task_completion_pct": feats["task_completion_pct"],
        "overdue_ratio": feats["overdue_ratio"],
    }
