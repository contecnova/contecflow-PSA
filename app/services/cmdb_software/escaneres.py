"""Escáneres: informes de Trivy y Grype, e interfaz para conectores de escaneo.

Un informe de escáner trae a la vez la composición (paquetes con versión) y
las vulnerabilidades que el escáner encontró en ella. `leer_informe` devuelve
``(componentes, avisos)`` con los mismos formatos que `formatos.Resultado` y
`avisos.guardar_avisos`; la importación los aplica a una versión de software
(o a una instancia) y guarda los avisos con su versión exacta afectada.

Syft no necesita parseador propio: produce CycloneDX o SPDX
(`formatos.leer`).

**Conectores de escaneo** (`ConectorDeEscaneo`): algo que, con su
configuración, devuelve instancias de software de una o varias máquinas en el
formato del inventario del agente (`importacion.aplicar_inventario`). Hay uno
de serie, `InventarioJson` (un fichero o una URL que ya devuelve ese formato).
Para añadir otro (SSH, WinRM, la API de un EDR…) basta con registrarlo en
`CONECTORES`.
"""
from __future__ import annotations

import json
from typing import Optional, Protocol

from app.services.cmdb_software.formatos import _componente
from app.services.cmdb_software.identificadores import parsear_purl

_SEV = {"CRITICAL": "critical", "HIGH": "high", "MEDIUM": "medium", "MODERATE": "medium", "LOW": "low",
        "NEGLIGIBLE": "low", "UNKNOWN": "unknown", "INFO": "none", "NONE": "none"}

#: Tipo de Trivy → tipo purl (cuando el paquete no trae su purl).
_TRIVY_TIPO = {"debian": "deb", "ubuntu": "deb", "alpine": "apk", "redhat": "rpm", "centos": "rpm", "rocky": "rpm",
               "alma": "rpm", "amazon": "rpm", "oracle": "rpm", "suse": "rpm", "photon": "rpm", "npm": "npm",
               "yarn": "npm", "pnpm": "npm", "node-pkg": "npm", "pip": "pypi", "pipenv": "pypi", "poetry": "pypi",
               "python-pkg": "pypi", "composer": "composer", "jar": "maven", "pom": "maven", "gradle": "maven",
               "gomod": "golang", "gobinary": "golang", "bundler": "gem", "gemspec": "gem", "cargo": "cargo",
               "rustbinary": "cargo", "nuget": "nuget", "dotnet-core": "nuget"}


def _afecta_exacta(purl: Optional[str], tipo: str, nombre: str, version: Optional[str],
                   arreglo: Optional[str]) -> dict:
    from app.services.cmdb_software.identificadores import clave_de_paquete
    p = parsear_purl(purl) if purl else None
    clave = p.clave() if p else clave_de_paquete(tipo, None, nombre)
    return {"package_key": clave, "ecosystem": p.type if p else tipo, "versions": [version] if version else [],
            "fixed": arreglo or None, "range_text": f"= {version}" + (f" (corregida en {arreglo})" if arreglo else "")}


def trivy(datos: dict) -> tuple[list[dict], list[dict]]:
    componentes: dict[str, dict] = {}
    avisos: dict[str, dict] = {}
    for r in datos.get("Results") or []:
        tipo = _TRIVY_TIPO.get((r.get("Type") or "").lower(), "generic")
        for p in r.get("Packages") or []:
            purl = (p.get("PkgIdentifier") or {}).get("PURL") or p.get("PURL")
            lic = " AND ".join(p.get("Licenses") or []) or None
            c = _componente(p.get("Name") or "", p.get("Version"), tipo, None, purl, lic)
            componentes.setdefault(c["ref"], c)
        for v in r.get("Vulnerabilities") or []:
            purl = (v.get("PkgIdentifier") or {}).get("PURL")
            c = _componente(v.get("PkgName") or "", v.get("InstalledVersion"), tipo, None, purl)
            componentes.setdefault(c["ref"], c)
            vid = v.get("VulnerabilityID")
            if not vid:
                continue
            cvss = None
            for _fuente, m in (v.get("CVSS") or {}).items():
                if m.get("V3Score") is not None:
                    cvss = (m.get("V3Score"), m.get("V3Vector"), "3.1")
                    break
                if m.get("V2Score") is not None and cvss is None:
                    cvss = (m.get("V2Score"), m.get("V2Vector"), "2.0")
            aviso = avisos.setdefault(vid, {
                "vuln_id": vid, "source": "trivy", "title": v.get("Title"), "description": v.get("Description"),
                "severity": _SEV.get((v.get("Severity") or "").upper(), "unknown"),
                "cvss_score": cvss[0] if cvss else None, "cvss_vector": cvss[1] if cvss else None,
                "cvss_version": cvss[2] if cvss else None, "cwe": v.get("CweIDs") or [],
                "references": (v.get("References") or [])[:20], "published_at": v.get("PublishedDate"),
                "modified_at": v.get("LastModifiedDate"), "affects": []})
            aviso["affects"].append(_afecta_exacta(c["purl"], c["type"], c["name"], c["version"],
                                                   (v.get("FixedVersion") or "").split(",")[0].strip() or None))
    return list(componentes.values()), list(avisos.values())


def grype(datos: dict) -> tuple[list[dict], list[dict]]:
    componentes: dict[str, dict] = {}
    avisos: dict[str, dict] = {}
    for m in datos.get("matches") or []:
        a = m.get("artifact") or {}
        tipo = {"deb": "deb", "apk": "apk", "rpm": "rpm", "npm": "npm", "python": "pypi", "java-archive": "maven",
                "go-module": "golang", "gem": "gem", "rust-crate": "cargo", "dotnet": "nuget",
                "php-composer": "composer"}.get(a.get("type") or "", "generic")
        lics = a.get("licenses") or []
        c = _componente(a.get("name") or "", a.get("version"), tipo, None, a.get("purl"),
                        " AND ".join(x if isinstance(x, str) else (x.get("value") or "") for x in lics) or None)
        componentes.setdefault(c["ref"], c)
        v = m.get("vulnerability") or {}
        vid = v.get("id")
        if not vid:
            continue
        relacionados = [r.get("id") for r in m.get("relatedVulnerabilities") or [] if r.get("id")]
        cvss = None
        for x in (v.get("cvss") or []) + [y for r in m.get("relatedVulnerabilities") or [] for y in r.get("cvss") or []]:
            score = (x.get("metrics") or {}).get("baseScore")
            if score is not None:
                cvss = (score, x.get("vector"), x.get("version"))
                break
        desc = v.get("description") or next((r.get("description") for r in m.get("relatedVulnerabilities") or []
                                             if r.get("description")), None)
        aviso = avisos.setdefault(vid, {
            "vuln_id": vid, "aliases": relacionados, "source": "grype", "title": None, "description": desc,
            "severity": _SEV.get((v.get("severity") or "").upper(), "unknown"),
            "cvss_score": cvss[0] if cvss else None, "cvss_vector": cvss[1] if cvss else None,
            "cvss_version": cvss[2] if cvss else None, "references": (v.get("urls") or [])[:20], "affects": []})
        arreglos = (v.get("fix") or {}).get("versions") or []
        aviso["affects"].append(_afecta_exacta(c["purl"], c["type"], c["name"], c["version"],
                                               arreglos[0] if arreglos else None))
    return list(componentes.values()), list(avisos.values())


def es_informe(datos) -> Optional[str]:
    if isinstance(datos, dict):
        if "Results" in datos and ("ArtifactName" in datos or "SchemaVersion" in datos):
            return "trivy"
        if "matches" in datos and ("source" in datos or "descriptor" in datos):
            return "grype"
    return None


def leer_informe(contenido: bytes | str) -> tuple[str, list[dict], list[dict]]:
    texto = contenido.decode("utf-8-sig", errors="replace") if isinstance(contenido, bytes) else contenido
    datos = json.loads(texto)
    tipo = es_informe(datos)
    if tipo == "trivy":
        return ("trivy", *trivy(datos))
    if tipo == "grype":
        return ("grype", *grype(datos))
    raise ValueError("informe_no_reconocido")


# ── Conectores de escaneo ────────────────────────────────────────────────────

class ConectorDeEscaneo(Protocol):
    nombre: str

    def escanear(self, config: dict) -> list[dict]:
        """[{ci: {name|hostname|ip_address}, instances: [...formato del agente...], complete: bool}]"""
        ...


class InventarioJson:
    """Lee el inventario de un JSON (contenido en `config['contenido']` o URL en `config['url']`)."""
    nombre = "inventario_json"

    def escanear(self, config: dict) -> list[dict]:
        contenido = config.get("contenido")
        if contenido is None and config.get("url"):
            import httpx
            r = httpx.get(config["url"], timeout=float(config.get("timeout") or 20),
                          headers={"Authorization": f"Bearer {config['token']}"} if config.get("token") else None)
            r.raise_for_status()
            contenido = r.text
        datos = json.loads(contenido) if isinstance(contenido, str) else contenido
        return datos if isinstance(datos, list) else [datos]


class ConectorRemoto:
    """SSH (Linux), WinRM (Windows) o API de EDR/RMM: `app/services/cmdb_software/escaneos.py`."""

    def __init__(self, tipo: str):
        self.nombre = tipo

    def escanear(self, config: dict) -> list[dict]:
        from app.services.cmdb_software.escaneos import recoger
        return recoger(self.nombre, config)


CONECTORES: dict[str, ConectorDeEscaneo] = {InventarioJson.nombre: InventarioJson(),
                                           "sw_ssh": ConectorRemoto("sw_ssh"), "sw_winrm": ConectorRemoto("sw_winrm"),
                                           "sw_api": ConectorRemoto("sw_api")}
