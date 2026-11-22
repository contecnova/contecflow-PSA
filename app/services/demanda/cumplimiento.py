"""Controles del flujo de demanda en el informe de cumplimiento.

- `demand_committee_bypass`: vías rápidas o saltos con justificación en los
  últimos 90 días (información para el auditor; «atención» si alguno no la tiene).
- `demand_stalled`: expedientes abiertos con el plazo de su fase vencido.
- `demand_decisions_without_justification`: rechazos, devoluciones, peticiones
  de información, esperas, saltos o bypass sin justificación (debe ser 0: el
  motor la exige, así que cualquier fila es una anomalía).
- `demand_log_integrity`: la cadena de hashes del log de cada expediente.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.demanda.definicion import CON_JUSTIFICACION


def controles(db, org, _control) -> list:
    from app.models.demanda import DemandRequest, DemandTransition
    from app.services.demanda.motor import ABIERTOS, estado_del_plazo, verificar_cadena
    desde = datetime.now(timezone.utc) - timedelta(days=90)
    bypass = db.query(DemandTransition).filter(DemandTransition.organization_id == org,
                                               DemandTransition.is_bypass.is_(True),
                                               DemandTransition.created_at >= desde).all()
    sin_motivo = [t for t in bypass if not (t.justification or "").strip()]
    abiertos = db.query(DemandRequest).filter(DemandRequest.organization_id == org,
                                              DemandRequest.status.in_(ABIERTOS)).all()
    vencidos = [r for r in abiertos if estado_del_plazo(r) == "breached"]
    sin_just = db.query(DemandTransition).filter(
        DemandTransition.organization_id == org,
        DemandTransition.decision.in_(CON_JUSTIFICACION),
        (DemandTransition.justification.is_(None)) | (DemandTransition.justification == "")).count()
    rotos = [r.code for r in db.query(DemandRequest).filter(DemandRequest.organization_id == org)
             .order_by(DemandRequest.created_at.desc()).limit(500).all() if not verificar_cadena(db, r)]
    return [
        _control("demand_committee_bypass", "attention" if sin_motivo else "info",
                 {"bypass_90d": len(bypass), "without_justification": len(sin_motivo)},
                 "demand_transitions con is_bypass (vía rápida con umbrales superados o fase saltada), 90 días",
                 ("ISO27001 A.5.4", "COBIT BAI02")),
        _control("demand_stalled", "pass" if not vencidos else "attention",
                 {"open": len(abiertos), "sla_breached": len(vencidos),
                  "codes": [r.code for r in vencidos[:20]]},
                 "demand_requests abiertos con sla_due_at vencido (sin contar pausas por información pendiente)",
                 ("ISO20000 8.2", "COBIT BAI02")),
        _control("demand_decisions_without_justification", "pass" if sin_just == 0 else "attention",
                 {"count": sin_just}, "demand_transitions de rechazo, devolución, información, espera o salto "
                                      "sin justificación", ("ISO27001 A.5.4",)),
        _control("demand_log_integrity", "pass" if not rotos else "attention",
                 {"broken_chains": len(rotos), "codes": rotos[:20]},
                 "hash encadenado de demand_transitions por expediente (últimos 500)", ("ISO27001 A.8.15",)),
    ]
