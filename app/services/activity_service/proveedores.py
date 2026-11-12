"""Cuadro de mando de proveedores: puntuaciones y ranking.

Parte de `app.services.activity_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.activity import VendorScore
from app.models.alm import ALMVendor
from app.core.errores import ErrorDeDominio


# ═══════════════════════════════════════════════════════════════════════════════
# VENDOR SCORECARD
# ═══════════════════════════════════════════════════════════════════════════════

def score_composite(s) -> float:
    scores = [
        s.sla_score, s.quality_score, s.support_score,
        s.price_score, s.innovation_score, s.compliance_score,
    ]
    weights = [0.25, 0.20, 0.20, 0.15, 0.10, 0.10]
    total_w = 0.0
    total = 0.0
    for sc, w in zip(scores, weights):  # noqa: B905
        if sc is not None:
            total += sc * w
            total_w += w
    return round(total / total_w, 2) if total_w > 0 else 0.0


def vendor_scorecard_payload(db: Session, vendor_id: str) -> dict:
    vendor = db.query(ALMVendor).filter(ALMVendor.id == vendor_id).first()
    if not vendor:
        raise ErrorDeDominio(404)
    scores = db.query(VendorScore).filter(
        VendorScore.vendor_id == vendor_id
    ).order_by(VendorScore.evaluated_at.desc()).all()
    return {
        "vendor_id": vendor_id,
        "vendor_name": vendor.name,
        "category": vendor.category.value if vendor.category else None,
        "evaluations": [{
            "id": s.id,
            "period": s.period,
            "composite_score": s.composite_score,
            "rating": ("Excelente" if (s.composite_score or 0) >= 8 else
                       "Bueno" if (s.composite_score or 0) >= 6 else
                       "Regular" if (s.composite_score or 0) >= 4 else "Deficiente"),
            "sla_score": s.sla_score,
            "quality_score": s.quality_score,
            "support_score": s.support_score,
            "price_score": s.price_score,
            "innovation_score": s.innovation_score,
            "compliance_score": s.compliance_score,
            "incidents_count": s.incidents_count,
            "notes": s.notes,
            "evaluated_at": s.evaluated_at.isoformat() if s.evaluated_at else None,
        } for s in scores],
        "latest_composite": scores[0].composite_score if scores else None,
        "trend": [{"period": s.period, "score": s.composite_score} for s in reversed(scores[-6:])],
    }


def add_vendor_score_record(db: Session, vendor_id: str, payload, current_user: User) -> dict:
    vendor = db.query(ALMVendor).filter(ALMVendor.id == vendor_id).first()
    if not vendor:
        raise ErrorDeDominio(404)
    for field in ["sla_score", "quality_score", "support_score", "price_score", "innovation_score", "compliance_score"]:
        v = getattr(payload, field, None)
        if v is not None and not (0 <= v <= 10):
            raise ErrorDeDominio(400, f"{field} must be 0-10")
    composite = score_composite(payload)
    score = VendorScore(
        vendor_id=vendor_id,
        evaluator_id=current_user.id,
        composite_score=composite,
        **payload.model_dump(),
    )
    db.add(score)
    db.commit()
    db.refresh(score)
    return {"id": score.id, "composite_score": composite}


def vendor_scorecard_ranking_payload(db: Session) -> list:
    subq = (
        db.query(VendorScore.vendor_id, func.max(VendorScore.evaluated_at).label("last_eval"))
        .group_by(VendorScore.vendor_id)
        .subquery()
    )
    latest = (
        db.query(VendorScore, ALMVendor)
        .join(ALMVendor, VendorScore.vendor_id == ALMVendor.id)
        .join(subq, (VendorScore.vendor_id == subq.c.vendor_id) & (VendorScore.evaluated_at == subq.c.last_eval))
        .all()
    )
    result = [{
        "vendor_id": vs.vendor_id,
        "vendor_name": v.name,
        "category": v.category.value if v.category else None,
        "period": vs.period,
        "composite_score": vs.composite_score,
        "rating": ("Excelente" if (vs.composite_score or 0) >= 8 else
                   "Bueno" if (vs.composite_score or 0) >= 6 else
                   "Regular" if (vs.composite_score or 0) >= 4 else "Deficiente"),
        "incidents_count": vs.incidents_count,
    } for vs, v in latest]
    result.sort(key=lambda x: -(x["composite_score"] or 0))
    return result
