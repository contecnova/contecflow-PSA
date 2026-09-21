"""
Change Impact Service — Fase 2 ITSM Intelligence
=================================================
Sprint 13-14: Análisis de impacto automático y scoring de riesgo para Change Requests.

Capacidades:
  1. score_change_risk()       — score 0-100 automático basado en heurísticas + histórico
  2. analyze_affected_cis()   — expande CIs afectados via grafo de dependencias
  3. suggest_maintenance_window() — ventana de menor incidentalidad (últimas 4 semanas)
  4. generate_impact_report() — informe completo para el CAB
  5. score_and_persist()      — wrapper que actualiza el Change Request en BD

Todos los métodos son read-only excepto score_and_persist (que escribe en el CR).
"""
from __future__ import annotations

import json
import logging
import os as _os
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.service_desk import ChangeStatus as _ChangeStatus
from app.models.service_desk import (
    CIRelation,
    ConfigurationItem,
    ITSMChangeRequest,
    ChangeRisk,
    ChangeType,
    Ticket,
)

logger = logging.getLogger(__name__)

# ── Risk scoring weights ──────────────────────────────────────────────────────

_CHANGE_TYPE_RISK = {
    ChangeType.standard: 10,
    ChangeType.normal: 40,
    ChangeType.emergency: 80,
}

_CURRENT_RISK_SCORE = {
    ChangeRisk.low: 10,
    ChangeRisk.medium: 35,
    ChangeRisk.high: 65,
    ChangeRisk.critical: 90,
}

# Number of affected CIs → risk contribution (capped at 30)
def _ci_count_risk(n: int) -> int:
    if n == 0:
        return 0
    elif n <= 2:
        return 10
    elif n <= 5:
        return 20
    else:
        return 30


# Downtime minutes → risk contribution (capped at 20)
def _downtime_risk(minutes: int) -> int:
    if minutes == 0:
        return 0
    elif minutes <= 30:
        return 5
    elif minutes <= 120:
        return 10
    elif minutes <= 480:
        return 15
    else:
        return 20


# ── CI dependency expansion ───────────────────────────────────────────────────

def _expand_ci_dependencies(
    db: Session,
    ci_ids: list[str],
    depth: int = 2,
) -> list[str]:
    """BFS-expand *ci_ids* via CIRelation to depth *depth*.

    Returns deduplicated list of all reachable CI IDs (including originals).
    """
    visited: set[str] = set(ci_ids)
    frontier = list(ci_ids)

    for _ in range(depth):
        if not frontier:
            break
        related = (
            db.query(CIRelation)
            .filter(
                CIRelation.source_ci_id.in_(frontier)
                | CIRelation.target_ci_id.in_(frontier)
            )
            .all()
        )
        next_frontier: list[str] = []
        for rel in related:
            for cid in (rel.source_ci_id, rel.target_ci_id):
                if cid not in visited:
                    visited.add(cid)
                    next_frontier.append(cid)
        frontier = next_frontier

    return list(visited)


def _get_ci_details(db: Session, ci_ids: list[str]) -> list[dict]:
    """Return lightweight info dicts for the given CI IDs."""
    if not ci_ids:
        return []
    cis = (
        db.query(ConfigurationItem)
        .filter(ConfigurationItem.id.in_(ci_ids))
        .all()
    )
    return [
        {
            "id": ci.id,
            "name": ci.name,
            "ci_type": ci.ci_type,
            "status": ci.status,
            "criticality": getattr(ci, "criticality", "normal"),
        }
        for ci in cis
    ]


# ── Open-ticket overlap ───────────────────────────────────────────────────────

def _open_tickets_on_cis(db: Session, ci_ids: list[str]) -> int:
    """Count open tickets linked to any of the CIs affected by the change."""
    if not ci_ids:
        return 0
    return (
        db.query(func.count(Ticket.id))
        .filter(
            Ticket.ci_id.in_(ci_ids),
            Ticket.status.notin_(["resolved", "closed"]),
        )
        .scalar()
        or 0
    )


# ── Incident history in window ────────────────────────────────────────────────

def _incident_count_last_days(
    db: Session, ci_ids: list[str], days: int = 30
) -> int:
    """Count incidents involving these CIs in the last *days* days."""
    if not ci_ids:
        return 0
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    return (
        db.query(func.count(Ticket.id))
        .filter(
            Ticket.ci_id.in_(ci_ids),
            Ticket.created_at >= cutoff,
        )
        .scalar()
        or 0
    )


# ── Maintenance window suggestion ─────────────────────────────────────────────

def suggest_maintenance_window(
    db: Session,
    change: ITSMChangeRequest,
    ci_ids: Optional[list[str]] = None,
) -> dict:
    """Suggest the lowest-incident 4-hour window over the next 7 days.

    Uses hourly incident frequency over the last 28 days to find the
    quietest combination of day-of-week + hour.

    Returns:
        {
          "day_of_week": 0-6 (0=Mon),
          "hour_utc": 0-23,
          "window_label": "Tuesday 02:00–06:00 UTC",
          "avg_incidents_in_window": float,
          "confidence": "low|medium|high",
        }
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=28)

    q = db.query(Ticket.created_at).filter(
        Ticket.created_at >= cutoff,
        Ticket.ticket_type == "incident",
    )
    if ci_ids:
        q = q.filter(Ticket.ci_id.in_(ci_ids))

    incidents = q.all()

    # Build hour_of_week frequency matrix (7 days × 24 hours)
    freq: list[list[int]] = [[0] * 24 for _ in range(7)]
    for (ts,) in incidents:
        if ts:
            ts_utc = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts
            dow = ts_utc.weekday()  # 0=Mon
            freq[dow][ts_utc.hour] += 1

    # Find 4-consecutive-hour window with minimum sum
    best_dow = 0
    best_hour = 2  # default: 02:00 UTC weekday
    best_sum = float("inf")

    for dow in range(7):
        for h in range(24):
            window_sum = sum(freq[dow][(h + i) % 24] for i in range(4))
            if window_sum < best_sum:
                best_sum = window_sum
                best_dow = dow
                best_hour = h

    _days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    window_label = f"{_days[best_dow]} {best_hour:02d}:00–{(best_hour+4)%24:02d}:00 UTC"

    confidence = "high" if len(incidents) >= 50 else ("medium" if len(incidents) >= 10 else "low")

    return {
        "day_of_week": best_dow,
        "hour_utc": best_hour,
        "window_label": window_label,
        "avg_incidents_in_window": round(best_sum / 4, 2),
        "confidence": confidence,
    }


# ── Risk scoring ──────────────────────────────────────────────────────────────

def score_change_risk(
    db: Session,
    change: ITSMChangeRequest,
) -> dict:
    """Compute automated risk score 0-100 for a Change Request.

    Components:
      - Change type             (10-80 pts)
      - Number of affected CIs  (0-30 pts)
      - Downtime planned        (0-20 pts)
      - Open tickets on CIs     (0-15 pts  penalty)
      - Recent incident history (0-15 pts  penalty)

    Returns:
        {
          "score": int,         # 0-100
          "risk_label": str,    # low|medium|high|critical
          "components": dict,
          "ci_ids_direct": list,
          "ci_ids_expanded": list,
        }
    """
    # Parse affected CIs from JSON
    direct_ci_ids: list[str] = []
    try:
        if change.affected_cis:
            raw = json.loads(change.affected_cis)
            direct_ci_ids = raw if isinstance(raw, list) else []
    except (json.JSONDecodeError, TypeError):
        direct_ci_ids = []

    expanded_ci_ids = _expand_ci_dependencies(db, direct_ci_ids, depth=2)

    # Scoring components
    type_score = _CHANGE_TYPE_RISK.get(change.change_type, 40)
    ci_score = _ci_count_risk(len(expanded_ci_ids))
    downtime_score = _downtime_risk(change.downtime_minutes or 0)

    open_tickets_n = _open_tickets_on_cis(db, expanded_ci_ids)
    open_tickets_penalty = min(15, open_tickets_n * 3)

    recent_incidents = _incident_count_last_days(db, expanded_ci_ids, days=30)
    incident_penalty = min(15, recent_incidents * 2)

    total = type_score + ci_score + downtime_score + open_tickets_penalty + incident_penalty
    total = min(100, total)

    risk_label = (
        "critical" if total >= 75
        else "high" if total >= 55
        else "medium" if total >= 30
        else "low"
    )

    return {
        "score": total,
        "risk_label": risk_label,
        "components": {
            "change_type_score": type_score,
            "ci_count_score": ci_score,
            "downtime_score": downtime_score,
            "open_tickets_penalty": open_tickets_penalty,
            "incident_penalty": incident_penalty,
        },
        "ci_ids_direct": direct_ci_ids,
        "ci_ids_expanded": expanded_ci_ids,
    }


# ── Impact report ─────────────────────────────────────────────────────────────

def generate_impact_report(db: Session, change_id: str) -> dict:
    """Generate a comprehensive impact analysis report for CAB review.

    Returns a structured dict ready to be serialised as JSON and stored
    in `sd_change_requests.impact_analysis_json`.
    """
    change = db.query(ITSMChangeRequest).filter(ITSMChangeRequest.id == change_id).first()
    if not change:
        return {"error": f"Change {change_id} not found"}

    risk_data = score_change_risk(db, change)
    ci_details = _get_ci_details(db, risk_data["ci_ids_expanded"])

    # CI criticality summary
    critical_cis = [c for c in ci_details if c.get("criticality") in ("critical", "high")]

    window = suggest_maintenance_window(db, change, risk_data["ci_ids_expanded"])

    open_incidents = _open_tickets_on_cis(db, risk_data["ci_ids_expanded"])
    recent_incidents_30d = _incident_count_last_days(db, risk_data["ci_ids_expanded"], 30)

    report = {
        "change_id": change_id,
        "change_number": change.number,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "risk_score": risk_data["score"],
        "risk_label": risk_data["risk_label"],
        "risk_components": risk_data["components"],
        "affected_cis": {
            "direct_count": len(risk_data["ci_ids_direct"]),
            "expanded_count": len(risk_data["ci_ids_expanded"]),
            "critical_cis": [c["name"] for c in critical_cis],
            "ci_list": ci_details,
        },
        "open_incidents_on_cis": open_incidents,
        "incidents_last_30d": recent_incidents_30d,
        "suggested_window": window,
        "summary": (
            f"Change '{change.title}' affects {len(risk_data['ci_ids_expanded'])} CIs "
            f"(direct: {len(risk_data['ci_ids_direct'])}). "
            f"Risk score: {risk_data['score']}/100 ({risk_data['risk_label'].upper()}). "
            f"Suggested maintenance window: {window['window_label']}."
        ),
    }

    return report


# ── Persist scoring back to the Change Request ────────────────────────────────

#: Los estados en los que un cambio esta esperando decision del CAB.
#:
#: Auditoria 2026-08 (hallazgo 22). Esto era `["submitted", "in_approval"]`, y
#: **`in_approval` no existe en el enum del modelo**. Hay DOS enums llamados
#: `ChangeStatus` en el repositorio:
#:
#:   · `app/models/service_desk/_enums.py` -> draft, submitted, **cab_review**,
#:     approved, scheduled, in_progress, implemented, post_review,
#:     closed_success, closed_failed, cancelled. Es el que usa la **columna**.
#:   · `app/services/service_desk/change_management_service.py` -> draft,
#:     submitted, **in_approval**, approved, ... Un enum local del servicio, y
#:     **no lo usaba nadie**: las funciones de su propio modulo importan el del
#:     modelo. Era el unico sitio donde `in_approval` existia.
#:
#: Tres consumidores importaban el del modelo y escribian
#: `ChangeStatus.in_approval`. Medido:
#:
#:   1. **`POST /sd/changes/batch-score`**: la referencia era incondicional, asi
#:      que el endpoint respondia **500 siempre** —`AttributeError: type object
#:      'ChangeStatus' has no attribute 'in_approval'`— y **nunca puntuo un solo
#:      cambio**. La escritura cruzada entre clientes que tenia dentro nunca fue
#:      alcanzable: reventaba antes de llegar a la consulta.
#:   2. **`GET /sd/changes/cab-dashboard`**: el valor por defecto del parametro
#:      era `"submitted,in_approval"`, y `in_approval` se caia del filtro por no
#:      estar en el enum. El panel del CAB listaba **solo `submitted`** y no
#:      mostraba **ninguno** de los cambios que estan de verdad en revision del
#:      CAB, que es `cab_review`. Y si el cliente mandaba un estado inexistente
#:      se llegaba a la rama de respaldo y respondia 500.
#:   3. **La tarea de Celery `change_impact_batch_score`**, cada 10 minutos:
#:      mismo `AttributeError`, atrapado por su `except` exterior, que dejaba una
#:      linea de log y devolvia. **La pasada programada de scoring llevaba
#:      fallando en cada tic**, asi que `auto_risk_score` solo se rellenaba en la
#:      transicion a `submitted` (`change_service.py`) y la auto-aprobacion de
#:      cambios estandar de bajo riesgo no se ejecutaba nunca.
#:
#: Ahora la constante sale del enum, asi que un renombrado revienta aqui y no
#: en un `AttributeError` a mitad de una peticion.
ESTADOS_PENDIENTES_DE_CAB = [
    _ChangeStatus.submitted.value,
    _ChangeStatus.cab_review.value,
]

#: Cuantos cambios puntua como maximo una pasada de `/batch-score`.
#:
#: Auditoria 2026-08 (hallazgo 22). El endpoint cargaba **todos** los cambios
#: pendientes sin puntuar, sin tope, y por cada uno hacia un `score_and_persist`
#: —que consulta elementos de configuracion, sus dependencias, los tickets
#: abiertos sobre ellos y el historial de incidencias— **y un `commit`**. Sin
#: tope, una cola acumulada convierte una peticion HTTP en un trabajo de lote de
#: duracion desconocida.
TOPE_DE_CAMBIOS_POR_PASADA = int(
    _os.getenv("CHANGE_BATCH_SCORE_MAX", "100"))


def _cambios_de_la_organizacion(db: Session, current_user):
    """La consulta base de cambios, acotada de forma EXPLICITA.

    Un superadmin no filtra. Un sujeto sin organizacion ve los cambios sin
    organizacion, no los de todos: el filtro no es condicional.
    """
    from app.models.service_desk import ITSMChangeRequest

    q = db.query(ITSMChangeRequest)
    if getattr(current_user, "is_superadmin", False):
        return q
    return q.filter(
        ITSMChangeRequest.organization_id
        == getattr(current_user, "organization_id", None))


def panel_del_cab(
    db: Session,
    current_user,
    *,
    estados: list[str],
    min_risk_score: int,
    page: int,
    page_size: int,
) -> dict:
    """Los cambios pendientes de decision, ordenados por riesgo."""
    from app.models.service_desk import ITSMChangeRequest
    from app.services.service_desk.change_service import serialize_change

    q = _cambios_de_la_organizacion(db, current_user).filter(
        ITSMChangeRequest.status.in_(estados))
    if min_risk_score > 0:
        q = q.filter(
            (ITSMChangeRequest.auto_risk_score >= min_risk_score)
            | ITSMChangeRequest.auto_risk_score.is_(None)
        )

    total = q.count()
    cambios = (
        q.order_by(ITSMChangeRequest.auto_risk_score.desc().nullslast())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "unscored": sum(1 for c in cambios if c.auto_risk_score is None),
        "items": [serialize_change(c) for c in cambios],
    }


def puntuar_cambios_pendientes(db: Session, current_user) -> dict:
    """Puntua los cambios pendientes sin score y auto-aprueba los de bajo riesgo.

    Auditoria 2026-08 (hallazgo 22). Aqui habia dos cosas, y la segunda es
    grave:

    1. **Sin tope.** Ver el comentario de `TOPE_DE_CAMBIOS_POR_PASADA`.
    2. **Sin filtro de organizacion, y esto ESCRIBE.** Un administrador de un
       cliente que llamara a `/batch-score` puntuaba y **auto-aprobaba las
       solicitudes de cambio de todos los demas**. No es una lectura de mas: es
       aprobar un cambio en la infraestructura de otro cliente, y queda firmado
       con el id de quien lanzo la pasada. En produccion el filtro implicito de
       `TenantSession` lo evitaba, pero era la unica capa y esto es una
       escritura, no una lectura.

    El `except Exception` que cuenta errores viene del original y se conserva
    —una pasada no debe abortar por un cambio que falla—, pero ahora el fallo
    se registra con el id del cambio en vez de perderse.
    """
    from app.models.service_desk import ITSMChangeRequest
    from app.services.service_desk.change_service import _maybe_auto_approve

    consulta = _cambios_de_la_organizacion(db, current_user).filter(
        ITSMChangeRequest.status.in_(ESTADOS_PENDIENTES_DE_CAB),
        ITSMChangeRequest.auto_risk_score.is_(None),
    )
    total_pendientes = consulta.count()
    pendientes = consulta.limit(TOPE_DE_CAMBIOS_POR_PASADA).all()

    puntuados = auto_aprobados = errores = 0
    for cambio in pendientes:
        try:
            score_and_persist(db, cambio.id)
            if _maybe_auto_approve(
                    db, cambio, system_user_id=str(current_user.id)):
                auto_aprobados += 1
            db.commit()
            puntuados += 1
        except Exception:
            db.rollback()
            errores += 1
            logger.warning(
                "batch-score: fallo al puntuar el cambio %s", cambio.id,
                exc_info=True)

    return {
        "ok": True,
        # Se conserva el nombre y el significado: cuantos habia pendientes.
        "total_pending": total_pendientes,
        "scored": puntuados,
        "auto_approved": auto_aprobados,
        "errors": errores,
        "truncated": total_pendientes > len(pendientes),
    }


def score_and_persist(db: Session, change_id: str) -> dict:
    """Compute risk score + impact report and write back to the Change Request.

    Writes:
      - change.auto_risk_score      (int)
      - change.impact_analysis_json (JSON string)
      - change.suggested_window_json (JSON string)

    Only writes to columns that exist on the model (defensive).
    Does NOT commit — caller must commit.
    """
    change = db.query(ITSMChangeRequest).filter(ITSMChangeRequest.id == change_id).first()
    if not change:
        return {"error": f"Change {change_id} not found"}

    report = generate_impact_report(db, change_id)
    risk_data = score_change_risk(db, change)
    window = suggest_maintenance_window(db, change, risk_data["ci_ids_expanded"])

    if hasattr(change, "auto_risk_score"):
        change.auto_risk_score = risk_data["score"]
    if hasattr(change, "impact_analysis_json"):
        change.impact_analysis_json = json.dumps(report)
    if hasattr(change, "suggested_window_json"):
        change.suggested_window_json = json.dumps(window)

    # Also upgrade the risk field if auto score is higher than current
    risk_labels = {
        ChangeRisk.low: 1,
        ChangeRisk.medium: 2,
        ChangeRisk.high: 3,
        ChangeRisk.critical: 4,
    }
    auto_label_map = {"low": ChangeRisk.low, "medium": ChangeRisk.medium,
                      "high": ChangeRisk.high, "critical": ChangeRisk.critical}
    auto_risk_enum = auto_label_map.get(risk_data["risk_label"], ChangeRisk.medium)

    current_rank = risk_labels.get(change.risk, 2)
    auto_rank = risk_labels.get(auto_risk_enum, 2)
    if auto_rank > current_rank:
        change.risk = auto_risk_enum

    db.flush()

    logger.info(
        "Change %s risk scored: %d/100 (%s)",
        change.number,
        risk_data["score"],
        risk_data["risk_label"],
    )

    return report


# ══════════════════════════════════════════════════════════════════════════════
# v23.10.44 — Automated Change Impact Analysis + Rollback Plan (new)
# ══════════════════════════════════════════════════════════════════════════════

import math


def _get_json_setting(db: Session, key: str) -> dict:
    from app.models.settings import AppSetting
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if not row or not row.value:
        return {}
    try:
        return json.loads(row.value)
    except (json.JSONDecodeError, TypeError):
        return {}


def _set_json_setting(db: Session, key: str, data: dict) -> None:
    from app.models.settings import AppSetting
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    serialized = json.dumps(data, ensure_ascii=False)
    if row:
        row.value = serialized
    else:
        row = AppSetting(key=key, value=serialized, description=f"Change impact: {key}")
        db.add(row)
    db.flush()


_CRITICALITY_RISK_SCORE = {"critical": 4, "high": 3, "medium": 2, "low": 1}
_RISK_LEVEL_THRESHOLDS = {"critical": 12, "high": 8, "medium": 4}


def _risk_level_label(score: float) -> str:
    if score >= _RISK_LEVEL_THRESHOLDS["critical"]:
        return "critical"
    if score >= _RISK_LEVEL_THRESHOLDS["high"]:
        return "high"
    if score >= _RISK_LEVEL_THRESHOLDS["medium"]:
        return "medium"
    return "low"


def get_risk_matrix_for_change(db: Session, change_id: str) -> list[dict]:
    """Calculate per-CI risk matrix for all CIs affected by the change."""
    change = db.query(ITSMChangeRequest).filter(ITSMChangeRequest.id == change_id).first()
    if not change:
        raise ValueError(f"Change {change_id} not found")

    risk_data = score_change_risk(db, change)
    ci_ids = risk_data.get("ci_ids_expanded", [])

    matrix: list[dict] = []
    for ci_id in ci_ids:
        ci = db.query(ConfigurationItem).filter(ConfigurationItem.id == ci_id).first()
        if not ci:
            continue
        criticality = (getattr(ci, "criticality", None) or "medium").lower()
        crit_score = _CRITICALITY_RISK_SCORE.get(criticality, 2)

        dep_count = (
            db.query(CIRelation)
            .filter(CIRelation.target_ci_id == ci_id)
            .count()
        )
        recent_incidents = _incident_count_last_days(db, [ci_id], days=30)
        dep_factor = math.sqrt(dep_count + 1)
        incident_factor = min(recent_incidents * 0.5, 2.0)
        risk_score = round(crit_score * dep_factor * (1 + incident_factor), 2)

        matrix.append({
            "ci_id": ci_id,
            "ci_name": ci.name,
            "ci_type": ci.ci_type.value,
            "criticality": criticality,
            "dependency_count": dep_count,
            "recent_incidents": recent_incidents,
            "risk_score": risk_score,
            "impact_level": _risk_level_label(risk_score),
        })

    matrix.sort(key=lambda x: x["risk_score"], reverse=True)
    return matrix


def analyze_change_impact_full(
    db: Session,
    change_id: str,
    current_user_id: Optional[str] = None,
) -> dict:
    """Full automated impact analysis: score + risk matrix + narrative + cache."""
    report = generate_impact_report(db, change_id)
    matrix = get_risk_matrix_for_change(db, change_id)
    report["detailed_risk_matrix"] = matrix[:20]
    report["analyzed_by"] = current_user_id

    # Persist
    _set_json_setting(db, f"sd.change.impact.{change_id}", report)
    db.commit()
    return report


def get_cached_impact_analysis(db: Session, change_id: str) -> dict:
    """Return cached impact analysis or 404."""
    from fastapi import HTTPException
    result = _get_json_setting(db, f"sd.change.impact.{change_id}")
    if not result:
        raise HTTPException(404, "Análisis de impacto no encontrado. Ejecuta POST /impact-analysis primero.")
    return result


def generate_rollback_plan(
    db: Session,
    change_id: str,
    current_user_id: Optional[str] = None,
) -> dict:
    """Generate a structured rollback plan for the change."""
    change = db.query(ITSMChangeRequest).filter(ITSMChangeRequest.id == change_id).first()
    if not change:
        from fastapi import HTTPException
        raise HTTPException(404, f"Change {change_id} not found")

    cached = _get_json_setting(db, f"sd.change.impact.{change_id}")
    overall_risk = cached.get("risk_label", "medium") if cached else "medium"
    affected_count = cached.get("affected_cis", {}).get("expanded_count", 0) if cached else 0

    steps = [
        {"step": 1, "action": "Detener el despliegue si está en progreso", "responsible": "Ingeniero de operaciones", "estimated_minutes": 5},
        {"step": 2, "action": "Verificar estado de todos los CIs afectados en el CMDB", "responsible": "CMDB Admin", "estimated_minutes": 10},
        {"step": 3, "action": f"Restaurar versión anterior de los componentes de '{change.title}'", "responsible": "Equipo técnico", "estimated_minutes": 30 if overall_risk in ("high", "critical") else 15},
        {"step": 4, "action": "Ejecutar smoke tests en sistemas restaurados", "responsible": "QA / Dev", "estimated_minutes": 20},
        {"step": 5, "action": "Confirmar estado operacional de los CIs afectados", "responsible": "NOC / Operaciones", "estimated_minutes": 10},
        {"step": 6, "action": "Notificar a stakeholders sobre el rollback y estado", "responsible": "Change Manager", "estimated_minutes": 5},
        {"step": 7, "action": "Registrar ticket post-incident y programar PIR", "responsible": "Change Manager", "estimated_minutes": 15},
    ]

    plan = {
        "change_id": change_id,
        "change_number": change.number,
        "change_title": change.title,
        "overall_risk": overall_risk,
        "affected_ci_count": affected_count,
        "rollback_steps": steps,
        "total_estimated_minutes": sum(s["estimated_minutes"] for s in steps),
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "generated_by": current_user_id,
    }

    _set_json_setting(db, f"sd.change.rollback.{change_id}", plan)
    db.commit()
    return plan


# ══════════════════════════════════════════════════════════════════════════════
# Testing Plan — structured, executable test steps by phase
# ══════════════════════════════════════════════════════════════════════════════

#: El plan de pruebas, declarado. Cada fila es un paso:
#:
#:    (fase, tipo, descripción, resultado esperado, minutos, responsable,
#:     automatizado, comando, condición)
#:
#: `condición` recibe el contexto del cambio y decide si el paso aplica;
#: `None` significa «siempre». Descripción, resultado y minutos se formatean o
#: calculan con ese mismo contexto.
#:
#: Auditoría 2026-09 (hallazgo 18): esto eran 197 líneas de llamadas a un
#: ayudante anidado, con las condiciones repartidas entre ellas — complejidad
#: 14. Un plan de pruebas **es** una tabla: verlo entero es lo que hace falta
#: para revisarlo con quien lo va a ejecutar, y añadir un paso es añadir una
#: fila en el sitio que le toca, no una rama en medio de un bloque.
_PASOS_DEL_PLAN: tuple[tuple, ...] = (
    # ── Antes del cambio ─────────────────────────────────────────────────────
    ("pre_change", "sanity",
     "Verificar estado actual de los CIs en CMDB: {cis}",
     "Todos los CIs en estado 'active' con configuración baseline registrada",
     10, "CMDB Admin", False, "", None),
    ("pre_change", "backup",
     "Confirmar snapshots/backups de configuración de CIs críticos",
     "Backups completados y verificados (restore point disponible)",
     15, "Equipo técnico", False, "", None),
    ("pre_change", "readiness",
     "Confirmar disponibilidad del plan de rollback y equipo de soporte",
     "Equipo de rollback en standby, procedimiento revisado y firmado",
     10, "Change Manager", False, "", "riesgo_medio"),
    ("pre_change", "noc_alert",
     "Notificar a NOC y colocar CIs en modo observación anticipada",
     "NOC confirma monitorización activa de alertas sobre CIs afectados",
     5, "NOC / Operaciones", False, "", "riesgo_alto"),
    ("pre_change", "maintenance_mode",
     "Activar modo mantenimiento en sistemas afectados ({cis})",
     "Sistemas en estado maintenance, sin tickets de incidente generados automáticamente",
     10, "Ingeniero de operaciones", True,
     "cmdb update-status --ci-ids <affected_ids> --status maintenance", "hay_parada"),

    # ── Durante el cambio ────────────────────────────────────────────────────
    ("execution", "milestone",
     "Confirmar inicio del cambio y registrar hora real de arranque",
     "Hora de inicio registrada en el Change Request (actual_start actualizado)",
     5, "Change Manager", False, "", None),
    ("execution", "monitoring",
     "Monitorizar métricas de salud de CIs durante el cambio: {cis}",
     "CPU/memoria/latencia dentro de umbrales normales; sin alertas críticas",
     "minutos_de_monitorizacion", "NOC / Operaciones", True,
     "monitoring check --ci-ids <affected_ids> --interval 5m", None),
    ("execution", "checkpoint",
     "Verificar hito intermedio: primeros CIs afectados han completado el cambio",
     "Al menos {mitad_de_cis} CIs en estado post-change sin errores",
     10, "Equipo técnico", False, "", "muchos_cis"),
    ("execution", "go_nogo",
     "Go/No-Go decision point a mitad del cambio",
     "Equipo técnico confirma continuación; si hay anomalías iniciar rollback",
     10, "Change Manager", False, "", "riesgo_alto"),

    # ── Después del cambio ───────────────────────────────────────────────────
    ("post_change", "smoke",
     "Smoke tests de conectividad y disponibilidad de CIs: {cis}",
     "Todos los CIs responden; endpoints críticos retornan HTTP 200 / ping exitoso",
     15, "QA / DevOps", True,
     "smoke-test --suite post_change --ci-ids <affected_ids>", None),
    ("post_change", "functional",
     "Tests funcionales de los servicios afectados por el cambio",
     "Todos los casos de prueba funcionales pasan sin regresiones",
     20, "QA / Dev", True,
     "pytest tests/functional/ --marker change_validation -v", None),
    ("post_change", "performance",
     "Comparación de baseline de rendimiento (antes vs después)",
     "Métricas de rendimiento dentro del ±10% respecto al baseline pre-cambio",
     15, "QA / DevOps", True,
     "perf-test --baseline pre_change --ci-ids <affected_ids>", "riesgo_alto"),
    ("post_change", "cmdb_update",
     "Verificar y actualizar CMDB con el nuevo estado de configuración",
     "CIs actualizados en CMDB; relaciones y atributos reflejan la nueva configuración",
     10, "CMDB Admin", False, "", None),
    ("post_change", "monitoring_30min",
     "Observar métricas de producción durante 30 minutos post-cambio",
     "Sin alertas inesperadas; incidentalidad normal para la ventana horaria",
     30, "NOC / Operaciones", True,
     "monitoring watch --duration 30m --alert-on-anomaly --ci-ids <affected_ids>", None),
    ("post_change", "maintenance_off",
     "Desactivar modo mantenimiento en todos los CIs afectados",
     "CIs vuelven a estado 'active'; monitorización de alertas reactiva",
     5, "Ingeniero de operaciones", True,
     "cmdb update-status --ci-ids <affected_ids> --status active", "hay_parada"),

    # ── Si hay que volver atrás ──────────────────────────────────────────────
    ("rollback_validation", "config_restore",
     "Verificar que la configuración anterior ha sido restaurada correctamente",
     "CIs con versión de configuración idéntica a la del snapshot pre-cambio",
     15, "Equipo técnico", False, "", None),
    ("rollback_validation", "smoke",
     "Smoke tests post-rollback sobre CIs afectados",
     "Todos los CIs responden y funcionan igual que antes del cambio",
     15, "QA / DevOps", True,
     "smoke-test --suite post_rollback --ci-ids <affected_ids>", None),
    ("rollback_validation", "cmdb_revert",
     "Confirmar que el CMDB refleja el estado pre-cambio",
     "Registro de CMDB coincide con el baseline capturado en pre_change",
     10, "CMDB Admin", False, "", None),
    ("rollback_validation", "incident_check",
     "Verificar ausencia de incidentes activos generados por el rollback",
     "Sin tickets de incidente abiertos atribuibles al cambio o su rollback",
     10, "NOC / Operaciones", True,
     "monitoring check --duration 15m --ci-ids <affected_ids>", None),
)

#: Las cuatro fases, en el orden en que se ejecutan. La tabla ya va ordenada,
#: pero el informe agrupa por fase y ese orden tiene que estar declarado.
_FASES_DEL_PLAN = ("pre_change", "execution", "post_change", "rollback_validation")


def _contexto_del_plan(change, riesgo: str, ci_details: list[dict]) -> dict:
    """Los datos con los que se deciden y se rellenan los pasos."""
    parada = change.downtime_minutes or 0
    n_cis = len(ci_details)
    return {
        "cis": ", ".join(c["name"] for c in ci_details[:3]) or "N/A",
        "mitad_de_cis": min(n_cis // 2, 5),
        # La monitorización dura lo que dure la parada, con un tope: sin parada
        # declarada, o con una muy larga, media hora es lo razonable.
        "minutos_de_monitorizacion": parada if 0 < parada <= 60 else 30,
        "riesgo_alto": riesgo in ("high", "critical"),
        "riesgo_medio": riesgo in ("medium", "high", "critical"),
        "hay_parada": parada > 0,
        "muchos_cis": n_cis > 3,
    }


def _pasos_aplicables(ctx: dict) -> list[dict]:
    """Los pasos de la tabla que aplican a este cambio, ya numerados."""
    pasos: list[dict] = []
    for fase, tipo, desc, esperado, minutos, responsable, automatico, comando, condicion in _PASOS_DEL_PLAN:
        if condicion and not ctx[condicion]:
            continue
        entrada = {
            "step": len(pasos) + 1,
            "phase": fase,
            "test_type": tipo,
            "description": desc.format(**ctx),
            "expected_result": esperado.format(**ctx),
            "estimated_minutes": ctx[minutos] if isinstance(minutos, str) else minutos,
            "responsible": responsable,
            "automated": automatico,
        }
        if comando:
            entrada["command"] = comando
        pasos.append(entrada)
    return pasos


def generate_testing_plan(
    db: Session,
    change_id: str,
    current_user_id: Optional[str] = None,
) -> dict:
    """Plan de pruebas con pasos ejecutables, adaptado al riesgo y al nº de CIs.

    Cuatro fases: validación previa, hitos durante la ventana, pruebas de humo
    y funcionales al terminar, y confirmación si hay que volver atrás.

    Se guarda en `AppSetting` para poder consultarlo después.
    """
    change = db.query(ITSMChangeRequest).filter(ITSMChangeRequest.id == change_id).first()
    if not change:
        from fastapi import HTTPException
        raise HTTPException(404, f"Change {change_id} not found")

    riesgo = score_change_risk(db, change)
    etiqueta = riesgo["risk_label"]
    ci_details = _get_ci_details(db, riesgo["ci_ids_expanded"])

    pasos = _pasos_aplicables(_contexto_del_plan(change, etiqueta, ci_details))

    plan = {
        "change_id": change_id,
        "change_number": change.number,
        "change_title": change.title,
        "risk_label": etiqueta,
        "total_steps": len(pasos),
        "estimated_total_minutes": sum(p["estimated_minutes"] for p in pasos),
        "phases": {
            fase: [p for p in pasos if p["phase"] == fase] for fase in _FASES_DEL_PLAN
        },
        "steps": pasos,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "generated_by": current_user_id,
    }

    _set_json_setting(db, f"sd.change.testing.{change_id}", plan)
    # El resumen en texto sólo se escribe si el campo está vacío: si alguien
    # redactó un plan a mano, generar otro no lo borra.
    if hasattr(change, "test_plan") and not change.test_plan:
        lineas = [f"[Auto-generated — {etiqueta.upper()} risk — {len(pasos)} steps]"]
        lineas += [f"{p['step']}. [{p['phase']}] {p['description']}" for p in pasos]
        change.test_plan = "\n".join(lineas)
    db.commit()
    return plan


# ══════════════════════════════════════════════════════════════════════════════
# Communications Plan — audiences, channels, timing
# ══════════════════════════════════════════════════════════════════════════════

_COMMS_AUDIENCES: dict[str, dict[str, list[str]]] = {
    # risk_label → {timing_bucket → [audience_dicts]}
    "low": {
        "pre_change": ["IT Operations Team"],
        "post_change": ["IT Operations Team"],
    },
    "medium": {
        "pre_change": ["IT Operations Team", "Service Desk", "Line Manager"],
        "post_change": ["IT Operations Team", "Service Desk"],
    },
    "high": {
        "pre_change": ["IT Operations Team", "Service Desk", "Line Manager", "End Users (affected services)"],
        "during_change": ["IT Operations Team", "Service Desk"],
        "post_change": ["IT Operations Team", "Service Desk", "Line Manager", "End Users (affected services)"],
    },
    "critical": {
        "pre_change": ["IT Operations Team", "Service Desk", "Line Manager", "End Users (affected services)", "Executive Team"],
        "during_change": ["IT Operations Team", "Service Desk", "Executive Team"],
        "post_change": ["IT Operations Team", "Service Desk", "Line Manager", "End Users (affected services)", "Executive Team"],
        "post_incident": ["Executive Team", "Key Stakeholders"],
    },
}

_CHANNEL_MAP: dict[str, str] = {
    "IT Operations Team": "email + IM (Slack/Teams)",
    "Service Desk": "email + ticketing system notification",
    "Line Manager": "email",
    "End Users (affected services)": "email + service portal banner",
    "Executive Team": "email + phone / executive summary",
    "Key Stakeholders": "email",
    "NOC": "IM (Slack/Teams) + monitoring alert",
}


#: El plan de comunicación, declarado. Cada fila es un aviso:
#:
#:    (cuándo, horas antes, público, canal, asunto, mensaje, responsable,
#:     condición)
#:
#: `condición` es `None` —siempre—, `"alto"` —riesgo alto o crítico— o
#: `"critico"`. `canal` a `None` significa «el canal por defecto de ese
#: público», que vive en `_CHANNEL_MAP`.
#:
#: Auditoría 2026-09 (hallazgo 18): eran 260 líneas de llamadas a un ayudante
#: anidado con las condiciones repartidas entre ellas. Un plan de comunicación
#: **es** una tabla, y verla entera es lo que hace falta para revisarla con
#: quien la va a enviar: quién recibe qué, cuándo, y por qué canal.
#:
#: Las llaves dobles `{{...}}` son huecos que rellena quien envía el aviso en
#: el momento; las simples se sustituyen aquí.
_AVISOS_DEL_PLAN: tuple[tuple, ...] = (
    # ── Antes del cambio ─────────────────────────────────────────────────────
    ("T-7d", 168, "Executive Team", None,
     "[CRITICAL CHANGE] {number} — {title}",
     "Se planifica un cambio crítico ({number}): «{title}».\n"
     "Ventana propuesta: {ventana}. Tiempo de inactividad estimado: {parada} min.\n"
     "Se requiere confirmación de disponibilidad y aprobación ejecutiva.",
     "Change Manager", "critico"),

    ("T-72h", 72, "End Users (affected services)", None,
     "[Aviso de mantenimiento] {number} — {title}",
     "Estimado usuario,\nSe realizará un mantenimiento programado ({number}) el {ventana}.\n"
     "Interrupción estimada: {parada} minutos. Disculpe las molestias.",
     "Service Desk / Comms Team", "critico"),

    ("T-48h", 48, "Service Desk", None,
     "[Aviso previo] Cambio {number} — {title}",
     "Notificación de cambio programado ({number}): «{title}».\n"
     "Ventana: {ventana}. Impacto: riesgo {RIESGO}.\n"
     "Prepara guiones de respuesta para consultas de usuarios durante la ventana.",
     "Change Manager", "alto"),

    ("T-48h", 48, "Line Manager", None,
     "[Cambio programado] {number} — {title}",
     "Cambio programado ({number}): «{title}».\n"
     "Ventana: {ventana}. Riesgo: {RIESGO}.\n"
     "Asegúrese de que el equipo técnico esté disponible durante la ventana.",
     "Change Manager", "alto"),

    ("T-24h", 24, "IT Operations Team", None,
     "[Recordatorio] Cambio mañana: {number} — {title}",
     "Recordatorio: mañana se ejecuta el cambio {number}: «{title}».\n"
     "Ventana: {ventana}. Plan de pruebas y rollback deben estar listos.\n"
     "Confirma disponibilidad respondiendo este mensaje.",
     "Change Manager", None),

    ("T-24h", 24, "End Users (affected services)", None,
     "[Recordatorio mantenimiento mañana] {number}",
     "Recordatorio: mañana {ventana} se realizará el mantenimiento {number}.\n"
     "Inactividad estimada: {parada} min. Guarda tu trabajo antes de la ventana.",
     "Service Desk / Comms Team", "alto"),

    ("T-1h", 1, "IT Operations Team", "IM (Slack/Teams) — canal #operations",
     "🔧 1 hora para inicio: {number}",
     "En 1 hora inicia el cambio {number}: «{title}».\n"
     "Confirma presencia en el canal de guardia. Plan de rollback accesible.",
     "Change Manager", None),

    ("T-1h", 1, "Service Desk", "IM (Slack/Teams) — canal #service-desk",
     "⚠️ Cambio iniciará en 1h: {number}",
     "En 1 hora inicia {number}. Activar modo guardia.\n"
     "Cualquier incidente relacionado durante la ventana: escalar a Change Manager.",
     "Change Manager", "alto"),

    # ── Durante el cambio ────────────────────────────────────────────────────
    ("change_start", 0, "IT Operations Team", "IM (Slack/Teams) — canal #operations",
     "▶️ Cambio iniciado: {number}",
     "El cambio {number} ha iniciado a las {{hora_inicio_utc}} UTC.\n"
     "Monitorización activa. Reportar anomalías inmediatamente.",
     "Change Manager", "alto"),

    ("change_midpoint", None, "Executive Team", None,
     "[Status update] Cambio {number} en progreso",
     "El cambio crítico {number} está en progreso.\n"
     "Estado: {{estado_actual}}. Sin anomalías mayores detectadas hasta el momento.",
     "Change Manager", "critico"),

    # ── Después del cambio ───────────────────────────────────────────────────
    ("post_change_success", None, "IT Operations Team", None,
     "✅ Cambio completado: {number}",
     "El cambio {number}: «{title}» se ha completado exitosamente.\n"
     "Todos los tests post-cambio pasaron. Sistemas en estado operacional normal.",
     "Change Manager", None),

    ("post_change_success", None, "End Users (affected services)", None,
     "✅ Mantenimiento finalizado: {number}",
     "El mantenimiento programado {number} ha concluido.\n"
     "Todos los servicios están disponibles con normalidad. Gracias por su paciencia.",
     "Service Desk / Comms Team", "alto"),

    ("post_change_failure_rollback", None, "IT Operations Team",
     "IM (Slack/Teams) — canal #operations (URGENTE)",
     "❌ ROLLBACK iniciado: {number}",
     "El cambio {number} ha activado el plan de rollback.\n"
     "Motivo: {{motivo_rollback}}. Equipo de rollback en acción. ETA: {{eta_minutos}} min.",
     "Change Manager", None),

    ("post_change_failure_rollback", None, "End Users (affected services)", None,
     "[Mantenimiento extendido] {number}",
     "El mantenimiento {number} ha encontrado un inconveniente y se está resolviendo.\n"
     "ETA de restauración: {{eta_restauracion}}. Pedimos disculpas por el tiempo adicional.",
     "Service Desk / Comms Team", "alto"),

    ("post_pir", None, "Executive Team", None,
     "[PIR] Cambio {number} — Informe post-implementación",
     "Se ha completado la Revisión Post-Implementación del cambio {number}.\n"
     "Resultado: {{resultado_pir}}. Informe completo adjunto.",
     "Change Manager", "critico"),
)


def _avisos_aplicables(ctx: dict) -> list[dict]:
    """Los avisos de la tabla que aplican a este cambio, ya numerados."""
    avisos: list[dict] = []
    for cuando, horas, publico, canal, asunto, mensaje, responsable, condicion in _AVISOS_DEL_PLAN:
        if condicion and not ctx[condicion]:
            continue
        avisos.append({
            "id": len(avisos) + 1,
            "timing": cuando,
            "hours_before_change": horas,
            "audience": publico,
            "channel": canal or _CHANNEL_MAP[publico],
            "subject": asunto.format(**ctx),
            "message_template": mensaje.format(**ctx),
            "responsible": responsable,
        })
    return avisos


def generate_comms_plan(
    db: Session,
    change_id: str,
    current_user_id: Optional[str] = None,
) -> dict:
    """Plan de comunicación con públicos, canales y momentos.

    Cubre el antes, el durante —sólo en riesgo alto o crítico— y el después.
    Las plantillas de mensaje se adaptan al nivel de riesgo. Se guarda en
    `AppSetting` para poder consultarlo luego.
    """
    change = db.query(ITSMChangeRequest).filter(ITSMChangeRequest.id == change_id).first()
    if not change:
        from fastapi import HTTPException
        raise HTTPException(404, f"Change {change_id} not found")

    riesgo = score_change_risk(db, change)
    etiqueta = riesgo["risk_label"]
    ventana = suggest_maintenance_window(db, change, riesgo["ci_ids_expanded"])
    ventana_texto = ventana.get("window_label", "pendiente de confirmar")

    ctx = {
        "number": change.number,
        "title": change.title,
        "ventana": ventana_texto,
        "parada": change.downtime_minutes or 0,
        "RIESGO": etiqueta.upper(),
        "alto": etiqueta in ("high", "critical"),
        "critico": etiqueta == "critical",
    }
    avisos = _avisos_aplicables(ctx)

    comms_plan = {
        "change_id": change_id,
        "change_number": change.number,
        "change_title": change.title,
        "risk_label": etiqueta,
        "suggested_window": ventana_texto,
        "total_notifications": len(avisos),
        "timeline_buckets": {
            "pre_change": [
                a for a in avisos
                if a["timing"].startswith("T-") or a["timing"] == "change_start"
            ],
            "during_change": [
                a for a in avisos if a["timing"] in ("change_start", "change_midpoint")
            ],
            "post_change": [a for a in avisos if a["timing"].startswith("post_")],
        },
        "notifications": avisos,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "generated_by": current_user_id,
    }

    _set_json_setting(db, f"sd.change.comms.{change_id}", comms_plan)
    db.commit()
    return comms_plan


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
        from fastapi import HTTPException
        raise HTTPException(404, f"Change {change_id} not found")

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
