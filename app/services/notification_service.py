"""
Notification Service — el correo saliente de la plataforma.

Auditoria 2026-11 (hallazgo 20). SMTP se abria directamente desde ocho sitios
(este, `auth_service`, `cab_service`, `bi_report_delivery_service`,
`scheduled_reports`, `collaboration/_email_digest`, `service_desk/correo` y la
prueba de conexion de `integration_test_service`), cada uno con su manera de
negociar TLS, de elegir remitente y de autenticarse —y con errores distintos en
cada copia—. Este modulo es ahora el UNICO de `app/` que importa `smtplib`
(lo vigila `tests/test_correo_un_solo_emisor.py`):

  * `ServidorSmtp`      — de donde salen host/puerto/credenciales/remitente:
                          `.del_entorno()` (`SMTP_*` del `.env`) o
                          `.de_organizacion(db, org_id)` (Admin → Integraciones,
                          con el `.env` de respaldo).
  * `construir_mensaje` — texto, HTML, CC, Reply-To, Message-ID y adjuntos.
  * `entregar`          — abre la conexion, negocia TLS, autentica y envia.
                          Lanza `ErrorDeCorreo`/`OSError`.
  * `enviar_correo`     — lo anterior en una llamada que NO lanza: devuelve
                          `ResultadoEnvio`.
  * `comprobar_smtp`    — la prueba de conexion de la pantalla de Admin.

`NotificationService.send_email` y `send_email_notification` se conservan con
su firma: los usan `encolar(...)` y una decena de servicios.
"""
from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Iterable, Optional, Sequence, Union

from app.core.config import settings
from app.services.settings_service import outbound_http_timeout

logger = logging.getLogger(__name__)

#: Lo que lanza `entregar` ademas de `OSError`. Los llamadores lo capturan con
#: este nombre para no tener que importar `smtplib`.
ErrorDeCorreo = smtplib.SMTPException


# ── Transporte SMTP ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ServidorSmtp:
    host: Optional[str]
    port: int = 587
    user: Optional[str] = None
    password: Optional[str] = None
    remitente: Optional[str] = None
    timeout: float = 30.0

    @property
    def configurado(self) -> bool:
        return bool(self.host)

    def remitente_efectivo(self) -> str:
        """`from` configurado → usuario SMTP → `NOTIFICATION_EMAIL_FROM`."""
        return self.remitente or self.user or settings.NOTIFICATION_EMAIL_FROM

    @classmethod
    def del_entorno(cls, timeout: float = 30.0) -> "ServidorSmtp":
        """El SMTP del `.env` (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM`)."""
        return cls(
            host=settings.SMTP_HOST or None,
            port=int(settings.SMTP_PORT or 587),
            user=settings.SMTP_USER or None,
            password=settings.SMTP_PASS or None,
            remitente=settings.SMTP_FROM or None,
            timeout=timeout,
        )

    @classmethod
    def de_organizacion(cls, db, org_id: Optional[str], timeout: float = 30.0) -> "ServidorSmtp":
        """El SMTP que la organizacion configuro en Admin, con el `.env` de respaldo."""
        from app.services.integration_credentials_service import get_provider_config
        cfg = get_provider_config(db, "smtp", org_id=org_id) or {}
        return cls(
            host=cfg.get("host") or None,
            port=int(cfg.get("port") or 587),
            user=cfg.get("user") or None,
            password=cfg.get("password") or None,
            remitente=cfg.get("from") or None,
            timeout=timeout,
        )


@dataclass
class ResultadoEnvio:
    enviado: bool
    message_id: Optional[str] = None
    error: Optional[str] = None


#: (nombre de fichero, contenido, tipo MIME «principal/secundario»)
Adjunto = tuple[str, bytes, str]


def _lista(valor: Union[str, Iterable[str], None]) -> list[str]:
    if not valor:
        return []
    if isinstance(valor, str):
        return [valor]
    return [v for v in valor if v]


def construir_mensaje(
    *,
    remitente: str,
    para: Union[str, Sequence[str]],
    asunto: str,
    html: Optional[str] = None,
    texto: Optional[str] = None,
    cc: Optional[Sequence[str]] = None,
    responder_a: Optional[str] = None,
    adjuntos: Optional[Sequence[Adjunto]] = None,
    con_message_id: bool = False,
) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = remitente
    msg["To"] = ", ".join(_lista(para))
    if cc:
        msg["Cc"] = ", ".join(_lista(cc))
    if responder_a:
        msg["Reply-To"] = responder_a
    if con_message_id:
        msg["Message-ID"] = make_msgid(domain=remitente.rpartition("@")[2] or None)
    if texto is not None:
        msg.set_content(texto)
        if html is not None:
            msg.add_alternative(html, subtype="html")
    else:
        msg.set_content(html or "", subtype="html")
    for nombre, contenido, tipo in adjuntos or ():
        principal, _, secundario = (tipo or "application/octet-stream").partition("/")
        msg.add_attachment(contenido, maintype=principal, subtype=secundario or "octet-stream",
                           filename=nombre)
    return msg


def _abrir(servidor: ServidorSmtp) -> smtplib.SMTP:
    """Conecta y deja la sesion cifrada y autenticada.

    Una sola politica para toda la aplicacion:
      * puerto 465 → TLS implicito (`SMTP_SSL`);
      * en otro puerto, STARTTLS si el servidor lo ofrece;
      * si no lo ofrece y hay credenciales (y no es el 25, el de relay
        interno), NO se mandan en claro: se lanza `SMTPNotSupportedError`.
    """
    if servidor.port == 465:
        conexion = smtplib.SMTP_SSL(servidor.host, servidor.port, timeout=servidor.timeout)
    else:
        conexion = smtplib.SMTP(servidor.host, servidor.port, timeout=servidor.timeout)
    try:
        conexion.ehlo()
        if servidor.port != 465:
            if conexion.has_extn("starttls"):
                conexion.starttls()
                conexion.ehlo()
            elif servidor.user and servidor.password and servidor.port != 25:
                raise smtplib.SMTPNotSupportedError(
                    "el servidor no ofrece STARTTLS: no se envian credenciales en claro")
        if servidor.user and servidor.password:
            conexion.login(servidor.user, servidor.password)
    except BaseException:
        conexion.close()
        raise
    return conexion


def entregar(servidor: ServidorSmtp, mensaje: EmailMessage,
             destinatarios: Optional[Sequence[str]] = None) -> None:
    """Envia `mensaje`. Lanza `ErrorDeCorreo` u `OSError` si no sale.

    Sin `destinatarios`, los toma de To/Cc/Bcc del mensaje.
    """
    if not servidor.configurado:
        raise ErrorDeCorreo("SMTP sin configurar (host)")
    conexion = _abrir(servidor)
    with conexion:
        conexion.send_message(mensaje, to_addrs=list(destinatarios) if destinatarios else None)


def comprobar_smtp(servidor: ServidorSmtp) -> None:
    """Conecta, negocia TLS, autentica y hace NOOP. Lanza si algo falla."""
    if not servidor.configurado:
        raise ErrorDeCorreo("SMTP host no configurado")
    with _abrir(servidor) as conexion:
        conexion.noop()


def enviar_correo(
    para: Union[str, Sequence[str]],
    asunto: str,
    html: Optional[str] = None,
    *,
    texto: Optional[str] = None,
    remitente: Optional[str] = None,
    cc: Optional[Sequence[str]] = None,
    responder_a: Optional[str] = None,
    adjuntos: Optional[Sequence[Adjunto]] = None,
    servidor: Optional[ServidorSmtp] = None,
    con_message_id: bool = False,
) -> ResultadoEnvio:
    """La puerta comun del correo saliente. No lanza: el fallo vuelve en el resultado."""
    servidor = servidor or ServidorSmtp.del_entorno()
    destinos = _lista(para) + _lista(cc)
    if not servidor.configurado:
        logger.warning("Correo NO enviado (SMTP sin configurar): asunto=%s", asunto)
        return ResultadoEnvio(False, error="SMTP sin configurar (host)")
    if not destinos:
        return ResultadoEnvio(False, error="sin destinatarios")
    msg = construir_mensaje(
        remitente=remitente or servidor.remitente_efectivo(), para=para, asunto=asunto,
        html=html, texto=texto, cc=cc, responder_a=responder_a, adjuntos=adjuntos,
        con_message_id=con_message_id,
    )
    try:
        entregar(servidor, msg, destinos)
    except (ErrorDeCorreo, OSError) as exc:
        dominios = ",".join(sorted({d.rpartition("@")[2] for d in destinos}))
        logger.warning("correo no enviado a @%s: %s", dominios, exc)
        return ResultadoEnvio(False, error=str(exc)[:500])
    logger.info("Correo enviado: asunto=%s destinatarios=%d", asunto, len(destinos))
    return ResultadoEnvio(True, message_id=msg["Message-ID"])


# ── API historica ────────────────────────────────────────────────────────────

class NotificationService:
    """Envio de correos de aviso con el SMTP del `.env`."""

    @staticmethod
    def send_email(
        to: str,
        subject: str,
        html_body: str,
        from_addr: Optional[str] = None,
    ) -> bool:
        """Envia un correo HTML. Devuelve si salio; sin `SMTP_HOST` registra y devuelve False.

        Auditoria 2026-08: aqui se leia `SMTP_PASSWORD`, ajuste que no existe
        (es `SMTP_PASS`), y ningun correo se autenticaba. Ahora las credenciales
        salen de `ServidorSmtp.del_entorno()`, el mismo sitio para todos.
        """
        return enviar_correo(
            to, subject, html_body, remitente=from_addr,
            servidor=ServidorSmtp.del_entorno(timeout=outbound_http_timeout(default=10.0)),
        ).enviado


def send_email_notification(to: str, subject: str, body: str) -> bool:
    """Synchronous wrapper around NotificationService.send_email for automation actions."""
    return NotificationService.send_email(to=to, subject=subject, html_body=body)


# Singleton instance
notification_service = NotificationService()
