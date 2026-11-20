"""Controles del informe de cumplimiento (`informe_de_cumplimiento.generar`).

- ``sw_critical_vulns_sla``: hallazgos críticos y altos abiertos fuera de SLA
  (atención si hay alguno; info si la empresa aún no tiene catálogo).
- ``sw_eol_production``: software sin soporte o en fin de vida en producción.
- ``sw_ci_without_owner``: CIs con software desplegado sin propietario, y
  software comprado, SaaS o propio sin propietario.
- ``sw_vuln_exceptions``: excepciones caducadas cuyo hallazgo sigue abierto y
  excepciones vigentes (el auditor ve cuántas y hasta cuándo).
- ``sw_vuln_feed``: antigüedad de la última sincronización de avisos
  (`not_measurable` si no hay ninguna fuente activa: se dice, no se inventa).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func


def controles(db, org, _control) -> list[dict]:
    from app.models.cmdb_software import (SoftwareInstance, SoftwareProduct, VulnerabilityException,
                                          VulnerabilityFinding)
    from app.models.service_desk.cmdb import ConfigurationItem
    from app.services.cmdb_software import ajustes
    from app.services.cmdb_software.analisis import fin_de_vida
    from app.services.cmdb_software.correlacion import VIVOS

    ahora = datetime.now(timezone.utc)
    salida = []
    productos = db.query(SoftwareProduct).filter(SoftwareProduct.organization_id == org,
                                                 SoftwareProduct.is_active.is_(True)).count()
    vivos = db.query(VulnerabilityFinding).filter(VulnerabilityFinding.organization_id == org,
                                                  VulnerabilityFinding.status.in_(VIVOS))
    graves = vivos.filter(VulnerabilityFinding.severity.in_(("critical", "high")),
                          VulnerabilityFinding.status != "accepted")
    fuera = graves.filter(VulnerabilityFinding.sla_due_at < ahora).count()
    salida.append(_control(
        "sw_critical_vulns_sla", "info" if not productos else ("pass" if fuera == 0 else "attention"),
        {"critical_high_open": graves.count(), "out_of_sla": fuera, "live_findings": vivos.count()},
        "sw_findings críticos/altos vivos con sla_due_at vencido (días por severidad de sw_config)",
        ("ISO27001 A.8.8", "SOC2 CC7.1", "ENS op.exp.4", "NIS2 art. 21.2.e")))
    eol = fin_de_vida(db, org, dias=0, solo_produccion=True)
    sin_soporte = [x for x in eol["instances"] if x["lifecycle"] in ("eol", "unsupported")]
    salida.append(_control(
        "sw_eol_production", "info" if not productos else ("pass" if not sin_soporte else "attention"),
        {"instances_eol": sum(1 for x in sin_soporte if x["lifecycle"] == "eol"),
         "instances_unsupported": sum(1 for x in sin_soporte if x["lifecycle"] == "unsupported"),
         "components_eol": eol["summary"]["eol"] - sum(1 for x in eol["instances"] if x["lifecycle"] == "eol")},
        "sw_instances en prod cuya versión (o rama) tiene eol_date/support_end pasado en sw_versions",
        ("ISO27001 A.8.8", "ISO27001 A.5.9", "ENS op.exp.1")))
    hosts = [c for (c,) in db.query(SoftwareInstance.ci_id).filter(
        SoftwareInstance.organization_id == org, SoftwareInstance.is_active.is_(True),
        SoftwareInstance.ci_id.isnot(None)).distinct()]
    cis_sin = db.query(ConfigurationItem).filter(ConfigurationItem.id.in_(hosts or [""]),
                                                 ConfigurationItem.owner_user_id.is_(None),
                                                 ConfigurationItem.is_active.is_(True)).count()
    prod_sin = db.query(SoftwareProduct).filter(SoftwareProduct.organization_id == org,
                                                SoftwareProduct.is_active.is_(True),
                                                SoftwareProduct.owner_user_id.is_(None),
                                                SoftwareProduct.origin.in_(("purchased", "saas", "in_house"))).count()
    salida.append(_control(
        "sw_ci_without_owner", "info" if not productos else ("pass" if cis_sin == 0 and prod_sin == 0 else "attention"),
        {"cis_with_software": len(hosts), "cis_without_owner": cis_sin, "applications_without_owner": prod_sin},
        "sd_configuration_items con sw_instances vivas sin owner_user_id + sw_products (comprado, SaaS, propio) sin propietario",
        ("ISO27001 A.5.9", "ISO27001 A.5.2")))
    hoy = ahora.date()
    exc = db.query(VulnerabilityException).filter(VulnerabilityException.organization_id == org)
    caducadas_abiertas = (exc.join(VulnerabilityFinding, VulnerabilityFinding.id == VulnerabilityException.finding_id)
                          .filter(VulnerabilityException.status == "expired",
                                  VulnerabilityFinding.status.in_(("open", "triaged", "in_progress"))).count())
    vigentes = exc.filter(VulnerabilityException.status == "approved", VulnerabilityException.expires_at >= hoy)
    sin_caducar = exc.filter(VulnerabilityException.status == "approved", VulnerabilityException.expires_at < hoy).count()
    salida.append(_control(
        "sw_vuln_exceptions", "pass" if caducadas_abiertas == 0 and sin_caducar == 0 else "attention",
        {"active": vigentes.count(), "pending": exc.filter(VulnerabilityException.status == "pending").count(),
         "expired_still_open": caducadas_abiertas, "approved_past_expiry": sin_caducar,
         "latest_expiry": (vigentes.with_entities(func.max(VulnerabilityException.expires_at)).scalar() or None)},
        "sw_vuln_exceptions (aprobadas con caducidad, segregación pedir/aprobar) y su hallazgo",
        ("ISO27001 A.5.36", "SOC2 CC3.4")))
    conf = ajustes.leer(db, org)
    activas = [f for f in ("osv", "nvd", "ghsa", "epss", "kev") if conf.get(f"{f}_enabled")]
    ultima = conf.get("last_sync_at")
    if not activas:
        salida.append(_control("sw_vuln_feed", "not_measurable" if productos else "info",
                               {"sources": [], "last_sync_at": ultima},
                               "sw_config: ninguna fuente de avisos activa (importación manual de ficheros)",
                               ("ISO27001 A.8.8",)))
    else:
        edad = None
        if ultima:
            momento = datetime.fromisoformat(ultima)
            if momento.tzinfo is None:   # la columna se guarda en UTC sin zona (SQLite y algunos drivers)
                momento = momento.replace(tzinfo=timezone.utc)
            edad = round((ahora - momento).total_seconds() / 86400, 1)
        salida.append(_control("sw_vuln_feed", "pass" if edad is not None and edad <= 7 else "attention",
                               {"sources": activas, "last_sync_at": ultima, "age_days": edad,
                                "status": conf.get("last_sync_status")},
                               "sw_config.last_sync_at (sincronización de avisos)", ("ISO27001 A.8.8", "ISO27001 A.5.7")))
    return salida


def _dias(n: int) -> timedelta:
    return timedelta(days=n)
