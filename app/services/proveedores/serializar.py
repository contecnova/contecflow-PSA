"""Respuestas JSON de `/suppliers` (una sola forma por entidad)."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from app.core import timeutil


def estado_de_documento(d, hoy: Optional[date] = None, dias_aviso: int = 30) -> str:
    hoy = hoy or timeutil.today()
    if d.expires_at is None:
        return "valid"
    if d.expires_at < hoy:
        return "expired"
    if d.expires_at <= hoy + timedelta(days=dias_aviso):
        return "expiring"
    return "valid"


def _f(v):
    return str(v) if v is not None else None


def _dt(v):
    return v.isoformat() if v is not None else None


def contrato(c, lineas: bool = True) -> dict:
    d = {
        "id": c.id, "subcontractor_id": c.subcontractor_id, "is_template": bool(c.is_template),
        "code": c.code, "title": c.title, "contract_type": c.contract_type, "modes": c.modes or [],
        "status": c.status, "start_date": _f(c.start_date), "end_date": _f(c.end_date),
        "auto_renew": bool(c.auto_renew), "notice_days": c.notice_days, "currency": c.currency,
        "committed_minimum": c.committed_minimum, "minimum_period": c.minimum_period, "total_cap": c.total_cap,
        "po_number": c.po_number, "po_amount": c.po_amount, "budget_id": c.budget_id, "project_id": c.project_id,
        "cost_center_id": c.cost_center_id, "payment_terms_days": c.payment_terms_days,
        "expenses_rebillable": bool(c.expenses_rebillable), "expenses_cap": c.expenses_cap,
        "internal_owner_id": c.internal_owner_id, "document_url": c.document_url, "notes": c.notes,
        "terminated_at": _f(c.terminated_at), "created_at": _dt(c.created_at),
    }
    if lineas:
        d["lines"] = [linea(x) for x in (c.lines or []) if x.is_active is not False]
    return d


def linea(x) -> dict:
    return {
        "id": x.id, "contract_id": x.contract_id, "model": x.model, "unit": x.unit, "description": x.description,
        "rate_id": x.rate_id, "rate_description": x.rate.description if getattr(x, "rate", None) else None,
        "service_id": x.service_id, "work_package_id": x.work_package_id, "unit_price": x.unit_price,
        "period": x.period, "included_units": x.included_units, "overage_price": x.overage_price,
        "tiers": x.tiers or [], "min_amount": x.min_amount, "max_amount": x.max_amount,
        "valid_from": _f(x.valid_from), "valid_until": _f(x.valid_until), "is_active": x.is_active is not False,
    }


def servicio(s) -> dict:
    return {
        "id": s.id, "subcontractor_id": s.subcontractor_id, "contract_id": s.contract_id,
        "service_type": s.service_type, "name": s.name, "scope": s.scope, "status": s.status,
        "start_date": _f(s.start_date), "end_date": _f(s.end_date), "agent_group_id": s.agent_group_id,
        "service_item_id": s.service_item_id, "alm_contract_id": s.alm_contract_id,
        "sla_response_hours": s.sla_response_hours, "sla_resolution_hours": s.sla_resolution_hours,
        "sla_target_pct": s.sla_target_pct, "kpis": s.kpis or [], "contracted_units": s.contracted_units,
        "unit": s.unit, "reporting_frequency": s.reporting_frequency, "credit_rules": s.credit_rules or [],
        "bonus_rules": s.bonus_rules or [], "internal_owner_id": s.internal_owner_id, "notes": s.notes,
        # Migracion 191: fuente de medicion (`medicion`).
        "metering_source": getattr(s, "metering_source", None) or "manual",
        "metering_config": getattr(s, "metering_config", None) or {},
        "metering_last_at": _dt(getattr(s, "metering_last_at", None)),
        "metering_last_quantity": getattr(s, "metering_last_quantity", None),
        "metering_last_error": getattr(s, "metering_last_error", None),
    }


def paquete(w, tareas: int | None = None) -> dict:
    return {
        "id": w.id, "subcontractor_id": w.subcontractor_id, "contract_id": w.contract_id,
        "project_id": w.project_id, "project_name": w.project.name if getattr(w, "project", None) else None,
        "scope_type": w.scope_type, "phase_id": w.phase_id, "milestone_id": w.milestone_id,
        "deliverable_id": w.deliverable_id, "uat_session_id": w.uat_session_id, "title": w.title,
        "description": w.description, "acceptance_criteria": w.acceptance_criteria, "status": w.status,
        "planned_start": _f(w.planned_start), "planned_end": _f(w.planned_end),
        "delivered_at": _f(w.delivered_at), "accepted_at": _f(w.accepted_at), "accepted_by": w.accepted_by,
        "rejection_reason": w.rejection_reason, "rejections": w.rejections or 0, "price": w.price,
        "currency": w.currency, "progress_pct": w.progress_pct, "last_report_at": _f(w.last_report_at),
        "internal_owner_id": w.internal_owner_id, "task_count": tareas,
    }


def informe(r) -> dict:
    return {
        "id": r.id, "subcontractor_id": r.subcontractor_id, "work_package_id": r.work_package_id,
        "service_id": r.service_id, "period_start": _f(r.period_start), "period_end": _f(r.period_end),
        "progress_pct": r.progress_pct, "summary": r.summary, "kpi_values": r.kpi_values or {},
        "risks": r.risks, "report_type": getattr(r, "report_type", None) or "progress",
        "attachments": getattr(r, "attachments", None) or [], "submitted_via": getattr(r, "submitted_via", None) or "internal",
        "status": r.status, "submitted_by": r.submitted_by, "reviewed_by": r.reviewed_by,
        "reviewed_at": _dt(r.reviewed_at), "review_notes": r.review_notes, "created_at": _dt(r.created_at),
    }


def consumo(u) -> dict:
    return {
        "id": u.id, "subcontractor_id": u.subcontractor_id, "contract_id": u.contract_id,
        "pricing_line_id": u.pricing_line_id, "service_id": u.service_id, "project_id": u.project_id,
        "period_start": _f(u.period_start), "period_end": _f(u.period_end), "unit": u.unit,
        "quantity": u.quantity, "amount": u.amount, "source": u.source, "description": u.description,
        "statement_id": u.statement_id, "created_at": _dt(u.created_at),
        "detail": getattr(u, "detail", None) or {}, "source_system": getattr(u, "source_system", None),
    }


def estado_de_cuenta(s) -> dict:
    return {
        "id": s.id, "subcontractor_id": s.subcontractor_id, "contract_id": s.contract_id,
        "contract_title": s.contract.title if getattr(s, "contract", None) else None,
        "period_start": _f(s.period_start), "period_end": _f(s.period_end), "currency": s.currency,
        "lines": s.lines or [], "subtotal": s.subtotal, "credits": s.credits, "bonus": s.bonus,
        "adjustments": s.adjustments, "expected_amount": s.expected_amount, "status": s.status,
        "invoice_id": s.invoice_id, "invoice_amount": s.invoice_amount, "difference": s.difference,
        "difference_pct": s.difference_pct, "dispute_reason": s.dispute_reason, "closed_by": s.closed_by,
        "approved_by": s.approved_by, "approved_at": _dt(s.approved_at), "created_at": _dt(s.created_at),
        "approval_request_id": getattr(s, "approval_request_id", None),
    }


def documento(d, hoy=None) -> dict:
    return {
        "id": d.id, "subcontractor_id": d.subcontractor_id, "doc_type": d.doc_type, "reference": d.reference,
        "issuer": d.issuer, "issued_at": _f(d.issued_at), "expires_at": _f(d.expires_at),
        "coverage_amount": d.coverage_amount, "document_url": d.document_url, "notes": d.notes,
        "verified_by": d.verified_by, "verified_at": _dt(d.verified_at), "status": estado_de_documento(d, hoy),
    }


def evaluacion(a) -> dict:
    return {
        "id": a.id, "subcontractor_id": a.subcontractor_id, "assessed_at": _f(a.assessed_at),
        "assessed_by": a.assessed_by, "criteria": a.criteria or {}, "score": a.score, "level": a.level,
        "next_review_date": _f(a.next_review_date), "due_diligence_done": bool(a.due_diligence_done),
        "notes": a.notes,
    }


def acceso(g) -> dict:
    return {
        "id": g.id, "subcontractor_id": g.subcontractor_id, "worker_id": g.worker_id, "system": g.system,
        "data_category": g.data_category, "access_level": g.access_level, "personal_data": bool(g.personal_data),
        "justification": g.justification, "granted_at": _f(g.granted_at), "granted_by": g.granted_by,
        "expires_at": _f(g.expires_at), "revoked_at": _f(g.revoked_at), "revoked_by": g.revoked_by,
        "revoke_reason": g.revoke_reason, "active": g.revoked_at is None,
    }


def clasificacion(s) -> dict:
    """Campos nuevos de la ficha (se anaden a `serialize_subcontractor`)."""
    return {
        "kind": s.kind or "company", "engagement_modes": s.engagement_modes or [],
        "lifecycle_status": s.lifecycle_status or "active", "freelancer_worker_id": s.freelancer_worker_id,
        "alm_vendor_id": s.alm_vendor_id, "internal_owner_id": s.internal_owner_id, "legal_name": s.legal_name,
        "website": s.website, "address": s.address, "training_enabled": bool(s.training_enabled),
        "data_access": bool(s.data_access), "data_categories": s.data_categories,
        "systems_access": s.systems_access, "risk_level": s.risk_level, "risk_score": s.risk_score,
        "next_review_date": _f(s.next_review_date), "suspended_at": _f(s.suspended_at),
        "offboarded_at": _f(s.offboarded_at), "offboarding_reason": s.offboarding_reason,
    }
