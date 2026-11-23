"""Mensajeria entre cliente y equipo.

Parte de `app.services.client_portal_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from typing import Optional
from sqlalchemy.orm import Session
from app.models.client_portal import ClientMessage
from sqlalchemy.orm import joinedload

from app.services.client_portal_service.serializacion import msg_out
from app.core.codigos_de_error import ErrorConCodigo


# ── Messaging ─────────────────────────────────────────────────────────────────

def get_client_messages(thread_id: Optional[str], current_client, db: Session) -> list:

    q = db.query(ClientMessage).options(
        joinedload(ClientMessage.sender_client),
        joinedload(ClientMessage.sender_user),
    ).filter(
        ClientMessage.project_id.in_(current_client.get_project_ids())
        if current_client.get_project_ids()
        else ClientMessage.project_id == None,
        ClientMessage.is_internal == False,
        ClientMessage.parent_id == None,
    )
    if thread_id:
        q = q.filter(ClientMessage.thread_id == thread_id)
    msgs = q.order_by(ClientMessage.created_at.desc()).all()
    _acc = current_client.get_project_ids()
    db.query(ClientMessage).filter(
        ClientMessage.project_id.in_(_acc) if _acc else ClientMessage.project_id == None,
        ClientMessage.sender_user_id != None,
        ClientMessage.is_read_by_client == False,
    ).update({"is_read_by_client": True})
    db.commit()
    result = []
    for m in msgs:
        d = msg_out(m)
        # Auditoría 22-11-2026 (A16): las respuestas internas del equipo no se
        # enseñan al cliente (antes solo se filtraban los mensajes raíz).
        replies = db.query(ClientMessage).options(
            joinedload(ClientMessage.sender_client), joinedload(ClientMessage.sender_user)
        ).filter(ClientMessage.parent_id == m.id, ClientMessage.is_internal == False  # noqa: E712
                 ).order_by(ClientMessage.created_at).all()
        d["replies"] = [msg_out(r) for r in replies]
        result.append(d)
    return result


def get_team_messages(project_id: str, db: Session) -> list:

    msgs = db.query(ClientMessage).options(
        joinedload(ClientMessage.sender_client),
        joinedload(ClientMessage.sender_user),
    ).filter(
        ClientMessage.project_id == project_id,
        ClientMessage.parent_id == None,
    ).order_by(ClientMessage.created_at.desc()).all()
    db.query(ClientMessage).filter(
        ClientMessage.project_id == project_id,
        ClientMessage.sender_client_id != None,
        ClientMessage.is_read_by_team == False,
    ).update({"is_read_by_team": True})
    db.commit()
    result = []
    for m in msgs:
        d = msg_out(m)
        replies = db.query(ClientMessage).options(
            joinedload(ClientMessage.sender_client), joinedload(ClientMessage.sender_user)
        ).filter(ClientMessage.parent_id == m.id).order_by(ClientMessage.created_at).all()
        d["replies"] = [msg_out(r) for r in replies]
        result.append(d)
    return result


def send_client_message(payload, current_client, db: Session) -> dict:
    import uuid

    accessible = current_client.get_project_ids()
    if not accessible:
        raise ErrorConCodigo("sin_proyectos")
    msg_project_id = (
        payload.project_id if (hasattr(payload, "project_id") and payload.project_id)
        else accessible[0]
    )
    if msg_project_id not in accessible:
        raise ErrorConCodigo("sin_acceso_proyecto")
    # A16: lista blanca de lo que manda el cliente. `is_internal` no lo decide
    # él (antes podía mandarlo) y el padre/hilo tienen que ser de SU proyecto
    # y visibles para él (antes se podía colgar un mensaje en un hilo ajeno).
    msg_data = payload.model_dump(exclude_unset=True)
    msg_data = {k: v for k, v in msg_data.items()
                if k in ("subject", "body", "feature_request_id", "uat_session_id", "thread_id", "parent_id")}
    if msg_data.get("parent_id"):
        padre = db.query(ClientMessage).filter(
            ClientMessage.id == msg_data["parent_id"],
            ClientMessage.project_id == msg_project_id,
            ClientMessage.is_internal == False,  # noqa: E712
        ).first()
        if not padre:
            raise ErrorConCodigo("sin_acceso_proyecto")
        msg_data["thread_id"] = padre.thread_id
    elif msg_data.get("thread_id"):
        ajeno = db.query(ClientMessage.id).filter(
            ClientMessage.thread_id == msg_data["thread_id"],
            ClientMessage.project_id != msg_project_id,
        ).first()
        if ajeno:
            raise ErrorConCodigo("sin_acceso_proyecto")
    msg = ClientMessage(
        project_id=msg_project_id,
        sender_client_id=current_client.id,
        is_read_by_team=False,
        is_read_by_client=True,
        is_internal=False,
        **msg_data,
    )
    if not msg.thread_id:
        msg.thread_id = str(uuid.uuid4())
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg_out(msg)


def send_team_message(payload, current_user, db: Session) -> dict:
    import uuid

    msg = ClientMessage(
        sender_user_id=current_user.id,
        is_read_by_team=True,
        is_read_by_client=False,
        **payload.model_dump(exclude_unset=True),
    )
    if not msg.thread_id:
        msg.thread_id = str(uuid.uuid4())
    db.add(msg)
    db.flush()
    # Campana del portal (16-11-2026): cada cliente del proyecto ve el mensaje
    # en su bandeja, no solo en la seccion de Mensajes.
    from app.services.avisos_del_portal import avisar_mensaje_del_equipo
    avisar_mensaje_del_equipo(db, msg, current_user)
    db.commit()
    db.refresh(msg)
    return msg_out(msg)
