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
  5. (retirada el 23-11-2026: `get_executive_dashboard` no tenía llamantes).
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

from typing import Optional

from app.models.service_desk._enums import ESTADOS_DE_PROBLEMA_RESUELTOS, ESTADOS_DE_TICKET_CERRADOS
from app.models.service_desk import (
    ITSMChangeRequest,
    ChangeStatus,
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


_CMM_NIVELES = (1, 2, 3, 4, 5)


def _g(db: Session, clave: str, **datos) -> str:
    """Texto del informe en el idioma de la empresa del contexto (`gov.*` en `textos_de_salida`)."""
    from app.services.textos_de_salida import texto_para
    return texto_para(db, clave, org_id=db.info.get("organization_id"), **datos)


def _cmm_label(db: Session, nivel: int) -> str:
    return _g(db, f"gov.cmm.{nivel}")


# ── Incident management audit ─────────────────────────────────────────────────

def _hallazgo_p1_sin_incidencia_mayor(db: Session, incidentes) -> tuple[int, Optional[dict]]:
    """P1 sin una incidencia mayor declarada. Devuelve `(penalización, hallazgo)`.

    Auditoría 2026-08/09. Esto preguntaba por `MajorIncident.tickets` detrás de
    un `hasattr`, y esa relación **no existía**: entre las dos entidades no
    había ni columna ni tabla de unión. El `hasattr` era correcto, así que la
    comprobación quedó declarada **no evaluable** — mejor eso que un falso
    positivo por cada P1.

    Desde la revisión 096 el enlace existe: `Ticket.major_incident_id`, con la
    decisión de cardinalidad dicha en voz alta —un ticket pertenece como mucho
    a UNA incidencia mayor, que es el modelo de ITIL y el conservador—. Así que
    esta comprobación vuelve a hacer su trabajo **sin tocar una línea de ella**.

    El `hasattr` se queda: un despliegue con la revisión 096 sin aplicar no debe
    reventar el informe de cumplimiento entero.
    """
    if not hasattr(MajorIncident, "tickets"):
        return 0, None

    p1 = [t for t in incidentes if t.priority == TicketPriority.p1_critical]
    sin_declarar = [
        t.number for t in p1
        if not db.query(MajorIncident).filter(
            MajorIncident.tickets.any(id=t.id)  # type: ignore[attr-defined]
        ).first()
    ]
    if not sin_declarar:
        return 0, None

    pct = round(len(sin_declarar) / max(len(p1), 1) * 100)
    return min(30, pct // 3), {
        "severity": "high" if pct >= 50 else "medium",
        "title": _g(db, "gov.inc.p1.titulo"),
        "count": len(sin_declarar),
        "details": _g(db, "gov.inc.p1.detalle", pct=pct, n=len(sin_declarar)),
        "sample": sin_declarar[:5],
    }


def _hallazgo_recurrentes_sin_problema(incidentes, db: Session) -> tuple[int, Optional[dict]]:
    """CIs con tres o más incidentes y ningún problema enlazado.

    Tres es el corte de ITIL para «esto ya no es casualidad»: a partir de ahí
    hay una causa raíz que alguien debería estar investigando.
    """
    por_ci: dict[str, list] = {}
    for t in incidentes:
        if t.ci_id:
            por_ci.setdefault(t.ci_id, []).append(t)

    recurrentes = [
        {"ci_id": ci_id, "incident_count": len(tickets)}
        for ci_id, tickets in por_ci.items()
        if len(tickets) >= 3 and not any(getattr(t, "problem_id", None) for t in tickets)
    ]
    if not recurrentes:
        return 0, None

    return min(20, len(recurrentes) * 4), {
        "severity": "medium",
        "title": _g(db, "gov.inc.recurrentes.titulo"),
        "count": len(recurrentes),
        "details": _g(db, "gov.inc.recurrentes.detalle", n=len(recurrentes)),
        "sample": recurrentes[:5],
    }


def _hallazgo_incumplimiento_de_sla(incidentes, db: Session) -> tuple[int, Optional[dict]]:
    """Tasa de incumplimiento de SLA por encima del 10 %.

    Sólo se miran los resueltos: un incidente abierto todavía puede cumplir.
    """
    resueltos = [t for t in incidentes if t.resolved_at]
    if not resueltos:
        return 0, None

    incumplidos = [t for t in resueltos if getattr(t, "sla_resolution_breached", False)]
    tasa = len(incumplidos) / len(resueltos)
    if tasa <= 0.10:
        return 0, None

    return min(20, int(tasa * 100) // 2), {
        "severity": "high" if tasa > 0.25 else "medium",
        "code": "sla_resolution_breach",
        "title": _g(db, "gov.inc.sla.titulo"),
        "count": len(incumplidos),
        "details": _g(db, "gov.inc.sla.detalle", tasa=round(tasa * 100, 1)),
    }


def audit_incident_management(db: Session, days: int = 30) -> dict:
    """Audita la gestión de incidentes de los últimos *days* días.

    Comprueba:
      - P1 sin incidencia mayor enlazada,
      - incidentes recurrentes del mismo CI (>3) sin problema enlazado,
      - tasa de incumplimiento de SLA en resolución.

    Devuelve::

        {
          "score": int (0-100),
          "findings": [{"severity", "title", "count", "details"}],
          "summary": str,
        }
    """
    desde = datetime.now(tz=timezone.utc) - timedelta(days=days)
    incidentes = (
        db.query(Ticket)
        .filter(Ticket.ticket_type == TicketType.incident, Ticket.created_at >= desde)
        .all()
    )

    score = 100
    findings = []
    for penalizacion, hallazgo in (
        _hallazgo_p1_sin_incidencia_mayor(db, incidentes),
        _hallazgo_recurrentes_sin_problema(incidentes, db),
        _hallazgo_incumplimiento_de_sla(incidentes, db),
    ):
        score -= penalizacion
        if hallazgo:
            findings.append(hallazgo)

    score = max(0, score)
    return {
        "score": score,
        "findings": findings,
        "summary": _g(db, "gov.resumen.incidentes", score=score, nivel=_cmm_level(score),
                      etiqueta=_cmm_label(db, _cmm_level(score)), n=len(incidentes), dias=days),
    }


# ── Change management audit ───────────────────────────────────────────────────

def audit_change_management(db: Session, days: int = 30) -> dict:
    """Audit change management practices.

    Checks:
      - Emergency changes without PIR
      - Normal changes approved without CAB record (`approved_by` missing or the requester)
      - Changes with high auto-risk score that were applied as standard
      - High rollback usage (pir_success = False rate)

    Returns same structure as audit_incident_management.
    """
    since = datetime.now(tz=timezone.utc) - timedelta(days=days)
    from app.core.umbrales import umbral as _umbral
    _riesgo_alto = _umbral("RISK_LEVEL_HIGH", db)

    changes = (
        db.query(ITSMChangeRequest)
        .filter(
            ITSMChangeRequest.created_at >= since,
            ITSMChangeRequest.status.in_([ChangeStatus.implemented, ChangeStatus.post_review,
                                          ChangeStatus.closed_success, ChangeStatus.closed_failed]),
        )
        .all()
    )

    findings = []
    score = 100

    # ── Finding 1: Emergency changes without PIR ──────────────────────────────
    emergency = [c for c in changes if c.change_type == ChangeType.emergency]
    # Migración 206 (docs/PIR.md): «con PIR» = una PIR aprobada o cerrada en `pir_revisiones`
    # (antes bastaba con texto en la columna `pir_notes`, que nadie rellenaba).
    from app.models.pir import PirRevision
    con_pir = {cid for (cid,) in db.query(PirRevision.change_id).filter(
        PirRevision.change_id.in_([c.id for c in emergency] or [""]),
        PirRevision.estado.in_(("aprobado", "cerrado"))).all()}
    emergency_no_pir = [c for c in emergency if c.id not in con_pir]
    if emergency_no_pir:
        pct = round(len(emergency_no_pir) / max(len(emergency), 1) * 100)
        score -= min(25, pct // 3)
        findings.append({
            "severity": "high" if pct >= 60 else "medium",
            "title": _g(db, "gov.chg.pir.titulo"),
            "count": len(emergency_no_pir),
            "details": _g(db, "gov.chg.pir.detalle", pct=pct),
            "sample": [c.number for c in emergency_no_pir[:5]],
        })

    # ── Finding 2: Normal changes without CAB approval ────────────────────────
    normal = [c for c in changes if c.change_type == ChangeType.normal]
    # Auditoria 2026-11-22 (C-SD5): se miraba `approver_id`, que nadie escribe
    # (el CAB y la decision del administrador escriben `approved_by`), asi que
    # el 100 % salia «sin CAB». Tampoco cuenta como aprobado el que aprobo el
    # propio solicitante.
    normal_no_cab = [c for c in normal
                     if not c.approved_by or c.approved_by == getattr(c, "requester_id", None)]
    if normal_no_cab:
        pct = round(len(normal_no_cab) / max(len(normal), 1) * 100)
        score -= min(20, pct // 4)
        findings.append({
            "severity": "high" if pct >= 40 else "medium",
            "title": _g(db, "gov.chg.cab.titulo"),
            "count": len(normal_no_cab),
            "details": _g(db, "gov.chg.cab.detalle", pct=pct),
            "sample": [c.number for c in normal_no_cab[:5]],
        })

    # ── Finding 3: Change failure rate ────────────────────────────────────────
    # 2026-11-22 (C-SD5): el estado es `closed_failed` (no "failed") y
    # `str(enum)` daba "ChangeStatus.x": la tasa de fallos salia siempre 0.
    failed = [c for c in changes if getattr(c.status, "value", c.status) == ChangeStatus.closed_failed.value]
    if changes:
        failure_rate = len(failed) / len(changes)
        if failure_rate > 0.10:
            penalty = min(20, int(failure_rate * 100) // 3)
            score -= penalty
            findings.append({
                "severity": "high" if failure_rate > 0.20 else "medium",
                "title": _g(db, "gov.chg.fallos.titulo"),
                "count": len(failed),
                "details": _g(db, "gov.chg.fallos.detalle", tasa=round(failure_rate * 100, 1)),
            })

    # ── Finding 4: Standard changes with high auto-risk ───────────────────────
    if hasattr(ITSMChangeRequest, "auto_risk_score"):
        high_risk_standard = [
            c for c in changes
            if c.change_type == ChangeType.standard
            # 19-11-2026: «alto» = RISK_LEVEL_HIGH de la empresa (antes 55 fijo).
            and getattr(c, "auto_risk_score", 0) and c.auto_risk_score >= _riesgo_alto
        ]
        if high_risk_standard:
            score -= min(15, len(high_risk_standard) * 3)
            findings.append({
                "severity": "medium",
                "title": _g(db, "gov.chg.estandar.titulo"),
                "count": len(high_risk_standard),
                "details": _g(db, "gov.chg.estandar.detalle", umbral=_riesgo_alto),
                "sample": [c.number for c in high_risk_standard[:5]],
            })

    score = max(0, score)
    summary = _g(db, "gov.resumen.cambios", score=score, nivel=_cmm_level(score),
                 etiqueta=_cmm_label(db, _cmm_level(score)), n=len(changes), dias=days)

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
            "title": _g(db, "gov.prob.rca.titulo"),
            "count": len(stale_no_rca),
            "details": _g(db, "gov.prob.rca.detalle", n=len(stale_no_rca)),
            "sample": [p.number for p in stale_no_rca[:5]],
        })

    # ── Finding 2: Auto-detected problems not reviewed ────────────────────────
    auto_detected = [p for p in problems if getattr(p, "auto_detected", False)]
    auto_no_review = [p for p in auto_detected if not p.root_cause and p.status not in (ProblemStatus.closed,)]
    if auto_no_review:
        score -= min(15, len(auto_no_review) * 3)
        findings.append({
            "severity": "medium",
            "title": _g(db, "gov.prob.auto.titulo"),
            "count": len(auto_no_review),
            "details": _g(db, "gov.prob.auto.detalle"),
        })

    score = max(0, score)
    summary = _g(db, "gov.resumen.problemas", score=score, nivel=_cmm_level(score),
                 etiqueta=_cmm_label(db, _cmm_level(score)), n=len(problems), dias=days)

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
                "title": _g(db, "gov.acc.pendientes.titulo"),
                "count": len(stale_access),
                "details": _g(db, "gov.acc.pendientes.detalle", n=len(stale_access), pct=pct),
                "sample": [t.number for t in stale_access[:5]],
            })
    except Exception as exc:
        logger.debug("Access ticket audit skipped: %s", exc)

    # ── Finding 2: Inactive users with active accounts ────────────────────────
    try:
        from app.models.user import User

        q_inactivos = db.query(User).filter(
            User.is_active.is_(True),
            User.last_login.isnot(None),
            User.last_login <= ninety_days_ago,
        )
        # Auditoria 2026-11-22 (servicios m-z, 4.3): solo las personas de la
        # empresa del informe, y la muestra con ids, no con correos: el informe
        # se guarda (`ComplianceReport`) y los correos quedaban en el sin
        # retencion propia.
        if db.info.get("organization_id"):
            q_inactivos = q_inactivos.filter(User.organization_id == db.info["organization_id"])
        inactive_users = q_inactivos.all()
        if inactive_users:
            score -= min(20, len(inactive_users) * 2)
            findings.append({
                "severity": "high" if len(inactive_users) > 10 else "medium",
                "title": _g(db, "gov.acc.inactivas.titulo"),
                "count": len(inactive_users),
                "details": _g(db, "gov.acc.inactivas.detalle", n=len(inactive_users)),
                "sample": [u.id for u in inactive_users[:5]],
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
                "title": _g(db, "gov.acc.privilegiados.titulo"),
                "count": len(unreviewed),
                "details": _g(db, "gov.acc.privilegiados.detalle", n=len(unreviewed)),
                "sample": [t.number for t in unreviewed[:5]],
            })
    except Exception as exc:
        logger.debug("Privileged access audit skipped: %s", exc)

    score = max(0, score)
    summary = _g(db, "gov.resumen.accesos", score=score, nivel=_cmm_level(score),
                 etiqueta=_cmm_label(db, _cmm_level(score)), dias=days)
    return {"score": score, "findings": findings, "summary": summary}


# ── Full compliance report ────────────────────────────────────────────────────

def _puntuacion_de_sla(auditoria_incidentes: dict) -> int:
    """La puntuación de SLA sale de los hallazgos de incidentes que lo mencionan.

    Tres puntos por incumplimiento, con suelo en cero: no es una fórmula fina,
    y por eso se reutiliza el hallazgo en vez de recontar — una sola fuente para
    el mismo dato.
    """
    puntuacion = 100
    for hallazgo in auditoria_incidentes["findings"]:
        if hallazgo.get("code") == "sla_resolution_breach":
            puntuacion = max(0, 100 - hallazgo["count"] * 3)
    return puntuacion


def _puntuacion_de_cmdb(db: Session) -> int:
    """El porcentaje de CIs descubiertos automáticamente.

    Sin CMDB, o si el módulo no está, se devuelve 50: ni bien ni mal. Poner 0
    penalizaría a quien no usa CMDB y 100 premiaría no tener datos.
    """
    try:
        from app.models.service_desk import ConfigurationItem as CI

        activos = db.query(func.count(CI.id)).filter(CI.is_active.is_(True))
        total = activos.scalar() or 0
        descubiertos = activos.filter(CI.is_discovered.is_(True)).scalar() or 0
        return round(descubiertos / total * 100) if total else 50
    except Exception:
        logger.warning("_puntuacion_de_cmdb: excepcion ignorada", exc_info=True)
        return 50


#: (dimensión, umbral, recomendación). Se emite la recomendación cuando la
#: puntuación de esa dimensión queda por debajo del umbral. Auditoría 2026-09
#: (hallazgo 18): eran seis `if` seguidos con el texto en línea.
_RECOMENDACIONES: tuple[tuple[str, int, str], ...] = (
    ("change_management", 70,
     "gov.rec.change_management"),
    ("incident_management", 70,
     "gov.rec.incident_management"),
    ("problem_management", 70,
     "gov.rec.problem_management"),
    ("sla_compliance", 80,
     "gov.rec.sla_compliance"),
    ("asset_cmdb", 60,
     "gov.rec.asset_cmdb"),
    ("access_reviews", 70,
     "gov.rec.access_reviews"),
)

#: Orden de gravedad para ordenar los hallazgos. Alfabéticamente `high` iría
#: después de `low`, que es justo al revés de lo que hace falta.
_ORDEN_DE_GRAVEDAD = {"high": 0, "medium": 1, "low": 2}


def generate_compliance_report(
    db: Session,
    days: int = 30,
    persist: bool = True,
) -> dict:
    """Informe de cumplimiento alineado con ITIL / ISO 20000.

    Corre todas las sub-auditorías, calcula la madurez ponderada y —si se pide—
    guarda el informe en ``sd_compliance_reports``.

    Devuelve::

        {
          "generated_at": str,
          "period_days": int,
          "overall_score": int,
          "cmm_level": int,
          "cmm_label": str,
          "dimensions": {nombre: {score, cmm_level, findings}},
          "top_findings": [los peores de todas las dimensiones],
          "recommendations": [str],
        }
    """
    # Problemas y accesos se miran en 90 días como mínimo: en una ventana de 30
    # apenas hay muestra y el resultado sería ruido.
    incidentes = audit_incident_management(db, days)
    cambios = audit_change_management(db, days)
    problemas = audit_problem_management(db, days=max(days, 90))
    accesos = audit_access_reviews(db, days=max(days, 90))

    dimensiones = {
        "incident_management": {"score": incidentes["score"], "findings": incidentes["findings"]},
        "change_management":   {"score": cambios["score"],    "findings": cambios["findings"]},
        "problem_management":  {"score": problemas["score"],  "findings": problemas["findings"]},
        "sla_compliance":      {"score": _puntuacion_de_sla(incidentes), "findings": []},
        "access_reviews":      {"score": accesos["score"],    "findings": accesos["findings"]},
        "asset_cmdb":          {"score": _puntuacion_de_cmdb(db), "findings": []},
    }
    for dim in dimensiones.values():
        dim["cmm_level"] = _cmm_level(dim["score"])
        dim["cmm_label"] = _cmm_label(db, dim["cmm_level"])

    global_ = round(sum(
        dimensiones[clave]["score"] * peso for clave, peso in _MATURITY_DIMENSIONS.items()
    ))

    hallazgos = [
        {**h, "dimension": nombre}
        for nombre, datos in dimensiones.items()
        for h in datos.get("findings", [])
    ]
    hallazgos.sort(key=lambda h: _ORDEN_DE_GRAVEDAD.get(h.get("severity", "low"), 2))

    report = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "period_days": days,
        "overall_score": global_,
        "cmm_level": _cmm_level(global_),
        "cmm_label": _cmm_label(db, _cmm_level(global_)),
        "dimensions": dimensiones,
        "top_findings": hallazgos[:10],
        "recommendations": [
            _g(db, texto) for dimension, umbral, texto in _RECOMENDACIONES
            if dimensiones[dimension]["score"] < umbral
        ],
    }

    if persist:
        _persist_compliance_report(db, report)

    return report


def _persist_compliance_report(db: Session, report: dict) -> None:
    """Guarda el informe en `sd_compliance_reports`.

    La organizacion la pone el sellado desde el contexto de la sesion: el
    worker lo genera una vez por organizacion (segunda auditoria 2026-11, #33;
    antes salia un unico informe de todas, con `organization_id` NULL). Un
    fallo al guardar se propaga: antes era un aviso y la tarea salia bien.
    """
    try:
        from app.models.service_desk import ComplianceReport
        rec = ComplianceReport(
            organization_id=db.info.get("organization_id"),
            id=str(uuid4()),
            generated_at=datetime.now(tz=timezone.utc),
            period_days=report["period_days"],
            overall_score=report["overall_score"],
            cmm_level=report["cmm_level"],
            report_json=json.dumps(report),
        )
        db.add(rec)
        db.commit()
    except Exception:
        db.rollback()
        logger.error("No se pudo guardar el informe de cumplimiento", exc_info=True)
        raise


# ── Executive dashboard ───────────────────────────────────────────────────────


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
            description=_g(db, "gov.contrato_calidad"),
        ))
    db.commit()
