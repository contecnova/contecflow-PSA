"""SAML 2.0 — Service Provider (23-11-2026).

Antes solo existían `/saml/metadata` y `/saml/health`: la metadata anunciaba un
ACS (`/saml/callback`) y un SLO (`/saml/logout`) que no existían, y el esquema
rechazaba `provider="saml"`. Ahora el flujo está completo:

1. `iniciar_login`: AuthnRequest (binding HTTP-Redirect) con un ID aleatorio,
   guardado con el `RelayState` en el almacén efímero de un solo uso
   (`estado_efimero`, Redis o memoria, el mismo del OIDC).
2. `validar_respuesta` (ACS, binding HTTP-POST). Controles, todos obligatorios:
   - XML sin DTD ni entidades (XXE) y con tamaño máximo;
   - `Status` = Success; sin aserciones cifradas (no soportadas: se rechazan);
   - **firma** XML-DSig con el certificado del IdP configurado (signxml, sin
     SHA-1), sobre la Response o sobre la Assertion; solo se confía en lo que
     devuelve el verificador (lo firmado), nunca en el documento recibido
     ("see what is signed"), y debe haber exactamente una Assertion;
   - `Issuer` = `saml_entity_id` del proveedor;
   - **audiencia**: `AudienceRestriction` incluye el entity ID de este SP;
   - **destino**: `Destination` de la Response (si viene) y `Recipient` de la
     `SubjectConfirmation` (bearer) = URL del ACS;
   - **caducidad**: `NotBefore` / `NotOnOrAfter` de `Conditions` y de la
     `SubjectConfirmationData`, con la holgura de reloj del SSO;
   - **anti-replay**: `InResponseTo` = el ID de la AuthnRequest pendiente, que
     se consume de forma atómica al llegar (GETDEL). Una respuesta repetida no
     encuentra su petición. Por eso no se acepta SSO iniciado por el IdP
     (respuestas sin `InResponseTo`).
3. El ACS no emite tokens: deja la identidad validada tras un **ticket** de un
   solo uso y redirige al login del frontend, que lo canjea por POST
   (`/saml/canjear`) y sigue el mismo camino que el OIDC (alta JIT, empresa,
   MFA, sesión, auditoría).
4. SLO: `construir_logout_request` (SP → IdP) y `validar_logout_request`
   (IdP → SP, binding HTTP-Redirect con firma de query RSA-SHA256/512
   obligatoria).

Librería: signxml (Python puro sobre lxml + cryptography). python3-saml y
pysaml2 necesitan xmlsec nativo, que rompería la instalación de setup.sh y
setup.bat en equipos sin libxmlsec1 (ver requirements.txt).
"""
from __future__ import annotations

import base64
import secrets
import urllib.parse
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional
from xml.sax.saxutils import escape as _escape

from app.core.config import settings


def _escapar(valor) -> str:
    """Escapa texto y comillas para meterlo en un atributo o nodo XML."""
    return _escape(str(valor), {'"': "&quot;"})

NS = {
    "samlp": "urn:oasis:names:tc:SAML:2.0:protocol",
    "saml": "urn:oasis:names:tc:SAML:2.0:assertion",
    "ds": "http://www.w3.org/2000/09/xmldsig#",
}
_SAMLP = "{%s}" % NS["samlp"]
_SAML = "{%s}" % NS["saml"]
_DS = "{%s}" % NS["ds"]
EXITO = "urn:oasis:names:tc:SAML:2.0:status:Success"
BEARER = "urn:oasis:names:tc:SAML:2.0:cm:bearer"
MAX_BYTES = 256 * 1024
PREFIJO_PETICION = "saml-peticion:"
PREFIJO_TICKET = "saml-ticket:"
_ALGORITMOS_QUERY = {
    "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256": "sha256",
    "http://www.w3.org/2001/04/xmldsig-more#rsa-sha512": "sha512",
}


class ErrorSaml(Exception):
    """Rechazo de una respuesta o petición SAML. `codigo` va a la auditoría y al frontend."""

    def __init__(self, codigo: str, detalle: str = ""):
        super().__init__(detalle or codigo)
        self.codigo = codigo
        self.detalle = detalle or codigo


@dataclass
class IdentidadSaml:
    config_id: str
    email: str
    nombre: str
    name_id: str
    sesion_idp: Optional[str] = None
    atributos: dict = field(default_factory=dict)


# ── URLs de este SP ──────────────────────────────────────────────────────────

def urls_sp() -> dict:
    base = (settings.BASE_URL or "").rstrip("/")
    return {
        "entity_id": f"{base}/api/v1/auth/saml/metadata",
        "acs": f"{base}/api/v1/auth/saml/callback",
        "slo": f"{base}/api/v1/auth/saml/logout",
    }


def metadata_xml() -> str:
    u = urls_sp()
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<EntityDescriptor xmlns="urn:oasis:names:tc:SAML:2.0:metadata" entityID="{_escapar(u['entity_id'])}">
  <SPSSODescriptor AuthnRequestsSigned="false" WantAssertionsSigned="true" protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <SingleLogoutService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect" Location="{_escapar(u['slo'])}"/>
    <NameIDFormat>urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress</NameIDFormat>
    <AssertionConsumerService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST" Location="{_escapar(u['acs'])}" index="1" isDefault="true"/>
  </SPSSODescriptor>
</EntityDescriptor>
"""


# ── Utilidades ───────────────────────────────────────────────────────────────

def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _instante(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _leer_instante(valor: Optional[str]) -> Optional[datetime]:
    if not valor:
        return None
    try:
        dt = datetime.fromisoformat(valor.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ErrorSaml("saml_fecha_no_valida", f"Fecha SAML no válida: {valor!r}") from exc
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _redirect(url_idp: str, parametro: str, xml: str, relay_state: Optional[str] = None) -> str:
    comprimido = zlib.compress(xml.encode("utf-8"))[2:-4]  # DEFLATE crudo (binding HTTP-Redirect)
    query = {parametro: base64.b64encode(comprimido).decode("ascii")}
    if relay_state:
        query["RelayState"] = relay_state
    return url_idp + ("&" if "?" in url_idp else "?") + urllib.parse.urlencode(query)


def _inflar(valor_b64: str) -> bytes:
    try:
        datos = base64.b64decode(valor_b64, validate=False)
        xml = zlib.decompress(datos, -15)
    except (ValueError, zlib.error) as exc:
        raise ErrorSaml("saml_codificacion_no_valida", "Mensaje SAML mal codificado") from exc
    if len(xml) > MAX_BYTES:
        raise ErrorSaml("saml_demasiado_grande")
    return xml


def parsear_xml(xml: bytes):
    """lxml sin DTD, sin entidades y sin red (XXE / billion laughs)."""
    from lxml import etree

    if len(xml) > MAX_BYTES:
        raise ErrorSaml("saml_demasiado_grande", "Respuesta SAML demasiado grande")
    cabecera = xml[:4096].upper()
    if b"<!DOCTYPE" in cabecera or b"<!ENTITY" in xml.upper():
        raise ErrorSaml("saml_dtd_no_permitido", "La respuesta SAML trae DTD o entidades")
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False,
                             dtd_validation=False, huge_tree=False, remove_pis=True)
    try:
        return etree.fromstring(xml, parser)
    except etree.XMLSyntaxError as exc:
        raise ErrorSaml("saml_xml_no_valido", "Respuesta SAML mal formada") from exc


def certificado_pem(texto: Optional[str]) -> str:
    """El certificado del IdP en PEM (acepta el base64 pelado que dan muchos IdP)."""
    limpio = (texto or "").strip()
    if not limpio:
        raise ErrorSaml("saml_sin_certificado", "El proveedor SAML no tiene certificado configurado")
    if "BEGIN CERTIFICATE" in limpio:
        return limpio
    cuerpo = "".join(limpio.split())
    lineas = [cuerpo[i:i + 64] for i in range(0, len(cuerpo), 64)]
    return "-----BEGIN CERTIFICATE-----\n" + "\n".join(lineas) + "\n-----END CERTIFICATE-----\n"


def _comprobar_ventana(no_antes: Optional[datetime], no_despues: Optional[datetime], ahora: datetime,
                       holgura: int, que: str) -> None:
    margen = timedelta(seconds=max(0, int(holgura)))
    if no_antes is not None and ahora + margen < no_antes:
        raise ErrorSaml("saml_aun_no_valida", f"{que} todavía no es válida (NotBefore)")
    if no_despues is not None and ahora - margen >= no_despues:
        raise ErrorSaml("saml_caducada", f"{que} caducada (NotOnOrAfter)")


# ── Login: AuthnRequest ──────────────────────────────────────────────────────

def iniciar_login(config) -> str:
    """URL del IdP con la AuthnRequest. Registra la petición pendiente (un solo uso)."""
    from app.services.auth_service.estado_efimero import register_sso_state

    if not config.saml_sso_url or not config.saml_entity_id:
        raise ErrorSaml("saml_config_incompleta", "Faltan saml_sso_url o saml_entity_id")
    u = urls_sp()
    peticion_id = "_" + secrets.token_hex(20)
    relay = secrets.token_urlsafe(32)
    register_sso_state(PREFIJO_PETICION + relay, {"config_id": config.id, "request_id": peticion_id})
    xml = (
        f'<samlp:AuthnRequest xmlns:samlp="{NS["samlp"]}" xmlns:saml="{NS["saml"]}" '
        f'ID="{peticion_id}" Version="2.0" IssueInstant="{_instante(_ahora())}" '
        f'Destination="{_escapar(config.saml_sso_url)}" '
        f'ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST" '
        f'AssertionConsumerServiceURL="{_escapar(u["acs"])}">'
        f'<saml:Issuer>{_escapar(u["entity_id"])}</saml:Issuer>'
        f'<samlp:NameIDPolicy Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress" AllowCreate="true"/>'
        f"</samlp:AuthnRequest>"
    )
    return _redirect(config.saml_sso_url, "SAMLRequest", xml, relay)


def consumir_peticion(relay_state: str) -> dict:
    """La petición pendiente de ese RelayState (y la borra). Sin ella no hay login."""
    from app.services.auth_service.estado_efimero import consume_sso_state_payload

    if not relay_state or len(relay_state) > 200:
        raise ErrorSaml("saml_relay_state_no_valido", "RelayState ausente o no válido")
    pendiente = consume_sso_state_payload(PREFIJO_PETICION + relay_state)
    if not pendiente or not pendiente.get("request_id") or not pendiente.get("config_id"):
        raise ErrorSaml("saml_peticion_desconocida",
                        "No hay una petición SAML pendiente: caducada, ya usada o iniciada por el IdP")
    return pendiente


# ── ACS: validación de la Response ───────────────────────────────────────────

def _verificar_firma(xml: bytes, raiz, certificado: str):
    """Devuelve la Assertion FIRMADA (de lo que devuelve signxml, no del documento)."""
    from signxml import InvalidInput, InvalidSignature, SignatureConfiguration, XMLVerifier

    aserciones = raiz.findall(f"{_SAML}Assertion")
    if len(aserciones) != 1 or len(raiz.findall(f".//{_SAML}Assertion")) != 1:
        raise ErrorSaml("saml_aserciones_no_validas", "La respuesta debe traer exactamente una Assertion")
    if raiz.find(f"{_DS}Signature") is not None:
        ubicacion = "./"
    elif aserciones[0].find(f"{_DS}Signature") is not None:
        ubicacion = f"./{_SAML}Assertion/"
    else:
        raise ErrorSaml("saml_sin_firma", "Ni la respuesta ni la aserción están firmadas")
    try:
        resultado = XMLVerifier().verify(
            xml, x509_cert=certificado,
            expect_config=SignatureConfiguration(location=ubicacion, expect_references=1),
        )
    except (InvalidSignature, InvalidInput) as exc:
        raise ErrorSaml("saml_firma_no_valida", f"Firma SAML no válida: {exc}") from exc
    firmado = resultado.signed_xml
    if firmado is None:
        raise ErrorSaml("saml_firma_no_valida", "La firma no cubre ningún elemento")
    if firmado.tag == f"{_SAMLP}Response":
        dentro = firmado.findall(f"{_SAML}Assertion")
        if len(dentro) != 1:
            raise ErrorSaml("saml_aserciones_no_validas", "La respuesta firmada no trae una única Assertion")
        return dentro[0]
    if firmado.tag == f"{_SAML}Assertion":
        return firmado
    raise ErrorSaml("saml_firma_no_valida", "La firma no cubre ni la Response ni la Assertion")


def _texto(nodo, ruta: str) -> str:
    hallado = nodo.find(ruta, NS)
    return (hallado.text or "").strip() if hallado is not None and hallado.text else ""


def _atributos(asercion) -> dict:
    salida: dict = {}
    for atributo in asercion.findall("saml:AttributeStatement/saml:Attribute", NS):
        nombre = atributo.get("Name") or ""
        valores = [(v.text or "").strip() for v in atributo.findall("saml:AttributeValue", NS) if (v.text or "").strip()]
        if nombre and valores:
            salida[nombre] = valores
            amigable = atributo.get("FriendlyName")
            if amigable:
                salida.setdefault(amigable, valores)
    return salida


def validar_respuesta(config, saml_response_b64: str, peticion_id: str,
                      ahora: Optional[datetime] = None, holgura: Optional[int] = None) -> IdentidadSaml:
    """Valida la Response del IdP (ver docstring del módulo) y devuelve la identidad."""
    if not saml_response_b64 or len(saml_response_b64) > MAX_BYTES * 2:
        raise ErrorSaml("saml_respuesta_vacia", "Falta SAMLResponse")
    try:
        xml = base64.b64decode(saml_response_b64, validate=False)
    except ValueError as exc:
        raise ErrorSaml("saml_codificacion_no_valida", "SAMLResponse no es base64") from exc
    raiz = parsear_xml(xml)
    if raiz.tag != f"{_SAMLP}Response":
        raise ErrorSaml("saml_no_es_response", "El mensaje no es una samlp:Response")
    if raiz.find(f".//{_SAML}EncryptedAssertion") is not None:
        raise ErrorSaml("saml_cifrada_no_soportada",
                        "Aserciones cifradas no soportadas: desactiva el cifrado en el IdP (la firma es obligatoria)")
    estado = raiz.find("samlp:Status/samlp:StatusCode", NS)
    if estado is None or estado.get("Value") != EXITO:
        raise ErrorSaml("saml_idp_rechazo", f"El IdP no autenticó: {estado.get('Value') if estado is not None else '?'}")

    u = urls_sp()
    destino = raiz.get("Destination")
    if destino and destino != u["acs"]:
        raise ErrorSaml("saml_destino_no_valido", "Destination no es el ACS de este SP")
    if raiz.get("InResponseTo") and raiz.get("InResponseTo") != peticion_id:
        raise ErrorSaml("saml_in_response_to", "InResponseTo no corresponde a la petición pendiente")

    asercion = _verificar_firma(xml, raiz, certificado_pem(config.saml_certificate))
    ahora = ahora or _ahora()
    if holgura is None:
        from app.services.auth_service.sso import sso_holgura_de_reloj
        holgura = sso_holgura_de_reloj()

    emisor = _texto(asercion, "saml:Issuer")
    if not config.saml_entity_id or emisor != config.saml_entity_id.strip():
        raise ErrorSaml("saml_emisor_no_valido", "Issuer de la aserción distinto del IdP configurado")

    condiciones = asercion.find("saml:Conditions", NS)
    if condiciones is None:
        raise ErrorSaml("saml_sin_condiciones", "La aserción no trae Conditions")
    _comprobar_ventana(_leer_instante(condiciones.get("NotBefore")),
                       _leer_instante(condiciones.get("NotOnOrAfter")), ahora, holgura, "La aserción")
    audiencias = [(a.text or "").strip() for a in condiciones.findall("saml:AudienceRestriction/saml:Audience", NS)]
    if u["entity_id"] not in audiencias:
        raise ErrorSaml("saml_audiencia_no_valida", "La aserción no está dirigida a este SP (Audience)")

    sujeto = asercion.find("saml:Subject", NS)
    if sujeto is None:
        raise ErrorSaml("saml_sin_sujeto", "La aserción no trae Subject")
    confirmada = False
    for confirmacion in sujeto.findall("saml:SubjectConfirmation", NS):
        if confirmacion.get("Method") != BEARER:
            continue
        datos = confirmacion.find("saml:SubjectConfirmationData", NS)
        if datos is None:
            continue
        if datos.get("Recipient") != u["acs"]:
            raise ErrorSaml("saml_destino_no_valido", "Recipient no es el ACS de este SP")
        if datos.get("InResponseTo") != peticion_id:
            raise ErrorSaml("saml_in_response_to", "InResponseTo no corresponde a la petición pendiente")
        no_despues = _leer_instante(datos.get("NotOnOrAfter"))
        if no_despues is None:
            raise ErrorSaml("saml_caducada", "SubjectConfirmationData sin NotOnOrAfter")
        _comprobar_ventana(_leer_instante(datos.get("NotBefore")), no_despues, ahora, holgura, "La confirmación")
        confirmada = True
        break
    if not confirmada:
        raise ErrorSaml("saml_sin_confirmacion", "Sin SubjectConfirmation bearer válida")

    name_id = _texto(sujeto, "saml:NameID")
    atributos = _atributos(asercion)
    clave_correo = (config.saml_attribute_email or "email").strip()
    clave_nombre = (config.saml_attribute_name or "displayName").strip()
    correo = (atributos.get(clave_correo) or [""])[0]
    if not correo and "@" in name_id:
        correo = name_id
    if not correo or "@" not in correo:
        raise ErrorSaml("saml_sin_email", "La aserción no trae el correo del usuario")
    nombre = (atributos.get(clave_nombre) or [""])[0] or correo
    autenticacion = asercion.find("saml:AuthnStatement", NS)
    sesion = autenticacion.get("SessionIndex") if autenticacion is not None else None
    return IdentidadSaml(config_id=config.id, email=correo.strip().lower(), nombre=nombre,
                         name_id=name_id or correo, sesion_idp=sesion, atributos=atributos)


def claims_de(config, identidad: IdentidadSaml) -> dict:
    """Las «claims» que espera `create_or_update_sso_user` (como un id_token OIDC)."""
    claims = {"sub": identidad.name_id, "email": identidad.email, "name": identidad.nombre}
    if config.saml_attribute_role:
        claims[config.groups_claim or "groups"] = identidad.atributos.get(config.saml_attribute_role.strip(), [])
    return claims


# ── Ticket de un solo uso: del ACS al frontend ───────────────────────────────

def emitir_ticket(identidad: IdentidadSaml) -> str:
    from app.services.auth_service.estado_efimero import register_sso_state

    ticket = secrets.token_urlsafe(32)
    register_sso_state(PREFIJO_TICKET + ticket, {
        "config_id": identidad.config_id, "email": identidad.email, "nombre": identidad.nombre,
        "name_id": identidad.name_id, "sesion_idp": identidad.sesion_idp, "atributos": identidad.atributos,
    })
    return ticket


def canjear_ticket(ticket: str) -> IdentidadSaml:
    from app.services.auth_service.estado_efimero import consume_sso_state_payload

    if not ticket or len(ticket) > 200:
        raise ErrorSaml("saml_ticket_no_valido")
    datos = consume_sso_state_payload(PREFIJO_TICKET + ticket)
    if not datos or not datos.get("email"):
        raise ErrorSaml("saml_ticket_no_valido", "Ticket SAML caducado o ya usado")
    return IdentidadSaml(config_id=datos["config_id"], email=datos["email"], nombre=datos.get("nombre") or "",
                         name_id=datos.get("name_id") or datos["email"], sesion_idp=datos.get("sesion_idp"),
                         atributos=datos.get("atributos") or {})


# ── SLO ──────────────────────────────────────────────────────────────────────

def construir_logout_request(config, name_id: str, sesion_idp: Optional[str] = None) -> Optional[str]:
    """URL del SLO del IdP con una LogoutRequest (SP → IdP); None si no hay SLO."""
    if not config.saml_slo_url:
        return None
    u = urls_sp()
    sesion = f"<samlp:SessionIndex>{_escapar(sesion_idp)}</samlp:SessionIndex>" if sesion_idp else ""
    xml = (
        f'<samlp:LogoutRequest xmlns:samlp="{NS["samlp"]}" xmlns:saml="{NS["saml"]}" '
        f'ID="_{secrets.token_hex(20)}" Version="2.0" IssueInstant="{_instante(_ahora())}" '
        f'Destination="{_escapar(config.saml_slo_url)}">'
        f'<saml:Issuer>{_escapar(u["entity_id"])}</saml:Issuer>'
        f'<saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress">{_escapar(name_id)}</saml:NameID>'
        f"{sesion}</samlp:LogoutRequest>"
    )
    return _redirect(config.saml_slo_url, "SAMLRequest", xml)


def _parametro_crudo(query_cruda: str, nombre: str) -> Optional[str]:
    for trozo in query_cruda.split("&"):
        if trozo.startswith(nombre + "="):
            return trozo
    return None


def verificar_firma_redirect(query_cruda: str, certificado: str, parametro: str = "SAMLRequest") -> None:
    """Firma del binding HTTP-Redirect: sobre `SAMLRequest=..&RelayState=..&SigAlg=..` tal cual llegaron."""
    from cryptography import x509
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    partes = [_parametro_crudo(query_cruda, n) for n in (parametro, "RelayState", "SigAlg")]
    firma_cruda = _parametro_crudo(query_cruda, "Signature")
    if not partes[0] or not partes[2] or not firma_cruda:
        raise ErrorSaml("saml_sin_firma", "El mensaje de logout del IdP debe venir firmado")
    algoritmo = urllib.parse.unquote_plus(partes[2].split("=", 1)[1])
    if algoritmo not in _ALGORITMOS_QUERY:
        raise ErrorSaml("saml_algoritmo_no_permitido", f"SigAlg no permitido: {algoritmo}")
    firmado = "&".join(p for p in partes if p).encode("ascii")
    try:
        firma = base64.b64decode(urllib.parse.unquote_plus(firma_cruda.split("=", 1)[1]))
        clave = x509.load_pem_x509_certificate(certificado.encode()).public_key()
        resumen = hashes.SHA256() if _ALGORITMOS_QUERY[algoritmo] == "sha256" else hashes.SHA512()
        clave.verify(firma, firmado, padding.PKCS1v15(), resumen)
    except (InvalidSignature, ValueError, TypeError, AttributeError) as exc:
        raise ErrorSaml("saml_firma_no_valida", "Firma del logout no válida") from exc


def validar_logout_request(configs: list, query_cruda: str, saml_request: str,
                           ahora: Optional[datetime] = None) -> tuple:
    """LogoutRequest iniciada por el IdP. Devuelve (config, name_id, id de la petición)."""
    raiz = parsear_xml(_inflar(saml_request))
    if raiz.tag != f"{_SAMLP}LogoutRequest":
        raise ErrorSaml("saml_no_es_logout", "El mensaje no es una LogoutRequest")
    emisor = _texto(raiz, "saml:Issuer")
    config = next((c for c in configs if (c.saml_entity_id or "").strip() == emisor), None)
    if config is None:
        raise ErrorSaml("saml_emisor_no_valido", "LogoutRequest de un IdP no configurado")
    verificar_firma_redirect(query_cruda, certificado_pem(config.saml_certificate))
    destino = raiz.get("Destination")
    if destino and destino != urls_sp()["slo"]:
        raise ErrorSaml("saml_destino_no_valido", "Destination no es el SLO de este SP")
    no_despues = _leer_instante(raiz.get("NotOnOrAfter"))
    if no_despues is not None and (ahora or _ahora()) >= no_despues:
        raise ErrorSaml("saml_caducada", "LogoutRequest caducada")
    name_id = _texto(raiz, "saml:NameID")
    if not name_id:
        raise ErrorSaml("saml_sin_sujeto", "LogoutRequest sin NameID")
    return config, name_id, raiz.get("ID") or ""


def construir_logout_response(config, en_respuesta_a: str) -> Optional[str]:
    if not config.saml_slo_url:
        return None
    u = urls_sp()
    xml = (
        f'<samlp:LogoutResponse xmlns:samlp="{NS["samlp"]}" xmlns:saml="{NS["saml"]}" '
        f'ID="_{secrets.token_hex(20)}" Version="2.0" IssueInstant="{_instante(_ahora())}" '
        f'Destination="{_escapar(config.saml_slo_url)}" InResponseTo="{_escapar(en_respuesta_a)}">'
        f'<saml:Issuer>{_escapar(u["entity_id"])}</saml:Issuer>'
        f'<samlp:Status><samlp:StatusCode Value="{EXITO}"/></samlp:Status>'
        f"</samlp:LogoutResponse>"
    )
    return _redirect(config.saml_slo_url, "SAMLResponse", xml)


def cerrar_sesiones_del_idp(db, query_cruda: str, saml_request: str, ip: Optional[str]):
    """SLO iniciado por el IdP: valida la LogoutRequest firmada y cierra las sesiones
    de su usuario (en la empresa de la configuración SAML), con auditoría y commit.

    Devuelve `(config, peticion_id, sesiones_cerradas)`; lanza `ErrorSaml` si la
    petición no vale. Prueba global 23-11-2026: vivía en la ruta, que consultaba
    `sso_configs`/`users` y confirmaba la transacción en la capa API.
    """
    from sqlalchemy import func
    from app.models.enterprise import SSOConfig
    from app.models.user import User
    from app.services.audit import audit_log
    from app.services.auth_service.tokens_y_cookies import revocar_sesiones_del_usuario
    from app.services.transaccion import confirmar
    configs = db.query(SSOConfig).filter(SSOConfig.provider == "saml", SSOConfig.is_active == True,  # noqa: E712
                                         SSOConfig.is_deleted == False).all()  # noqa: E712
    config, name_id, peticion_id = validar_logout_request(configs, query_cruda, saml_request)
    q = db.query(User).filter(func.lower(User.email) == name_id.strip().lower())
    if config.organization_id:
        q = q.filter(User.organization_id == config.organization_id)
    usuario = q.first()
    cerradas = 0
    if usuario is not None:
        cerradas = revocar_sesiones_del_usuario(db, usuario.id, "saml_slo_idp")
        audit_log(db, usuario, "LOGOUT", "users", usuario.id, usuario.full_name,
                  metadata={"metodo": "saml", "origen": "idp", "sso_config_id": config.id,
                            "sesiones_cerradas": cerradas},
                  ip_address=ip)
    confirmar(db)
    return config, peticion_id, cerradas


def url_de_logout_del_usuario(db, usuario) -> Optional[str]:
    """SLO SAML (23-11-2026): si entró por SAML y su IdP tiene SLO, la URL a la que
    el frontend redirige para cerrar también la sesión del IdP (la configuración de
    su empresa o, si no hay, la global)."""
    if (getattr(usuario, "sso_provider", None) or "") != "saml":
        return None
    from sqlalchemy import or_
    from app.models.enterprise import SSOConfig
    config = db.query(SSOConfig).filter(
        SSOConfig.provider == "saml", SSOConfig.is_active == True, SSOConfig.is_deleted == False,  # noqa: E712
        or_(SSOConfig.organization_id == usuario.organization_id, SSOConfig.organization_id.is_(None)),
    ).order_by(SSOConfig.organization_id.is_(None)).first()
    return construir_logout_request(config, usuario.email or usuario.username) if config else None
