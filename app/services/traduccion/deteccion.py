"""Idioma de cada mensaje al guardarlo (entrada).

Al hacer `flush`, los mensajes nuevos sin idioma (comentarios de ticket,
tickets, mensajes de los canales) reciben el que detecta `idiomas.detectar`
si la confianza llega a `TRANSLATION_DETECT_MIN_CONFIDENCE`. Es local: no sale
nada de la aplicacion, asi que se hace aunque la empresa no traduzca. Si no es
seguro, queda vacio y lo rellena el proveedor la primera vez que se traduce.

Cubre todos los sitios que crean mensajes (portal, correo entrante, chat,
WhatsApp, Slack, asistente, agentes) sin tocar cada uno.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: Modelo -> campo con el texto.
_CAMPOS = {"TicketComment": "body", "Ticket": "description", "ChannelMessage": "body"}


def antes_de_guardar(session, flush_context, instances) -> None:
    nuevos = [o for o in session.new if type(o).__name__ in _CAMPOS and getattr(o, "language", None) is None]
    if not nuevos:
        return
    from app.services.traduccion.idiomas import detectar
    minimas: dict = {}
    for o in nuevos:
        if type(o).__name__ == "ChannelMessage" and getattr(o, "author_type", None) == "system":
            continue
        org = getattr(o, "organization_id", None) or session.info.get("organization_id")
        if org not in minimas:
            try:
                from app.services.traduccion.ajustes import confianza_minima
                minimas[org] = confianza_minima(session, org)
            except Exception:
                logger.debug("deteccion: sin ajuste de confianza", exc_info=True)
                minimas[org] = None
        if minimas[org] is None:
            continue
        idioma, confianza = detectar(getattr(o, _CAMPOS[type(o).__name__], None))
        if idioma and confianza >= minimas[org]:
            o.language = idioma


def registrar() -> None:
    from sqlalchemy import event
    from sqlalchemy.orm import Session
    if not event.contains(Session, "before_flush", antes_de_guardar):
        event.listen(Session, "before_flush", antes_de_guardar)


# Se registra al importar el modulo (app/main.py y app/worker.py lo importan),
# igual que `ticket_events` y `automation_events`.
registrar()
