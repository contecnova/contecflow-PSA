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
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.service_desk import (
    CIRelation,
    ConfigurationItem,
    ITSMChangeRequest,
    ChangeRisk,
    ChangeType,
    Ticket,
    TicketStatus,
    TicketPriority,
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

import math  # noqa: E402


def _get_json_setting(db: Session, key: str) -> dict:
    from app.models.settings import AppSetting  # noqa: PLC0415
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if not row or not row.value:
        return {}
    try:
        return json.loads(row.value)
    except (json.JSONDecodeError, TypeError):
        return {}


def _set_json_setting(db: Session, key: str, data: dict) -> None:
    from app.models.settings import AppSetting  # noqa: PLC0415
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
    from fastapi import HTTPException  # noqa: PLC0415
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
        from fastapi import HTTPException  # noqa: PLC0415
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

def generate_testing_plan(
    db: Session,
    change_id: str,
    current_user_id: Optional[str] = None,
) -> dict:
    """Generate a structured testing plan with executable steps for each phase.

    Steps are organised into four phases:
      - pre_change        : validation before starting the change
      - execution         : checkpoints during the change window
      - post_change       : smoke / functional / performance tests after
      - rollback_validation: confirmation tests if rollback is triggered

    Adapted to risk level and CI count. Cached in AppSetting for later retrieval.
    """
    change = db.query(ITSMChangeRequest).filter(ITSMChangeRequest.id == change_id).first()
    if not change:
        from fastapi import HTTPException  # noqa: PLC0415
        raise HTTPException(404, f"Change {change_id} not found")

    risk_data = score_change_risk(db, change)
    risk_label = risk_data["risk_label"]
    ci_details = _get_ci_details(db, risk_data["ci_ids_expanded"])
    ci_count = len(ci_details)
    top_ci_names = ", ".join(c["name"] for c in ci_details[:3]) or "N/A"
    downtime = change.downtime_minutes or 0

    HIGH_RISK = risk_label in ("high", "critical")
    MED_RISK = risk_label in ("medium", "high", "critical")

    steps: list[dict] = []
    step = 1

    # ── PRE-CHANGE ────────────────────────────────────────────────────────────
    def _add(phase: str, test_type: str, description: str, expected_result: str,
             minutes: int, responsible: str, automated: bool = False, command: str = "") -> None:
        nonlocal step
        entry: dict = {
            "step": step,
            "phase": phase,
            "test_type": test_type,
            "description": description,
            "expected_result": expected_result,
            "estimated_minutes": minutes,
            "responsible": responsible,
            "automated": automated,
        }
        if command:
            entry["command"] = command
        steps.append(entry)
        step += 1

    _add("pre_change", "sanity",
         f"Verificar estado actual de los CIs en CMDB: {top_ci_names}",
         "Todos los CIs en estado 'active' con configuración baseline registrada",
         10, "CMDB Admin", automated=False)

    _add("pre_change", "backup",
         "Confirmar snapshots/backups de configuración de CIs críticos",
         "Backups completados y verificados (restore point disponible)",
         15, "Equipo técnico", automated=False)

    if MED_RISK:
        _add("pre_change", "readiness",
             "Confirmar disponibilidad del plan de rollback y equipo de soporte",
             "Equipo de rollback en standby, procedimiento revisado y firmado",
             10, "Change Manager", automated=False)

    if HIGH_RISK:
        _add("pre_change", "noc_alert",
             "Notificar a NOC y colocar CIs en modo observación anticipada",
             "NOC confirma monitorización activa de alertas sobre CIs afectados",
             5, "NOC / Operaciones", automated=False)

    if downtime > 0:
        _add("pre_change", "maintenance_mode",
             f"Activar modo mantenimiento en sistemas afectados ({top_ci_names})",
             "Sistemas en estado maintenance, sin tickets de incidente generados automáticamente",
             10, "Ingeniero de operaciones", automated=True,
             command="cmdb update-status --ci-ids <affected_ids> --status maintenance")

    # ── EXECUTION ─────────────────────────────────────────────────────────────
    _add("execution", "milestone",
         "Confirmar inicio del cambio y registrar hora real de arranque",
         "Hora de inicio registrada en el Change Request (actual_start actualizado)",
         5, "Change Manager", automated=False)

    _add("execution", "monitoring",
         f"Monitorizar métricas de salud de CIs durante el cambio: {top_ci_names}",
         "CPU/memoria/latencia dentro de umbrales normales; sin alertas críticas",
         downtime if 0 < downtime <= 60 else 30, "NOC / Operaciones", automated=True,
         command="monitoring check --ci-ids <affected_ids> --interval 5m")

    if ci_count > 3:
        _add("execution", "checkpoint",
             "Verificar hito intermedio: primeros CIs afectados han completado el cambio",
             f"Al menos {min(ci_count // 2, 5)} CIs en estado post-change sin errores",
             10, "Equipo técnico", automated=False)

    if HIGH_RISK:
        _add("execution", "go_nogo",
             "Go/No-Go decision point a mitad del cambio",
             "Equipo técnico confirma continuación; si hay anomalías iniciar rollback",
             10, "Change Manager", automated=False)

    # ── POST-CHANGE ───────────────────────────────────────────────────────────
    _add("post_change", "smoke",
         f"Smoke tests de conectividad y disponibilidad de CIs: {top_ci_names}",
         "Todos los CIs responden; endpoints críticos retornan HTTP 200 / ping exitoso",
         15, "QA / DevOps", automated=True,
         command="smoke-test --suite post_change --ci-ids <affected_ids>")

    _add("post_change", "functional",
         "Tests funcionales de los servicios afectados por el cambio",
         "Todos los casos de prueba funcionales pasan sin regresiones",
         20, "QA / Dev", automated=True,
         command="pytest tests/functional/ --marker change_validation -v")

    if HIGH_RISK:
        _add("post_change", "performance",
             "Comparación de baseline de rendimiento (antes vs después)",
             "Métricas de rendimiento dentro del ±10% respecto al baseline pre-cambio",
             15, "QA / DevOps", automated=True,
             command="perf-test --baseline pre_change --ci-ids <affected_ids>")

    _add("post_change", "cmdb_update",
         "Verificar y actualizar CMDB con el nuevo estado de configuración",
         "CIs actualizados en CMDB; relaciones y atributos reflejan la nueva configuración",
         10, "CMDB Admin", automated=False)

    _add("post_change", "monitoring_30min",
         "Observar métricas de producción durante 30 minutos post-cambio",
         "Sin alertas inesperadas; incidentalidad normal para la ventana horaria",
         30, "NOC / Operaciones", automated=True,
         command="monitoring watch --duration 30m --alert-on-anomaly --ci-ids <affected_ids>")

    if downtime > 0:
        _add("post_change", "maintenance_off",
             "Desactivar modo mantenimiento en todos los CIs afectados",
             "CIs vuelven a estado 'active'; monitorización de alertas reactiva",
             5, "Ingeniero de operaciones", automated=True,
             command="cmdb update-status --ci-ids <affected_ids> --status active")

    # ── ROLLBACK VALIDATION ───────────────────────────────────────────────────
    _add("rollback_validation", "config_restore",
         "Verificar que la configuración anterior ha sido restaurada correctamente",
         "CIs con versión de configuración idéntica a la del snapshot pre-cambio",
         15, "Equipo técnico", automated=False)

    _add("rollback_validation", "smoke",
         "Smoke tests post-rollback sobre CIs afectados",
         "Todos los CIs responden y funcionan igual que antes del cambio",
         15, "QA / DevOps", automated=True,
         command="smoke-test --suite post_rollback --ci-ids <affected_ids>")

    _add("rollback_validation", "cmdb_revert",
         "Confirmar que el CMDB refleja el estado pre-cambio",
         "Registro de CMDB coincide con el baseline capturado en pre_change",
         10, "CMDB Admin", automated=False)

    _add("rollback_validation", "incident_check",
         "Verificar ausencia de incidentes activos generados por el rollback",
         "Sin tickets de incidente abiertos atribuibles al cambio o su rollback",
         10, "NOC / Operaciones", automated=True,
         command="monitoring check --duration 15m --ci-ids <affected_ids>")

    # ── Assemble plan ─────────────────────────────────────────────────────────
    def _phase_steps(phase: str) -> list[dict]:
        return [s for s in steps if s["phase"] == phase]

    plan = {
        "change_id": change_id,
        "change_number": change.number,
        "change_title": change.title,
        "risk_label": risk_label,
        "total_steps": len(steps),
        "estimated_total_minutes": sum(s["estimated_minutes"] for s in steps),
        "phases": {
            "pre_change": _phase_steps("pre_change"),
            "execution": _phase_steps("execution"),
            "post_change": _phase_steps("post_change"),
            "rollback_validation": _phase_steps("rollback_validation"),
        },
        "steps": steps,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "generated_by": current_user_id,
    }

    # Persist in AppSetting cache and optionally update the test_plan text column
    _set_json_setting(db, f"sd.change.testing.{change_id}", plan)
    if hasattr(change, "test_plan") and not change.test_plan:
        summary_lines = [f"[Auto-generated — {risk_label.upper()} risk — {len(steps)} steps]"]
        for s in steps:
            summary_lines.append(f"{s['step']}. [{s['phase']}] {s['description']}")
        change.test_plan = "\n".join(summary_lines)
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


def generate_comms_plan(
    db: Session,
    change_id: str,
    current_user_id: Optional[str] = None,
) -> dict:
    """Generate a structured communications plan with audiences, channels, and timing.

    The plan covers pre-change, during-change (for high/critical), and post-change
    notifications. Message templates adapt to risk level. Cached in AppSetting.
    """
    change = db.query(ITSMChangeRequest).filter(ITSMChangeRequest.id == change_id).first()
    if not change:
        from fastapi import HTTPException  # noqa: PLC0415
        raise HTTPException(404, f"Change {change_id} not found")

    risk_data = score_change_risk(db, change)
    risk_label = risk_data["risk_label"]

    window = suggest_maintenance_window(db, change, risk_data["ci_ids_expanded"])
    window_label = window.get("window_label", "pendiente de confirmar")
    downtime = change.downtime_minutes or 0

    HIGH_RISK = risk_label in ("high", "critical")

    notifications: list[dict] = []
    n = 1

    def _notif(timing: str, hours_before: Optional[int], audience: str, channel: str,
               subject: str, message_template: str, responsible: str) -> None:
        nonlocal n
        notifications.append({
            "id": n,
            "timing": timing,
            "hours_before_change": hours_before,
            "audience": audience,
            "channel": channel,
            "subject": subject,
            "message_template": message_template,
            "responsible": responsible,
        })
        n += 1

    title = change.title
    number = change.number

    # ── PRE-CHANGE ────────────────────────────────────────────────────────────
    if risk_label == "critical":
        _notif(
            timing="T-7d", hours_before=168,
            audience="Executive Team",
            channel=_CHANNEL_MAP["Executive Team"],
            subject=f"[CRITICAL CHANGE] {number} — {title}",
            message_template=(
                f"Se planifica un cambio crítico ({number}): «{title}».\n"
                f"Ventana propuesta: {window_label}. Tiempo de inactividad estimado: {downtime} min.\n"
                "Se requiere confirmación de disponibilidad y aprobación ejecutiva."
            ),
            responsible="Change Manager",
        )
        _notif(
            timing="T-72h", hours_before=72,
            audience="End Users (affected services)",
            channel=_CHANNEL_MAP["End Users (affected services)"],
            subject=f"[Aviso de mantenimiento] {number} — {title}",
            message_template=(
                f"Estimado usuario,\nSe realizará un mantenimiento programado ({number}) el {window_label}.\n"
                f"Interrupción estimada: {downtime} minutos. Disculpe las molestias."
            ),
            responsible="Service Desk / Comms Team",
        )

    if HIGH_RISK:
        _notif(
            timing="T-48h", hours_before=48,
            audience="Service Desk",
            channel=_CHANNEL_MAP["Service Desk"],
            subject=f"[Aviso previo] Cambio {number} — {title}",
            message_template=(
                f"Notificación de cambio programado ({number}): «{title}».\n"
                f"Ventana: {window_label}. Impacto: riesgo {risk_label.upper()}.\n"
                "Prepara guiones de respuesta para consultas de usuarios durante la ventana."
            ),
            responsible="Change Manager",
        )
        _notif(
            timing="T-48h", hours_before=48,
            audience="Line Manager",
            channel=_CHANNEL_MAP["Line Manager"],
            subject=f"[Cambio programado] {number} — {title}",
            message_template=(
                f"Cambio programado ({number}): «{title}».\n"
                f"Ventana: {window_label}. Riesgo: {risk_label.upper()}.\n"
                "Asegúrese de que el equipo técnico esté disponible durante la ventana."
            ),
            responsible="Change Manager",
        )

    # All risk levels get T-24h notification to IT team
    _notif(
        timing="T-24h", hours_before=24,
        audience="IT Operations Team",
        channel=_CHANNEL_MAP["IT Operations Team"],
        subject=f"[Recordatorio] Cambio mañana: {number} — {title}",
        message_template=(
            f"Recordatorio: mañana se ejecuta el cambio {number}: «{title}».\n"
            f"Ventana: {window_label}. Plan de pruebas y rollback deben estar listos.\n"
            "Confirma disponibilidad respondiendo este mensaje."
        ),
        responsible="Change Manager",
    )

    if HIGH_RISK:
        _notif(
            timing="T-24h", hours_before=24,
            audience="End Users (affected services)",
            channel=_CHANNEL_MAP["End Users (affected services)"],
            subject=f"[Recordatorio mantenimiento mañana] {number}",
            message_template=(
                f"Recordatorio: mañana {window_label} se realizará el mantenimiento {number}.\n"
                f"Inactividad estimada: {downtime} min. Guarda tu trabajo antes de la ventana."
            ),
            responsible="Service Desk / Comms Team",
        )

    _notif(
        timing="T-1h", hours_before=1,
        audience="IT Operations Team",
        channel="IM (Slack/Teams) — canal #operations",
        subject=f"🔧 1 hora para inicio: {number}",
        message_template=(
            f"En 1 hora inicia el cambio {number}: «{title}».\n"
            "Confirma presencia en el canal de guardia. Plan de rollback accesible."
        ),
        responsible="Change Manager",
    )

    if HIGH_RISK:
        _notif(
            timing="T-1h", hours_before=1,
            audience="Service Desk",
            channel="IM (Slack/Teams) — canal #service-desk",
            subject=f"⚠️ Cambio iniciará en 1h: {number}",
            message_template=(
                f"En 1 hora inicia {number}. Activar modo guardia.\n"
                "Cualquier incidente relacionado durante la ventana: escalar a Change Manager."
            ),
            responsible="Change Manager",
        )

    # ── DURING CHANGE ─────────────────────────────────────────────────────────
    if HIGH_RISK:
        _notif(
            timing="change_start", hours_before=0,
            audience="IT Operations Team",
            channel="IM (Slack/Teams) — canal #operations",
            subject=f"▶️ Cambio iniciado: {number}",
            message_template=(
                f"El cambio {number} ha iniciado a las {{hora_inicio_utc}} UTC.\n"
                "Monitorización activa. Reportar anomalías inmediatamente."
            ),
            responsible="Change Manager",
        )

    if risk_label == "critical":
        _notif(
            timing="change_midpoint", hours_before=None,
            audience="Executive Team",
            channel=_CHANNEL_MAP["Executive Team"],
            subject=f"[Status update] Cambio {number} en progreso",
            message_template=(
                f"El cambio crítico {number} está en progreso.\n"
                "Estado: {{estado_actual}}. Sin anomalías mayores detectadas hasta el momento."
            ),
            responsible="Change Manager",
        )

    # ── POST-CHANGE ───────────────────────────────────────────────────────────
    _notif(
        timing="post_change_success", hours_before=None,
        audience="IT Operations Team",
        channel=_CHANNEL_MAP["IT Operations Team"],
        subject=f"✅ Cambio completado: {number}",
        message_template=(
            f"El cambio {number}: «{title}» se ha completado exitosamente.\n"
            "Todos los tests post-cambio pasaron. Sistemas en estado operacional normal."
        ),
        responsible="Change Manager",
    )

    if HIGH_RISK:
        _notif(
            timing="post_change_success", hours_before=None,
            audience="End Users (affected services)",
            channel=_CHANNEL_MAP["End Users (affected services)"],
            subject=f"✅ Mantenimiento finalizado: {number}",
            message_template=(
                f"El mantenimiento programado {number} ha concluido.\n"
                "Todos los servicios están disponibles con normalidad. Gracias por su paciencia."
            ),
            responsible="Service Desk / Comms Team",
        )

    _notif(
        timing="post_change_failure_rollback", hours_before=None,
        audience="IT Operations Team",
        channel="IM (Slack/Teams) — canal #operations (URGENTE)",
        subject=f"❌ ROLLBACK iniciado: {number}",
        message_template=(
            f"El cambio {number} ha activado el plan de rollback.\n"
            "Motivo: {{motivo_rollback}}. Equipo de rollback en acción. ETA: {{eta_minutos}} min."
        ),
        responsible="Change Manager",
    )

    if HIGH_RISK:
        _notif(
            timing="post_change_failure_rollback", hours_before=None,
            audience="End Users (affected services)",
            channel=_CHANNEL_MAP["End Users (affected services)"],
            subject=f"[Mantenimiento extendido] {number}",
            message_template=(
                f"El mantenimiento {number} ha encontrado un inconveniente y se está resolviendo.\n"
                "ETA de restauración: {{eta_restauracion}}. Pedimos disculpas por el tiempo adicional."
            ),
            responsible="Service Desk / Comms Team",
        )

    if risk_label == "critical":
        _notif(
            timing="post_pir", hours_before=None,
            audience="Executive Team",
            channel=_CHANNEL_MAP["Executive Team"],
            subject=f"[PIR] Cambio {number} — Informe post-implementación",
            message_template=(
                f"Se ha completado la Revisión Post-Implementación del cambio {number}.\n"
                "Resultado: {{resultado_pir}}. Informe completo adjunto."
            ),
            responsible="Change Manager",
        )

    comms_plan = {
        "change_id": change_id,
        "change_number": number,
        "change_title": title,
        "risk_label": risk_label,
        "suggested_window": window_label,
        "total_notifications": len(notifications),
        "timeline_buckets": {
            "pre_change": [n for n in notifications if n["timing"].startswith("T-") or n["timing"] == "change_start"],
            "during_change": [n for n in notifications if n["timing"] in ("change_start", "change_midpoint")],
            "post_change": [n for n in notifications if n["timing"].startswith("post_")],
        },
        "notifications": notifications,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "generated_by": current_user_id,
    }

    _set_json_setting(db, f"sd.change.comms.{change_id}", comms_plan)
    db.commit()
    return comms_plan


# ══════════════════════════════════════════════════════════════════════════════
# What-If Simulation — pure computation, no DB writes
# ══════════════════════════════════════════════════════════════════════════════

def simulate_change_whatif(
    db: Session,
    change_id: str,
    overrides: dict,
) -> dict:
    """Simulate the risk impact of hypothetical changes to a Change Request.

    *Does not persist anything.* Returns a side-by-side comparison of the
    original vs simulated scenario including risk score, label, components,
    and maintenance window.

    Supported overrides (all optional):
        downtime_minutes  (int)   : simulate a different planned downtime
        change_type       (str)   : standard | normal | emergency
        extra_ci_ids      (list)  : add CIs to the affected set
        remove_ci_ids     (list)  : remove CIs from the affected set
        scheduled_hour_utc (int)  : evaluate a specific hour (0-23) for the window
        scheduled_dow      (int)  : evaluate a specific day-of-week (0=Mon) for the window

    Returns:
        {
          "change_id": ...,
          "original": {score, risk_label, components, window},
          "simulated": {score, risk_label, components, window},
          "delta": {score_diff, risk_change, window_changed},
          "overrides_applied": {...},
        }
    """
    from types import SimpleNamespace  # noqa: PLC0415

    change = db.query(ITSMChangeRequest).filter(ITSMChangeRequest.id == change_id).first()
    if not change:
        from fastapi import HTTPException  # noqa: PLC0415
        raise HTTPException(404, f"Change {change_id} not found")

    # ── ORIGINAL ──────────────────────────────────────────────────────────────
    orig_risk = score_change_risk(db, change)
    orig_ci_ids = orig_risk["ci_ids_expanded"]
    orig_window = suggest_maintenance_window(db, change, orig_ci_ids)

    # ── BUILD SIMULATED CHANGE OBJECT (SimpleNamespace — no DB touch) ─────────
    orig_direct_ids: list[str] = []
    try:
        if change.affected_cis:
            raw = json.loads(change.affected_cis)
            orig_direct_ids = raw if isinstance(raw, list) else []
    except (json.JSONDecodeError, TypeError):
        orig_direct_ids = []

    sim_direct_ids = list(orig_direct_ids)
    for cid in overrides.get("extra_ci_ids", []):
        if cid not in sim_direct_ids:
            sim_direct_ids.append(cid)
    remove_set = set(overrides.get("remove_ci_ids", []))
    sim_direct_ids = [cid for cid in sim_direct_ids if cid not in remove_set]

    # Map string change_type to enum
    sim_change_type = change.change_type
    if "change_type" in overrides:
        try:
            sim_change_type = ChangeType(overrides["change_type"])
        except ValueError:
            pass  # ignore invalid enum, keep original

    sim_downtime = int(overrides["downtime_minutes"]) if "downtime_minutes" in overrides else (change.downtime_minutes or 0)

    sim_obj = SimpleNamespace(
        change_type=sim_change_type,
        risk=change.risk,
        affected_cis=json.dumps(sim_direct_ids),
        downtime_minutes=sim_downtime,
    )

    sim_risk = score_change_risk(db, sim_obj)  # type: ignore[arg-type]
    sim_ci_ids = sim_risk["ci_ids_expanded"]
    sim_window = suggest_maintenance_window(db, change, sim_ci_ids)

    # If caller requested evaluation of a specific window slot
    proposed_window: Optional[dict] = None
    if "scheduled_hour_utc" in overrides or "scheduled_dow" in overrides:
        prop_hour = int(overrides.get("scheduled_hour_utc", sim_window["hour_utc"]))
        prop_dow = int(overrides.get("scheduled_dow", sim_window["day_of_week"]))
        prop_hour = max(0, min(23, prop_hour))
        prop_dow = max(0, min(6, prop_dow))

        # Count incidents in proposed slot using same freq matrix logic
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=28)
        q = db.query(Ticket.created_at).filter(
            Ticket.created_at >= cutoff,
            Ticket.ticket_type == "incident",
        )
        if sim_ci_ids:
            q = q.filter(Ticket.ci_id.in_(sim_ci_ids))
        incidents = q.all()

        freq: list[list[int]] = [[0] * 24 for _ in range(7)]
        for (ts,) in incidents:
            if ts:
                ts_utc = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts
                freq[ts_utc.weekday()][ts_utc.hour] += 1

        proposed_window_sum = sum(freq[prop_dow][(prop_hour + i) % 24] for i in range(4))
        _days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        proposed_window = {
            "day_of_week": prop_dow,
            "hour_utc": prop_hour,
            "window_label": f"{_days[prop_dow]} {prop_hour:02d}:00–{(prop_hour+4)%24:02d}:00 UTC",
            "avg_incidents_in_window": round(proposed_window_sum / 4, 2),
            "vs_optimal_diff": round((proposed_window_sum / 4) - sim_window["avg_incidents_in_window"], 2),
            "is_optimal": proposed_window_sum / 4 <= sim_window["avg_incidents_in_window"] + 0.1,
        }

    # ── DELTA ─────────────────────────────────────────────────────────────────
    _risk_rank = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    orig_rank = _risk_rank.get(orig_risk["risk_label"], 2)
    sim_rank = _risk_rank.get(sim_risk["risk_label"], 2)
    delta_rank = sim_rank - orig_rank
    risk_change = (
        "escalated" if delta_rank > 0
        else "reduced" if delta_rank < 0
        else "unchanged"
    )

    result: dict = {
        "change_id": change_id,
        "change_number": change.number,
        "original": {
            "score": orig_risk["score"],
            "risk_label": orig_risk["risk_label"],
            "components": orig_risk["components"],
            "ci_count_expanded": len(orig_ci_ids),
            "window": orig_window,
        },
        "simulated": {
            "score": sim_risk["score"],
            "risk_label": sim_risk["risk_label"],
            "components": sim_risk["components"],
            "ci_count_expanded": len(sim_ci_ids),
            "window": sim_window,
        },
        "delta": {
            "score_diff": sim_risk["score"] - orig_risk["score"],
            "risk_change": risk_change,
            "ci_count_diff": len(sim_ci_ids) - len(orig_ci_ids),
            "window_changed": sim_window["window_label"] != orig_window["window_label"],
        },
        "overrides_applied": {
            k: v for k, v in overrides.items() if k not in ("extra_ci_ids", "remove_ci_ids")
        },
    }
    if "extra_ci_ids" in overrides:
        result["overrides_applied"]["extra_ci_ids"] = overrides["extra_ci_ids"]
    if "remove_ci_ids" in overrides:
        result["overrides_applied"]["remove_ci_ids"] = overrides["remove_ci_ids"]
    if proposed_window is not None:
        result["proposed_window_evaluation"] = proposed_window

    return result
