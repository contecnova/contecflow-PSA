"""Series de gobierno y automatizacion: playbooks, aprobaciones, flujos, SoD, GRC e importaciones.

Parte de `app.services.bi_smart_alerts.metrics` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from app.services.bi_smart_alerts.metrics._contexto import _Ctx, logger


def _serie_playbook(ctx: _Ctx) -> Optional[list[float]]:
    """Metricas que comparten consulta:

    · playbook_success_count
    · playbook_failure_count
    """
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key in ("playbook_success_count","playbook_failure_count"):
        try:
            from app.models.service_desk import AutonomousPlaybook
            from sqlalchemy import func as sqf
            field = AutonomousPlaybook.success_count if metric_key=="playbook_success_count" else AutonomousPlaybook.failure_count
            v = db.query(sqf.sum(field)).scalar() or 0
            return _current(float(v))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_pending_approvals(ctx: _Ctx) -> Optional[list[float]]:
    """Metricas que comparten consulta:

    · pending_approvals
    · approvals_approved_count
    · approvals_rejected_count
    """
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key in ("pending_approvals","approvals_approved_count","approvals_rejected_count"):
        try:
            from app.models.billing_reports import ApprovalRequest
            STATUS = {"pending_approvals":"pending","approvals_approved_count":"approved","approvals_rejected_count":"rejected"}
            return _current(float(db.query(ApprovalRequest).filter(
                ApprovalRequest.status == STATUS[metric_key]
            ).count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_workflow(ctx: _Ctx) -> Optional[list[float]]:
    """Metricas que comparten consulta:

    · workflow_runs_total
    · workflow_success_total
    · workflow_error_total
    """
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key in ("workflow_runs_total","workflow_success_total","workflow_error_total"):
        try:
            from app.models.billing_reports import AutomationWorkflow
            from sqlalchemy import func as sqf
            FIELD = {"workflow_runs_total": AutomationWorkflow.run_count,
                     "workflow_success_total": AutomationWorkflow.success_count,
                     "workflow_error_total": AutomationWorkflow.error_count}
            v = db.query(sqf.sum(FIELD[metric_key])).scalar() or 0
            return _current(float(v))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_sod_violations(ctx: _Ctx) -> Optional[list[float]]:
    """Metricas que comparten consulta:

    · sod_violations_total
    · sod_violations_unresolved
    """
    _current, _empty_like, db, metric_key, organization_id = ctx.current, ctx.empty_like, ctx.db, ctx.key, ctx.org_id
    if metric_key in ("sod_violations_total","sod_violations_unresolved"):
        try:
            from app.models.billing_reports import SodViolation
            q = db.query(SodViolation)
            if metric_key == "sod_violations_unresolved":
                q = q.filter(SodViolation.resolved == False)
            return _current(float(q.count()))
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_grc(ctx: _Ctx) -> Optional[list[float]]:
    """Metricas que comparten consulta:

    · grc_audit_events_total
    · grc_critical_events
    """
    _empty_like, db, metric_key, organization_id, series, start_date = ctx.empty_like, ctx.db, ctx.key, ctx.org_id, ctx.series, ctx.start_date
    if metric_key in ("grc_audit_events_total","grc_critical_events"):
        try:
            from app.models.billing_reports import GrcAuditLog
            rows = db.query(GrcAuditLog.timestamp, GrcAuditLog.severity).filter(
                GrcAuditLog.timestamp >= start_date
            ).all()
            bkt: dict[str,float] = defaultdict(float)
            for ts, sev in rows:
                if ts:
                    if metric_key == "grc_audit_events_total":
                        bkt[f"{ts.year:04d}-{ts.month:02d}"] += 1.0
                    elif sev == "critical":
                        bkt[f"{ts.year:04d}-{ts.month:02d}"] += 1.0
            return [float(bkt.get(m["month"],0.0)) for m in series]
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()

def _serie_imports(ctx: _Ctx) -> Optional[list[float]]:
    """Metricas que comparten consulta:

    · imports_completed_count
    · imports_failed_count
    · imports_success_rate
    """
    _empty_like, db, metric_key, organization_id, series, start_date = ctx.empty_like, ctx.db, ctx.key, ctx.org_id, ctx.series, ctx.start_date
    if metric_key in ("imports_completed_count","imports_failed_count","imports_success_rate"):
        try:
            from app.models.billing_reports import ImportJob
            rows = db.query(ImportJob.completed_at, ImportJob.status,
                            ImportJob.succeeded, ImportJob.total_rows).filter(
                ImportJob.completed_at >= start_date
            ).all()
            bkt: dict[str,float] = defaultdict(float)
            bkt_ok: dict[str,float] = defaultdict(float)
            bkt_tot: dict[str,float] = defaultdict(float)
            for ca, st, ok, tot in rows:
                if not ca: continue
                k = f"{ca.year:04d}-{ca.month:02d}"; sv = str(getattr(st,"value",st))
                if metric_key == "imports_completed_count" and sv == "completed":
                    bkt[k] += 1.0
                elif metric_key == "imports_failed_count" and sv in ("failed","partial"):
                    bkt[k] += 1.0
                elif metric_key == "imports_success_rate":
                    bkt_ok[k] += float(ok or 0); bkt_tot[k] += float(tot or 0)
            if metric_key == "imports_success_rate":
                return [round(bkt_ok[m["month"]]/bkt_tot[m["month"]]*100,2)
                        if bkt_tot.get(m["month"],0)>0 else 0.0 for m in series]
            return [float(bkt.get(m["month"],0.0)) for m in series]
        except Exception:
            logger.debug("Failed to fetch metric %s for org=%s", metric_key, organization_id, exc_info=True)
            return _empty_like()
