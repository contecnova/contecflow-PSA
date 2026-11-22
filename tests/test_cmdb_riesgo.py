"""Índice de riesgo y gestión de vulnerabilidades (22-11-2026, rev. 194).

Lo que se mide (sin red: las APIs de terceros se simulan con sus formatos públicos):
- ajustes: valores por defecto, validación (pesos que suman 1, rangos) y auditoría;
- fórmula: riesgo de un hallazgo y saturación de los factores;
- de punta a punta por API: índice con desglose, recálculo e histórico,
  comparación, plan de reducción, eventos, métricas, superficies, vistas
  guardadas con propietario, exposición por puertos públicos, control
  compensatorio (baja la prioridad sin cerrar, revocación, caducidad),
  intentos de explotación (dedup y casado), importación de terceros con
  deduplicación frente a la correlación y cierre por importación completa,
  informes programados, avisos, cumplimiento y retención;
- parsers de Trend Vision One, Defender VM, Qualys (con base de conocimiento),
  Tenable y Rapid7, y conectores por API simulados.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from app.services.cmdb_software.riesgo import ajustes as aj
from app.services.cmdb_software.riesgo import calculo, terceros
from tests.conftest import auth

B = "/api/v1/cmdb/software"
R = f"{B}/risk"
ORG = "1"

NVD = {"vulnerabilities": [{"cve": {
    "id": "CVE-2021-23017", "descriptions": [{"lang": "en", "value": "nginx resolver"}],
    "metrics": {"cvssMetricV31": [{"type": "Primary", "cvssData": {"baseScore": 9.8, "baseSeverity": "CRITICAL",
                                                                    "vectorString": "CVSS:3.1/AV:N"}}]},
    "configurations": [{"nodes": [{"cpeMatch": [{"vulnerable": True, "criteria": "cpe:2.3:a:f5:nginx:*:*:*:*:*:*:*:*",
                                                 "versionStartIncluding": "0.6.18",
                                                 "versionEndExcluding": "1.20.1"}]}]}]}}]}


# ── Unitarios ────────────────────────────────────────────────────────────────

def test_ajustes_por_defecto_validos():
    s = aj.validar(aj.DEFECTO)
    assert abs(sum(s["weights"].values()) - 1) < 1e-9
    assert set(s["weights"]) == set(aj.FACTORES)


def test_ajustes_pesos_que_no_suman():
    malo = json.loads(json.dumps(aj.DEFECTO))
    malo["weights"]["vulnerabilities"] = 0.9
    with pytest.raises(Exception) as e:
        aj.validar(malo)
    assert getattr(e.value, "code", None) == "swr_pesos_no_suman"
    malo = json.loads(json.dumps(aj.DEFECTO))
    malo["impact_ranges"] = {"high_from": 30, "medium_from": 40}
    with pytest.raises(Exception) as e:
        aj.validar(malo)
    assert getattr(e.value, "code", None) == "swr_rangos_de_impacto"


class _V:
    def __init__(self, cvss=None, kev=False, epss=None, severity="high"):
        self.cvss_score, self.kev, self.epss_score, self.severity = cvss, kev, epss, severity


class _F:
    def __init__(self, dias=0, intentos=0, posible=False, severity="high"):
        self.first_seen_at = datetime.now(timezone.utc) - timedelta(days=dias)
        self.exploit_attempts = intentos
        self.severity = severity
        self.score_detail = json.dumps({"possible": True}) if posible else None


def test_riesgo_de_hallazgo():
    c = json.loads(json.dumps(aj.DEFECTO))
    base, _ = calculo.riesgo_de_hallazgo(c, _V(cvss=7.0), _F(), "high", "internal")
    kev, _ = calculo.riesgo_de_hallazgo(c, _V(cvss=7.0, kev=True), _F(), "high", "internal")
    internet, _ = calculo.riesgo_de_hallazgo(c, _V(cvss=7.0), _F(), "high", "internet")
    viejo, _ = calculo.riesgo_de_hallazgo(c, _V(cvss=7.0), _F(dias=400), "high", "internal")
    mitigado, det = calculo.riesgo_de_hallazgo(c, _V(cvss=7.0), _F(), "high", "internal", reduccion=0.5)
    posible, _ = calculo.riesgo_de_hallazgo(c, _V(cvss=7.0), _F(posible=True), "high", "internal")
    assert kev > base and internet > base and viejo > base
    assert mitigado == pytest.approx(base * 0.5, abs=0.11) and det["reduction"] == 0.5
    assert posible == pytest.approx(base * 0.5, abs=0.11)
    tope, _ = calculo.riesgo_de_hallazgo(c, _V(cvss=10, kev=True, epss=1), _F(dias=999, intentos=3), "critical", "internet")
    assert tope == 100


def test_saturacion_e_indice():
    c = json.loads(json.dumps(aj.DEFECTO))
    cero = calculo.indice_de_puntos({f: 0 for f in aj.FACTORES}, c)
    assert cero == 0
    mucho = calculo.indice_de_puntos({f: 1000 for f in aj.FACTORES}, c)
    assert mucho == pytest.approx(100, abs=0.1)
    uno = calculo.indice_de_puntos({**{f: 0 for f in aj.FACTORES}, "vulnerabilities": 5}, c)
    assert uno == pytest.approx(0.35 * 100 * (1 - 2.718281828 ** -1), abs=0.2)


# ── Parsers de terceros ──────────────────────────────────────────────────────

def test_parser_defender():
    datos = {"value": [{"id": "x1", "cveId": "CVE-2021-23017", "machineId": "m1", "productName": "nginx",
                        "productVendor": "f5", "productVersion": "1.18.0", "severity": "Critical",
                        "fixingKbId": None}]}
    d = terceros.desde_defender(datos, {"m1": {"computerDnsName": "web-01.local", "lastIpAddress": "10.0.0.5"}})
    assert d == [{**d[0], "host": "web-01.local", "ip": "10.0.0.5", "cve": "CVE-2021-23017", "product": "nginx",
                  "version": "1.18.0", "severity": "critical", "status": "open"}]


def test_parser_trend_tenable_rapid7_csv():
    t = terceros.desde_trendmicro({"items": [{"deviceName": "web-01", "ipAddresses": ["10.0.0.5"],
                                              "cveRecords": [{"id": "CVE-2023-1", "cvssScore": 8.1, "riskLevel": "high"}],
                                              "productName": "openssl", "productVersion": "3.0.1"}]})
    assert t[0]["cve"] == "CVE-2023-1" and t[0]["severity"] == "high" and t[0]["ip"] == "10.0.0.5"
    te = terceros.desde_tenable([{"asset": {"hostname": "db-01", "ipv4": "10.0.0.9"},
                                  "plugin": {"id": 1234, "name": "Old SSH", "cve": [], "cvss3_base_score": 5.3,
                                             "cpe": ["cpe:/a:openbsd:openssh:7.4"]},
                                  "severity": "medium", "state": "OPEN", "port": {"port": 22}}])
    assert te[0]["cve"] == "TENABLE-1234" and te[0]["product"] == "openssh" and te[0]["version"] == "7.4"
    assert te[0]["ports"] == [22]
    r7 = terceros.desde_rapid7([{"hostName": "app-01", "ip": "10.0.0.7", "vulnerabilities": [
        {"id": "apache-httpd-cve-2021-41773", "title": "Path traversal", "cves": ["CVE-2021-41773"],
         "cvss": {"v3": {"score": 7.5}}, "severity": "Severe", "status": "vulnerable"}]}])
    assert r7[0]["cve"] == "CVE-2021-41773" and r7[0]["cvss"] == 7.5
    csv_ = terceros.desde_csv("host,ip,cve,product,version,severity,status\nweb-01,10.0.0.5,CVE-2023-2,php,8.1.2,high,fixed\n")
    assert csv_[0]["status"] == "fixed" and csv_[0]["product"] == "php"


def test_parser_qualys_con_base_de_conocimiento():
    deteccion = """<?xml version="1.0"?><HOST_LIST_VM_DETECTION_OUTPUT><RESPONSE><HOST_LIST><HOST>
      <ID>11</ID><IP>10.0.0.5</IP><DNS>web-01.local</DNS><DETECTION_LIST>
        <DETECTION><QID>38170</QID><TYPE>Confirmed</TYPE><SEVERITY>4</SEVERITY><STATUS>Active</STATUS>
          <PORT>443</PORT><FIRST_FOUND_DATETIME>2026-10-01T00:00:00Z</FIRST_FOUND_DATETIME></DETECTION>
        <DETECTION><QID>99999</QID><TYPE>Info</TYPE><SEVERITY>1</SEVERITY><STATUS>Active</STATUS></DETECTION>
      </DETECTION_LIST></HOST></HOST_LIST></RESPONSE></HOST_LIST_VM_DETECTION_OUTPUT>"""
    kb = terceros.base_de_conocimiento_qualys("""<KNOWLEDGE_BASE_VULN_LIST_OUTPUT><RESPONSE><VULN_LIST><VULN>
      <QID>38170</QID><TITLE>SSL weak</TITLE><CVE_LIST><CVE><ID>CVE-2016-2183</ID></CVE></CVE_LIST>
      <CVSS_V3><BASE>7.5</BASE></CVSS_V3></VULN></VULN_LIST></RESPONSE></KNOWLEDGE_BASE_VULN_LIST_OUTPUT>""")
    d = terceros.desde_qualys(deteccion, kb)
    assert len(d) == 1 and d[0]["cve"] == "CVE-2016-2183" and d[0]["severity"] == "high" and d[0]["ports"] == [443]
    sin_kb = terceros.desde_qualys(deteccion)
    assert sin_kb[0]["cve"] == "QID-38170"


def test_fichero_no_reconocido():
    with pytest.raises(Exception) as e:
        terceros.leer_fichero("defender", b"<xml/>")
    assert getattr(e.value, "code", None) == "swr_fichero_no_reconocido"
    with pytest.raises(Exception) as e:
        terceros.leer_fichero("nessus", b"{}")
    assert getattr(e.value, "code", None) == "swr_fuente_no_valida"


# ── De punta a punta ─────────────────────────────────────────────────────────

@pytest.fixture
def entorno(db, client, pm_token):
    """Dos CIs (uno con IP pública), nginx vulnerable expuesto y un cliente interno."""
    from app.models.clients import Client
    from app.models.service_desk._enums import CIType
    from app.models.service_desk.cmdb import ConfigurationItem
    web = ConfigurationItem(organization_id=ORG, code="CI-RK-1", name="web-01", ci_type=CIType.server,
                            hostname="web-01.local", ip_address="8.8.4.4", criticality="high")
    caja = ConfigurationItem(organization_id=ORG, code="CI-RK-2", name="pod-01", ci_type=CIType.container,
                             hostname="pod-01", ip_address="10.0.0.20", criticality="medium")
    unidad = Client(organization_id=ORG, name="Unidad TI")
    if hasattr(Client, "kind"):
        unidad.kind = "interno"
    db.add_all([web, caja, unidad])
    db.commit()
    nginx = client.post(f"{B}/products", json={"name": "nginx"}, headers=auth(pm_token)).json()["data"]
    inst = client.post(f"{B}/instances", json={"product_id": nginx["id"], "version": "1.18.0", "ci_id": web.id,
                                               "environment": "prod", "client_id": unidad.id, "ports": [443]},
                       headers=auth(pm_token)).json()["data"]
    client.post(f"{B}/instances", json={"product_id": nginx["id"], "version": "1.18.0", "ci_id": caja.id,
                                        "environment": "prod"}, headers=auth(pm_token))
    r = client.post(f"{B}/vulnerabilities/import", files={"file": ("nvd.json", json.dumps(NVD), "application/json")},
                    headers=auth(pm_token))
    assert r.status_code == 200, r.text
    return {"web": web, "caja": caja, "unidad": unidad, "nginx": nginx, "inst": inst}


def test_ajustes_por_api_y_guardas(client, db, admin_token, pm_token):
    r = client.get(f"{R}/settings", headers=auth(pm_token))
    assert r.status_code == 200 and r.json()["data"]["defaults"]["weights"]["vulnerabilities"] == 0.35
    malo = client.put(f"{R}/settings", json={"weights": {"vulnerabilities": 0.9}}, headers=auth(admin_token))
    assert malo.status_code == 422 and malo.json()["code"] == "swr_pesos_no_suman"
    assert client.put(f"{R}/settings", json={"target": 20}, headers=auth(pm_token)).status_code == 403
    ok = client.put(f"{R}/settings", json={"target": 20, "alerts": {"index_above": 10, "roles": ["admin"]}},
                    headers=auth(admin_token))
    assert ok.status_code == 200 and ok.json()["data"]["target"] == 20
    from app.models.enterprise import AuditLog
    assert db.query(AuditLog).filter(AuditLog.resource == "sw_risk_settings").count() >= 1


def test_indice_plan_y_metricas(client, db, pm_token, entorno):
    web = entorno["web"]
    # Exposición: 443 en IP pública → internet
    r = client.post(f"{R}/exposure/detect", headers=auth(pm_token))
    assert r.status_code == 200 and r.json()["data"]["set_internet"] == 1, r.text
    idx = client.get(f"{R}/index", headers=auth(pm_token)).json()["data"]
    assert 0 < idx["score"] <= 100 and idx["counts"]["findings_live"] == 2 and idx["counts"]["internet_assets"] == 1
    assert {f["key"] for f in idx["factors"]} == set(aj.FACTORES)
    assert idx["evaluated_at"] is None
    # Recalcular guarda la foto y la fecha de evaluación
    rc = client.post(f"{R}/recalculate", headers=auth(pm_token))
    assert rc.status_code == 200 and rc.json()["data"]["org_score"] == idx["score"]
    idx2 = client.get(f"{R}/index", headers=auth(pm_token)).json()["data"]
    assert idx2["evaluated_at"]
    hist = client.get(f"{R}/history", headers=auth(pm_token)).json()["items"]
    assert len(hist) == 1 and hist[0]["score"] == idx["score"]
    # Máquina y cliente interno (unidad)
    maq = client.get(f"{R}/index", params={"scope_type": "machine", "scope_id": web.id}, headers=auth(pm_token)).json()
    assert maq["data"]["counts"]["findings_live"] == 1 and maq["data"]["scope_name"] == "web-01"
    comp = client.get(f"{R}/compare", params={"scope_type": "client"}, headers=auth(pm_token)).json()["items"]
    unidad = next(x for x in comp if x["scope_id"] == entorno["unidad"].id)
    assert unidad["findings_live"] == 1
    malo = client.get(f"{R}/index", params={"scope_type": "galaxy"}, headers=auth(pm_token))
    assert malo.status_code == 422 and malo.json()["code"] == "swr_ambito_no_valido"
    # Plan: de X a 0 → los dos hallazgos, el expuesto primero, con «actualizar a 1.20.1»
    plan = client.get(f"{R}/plan", params={"target": 0}, headers=auth(pm_token)).json()["data"]
    assert len(plan["steps"]) == 2 and plan["steps"][0]["finding"]["ci_name"] == "web-01"
    assert plan["steps"][0]["impact"] >= plan["steps"][1]["impact"] > 0
    assert plan["steps"][0]["actions"][0]["code"] == "upgrade" and plan["steps"][0]["actions"][0]["params"]["to"] == "1.20.1"
    assert plan["final_score"] < plan["current"]
    ev = client.get(f"{R}/events", headers=auth(pm_token)).json()
    assert ev["meta"]["total"] >= 2 if "meta" in ev else len(ev["items"]) >= 2
    # Métricas y superficies
    m = client.get(f"{R}/metrics", headers=auth(pm_token)).json()["data"]
    assert m["assets"] == 2 and m["assets_with_vulns"] == 2 and m["pct_machines_with_vulns"] == 100.0
    assert m["internal_assets"] == 1 and m["by_state"]["new"] == 2 and m["density_per_asset"] == 1.0
    s = client.get(f"{R}/surfaces", headers=auth(pm_token)).json()["data"]
    assert s["internet"]["findings"] == 1 and s["container"]["findings"] == 1 and s["internal"]["findings"] == 1
    por_cve = client.get(f"{R}/findings", params={"group_by": "cve"}, headers=auth(pm_token)).json()["items"]
    assert por_cve[0]["vuln_id"] == "CVE-2021-23017" and por_cve[0]["assets"] == 2
    por_activo = client.get(f"{R}/findings", params={"group_by": "asset", "surface": "container"},
                            headers=auth(pm_token)).json()["items"]
    assert [x["ci_name"] for x in por_activo] == ["pod-01"]


def test_controles_e_intentos(client, db, admin_token, pm_token, entorno):
    hallazgos = client.get(f"{B}/findings", params={"ci_id": entorno["web"].id}, headers=auth(pm_token)).json()["items"]
    h = hallazgos[0]
    antes = h["priority_score"]
    malo = client.post(f"{R}/controls", json={"finding_ids": [h["id"]], "control_type": "waf", "description": "WAF",
                                              "expires_at": (date.today() - timedelta(days=1)).isoformat()},
                       headers=auth(pm_token))
    assert malo.status_code == 422 and malo.json()["code"] in ("swr_control_caducidad", "swr_control_descripcion")
    r = client.post(f"{R}/controls", json={"finding_ids": [h["id"]], "control_type": "waf",
                                           "description": "Regla WAF que bloquea el resolver",
                                           "expires_at": (date.today() + timedelta(days=30)).isoformat()},
                    headers=auth(pm_token))
    assert r.status_code == 201, r.text
    control = r.json()["items"][0] if "items" in r.json() else r.json()["data"][0]
    assert control["reduction"] == 0.5
    despues = client.get(f"{B}/findings/{h['id']}", headers=auth(pm_token)).json()["data"]
    assert despues["status"] == h["status"] and despues["priority_score"] == pytest.approx(antes * 0.5, abs=0.2)
    # Intentos de explotación: casan con el hallazgo y no se duplican
    csv_ = (f"id,cve,host,observed_at,action,count\n"
            f"e1,CVE-2021-23017,web-01,{datetime.now(timezone.utc).isoformat()},allowed,3\n").encode()
    r1 = client.post(f"{R}/exploits/import", files={"file": ("e.csv", csv_, "text/csv")}, headers=auth(pm_token))
    assert r1.status_code == 200 and r1.json()["data"]["matched"] == 1, r1.text
    r2 = client.post(f"{R}/exploits/import", files={"file": ("e.csv", csv_, "text/csv")}, headers=auth(pm_token))
    assert r2.json()["data"]["duplicates"] == 1
    from app.models.cmdb_software import VulnerabilityFinding
    db.expire_all()
    assert db.get(VulnerabilityFinding, h["id"]).exploit_attempts == 3
    idx = client.get(f"{R}/index", headers=auth(pm_token)).json()["data"]
    assert idx["counts"]["exploited"] >= 1 and idx["counts"]["exploit_events"] == 1
    # Revocar y caducar
    rv = client.post(f"{R}/controls/{control['id']}/revoke", json={"reason": "Se quita el WAF"}, headers=auth(pm_token))
    assert rv.status_code == 200 and rv.json()["data"]["status"] == "revoked"
    otra = client.post(f"{R}/controls/{control['id']}/revoke", json={}, headers=auth(pm_token))
    assert otra.status_code == 422 and otra.json()["code"] == "swr_control_no_activo"
    from app.models.cmdb_riesgo import CompensatingControl
    from app.services.cmdb_software.riesgo import controles
    c = CompensatingControl(organization_id=ORG, finding_id=h["id"], control_type="ips", description="IPS viejo",
                            reduction=0.5, expires_at=date.today() - timedelta(days=1), status="active")
    db.add(c)
    db.commit()
    assert controles.caducar(db, ORG) == 1
    db.commit()
    # Cumplimiento: mitigación caducada con el hallazgo vivo y explotados abiertos
    from app.services.cmdb_software.riesgo.cumplimiento import controles as ctrls

    def _control(id_, estado, medido, fuente, marcos):
        return {"id": id_, "status": estado, "measured": medido}
    por_id = {x["id"]: x for x in ctrls(db, ORG, _control)}
    assert por_id["sw_mitigations_expired"]["status"] == "attention"
    assert por_id["sw_kev_open"]["status"] == "attention"
    assert por_id["sw_risk_index"]["measured"]["score"] > 0


def test_terceros_deduplica_con_la_correlacion(client, db, pm_token, entorno):
    defender = {"value": [{"id": "1", "cveId": "CVE-2021-23017", "deviceName": "web-01.local",
                           "softwareName": "nginx", "softwareVendor": "f5", "softwareVersion": "1.18.0",
                           "vulnerabilitySeverityLevel": "Critical"},
                          {"id": "2", "cveId": "CVE-2024-9999", "deviceName": "nuevo-02", "lastIpAddress": "10.1.1.1",
                           "softwareName": "7-Zip", "softwareVendor": "igor pavlov", "softwareVersion": "19.00",
                           "vulnerabilitySeverityLevel": "High", "cvssScore": 7.8}]}
    r = client.post(f"{R}/import/file", data={"source": "defender", "create_cis": "true", "complete": "true"},
                    files={"file": ("defender.json", json.dumps(defender), "application/json")}, headers=auth(pm_token))
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["detections"] == 2 and d["findings_updated"] == 1 and d["findings_new"] == 1 and d["cis_created"] == 1
    hallazgos = client.get(f"{R}/findings", headers=auth(pm_token)).json()["items"]
    nginx_web = [h for h in hallazgos if h["vuln_id"] == "CVE-2021-23017" and h["ci_name"] == "web-01"]
    assert len(nginx_web) == 1 and set(nginx_web[0]["detected_by"]) == {"correlation", "defender"}
    # La reevaluación propia no cierra lo que sigue informando un tercero
    zip_ = next(h for h in hallazgos if h["vuln_id"] == "CVE-2024-9999")
    assert client.post(f"{B}/reevaluate", headers=auth(pm_token)).status_code == 200
    assert client.get(f"{B}/findings/{zip_['id']}", headers=auth(pm_token)).json()["data"]["status"] == "open"
    # Importación completa sin 7-Zip → resuelto; nginx sigue (lo ve la correlación)
    solo_nginx = {"value": defender["value"][:1]}
    r = client.post(f"{R}/import/file", data={"source": "defender", "complete": "true"},
                    files={"file": ("d.json", json.dumps(solo_nginx), "application/json")}, headers=auth(pm_token))
    assert r.json()["data"]["findings_resolved"] == 1
    assert client.get(f"{B}/findings/{zip_['id']}", headers=auth(pm_token)).json()["data"]["status"] == "resolved"


def test_conector_por_api_simulado(client, db, admin_token, pm_token, entorno, monkeypatch):
    llamadas = []

    def falso(metodo, url, **k):
        llamadas.append((metodo, url))
        if "oauth2" in url:
            return {"access_token": "tok"}
        if url.endswith("/api/machines"):
            return {"value": [{"id": "m1", "computerDnsName": "web-01.local", "lastIpAddress": "8.8.4.4"}]}
        return {"value": [{"id": "v1", "cveId": "CVE-2021-23017", "machineId": "m1", "productName": "nginx",
                           "productVendor": "f5", "productVersion": "1.18.0", "severity": "Critical"}]}
    monkeypatch.setattr(terceros, "_http", falso)
    r = client.post(f"{B}/scanners", json={"name": "Defender", "type": "sw_vm_defender",
                                           "config": {"tenant_id": "t", "client_id": "c", "client_secret": "s3creto"}},
                    headers=auth(admin_token))
    assert r.status_code == 201, r.text
    assert "s3creto" not in r.text
    run = client.post(f"{B}/scanners/{r.json()['data']['id']}/run", json={}, headers=auth(pm_token))
    assert run.status_code == 200 and run.json()["data"]["status"] == "ok", run.text
    assert any("oauth2" in u for _, u in llamadas) and any("machinesVulnerabilities" in u for _, u in llamadas)
    campos = client.get(f"{B}/scanners/fields", headers=auth(admin_token)).json()["data"]
    assert "sw_vm_qualys" in json.dumps(campos)


def test_vistas_informes_avisos_y_retencion(client, db, admin_token, pm_token, entorno):
    v = client.post(f"{R}/views", json={"name": "Críticos en Internet", "surface": "internet", "group_by": "asset",
                                        "filters": {"severity": "critical"}, "columns": ["risk", "vuln"], "shared": True},
                    headers=auth(pm_token))
    assert v.status_code == 201, v.text
    vid = v.json()["data"]["id"]
    ajena = client.patch(f"{R}/views/{vid}", json={"name": "Otra"}, headers=auth(admin_token))
    assert ajena.status_code == 403 and ajena.json()["code"] == "swr_vista_ajena"
    assert any(x["id"] == vid and not x["mine"] for x in client.get(f"{R}/views", headers=auth(admin_token)).json()["items"])
    mala = client.post(f"{R}/views", json={"name": "x2", "columns": ["inventada"]}, headers=auth(pm_token))
    assert mala.status_code == 422
    # Informes programados
    inf = client.post(f"{R}/reports", json={"name": "Riesgo semanal", "report_type": "cyber_risk", "scope_type": "org",
                                            "frequency": "weekly", "day_of_week": 0, "recipients": ["ciso@example.com"]},
                      headers=auth(pm_token))
    assert inf.status_code == 201, inf.text
    assert inf.json()["data"]["next_run_at"]
    sin = client.post(f"{R}/reports", json={"name": "x", "report_type": "cyber_risk", "recipients": ["no-es-correo"]},
                      headers=auth(pm_token))
    assert sin.status_code == 422 and sin.json()["code"] in ("swr_destinatarios", "sw_nombre_obligatorio")
    assert len(client.get(f"{R}/reports", headers=auth(pm_token)).json()["items"]) == 1
    try:
        import reportlab  # noqa: F401
        from app.models.billing_reports import ScheduledReport
        from app.services.report_pdf_service import build_report_pdf
        for tipo in ("cyber_risk", "vuln_management"):
            rep = db.get(ScheduledReport, inf.json()["data"]["id"])
            rep.report_type = tipo
            pdf = build_report_pdf(rep, db, org_id=ORG)
            assert pdf[:4] == b"%PDF"
    except ImportError:
        pass
    # Avisos: índice por encima del umbral → campana, sin repetir
    client.put(f"{R}/settings", json={"alerts": {"index_above": 0, "kev_new": True, "roles": ["admin"]}},
               headers=auth(admin_token))
    from app.services.cmdb_software.riesgo import alertas
    primera = alertas.revisar(db, ORG)
    db.commit()
    segunda = alertas.revisar(db, ORG)
    assert primera["index_above"] >= 1 and segunda["index_above"] == 0
    # Retención: el trabajo diario poda lo anterior a history_days
    from app.models.cmdb_riesgo import RiskSnapshot
    from app.services.cmdb_software.riesgo.trabajos import podar_historico
    db.add(RiskSnapshot(organization_id=ORG, scope_type="org", scope_id="", day=date.today() - timedelta(days=900),
                        score=50))
    db.commit()
    assert podar_historico(db, ORG, 730) == 1
    from app.db.bloqueo_legal import TIPOS
    assert {"sw_risk_snapshots", "sw_exploit_events", "sw_risk_alert_log"} <= set(TIPOS)


def test_meta_y_guardas(client, pm_token):
    m = client.get(f"{R}/meta", headers=auth(pm_token)).json()["data"]
    assert "sw_vm_tenable" in m["connector_types"] and m["control_reductions"]["virtual_patch"] == 0.7
