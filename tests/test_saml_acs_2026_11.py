"""SAML 2.0: ACS con firma, audiencia, destino, caducidad y anti-replay (23-11-2026).

Antes solo existían `/saml/metadata` y `/saml/health`. Estas pruebas firman
respuestas de verdad con signxml y un certificado autofirmado, y comprueban que
`app.services.auth_service.saml.validar_respuesta` acepta la buena y rechaza
cada manipulación.
"""
from __future__ import annotations

import base64
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

pytest.importorskip("signxml")

from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from cryptography.x509.oid import NameOID  # noqa: E402

from app.services.auth_service import saml  # noqa: E402

IDP = "https://idp.example.com/metadata"


def _clave_y_cert():
    clave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nombre = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "idp.example.com")])
    ahora = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(nombre).issuer_name(nombre)
            .public_key(clave.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(ahora - timedelta(days=1)).not_valid_after(ahora + timedelta(days=30))
            .sign(clave, hashes.SHA256()))
    pem_clave = clave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption())
    return pem_clave, cert.public_bytes(serialization.Encoding.PEM).decode()


CLAVE, CERT = _clave_y_cert()
OTRA_CLAVE, OTRO_CERT = _clave_y_cert()


def _config(**cambios):
    base = dict(id="cfg-saml", provider="saml", saml_entity_id=IDP, saml_sso_url="https://idp.example.com/sso",
                saml_slo_url=None, saml_certificate=CERT, saml_attribute_email="email",
                saml_attribute_name="displayName", saml_attribute_role=None, groups_claim="groups")
    base.update(cambios)
    return SimpleNamespace(**base)


def _t(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _respuesta(peticion="_pet1", audiencia=None, recipient=None, no_despues=None, emisor=IDP,
               correo="ana@empresa.com", destino=None):
    u = saml.urls_sp()
    ahora = datetime.now(timezone.utc)
    no_despues = no_despues or ahora + timedelta(minutes=5)
    rid, aid = f"_{uuid.uuid4().hex}", f"_{uuid.uuid4().hex}"
    return f"""<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" ID="{rid}" Version="2.0" IssueInstant="{_t(ahora)}" Destination="{destino or u['acs']}" InResponseTo="{peticion}">
<saml:Issuer>{emisor}</saml:Issuer>
<samlp:Status><samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/></samlp:Status>
<saml:Assertion ID="{aid}" Version="2.0" IssueInstant="{_t(ahora)}">
<saml:Issuer>{emisor}</saml:Issuer>
<saml:Subject><saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress">{correo}</saml:NameID>
<saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer"><saml:SubjectConfirmationData InResponseTo="{peticion}" NotOnOrAfter="{_t(no_despues)}" Recipient="{recipient or u['acs']}"/></saml:SubjectConfirmation></saml:Subject>
<saml:Conditions NotBefore="{_t(ahora - timedelta(minutes=1))}" NotOnOrAfter="{_t(no_despues)}"><saml:AudienceRestriction><saml:Audience>{audiencia or u['entity_id']}</saml:Audience></saml:AudienceRestriction></saml:Conditions>
<saml:AuthnStatement AuthnInstant="{_t(ahora)}" SessionIndex="sesion-1"/>
<saml:AttributeStatement><saml:Attribute Name="email"><saml:AttributeValue>{correo}</saml:AttributeValue></saml:Attribute><saml:Attribute Name="displayName"><saml:AttributeValue>Ana Torres</saml:AttributeValue></saml:Attribute></saml:AttributeStatement>
</saml:Assertion>
</samlp:Response>""", rid


def _firmar(xml: str, rid: str, clave=CLAVE, cert=CERT) -> bytes:
    from lxml import etree
    from signxml import XMLSigner

    raiz = etree.fromstring(xml.encode())
    firmado = XMLSigner(c14n_algorithm="http://www.w3.org/2001/10/xml-exc-c14n#").sign(
        raiz, key=clave, cert=cert, reference_uri=f"#{rid}")
    return etree.tostring(firmado)


def _b64(datos: bytes) -> str:
    return base64.b64encode(datos).decode()


def test_respuesta_firmada_y_correcta_da_la_identidad():
    xml, rid = _respuesta()
    identidad = saml.validar_respuesta(_config(), _b64(_firmar(xml, rid)), "_pet1", holgura=0)
    assert identidad.email == "ana@empresa.com"
    assert identidad.nombre == "Ana Torres"
    assert identidad.sesion_idp == "sesion-1"


@pytest.mark.parametrize(("cambio", "codigo"), [
    ({"audiencia": "https://otro-sp.example.com"}, "saml_audiencia_no_valida"),
    ({"recipient": "https://atacante.example.com/acs"}, "saml_destino_no_valido"),
    ({"emisor": "https://otro-idp.example.com"}, "saml_emisor_no_valido"),
    ({"peticion": "_otra"}, "saml_in_response_to"),
])
def test_cada_control_rechaza_su_manipulacion(cambio, codigo):
    xml, rid = _respuesta(**cambio)
    with pytest.raises(saml.ErrorSaml) as e:
        saml.validar_respuesta(_config(), _b64(_firmar(xml, rid)), "_pet1", holgura=0)
    assert e.value.codigo == codigo


def test_caducada_se_rechaza():
    xml, rid = _respuesta(no_despues=datetime.now(timezone.utc) - timedelta(minutes=10))
    with pytest.raises(saml.ErrorSaml) as e:
        saml.validar_respuesta(_config(), _b64(_firmar(xml, rid)), "_pet1", holgura=0)
    assert e.value.codigo == "saml_caducada"


def test_firma_de_otra_clave_se_rechaza():
    xml, rid = _respuesta()
    with pytest.raises(saml.ErrorSaml) as e:
        saml.validar_respuesta(_config(), _b64(_firmar(xml, rid, OTRA_CLAVE, OTRO_CERT)), "_pet1", holgura=0)
    assert e.value.codigo == "saml_firma_no_valida"


def test_manipular_lo_firmado_rompe_la_firma():
    xml, rid = _respuesta()
    firmado = _firmar(xml, rid).replace(b"ana@empresa.com", b"jefe@empresa.com")
    with pytest.raises(saml.ErrorSaml) as e:
        saml.validar_respuesta(_config(), _b64(firmado), "_pet1", holgura=0)
    assert e.value.codigo == "saml_firma_no_valida"


def test_sin_firma_se_rechaza():
    xml, _ = _respuesta()
    with pytest.raises(saml.ErrorSaml) as e:
        saml.validar_respuesta(_config(), _b64(xml.encode()), "_pet1", holgura=0)
    assert e.value.codigo == "saml_sin_firma"


def test_dtd_y_entidades_se_rechazan_antes_de_parsear():
    malo = b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]><r>&x;</r>'
    with pytest.raises(saml.ErrorSaml) as e:
        saml.validar_respuesta(_config(), _b64(malo), "_pet1", holgura=0)
    assert e.value.codigo == "saml_dtd_no_permitido"


def test_la_peticion_pendiente_es_de_un_solo_uso(monkeypatch):
    """Anti-replay: el RelayState se consume al llegar; la misma respuesta otra vez no tiene petición."""
    url = saml.iniciar_login(_config())
    relay = url.split("RelayState=", 1)[1].split("&", 1)[0]
    from urllib.parse import unquote
    relay = unquote(relay)
    assert saml.consumir_peticion(relay)["config_id"] == "cfg-saml"
    with pytest.raises(saml.ErrorSaml) as e:
        saml.consumir_peticion(relay)
    assert e.value.codigo == "saml_peticion_desconocida"


def test_el_ticket_del_frontend_es_de_un_solo_uso():
    ticket = saml.emitir_ticket(saml.IdentidadSaml(config_id="cfg-saml", email="ana@empresa.com",
                                                   nombre="Ana", name_id="ana@empresa.com"))
    assert saml.canjear_ticket(ticket).email == "ana@empresa.com"
    with pytest.raises(saml.ErrorSaml):
        saml.canjear_ticket(ticket)


def test_metadata_anuncia_acs_y_slo_que_existen(client):
    r = client.get("/api/v1/auth/saml/metadata")
    assert r.status_code == 200
    u = saml.urls_sp()
    assert u["acs"] in r.text and u["slo"] in r.text
    rutas = {(m, ruta.path) for ruta in client.app.routes for m in getattr(ruta, "methods", set()) or set()}
    assert ("POST", "/api/v1/auth/saml/callback") in rutas
    assert ("GET", "/api/v1/auth/saml/logout") in rutas


def test_acs_sin_peticion_pendiente_redirige_con_error_y_audita(client, db):
    from app.models.enterprise import AuditLog

    r = client.post("/api/v1/auth/saml/callback", data={"SAMLResponse": _b64(b"<x/>"), "RelayState": "nada"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert "saml_error=saml_peticion_desconocida" in r.headers["location"]
    assert db.query(AuditLog).filter(AuditLog.action == "LOGIN_FAILED").count() >= 1
