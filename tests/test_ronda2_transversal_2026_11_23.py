"""Segunda ronda transversal de la auditoría 2026-11-22 (23-11-2026).

- Microsoft 365 / Graph con credencial y token POR EMPRESA (03 A-MP3); los
  `AZURE_*` solo como credencial de plataforma explícita.
- Correo (SMTP/IMAP) a la IP ya validada (anti DNS rebinding).
- Pruebas de conexión que dicen qué han verificado de verdad.

docs/seguridad/entrada_y_salida.md y docs/integraciones/pruebas_de_conexion.md.
"""
from __future__ import annotations

import socket
from types import SimpleNamespace

import pytest

from app.core.errores import ErrorDeDominio

PROPIA = {"tenant_id": "contoso.onmicrosoft.com", "client_id": "cid", "client_secret": "sec"}


def _secretos(valores: dict):
    return lambda db, provider, campo, ajuste, org_id: valores.get(campo)


# ── Microsoft 365 / Graph por empresa ────────────────────────────────────────

def test_graph_usa_la_credencial_de_la_empresa(monkeypatch):
    from app.services import integration_credentials_service as ics
    from app.services import m365_service as m

    monkeypatch.setattr(ics, "secreto_propio_de_la_organizacion", _secretos(PROPIA))
    cred = m.credenciales_de_graph(object(), "org-1")
    assert cred == {**PROPIA, "origen": "empresa"}


def test_sin_credencial_propia_no_cae_a_los_azure_globales(monkeypatch):
    from app.services import integration_credentials_service as ics
    from app.services import m365_service as m

    monkeypatch.setattr(ics, "secreto_propio_de_la_organizacion", _secretos({}))
    monkeypatch.setattr(m.settings, "AZURE_TENANT_ID", "plataforma", raising=False)
    monkeypatch.setattr(m.settings, "AZURE_CLIENT_ID", "pcid", raising=False)
    monkeypatch.setattr(m.settings, "AZURE_CLIENT_SECRET", "psec", raising=False)
    monkeypatch.setattr(m.settings, "M365_PLATFORM_CREDENTIALS_ENABLED", False, raising=False)
    assert m.credenciales_de_graph(object(), "org-1") is None
    with pytest.raises(ErrorDeDominio) as e:
        m.require_m365(object(), "org-1")
    assert e.value.status_code == 503

    monkeypatch.setattr(m.settings, "M365_PLATFORM_CREDENTIALS_ENABLED", True, raising=False)
    assert m.credenciales_de_graph(object(), "org-1")["origen"] == "plataforma"


def test_una_credencial_propia_a_medias_no_se_completa_con_la_de_plataforma(monkeypatch):
    from app.services import integration_credentials_service as ics
    from app.services import m365_service as m

    monkeypatch.setattr(ics, "secreto_propio_de_la_organizacion", _secretos({"tenant_id": "t"}))
    monkeypatch.setattr(m.settings, "M365_PLATFORM_CREDENTIALS_ENABLED", True, raising=False)
    monkeypatch.setattr(m.settings, "AZURE_TENANT_ID", "p", raising=False)
    monkeypatch.setattr(m.settings, "AZURE_CLIENT_ID", "p", raising=False)
    monkeypatch.setattr(m.settings, "AZURE_CLIENT_SECRET", "p", raising=False)
    assert m.credenciales_de_graph(object(), "org-1") is None


def test_el_token_se_cachea_por_credencial_y_el_tenant_no_cambia_la_ruta(monkeypatch):
    from app.services import m365_service as m

    pedidos = []

    class _Cliente:
        def __init__(self, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, data=None):
            pedidos.append((url, data["client_id"]))
            return SimpleNamespace(status_code=200, json=lambda: {"access_token": f"tok-{data['client_id']}",
                                                                   "expires_in": 3600})

    monkeypatch.setattr(m.httpx, "Client", _Cliente)
    m._tokens.clear()
    a = {**PROPIA, "client_id": "a"}
    b = {**PROPIA, "client_id": "b"}
    assert m.token_de_graph_sync(a) == "tok-a" and m.token_de_graph_sync(a) == "tok-a"
    assert m.token_de_graph_sync(b) == "tok-b"
    assert [p[1] for p in pedidos] == ["a", "b"], "una petición por credencial; la segunda sale de la caché"
    with pytest.raises(ErrorDeDominio):
        m.token_de_graph_sync({**PROPIA, "tenant_id": "x/../common?y=1", "client_id": "c"})


@pytest.mark.parametrize("valor,ok", [
    ("19:abc123@thread.tacv2", True), ("contoso.sharepoint.com,1-2,3-4", True),
    ("00000000-0000-0000-0000-000000000000", True), ("../users/otro", False), ("a/b", False),
    ("x?$select=*", False), ("", False),
])
def test_los_identificadores_de_graph_no_cambian_la_ruta(valor, ok):
    from app.services.m365_service import id_de_graph
    if ok:
        assert id_de_graph(valor)
    else:
        with pytest.raises(ErrorDeDominio):
            id_de_graph(valor)


def test_nadie_usa_los_azure_globales_fuera_de_la_credencial_de_plataforma():
    import pathlib
    import re
    raiz = pathlib.Path(__file__).resolve().parent.parent / "app"
    malos = [f.relative_to(raiz).as_posix() for f in raiz.rglob("*.py")
             if re.search(r"settings\.AZURE_(TENANT_ID|CLIENT_ID|CLIENT_SECRET)\b", f.read_text(encoding="utf-8"))
             and f.relative_to(raiz).as_posix() != "services/m365_service.py"]
    assert malos == []


# ── Correo a la IP validada ──────────────────────────────────────────────────

def test_ip_fijada_devuelve_la_ip_validada_y_rechaza_lo_que_no_resuelve(monkeypatch):
    import ipaddress

    from app.core import conexion_fijada as cf

    monkeypatch.setattr(cf, "validar_host_saliente", lambda h, field="host": [ipaddress.ip_address("203.0.113.9")])
    assert cf.ip_fijada("mail.example.com") == "203.0.113.9"
    monkeypatch.setattr(cf, "validar_host_saliente", lambda h, field="host": [])
    monkeypatch.setattr(cf, "_hosts_privados_permitidos", lambda: {"relay.interno"})
    assert cf.ip_fijada("relay.interno") is None
    with pytest.raises(ErrorDeDominio):
        cf.ip_fijada("no-resuelve.example.com")


def _conexion_grabada(monkeypatch):
    from app.core import conexion_fijada as cf
    destinos = []

    def _create_connection(destino, *a, **k):
        destinos.append(destino)
        raise ConnectionRefusedError("sin red en el test")
    monkeypatch.setattr(cf.socket, "create_connection", _create_connection)
    return destinos


def test_smtp_de_empresa_conecta_a_la_ip_validada_y_no_vuelve_a_resolver(monkeypatch):
    from app.services import notification_service as ns
    destinos = _conexion_grabada(monkeypatch)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: pytest.fail("no se vuelve a resolver"))
    with pytest.raises(OSError):
        ns.SmtpFijado("mail.example.com", 587, ip_fijada="203.0.113.9", timeout=1)
    with pytest.raises(OSError):
        ns.SmtpSslFijado("mail.example.com", 465, ip_fijada="203.0.113.9", timeout=1)
    assert destinos == [("203.0.113.9", 587), ("203.0.113.9", 465)]


def test_imap_conecta_a_la_ip_validada_con_certificado_verificado(monkeypatch):
    import ssl

    from app.core.conexion_fijada import Imap4SslFijado
    from app.services.notification_service import contexto_tls
    destinos = _conexion_grabada(monkeypatch)
    with pytest.raises(OSError):
        Imap4SslFijado("imap.example.com", 993, ip_fijada="203.0.113.9", ssl_context=contexto_tls(), timeout=1)
    assert destinos == [("203.0.113.9", 993)]
    assert contexto_tls().verify_mode == ssl.CERT_REQUIRED


def test_la_ip_real_del_otro_extremo_se_comprueba(monkeypatch):
    from app.core import conexion_fijada as cf
    from app.core.outbound_url import ConexionBloqueada

    class _Sock:
        cerrado = False

        def getpeername(self):
            return ("10.0.0.7", 25)

        def close(self):
            _Sock.cerrado = True
    monkeypatch.setattr(cf.socket, "create_connection", lambda *a, **k: _Sock())
    with pytest.raises(ConexionBloqueada):
        cf.socket_fijado("mail.example.com", None, 25, 1)
    assert _Sock.cerrado


# ── Pruebas de conexión honestas ─────────────────────────────────────────────

def test_cada_proveedor_de_credenciales_tiene_prueba():
    from app.services.integration_credentials_service import PROVIDER_REGISTRY
    from app.services.integration_test_service import _PROBES
    assert set(PROVIDER_REGISTRY) - set(_PROBES) == set()


def test_docusign_ya_no_dice_ok_sin_verificar_nada(monkeypatch, db):
    from app.services import integration_test_service as its

    class _Cliente:
        def __init__(self, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url):
            return SimpleNamespace(status_code=200)
    monkeypatch.setattr(its, "cliente_httpx", _Cliente)
    r = its._test_docusign({"integration_key": "k", "secret_key": "s", "account_id": "a"}, db)
    assert r["ok"] and r["verificado"] == "configuracion"
    r = its._test_docusign({"account_id": "a"}, db)
    assert not r["ok"] and r["verificado"] == "nada"


def test_la_prueba_de_salesforce_dice_que_verifico_y_que_no_hay_salida(monkeypatch, db):
    from app.services import salesforce_service as sf
    vistas = []

    class _Cliente:
        def __init__(self, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, params=None, headers=None):
            vistas.append(url.rsplit("/", 1)[-1])
            return SimpleNamespace(status_code=200)
    monkeypatch.setattr(sf, "preparar_sincronizacion", lambda db, i, o: (None, "https://x.my.salesforce.com", "t"))
    from app.core import outbound_url
    monkeypatch.setattr(outbound_url, "cliente_httpx", _Cliente)
    monkeypatch.setattr(outbound_url, "validate_outbound_url", lambda url, **k: url)
    r = sf.probar_conexion(db, "inst", "1")
    assert r["ok"] and r["verificado"] == "credencial_y_uso" and r["salida"] == "no_implementada"
    assert vistas == ["limits", "query"]
