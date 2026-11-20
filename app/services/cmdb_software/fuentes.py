"""Fuentes de avisos y de ciclo de vida: OSV, NVD, GitHub, EPSS, KEV y endoflife.date.

Todas apagadas por defecto y configurables por empresa (`ajustes`). Solo se
pregunta por lo que la empresa tiene: los purl con versión de sus instancias y
componentes (OSV), los CPE de su catálogo (NVD), sus paquetes por ecosistema
(GitHub) y los CVE de sus hallazgos (EPSS, KEV). `max_queries` limita las
consultas por pasada.

Toda la red pasa por `_get` y `_post` (httpx), que los tests sustituyen.
Cada sincronización deja `sw_sync_runs` con sus cifras o su error.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.models.cmdb_software import (SoftwareComponent, SoftwareInstance, SoftwareProduct, SoftwareVersion,
                                      Vulnerability, VulnerabilitySyncRun)
from app.services.cmdb_software import ajustes, avisos, identificadores as ids
from app.services.cmdb_software.versiones import valida

logger = logging.getLogger(__name__)

FUENTES = ("osv", "nvd", "ghsa", "epss", "kev", "eol")
_ECOSISTEMA_GHSA = {"npm": "npm", "pypi": "pip", "composer": "composer", "maven": "maven", "golang": "go",
                    "gem": "rubygems", "cargo": "rust", "nuget": "nuget", "hex": "erlang", "pub": "pub",
                    "swift": "swift", "github": "actions"}


def _get(url: str, params: Optional[dict] = None, headers: Optional[dict] = None, timeout: float = 20):
    import httpx
    r = httpx.get(url, params=params, headers=headers, timeout=timeout, follow_redirects=True)
    r.raise_for_status()
    return r.json()


def _post(url: str, json_: dict, headers: Optional[dict] = None, timeout: float = 20):
    import httpx
    r = httpx.post(url, json=json_, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _q(db, modelo, org):
    q = db.query(modelo)
    return q.filter(modelo.organization_id == org) if org else q


# ── Lo que tiene la empresa ──────────────────────────────────────────────────

def purls_con_version(db: Session, org) -> list[str]:
    """purl con versión de instancias y componentes (únicos)."""
    salida: set[str] = set()
    prods = {p.id: p for p in _q(db, SoftwareProduct, org).filter(SoftwareProduct.purl_name.isnot(None))}
    for i in _q(db, SoftwareInstance, org).filter(SoftwareInstance.is_active.is_(True)):
        p = prods.get(i.product_id)
        if p and valida(i.version) and p.purl_type != "generic":
            salida.add(ids.construir_purl(p.purl_type, p.purl_namespace, p.purl_name, i.version))
    for c in _q(db, SoftwareComponent, org):
        p = prods.get(c.component_product_id)
        if p and valida(c.component_version) and p.purl_type != "generic":
            salida.add(ids.construir_purl(p.purl_type, p.purl_namespace, p.purl_name, c.component_version))
    return sorted(salida)


def cpes_del_catalogo(db: Session, org) -> list[tuple[str, str]]:
    return sorted({(p.cpe_vendor, p.cpe_product) for p in _q(db, SoftwareProduct, org).filter(
        SoftwareProduct.cpe_vendor.isnot(None), SoftwareProduct.is_active.is_(True))})


def _registro(db, org, fuente, usuario, disparo) -> VulnerabilitySyncRun:
    r = VulnerabilitySyncRun(organization_id=org, source=fuente, triggered_by=disparo,
                             created_by=getattr(usuario, "id", None))
    db.add(r)
    db.flush()
    return r


def _cerrar(r: VulnerabilitySyncRun, estado: str, err: Optional[str] = None) -> None:
    r.status = estado
    r.error = (err or None) and err[:2000]
    r.finished_at = datetime.now(timezone.utc)


# ── OSV ──────────────────────────────────────────────────────────────────────

def sincronizar_osv(db: Session, org, conf: dict, r: VulnerabilitySyncRun) -> None:
    base = conf["osv_url_effective"].rstrip("/")
    purls = purls_con_version(db, org)[: conf["max_queries"] * 100]
    ids_vistos: set[str] = set()
    for i in range(0, len(purls), 100):
        lote = purls[i:i + 100]
        resp = _post(f"{base}/v1/querybatch", {"queries": [{"package": {"purl": p}} for p in lote]},
                     timeout=conf["timeout_seconds"])
        r.queries += 1
        for res in resp.get("results") or []:
            for v in res.get("vulns") or []:
                if v.get("id"):
                    ids_vistos.add(v["id"])
    detalle = []
    for vid in sorted(ids_vistos)[: conf["max_queries"]]:
        d = _get(f"{base}/v1/vulns/{vid}", timeout=conf["timeout_seconds"])
        r.queries += 1
        detalle.append(avisos.desde_osv(d))
    res = avisos.guardar_avisos(db, org, detalle, "osv")
    r.vulnerabilities += res["created"] + res["updated"]


# ── NVD ──────────────────────────────────────────────────────────────────────

def sincronizar_nvd(db: Session, org, conf: dict, r: VulnerabilitySyncRun) -> None:
    url = conf["nvd_url_effective"]
    clave = ajustes.secreto(db, org, "nvd_api_key")
    cabeceras = {"apiKey": clave} if clave else None
    detalle = []
    for vendor, product in cpes_del_catalogo(db, org)[: conf["max_queries"]]:
        inicio = 0
        while True:
            resp = _get(url, params={"virtualMatchString": f"cpe:2.3:a:{vendor}:{product}", "startIndex": inicio,
                                     "resultsPerPage": 2000}, headers=cabeceras, timeout=conf["timeout_seconds"])
            r.queries += 1
            items = resp.get("vulnerabilities") or []
            detalle.extend(avisos.desde_nvd(x) for x in items)
            inicio += len(items)
            if not items or inicio >= int(resp.get("totalResults") or 0) or r.queries >= conf["max_queries"]:
                break
    res = avisos.guardar_avisos(db, org, detalle, "nvd")
    r.vulnerabilities += res["created"] + res["updated"]


# ── GitHub ───────────────────────────────────────────────────────────────────

def sincronizar_ghsa(db: Session, org, conf: dict, r: VulnerabilitySyncRun) -> None:
    base = conf["ghsa_url_effective"].rstrip("/")
    token = ajustes.secreto(db, org, "ghsa_token")
    cabeceras = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        cabeceras["Authorization"] = f"Bearer {token}"
    detalle = []
    paquetes = sorted({(p.purl_type, p.purl_namespace, p.purl_name) for p in _q(db, SoftwareProduct, org).filter(
        SoftwareProduct.purl_type.in_(list(_ECOSISTEMA_GHSA)), SoftwareProduct.is_active.is_(True))},
        key=lambda x: (x[0] or "", x[1] or "", x[2] or ""))
    for tipo, espacio, nombre in paquetes[: conf["max_queries"]]:
        sep = ":" if tipo == "maven" else "/"
        paquete = f"{espacio}{sep}{nombre}" if espacio else nombre
        resp = _get(f"{base}/advisories", params={"ecosystem": _ECOSISTEMA_GHSA[tipo], "affects": paquete,
                                                  "per_page": 100}, headers=cabeceras,
                    timeout=conf["timeout_seconds"])
        r.queries += 1
        detalle.extend(avisos.desde_ghsa(d) for d in resp or [] if isinstance(d, dict))
    res = avisos.guardar_avisos(db, org, detalle, "ghsa")
    r.vulnerabilities += res["created"] + res["updated"]


# ── EPSS y KEV ───────────────────────────────────────────────────────────────

def _cves(db, org) -> list[Vulnerability]:
    import json
    salida = []
    for v in _q(db, Vulnerability, org).all():
        if v.vuln_id.startswith("CVE-") or any(a.startswith("CVE-") for a in json.loads(v.aliases or "[]")):
            salida.append(v)
    return salida


def _cve_de(v: Vulnerability) -> Optional[str]:
    import json
    if v.vuln_id.startswith("CVE-"):
        return v.vuln_id
    return next((a for a in json.loads(v.aliases or "[]") if a.startswith("CVE-")), None)


def sincronizar_epss(db: Session, org, conf: dict, r: VulnerabilitySyncRun) -> None:
    por_cve: dict[str, list[Vulnerability]] = {}
    for v in _cves(db, org):
        por_cve.setdefault(_cve_de(v), []).append(v)
    claves = sorted(k for k in por_cve if k)
    for i in range(0, len(claves), 100):
        resp = _get(conf["epss_url_effective"], params={"cve": ",".join(claves[i:i + 100])},
                    timeout=conf["timeout_seconds"])
        r.queries += 1
        for d in resp.get("data") or []:
            for v in por_cve.get(d.get("cve"), []):
                v.epss_score = float(d.get("epss") or 0)
                v.epss_percentile = float(d.get("percentile") or 0)
                r.vulnerabilities += 1
        if r.queries >= conf["max_queries"]:
            break


def sincronizar_kev(db: Session, org, conf: dict, r: VulnerabilitySyncRun) -> None:
    resp = _get(conf["kev_url_effective"], timeout=conf["timeout_seconds"])
    r.queries += 1
    kev = {}
    for d in resp.get("vulnerabilities") or []:
        if d.get("cveID"):
            kev[d["cveID"]] = d.get("dateAdded")
    for v in _cves(db, org):
        cve = _cve_de(v)
        en_kev = cve in kev
        if en_kev != bool(v.kev):
            v.kev = en_kev
            r.vulnerabilities += 1
        if en_kev and kev[cve]:
            try:
                v.kev_added = date.fromisoformat(kev[cve][:10])
            except ValueError:
                pass


# ── endoflife.date ───────────────────────────────────────────────────────────

#: Producto del catálogo (clave conocida o nombre) → producto de endoflife.date.
EOL_PRODUCTOS = {"php": "php", "nginx": "nginx", "apache": "apache-http-server", "tomcat": "tomcat",
                 "mysql": "mysql", "mariadb": "mariadb", "postgresql": "postgresql", "mssql": "mssql-server",
                 "mongodb": "mongodb", "redis": "redis", "openssl": "openssl", "nodejs": "nodejs", "python": "python",
                 "java": "eclipse-temurin", "dotnet": "dotnet", "haproxy": "haproxy", "rabbitmq": "rabbitmq",
                 "elasticsearch": "elasticsearch", "kubernetes": "kubernetes", "wordpress": "wordpress",
                 "docker": "docker-engine", "iis": "iis"}


def _fecha_o_bool(v) -> Optional[date]:
    if isinstance(v, str) and len(v) >= 10:
        try:
            return date.fromisoformat(v[:10])
        except ValueError:
            return None
    return None


def aplicar_ciclos(db: Session, org, p: SoftwareProduct, ciclos: list[dict], fuente: str = "endoflife") -> int:
    """Ciclos al estilo endoflife.date ``[{cycle, releaseDate, support, eol, extendedSupport, latest}]``."""
    n = 0
    for c in ciclos or []:
        rama = str(c.get("cycle") or "").strip()
        if not rama:
            continue
        v = _q(db, SoftwareVersion, org).filter(SoftwareVersion.product_id == p.id,
                                                SoftwareVersion.version == rama).first()
        if v is None:
            v = SoftwareVersion(organization_id=org, product_id=p.id, version=rama)
            db.add(v)
        if v.lifecycle_source == "manual":
            continue     # lo puesto a mano manda
        v.cycle = rama
        v.release_date = _fecha_o_bool(c.get("releaseDate")) or v.release_date
        v.support_end = _fecha_o_bool(c.get("support")) or v.support_end
        v.eol_date = _fecha_o_bool(c.get("eol")) or v.eol_date
        v.extended_support_end = _fecha_o_bool(c.get("extendedSupport")) or v.extended_support_end
        v.lifecycle_source = fuente
        n += 1
    db.flush()
    return n


def sincronizar_eol(db: Session, org, conf: dict, r: VulnerabilitySyncRun) -> None:
    base = conf["eol_url_effective"].rstrip("/")
    for p in _q(db, SoftwareProduct, org).filter(SoftwareProduct.is_active.is_(True)).all():
        clave = ids.conocido(p.name) or ids.conocido(p.purl_name)
        destino = EOL_PRODUCTOS.get(clave or "")
        if not destino:
            continue
        ciclos = _get(f"{base}/{destino}.json", timeout=conf["timeout_seconds"])
        r.queries += 1
        r.vulnerabilities += aplicar_ciclos(db, org, p, ciclos if isinstance(ciclos, list) else [])
        if r.queries >= conf["max_queries"]:
            break


_FUNCIONES = {"osv": sincronizar_osv, "nvd": sincronizar_nvd, "ghsa": sincronizar_ghsa, "epss": sincronizar_epss,
              "kev": sincronizar_kev, "eol": sincronizar_eol}


def sincronizar(db: Session, org, fuentes: Optional[list[str]] = None, usuario=None, disparo: str = "manual",
                estricto: bool = True) -> list[dict]:
    """Sincroniza las fuentes pedidas (o todas las activas) y reevalúa. Devuelve un resumen por fuente.

    `estricto`: pedir una fuente apagada es un error (desde la pantalla); en
    el trabajo de fondo se salta.
    """
    conf = ajustes.leer(db, org)
    activas = [f for f in FUENTES if conf.get(f"{f}_enabled")]
    pedidas = fuentes or activas
    salida = []
    for f in pedidas:
        if f not in FUENTES:
            raise error(422, "sw_valor_no_valido", campo="source", valor=f)
        if f not in activas:
            if estricto:
                raise error(422, "sw_fuente_desactivada", fuente=f)
            continue
        r = _registro(db, org, f, usuario, disparo)
        try:
            with db.begin_nested():
                _FUNCIONES[f](db, org, conf, r)
            _cerrar(r, "ok")
        except Exception as e:  # noqa: BLE001 - una fuente caída no para las demás
            logger.warning("sincronizacion %s de %s: %s", f, org, e)
            _cerrar(r, "error", f"{type(e).__name__}: {e}")
        salida.append({"source": f, "status": r.status, "queries": r.queries, "vulnerabilities": r.vulnerabilities,
                       "error": r.error})
    c = ajustes.fila(db, org, crear=True)
    c.last_sync_at = datetime.now(timezone.utc)
    c.last_sync_status = "error" if any(s["status"] == "error" for s in salida) else "ok"
    db.flush()
    return salida


def probar(db: Session, org, fuente: str) -> dict:
    """Prueba de conexión de una fuente (una consulta mínima), sin guardar nada."""
    conf = ajustes.leer(db, org)
    try:
        if fuente == "osv":
            _post(f"{conf['osv_url_effective'].rstrip('/')}/v1/query",
                  {"package": {"purl": "pkg:npm/lodash@4.17.20"}}, timeout=conf["timeout_seconds"])
        elif fuente == "nvd":
            clave = ajustes.secreto(db, org, "nvd_api_key")
            _get(conf["nvd_url_effective"], params={"cveId": "CVE-2021-44228"},
                 headers={"apiKey": clave} if clave else None, timeout=conf["timeout_seconds"])
        elif fuente == "ghsa":
            token = ajustes.secreto(db, org, "ghsa_token")
            _get(f"{conf['ghsa_url_effective'].rstrip('/')}/advisories", params={"per_page": 1},
                 headers={"Authorization": f"Bearer {token}"} if token else None, timeout=conf["timeout_seconds"])
        elif fuente == "epss":
            _get(conf["epss_url_effective"], params={"cve": "CVE-2021-44228"}, timeout=conf["timeout_seconds"])
        elif fuente == "kev":
            _get(conf["kev_url_effective"], timeout=conf["timeout_seconds"])
        elif fuente == "eol":
            _get(f"{conf['eol_url_effective'].rstrip('/')}/nginx.json", timeout=conf["timeout_seconds"])
        else:
            raise error(422, "sw_valor_no_valido", campo="source", valor=fuente)
    except Exception as e:  # noqa: BLE001
        if getattr(e, "code", None) == "sw_valor_no_valido":
            raise
        return {"ok": False, "error": f"{type(e).__name__}"}
    return {"ok": True}
