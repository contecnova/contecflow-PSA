"""Controles del informe de cumplimiento del índice de riesgo (§11.11 del diseño).

- ``sw_risk_index``: índice de la empresa frente al umbral de avisos
  (`alerts.index_above`) o, sin él, `RISK_LEVEL_HIGH`.
- ``sw_kev_open``: hallazgos críticos o altos explotados (KEV o con intentos)
  vivos y sin excepción.
- ``sw_mitigations_expired``: controles compensatorios caducados cuyo hallazgo
  sigue vivo (y sin otro control activo).
"""
from __future__ import annotations

from datetime import date


def controles(db, org, _control) -> list[dict]:
    from app.models.cmdb_riesgo import CompensatingControl
    from app.models.cmdb_software import SoftwareProduct, Vulnerability, VulnerabilityFinding
    from app.services.cmdb_software.correlacion import VIVOS
    from app.services.cmdb_software.riesgo import calculo as calc
    salida = []
    productos = db.query(SoftwareProduct.id).filter(SoftwareProduct.organization_id == org).first() is not None
    ctx = calc.contexto(db, org)
    idx = calc.indice(calc.filtrar(ctx, "org", ""), ctx.conf)
    umbral = ctx.conf["alerts"].get("index_above")
    if umbral is None:
        from app.core.umbrales import umbral as leer_umbral
        try:
            umbral = leer_umbral("RISK_LEVEL_HIGH", db, org)
        except Exception:  # noqa: BLE001 - sin el ajuste, el de fábrica
            umbral = 50.0
    salida.append(_control(
        "sw_risk_index", "info" if not productos else ("pass" if idx["score"] <= umbral else "attention"),
        {"score": idx["score"], "threshold": umbral, "accepted_score": idx["accepted_score"],
         "target": ctx.conf["target"]},
        "índice de riesgo de la empresa (sw_findings, deriva, fin de vida, sw_exploit_events) frente al umbral",
        ("ISO27001 A.5.7", "ISO27001 A.8.8", "NIS2 art. 21.2.a")))
    explotados = (db.query(VulnerabilityFinding).join(Vulnerability, Vulnerability.id == VulnerabilityFinding.vulnerability_id)
                  .filter(VulnerabilityFinding.organization_id == org,
                          VulnerabilityFinding.status.in_(tuple(s for s in VIVOS if s != "accepted")),
                          VulnerabilityFinding.severity.in_(("critical", "high")),
                          (Vulnerability.kev.is_(True)) | (VulnerabilityFinding.exploit_attempts > 0)).count())
    salida.append(_control(
        "sw_kev_open", "info" if not productos else ("pass" if explotados == 0 else "attention"),
        {"exploited_critical_high_open": explotados},
        "sw_findings críticos/altos vivos sin excepción con KEV o exploit_attempts > 0",
        ("ISO27001 A.8.8", "ENS op.exp.4", "NIS2 art. 21.2.e")))
    hoy = date.today()
    activos = {c.finding_id for c in db.query(CompensatingControl).filter(
        CompensatingControl.organization_id == org, CompensatingControl.status == "active",
        CompensatingControl.expires_at >= hoy)}
    caducados = (db.query(CompensatingControl).join(VulnerabilityFinding,
                                                    VulnerabilityFinding.id == CompensatingControl.finding_id)
                 .filter(CompensatingControl.organization_id == org,
                         (CompensatingControl.status == "expired") | ((CompensatingControl.status == "active")
                                                                      & (CompensatingControl.expires_at < hoy)),
                         VulnerabilityFinding.status.in_(VIVOS)).all())
    sin_cubrir = {c.finding_id for c in caducados if c.finding_id not in activos}
    salida.append(_control(
        "sw_mitigations_expired", "pass" if not sin_cubrir else "attention",
        {"expired_controls_open_findings": len(sin_cubrir), "active_controls": len(activos)},
        "sw_compensating_controls caducados con el hallazgo vivo y sin otro control activo",
        ("ISO27001 A.5.36", "ISO27001 A.8.8", "SOC2 CC7.1")))
    return salida
