"""Chat del portal: ficheros de adjuntos al borrar (antes al final de `app/models/portal_conversations.py`).

Las filas de `portal_conversation_attachments` se borran por el ORM (retención,
cascada con el mensaje o la conversación, supresión RGPD): al borrar se apunta
la clave del fichero; DESPUÉS de confirmar se quita del almacén; si la
transacción se deshace, no se toca nada.

Migración 211 (24-11-2026): también `sd_channel_attachments` (chat en vivo de
Soporte), con la misma lista de claves.

24-11-2026 (prueba general): sale del modelo porque un modelo no importa
servicios (`collaboration._storage`, tests/test_auditoria_2026_11_capas_y_stripe.py).
Mismo patrón que `cuaderno_borrado`: lo registra `app/models/__init__.py` con
todos los modelos ya cargados.
"""
from __future__ import annotations

import logging

from sqlalchemy import event
from sqlalchemy.orm import Session, object_session

log = logging.getLogger(__name__)

_CLAVE = "portal_chat_ficheros_a_borrar"


def _apuntar(mapper, connection, target) -> None:
    sesion = object_session(target)
    if sesion is not None and target.storage_key:
        sesion.info.setdefault(_CLAVE, []).append(target.storage_key)


def _tras_confirmar(session) -> None:
    claves = session.info.pop(_CLAVE, None)
    if not claves:
        return
    from app.services.collaboration._storage import storage
    for clave in claves:
        try:
            storage.delete(clave)
        except Exception:  # noqa: BLE001 - un fichero que no está no impide el resto
            log.warning("chat del portal: no se pudo borrar el fichero %s", clave, exc_info=True)


def _descartar(session, previous_transaction) -> None:
    session.info.pop(_CLAVE, None)


def registrar() -> None:
    from app.models.portal_conversations import PortalConversationAttachment
    from app.models.service_desk.mercado import ChannelAttachment
    if not event.contains(PortalConversationAttachment, "after_delete", _apuntar):
        event.listen(PortalConversationAttachment, "after_delete", _apuntar)
        event.listen(Session, "after_commit", _tras_confirmar)
        event.listen(Session, "after_soft_rollback", _descartar)
    # Migracion 211: los adjuntos del chat en vivo de Soporte, igual.
    if not event.contains(ChannelAttachment, "after_delete", _apuntar):
        event.listen(ChannelAttachment, "after_delete", _apuntar)
