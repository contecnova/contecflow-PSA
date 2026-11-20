"""Correlación: avisos × lo que la empresa tiene → hallazgos, prioridad y SLA.

**Ocurrencias** de un producto en una versión:

- cada instancia desplegada viva (no retirada): «nginx 1.18.0 en web-01»;
- cada componente de una versión de software: «lodash 4.17.20 dentro de
  Portal 2.3».

Una ocurrencia está afectada por un aviso si coincide el paquete (clave purl
del producto) **o** el CPE (fabricante:producto), y su versión cae en algún
rango del aviso (`versiones.en_rango`). Cada coincidencia es un hallazgo con
clave estable (`finding_key`), así que reevaluar no duplica.

**Ciclo automático**: lo que aparece se abre; lo que ya no aparece (se
actualizó o se quitó) se cierra como `resolved` y queda verificado por la
reevaluación (`verified_at`); lo que vuelve a aparecer se reabre. Lo marcado a
mano como falso positivo no se reabre.

**Prioridad** (0-100, con su desglose en `score_detail`)::

    base   = CVSS × 10 (sin CVSS: critical 90, high 70, medium 50, low 20, unknown 50)
    base  += 15 si está en KEV;  += EPSS × 20
    × criticidad (critical 1,0 · high 0,9 · medium 0,75 · low 0,6)  — la mayor de producto, instancia y CI
    × exposición (internet 1,0 · internal 0,8 · isolated 0,5)
    × entorno   (prod 1,0 · pre/dr 0,8 · test 0,6 · dev 0,5)

Para un componente, el contexto (entorno, exposición, criticidad) es el más
grave de las instancias del software que lo lleva.

**SLA**: ``first_seen_at`` + días de la severidad (`ajustes.sla_dias`; KEV
manda si es más corto).

**Versión desconocida** (``requirements.txt`` sin versión fija y sin lock en la
misma importación, ``pom.xml`` sin versión resoluble…): la ocurrencia no se
ignora. Cada aviso de ese paquete (o CPE) produce un hallazgo **posible**
(``score_detail.possible``): prioridad a la mitad y sin plazo de SLA (no
cuenta como fuera de SLA). Se confirma en el triaje, se descarta como falso
positivo o desaparece solo al conocerse la versión.

Los paquetes de distribución (deb, rpm, apk) solo casan por paquete, nunca por
CPE: las distribuciones parchean sin cambiar la versión de origen.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.cmdb_software import (SoftwareComponent, SoftwareInstance, SoftwareProduct, SoftwareVersion,
                                      Vulnerability, VulnerabilityAffect, VulnerabilityFinding)
from app.models.service_desk.cmdb import ConfigurationItem
from app.services.audit import audit_log
from app.services.cmdb_software import ajustes
from app.services.cmdb_software import identificadores as ids
from app.services.cmdb_software.versiones import en_rango, valida

ABIERTOS = ("open", "triaged", "in_progress", "mitigated")
#: Estados en los que el hallazgo sigue vivo (y la reevaluación lo puede cerrar).
VIVOS = ABIERTOS + ("accepted",)
CERRADOS = ("resolved", "false_positive")

_BASE_SEV = {"critical": 90, "high": 70, "medium": 50, "low": 20, "none": 0, "unknown": 50}
_CRIT = {"critical": 1.0, "high": 0.9, "medium": 0.75, "low": 0.6}
_EXPO = {"internet": 1.0, "internal": 0.8, "isolated": 0.5}
_ENTORNO = {"prod": 1.0, "pre": 0.8, "dr": 0.8, "test": 0.6, "dev": 0.5}
_ORDEN_CRIT = ("low", "medium", "high", "critical")
_ORDEN_EXPO = ("isolated", "internal", "internet")
_ORDEN_ENT = ("dev", "test", "pre", "dr", "prod")
ORDEN_SEV = {"critical": 4, "high": 3, "medium": 2, "unknown": 2, "low": 1, "none": 0}


def ahora() -> datetime:
    return datetime.now(timezone.utc)


def _q(db, modelo, org):
    q = db.query(modelo)
    return q.filter(modelo.organization_id == org) if org else q


def _max(valores, orden, defecto):
    vals = [v for v in valores if v in orden]
    return max(vals, key=orden.index) if vals else defecto


def prioridad(vuln: Vulnerability, criticidad: str, exposicion: str, entorno: str) -> tuple[float, dict]:
    base = float(vuln.cvss_score) * 10 if vuln.cvss_score is not None else float(_BASE_SEV.get(vuln.severity, 50))
    kev = 15.0 if vuln.kev else 0.0
    epss = round(float(vuln.epss_score or 0) * 20, 2)
    factores = {"criticality": _CRIT.get(criticidad, 0.75), "exposure": _EXPO.get(exposicion, 0.8),
                "environment": _ENTORNO.get(entorno, 1.0)}
    total = (base + kev + epss) * factores["criticality"] * factores["exposure"] * factores["environment"]
    total = round(min(100.0, max(0.0, total)), 1)
    return total, {"base": base, "kev": kev, "epss": epss, **factores, "criticality_level": criticidad,
                   "exposure_level": exposicion, "environment_level": entorno, "score": total}


def severidad_efectiva(vuln: Vulnerability) -> str:
    return vuln.severity if vuln.severity in ORDEN_SEV else "unknown"


def vencimiento(conf: dict, vuln: Vulnerability, desde: datetime) -> datetime:
    sev = severidad_efectiva(vuln)
    dias = ajustes.sla_dias(conf, "medium" if sev in ("unknown", "none") else sev)
    if vuln.kev:
        dias = min(dias, ajustes.sla_dias(conf, sev, kev=True))
    return desde + timedelta(days=dias)


class _Indice:
    """Avisos indexados por paquete y por CPE."""

    def __init__(self, db, org):
        self.por_paquete: dict[str, list] = {}
        self.por_cpe: dict[tuple, list] = {}
        vulns = {v.id: v for v in _q(db, Vulnerability, org).filter(Vulnerability.withdrawn_at.is_(None))}
        self.vulns = vulns
        for a in _q(db, VulnerabilityAffect, org):
            v = vulns.get(a.vulnerability_id)
            if v is None:
                continue
            if a.package_key:
                self.por_paquete.setdefault(a.package_key, []).append((v, a))
            if a.cpe_vendor and a.cpe_product:
                self.por_cpe.setdefault((a.cpe_vendor, a.cpe_product), []).append((v, a))

    def candidatos(self, p: SoftwareProduct) -> list[tuple]:
        """Avisos del paquete o del CPE del producto, sin mirar la versión.

        Los paquetes de distribución (deb, rpm, apk) solo casan por paquete: las
        distribuciones parchean sin cambiar la versión de origen y el rango de NVD
        (por CPE) daría falsos positivos.
        """
        salida = []
        if p.purl_name:
            salida += self.por_paquete.get(ids.clave_de_paquete(p.purl_type, p.purl_namespace, p.purl_name), [])
        if p.purl_type not in ("deb", "rpm", "apk"):
            for cpe in ids.cpes_de(p.name, p.cpe_vendor, p.cpe_product):
                salida += self.por_cpe.get(cpe, [])
        return salida

    def posibles(self, p: SoftwareProduct) -> list[tuple]:
        """Para una versión desconocida: un aviso por vulnerabilidad del paquete (posible afectado)."""
        salida, vistos = [], set()
        for v, a in self.candidatos(p):
            if v.id not in vistos:
                vistos.add(v.id)
                salida.append((v, a))
        return salida

    def afectan(self, p: SoftwareProduct, version: Optional[str]) -> list[tuple]:
        candidatos = self.candidatos(p)
        salida, vistos = [], set()
        for v, a in candidatos:
            exactas = json.loads(a.versions) if a.versions else None
            if en_rango(version, a.introduced, a.fixed, a.last_affected, a.introduced_inclusive, exactas):
                if v.id not in vistos:
                    vistos.add(v.id)
                    salida.append((v, a))
        return salida


def ocurrencias(db: Session, org) -> list[dict]:
    """Instancias vivas y componentes, con su contexto (entorno, exposición, criticidad, CI)."""
    prods = {p.id: p for p in _q(db, SoftwareProduct, org)}
    cis = {c.id: c for c in _q(db, ConfigurationItem, org)}
    instancias = [i for i in _q(db, SoftwareInstance, org).filter(SoftwareInstance.is_active.is_(True),
                                                                   SoftwareInstance.status != "retired")]
    por_version: dict[str, list[SoftwareInstance]] = {}
    for i in instancias:
        if i.version_id:
            por_version.setdefault(i.version_id, []).append(i)

    def contexto(lista: list[SoftwareInstance], prod: Optional[SoftwareProduct]) -> dict:
        crits = [prod.criticality if prod else None]
        for i in lista:
            crits.append(i.criticality)
            host = cis.get(i.ci_id)
            crits.append(host.criticality if host else None)
        return {"environment": _max([i.environment for i in lista], _ORDEN_ENT, "prod" if not lista else "dev"),
                "exposure": _max([i.exposure for i in lista], _ORDEN_EXPO, "internal"),
                "criticality": _max(crits, _ORDEN_CRIT, "medium")}

    salida = []
    for i in instancias:
        p = prods.get(i.product_id)
        if p is None:
            continue
        salida.append({"product": p, "version": i.version, "instance": i, "parent_version_id": None,
                       "component": None, **contexto([i], p)})
    versiones = {v.id: v for v in _q(db, SoftwareVersion, org)}
    for c in _q(db, SoftwareComponent, org):
        p = prods.get(c.component_product_id)
        padre = versiones.get(c.parent_version_id)
        if p is None or padre is None:
            continue
        salida.append({"product": p, "version": c.component_version, "instance": None,
                       "parent_version_id": c.parent_version_id, "component": c,
                       **contexto(por_version.get(c.parent_version_id, []), prods.get(padre.product_id))})
    return salida


def _clave(v: Vulnerability, oc: dict) -> str:
    ctx = f"i:{oc['instance'].id}" if oc["instance"] is not None else f"v:{oc['parent_version_id']}"
    return f"{v.id}|{oc['product'].id}|{oc['version'] or ''}|{ctx}"[:300]


def reevaluar(db: Session, org, usuario=None) -> dict:
    """Recalcula todos los hallazgos de la empresa. No confirma."""
    conf = ajustes.leer(db, org)
    indice = _Indice(db, org)
    existentes = {f.finding_key: f for f in _q(db, VulnerabilityFinding, org)}
    momento = ahora()
    vistos: set[str] = set()
    nuevos: list[VulnerabilityFinding] = []
    reabiertos = 0
    for oc in ocurrencias(db, org):
        # Versión desconocida (requirements sin «==», pom sin versión...): no se
        # ignora; se avisa como posible afectado, sin plazo de SLA y con la
        # prioridad a la mitad, hasta que se conozca la versión o se descarte.
        posible = not valida(oc["version"])
        pares = indice.posibles(oc["product"]) if posible else indice.afectan(oc["product"], oc["version"])
        for vuln, afecta in pares:
            clave = _clave(vuln, oc)
            if clave in vistos:
                continue
            vistos.add(clave)
            f = existentes.get(clave)
            puntos, detalle = prioridad(vuln, oc["criticality"], oc["exposure"], oc["environment"])
            if posible:
                puntos = round(puntos / 2, 1)
                detalle = {**detalle, "possible": True, "score": puntos, "reason": "unknown_version"}
            if f is None:
                f = VulnerabilityFinding(organization_id=org, finding_key=clave, vulnerability_id=vuln.id,
                                         product_id=oc["product"].id, affected_version=oc["version"],
                                         instance_id=oc["instance"].id if oc["instance"] is not None else None,
                                         parent_version_id=oc["parent_version_id"],
                                         component_id=oc["component"].id if oc["component"] is not None else None,
                                         status="open", first_seen_at=momento)
                db.add(f)
                existentes[clave] = f
                nuevos.append(f)
            elif f.status == "resolved":
                f.status, f.closed_at, f.verified_at, f.resolution = "open", None, None, None
                f.first_seen_at = momento
                reabiertos += 1
                audit_log(db, usuario, "UPDATE", "sw_finding", f.id, vuln.vuln_id,
                          old_values={"status": "resolved"}, new_values={"status": "open"},
                          metadata={"reason": "reappeared"})
            f.last_seen_at = momento
            f.severity = severidad_efectiva(vuln)
            f.priority_score, f.score_detail = puntos, json.dumps(detalle)
            f.environment, f.exposure = oc["environment"], oc["exposure"]
            f.fixed_version = afecta.fixed or f.fixed_version
            if f.status in VIVOS:
                f.sla_due_at = None if posible else vencimiento(conf, vuln, f.first_seen_at or momento)
    resueltos = 0
    for clave, f in existentes.items():
        if clave in vistos or f.status not in VIVOS:
            continue
        anterior = f.status
        f.status, f.closed_at, f.verified_at = "resolved", momento, momento
        f.resolution = f.resolution or "not_present"
        resueltos += 1
        audit_log(db, usuario, "UPDATE", "sw_finding", f.id, f.finding_key[:80],
                  old_values={"status": anterior}, new_values={"status": "resolved"},
                  metadata={"reason": "verified_by_rescan"})
    db.flush()
    return {"findings_new": len(nuevos), "findings_reopened": reabiertos, "findings_resolved": resueltos,
            "findings_live": sum(1 for f in existentes.values() if f.status in VIVOS),
            "new_ids": [f.id for f in nuevos]}


def reevaluar_y_registrar(db: Session, org, usuario=None, disparo: str = "manual") -> dict:
    from app.models.cmdb_software import VulnerabilitySyncRun
    r = VulnerabilitySyncRun(organization_id=org, source="correlate", triggered_by=disparo,
                             created_by=getattr(usuario, "id", None))
    db.add(r)
    db.flush()
    res = reevaluar(db, org, usuario)
    r.status, r.finished_at = "ok", ahora()
    r.findings_new, r.findings_resolved = res["findings_new"], res["findings_resolved"]
    db.flush()
    return res
