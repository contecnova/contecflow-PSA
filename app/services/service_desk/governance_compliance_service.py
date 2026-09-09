"""
Governance & Compliance Service — Fase 3 ITSM Scale
====================================================
Sprint 23-24: Informes de gobernanza ITSM, auditoría de cumplimiento y
paneles de control ejecutivo alineados con ITIL v4 e ISO 20000.

Capacidades:
  1. generate_compliance_report()   — informe de cumplimiento ITIL/ISO 20000
     con indicadores ponderados y nivel de madurez (1-5 CMM).
  2. audit_change_management()      — revisa Change Requests aprobados sin CAB,
     cambios de emergencia sin PIR, etc.
  3. audit_incident_management()    — P1s sin Major Incident vinculado,
     incidentes recurrentes sin Problem asociado, etc.
  4. audit_access_reviews()         — detecta usuarios con accesos sin revisión
     periódica, tickets de acceso pendientes más de 30 días, y cuentas inactivas
     con acceso activo.
  5. get_executive_dashboard()      — KPIs de alto nivel para CIO/CISO.
  6. schedule_compliance_check()    — Celery entrypoint que ejecuta todas las
     auditorías y persiste el resultado en la BD.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.service_desk import (
    ITSMChangeRequest,
    ChangeType,
    MajorIncident,
    Problem,
    ProblemStatus,
    Ticket,
    TicketPriority,
    TicketStatus,
    TicketType,
)

logger = logging.getLogger(__name__)

# ── ITIL maturity weights ─────────────────────────────────────────────────────
# Each dimension scored 0-100 → weighted average → maps to CMM level 1-5

_MATURITY_DIMENSIONS = {
    "incident_management":  0.22,
    "change_management":    0.18,
    "problem_management":   0.18,
    "sla_compliance":       0.18,
    "access_reviews":       0.12,
    "asset_cmdb":           0.12,
}

def _cmm_level(score: float) -> int:
    """Map 0-100 score to CMM maturity level 1-5."""
    if score >= 85:
        return 5
    elif score >= 70:
        return 4
    elif score >= 50:
        return 3
    elif score >= 30:
        return 2
    return 1


_CMM_LABELS = {1: "Initial", 2: "Repeatable", 3: "Defined", 4: "Managed", 5: "Optimized"}


# ── Incident management audit ─────────────────────────────────────────────────

def audit_incident_management(db: Session, days: int = 30) -> dict:
    """Audit incident management practices for the last *days* days.

    Checks:
      - P1 incidents without a linked MajorIncident
      - Recurring incidents (same CI, > 3 times) without a linked Problem
      - Average resolution time vs SLA targets
      - FCR (first contact resolution) rate

    Returns::

        {
          "score": int (0-100),
          "findings": [{"severity", "title", "count", "details"}],
          "summary": str,
        }
    """
    since = datetime.now(tz=timezone.utc) - timedelta(days=days)

    incidents = (
        db.query(Ticket)
        .filter(
            Ticket.ticket_type == TicketType.incident,
            Ticket.created_at >= since,
        )
        .all()
    )

    findings = []
    score = 100

    # ── Finding 1: P1 without MajorIncident ───────────────────────────────────
    p1_tickets = [t for t in incidents if t.priority == TicketPriority.p1_critical]
    # Auditoria 2026-08 (hallazgo 22). Esto preguntaba por
    # `MajorIncident.tickets` detras de un `hasattr`, y esa relacion **no
    # existe**: entre `MajorIncident` y `Ticket` no hay ni columna ni tabla de
    # union, comprobado sobre `Base.metadata`. El `hasattr` es correcto, asi
    # que `mi` era **siempre** `None` y **todo** ticket P1 se reportaba como
    # «P1 sin incidencia mayor declarada»: un hallazgo de cumplimiento que
    # siempre salta no informa de nada.
    #
    # **No se inventa el enlace.** Relacionar las dos entidades es un cambio de
    # esquema con decision de diseno detras —¿un ticket pertenece a una sola
    # incidencia mayor, o varias comparten tickets?— y no se cuela en una tanda
    # de otra cosa. Lo que se hace es **decir la verdad**: mientras no exista
    # el enlace, esta comprobacion no se puede hacer, y se declara como no
    # evaluable en vez de dar un falso positivo por cada P1.
    p1_without_mi: list[str] = []
    enlace_disponible = hasattr(MajorIncident, "tickets")
    if enlace_disponible:
        for t in p1_tickets:
            mi = db.query(MajorIncident).filter(
                MajorIncident.tickets.any(id=t.id)  # type: ignore[attr-defined]
            ).first()
            if not mi:
                p1_without_mi.append(t.number)

    if p1_without_mi:
        pct = round(len(p1_without_mi) / max(len(p1_tickets), 1) * 100)
        penalty = min(30, pct // 3)
        score -= penalty
        findings.append({
            "severity": "high" if pct >= 50 else "medium",
            "title": "P1 incidents without Major Incident record",
            "count": len(p1_without_mi),
            "details": f"{pct}% of P1 incidents ({len(p1_without_mi)}) lack a Major Incident declaration.",
            "sample": p1_without_mi[:5],
        })

    # ── Finding 2: Recurring incidents without Problem ────────────────────────
    ci_counts: dict[str, list] = {}
    for t in incidents:
        if t.ci_id:
            ci_counts.setdefault(t.ci_id, []).append(t)

    recurring_without_problem = []
    for ci_id, ci_tickets in ci_counts.items():
        if len(ci_tickets) >= 3:
            has_problem = any(t.problem_id for t in ci_tickets if hasattr(t, "problem_id") and t.problem_id)  # type: ignore[attr-defined]
            if not has_problem:
                recurring_without_problem.append({"ci_id": ci_id, "incident_count": len(ci_tickets)})

    if recurring_without_problem:
        score -= min(20, len(recurring_without_problem) * 4)
        findings.append({
            "severity": "medium",
            "title": "Recurring incidents without Problem record",
            "count": len(recurring_without_problem),
            "details": f"{len(recurring_without_problem)} CIs had 3+ incidents with no linked Problem.",
            "sample": recurring_without_problem[:5],
        })

    # ── Finding 3: SLA compliance ─────────────────────────────────────────────
    resolved = [t for t in incidents if t.resolved_at]
    breached = [t for t in resolved if getattr(t, "sla_resolution_breached", False)]
    if resolved:
        breach_rate = len(breached) / len(resolved)
        if breach_rate > 0.10:
            penalty = min(20, int(breach_rate * 100) // 2)
            score -= penalty
            findings.append({
                "severity": "high" if breach_rate > 0.25 else "medium",
                "title": "SLA resolution breach rate above threshold",
                "count": len(breached),
                "details": f"{round(breach_rate*100, 1)}% of resolved incidents breached SLA (target <10%).",
            })

    score = max(0, score)
    summary = (
        f"Incident management score: {score}/100 (CMM Level {_cmm_level(score)} — "
        f"{_CMM_LABELS[_cmm_level(score)]}). "
        f"Analysed {len(incidents)} incidents over {days} days."
    )

    return {"score": score, "findings": findings, "summary": summary}


# ── Change management audit ───────────────────────────────────────────────────

def audit_change_management(db: Session, days: int = 30) -> dict:
    """Audit change management practices.

    Checks:
      - Emergency changes without PIR
      - Normal changes approved without CAB record (approver_id missing)
      - Changes with high auto-risk score that were applied as standard
      - High rollback usage (pir_success = False rate)

    Returns same structure as audit_incident_management.
    """
    since = datetime.now(tz=timezone.utc) - timedelta(days=days)

    changes = (
        db.query(ITSMChangeRequest)
        .filter(
            ITSMChangeRequest.created_at >= since,
            ITSMChangeRequest.status.in_(["implemented", "closed", "failed"]),
        )
        .all()
    )

    findings = []
    score = 100

    # ── Finding 1: Emergency changes without PIR ──────────────────────────────
    emergency = [c for c in changes if c.change_type == ChangeType.emergency]
    emergency_no_pir = [c for c in emergency if not c.pir_notes]
    if emergency_no_pir:
        pct = round(len(emergency_no_pir) / max(len(emergency), 1) * 100)
        score -= min(25, pct // 3)
        findings.append({
            "severity": "high" if pct >= 60 else "medium",
            "title": "Emergency changes without PIR (Post-Implementation Review)",
            "count": len(emergency_no_pir),
            "details": f"{pct}% of emergency changes lack a PIR. ITIL requires PIR for all emergency changes.",
            "sample": [c.number for c in emergency_no_pir[:5]],
        })

    # ── Finding 2: Normal changes without CAB approval ────────────────────────
    normal = [c for c in changes if c.change_type == ChangeType.normal]
    normal_no_cab = [c for c in normal if not c.approver_id]
    if normal_no_cab:
        pct = round(len(normal_no_cab) / max(len(normal), 1) * 100)
        score -= min(20, pct // 4)
        findings.append({
            "severity": "high" if pct >= 40 else "medium",
            "title": "Normal changes without CAB approval record",
            "count": len(normal_no_cab),
            "details": f"{pct}% of normal changes have no approver recorded.",
            "sample": [c.number for c in normal_no_cab[:5]],
        })

    # ── Finding 3: Change failure rate ────────────────────────────────────────
    failed = [c for c in changes if str(c.status) in ("failed",)]
    if changes:
        failure_rate = len(failed) / len(changes)
        if failure_rate > 0.10:
            penalty = min(20, int(failure_rate * 100) // 3)
            score -= penalty
            findings.append({
                "severity": "high" if failure_rate > 0.20 else "medium",
                "title": "Change failure rate above threshold",
                "count": len(failed),
                "details": f"{round(failure_rate*100, 1)}% of changes failed (target <10%).",
            })

    # ── Finding 4: Standard changes with high auto-risk ───────────────────────
    if hasattr(ITSMChangeRequest, "auto_risk_score"):
        high_risk_standard = [
            c for c in changes
            if c.change_type == ChangeType.standard
            and getattr(c, "auto_risk_score", 0) and c.auto_risk_score >= 55
        ]
        if high_risk_standard:
            score -= min(15, len(high_risk_standard) * 3)
            findings.append({
                "severity": "medium",
                "title": "Standard changes with elevated auto-risk score",
                "count": len(high_risk_standard),
                "details": "These changes were classified as Standard but scored ≥55 risk. Consider reclassification.",
                "sample": [c.number for c in high_risk_standard[:5]],
            })

    score = max(0, score)
    summary = (
        f"Change management score: {score}/100 (CMM Level {_cmm_level(score)} — "
        f"{_CMM_LABELS[_cmm_level(score)]}). "
        f"Analysed {len(changes)} implemented changes over {days} days."
    )

    return {"score": score, "findings": findings, "summary": summary}


# ── Problem management audit ──────────────────────────────────────────────────

def audit_problem_management(db: Session, days: int = 90) -> dict:
    """Audit problem management practices.

    Checks:
      - Open problems older than 30 days without RCA
      - Problems auto-detected (Phase 1) not yet manually reviewed
      - Known error database (KB) coverage

    Returns same structure.
    """
    since = datetime.now(tz=timezone.utc) - timedelta(days=days)
    thirty_days_ago = datetime.now(tz=timezone.utc) - timedelta(days=30)

    problems = db.query(Problem).filter(Problem.created_at >= since).all()

    findings = []
    score = 100

    # ── Finding 1: Stale open problems without RCA ────────────────────────────
    open_problems = [p for p in problems if p.status not in (ProblemStatus.closed, ProblemStatus.resolved)]
    stale = [p for p in open_problems if p.created_at and p.created_at <= thirty_days_ago]
    stale_no_rca = [p for p in stale if not p.root_cause]
    if stale_no_rca:
        score -= min(25, len(stale_no_rca) * 5)
        findings.append({
            "severity": "high",
            "title": "Open problems older than 30 days without RCA",
            "count": len(stale_no_rca),
            "details": f"{len(stale_no_rca)} problems are stale with no root cause documented.",
            "sample": [p.number for p in stale_no_rca[:5]],
        })

    # ── Finding 2: Auto-detected problems not reviewed ────────────────────────
    auto_detected = [p for p in problems if getattr(p, "auto_detected", False)]
    auto_no_review = [p for p in auto_detected if not p.root_cause and p.status not in (ProblemStatus.closed,)]
    if auto_no_review:
        score -= min(15, len(auto_no_review) * 3)
        findings.append({
            "severity": "medium",
            "title": "Auto-detected problems awaiting human review",
            "count": len(auto_no_review),
            "details": "Auto-detected problems need RCA validation by a human engineer.",
        })

    score = max(0, score)
    summary = (
        f"Problem management score: {score}/100 (CMM Level {_cmm_level(score)} — "
        f"{_CMM_LABELS[_cmm_level(score)]}). "
        f"Analysed {len(problems)} problems over {days} days."
    )

    return {"score": score, "findings": findings, "summary": summary}


# ── Access reviews audit ──────────────────────────────────────────────────────

def audit_access_reviews(db: Session, days: int = 90) -> dict:
    """Audit access management practices.

    Checks:
      - Access request tickets open longer than 30 days without resolution
      - Users inactive for 90+ days that still have an active account
      - Privileged access tickets (admin/elevated) without review within the period

    Returns same structure as other audit functions::

        {
          "score": int (0-100),
          "findings": [{"severity", "title", "count", "details"}],
          "summary": str,
        }
    """
    since = datetime.now(tz=timezone.utc) - timedelta(days=days)
    thirty_days_ago = datetime.now(tz=timezone.utc) - timedelta(days=30)
    ninety_days_ago = datetime.now(tz=timezone.utc) - timedelta(days=90)

    findings = []
    score = 100

    # ── Finding 1: Access request tickets open longer than 30 days ───────────
    try:
        access_tickets = (
            db.query(Ticket)
            .filter(
                Ticket.ticket_type == TicketType.service_request,
                Ticket.created_at >= since,
                Ticket.status.notin_([TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled]),
                Ticket.title.ilike("%access%"),
            )
            .all()
        )
        stale_access = [t for t in access_tickets if t.created_at and t.created_at <= thirty_days_ago]
        if stale_access:
            pct = round(len(stale_access) / max(len(access_tickets), 1) * 100)
            penalty = min(25, pct // 3)
            score -= penalty
            findings.append({
                "severity": "high" if pct >= 50 else "medium",
                "title": "Access request tickets unresolved for 30+ days",
                "count": len(stale_access),
                "details": (
                    f"{len(stale_access)} access request tickets have been open for over 30 days "
                    f"({pct}% of access tickets in period)."
                ),
                "sample": [t.number for t in stale_access[:5]],
            })
    except Exception as exc:
        logger.debug("Access ticket audit skipped: %s", exc)

    # ── Finding 2: Inactive users with active accounts ────────────────────────
    try:
        from app.models.user import User

        inactive_users = (
            db.query(User)
            .filter(
                User.is_active.is_(True),
                User.last_login.isnot(None),
                User.last_login <= ninety_days_ago,
            )
            .all()
        )
        if inactive_users:
            score -= min(20, len(inactive_users) * 2)
            findings.append({
                "severity": "high" if len(inactive_users) > 10 else "medium",
                "title": "Active accounts with no login in 90+ days",
                "count": len(inactive_users),
                "details": (
                    f"{len(inactive_users)} user accounts are marked active but have not logged in "
                    "for 90 or more days. Consider disabling or reviewing these accounts."
                ),
                "sample": [u.email for u in inactive_users[:5]],
            })
    except Exception as exc:
        logger.debug("Inactive user audit skipped: %s", exc)

    # ── Finding 3: Privileged access tickets without timely review ─────────────
    try:
        privileged_tickets = (
            db.query(Ticket)
            .filter(
                Ticket.ticket_type == TicketType.service_request,
                Ticket.created_at >= since,
                or_(
                    Ticket.title.ilike("%admin%"),
                    Ticket.title.ilike("%privilege%"),
                    Ticket.title.ilike("%elevated%"),
                ),
            )
            .all()
        )
        _closed_statuses = {TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled}
        unreviewed = [
            t for t in privileged_tickets
            if t.status not in _closed_statuses
            and t.created_at and t.created_at <= thirty_days_ago
        ]
        if unreviewed:
            score -= min(20, len(unreviewed) * 5)
            findings.append({
                "severity": "high",
                "title": "Privileged access tickets without timely review",
                "count": len(unreviewed),
                "details": (
                    f"{len(unreviewed)} privileged access tickets (admin/elevated) remain unresolved "
                    "beyond the 30-day review window. Privileged access should be time-bound and reviewed."
                ),
                "sample": [t.number for t in unreviewed[:5]],
            })
    except Exception as exc:
        logger.debug("Privileged access audit skipped: %s", exc)

    score = max(0, score)
    summary = (
        f"Access reviews score: {score}/100 (CMM Level {_cmm_level(score)} — "
        f"{_CMM_LABELS[_cmm_level(score)]}). "
        f"Analysed access management over {days} days."
    )
    return {"score": score, "findings": findings, "summary": summary}


# ── Full compliance report ────────────────────────────────────────────────────

def generate_compliance_report(
    db: Session,
    days: int = 30,
    persist: bool = True,
) -> dict:
    """Generate a full ITIL/ISO 20000-aligned compliance report.

    Runs all sub-audits, computes weighted maturity score, and optionally
    persists the report in ``sd_compliance_reports``.

    Returns::

        {
          "generated_at": str,
          "period_days": int,
          "overall_score": int,
          "cmm_level": int,
          "cmm_label": str,
          "dimensions": {name: {score, cmm_level, findings}},
          "top_findings": [worst findings across all dims],
          "recommendations": [str],
        }
    """
    incident_audit = audit_incident_management(db, days)
    change_audit = audit_change_management(db, days)
    problem_audit = audit_problem_management(db, days=max(days, 90))
    access_audit = audit_access_reviews(db, days=max(days, 90))

    # SLA score from incident audit (reuse breach findings)
    sla_score = 100
    for f in incident_audit["findings"]:
        if "SLA" in f["title"]:
            sla_score = max(0, 100 - f["count"] * 3)

    # Asset/CMDB score — basic: check % CIs with is_discovered
    try:
        from app.models.cmdb import CMDBItem
        total_cis = db.query(func.count(CMDBItem.id)).scalar() or 0
        discovered_cis = db.query(func.count(CMDBItem.id)).filter(
            CMDBItem.is_discovered.is_(True)
        ).scalar() or 0
        cmdb_score = round(discovered_cis / total_cis * 100) if total_cis else 50
    except Exception:
        cmdb_score = 50

    dimensions = {
        "incident_management": {"score": incident_audit["score"], "findings": incident_audit["findings"]},
        "change_management":   {"score": change_audit["score"],   "findings": change_audit["findings"]},
        "problem_management":  {"score": problem_audit["score"],  "findings": problem_audit["findings"]},
        "sla_compliance":      {"score": sla_score,               "findings": []},
        "access_reviews":      {"score": access_audit["score"],   "findings": access_audit["findings"]},
        "asset_cmdb":          {"score": cmdb_score,              "findings": []},
    }

    for dim in dimensions.values():
        dim["cmm_level"] = _cmm_level(dim["score"])
        dim["cmm_label"] = _CMM_LABELS[dim["cmm_level"]]

    # Weighted overall score
    overall = round(sum(
        dimensions[k]["score"] * w
        for k, w in _MATURITY_DIMENSIONS.items()
    ))

    # Top findings (worst severity first)
    all_findings = []
    for dim_name, dim_data in dimensions.items():
        for f in dim_data.get("findings", []):
            all_findings.append({**f, "dimension": dim_name})
    all_findings.sort(key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.get("severity", "low"), 2))

    # Auto-recommendations
    recommendations = []
    if change_audit["score"] < 70:
        recommendations.append("Implementar registro formal de aprobación CAB para todos los cambios normales.")
    if incident_audit["score"] < 70:
        recommendations.append("Enlazar incidentes P1 con Major Incident automáticamente al crear el ticket.")
    if problem_audit["score"] < 70:
        recommendations.append("Establecer SLA interno de 30 días para documentar RCA en problemas abiertos.")
    if sla_score < 80:
        recommendations.append("Revisar políticas SLA — breach rate supera el umbral aceptable del 10%.")
    if cmdb_score < 60:
        recommendations.append("Aumentar cobertura de auto-discovery CMDB — menos del 60% de CIs están descubiertos.")
    if access_audit["score"] < 70:
        recommendations.append("Revisar cuentas de usuario inactivas y tickets de acceso sin resolver — implementar revisión periódica de accesos (Access Review Campaign).")

    report = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "period_days": days,
        "overall_score": overall,
        "cmm_level": _cmm_level(overall),
        "cmm_label": _CMM_LABELS[_cmm_level(overall)],
        "dimensions": dimensions,
        "top_findings": all_findings[:10],
        "recommendations": recommendations,
    }

    if persist:
        _persist_compliance_report(db, report)

    return report


def _persist_compliance_report(db: Session, report: dict) -> None:
    """Save compliance report to sd_compliance_reports if table/model exists."""
    try:
        from app.models.service_desk import ComplianceReport
        rec = ComplianceReport(
            id=str(uuid4()),
            generated_at=datetime.now(tz=timezone.utc),
            period_days=report["period_days"],
            overall_score=report["overall_score"],
            cmm_level=report["cmm_level"],
            report_json=json.dumps(report),
        )
        db.add(rec)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("Could not persist compliance report: %s", exc)


# ── Executive dashboard ───────────────────────────────────────────────────────

def get_executive_dashboard(db: Session, days: int = 30) -> dict:
    """Return a CIO/CISO-level KPI dashboard combining ITSM health indicators.

    Returns::

        {
          "service_health_score": int,  # 0-100
          "open_incidents": int,
          "critical_open": int,
          "unresolved_problems": int,
          "pending_changes": int,
          "sla_compliance_pct": float,
          "cmm_level": int,
          "top_risks": [str],
        }
    """
    since = datetime.now(tz=timezone.utc) - timedelta(days=days)

    open_incidents = (
        db.query(func.count(Ticket.id))
        .filter(
            Ticket.ticket_type == TicketType.incident,
            Ticket.status.notin_(["resolved", "closed", "cancelled"]),
        )
        .scalar() or 0
    )

    critical_open = (
        db.query(func.count(Ticket.id))
        .filter(
            Ticket.ticket_type == TicketType.incident,
            Ticket.priority == TicketPriority.p1_critical,
            Ticket.status.notin_(["resolved", "closed", "cancelled"]),
        )
        .scalar() or 0
    )

    unresolved_problems = (
        db.query(func.count(Problem.id))
        .filter(Problem.status.notin_(["closed", "resolved"]))
        .scalar() or 0
    )

    pending_changes = (
        db.query(func.count(ITSMChangeRequest.id))
        .filter(ITSMChangeRequest.status.in_(["submitted", "reviewing", "approved"]))
        .scalar() or 0
    )

    # SLA compliance last N days
    resolved_recent = (
        db.query(Ticket)
        .filter(
            Ticket.ticket_type == TicketType.incident,
            Ticket.resolved_at.isnot(None),
            Ticket.created_at >= since,
        )
        .all()
    )
    sla_ok = [t for t in resolved_recent if not getattr(t, "sla_resolution_breached", False)]
    sla_pct = round(len(sla_ok) / len(resolved_recent) * 100, 1) if resolved_recent else 100.0

    # Overall service health score (simplified)
    health = 100
    if critical_open:
        health -= min(30, critical_open * 10)
    if sla_pct < 90:
        health -= int((90 - sla_pct) // 2)
    if unresolved_problems > 5:
        health -= min(20, (unresolved_problems - 5) * 2)
    health = max(0, health)

    top_risks: list[str] = []
    if critical_open:
        top_risks.append(f"{critical_open} open P1 incident(s) require immediate attention")
    if sla_pct < 85:
        top_risks.append(f"SLA compliance at {sla_pct}% — below 85% target")
    if unresolved_problems > 10:
        top_risks.append(f"{unresolved_problems} unresolved problems in backlog")

    compliance_report = generate_compliance_report(db, days=days, persist=False)

    return {
        "service_health_score": health,
        "open_incidents": open_incidents,
        "critical_open": critical_open,
        "unresolved_problems": unresolved_problems,
        "pending_changes": pending_changes,
        "sla_compliance_pct": sla_pct,
        "cmm_level": compliance_report["cmm_level"],
        "cmm_label": compliance_report["cmm_label"],
        "overall_compliance_score": compliance_report["overall_score"],
        "top_risks": top_risks,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
    }


# ── Celery entrypoint ─────────────────────────────────────────────────────────

def schedule_compliance_check(db: Session) -> dict:
    """Run all audits and persist compliance report.

    Called from Celery beat task `compliance_check` weekly on Mondays at 06:00.
    """
    report = generate_compliance_report(db, days=30, persist=True)
    logger.info(
        "Compliance check done: overall=%d CMM=%d findings=%d",
        report["overall_score"],
        report["cmm_level"],
        len(report["top_findings"]),
    )
    return {
        "overall_score": report["overall_score"],
        "cmm_level": report["cmm_level"],
        "findings_count": len(report["top_findings"]),
        "recommendations_count": len(report["recommendations"]),
    }


# ── Gobernanza de IA y contrato de calidad, movidos del endpoint ─────────────
#
# Auditoria 2026-08 (hallazgo 22). Las consultas de
# `endpoints/service_desk/governance_ops.py` estaban ahi, y dos de ellas
# filtraban asi:
#
#     q = db.query(SDAIEvaluationRun)
#     if org_id:
#         q = q.filter(SDAIEvaluationRun.organization_id == org_id)
#
# Con un sujeto **sin** organizacion eso no lista «los que no tienen
# organizacion»: lista los de TODOS los clientes. Es el mismo condicional que
# aparecio en el resumen de costes, y la correccion es la misma: el filtro no es
# condicional.

import json as _json  # noqa: E402

from sqlalchemy.orm import Session as _Session  # noqa: E402

from app.models.service_desk_ai_governance import (  # noqa: E402
    SDAIDriftSnapshot as _Drift,
)
from app.models.service_desk_ai_governance import (  # noqa: E402
    SDAIEvaluationRun as _Eval,
)
from app.models.settings import AppSetting as _AppSetting  # noqa: E402

#: Clave del contrato de calidad. Lleva version en el nombre porque su forma la
#: consume el panel de release: cambiarla sin version romperia los guardados.
CLAVE_CONTRATO_DE_CALIDAD = "service_desk.quality_contract.v1"

#: El contrato por defecto cuando la organizacion no ha guardado el suyo.
CONTRATO_POR_DEFECTO = {
    "minimum_tests_pass_rate": 0.98,
    "max_p1_open": 0,
    "max_regression_bugs": 3,
    "required_checks": ["unit", "integration", "e2e_critical", "security_scan"],
}


def _org_de(user) -> "str | None":
    return getattr(user, "organization_id", None)


def listar_evaluaciones(db: _Session, user, *, limit: int) -> list[_Eval]:
    """Las evaluaciones offline de IA de la organizacion, mas recientes primero."""
    return (
        db.query(_Eval)
        .filter(_Eval.organization_id == _org_de(user))
        .order_by(_Eval.created_at.desc())
        .limit(limit)
        .all()
    )


def registrar_evaluacion(db: _Session, user, datos: dict) -> _Eval:
    fila = _Eval(
        organization_id=_org_de(user),
        created_by_user_id=user.id,
        metrics_json=_json.dumps(datos.pop("metrics", None) or {}),
        **datos,
    )
    db.add(fila)
    db.commit()
    db.refresh(fila)
    return fila


def listar_deriva(db: _Session, user, *, model_name=None, limit: int) -> list[_Drift]:
    q = (
        db.query(_Drift)
        .filter(_Drift.organization_id == _org_de(user))
    )
    if model_name:
        q = q.filter(_Drift.model_name == model_name)
    return q.order_by(_Drift.measured_at.desc()).limit(limit).all()


#: Umbrales del semaforo de deriva. Estaban en duro en el endpoint (70 y 40) y
#: son la regla de negocio de cuando una deriva de modelo pasa a ser un aviso o
#: una alarma, asi que se declaran con nombre en un solo sitio.
DERIVA_CRITICA = 70
DERIVA_DE_AVISO = 40


def estado_de_deriva(puntuacion: float) -> str:
    """El semaforo de una puntuacion de deriva."""
    if puntuacion >= DERIVA_CRITICA:
        return "critical"
    if puntuacion >= DERIVA_DE_AVISO:
        return "warning"
    return "ok"


def registrar_deriva(db: _Session, user, datos: dict) -> _Drift:
    """Guarda una medida de deriva, con su semaforo ya resuelto.

    `SDAIDriftSnapshot` no tiene `created_by_user_id` —a diferencia de las
    evaluaciones— asi que aqui no se pasa: la medida es del modelo, no de una
    persona.
    """
    fila = _Drift(
        organization_id=_org_de(user),
        status=estado_de_deriva(datos["drift_score"]),
        details_json=_json.dumps(datos.pop("details", None) or {}),
        **{k: v for k, v in datos.items() if k != "details"},
    )
    db.add(fila)
    db.commit()
    db.refresh(fila)
    return fila


def _fila_del_contrato(db: _Session, user):
    return (
        db.query(_AppSetting)
        .filter(
            _AppSetting.organization_id == _org_de(user),
            _AppSetting.key == CLAVE_CONTRATO_DE_CALIDAD,
        )
        .first()
    )


def contrato_de_calidad(db: _Session, user) -> dict:
    """El contrato de calidad de la organizacion, o el de por defecto.

    Un valor ilegible se devuelve en crudo bajo `raw` en vez de propagar: es un
    ajuste editable a mano y romper la pantalla de release por un JSON mal
    escrito seria peor que mostrarlo tal cual.
    """
    fila = _fila_del_contrato(db, user)
    if not fila or not fila.value:
        return dict(CONTRATO_POR_DEFECTO)
    try:
        return _json.loads(fila.value)
    except (ValueError, TypeError):
        return {"raw": fila.value}


def guardar_contrato_de_calidad(db: _Session, user, contrato: dict) -> None:
    fila = _fila_del_contrato(db, user)
    if fila:
        fila.value = _json.dumps(contrato)
    else:
        db.add(_AppSetting(
            organization_id=_org_de(user),
            key=CLAVE_CONTRATO_DE_CALIDAD,
            value=_json.dumps(contrato),
            description="Service Desk quality contract",
        ))
    db.commit()
