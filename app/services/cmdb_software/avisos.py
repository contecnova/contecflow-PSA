"""Avisos de vulnerabilidad: formato común, guardado y lectura de ficheros.

**Formato común** (lo producen `fuentes`, `escaneres` y los lectores de
fichero de aquí) ::

    {vuln_id, aliases, source, title, description, severity, cvss_score,
     cvss_vector, cvss_version, cwe, references, published_at, modified_at,
     withdrawn_at, affects: [{package_key | (ecosystem + name [+ namespace]) |
     (cpe_vendor + cpe_product), introduced, introduced_inclusive, fixed,
     last_affected, versions, range_text}]}

`guardar_avisos` hace upsert por (empresa, id) y sustituye sus «afecta a»
por los que llegan de esa misma lectura (un aviso actualizado puede corregir
el rango).

Ficheros (`leer_fichero`, sin red): OSV JSON (uno o lista), respuesta de NVD
2.0, lista de GitHub Advisories, informes de Trivy/Grype y CSV
(``vuln_id, purl|package|cpe, introduced, fixed, last_affected, versions,
severity, cvss, title, description``).
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.core import timeutil
from app.core.codigos_de_error import error
from app.models.cmdb_software import Vulnerability, VulnerabilityAffect, VulnerabilitySyncRun
from app.services.audit import audit_log
from app.services.cmdb_software import identificadores as ids
from app.services.cmdb_software.versiones import rango_de_texto

SEVERIDADES = ("critical", "high", "medium", "low", "none", "unknown")

#: Ecosistema de OSV/GitHub → tipo purl.
ECOSISTEMAS = {"npm": "npm", "pypi": "pypi", "packagist": "composer", "composer": "composer", "maven": "maven",
               "go": "golang", "golang": "golang", "rubygems": "gem", "crates.io": "cargo", "rust": "cargo",
               "cargo": "cargo", "nuget": "nuget", "hex": "hex", "pub": "pub", "debian": "deb", "ubuntu": "deb",
               "alpine": "apk", "rocky linux": "rpm", "almalinux": "rpm", "red hat": "rpm", "swifturl": "swift",
               "github actions": "github", "actions": "github", "erlang": "hex", "rust crates": "cargo"}


def severidad_de_cvss(score: Optional[float]) -> str:
    if score is None:
        return "unknown"
    if score >= 9.0:
        return "critical"
    if score >= 7.0:
        return "high"
    if score >= 4.0:
        return "medium"
    if score > 0:
        return "low"
    return "none"


def _cvss_desde_vector(vector: Optional[str]) -> Optional[float]:
    """Puntuación base CVSS 3.x a partir del vector (para OSV, que solo trae el vector)."""
    if not vector or not vector.startswith("CVSS:3"):
        return None
    try:
        m = dict(p.split(":", 1) for p in vector.split("/")[1:])
        av = {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2}[m["AV"]]
        ac = {"L": 0.77, "H": 0.44}[m["AC"]]
        cambia = m["S"] == "C"
        pr = {"N": 0.85, "L": 0.68 if cambia else 0.62, "H": 0.5 if cambia else 0.27}[m["PR"]]
        ui = {"N": 0.85, "R": 0.62}[m["UI"]]
        c, i, a = ({"H": 0.56, "L": 0.22, "N": 0.0}[m[k]] for k in ("C", "I", "A"))
    except (KeyError, ValueError):
        return None
    import math

    def redondear(x):
        return math.ceil(x * 10 - 1e-9) / 10
    iss = 1 - (1 - c) * (1 - i) * (1 - a)
    impacto = 7.52 * (iss - 0.029) - 3.25 * (iss - 0.02) ** 15 if cambia else 6.42 * iss
    explot = 8.22 * av * ac * pr * ui
    if impacto <= 0:
        return 0.0
    return redondear(min(1.08 * (impacto + explot), 10)) if cambia else redondear(min(impacto + explot, 10))


def _fecha(v) -> Optional[datetime]:
    if not v:
        return None
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.fromisoformat(str(v)[:10])
        except ValueError:
            return None


def clave_de_afecta(a: dict) -> Optional[str]:
    if a.get("package_key"):
        return a["package_key"]
    if a.get("purl"):
        p = ids.parsear_purl(a["purl"])
        return p.clave() if p else None
    if a.get("name"):
        # OSV versiona los ecosistemas de distribución («Debian:11», «Ubuntu:22.04:LTS», «Alpine:v3.18»):
        # cuenta la distribución, que es el espacio del purl (pkg:deb/ubuntu/openssl).
        base = (a.get("ecosystem") or "generic").split(":")[0].strip().lower()
        tipo = ECOSISTEMAS.get(base, base)
        espacio, nombre = a.get("namespace"), a["name"]
        if not espacio and tipo in ("deb", "rpm", "apk"):
            espacio = {"red hat": "rhel", "rocky linux": "rocky"}.get(base, base)
        if not espacio and tipo in ("composer", "golang", "maven") and ("/" in nombre or ":" in nombre):
            sep = ":" if tipo == "maven" else "/"
            espacio, _, nombre = nombre.rpartition(sep)
        if not espacio and tipo == "npm" and nombre.startswith("@") and "/" in nombre:
            espacio, nombre = nombre.split("/", 1)
        return ids.clave_de_paquete(tipo, espacio, nombre)
    return None


def guardar_avisos(db: Session, org, avisos: list[dict], fuente: str) -> dict:
    """Upsert; devuelve {created, updated}."""
    creados = actualizados = 0
    for a in avisos:
        vid = (a.get("vuln_id") or "").strip()[:80]
        if not vid:
            continue
        q = db.query(Vulnerability).filter(Vulnerability.vuln_id == vid)
        q = q.filter(Vulnerability.organization_id == org) if org else q
        v = q.first()
        if v is None:
            v = Vulnerability(organization_id=org, vuln_id=vid, source=a.get("source") or fuente)
            db.add(v)
            creados += 1
        else:
            actualizados += 1
        score = a.get("cvss_score")
        if score is None and a.get("cvss_vector"):
            score = _cvss_desde_vector(a["cvss_vector"])
        sev = (a.get("severity") or "").lower()
        if sev not in SEVERIDADES or sev == "unknown":
            sev = severidad_de_cvss(score) if score is not None else (v.severity or "unknown")
        v.severity = sev
        for campo in ("title", "description", "cvss_vector", "cvss_version"):
            if a.get(campo):
                valor = str(a[campo])
                setattr(v, campo, valor[:500] if campo == "title" else valor[:200] if campo == "cvss_vector"
                        else valor[:10] if campo == "cvss_version" else valor)
        if score is not None:
            v.cvss_score = float(score)
        if a.get("kev"):
            v.kev = True
        if a.get("epss_score") is not None:
            v.epss_score = float(a["epss_score"])
        alias = set(json.loads(v.aliases)) if v.aliases else set()
        alias |= {x for x in a.get("aliases") or [] if x and x != vid}
        v.aliases = json.dumps(sorted(alias)) if alias else None
        if a.get("cwe"):
            v.cwe = json.dumps(list(dict.fromkeys(a["cwe"]))[:20])
        if a.get("references"):
            v.references = json.dumps(list(dict.fromkeys(a["references"]))[:30])
        for campo in ("published_at", "modified_at", "withdrawn_at"):
            f = _fecha(a.get(campo))
            if f:
                setattr(v, campo, f)
        db.flush()
        afectas = a.get("affects")
        if afectas is not None:
            if fuente not in ("trivy", "grype"):
                db.query(VulnerabilityAffect).filter(VulnerabilityAffect.vulnerability_id == v.id).delete(
                    synchronize_session=False)
            for x in afectas:
                clave = clave_de_afecta(x)
                if not clave and not (x.get("cpe_vendor") and x.get("cpe_product")):
                    continue
                versiones_exactas = [str(s) for s in x.get("versions") or [] if s]
                if fuente in ("trivy", "grype"):
                    duplicada = db.query(VulnerabilityAffect.id).filter(
                        VulnerabilityAffect.vulnerability_id == v.id, VulnerabilityAffect.package_key == clave,
                        VulnerabilityAffect.versions == (json.dumps(versiones_exactas) if versiones_exactas else None)
                    ).first()
                    if duplicada:
                        continue
                db.add(VulnerabilityAffect(
                    organization_id=org, vulnerability_id=v.id, package_key=clave,
                    ecosystem=(x.get("ecosystem") or (clave.split("/", 1)[0] if clave else None) or None),
                    cpe_vendor=(x.get("cpe_vendor") or None) and x["cpe_vendor"].lower(),
                    cpe_product=(x.get("cpe_product") or None) and x["cpe_product"].lower(),
                    introduced=x.get("introduced"), introduced_inclusive=x.get("introduced_inclusive", True),
                    fixed=x.get("fixed"), last_affected=x.get("last_affected"),
                    versions=json.dumps(versiones_exactas) if versiones_exactas else None,
                    range_text=(x.get("range_text") or None) and str(x["range_text"])[:300]))
    db.flush()
    return {"created": creados, "updated": actualizados}


# ── OSV ──────────────────────────────────────────────────────────────────────

def desde_osv(d: dict) -> dict:
    sev = None
    vector = None
    for s in d.get("severity") or []:
        if (s.get("type") or "").startswith("CVSS_V3") or (s.get("type") or "").startswith("CVSS_V4"):
            vector = s.get("score")
            break
    afectas = []
    for a in d.get("affected") or []:
        paquete = a.get("package") or {}
        base = {"ecosystem": paquete.get("ecosystem"), "name": paquete.get("name"), "purl": paquete.get("purl")}
        exactas = [str(x) for x in a.get("versions") or []]
        rangos = [r for r in a.get("ranges") or [] if r.get("type") in ("SEMVER", "ECOSYSTEM")]
        for r in rangos:
            tramo: dict = {}
            for ev in r.get("events") or []:
                if "introduced" in ev:
                    if tramo:
                        afectas.append({**base, **tramo, "range_text": json.dumps(r.get("events"))[:300]})
                    tramo = {"introduced": ev["introduced"]}
                elif "fixed" in ev:
                    tramo["fixed"] = ev["fixed"]
                    afectas.append({**base, **tramo, "range_text": json.dumps(r.get("events"))[:300]})
                    tramo = {}
                elif "last_affected" in ev:
                    tramo["last_affected"] = ev["last_affected"]
                    afectas.append({**base, **tramo, "range_text": json.dumps(r.get("events"))[:300]})
                    tramo = {}
            if tramo:
                afectas.append({**base, **tramo, "range_text": json.dumps(r.get("events"))[:300]})
        if exactas:
            afectas.append({**base, "versions": exactas})
        sev = sev or (a.get("database_specific") or {}).get("severity") or (a.get("ecosystem_specific") or {}).get("severity")
    sev = sev or (d.get("database_specific") or {}).get("severity")
    return {"vuln_id": d.get("id"), "aliases": d.get("aliases") or [], "source": "osv", "title": d.get("summary"),
            "description": d.get("details"), "severity": (sev or "").lower().replace("moderate", "medium"),
            "cvss_vector": vector, "cvss_version": vector.split("/")[0].split(":")[1] if vector and ":" in vector else None,
            "cwe": (d.get("database_specific") or {}).get("cwe_ids") or [],
            "references": [r.get("url") for r in d.get("references") or [] if r.get("url")],
            "published_at": d.get("published"), "modified_at": d.get("modified"), "withdrawn_at": d.get("withdrawn"),
            "affects": afectas}


# ── NVD 2.0 ──────────────────────────────────────────────────────────────────

def desde_nvd(item: dict) -> dict:
    cve = item.get("cve") or item
    metricas = cve.get("metrics") or {}
    score = vector = version = sev = None
    for clave in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        lista = metricas.get(clave) or []
        if lista:
            m = next((x for x in lista if x.get("type") == "Primary"), lista[0])
            datos = m.get("cvssData") or {}
            score, vector, version = datos.get("baseScore"), datos.get("vectorString"), datos.get("version")
            sev = datos.get("baseSeverity") or m.get("baseSeverity")
            break
    afectas = []
    for conf in cve.get("configurations") or []:
        for nodo in conf.get("nodes") or []:
            for cm in nodo.get("cpeMatch") or []:
                if not cm.get("vulnerable", True):
                    continue
                c = ids.parsear_cpe(cm.get("criteria"))
                if not c:
                    continue
                tramo = {"cpe_vendor": c.vendor, "cpe_product": c.product}
                if cm.get("versionStartIncluding"):
                    tramo["introduced"] = cm["versionStartIncluding"]
                if cm.get("versionStartExcluding"):
                    tramo["introduced"], tramo["introduced_inclusive"] = cm["versionStartExcluding"], False
                if cm.get("versionEndExcluding"):
                    tramo["fixed"] = cm["versionEndExcluding"]
                if cm.get("versionEndIncluding"):
                    tramo["last_affected"] = cm["versionEndIncluding"]
                if not any(k in tramo for k in ("introduced", "fixed", "last_affected")):
                    if c.version:
                        tramo["versions"] = [c.version]
                    else:
                        tramo["introduced"] = "0"    # «todas las versiones»
                tramo["range_text"] = cm.get("criteria")
                afectas.append(tramo)
    desc = next((d.get("value") for d in cve.get("descriptions") or [] if d.get("lang") == "en"), None)
    cwe = [d.get("value") for w in cve.get("weaknesses") or [] for d in w.get("description") or []
           if (d.get("value") or "").startswith("CWE-")]
    return {"vuln_id": cve.get("id"), "source": "nvd", "title": (desc or "")[:200] or None, "description": desc,
            "severity": (sev or "").lower(), "cvss_score": score, "cvss_vector": vector, "cvss_version": version,
            "cwe": cwe, "references": [r.get("url") for r in cve.get("references") or [] if r.get("url")],
            "published_at": cve.get("published"), "modified_at": cve.get("lastModified"),
            "kev": bool(cve.get("cisaExploitAdd")), "affects": afectas}


# ── GitHub Advisories ────────────────────────────────────────────────────────

def desde_ghsa(d: dict) -> dict:
    afectas = []
    for v in d.get("vulnerabilities") or []:
        paquete = v.get("package") or {}
        base = {"ecosystem": paquete.get("ecosystem"), "name": paquete.get("name")}
        rango = v.get("vulnerable_version_range") or ""
        tramos = rango_de_texto(rango)
        parche = v.get("first_patched_version")
        if isinstance(parche, dict):
            parche = parche.get("identifier")
        if not tramos and parche:
            tramos = [{"fixed": parche}]
        for t in tramos:
            if parche and not t.get("fixed") and not t.get("last_affected") and not t.get("versions"):
                t["fixed"] = parche
            afectas.append({**base, **t, "range_text": rango})
    cvss = d.get("cvss") or {}
    if not cvss.get("score") and isinstance(d.get("cvss_severities"), dict):
        cvss = d["cvss_severities"].get("cvss_v3") or {}
    return {"vuln_id": d.get("ghsa_id"), "aliases": [d["cve_id"]] if d.get("cve_id") else [],
            "source": "ghsa", "title": d.get("summary"), "description": d.get("description"),
            "severity": (d.get("severity") or "").lower().replace("moderate", "medium"),
            "cvss_score": cvss.get("score"), "cvss_vector": cvss.get("vector_string"),
            "cwe": [c.get("cwe_id") for c in d.get("cwes") or [] if c.get("cwe_id")],
            "references": d.get("references") or ([d["html_url"]] if d.get("html_url") else []),
            "published_at": d.get("published_at"), "modified_at": d.get("updated_at"),
            "withdrawn_at": d.get("withdrawn_at"), "affects": afectas}


# ── CSV ──────────────────────────────────────────────────────────────────────

def desde_csv(texto: str) -> list[dict]:
    muestra = texto[:2000]
    lector = csv.DictReader(io.StringIO(texto), delimiter=";" if muestra.count(";") > muestra.count(",") else ",")
    avisos: dict[str, dict] = {}
    for fila in lector:
        fila = {(k or "").strip().lower(): (v or "").strip() for k, v in fila.items()}
        vid = fila.get("vuln_id") or fila.get("id") or fila.get("cve")
        if not vid:
            continue
        a = avisos.setdefault(vid, {"vuln_id": vid, "source": "file", "title": fila.get("title") or None,
                                    "description": fila.get("description") or None,
                                    "severity": (fila.get("severity") or "").lower(),
                                    "cvss_score": float(fila["cvss"]) if fila.get("cvss") else None, "affects": []})
        afecta: dict = {}
        if fila.get("purl"):
            afecta["purl"] = fila["purl"]
        elif fila.get("cpe"):
            c = ids.parsear_cpe(fila["cpe"])
            if c:
                afecta.update(cpe_vendor=c.vendor, cpe_product=c.product)
        elif fila.get("package"):
            afecta.update(ecosystem=fila.get("ecosystem") or "generic", name=fila["package"])
        else:
            continue
        for k in ("introduced", "fixed", "last_affected"):
            if fila.get(k):
                afecta[k] = fila[k]
        if fila.get("versions"):
            afecta["versions"] = [x for x in fila["versions"].replace(";", " ").replace("|", " ").split() if x]
        if fila.get("range"):
            for t in rango_de_texto(fila["range"]):
                a["affects"].append({**afecta, **t, "range_text": fila["range"]})
            continue
        a["affects"].append(afecta)
    return list(avisos.values())


def leer_fichero(contenido: bytes, nombre: Optional[str] = None) -> tuple[str, list[dict]]:
    """(formato, avisos en formato común)."""
    from app.services.cmdb_software import escaneres
    texto = contenido.decode("utf-8-sig", errors="replace")
    base = (nombre or "").lower()
    if texto.lstrip()[:1] in ("{", "["):
        datos = json.loads(texto)
        tipo = escaneres.es_informe(datos)
        if tipo:
            formato, _comps, avisos = escaneres.leer_informe(contenido)
            return formato, avisos
        if isinstance(datos, dict) and "vulnerabilities" in datos and isinstance(datos["vulnerabilities"], list) \
                and datos["vulnerabilities"] and "cve" in datos["vulnerabilities"][0]:
            return "nvd", [desde_nvd(x) for x in datos["vulnerabilities"]]
        if isinstance(datos, dict) and "cve" in datos and "id" in (datos.get("cve") or {}):
            return "nvd", [desde_nvd(datos)]
        lista = datos if isinstance(datos, list) else datos.get("vulns") or datos.get("advisories") or [datos]
        salida, formato = [], "osv"
        for d in lista:
            if not isinstance(d, dict):
                continue
            if d.get("ghsa_id"):
                salida.append(desde_ghsa(d))
                formato = "ghsa"
            elif d.get("affected") is not None or (d.get("id") and d.get("modified")):
                salida.append(desde_osv(d))
            elif d.get("vuln_id"):
                salida.append(d)       # ya viene en el formato común
                formato = "json"
        return formato, salida
    if base.endswith(".csv") or "vuln_id" in texto[:200].lower() or "cve" in texto[:200].lower():
        return "csv", desde_csv(texto)
    from app.core.codigos_de_error import ErrorConCodigo
    raise ErrorConCodigo("sw_formato_no_reconocido", detail="Formato de avisos no reconocido", nombre=nombre or "?")


def importar_fichero_de_avisos(db: Session, org, contenido: bytes, nombre: Optional[str], usuario) -> dict:
    """Lee un fichero de avisos, los guarda, reevalúa y deja la ejecución y la auditoría. No confirma."""
    from app.services.cmdb_software import correlacion
    try:
        formato, lista = leer_fichero(contenido, nombre)
    except Exception as e:  # noqa: BLE001 - fichero ilegible: 422 con código
        raise error(422, "sw_formato_no_reconocido", nombre=nombre or type(e).__name__)
    r = VulnerabilitySyncRun(organization_id=org, source="file", triggered_by="import", created_by=usuario.id)
    db.add(r)
    res = guardar_avisos(db, org, lista, "file" if formato not in ("trivy", "grype") else formato)
    cor = correlacion.reevaluar(db, org, usuario)
    r.status, r.finished_at = "ok", timeutil.utcnow_aware()
    r.vulnerabilities, r.findings_new, r.findings_resolved = res["created"] + res["updated"], cor["findings_new"],         cor["findings_resolved"]
    audit_log(db, usuario, "IMPORT", "sw_vulnerabilities", r.id, nombre,
              metadata={"format": formato, **res, "findings_new": cor["findings_new"]})
    return {"format": formato, **res, **{k: v for k, v in cor.items() if k != "new_ids"}}
