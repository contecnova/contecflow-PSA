"""Entrega saliente comun: webhooks de Slack/Teams y correo de informes.

Auditoria 2026-11 (#35). Habia un emisor por modulo:

  * Slack: `integrations.send_slack_message` (urllib), `slack_service.send_slack_message`
    (urllib), `endpoints/slack_block_kit.py` (`httpx` directo en la API, SIN validar
    la URL que llega en el cuerpo: SSRF), `scheduled_reports._send_slack` (urllib) y
    `bi_report_delivery_service._send_slack` (`httpx.post` sin validar la URL).
  * Teams: `integrations.send_teams_message` y `bi_report_delivery_service._send_teams`
    (`httpx.post` sin validar).
  * correo de informes: `scheduled_reports._send_email` (un mensaje con todos los
    destinatarios en `To`) y `bi_report_delivery_service._send_email` (uno por
    destinatario).

Ahora todos pasan por aqui:

  * `enviar_a_webhook`: URL validada (`validate_outbound_url`) y conexion por
    `cliente_httpx` (cada redireccion y la IP final validadas). No lanza: el
    fallo vuelve en el resultado, sin el cuerpo de la respuesta remota.
  * `mensaje_de_slack` / `tarjeta_de_teams`: los cuerpos.
  * `enviar_informe_por_correo`: `notification_service.enviar_correo`, un mensaje
    por destinatario (nadie ve a los demas).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Sequence

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResultadoWebhook:
    ok: bool
    status: Optional[int] = None
    error: Optional[str] = None
    datos: Optional[dict] = None   # cuerpo JSON de la respuesta, si lo hay (API de Slack)
    texto: str = ""                # cuerpo de texto (Slack responde «ok»)

    def __bool__(self) -> bool:
        return self.ok


def enviar_a_webhook(url: str, payload: dict, *, headers: Optional[dict] = None,
                     timeout: float = 10.0, campo: str = "webhook_url",
                     estados_ok: Sequence[int] = (200, 201, 202, 204)) -> ResultadoWebhook:
    """POST JSON a un webhook saliente (Slack, Teams, API de Slack). No lanza."""
    import httpx

    from app.core.errores import ErrorDeDominio
    from app.core.outbound_url import cliente_httpx, validate_outbound_url

    try:
        destino = validate_outbound_url(url or "", field=campo)
    except ErrorDeDominio as exc:
        logger.warning("%s rechazado: %s", campo, exc.detail)
        return ResultadoWebhook(False, error=f"{campo} no permitido: {exc.detail}")
    try:
        with cliente_httpx(timeout=timeout) as cliente:
            resp = cliente.post(destino, json=payload, headers=headers or {})
    except (httpx.HTTPError, PermissionError, OSError) as exc:
        logger.warning("Webhook saliente sin entregar (%s): %s", campo, type(exc).__name__)
        return ResultadoWebhook(False, error="No se pudo conectar con el destino")
    datos = None
    try:
        if "json" in (resp.headers.get("content-type") or ""):
            datos = resp.json()
    except ValueError:
        datos = None
    if resp.status_code not in estados_ok:
        logger.warning("Webhook saliente (%s) -> HTTP %s", campo, resp.status_code)
        return ResultadoWebhook(False, status=resp.status_code, error=f"HTTP {resp.status_code}")
    return ResultadoWebhook(True, status=resp.status_code, datos=datos, texto=(resp.text or "")[:200])


def mensaje_de_slack(texto: str, bloques: Optional[list] = None, **extra) -> dict:
    """Cuerpo de un Incoming Webhook de Slack."""
    payload = {"text": texto, **{k: v for k, v in extra.items() if v is not None}}
    if bloques:
        payload["blocks"] = bloques
    return payload


def tarjeta_de_teams(titulo: str, resumen: str, url: Optional[str] = None,
                     hechos: Optional[list] = None, color: str = "0078D7") -> dict:
    """MessageCard de un Incoming Webhook de Teams."""
    payload = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": (color or "0078D7").lstrip("#"),
        "summary": titulo,
        "sections": [{
            "activityTitle": f"**{titulo}**",
            "activitySubtitle": resumen,
            "facts": [{"name": k, "value": str(v)} for k, v in (hechos or [])],
            "markdown": True,
        }],
    }
    if url:
        payload["potentialAction"] = [{
            "@type": "OpenUri", "name": "Ver en Contecflow",
            "targets": [{"os": "default", "uri": url}],
        }]
    return payload


def enviar_informe_por_correo(destinatarios: Sequence[str], asunto: str, html: str, *,
                              adjunto: Optional[tuple] = None, servidor=None) -> list[str]:
    """Envia el informe a cada destinatario por separado. Devuelve los que fallaron.

    `adjunto` es `(nombre, bytes, tipo_mime)`. Lanza `RuntimeError` si el SMTP no
    esta configurado: un informe que no puede salir no se da por enviado.
    """
    from app.services.notification_service import ServidorSmtp, enviar_correo

    servidor = servidor or ServidorSmtp.del_entorno()
    if not servidor.configurado:
        raise RuntimeError("El correo no está configurado (SMTP_HOST): el informe no se ha enviado")
    adjuntos = [adjunto] if adjunto and adjunto[1] else None
    fallidos = []
    for destinatario in dict.fromkeys(d for d in destinatarios if d):
        if not enviar_correo(destinatario, asunto, html, adjuntos=adjuntos, servidor=servidor).enviado:
            fallidos.append(destinatario)
    return fallidos
