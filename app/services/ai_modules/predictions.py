"""ai_modules.predictions — extracted from the former ai_modules_service god-file."""

from __future__ import annotations
import json
import time
import logging
from datetime import datetime, timedelta, date, timezone
from app.core.timeutil import utcnow
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.config import settings
from app.services.ai_dispatch import call_ai
from app.core.security import verify_client_token
from app.models.ai_chat import (
    AIActionLog, AIPrediction, AIVoiceCommand,
    AIMeeting, AIMeetingAction, AIContract, AIContractClause,
    AIKBArticle, AIClientChatSession, AIClientChatMessage,
    AIAgentExecution as _ExecRecord,
)
from app.models.imputation import Imputation
from app.models.project import Project
from app.models.service_desk import Ticket
from app.models.task import Task
from app.models.user import User
from app.worker import run_agent_task
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

_log = logging.getLogger(__name__)


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
    signals = []
    cost_score = 0.0
    sched_score = 0.0

    if cpi < 0.7:
        cost_score += 0.45
        signals.append({"signal": "CPI crítico", "value": round(cpi, 2), "weight": 0.45, "type": "cost"})
    elif cpi < 0.85:
        cost_score += 0.25
        signals.append({"signal": "CPI bajo", "value": round(cpi, 2), "weight": 0.25, "type": "cost"})
    elif cpi < 1.0:
        cost_score += 0.10
        signals.append({"signal": "CPI ligeramente bajo", "value": round(cpi, 2), "weight": 0.10, "type": "cost"})

    if spi < 0.65:
        sched_score += 0.5
        signals.append({"signal": "SPI crítico (muy retrasado)", "value": round(spi, 2), "weight": 0.5, "type": "schedule"})
    elif spi < 0.8:
        sched_score += 0.3
        signals.append({"signal": "SPI bajo", "value": round(spi, 2), "weight": 0.3, "type": "schedule"})
    elif spi < 0.95:
        sched_score += 0.15
        signals.append({"signal": "SPI moderadamente bajo", "value": round(spi, 2), "weight": 0.15, "type": "schedule"})

    burn_delta = budget_used_pct - elapsed_pct
    if burn_delta > 20:
        cost_score += 0.3
        signals.append({"signal": "Quema de presupuesto avanzada vs tiempo", "value": round(burn_delta, 1), "weight": 0.3, "type": "cost"})
    elif burn_delta > 10:
        cost_score += 0.15
        signals.append({"signal": "Quema de presupuesto algo elevada", "value": round(burn_delta, 1), "weight": 0.15, "type": "cost"})

    completion_gap = elapsed_pct - task_completion_pct
    if completion_gap > 25:
        sched_score += 0.35
        signals.append({"signal": "Tareas retrasadas respecto al avance temporal", "value": round(completion_gap, 1), "weight": 0.35, "type": "schedule"})
    elif completion_gap > 10:
        sched_score += 0.15
        signals.append({"signal": "Leve retraso en finalización de tareas", "value": round(completion_gap, 1), "weight": 0.15, "type": "schedule"})

    if overdue_task_ratio > 0.4:
        sched_score += 0.25
        cost_score  += 0.1
        signals.append({"signal": "Alto porcentaje de tareas vencidas", "value": f"{overdue_task_ratio*100:.0f}%", "weight": 0.25, "type": "both"})
    elif overdue_task_ratio > 0.2:
        sched_score += 0.1
        signals.append({"signal": "Tareas vencidas moderadas", "value": f"{overdue_task_ratio*100:.0f}%", "weight": 0.1, "type": "schedule"})

    if team_load_pct > 110:
        cost_score  += 0.15
        sched_score += 0.2
        signals.append({"signal": "Equipo sobrecargado (burnout risk)", "value": f"{team_load_pct:.0f}%", "weight": 0.15, "type": "both"})

    cost_prob  = min(round(cost_score,  2), 0.97)
    sched_prob = min(round(sched_score, 2), 0.97)

    cost_overrun_pct = 0.0
    if cpi > 0 and cpi < 1:
        cost_overrun_pct = round((1 / cpi - 1) * 100 * budget_used_pct / 100, 1)

    sched_overrun_days = 0
    if spi > 0 and spi < 1:
        sched_overrun_days = max(0, int((1 / spi - 1) * 30))

    n_signals = len(signals)
    confidence = "high" if n_signals >= 4 else ("medium" if n_signals >= 2 else "low")

    if cost_prob > 0.6 and sched_prob > 0.6:
        rec = "Revisión ejecutiva urgente: alto riesgo de sobrecosto y retraso. Considera replanning o recorte de alcance."
    elif cost_prob > 0.5:
        rec = "Revisar coste: CPI bajo indica gasto mayor que lo planificado. Optimiza asignaciones."
    elif sched_prob > 0.5:
        rec = "Revisar cronograma: SPI bajo y tareas vencidas. Considera aumentar capacidad o reducir alcance."
    elif cost_prob + sched_prob < 0.3:
        rec = "Proyecto dentro de parámetros normales. Mantén el seguimiento semanal."
    else:
        rec = "Señales de alerta moderadas. Monitorea KPIs semana a semana."

    return {
        "cost_overrun_prob":     cost_prob,
        "schedule_overrun_prob": sched_prob,
        "cost_overrun_pct":      cost_overrun_pct,
        "schedule_overrun_days": sched_overrun_days,
        "confidence":            confidence,
        "signals":               signals,
        "recommendation":        rec,
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
    from app.services.ml_features import extract_project_features  # noqa: PLC0415

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
