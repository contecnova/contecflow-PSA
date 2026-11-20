"""CMDB de software: conectores de escaneo, POM con padre, varios ficheros y «posible afectado».

Sin red ni equipos reales: SSH y WinRM se sustituyen por ejecutores simulados
(`escaneos.EJECUTORES`) que devuelven lo que devolverían esas órdenes, y la
API de EDR/RMM por `escaneos._http_get`.
"""
from __future__ import annotations

import io
import json
import zipfile

import pytest

from app.services.cmdb_software import escaneos, formatos
from tests.conftest import auth

B = "/api/v1/cmdb/software"

SALIDAS_LINUX = {
    "cat /etc/os-release": 'ID=ubuntu\nVERSION_ID="22.04"\nPRETTY_NAME="Ubuntu 22.04.3 LTS"\nNAME="Ubuntu"\n',
    "hostname -f": "web-02.local\n",
    "hostname -I": "10.0.0.7 172.17.0.1\n",
    "uname -r": "5.15.0-91-generic\n",
    "ss -ltnpH": ('LISTEN 0      511          0.0.0.0:443        0.0.0.0:*    users:(("nginx",pid=812,fd=6))\n'
                  'LISTEN 0      128          0.0.0.0:22         0.0.0.0:*    users:(("sshd",pid=700,fd=3))\n'),
    "nginx -v": "nginx version: nginx/1.18.0 (Ubuntu)\n",
    "nginx -T": "server {\n listen 443 ssl;\n ssl_protocols TLSv1 TLSv1.2;\n server_tokens on;\n}\n",
    "php -v": "PHP 8.1.2-1ubuntu2.14 (cli) (built: Aug 18 2023)\n",
    "openssl version": "OpenSSL 3.0.2 15 Mar 2022\n",
    "ssh -V": "OpenSSH_8.9p1 Ubuntu-3ubuntu0.4, OpenSSL 3.0.2\n",
    "dpkg-query": "openssl\t3.0.2-0ubuntu1.10\nlibc6\t2.35-0ubuntu3.4\nvim\t2:8.2.3995-1ubuntu2\n",
}


def ejecutor_linux(salidas=SALIDAS_LINUX):
    def ejecutar(orden: str):
        for clave, salida in salidas.items():
            if clave in orden:
                return 0, salida
        return 127, ""
    return ejecutar


def test_recoger_linux():
    inv = escaneos.recoger_linux(ejecutor_linux(), {"read_configs": True})
    assert inv["host"]["hostname"] == "web-02.local" and inv["host"]["ip_address"] == "10.0.0.7"
    por_nombre = {i["name"]: i for i in inv["instances"]}
    assert por_nombre["Ubuntu"]["version"] == "22.04" and "canonical:ubuntu_linux" in por_nombre["Ubuntu"]["cpe"]
    nginx = por_nombre["nginx"]
    assert nginx["version"] == "1.18.0" and nginx["ports"] == [443] and nginx["config"]["tls_protocols"]
    assert por_nombre["php"]["version"] == "8.1.2" and por_nombre["openssh"]["ports"] == [22]
    # Paquetes: solo los relevantes (openssl, libc6), con su purl de distribución
    assert por_nombre["openssl"]["purl"].startswith("pkg:deb/ubuntu/openssl@") and "vim" not in por_nombre
    todos = escaneos.recoger_linux(ejecutor_linux(), {"all_packages": True})
    assert "vim" in {i["name"] for i in todos["instances"]}


WINDOWS = {"hostname": "APP01", "fqdn": "app01.corp.local", "os": {"Caption": "Microsoft Windows Server 2019 Standard",
                                                                 "Version": "10.0.17763"},
           "ips": ["10.0.1.20"], "apps": [{"DisplayName": "7-Zip 19.00", "DisplayVersion": "19.00", "Publisher": "Igor Pavlov"},
                                          {"DisplayName": "Microsoft SQL Server 2019", "DisplayVersion": "15.0.2000.5",
                                           "Publisher": "Microsoft Corporation"}],
           "services": [{"Name": "W3SVC", "State": "Running"}], "iis": {"VersionString": "Version 10.0", "MajorVersion": 10},
           "sites": [{"name": "Default Web Site", "state": "Started", "path": "C:\\inetpub\\wwwroot",
                      "bindings": ["http *:80:", "https *:443:"]}], "ports": [{"port": 80, "process": "System"}]}


def test_interpretar_windows():
    inv = escaneos.interpretar_windows(WINDOWS)
    por_nombre = {i["name"]: i for i in inv["instances"]}
    assert inv["host"]["hostname"] == "app01.corp.local"
    assert por_nombre["Microsoft IIS"]["version"] == "10.0" and por_nombre["Microsoft IIS"]["ports"] == [80, 443]
    assert por_nombre["Microsoft IIS"]["config"]["tls"] is True
    assert por_nombre["7-Zip 19.00"]["vendor"] == "Igor Pavlov"
    assert por_nombre["Windows Server 2019 Standard"]["config"]["running_services"] == ["W3SVC"]


def test_recoger_api_con_mapeo(monkeypatch):
    paginas = {"https://edr/api/devices": {"data": {"items": [{"name": "pc-1", "ip": "10.0.2.5", "apps": [
        {"title": "Google Chrome", "ver": "118.0.5993.70", "pub": "Google LLC"}]}]}, "next": "https://edr/api/devices?p=2"},
        "https://edr/api/devices?p=2": {"data": {"items": [{"name": "pc-2", "apps": []}]}, "next": None}}
    vistas = []

    def falso(url, headers=None, timeout=30):
        vistas.append(headers.get("Authorization"))
        return paginas[url]
    monkeypatch.setattr(escaneos, "_http_get", falso)
    equipos = escaneos.recoger_api({"url": "https://edr/api/devices", "token": "t0k", "list_path": "data.items",
                                    "host_field": "name", "software_field": "apps", "name_field": "title",
                                    "version_field": "ver", "vendor_field": "pub", "next_path": "next"})
    assert [e["host"]["hostname"] for e in equipos] == ["pc-1", "pc-2"]
    assert equipos[0]["instances"][0]["version"] == "118.0.5993.70" and vistas == ["Bearer t0k", "Bearer t0k"]


def test_un_equipo_caido_no_para_el_resto(monkeypatch):
    def fabrica(host, conf):
        if host.startswith("caido"):
            raise TimeoutError("sin respuesta")
        return ejecutor_linux(), (lambda: None)
    monkeypatch.setitem(escaneos.EJECUTORES, "sw_ssh", fabrica)
    r = escaneos.recoger("sw_ssh", {"hosts": "caido.local, web-02.local"})
    assert r[0]["error"] == "TimeoutError" and r[1]["host"]["hostname"] == "web-02.local"


def test_sin_libreria_ssh_error_con_codigo(monkeypatch):
    import builtins
    original = builtins.__import__

    def sin_paramiko(nombre, *a, **k):
        if nombre == "paramiko":
            raise ImportError(nombre)
        return original(nombre, *a, **k)
    monkeypatch.setattr(builtins, "__import__", sin_paramiko)
    with pytest.raises(Exception) as e:
        escaneos._ssh("h", {})
    # `ErrorConCodigo` lleva `codigo`; `ErrorDeDominio`, `code`: vale cualquiera de los dos.
    assert (getattr(e.value, "codigo", None) or getattr(e.value, "code", None)) == "sw_dependencia_no_instalada"


def test_conexion_de_punta_a_punta(client, db, admin_token, pm_token, monkeypatch):
    monkeypatch.setitem(escaneos.EJECUTORES, "sw_ssh", lambda host, conf: (ejecutor_linux(), lambda: None))
    r = client.post(f"{B}/scanners", json={"name": "Linux prod", "type": "sw_ssh", "scan_interval_minutes": 1440,
                                           "config": {"hosts": "web-02.local", "username": "inventario",
                                                      "password": "clave-ssh-secreta", "read_configs": True,
                                                      "environment": "prod", "exposure": "internet"}},
                    headers=auth(admin_token))
    assert r.status_code == 201, r.text
    conexion = r.json()["data"]
    assert "clave-ssh-secreta" not in r.text and conexion["secrets_set"] == ["password"]
    # La configuración queda cifrada en la base
    from app.models.cmdb import CMDBDiscoveryProvider
    fila = db.get(CMDBDiscoveryProvider, conexion["id"])
    assert "clave-ssh-secreta" not in (fila.config_json or "")
    # Solo dirección configura; PM escanea bajo demanda
    assert client.post(f"{B}/scanners", json={"name": "x", "type": "sw_ssh"}, headers=auth(pm_token)).status_code == 403
    r = client.post(f"{B}/scanners/{conexion['id']}/run", json={}, headers=auth(pm_token))
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["status"] == "ok" and d["hosts"] == 1 and d["cis_created"] == 1 and d["created"] >= 4
    maquinas = client.get(f"{B}/where-used", params={"q": "nginx"}, headers=auth(pm_token)).json()["data"]
    inst = maquinas["instances"][0]
    assert inst["ci_name"] == "web-02.local" and inst["environment"] == "prod" and inst["exposure"] == "internet"
    # Segunda pasada: no duplica; programada por el descubrimiento de la CMDB
    from app.services.cmdb.discovery import run_discovery_for_provider
    job = run_discovery_for_provider(db, fila)
    assert job.status == "ok"
    assert client.get(f"{B}/where-used", params={"q": "nginx"}, headers=auth(pm_token)).json()["data"]["summary"][
        "instances"] == 1
    runs = client.get(f"{B}/scanners/{conexion['id']}/runs", headers=auth(pm_token)).json()["items"]
    assert len(runs) == 2
    from app.models.enterprise import AuditLog
    acciones = {(a.resource, a.action) for a in db.query(AuditLog).filter(AuditLog.resource.like("sw_scan%"))}
    assert ("sw_scan_connection", "CREATE") in acciones and ("sw_scan", "SCAN") in acciones
    assert all("clave-ssh-secreta" not in (a.new_values or "") for a in db.query(AuditLog).all())


# ── POM con padre, varios ficheros y versión desconocida ────────────────────

PADRE = ("<project><groupId>com.acme</groupId><artifactId>padre</artifactId><version>1.0</version>"
         "<packaging>pom</packaging><properties><spring.version>5.3.18</spring.version></properties>"
         "<dependencyManagement><dependencies><dependency><groupId>org.apache.logging.log4j</groupId>"
         "<artifactId>log4j-core</artifactId><version>2.14.1</version></dependency></dependencies>"
         "</dependencyManagement></project>")
HIJO = ("<project><parent><groupId>com.acme</groupId><artifactId>padre</artifactId><version>1.0</version></parent>"
        "<artifactId>app</artifactId><dependencies>"
        "<dependency><groupId>org.springframework</groupId><artifactId>spring-core</artifactId>"
        "<version>${spring.version}</version></dependency>"
        "<dependency><groupId>org.apache.logging.log4j</groupId><artifactId>log4j-core</artifactId></dependency>"
        "<dependency><groupId>com.acme</groupId><artifactId>util</artifactId><version>${project.version}</version>"
        "</dependency></dependencies></project>")


def test_pom_con_padre_y_dependency_management():
    r = formatos.leer_varios([("app/pom.xml", HIJO.encode()), ("padre/pom.xml", PADRE.encode())])
    versiones = {c["name"]: c["version"] for c in r.componentes}
    assert versiones == {"spring-core": "5.3.18", "log4j-core": "2.14.1", "util": "1.0"}
    # Sin el padre, lo que no se resuelve queda sin versión (no se inventa)
    solo = formatos.pom_xml(HIJO)
    assert {c["name"]: c["version"] for c in solo.componentes}["log4j-core"] is None


def test_zip_y_requirements_con_freeze():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("requirements.txt", "requests>=2\nflask\n")
        z.writestr("freeze/pip-freeze.txt", "requests==2.31.0\n")
        z.writestr("../malo.txt", "x==1\n")
        z.writestr("LEEME.md", "hola")
    r = formatos.leer_varios([("deps.zip", buf.getvalue())])
    versiones = {c["name"]: c["version"] for c in r.componentes}
    assert versiones == {"requests": "2.31.0", "flask": None}
    assert "LEEME.md" in r.ignorados


def test_version_desconocida_es_posible_afectado(client, db, pm_token):
    p = client.post(f"{B}/products", json={"name": "API interna", "origin": "in_house"}, headers=auth(pm_token)).json()["data"]
    v = client.post(f"{B}/products/{p['id']}/versions", json={"version": "1.0"}, headers=auth(pm_token)).json()["data"]
    r = client.post(f"{B}/versions/{v['id']}/import",
                    files=[("files", ("requirements.txt", b"requests>=2\n", "text/plain")),
                           ("files", ("otros.txt", b"django>=4\n", "text/plain"))],
                    headers=auth(pm_token))
    assert r.status_code == 200 and r.json()["data"]["unknown_version"] == 2, r.text
    osv = {"id": "GHSA-j8r2-6x86-q33q", "modified": "2023-05-26T00:00:00Z", "summary": "requests leaks proxy auth",
           "database_specific": {"severity": "MODERATE"},
           "affected": [{"package": {"ecosystem": "PyPI", "name": "requests"},
                         "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "2.3.0"}, {"fixed": "2.31.0"}]}]}]}
    r = client.post(f"{B}/vulnerabilities/import", files={"file": ("osv.json", json.dumps(osv), "application/json")},
                    headers=auth(pm_token))
    assert r.status_code == 200, r.text
    h = client.get(f"{B}/findings", params={"possible": True}, headers=auth(pm_token)).json()["items"]
    assert len(h) == 1 and h[0]["possible"] is True and h[0]["sla_due_at"] is None
    assert h[0]["affected_version"] is None and h[0]["product_name"] == "requests"
    # Al conocer la versión (lock), el posible desaparece y queda el real (o nada si no está afectada)
    r = client.post(f"{B}/versions/{v['id']}/import",
                    files=[("files", ("requirements.txt", b"requests>=2\n", "text/plain")),
                           ("files", ("freeze.txt", b"requests==2.28.0\n", "text/plain"))],
                    data={"replace": "true"}, headers=auth(pm_token))
    assert r.status_code == 200, r.text
    vivos = client.get(f"{B}/findings", headers=auth(pm_token)).json()["items"]
    assert [(x["affected_version"], x["possible"]) for x in vivos] == [("2.28.0", False)]


def test_paquetes_de_distribucion_no_casan_por_cpe(db):
    from app.models.cmdb_software import SoftwareProduct
    from app.services.cmdb_software.correlacion import _Indice
    p = SoftwareProduct(name="openssl", purl_type="deb", purl_namespace="ubuntu", purl_name="openssl",
                        cpe_vendor="openssl", cpe_product="openssl", match_key="x")
    indice = _Indice.__new__(_Indice)
    indice.por_paquete, indice.por_cpe, indice.vulns = {}, {("openssl", "openssl"): [("v", "a")]}, {}
    assert indice.candidatos(p) == []


def test_ecosistemas_de_distribucion_de_osv():
    from app.services.cmdb_software.avisos import clave_de_afecta
    assert clave_de_afecta({"ecosystem": "Ubuntu:22.04:LTS", "name": "openssl"}) == "deb/ubuntu/openssl"
    assert clave_de_afecta({"ecosystem": "Debian:11", "name": "nginx"}) == "deb/debian/nginx"
    assert clave_de_afecta({"ecosystem": "Alpine:v3.18", "name": "busybox"}) == "apk/alpine/busybox"
    assert clave_de_afecta({"ecosystem": "PyPI", "name": "Django_REST"}) == "pypi//django-rest"