"""Colaboración vista desde el portal de cliente (`ClientUser`).

Auditoría 2026-08 (hallazgo 22). Estas operaciones vivían en
`endpoints/collaboration_portal.py` con **21 consultas y escrituras directas**, y
al bajarlas apareció que el portal era **una segunda vía de envío de mensajes con
casi ningún control de la primera**:

* **Los mensajes de cliente no se indexaban para búsqueda.** El endpoint creaba
  la fila y ya; `search_engine.index()` sólo lo llamaba la vía interna.

  > **Con cuidado en el alcance, porque mi primera lectura fue peor de lo que
  > es.** `SimpleSqlSearch.index()` y el `PgFtsSearch` que hereda de él son
  > **no-op**: su búsqueda consulta la tabla de mensajes, así que con SQLite o
  > Postgres el cliente sí encontraba sus mensajes. El indexado sólo hace algo
  > con `COLLAB_SEARCH_BACKEND=opensearch`, y **ahí** los mensajes del portal
  > eran invisibles para la búsqueda. Es un defecto condicionado al backend, no
  > uno que se viera en cualquier despliegue.
* **No pasaban por el escaneo DLP**, que la vía interna sí aplica. Es la misma
  forma que las dos puertas de subida de adjuntos: mismo destino, una con
  controles y otra sin ellos.
* **El reparto de notificaciones era parcial y con una comparación imposible.**
  Sólo avisaba en conversaciones directas, sólo a los dos usuarios internos, y
  se protegía con `uid != current_client.id`: `user_a_id` y `user_b_id` son de
  `users` y `current_client.id` es de `client_users`, así que esa comparación
  **nunca podía ser falsa**. Los clientes contraparte no recibían nada, y en
  canales y grupos no se avisaba a nadie. El aparato interno ya sabe tratar
  destinatarios cliente y excluir al autor por `client_user_id`, así que no hacía
  falta escribir nada nuevo: hacía falta usarlo.
* Los hilos (`parent_message_id` → `CollaborationThread`) tampoco se creaban.

Así que aquí no se reimplementa el envío: se llama a
`messages.send_message` con `client_user_id`, que es la única vía.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.timeutil import utcnow
from app.models.client_portal import ClientUser
from app.models.collaboration import (
    CollaborationChannel,
    CollaborationConversation,
    CollaborationConversationMember,
    CollaborationDirectConversation,
    CollaborationGroupConversation,
    CollaborationMessage,
    CollaborationNotification,
    CollaborationReaction,
    CollaborationRead,
)
from app.services.collaboration._permissions import is_client_conversation_participant
from app.services.collaboration.workspaces import MAX_NOTIFICACIONES
from app.services.traffic_control_service import consume_quota
from app.core.errores import ErrorDeDominio

#: Ventana del tope de mensajes del portal, en segundos.
VENTANA_DE_CUOTA_SEGUNDOS = 60

#: Título de una conversación directa cuando el otro lado es interno. El cliente
#: no ve nombres de empleados: ve con quién habla desde su punto de vista.
TITULO_DIRECTO_CON_INTERNO = "Soporte"
TITULO_DIRECTO = "Chat directo"
TITULO_GRUPO = "Grupo"


def _org(client: ClientUser) -> Optional[str]:
    return getattr(client, "organization_id", None)


def conversaciones_del_cliente(db: Session, client: ClientUser) -> set[str]:
    """Los ids de conversación en los que participa este cliente.

    Dos vías: ser un lado de una conversación directa, o estar en la tabla de
    miembros (grupos y canales compartidos).
    """
    directos = {
        r[0]
        for r in db.query(CollaborationDirectConversation.conversation_id).filter(
            or_(
                CollaborationDirectConversation.client_user_a_id == client.id,
                CollaborationDirectConversation.client_user_b_id == client.id,
            )
        ).all()
    }
    miembro_de = {
        r[0]
        for r in db.query(CollaborationConversationMember.conversation_id).filter(
            CollaborationConversationMember.client_user_id == client.id
        ).all()
    }
    return directos | miembro_de


def list_conversations(db: Session, client: ClientUser) -> list[dict]:
    """Las conversaciones del cliente, con su título.

    Los tres tipos se resuelven en **tres consultas**, una por tipo. El endpoint
    hacía una consulta por conversación para averiguar su título: con veinte
    conversaciones eran veintiuna consultas.
    """
    ids = conversaciones_del_cliente(db, client)
    if not ids:
        return []

    convs = (
        db.query(CollaborationConversation)
        .filter(CollaborationConversation.id.in_(ids))
        .all()
    )

    canales = {
        c.conversation_id: c
        for c in db.query(CollaborationChannel)
        .filter(CollaborationChannel.conversation_id.in_(ids))
        .all()
    }
    directos = {
        d.conversation_id: d
        for d in db.query(CollaborationDirectConversation)
        .filter(CollaborationDirectConversation.conversation_id.in_(ids))
        .all()
    }
    grupos = {
        g.conversation_id: g
        for g in db.query(CollaborationGroupConversation)
        .filter(CollaborationGroupConversation.conversation_id.in_(ids))
        .all()
    }

    salida = []
    for conv in convs:
        titulo = None
        if conv.kind == "channel":
            canal = canales.get(conv.id)
            titulo = f"# {canal.name}" if canal else None
        elif conv.kind == "direct":
            directo = directos.get(conv.id)
            titulo = TITULO_DIRECTO
            if directo and directo.user_a_id:
                titulo = TITULO_DIRECTO_CON_INTERNO
        elif conv.kind == "group":
            grupo = grupos.get(conv.id)
            titulo = (grupo and grupo.title) or TITULO_GRUPO
        salida.append({
            "id": conv.id, "kind": conv.kind, "title": titulo,
            "last_activity_at": conv.last_activity_at,
        })
    return salida


def list_messages(
    db: Session, client: ClientUser, conversation_id: str, *,
    before: Optional[str] = None, limit: int = 50,
) -> list[CollaborationMessage]:
    """Los mensajes de una conversación del cliente, del más antiguo al último."""
    if not is_client_conversation_participant(db, client, conversation_id):
        raise ErrorDeDominio(403, "No tienes acceso a esta conversación")

    q = db.query(CollaborationMessage).filter(
        CollaborationMessage.conversation_id == conversation_id,
        CollaborationMessage.parent_message_id.is_(None),
    )
    if before:
        # El ancla se acota a ESTA conversación. El endpoint la buscaba por id a
        # secas, así que un id de otra conversación desplazaba la ventana de
        # paginación con una fecha ajena.
        ancla = (
            db.query(CollaborationMessage)
            .filter(
                CollaborationMessage.id == before,
                CollaborationMessage.conversation_id == conversation_id,
            )
            .first()
        )
        if ancla:
            q = q.filter(CollaborationMessage.sent_at < ancla.sent_at)

    filas = q.order_by(CollaborationMessage.sent_at.desc()).limit(limit).all()
    filas.reverse()
    return filas


def send_message(db: Session, client: ClientUser, payload) -> CollaborationMessage:
    """Publica un mensaje del cliente por la vía única de envío."""
    from app.services.collaboration.messages import send_message as enviar

    conversation_id = payload.conversation_id
    if not conversation_id:
        raise ErrorDeDominio(400, "conversation_id requerido")

    cuota = consume_quota(
        db,
        scope="collab.portal.message.client",
        tenant_id=_org(client),
        subject=client.id,
        limit=settings.COLLAB_PORTAL_MESSAGE_PER_MIN,
        window_seconds=VENTANA_DE_CUOTA_SEGUNDOS,
    )
    if not cuota["allowed"]:
        raise ErrorDeDominio(
            status_code=429,
            detail=f"Portal message rate limit exceeded. Retry in {cuota['retry_after']}s",
        )

    return enviar(
        db, client,
        body=payload.body,
        conversation_id=conversation_id,
        parent_message_id=payload.parent_message_id,
        type=payload.type or "text",
        metadata_json=payload.metadata_json or {},
        client_user_id=client.id,
    )


def toggle_reaction(db: Session, client: ClientUser, message_id: str, emoji: str) -> dict:
    """Pone o quita la reacción del cliente a un mensaje."""
    msg = (
        db.query(CollaborationMessage)
        .filter(CollaborationMessage.id == message_id)
        .first()
    )
    if not msg:
        raise ErrorDeDominio(404, "Mensaje no encontrado")
    if not is_client_conversation_participant(db, client, msg.conversation_id):
        raise ErrorDeDominio(403, "No tienes acceso")

    existente = (
        db.query(CollaborationReaction)
        .filter(
            CollaborationReaction.message_id == message_id,
            CollaborationReaction.client_user_id == client.id,
            CollaborationReaction.emoji == emoji,
        )
        .first()
    )
    if existente:
        db.delete(existente)
    else:
        db.add(CollaborationReaction(
            organization_id=msg.organization_id, message_id=message_id,
            client_user_id=client.id, emoji=emoji,
        ))
    db.commit()
    return {"toggled": True, "added": existente is None}


def mark_read(
    db: Session, client: ClientUser, conversation_id: str, last_message_id,
) -> None:
    if not is_client_conversation_participant(db, client, conversation_id):
        raise ErrorDeDominio(403, "No tienes acceso")

    fila = (
        db.query(CollaborationRead)
        .filter(
            CollaborationRead.conversation_id == conversation_id,
            CollaborationRead.client_user_id == client.id,
        )
        .first()
    )
    if fila:
        fila.last_message_id = last_message_id
        fila.last_read_at = utcnow()
    else:
        db.add(CollaborationRead(
            organization_id=_org(client),
            conversation_id=conversation_id,
            client_user_id=client.id,
            last_message_id=last_message_id,
        ))
    db.commit()


def list_notifications(
    db: Session, client: ClientUser, *, unread_only: bool = False,
) -> list[dict]:
    """Las notificaciones del cliente, las más recientes primero.

    El tope es el mismo que el del listado interno y por eso se comparte: es el
    mismo concepto —cuántos avisos tiene sentido entregar de una vez— y no dos
    valores que coinciden por casualidad.
    """
    q = db.query(CollaborationNotification).filter(
        CollaborationNotification.client_user_id == client.id
    )
    if unread_only:
        q = q.filter(CollaborationNotification.is_read == False)  # noqa: E712
    filas = (
        q.order_by(CollaborationNotification.created_at.desc())
        .limit(MAX_NOTIFICACIONES)
        .all()
    )
    return [{
        "id": n.id, "kind": n.kind, "title": n.title, "body": n.body,
        "conversation_id": n.conversation_id, "message_id": n.message_id,
        "is_read": n.is_read, "created_at": n.created_at,
    } for n in filas]


def mark_all_notifications_read(db: Session, client: ClientUser) -> int:
    """`UPDATE` masivo: cargarlas para marcarlas una a una serían tantas
    consultas como notificaciones."""
    n = db.query(CollaborationNotification).filter(
        CollaborationNotification.client_user_id == client.id,
        CollaborationNotification.is_read == False,  # noqa: E712
    ).update({"is_read": True, "read_at": utcnow()})
    db.commit()
    return int(n)


def search(db: Session, client: ClientUser, *, query: str, limit: int) -> list[dict]:
    """Busca sólo en las conversaciones del cliente.

    Sin conversaciones no se llama al motor: `conversation_ids=[]` sería una
    búsqueda sin acotar.
    """
    from app.services.collaboration._search import search_engine

    ids = list(conversaciones_del_cliente(db, client))
    if not ids:
        return []
    return search_engine.search(
        db, organization_id=_org(client),
        query=query, conversation_ids=ids, limit=limit,
    )
