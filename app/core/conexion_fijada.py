"""Conexiones de correo (SMTP e IMAP) a la IP ya validada (23-11-2026).

Auditoría 2026-11-22 (01 M7, 03 «SSRF por IMAP»). El host SMTP o IMAP de una
empresa lo escribe su administrador. `validar_host_saliente` lo resolvía y lo
validaba, pero después `smtplib`/`imaplib` volvían a resolver el nombre por su
cuenta al conectar: un DNS con TTL 0 podía contestar una IP pública a la
validación y una interna (127.0.0.1, 169.254.169.254, la red del servidor) a la
conexión real (DNS rebinding). Ahora:

1. `ip_fijada(host)` valida el host y devuelve UNA de las IPs validadas.
2. `socket_fijado` abre el socket contra esa IP (no vuelve a resolver) y
   comprueba la IP del otro extremo (`comprobar_conexion`). Lo usan
   `Imap4SslFijado` (aquí) y `SmtpFijado`/`SmtpSslFijado` (en
   `notification_service`, el único módulo que importa `smtplib`), que
   negocian TLS con el NOMBRE original: SNI y verificación del certificado
   siguen siendo los del host configurado.
3. Un host que no resuelve en la validación se rechaza (antes pasaba: la
   segunda resolución, la de la conexión, podía dar una IP interna).

Un host de `OUTBOUND_PRIVATE_HOSTS_ALLOWED` (relay interno declarado) no se
fija: `validar_host_saliente` no devuelve IPs y se conecta por nombre, como
antes. El SMTP de plataforma (`SMTP_HOST` del entorno) tampoco pasa por aquí.

Documentado en docs/seguridad/entrada_y_salida.md («Correo: IP fijada»).
"""
from __future__ import annotations

import imaplib
import socket
from typing import Optional

from app.core.codigos_de_error import error
from app.core.outbound_url import _hosts_privados_permitidos, comprobar_conexion, validar_host_saliente


def ip_fijada(host: str, field: str = "host") -> Optional[str]:
    """La IP (texto) a la que conectar, ya validada; `None` solo si el host es
    un privado permitido explícitamente (se conecta por nombre). Lanza el 400
    del guardia si el host no es aceptable o no resuelve."""
    ips = validar_host_saliente(host, field=field)
    if ips:
        return str(ips[0])
    nombre = (host or "").strip().lower().rstrip(".").strip("[]")
    if nombre in _hosts_privados_permitidos():
        return None
    raise error(400, "host_no_resuelve", detail=f"{field}: el nombre no resuelve", campo=field)


def socket_fijado(host: str, ip: Optional[str], port: int, timeout, source_address=None) -> socket.socket:
    destino = (ip or host, port)
    if timeout is None or timeout is socket._GLOBAL_DEFAULT_TIMEOUT:  # type: ignore[attr-defined]
        sock = socket.create_connection(destino, source_address=source_address)
    else:
        sock = socket.create_connection(destino, timeout, source_address)
    try:
        comprobar_conexion(host, sock.getpeername()[0])
    except BaseException:
        sock.close()
        raise
    return sock


class Imap4SslFijado(imaplib.IMAP4_SSL):
    """`imaplib.IMAP4_SSL` que conecta a `ip_fijada` con SNI del nombre.

    Ojo: sin `ssl_context`, `imaplib` usa un contexto que NO verifica el
    certificado; quien lo crea pasa `contexto_tls()` (verifica salvo
    `SMTP_TLS_VERIFY=false`)."""

    def __init__(self, host: str = "", port: int = imaplib.IMAP4_SSL_PORT, *,
                 ip_fijada: Optional[str] = None, **kwargs):
        self._ip_fijada = ip_fijada
        super().__init__(host, port, **kwargs)

    def _create_socket(self, timeout):
        if timeout is not None and not timeout:
            raise ValueError("Non-blocking socket (timeout=0) is not supported")
        sock = socket_fijado(self.host, self._ip_fijada, self.port, timeout)
        return self.ssl_context.wrap_socket(sock, server_hostname=self.host)
