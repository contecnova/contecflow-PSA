"""Importación de terceros: Trend Vision One, Microsoft Defender VM, Qualys,
Tenable, Rapid7 y SIEM genérico (§11.9 del diseño).

**Conexiones**: son conexiones de escaneo (`escaneos.py`, `cmdb_discovery_providers`)
de tipo ``sw_vm_*`` y ``sw_siem``: configuración cifrada, programación e
historial heredados. `escaneos.ejecutar` delega aquí (`ejecutar_conexion`).

**Fichero**: `importar_fichero(fuente, contenido)` con las exportaciones JSON
de cada consola, XML de Qualys o el CSV común (`host, ip, cve, product, vendor,
version, fixed_version, severity, cvss, status, first_seen`).

Todo se normaliza a **detecciones** y `aplicar` las lleva a la CMDB:

1. CI por nombre, FQDN o IP (o se crea con la reconciliación si `create_cis`);
2. producto por la conciliación del catálogo (o «sin identificar (fuente)»);
3. instancia del producto en ese CI (versión observada);
4. aviso por su id (CVE; si no hay, ``QID-…``, ``TENABLE-…``…) sin pisar
   datos mejores;
5. hallazgo con **la misma clave que la correlación** → lo que detectan a la
   vez la correlación y el tercero es un solo hallazgo con
   ``detected_by = [correlation, <fuente>]``.

Con ``complete`` (importación completa), la fuente se quita de los hallazgos
que ya no informa; sin ninguna fuente viva, el hallazgo pasa a ``resolved``.

Las APIs se llaman por `_http` (sustituible en tests). **No se han probado
contra consolas reales**: los formatos son los públicos de cada API.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import re
from datetime import datetime, timezone
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import ErrorConCodigo, error
from app.core.config import settings
from app.services.audit import audit_log

logger = logging.getLogger(__name__)

FUENTES = ("trendmicro", "defender", "qualys", "tenable", "rapid7", "file")
TIPO_A_FUENTE = {"sw_vm_trendmicro": "trendmicro", "sw_vm_defender": "defender", "sw_vm_qualys": "qualys",
                 "sw_vm_tenable": "tenable", "sw_vm_rapid7": "rapid7"}
#: Campos de cada conexión (las secretas, con `*`): los usa `escaneos.CAMPOS`.
CAMPOS = {
    "sw_vm_trendmicro": ("url", "token*", "create_cis", "complete", "max_pages", "environment", "timeout"),
    "sw_vm_defender": ("url", "tenant_id", "client_id", "client_secret*", "create_cis", "complete", "max_pages",
                       "environment", "timeout"),
    "sw_vm_qualys": ("url", "username", "password*", "with_kb", "create_cis", "complete", "max_pages", "environment",
                     "timeout"),
    "sw_vm_tenable": ("url", "access_key*", "secret_key*", "create_cis", "complete", "max_pages", "environment",
                      "timeout"),
    "sw_vm_rapid7": ("url", "username", "password*", "create_cis", "complete", "max_pages", "environment", "timeout"),
    "sw_siem": ("url", "token*", "auth_header", "list_path", "cve_field", "host_field", "ip_field", "time_field",
                "action_field", "count_field", "id_field", "next_path", "max_pages", "days", "timeout"),
}
URLS = {"sw_vm_trendmicro": "https://api.xdr.trendmicro.com", "sw_vm_defender": "https://api.securitycenter.microsoft.com",
        "sw_vm_tenable": "https://cloud.tenable.com"}
_SEV_TEXTO = {"critical": "critical", "high": "high", "medium": "medium", "moderate": "medium", "low": "low",
              "info": "none", "informational": "none", "none": "none"}


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _sev(v) -> Optional[str]:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)) or str(v).isdigit():
        n = int(float(v))
        return {5: "critical", 4: "high", 3: "medium", 2: "low", 1: "low", 0: "none"}.get(n)
    return _SEV_TEXTO.get(str(v).strip().lower())


def _float(v) -> Optional[float]:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _cves(*valores) -> list[str]:
    salida = []
    for v in valores:
        if not v:
            continue
        lista = v if isinstance(v, list) else re.split(r"[\s,;]+", str(v))
        for x in lista:
            x = (x.get("id") if isinstance(x, dict) else str(x)).strip().upper() if x else ""
            if x.startswith("CVE-"):
                salida.append(x)
    return list(dict.fromkeys(salida))


def _det(**k) -> dict:
    estado = str(k.get("status") or "open").lower()
    k["status"] = "fixed" if estado in ("fixed", "resolved", "remediated", "closed", "patched", "inactive") else "open"
    return k


def _por_cve(base: dict, cves: list[str], ref: Optional[str], prefijo: str) -> list[dict]:
    if cves:
        return [_det(**{**base, "cve": c}) for c in cves]
    if ref:
        return [_det(**{**base, "cve": f"{prefijo}-{ref}"})]
    return []


# ── Parsers de cada formato ──────────────────────────────────────────────────

def desde_trendmicro(datos) -> list[dict]:
    items = datos.get("items") if isinstance(datos, dict) else datos
    salida = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        ips = it.get("ipAddresses") or it.get("ip") or []
        ip = ips[0] if isinstance(ips, list) and ips else (ips if isinstance(ips, str) else None)
        base = {"host": it.get("deviceName") or it.get("endpointName") or it.get("hostname"), "ip": ip,
                "asset_id": it.get("deviceId") or it.get("id"), "product": it.get("productName") or it.get("softwareName"),
                "vendor": it.get("productVendor") or it.get("vendor"), "version": it.get("productVersion"),
                "fixed_version": it.get("fixedVersion"), "first_seen": it.get("firstDetectedDateTime") or it.get("firstSeen"),
                "last_seen": it.get("lastDetectedDateTime") or it.get("lastSeen"), "status": it.get("status")}
        registros = it.get("cveRecords") or it.get("vulnerabilities")
        if isinstance(registros, list) and registros:
            for r in registros:
                if not isinstance(r, dict):
                    continue
                salida += _por_cve({**base, "title": r.get("description") or r.get("title"),
                                    "severity": _sev(r.get("riskLevel") or r.get("severity")),
                                    "cvss": _float(r.get("cvssScore")),
                                    "product": r.get("productName") or base["product"],
                                    "version": r.get("productVersion") or base["version"],
                                    "status": r.get("status") or base["status"]},
                                   _cves(r.get("id"), r.get("cveId")), r.get("id"), "TREND")
        else:
            salida += _por_cve({**base, "title": it.get("description"), "severity": _sev(it.get("riskLevel") or it.get("severity")),
                                "cvss": _float(it.get("cvssScore"))}, _cves(it.get("cveId"), it.get("cveIds")),
                               it.get("vulnerabilityId"), "TREND")
    return salida


def desde_defender(datos, maquinas: Optional[dict] = None) -> list[dict]:
    filas = datos.get("value") if isinstance(datos, dict) else datos
    maquinas = maquinas or {}
    salida = []
    for r in filas or []:
        if not isinstance(r, dict):
            continue
        m = maquinas.get(r.get("machineId") or r.get("deviceId")) or {}
        base = {"host": r.get("deviceName") or r.get("computerDnsName") or m.get("computerDnsName"),
                "ip": r.get("lastIpAddress") or m.get("lastIpAddress"), "asset_id": r.get("machineId") or r.get("deviceId"),
                "product": r.get("softwareName") or r.get("productName"),
                "vendor": r.get("softwareVendor") or r.get("productVendor"),
                "version": r.get("softwareVersion") or r.get("productVersion"),
                "fixed_version": r.get("recommendedSecurityUpdate") or r.get("fixingKbId"),
                "severity": _sev(r.get("vulnerabilitySeverityLevel") or r.get("severity")),
                "cvss": _float(r.get("cvssScore")), "title": r.get("name") or r.get("cveId"),
                "first_seen": r.get("firstSeenTimestamp"), "last_seen": r.get("lastSeenTimestamp"),
                "status": r.get("status") or ("fixed" if r.get("remediated") else "open")}
        salida += _por_cve(base, _cves(r.get("cveId")), r.get("id"), "MDVM")
    return salida


def _xml(texto: str):
    try:
        from defusedxml import ElementTree as ET
    except ImportError:  # pragma: no cover - defusedxml está en requirements
        import xml.etree.ElementTree as ET
    return ET.fromstring(texto)


def _t(nodo, ruta: str) -> Optional[str]:
    x = nodo.find(ruta)
    return x.text.strip() if x is not None and x.text else None


def base_de_conocimiento_qualys(texto: str) -> dict:
    """QID → {title, cves, cvss} del XML de la base de conocimiento."""
    raiz = _xml(texto)
    salida = {}
    for v in raiz.iter("VULN"):
        qid = _t(v, "QID")
        if qid:
            salida[qid] = {"title": _t(v, "TITLE"), "cves": [_t(c, "ID") for c in v.iter("CVE") if _t(c, "ID")],
                           "cvss": _float(_t(v, "CVSS_V3/BASE") or _t(v, "CVSS/BASE"))}
    return salida


def desde_qualys(texto: str, kb: Optional[dict] = None) -> list[dict]:
    raiz = _xml(texto)
    kb = kb or {}
    salida = []
    for h in raiz.iter("HOST"):
        base_host = {"host": _t(h, "DNS") or _t(h, "NETBIOS") or _t(h, "IP"), "ip": _t(h, "IP"), "asset_id": _t(h, "ID")}
        for d in h.iter("DETECTION"):
            qid = _t(d, "QID")
            info = kb.get(qid or "", {})
            tipo = (_t(d, "TYPE") or "Confirmed").lower()
            if tipo == "info":
                continue
            base = {**base_host, "severity": _sev(_t(d, "SEVERITY")), "cvss": info.get("cvss"),
                    "title": info.get("title") or f"QID {qid}", "status": _t(d, "STATUS"),
                    "first_seen": _t(d, "FIRST_FOUND_DATETIME"), "last_seen": _t(d, "LAST_FOUND_DATETIME"),
                    "ports": [int(_t(d, "PORT"))] if (_t(d, "PORT") or "").isdigit() else [],
                    "possible": tipo == "potential"}
            salida += _por_cve(base, _cves(info.get("cves")), qid, "QID")
    return salida


def _cpe_producto(cpes) -> tuple[Optional[str], Optional[str], Optional[str]]:
    for c in cpes or []:
        partes = str(c).replace("cpe:/", "cpe:2.3:").split(":")
        if len(partes) >= 5:
            desde = 3 if partes[1] == "2.3" else 2
            vendor, producto = partes[desde:desde + 2] if len(partes) > desde + 1 else (None, None)
            version = partes[desde + 2] if len(partes) > desde + 2 and partes[desde + 2] not in ("*", "-", "") else None
            if producto:
                return producto.replace("_", " "), vendor, version
    return None, None, None


def desde_tenable(datos) -> list[dict]:
    filas = datos if isinstance(datos, list) else (datos.get("vulnerabilities") or datos.get("items") or [])
    salida = []
    for r in filas:
        if not isinstance(r, dict):
            continue
        a, p = r.get("asset") or {}, r.get("plugin") or {}
        producto, fabricante, version = _cpe_producto(p.get("cpe"))
        base = {"host": a.get("hostname") or a.get("fqdn") or a.get("netbios_name") or a.get("ipv4"),
                "fqdn": a.get("fqdn"), "ip": a.get("ipv4"), "asset_id": a.get("uuid"), "product": producto,
                "vendor": fabricante, "version": version,
                "severity": _sev(r.get("severity")), "cvss": _float(p.get("cvss3_base_score") or p.get("cvss_base_score")),
                "title": p.get("name"), "status": r.get("state"), "first_seen": r.get("first_found"),
                "last_seen": r.get("last_found"),
                "ports": [r["port"]["port"]] if isinstance(r.get("port"), dict) and r["port"].get("port") else []}
        salida += _por_cve(base, _cves(p.get("cve")), p.get("id"), "TENABLE")
    return salida


def desde_rapid7(datos) -> list[dict]:
    activos = datos if isinstance(datos, list) else (datos.get("resources") or datos.get("assets") or [])
    salida = []
    for a in activos:
        if not isinstance(a, dict):
            continue
        base_host = {"host": a.get("hostName") or a.get("hostname") or a.get("ip"), "ip": a.get("ip"),
                     "asset_id": a.get("id")}
        for v in a.get("vulnerabilities") or []:
            if not isinstance(v, dict):
                continue
            cvss = v.get("cvss") or {}
            base = {**base_host, "title": v.get("title"), "severity": _sev(v.get("severity")),
                    "cvss": _float(v.get("cvssV3") or (cvss.get("v3") or {}).get("score") or (cvss.get("v2") or {}).get("score")),
                    "status": "fixed" if str(v.get("status", "")).lower() in ("fixed", "remediated") else "open",
                    "first_seen": v.get("since") or v.get("firstFound"), "product": v.get("product"),
                    "version": v.get("productVersion")}
            salida += _por_cve(base, _cves(v.get("cves")), v.get("id"), "R7")
    return salida


def desde_csv(texto: str) -> list[dict]:
    muestra = texto[:2000]
    lector = csv.DictReader(io.StringIO(texto), delimiter=";" if muestra.count(";") > muestra.count(",") else ",")
    salida = []
    for fila in lector:
        f = {(k or "").strip().lower(): (v or "").strip() for k, v in fila.items()}
        if not (f.get("host") or f.get("ip")) or not (f.get("cve") or f.get("id")):
            continue
        base = {"host": f.get("host") or f.get("ip"), "ip": f.get("ip") or None, "product": f.get("product") or None,
                "vendor": f.get("vendor") or None, "version": f.get("version") or None,
                "fixed_version": f.get("fixed_version") or None, "severity": _sev(f.get("severity")),
                "cvss": _float(f.get("cvss")), "title": f.get("title") or None, "status": f.get("status") or "open",
                "first_seen": f.get("first_seen") or None}
        salida += _por_cve(base, _cves(f.get("cve")), f.get("id"), "EXT")
    return salida


class _NoReconocido(Exception):
    """El contenido no es del formato de esa fuente (se responde con `swr_fichero_no_reconocido`)."""


def leer_fichero(fuente: str, contenido: bytes) -> list[dict]:
    if fuente not in FUENTES:
        raise error(422, "swr_fuente_no_valida", fuente=fuente)
    texto = contenido.decode("utf-8-sig", errors="replace").strip()
    if not texto:
        raise error(422, "sw_fichero_vacio")
    try:
        if texto.startswith("<"):
            if fuente != "qualys":
                raise _NoReconocido("xml")
            return desde_qualys(texto)
        if texto[0] in "[{":
            datos = json.loads(texto)
            if fuente == "trendmicro":
                return desde_trendmicro(datos)
            if fuente == "defender":
                return desde_defender(datos)
            if fuente == "tenable":
                return desde_tenable(datos)
            if fuente == "rapid7":
                return desde_rapid7(datos)
            raise _NoReconocido("json")
        return desde_csv(texto)
    except (_NoReconocido, ValueError, KeyError, TypeError, AttributeError) as e:
        logger.info("fichero de %s no reconocido: %s", fuente, e)
        raise error(422, "swr_fichero_no_reconocido", fuente=fuente)
    except Exception as e:  # noqa: BLE001 - XML mal formado o peligroso (defusedxml)
        logger.info("fichero de %s no reconocido: %s", fuente, e)
        raise error(422, "swr_fichero_no_reconocido", fuente=fuente)


# ── Aplicar detecciones ──────────────────────────────────────────────────────

def _fecha(v) -> Optional[datetime]:
    from app.services.cmdb_software.riesgo.controles import _fecha_hora
    return _fecha_hora(v)


def _ci(db: Session, org, d: dict, crear: bool, tipo_proveedor: str, proveedor=None):
    from app.services.cmdb.models import reconcile_cis
    from app.services.cmdb.parser import normalize_agent_payload
    from app.services.cmdb_software.importacion import buscar_ci
    for clave in ("host", "fqdn", "ip"):
        valor = d.get(clave)
        encontrado = buscar_ci(db, org, valor)
        if encontrado is None and clave == "host" and valor and "." in str(valor):
            encontrado = buscar_ci(db, org, str(valor).split(".")[0])
        if encontrado is not None:
            return encontrado, False
    if not crear or not (d.get("host") or d.get("ip")):
        return None, False
    host = {"hostname": d.get("host") or d.get("ip"), "fqdn": d.get("fqdn"), "ip_address": d.get("ip")}
    ci_dict = normalize_agent_payload(host, f"{tipo_proveedor}:{d.get('asset_id') or host['hostname']}")
    reconcile_cis(db, [ci_dict], tipo_proveedor, provider=proveedor, organization_id=org, retirar_ausentes=False)
    db.flush()
    return buscar_ci(db, org, host["hostname"]) or buscar_ci(db, org, d.get("ip")), True


def aplicar(db: Session, org, fuente: str, detecciones: list[dict], crear_cis: bool = True, completa: bool = False,
            usuario=None, proveedor=None, entorno: Optional[str] = None) -> dict:
    """Lleva las detecciones a CIs, productos, instancias, avisos y hallazgos. No confirma."""
    from app.models.cmdb_software import SoftwareInstance, SoftwareProduct, Vulnerability, VulnerabilityFinding
    from app.services.cmdb_software import ajustes as base
    from app.services.cmdb_software import catalogo as cat
    from app.services.cmdb_software.avisos import guardar_avisos
    from app.services.cmdb_software.correlacion import VIVOS, _clave, fuentes_de, poner_fuentes, vencimiento
    from app.services.cmdb_software.importacion import _instancia_existente
    conf = base.leer(db, org)
    momento = _ahora()
    tipo_proveedor = getattr(proveedor, "provider_type", None) or f"sw_import_{fuente}"
    r = {"source": fuente, "detections": len(detecciones), "cis_created": 0, "products_created": 0,
         "instances_created": 0, "findings_new": 0, "findings_updated": 0, "findings_resolved": 0,
         "unmatched_hosts": [], "errors": []}
    vistos: set = set()
    cache_ci: dict = {}
    # Avisos (sin pisar lo mejor que ya hubiera: guardar_avisos solo pone lo que trae)
    avisos: dict = {}
    for d in detecciones:
        if d.get("status") == "fixed":
            continue
        a = avisos.setdefault(d["cve"], {"vuln_id": d["cve"], "source": fuente[:12]})
        for k_origen, k_destino in (("title", "title"), ("cvss", "cvss_score"), ("severity", "severity")):
            if d.get(k_origen) and not a.get(k_destino):
                a[k_destino] = d[k_origen]
    existentes_v = {v.vuln_id: v for v in calc_q(db, Vulnerability, org).filter(
        Vulnerability.vuln_id.in_(list(avisos) or [""]))}
    nuevos_avisos = [a for vid, a in avisos.items() if vid not in existentes_v]
    for vid, a in avisos.items():
        v = existentes_v.get(vid)
        if v is not None:
            # Solo se completa lo que falta.
            if v.cvss_score is None and a.get("cvss_score") is not None:
                v.cvss_score = float(a["cvss_score"])
            if (not v.severity or v.severity == "unknown") and a.get("severity"):
                v.severity = a["severity"]
            if not v.title and a.get("title"):
                v.title = str(a["title"])[:500]
    if nuevos_avisos:
        guardar_avisos(db, org, nuevos_avisos, fuente[:12])
    vulns = {v.vuln_id: v for v in calc_q(db, Vulnerability, org).filter(
        Vulnerability.vuln_id.in_(list(avisos) or [""]))}
    for n, d in enumerate(detecciones, start=1):
        try:
            clave_host = (d.get("host") or "", d.get("ip") or "")
            if clave_host not in cache_ci:
                with db.begin_nested():
                    cache_ci[clave_host] = _ci(db, org, d, crear_cis, tipo_proveedor, proveedor)
                r["cis_created"] += int(cache_ci[clave_host][1])
            ci = cache_ci[clave_host][0]
            if ci is None:
                h = d.get("host") or d.get("ip")
                if h and h not in r["unmatched_hosts"]:
                    r["unmatched_hosts"].append(h)
                continue
            if d.get("product"):
                prod, nuevo = cat.buscar_o_crear_producto(db, org, str(d["product"])[:200], None, None, None, None,
                                                          "application", "purchased", None,
                                                          (str(d["vendor"])[:200] if d.get("vendor") else None))
            else:
                clave = f"import:{fuente}:unidentified"
                prod = cat.por_clave(db, org, clave)
                nuevo = prod is None
                if prod is None:
                    prod = SoftwareProduct(organization_id=org, name=f"Sin identificar ({fuente})", category="other",
                                           origin="purchased", match_key=clave)
                    db.add(prod)
                    db.flush()
            r["products_created"] += int(nuevo)
            inst = _instancia_existente(db, org, prod.id, ci.id, None, f"{fuente}:{ci.id}:{prod.id}", None)
            if inst is None:
                datos = {"product_id": prod.id, "ci_id": ci.id, "version": str(d["version"]) if d.get("version") else None,
                         "external_key": f"{fuente}:{ci.id}:{prod.id}", "name": prod.name, "status": "running",
                         "ports": d.get("ports") or []}
                if entorno:
                    datos["environment"] = entorno
                inst = cat.crear_instancia(db, org, datos, usuario, origen="import", auditar=False)
                r["instances_created"] += 1
            elif d.get("version") and not inst.version:
                inst.version = str(d["version"])[:100]
            v = vulns.get(d["cve"])
            if v is None:
                continue
            oc = {"instance": inst, "parent_version_id": None, "product": prod, "version": inst.version}
            clave_f = _clave(v, oc)
            f = calc_q(db, VulnerabilityFinding, org).filter(VulnerabilityFinding.finding_key == clave_f).first()
            if d.get("status") == "fixed":
                if f is not None and f.status in VIVOS:
                    restantes = [x for x in fuentes_de(f) if x != fuente]
                    poner_fuentes(f, restantes)
                    if not restantes:
                        f.status, f.closed_at, f.verified_at, f.resolution = "resolved", momento, momento, "fixed"
                        r["findings_resolved"] += 1
                continue
            vistos.add(clave_f)
            if f is None:
                f = VulnerabilityFinding(organization_id=org, finding_key=clave_f, vulnerability_id=v.id,
                                         product_id=prod.id, affected_version=inst.version, instance_id=inst.id,
                                         status="open", first_seen_at=_fecha(d.get("first_seen")) or momento,
                                         severity=v.severity or "unknown", environment=inst.environment,
                                         exposure=inst.exposure, detected_by=json.dumps([fuente]))
                db.add(f)
                r["findings_new"] += 1
            else:
                if f.status == "resolved":
                    f.status, f.closed_at, f.verified_at, f.resolution = "open", None, None, None
                poner_fuentes(f, fuentes_de(f) + [fuente] if f.detected_by else [fuente, "correlation"])
                r["findings_updated"] += 1
            f.last_seen_at = momento
            if d.get("fixed_version") and not f.fixed_version:
                f.fixed_version = str(d["fixed_version"])[:100]
            if f.priority_score is None:
                from app.services.cmdb_software.correlacion import prioridad
                puntos, detalle = prioridad(v, prod.criticality or "medium", inst.exposure or "internal",
                                            inst.environment or "prod")
                if d.get("possible"):
                    puntos, detalle = round(puntos / 2, 1), {**detalle, "possible": True, "score": round(puntos / 2, 1)}
                f.priority_score, f.score_detail = puntos, json.dumps(detalle)
            if f.status in VIVOS and f.sla_due_at is None and not d.get("possible"):
                f.sla_due_at = vencimiento(conf, v, f.first_seen_at or momento)
            db.flush()
        except Exception as e:  # noqa: BLE001 - una detección mala no tumba el resto
            logger.warning("aplicar: excepcion ignorada", exc_info=True)
            r["errors"].append({"row": n, "error": getattr(e, "codigo", None) or getattr(e, "code", None)
                                or type(e).__name__})
    if completa:
        for f in calc_q(db, VulnerabilityFinding, org).filter(VulnerabilityFinding.status.in_(VIVOS),
                                                             VulnerabilityFinding.detected_by.like(f'%"{fuente}"%')):
            if f.finding_key in vistos:
                continue
            restantes = [x for x in fuentes_de(f) if x != fuente]
            poner_fuentes(f, restantes)
            if not restantes:
                f.status, f.closed_at, f.verified_at, f.resolution = "resolved", momento, momento, "not_present"
                r["findings_resolved"] += 1
    db.flush()
    audit_log(db, usuario, "IMPORT", "sw_third_party", getattr(proveedor, "id", None) or fuente, fuente,
              metadata={k: v for k, v in r.items() if k not in ("errors", "unmatched_hosts")}
              | {"errors": len(r["errors"]), "unmatched_hosts": len(r["unmatched_hosts"]), "complete": completa})
    r["errors"] = r["errors"][:100]
    r["unmatched_hosts"] = r["unmatched_hosts"][:100]
    return r


def calc_q(db, modelo, org):
    q = db.query(modelo)
    return q.filter(modelo.organization_id == org) if org else q


def importar_fichero(db: Session, org, fuente: str, contenido: bytes, crear_cis: bool = True, completa: bool = False,
                     usuario=None) -> dict:
    from app.services.cmdb_software.importacion import comprobar_fichero
    comprobar_fichero(contenido)
    detecciones = leer_fichero(fuente, contenido)
    return aplicar(db, org, fuente, detecciones, crear_cis, completa, usuario)


# ── APIs ─────────────────────────────────────────────────────────────────────

def _http_real(metodo: str, url: str, *, headers: Optional[dict] = None, params: Optional[dict] = None,
               json_: Optional[dict] = None, data: Optional[dict] = None, auth: Optional[tuple] = None,
               timeout: float = 30):
    # SSRF: la URL es de la conexión (empresa) o del proveedor; `peticion` valida URL, redirecciones e IP
    # conectada. Con credenciales (cabeceras que no sean Accept, auth o cuerpo) no se siguen redirecciones.
    from app.core.outbound_url import peticion
    con_credenciales = bool(auth or data or any(k.lower() != "accept" for k in (headers or {})))
    r = peticion(metodo, url, field="url", headers=headers, params=params, json=json_, data=data, auth=auth,
                 timeout=timeout, follow_redirects=not con_credenciales)
    r.raise_for_status()
    tipo = r.headers.get("content-type", "")
    return r.json() if "json" in tipo else r.text


#: Llamada HTTP (los tests la sustituyen).
_http: Callable = _http_real


def _llamar(fuente: str, *args, **kwargs):
    try:
        return _http(*args, **kwargs)
    except ErrorConCodigo:
        raise
    except Exception as e:  # noqa: BLE001
        raise ErrorConCodigo("swr_api_tercero", fuente=fuente, detalle=str(e)[:200])


def _base(conf: dict, tipo: str) -> str:
    url = (conf.get("url") or URLS.get(tipo) or "").rstrip("/")
    if not url:
        raise ErrorConCodigo("sw_conexion_incompleta", campo="url")
    return url


def _siguiente(base: str, sig, fuente: str):
    """URL de la página siguiente solo si es del mismo origen que la configurada (si no, se corta)."""
    from app.core.outbound_url import mismo_origen
    if not isinstance(sig, str) or not sig.startswith(("http://", "https://")):
        return None
    if not mismo_origen(base, sig):
        logger.warning("paginación de %s: la página siguiente es de otro origen; se detiene", fuente)
        return None
    return sig


def recoger_trendmicro(conf: dict) -> list[dict]:
    if not conf.get("token"):
        raise ErrorConCodigo("sw_conexion_incompleta", campo="token")
    url = f"{_base(conf, 'sw_vm_trendmicro')}/v3.0/asrm/vulnerableDevices"
    cab = {"Authorization": f"Bearer {conf['token']}", "Accept": "application/json"}
    salida, paginas = [], 0
    while url and paginas < int(conf.get("max_pages") or 20):
        datos = _llamar("trendmicro", "GET", url, headers=cab, timeout=float(conf.get("timeout") or 30))
        salida += desde_trendmicro(datos)
        paginas += 1
        url = _siguiente(_base(conf, "sw_vm_trendmicro"), datos.get("nextLink") if isinstance(datos, dict) else None,
                         "trendmicro")
    return salida


def recoger_defender(conf: dict) -> list[dict]:
    for campo in ("tenant_id", "client_id", "client_secret"):
        if not conf.get(campo):
            raise ErrorConCodigo("sw_conexion_incompleta", campo=campo)
    base = _base(conf, "sw_vm_defender")
    t = float(conf.get("timeout") or 30)
    token = _llamar("defender", "POST", f"{settings.MICROSOFT_OAUTH_BASE.rstrip('/')}/{conf['tenant_id']}/oauth2/v2.0/token",
                    data={"client_id": conf["client_id"], "client_secret": conf["client_secret"],
                          "grant_type": "client_credentials", "scope": f"{base}/.default"}, timeout=t)
    cab = {"Authorization": f"Bearer {token.get('access_token')}", "Accept": "application/json"}
    maquinas, url, paginas = {}, f"{base}/api/machines", 0
    while url and paginas < int(conf.get("max_pages") or 20):
        datos = _llamar("defender", "GET", url, headers=cab, timeout=t)
        for m in datos.get("value") or []:
            maquinas[m.get("id")] = m
        url, paginas = _siguiente(base, datos.get("@odata.nextLink"), "defender"), paginas + 1
    salida, url, paginas = [], f"{base}/api/vulnerabilities/machinesVulnerabilities", 0
    while url and paginas < int(conf.get("max_pages") or 20):
        datos = _llamar("defender", "GET", url, headers=cab, timeout=t)
        salida += desde_defender(datos, maquinas)
        url, paginas = _siguiente(base, datos.get("@odata.nextLink"), "defender"), paginas + 1
    return salida


def recoger_qualys(conf: dict) -> list[dict]:
    for campo in ("url", "username", "password"):
        if not conf.get(campo):
            raise ErrorConCodigo("sw_conexion_incompleta", campo=campo)
    base = conf["url"].rstrip("/")
    t = float(conf.get("timeout") or 60)
    cab = {"X-Requested-With": "contecflow"}
    auth = (conf["username"], conf["password"])
    # A22 (auditoría 22-11-2026): paginación documentada de la API VM de Qualys
    # (v2 «host list detection»): una respuesta truncada trae
    # `<WARNING><CODE>1980</CODE><URL>…&id_min=N</URL></WARNING>`; se pide la
    # siguiente con ese `id_min` hasta que no haya aviso (o `max_pages`). Antes
    # solo se leía la primera página (1.000 hosts).
    datos = {"action": "list", "show_results": 0, "status": "New,Active,Re-Opened,Fixed", "truncation_limit": 1000}
    paginas: list[str] = []
    for _ in range(int(conf.get("max_pages") or 50)):
        texto = _llamar("qualys", "POST", f"{base}/api/2.0/fo/asset/host/vm/detection/", headers=cab, auth=auth,
                        data=datos, timeout=t)
        paginas.append(texto)
        siguiente = _id_min_siguiente_qualys(texto)
        if not siguiente:
            break
        datos = {**datos, "id_min": siguiente}
    else:
        raise ErrorConCodigo("sw_respuesta_truncada", fuente="qualys")
    kb = {}
    if conf.get("with_kb", True):
        qids = sorted({q.text for texto in paginas for q in _xml(texto).iter("QID") if q.text})
        for i in range(0, len(qids), 1000):
            texto_kb = _llamar("qualys", "POST", f"{base}/api/2.0/fo/knowledge_base/vuln/", headers=cab, auth=auth,
                               data={"action": "list", "ids": ",".join(qids[i:i + 1000])}, timeout=t)
            kb.update(base_de_conocimiento_qualys(texto_kb))
    salida: list[dict] = []
    for texto in paginas:
        salida += desde_qualys(texto, kb)
    return salida


def _id_min_siguiente_qualys(texto: str) -> Optional[str]:
    """El `id_min` de la página siguiente si la respuesta viene truncada (aviso 1980)."""
    from urllib.parse import parse_qs, urlparse
    raiz = _xml(texto)
    for aviso in raiz.iter("WARNING"):
        url = _t(aviso, "URL")
        if url:
            valores = parse_qs(urlparse(url).query).get("id_min")
            if valores:
                return valores[0]
    return None


def recoger_tenable(conf: dict) -> list[dict]:
    for campo in ("access_key", "secret_key"):
        if not conf.get(campo):
            raise ErrorConCodigo("sw_conexion_incompleta", campo=campo)
    base = _base(conf, "sw_vm_tenable")
    t = float(conf.get("timeout") or 30)
    cab = {"X-ApiKeys": f"accessKey={conf['access_key']};secretKey={conf['secret_key']}", "Accept": "application/json"}
    exp = _llamar("tenable", "POST", f"{base}/vulns/export", headers=cab, json_={"num_assets": 500}, timeout=t)
    uuid_ = exp.get("export_uuid")
    estado = {}
    # A22 (auditoría 22-11-2026): la exportación de Tenable.io es asíncrona
    # (`QUEUED`/`PROCESSING` → `FINISHED`); se espera entre consultas con
    # retroceso (`poll_seconds`, hasta 30 s) y, si no termina o falla, error:
    # antes se consultaba sin espera y se seguía con los trozos que hubiera.
    import time as _time
    espera = float(conf.get("poll_seconds") or 2)
    for _ in range(int(conf.get("max_pages") or 30)):
        estado = _llamar("tenable", "GET", f"{base}/vulns/export/{uuid_}/status", headers=cab, timeout=t)
        if estado.get("status") in ("FINISHED", "ERROR", "CANCELLED"):
            break
        _time.sleep(espera)
        espera = min(espera * 2, 30.0)
    if estado.get("status") != "FINISHED":
        raise ErrorConCodigo("sw_respuesta_truncada", fuente="tenable")
    salida = []
    for trozo in estado.get("chunks_available") or []:
        salida += desde_tenable(_llamar("tenable", "GET", f"{base}/vulns/export/{uuid_}/chunks/{trozo}", headers=cab,
                                        timeout=t))
    return salida


def recoger_rapid7(conf: dict) -> list[dict]:
    for campo in ("url", "username", "password"):
        if not conf.get(campo):
            raise ErrorConCodigo("sw_conexion_incompleta", campo=campo)
    base = conf["url"].rstrip("/")
    t = float(conf.get("timeout") or 30)
    auth = (conf["username"], conf["password"])
    activos, pagina, detalles = [], 0, {}
    while pagina < int(conf.get("max_pages") or 10):
        datos = _llamar("rapid7", "GET", f"{base}/api/3/assets", auth=auth, params={"page": pagina, "size": 100},
                        timeout=t)
        recursos = datos.get("resources") or []
        for a in recursos:
            vulns = _llamar("rapid7", "GET", f"{base}/api/3/assets/{a.get('id')}/vulnerabilities", auth=auth,
                            timeout=t).get("resources") or []
            lista = []
            for v in vulns:
                vid = v.get("id")
                if vid not in detalles:
                    detalles[vid] = _llamar("rapid7", "GET", f"{base}/api/3/vulnerabilities/{vid}", auth=auth, timeout=t)
                d = detalles[vid] or {}
                lista.append({"id": vid, "title": d.get("title"), "cves": d.get("cves"), "cvss": d.get("cvss"),
                              "severity": d.get("severity"), "status": v.get("status"), "since": v.get("since")})
            activos.append({"hostName": a.get("hostName"), "ip": a.get("ip"), "id": a.get("id"),
                            "vulnerabilities": lista})
        pagina += 1
        total = (datos.get("page") or {}).get("totalPages") or 1
        if pagina >= total:
            break
    return desde_rapid7(activos)


def ruta_json(datos, ruta: Optional[str]):
    """Valor de una ruta con puntos (``data.devices``) en un JSON."""
    if not ruta:
        return datos
    actual = datos
    for parte in ruta.split("."):
        if isinstance(actual, dict):
            actual = actual.get(parte)
        elif isinstance(actual, list) and parte.isdigit() and int(parte) < len(actual):
            actual = actual[int(parte)]
        else:
            return None
    return actual




def recoger_siem(conf: dict) -> list[dict]:
    url = conf.get("url")
    if not url:
        raise ErrorConCodigo("sw_conexion_incompleta", campo="url")
    cab = {"Accept": "application/json"}
    if conf.get("token"):
        nombre = conf.get("auth_header") or "Authorization"
        cab[nombre] = conf["token"] if nombre.lower() != "authorization" or " " in conf["token"] \
            else f"Bearer {conf['token']}"
    filas, paginas = [], 0
    while url and paginas < int(conf.get("max_pages") or 10):
        datos = _llamar("siem", "GET", url, headers=cab, params={"days": conf.get("days") or 7} if paginas == 0 else None,
                        timeout=float(conf.get("timeout") or 30))
        lista = ruta_json(datos, conf.get("list_path")) if conf.get("list_path") else datos
        for e in lista if isinstance(lista, list) else []:
            if not isinstance(e, dict):
                continue
            filas.append({"cve": ruta_json(e, conf.get("cve_field") or "cve"), "host": ruta_json(e, conf.get("host_field") or "host"),
                          "ip": ruta_json(e, conf.get("ip_field") or "ip"),
                          "observed_at": ruta_json(e, conf.get("time_field") or "timestamp"),
                          "action": ruta_json(e, conf.get("action_field") or "action"),
                          "count": ruta_json(e, conf.get("count_field") or "count"),
                          "id": ruta_json(e, conf.get("id_field") or "id")})
        paginas += 1
        sig = ruta_json(datos, conf.get("next_path")) if conf.get("next_path") else None
        url = _siguiente(conf.get("url"), sig, "siem")
    return filas


RECOGEDORES = {"sw_vm_trendmicro": recoger_trendmicro, "sw_vm_defender": recoger_defender,
               "sw_vm_qualys": recoger_qualys, "sw_vm_tenable": recoger_tenable, "sw_vm_rapid7": recoger_rapid7}


def ejecutar_conexion(db: Session, c, usuario=None, disparo: str = "manual") -> dict:
    """Lo que llama `escaneos.ejecutar` para los tipos de terceros. No confirma."""
    from app.services.cmdb.parser import load_config
    conf = load_config(c)
    if c.provider_type == "sw_siem":
        from app.services.cmdb_software.riesgo.controles import aplicar_eventos
        r = aplicar_eventos(db, c.organization_id, recoger_siem(conf), f"siem:{c.name}"[:30], usuario)
        return {"hosts": r["matched"], "errors": r["errors"], "cis_created": 0, "events": r, "trigger": disparo}
    fuente = TIPO_A_FUENTE[c.provider_type]
    detecciones = RECOGEDORES[c.provider_type](conf)
    r = aplicar(db, c.organization_id, fuente, detecciones, bool(conf.get("create_cis", True)),
                # Auditoría 22-11-2026 (A22): por defecto NO es inventario completo; una
                # respuesta truncada ya no marca «resueltos» en masa los hallazgos ausentes.
                bool(conf.get("complete", False)), usuario, c, conf.get("environment") or None)
    return {"hosts": len({(d.get("host"), d.get("ip")) for d in detecciones}), "errors": r["errors"],
            "cis_created": r["cis_created"], "findings_new": r["findings_new"],
            "findings_resolved": r["findings_resolved"], "import": r, "trigger": disparo}


def probar_conexion(c) -> dict:
    from app.services.cmdb.parser import load_config
    conf = load_config(c)
    try:
        if c.provider_type == "sw_siem":
            return {"ok": True, "devices": len(recoger_siem({**conf, "max_pages": 1}))}
        n = len(RECOGEDORES[c.provider_type]({**conf, "max_pages": 1}))
        return {"ok": True, "devices": n}
    except Exception as e:  # noqa: BLE001
        logger.debug("probar_conexion: excepcion ignorada", exc_info=True)
        return {"ok": False, "error": getattr(e, "codigo", None) or getattr(e, "code", None) or type(e).__name__}
