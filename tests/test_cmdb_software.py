"""CMDB de software, composición y vulnerabilidades (19-11-2026, rev. 190).

Lo que se mide (fuentes externas simuladas: ninguna llamada de red):
- identificadores (purl, CPE, clave de conciliación y alias conocidos);
- comparador de versiones y rangos (semver, PHP, Debian, pre-versiones);
- parseadores de SBOM y dependencias (CycloneDX, SPDX, composer.lock,
  package-lock v2, requirements, poetry.lock, pom.xml, go.mod, go.sum,
  Gemfile.lock) e informes de Trivy/Grype;
- configuración: nginx/php.ini y que los secretos nunca se guardan;
- licencias: familias y conflictos;
- de punta a punta por API: catálogo, instancia con configuración, SBOM,
  avisos (OSV simulado y fichero NVD), correlación, «dónde se usa»,
  impacto, SLA, remediación, excepción con segregación y caducidad,
  reevaluación que verifica la corrección, controles de cumplimiento,
  retención y guardas por rol.
"""
from __future__ import annotations

import io
import json
from datetime import date, timedelta

import pytest

from app.services.cmdb_software import configuracion as cfg
from app.services.cmdb_software import formatos, identificadores as ids, licencias, versiones
from tests.conftest import auth

B = "/api/v1/cmdb/software"


# ── Unitarios ────────────────────────────────────────────────────────────────

def test_purl_y_cpe():
    p = ids.parsear_purl("pkg:npm/%40babel/core@7.22.0")
    assert (p.type, p.namespace, p.name, p.version) == ("npm", "@babel", "core", "7.22.0")
    assert ids.parsear_purl("pkg:pypi/Django_Rest@1.0").clave() == "pypi//django-rest"
    c = ids.parsear_cpe("cpe:2.3:a:php:php:8.1.27:*:*:*:*:*:*:*")
    assert (c.vendor, c.product, c.version) == ("php", "php", "8.1.27")
    # php-fpm, php y PHP acaban en el mismo producto
    assert ids.clave_de_producto("php-fpm") == ids.clave_de_producto("PHP") == "cpe:php:php"
    assert ("nginx", "nginx") in ids.cpes_de("nginx", "f5", "nginx")


@pytest.mark.parametrize("a,b,esperado", [
    ("8.1.27", "8.2", -1), ("1.0", "1.0.0", 0), ("1.0.0-rc1", "1.0.0", -1), ("v1.2.3", "1.2.3", 0),
    ("1:1.18.0-6ubuntu14.4", "1.24.0", 1), ("2.17.1", "2.17.0", 1), ("1.0.post1", "1.0.1", -1),
    ("5.3.18.RELEASE", "5.3.18", 0), ("10.0", "9.9", 1),
])
def test_comparar_versiones(a, b, esperado):
    assert versiones.comparar(a, b) == esperado


def test_rangos():
    assert versiones.en_rango("4.17.20", introduced="0", fixed="4.17.21")
    assert not versiones.en_rango("4.17.21", introduced="0", fixed="4.17.21")
    assert versiones.en_rango("1.2", last_affected="1.2")
    assert not versiones.en_rango("1.0", introduced="1.0", introduced_inclusive=False, fixed="2")
    assert versiones.en_rango("3.0.1", exactas=["3.0.1"])
    assert not versiones.en_rango("3.0.1")                         # sin límites no se afirma
    assert versiones.rango_de_texto(">= 1.0, < 1.2.5") == [{"introduced": "1.0", "introduced_inclusive": True,
                                                             "fixed": "1.2.5"}]
    assert versiones.cumple("8.1.27", "lt", "8.2") and versiones.cumple("8.1.27", "prefix", "8.1")


def test_cyclonedx_con_arbol():
    bom = {"bomFormat": "CycloneDX", "metadata": {"component": {"name": "portal", "version": "2.3", "bom-ref": "app"}},
           "components": [
               {"bom-ref": "laravel", "name": "framework", "group": "laravel", "version": "10.2.0",
                "purl": "pkg:composer/laravel/framework@10.2.0", "licenses": [{"license": {"id": "MIT"}}]},
               {"bom-ref": "monolog", "name": "monolog", "group": "monolog", "version": "3.4.0",
                "purl": "pkg:composer/monolog/monolog@3.4.0"}],
           "dependencies": [{"ref": "app", "dependsOn": ["laravel"]}, {"ref": "laravel", "dependsOn": ["monolog"]}]}
    r = formatos.leer(json.dumps(bom))
    por_nombre = {c["name"]: c for c in r.componentes}
    assert r.formato == "cyclonedx" and por_nombre["framework"]["direct"] is True
    assert por_nombre["monolog"]["direct"] is False and por_nombre["monolog"]["via"] == "laravel"
    assert por_nombre["framework"]["license"] == "MIT"


def test_ficheros_de_dependencias():
    composer = {"content-hash": "x", "packages": [{"name": "guzzlehttp/guzzle", "version": "v7.5.0", "license": ["MIT"],
                                                   "require": {"psr/http-message": "^1"}},
                                                  {"name": "psr/http-message", "version": "1.1"}], "packages-dev": []}
    r = formatos.leer(json.dumps(composer), "composer.lock")
    assert {(c["namespace"], c["name"], c["version"]) for c in r.componentes} == {("guzzlehttp", "guzzle", "7.5.0"),
                                                                                  ("psr", "http-message", "1.1")}
    lock = {"lockfileVersion": 3, "packages": {"": {"dependencies": {"express": "^4"}},
                                               "node_modules/express": {"version": "4.18.2", "dependencies": {"qs": "*"}},
                                               "node_modules/qs": {"version": "6.11.0"}}}
    r = formatos.leer(json.dumps(lock), "package-lock.json")
    qs = next(c for c in r.componentes if c["name"] == "qs")
    assert qs["direct"] is False and qs["via"] == "node_modules/express"
    r = formatos.leer("requests==2.31.0\nflask>=2\n# comentario\n", "requirements.txt")
    assert [(c["name"], c["version"]) for c in r.componentes] == [("requests", "2.31.0"), ("flask", None)]
    poetry = '[[package]]\nname = "Django"\nversion = "4.2.1"\ncategory = "main"\n\n[metadata]\npython-versions = "^3.11"\n'
    assert formatos.leer(poetry, "poetry.lock").componentes[0]["purl"] == "pkg:pypi/Django@4.2.1"
    pom = ('<project xmlns="http://maven.apache.org/POM/4.0.0"><artifactId>app</artifactId><properties>'
           '<log4j.version>2.14.1</log4j.version></properties><dependencies><dependency><groupId>org.apache.logging.log4j'
           '</groupId><artifactId>log4j-core</artifactId><version>${log4j.version}</version></dependency></dependencies></project>')
    c = formatos.leer(pom, "pom.xml").componentes[0]
    assert (c["namespace"], c["name"], c["version"], c["type"]) == ("org.apache.logging.log4j", "log4j-core", "2.14.1", "maven")
    gomod = "module x\n\nrequire (\n\tgithub.com/gin-gonic/gin v1.9.0\n\tgolang.org/x/net v0.7.0 // indirect\n)\n"
    r = formatos.leer(gomod, "go.mod")
    assert [c["direct"] for c in r.componentes] == [True, False]
    gosum = "github.com/a/b v1.0.0 h1:abc=\ngithub.com/a/b v1.0.0/go.mod h1:def=\n"
    assert len(formatos.leer(gosum, "go.sum").componentes) == 1
    gem = "GEM\n  remote: x\n  specs:\n    rails (7.0.4)\n      actionpack (= 7.0.4)\n    actionpack (7.0.4)\n\nDEPENDENCIES\n  rails\n"
    r = formatos.leer(gem, "Gemfile.lock")
    assert {c["name"]: c["direct"] for c in r.componentes} == {"rails": True, "actionpack": False}
    with pytest.raises(formatos.FormatoNoReconocido):
        formatos.leer("nada que ver", "x.bin")


def test_spdx_json():
    doc = {"spdxVersion": "SPDX-2.3", "documentDescribes": ["SPDXRef-app"],
           "packages": [{"SPDXID": "SPDXRef-app", "name": "app", "versionInfo": "1"},
                        {"SPDXID": "SPDXRef-lodash", "name": "lodash", "versionInfo": "4.17.20",
                         "licenseConcluded": "MIT",
                         "externalRefs": [{"referenceType": "purl", "referenceLocator": "pkg:npm/lodash@4.17.20"}]}],
           "relationships": [{"spdxElementId": "SPDXRef-app", "relationshipType": "DEPENDS_ON",
                              "relatedSpdxElement": "SPDXRef-lodash"}]}
    r = formatos.leer(json.dumps(doc))
    assert r.raiz["name"] == "app" and r.componentes[0]["purl"] == "pkg:npm/lodash@4.17.20"


def test_informes_de_escaner():
    from app.services.cmdb_software import escaneres
    trivy = {"SchemaVersion": 2, "ArtifactName": "img", "Results": [{"Type": "debian", "Packages": [], "Vulnerabilities": [
        {"VulnerabilityID": "CVE-2023-0001", "PkgName": "openssl", "InstalledVersion": "1.1.1n-0", "FixedVersion": "1.1.1t-0",
         "Severity": "HIGH", "CVSS": {"nvd": {"V3Score": 7.5, "V3Vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H"}}}]}]}
    tipo, comps, avisos = escaneres.leer_informe(json.dumps(trivy))
    assert tipo == "trivy" and avisos[0]["cvss_score"] == 7.5 and avisos[0]["affects"][0]["versions"] == ["1.1.1n-0"]
    grype = {"source": {}, "matches": [{"vulnerability": {"id": "GHSA-x", "severity": "Critical", "fix": {"versions": ["2.0"]}},
                                        "artifact": {"name": "lib", "version": "1.0", "type": "npm", "purl": "pkg:npm/lib@1.0"}}]}
    tipo, comps, avisos = escaneres.leer_informe(json.dumps(grype))
    assert tipo == "grype" and avisos[0]["severity"] == "critical" and comps[0]["purl"] == "pkg:npm/lib@1.0"


def test_configuracion_y_secretos():
    nginx = ("load_module modules/ngx_http_geoip_module.so;\nhttp {\n server {\n  listen 443 ssl;\n"
             "  ssl_protocols TLSv1 TLSv1.2;\n  server_tokens on;\n  ssl_certificate_key /etc/ssl/k.pem;\n"
             "  proxy_pass http://127.0.0.1:9000;\n }\n}\n")
    d = cfg.parsear_nginx(nginx)
    assert d["ports"] == [443] and d["tls"] and d["tls_protocols"] == ["TLSv1", "TLSv1.2"]
    assert d["modules"] == ["ngx_http_geoip_module"] and d["upstreams"] == ["http://127.0.0.1:9000"]
    secreta, _ = cfg.interpretar(texto="DB_PASSWORD=supersecreta\nAPP_URL=https://x\n"
                                 "DATABASE_URL=mysql://app:otraclave@db/x\n", formato="env")
    texto = json.dumps(secreta)
    assert "supersecreta" not in texto and "otraclave" not in texto and secreta["APP_URL"] == "https://x"
    assert cfg.enmascarar({"ssl_certificate_key": "/etc/k.pem"})["ssl_certificate_key"] == "/etc/k.pem"
    fallos = cfg.evaluar_linea_base(d, [{"key": "tls_protocols", "op": "not_contains", "value": "TLSv1 ", "severity": "high"},
                                        {"key": "server_tokens", "op": "eq", "value": "off", "severity": "low"}])
    # La configuración tiene TLSv1 activo: la regla «no contiene TLSv1» también falla.
    assert [f["key"] for f in fallos] == ["tls_protocols", "server_tokens"]
    php = cfg.parsear_ini("[PHP]\nexpose_php = On\n[mail function]\nSMTP=localhost\n")
    assert php["expose_php"] == "On"


def test_licencias():
    assert licencias.familia_de_expresion("MIT OR GPL-3.0") == "permissive"
    assert licencias.familia_de_expresion("MIT AND GPL-3.0-only") == "strong_copyleft"
    assert licencias.familia_de("LGPL-2.1") == "weak_copyleft"
    assert licencias.evaluar("AGPL-3.0", "saas", "in_house")["reason"] == "network_copyleft_service"
    assert licencias.evaluar("GPL-2.0", "distributed", "in_house")["reason"] == "copyleft_distributed"
    assert licencias.evaluar("MIT", "saas", "in_house") is None
    assert licencias.evaluar("WTFPL", None, None, prohibidas="WTFPL")["level"] == "conflict"


# ── De punta a punta ─────────────────────────────────────────────────────────

ORG = "1"


@pytest.fixture
def ci_web(db):
    from app.models.service_desk.cmdb import ConfigurationItem
    from app.models.service_desk._enums import CIType
    ci = ConfigurationItem(organization_id=ORG, code="CI-SW-1", name="web-01", ci_type=CIType.server,
                           hostname="web-01.local", ip_address="10.0.0.5", criticality="high")
    db.add(ci)
    db.commit()
    return ci


def _crear(client, token, ruta, datos, codigo=201):
    r = client.post(f"{B}{ruta}", json=datos, headers=auth(token))
    assert r.status_code == codigo, r.text
    return r.json()["data"]


def test_de_punta_a_punta(client, db, admin_token, pm_token, ci_web, monkeypatch):
    # Catálogo: un software propio y nginx (base conocida: CPE y purl solos)
    portal = _crear(client, pm_token, "/products", {"name": "Portal clientes", "origin": "in_house",
                                                     "category": "application", "distribution": "saas"})
    nginx = _crear(client, pm_token, "/products", {"name": "nginx"})
    assert nginx["cpe_vendor"] == "f5" and nginx["category"] == "web_server"
    dup = client.post(f"{B}/products", json={"name": "NGINX"}, headers=auth(pm_token))
    assert dup.status_code == 409 and dup.json()["code"] == "sw_producto_duplicado"

    # Instancia de nginx en web-01 con su configuración: los secretos no se guardan
    inst = _crear(client, pm_token, "/instances", {
        "product_id": nginx["id"], "version": "1.18.0", "ci_id": ci_web.id, "environment": "prod", "exposure": "internet",
        "config_text": "server {\n listen 443 ssl;\n ssl_protocols TLSv1 TLSv1.2;\n}\n", "config_format": "nginx"})
    assert inst["config"]["ports"] == [443]
    r = client.patch(f"{B}/instances/{inst['id']}", json={"config": {"listen": "443", "api_token": "abc123secreto"}},
                     headers=auth(pm_token))
    assert r.status_code == 200 and "abc123secreto" not in r.text
    from app.models.cmdb_software import SoftwareConfigSnapshot
    assert all("abc123secreto" not in (s.config_json or "") for s in db.query(SoftwareConfigSnapshot).all())

    # Versión del portal con su composición (SBOM): lodash vulnerable
    v = _crear(client, pm_token, f"/products/{portal['id']}/versions", {"version": "2.3.0"})
    bom = {"bomFormat": "CycloneDX", "components": [
        {"name": "lodash", "version": "4.17.20", "purl": "pkg:npm/lodash@4.17.20", "licenses": [{"license": {"id": "MIT"}}]},
        {"name": "php", "version": "8.1.27", "type": "platform"}]}
    r = client.post(f"{B}/versions/{v['id']}/import", files={"file": ("bom.json", json.dumps(bom), "application/json")},
                    headers=auth(pm_token))
    assert r.status_code == 200 and r.json()["data"]["total"] == 2, r.text
    _crear(client, pm_token, "/instances", {"product_id": portal["id"], "version_id": v["id"], "ci_id": ci_web.id,
                                            "environment": "prod", "exposure": "internet"})

    # Avisos: OSV simulado (lodash) y fichero NVD (nginx por CPE)
    from app.services.cmdb_software import fuentes
    llamadas = []

    def falso_post(url, json_, headers=None, timeout=20):
        llamadas.append(url)
        return {"results": [{"vulns": [{"id": "GHSA-35jh-r3h4-6jhm"}]} for _ in json_["queries"]]}

    def falso_get(url, params=None, headers=None, timeout=20):
        llamadas.append(url)
        return {"id": "GHSA-35jh-r3h4-6jhm", "aliases": ["CVE-2021-23337"], "summary": "Command injection in lodash",
                "modified": "2021-02-15T00:00:00Z",
                "severity": [{"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L/PR:H/UI:N/S:U/C:H/I:H/A:H"}],
                "affected": [{"package": {"ecosystem": "npm", "name": "lodash"},
                              "ranges": [{"type": "SEMVER", "events": [{"introduced": "0"}, {"fixed": "4.17.21"}]}]}]}
    monkeypatch.setattr(fuentes, "_post", falso_post)
    monkeypatch.setattr(fuentes, "_get", falso_get)
    assert client.put(f"{B}/config", json={"osv_enabled": True, "sla_days_high": 30, "nvd_api_key": "clave-nvd"},
                      headers=auth(admin_token)).status_code == 200
    conf = client.get(f"{B}/config", headers=auth(admin_token)).json()["data"]
    assert conf["nvd_api_key_set"] is True and "clave-nvd" not in json.dumps(conf)
    r = client.post(f"{B}/sync", json={"sources": ["osv"]}, headers=auth(pm_token))
    assert r.status_code == 200 and r.json()["data"]["sources"][0]["status"] == "ok", r.text
    assert any("querybatch" in u for u in llamadas)

    nvd = {"vulnerabilities": [{"cve": {"id": "CVE-2021-23017", "descriptions": [{"lang": "en", "value": "nginx resolver"}],
                                        "metrics": {"cvssMetricV31": [{"type": "Primary", "cvssData": {
                                            "baseScore": 9.8, "baseSeverity": "CRITICAL", "vectorString": "CVSS:3.1/AV:N"}}]},
                                        "configurations": [{"nodes": [{"cpeMatch": [{
                                            "vulnerable": True, "criteria": "cpe:2.3:a:f5:nginx:*:*:*:*:*:*:*:*",
                                            "versionStartIncluding": "0.6.18", "versionEndExcluding": "1.20.1"}]}]}]}}]}
    r = client.post(f"{B}/vulnerabilities/import", files={"file": ("nvd.json", json.dumps(nvd), "application/json")},
                    headers=auth(pm_token))
    assert r.status_code == 200 and r.json()["data"]["format"] == "nvd", r.text

    hallazgos = client.get(f"{B}/findings", headers=auth(pm_token)).json()["items"]
    por_vuln = {h["vuln_id"]: h for h in hallazgos}
    assert set(por_vuln) == {"GHSA-35jh-r3h4-6jhm", "CVE-2021-23017"}
    critico = por_vuln["CVE-2021-23017"]
    assert critico["ci_name"] == "web-01" and critico["severity"] == "critical" and critico["fixed_version"] == "1.20.1"
    assert critico["sla_due_at"] and critico["priority_score"] > 70
    lodash = por_vuln["GHSA-35jh-r3h4-6jhm"]
    assert lodash["parent_product_name"] == "Portal clientes" and lodash["severity"] == "high"

    # ¿Dónde está nginx? ¿Qué usa PHP < 8.2?
    d = client.get(f"{B}/where-used", params={"q": "nginx"}, headers=auth(pm_token)).json()["data"]
    assert d["summary"]["instances"] == 1 and d["machines"][0]["name"] == "web-01"
    d = client.get(f"{B}/where-used", params={"q": "php < 8.2"}, headers=auth(pm_token)).json()["data"]
    assert d["software"][0]["product_name"] == "Portal clientes" and d["software"][0]["machines"][0]["name"] == "web-01"
    assert client.get(f"{B}/where-used", params={"q": "php < 8.1"}, headers=auth(pm_token)).json()["data"]["summary"][
        "software"] == 0

    # Impacto del aviso de lodash: software, máquina
    imp = client.get(f"{B}/impact", params={"finding_id": lodash["id"]}, headers=auth(pm_token)).json()["data"]
    assert imp["software"][0]["version"] == "2.3.0" and imp["machines"][0]["name"] == "web-01"

    # Árbol, vista por máquina, cuadro de mando, grafo
    arbol = client.get(f"{B}/versions/{v['id']}/tree", headers=auth(pm_token)).json()["data"]
    assert arbol["summary"]["components"] == 2
    maq = client.get(f"{B}/machines/{ci_web.id}", headers=auth(pm_token)).json()["data"]
    assert len(maq["instances"]) == 2 and maq["findings_by_severity"]
    tablero = client.get(f"{B}/dashboard", headers=auth(pm_token)).json()["data"]
    assert tablero["findings_live"] == 2 and tablero["findings_kev"] == 0
    g = client.get(f"{B}/graph", params={"ci_id": ci_web.id}, headers=auth(pm_token)).json()["data"]
    assert any(e["rel_type"] == "hosts" for e in g["edges"])

    # Remediación: cambio con los CIs afectados
    r = client.post(f"{B}/findings/{critico['id']}/remediate", json={"type": "change"}, headers=auth(pm_token))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["finding"]["status"] == "in_progress" and r.json()["data"]["finding"]["change_id"]

    # Excepción: quien la pide no la aprueba; la aprueba otro admin; caduca y reabre
    caduca = (date.today() + timedelta(days=30)).isoformat()
    e = _crear(client, admin_token, f"/findings/{lodash['id']}/exceptions",
               {"reason": "Mitigado por WAF y sin entrada de usuario", "expires_at": caduca})
    propia = client.post(f"{B}/exceptions/{e['id']}/approve", json={}, headers=auth(admin_token))
    assert propia.status_code == 403 and propia.json()["code"] == "sw_excepcion_propia"
    assert client.post(f"{B}/exceptions/{e['id']}/approve", json={}, headers=auth(pm_token)).status_code == 403
    from app.models.cmdb_software import VulnerabilityException, VulnerabilityFinding
    from app.services.cmdb_software import gestion
    ex = db.get(VulnerabilityException, e["id"])
    from app.models.user import User
    otro = db.query(User).filter(User.id == "pm-test-id").first()
    gestion._aplicar_decision(db, ex, True, otro, "ok")
    db.commit()
    assert db.get(VulnerabilityFinding, lodash["id"]).status == "accepted"
    ex.expires_at = date.today() - timedelta(days=1)
    db.commit()
    assert gestion.caducar_excepciones(db, ORG) == 1
    db.commit()
    assert db.get(VulnerabilityFinding, lodash["id"]).status == "open"

    # Corregir: nginx a 1.24.0 → el hallazgo se cierra verificado por la reevaluación
    r = client.patch(f"{B}/instances/{inst['id']}", json={"version": "1.24.0"}, headers=auth(pm_token))
    assert r.status_code == 200
    f = db.get(VulnerabilityFinding, critico["id"])
    db.refresh(f)
    assert f.status == "resolved" and f.verified_at is not None

    # Cumplimiento y retención
    from app.services.informe_de_cumplimiento import generar
    ids_ = {c["id"] for c in generar(db, ORG)["controls"]}
    assert {"sw_critical_vulns_sla", "sw_eol_production", "sw_ci_without_owner", "sw_vuln_exceptions",
            "sw_vuln_feed"} <= ids_
    from app.db.bloqueo_legal import TIPOS
    assert {"sw_config_snapshots", "sw_findings"} <= set(TIPOS)

    # Auditoría
    from app.models.enterprise import AuditLog
    recursos = {a.resource for a in db.query(AuditLog).filter(AuditLog.resource.like("sw_%"))}
    assert {"sw_product", "sw_instance", "sw_instance_config", "sw_components", "sw_finding", "sw_vuln_exception",
            "sw_config"} <= recursos


def test_guardas_por_rol(client, dev_token, pm_token):
    assert client.get(f"{B}/dashboard", headers=auth(dev_token)).status_code == 403
    assert client.get(f"{B}/products", headers=auth(dev_token)).status_code == 403
    assert client.get(f"{B}/config", headers=auth(pm_token)).status_code == 403


def test_csv_y_eol(client, db, pm_token, ci_web):
    csv_ = ("name,version,host,environment,install_path,eol_date\n"
            "PHP,7.4.33,web-01,prod,/usr/bin/php,2022-11-28\n")
    r = client.post(f"{B}/import/csv", files={"file": ("cat.csv", io.BytesIO(csv_.encode()), "text/csv")},
                    headers=auth(pm_token))
    assert r.status_code == 200 and r.json()["data"]["instances_created"] == 1, r.text
    eol = client.get(f"{B}/analysis/eol", params={"prod_only": True}, headers=auth(pm_token)).json()["data"]
    assert eol["instances"][0]["lifecycle"] == "eol"


def test_herramienta_de_nexus_con_politica():
    from app.services.ai_chat.tool_execution.executor import _HANDLERS
    from app.services.ai_chat.tool_execution.politica import POLITICAS
    from app.services.ai_chat.tool_execution.schema import AGENT_TOOLS
    assert "search_software_inventory" in _HANDLERS and "search_software_inventory" in POLITICAS
    assert any(t["name"] == "search_software_inventory" for t in AGENT_TOOLS)
