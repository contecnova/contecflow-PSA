"""Un solo emisor de correo (auditoria 2026-11, hallazgo 20).

SMTP se abria desde ocho modulos, cada uno con su TLS, su remitente y su
manera de autenticarse. Ahora solo `app/services/notification_service.py`
importa `smtplib`; el resto llama a `enviar_correo`/`entregar`.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from app.services import notification_service as ns

EMISOR = "app/services/notification_service.py"
PROHIBIDOS = {"smtplib", "aiosmtplib"}


def _importa_smtp(fichero: pathlib.Path) -> list[int]:
    arbol = ast.parse(fichero.read_text(encoding="utf-8", errors="replace"))
    lineas = []
    for n in ast.walk(arbol):
        if isinstance(n, ast.Import) and any(a.name.split(".")[0] in PROHIBIDOS for a in n.names):
            lineas.append(n.lineno)
        elif isinstance(n, ast.ImportFrom) and (n.module or "").split(".")[0] in PROHIBIDOS:
            lineas.append(n.lineno)
        elif (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "__import__"
              and n.args and isinstance(n.args[0], ast.Constant) and n.args[0].value in PROHIBIDOS):
            lineas.append(n.lineno)
    return lineas


def test_EL_ESTRUCTURAL_solo_el_emisor_importa_smtplib():
    infractores = []
    for f in sorted(pathlib.Path("app").rglob("*.py")):
        if "__pycache__" in f.parts or f.as_posix() == EMISOR:
            continue
        for linea in _importa_smtp(f):
            infractores.append(f"{f.as_posix()}:{linea}")
    assert not infractores, (
        "smtplib solo se importa en notification_service.py; usa enviar_correo/entregar: "
        + ", ".join(infractores))
    assert _importa_smtp(pathlib.Path(EMISOR)), "el emisor comun deberia seguir siendo quien importa smtplib"


class _SmtpFalso:
    instancias: list = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port, self.timeout = host, port, timeout
        self.tls = False
        self.login_con = None
        self.enviados = []
        self.extensiones = {"starttls"}
        _SmtpFalso.instancias.append(self)

    def ehlo(self):
        return (250, b"ok")

    def has_extn(self, nombre):
        return nombre.lower() in self.extensiones

    def starttls(self):
        self.tls = True

    def login(self, u, p):
        self.login_con = (u, p)

    def send_message(self, msg, to_addrs=None):
        self.enviados.append((msg, to_addrs))

    def noop(self):
        return (250, b"ok")

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def smtp(monkeypatch):
    _SmtpFalso.instancias = []
    monkeypatch.setattr(ns.smtplib, "SMTP", _SmtpFalso)
    monkeypatch.setattr(ns.smtplib, "SMTP_SSL", _SmtpFalso)
    return _SmtpFalso


def _servidor(**kw):
    base = dict(host="smtp.test", port=587, user="u", password="p", remitente="avisos@empresa.com")
    base.update(kw)
    return ns.ServidorSmtp(**base)


def test_envia_html_cc_adjunto_y_autentica_con_tls(smtp):
    r = ns.enviar_correo(["a@x.com"], "Asunto", "<p>hola</p>", cc=["c@x.com"],
                         adjuntos=[("i.pdf", b"%PDF", "application/pdf")], servidor=_servidor())
    assert r.enviado
    con = smtp.instancias[0]
    assert con.tls and con.login_con == ("u", "p")
    msg, destinos = con.enviados[0]
    assert destinos == ["a@x.com", "c@x.com"]
    assert msg["From"] == "avisos@empresa.com" and msg["Cc"] == "c@x.com"
    adjuntos = list(msg.iter_attachments())
    assert [a.get_filename() for a in adjuntos] == ["i.pdf"]
    assert adjuntos[0].get_content_type() == "application/pdf"


def test_no_manda_credenciales_en_claro_si_no_hay_starttls(smtp, monkeypatch):
    monkeypatch.setattr(_SmtpFalso, "has_extn", lambda self, n: False)
    r = ns.enviar_correo("a@x.com", "s", "<p>x</p>", servidor=_servidor())
    assert not r.enviado and "STARTTLS" in r.error
    assert smtp.instancias[0].login_con is None and not smtp.instancias[0].enviados


def test_sin_host_no_envia_ni_lanza(smtp):
    r = ns.enviar_correo("a@x.com", "s", "<p>x</p>", servidor=_servidor(host=None))
    assert not r.enviado and not smtp.instancias


def test_send_email_historico_usa_el_env(smtp, monkeypatch):
    monkeypatch.setattr(ns.settings, "SMTP_HOST", "smtp.env")
    monkeypatch.setattr(ns.settings, "SMTP_USER", "envuser")
    monkeypatch.setattr(ns.settings, "SMTP_PASS", "envpass")
    monkeypatch.setattr(ns.settings, "SMTP_FROM", "from@env.com")
    assert ns.NotificationService.send_email("a@x.com", "s", "<p>x</p>") is True
    con = smtp.instancias[0]
    assert con.host == "smtp.env" and con.timeout == 10.0 and con.login_con == ("envuser", "envpass")
    assert con.enviados[0][0]["From"] == "from@env.com"


def test_correo_del_service_desk_usa_la_config_de_la_organizacion(smtp, monkeypatch):
    from app.services.service_desk import correo
    monkeypatch.setattr(
        "app.services.integration_credentials_service.get_provider_config",
        lambda db, prov, org_id=None: {"host": "smtp.org", "port": 465, "user": "o", "password": "k",
                                       "from": "sd@org.com"})
    r = correo.enviar(None, "org-1", "cliente@x.com", "Ticket", "<p>h</p>", "h", responder_a="r@org.com")
    assert r.enviado and r.message_id and r.message_id.endswith("@org.com>")
    con = smtp.instancias[0]
    assert con.host == "smtp.org" and con.port == 465 and not con.tls  # 465: TLS implicito
    msg = con.enviados[0][0]
    assert msg["Reply-To"] == "r@org.com" and msg.get_body(("plain",)).get_content().strip() == "h"


def test_informe_bi_un_mensaje_por_destinatario(smtp, monkeypatch):
    from app.services import bi_report_delivery_service as bi
    monkeypatch.setattr(ns.settings, "SMTP_HOST", "smtp.env")
    assert bi._send_email(["a@x.com", "b@x.com"], "s", "<p>x</p>", b"data", "r.xlsx") is True
    enviados = [m for c in smtp.instancias for m, _ in c.enviados]
    assert [m["To"] for m in enviados] == ["a@x.com", "b@x.com"]
    assert all(len(m.get_all("To")) == 1 for m in enviados)
