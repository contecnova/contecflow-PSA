"""Hilos de mensajes anteriores al modelo de conversaciones: busqueda y listado.

Parte de `app.services.portal_conversation_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from typing import Optional
from sqlalchemy.orm import Session, joinedload
from app.models.client_portal import ClientMessage, ClientUser

from app.services.portal_conversation_service._comun import (
    _get_project_for_team,
    _legacy_roots_query,
    _legacy_thread_key,
)
from app.services.portal_conversation_service.serializacion import _legacy_conversation_out


def _get_legacy_thread_for_team(conversation_id: str, current_user, db: Session) -> tuple[ClientMessage, list[ClientMessage]]:
    thread_key = _legacy_thread_key(conversation_id)
    root = _legacy_roots_query(db).filter(ClientMessage.thread_id == thread_key).first()
    if not root:
        root = _legacy_roots_query(db).filter(ClientMessage.id == thread_key).first()
    if not root:
        raise ValueError("Conversación no encontrada")
    if root.project_id:
        _get_project_for_team(root.project_id, current_user, db)
    replies = db.query(ClientMessage).options(
        joinedload(ClientMessage.sender_client),
        joinedload(ClientMessage.sender_user),
        joinedload(ClientMessage.project),
    ).filter(ClientMessage.parent_id == root.id).order_by(ClientMessage.created_at).all()
    return root, replies


def _get_legacy_thread_for_client(conversation_id: str, current_client: ClientUser, db: Session) -> tuple[ClientMessage, list[ClientMessage]]:
    thread_key = _legacy_thread_key(conversation_id)
    root = _legacy_roots_query(db).filter(ClientMessage.thread_id == thread_key).first()
    if not root:
        root = _legacy_roots_query(db).filter(ClientMessage.id == thread_key).first()
    if not root:
        raise ValueError("Conversación no encontrada")
    if root.project_id and root.project_id not in set(current_client.get_project_ids()):
        raise ValueError("Conversación no encontrada")
    if root.sender_client and current_client.client_org_id and root.sender_client.client_org_id and root.sender_client.client_org_id != current_client.client_org_id:
        raise ValueError("Conversación no encontrada")
    replies = db.query(ClientMessage).options(
        joinedload(ClientMessage.sender_client),
        joinedload(ClientMessage.sender_user),
        joinedload(ClientMessage.project),
    ).filter(ClientMessage.parent_id == root.id).order_by(ClientMessage.created_at).all()
    return root, replies


def _list_legacy_threads_for_team(current_user, db: Session, project_id: Optional[str], client_org_id: Optional[str]) -> list:
    query = _legacy_roots_query(db)
    if project_id:
        query = query.filter(ClientMessage.project_id == project_id)
    roots = query.order_by(ClientMessage.created_at.desc()).all()
    result = []
    for root in roots:
        if root.project_id:
            try:
                _get_project_for_team(root.project_id, current_user, db)
            except ValueError:
                continue
        if client_org_id and (not root.sender_client or root.sender_client.client_org_id != client_org_id):
            continue
        replies = db.query(ClientMessage).options(
            joinedload(ClientMessage.sender_client),
            joinedload(ClientMessage.sender_user),
            joinedload(ClientMessage.project),
        ).filter(ClientMessage.parent_id == root.id).order_by(ClientMessage.created_at).all()
        result.append(_legacy_conversation_out(root, replies))
    return result


def _list_legacy_threads_for_client(current_client: ClientUser, db: Session) -> list:
    accessible = set(current_client.get_project_ids())
    roots = _legacy_roots_query(db).order_by(ClientMessage.created_at.desc()).all()
    result = []
    for root in roots:
        if root.project_id and root.project_id not in accessible:
            continue
        if root.sender_client and current_client.client_org_id and root.sender_client.client_org_id and root.sender_client.client_org_id != current_client.client_org_id:
            continue
        replies = db.query(ClientMessage).options(
            joinedload(ClientMessage.sender_client),
            joinedload(ClientMessage.sender_user),
            joinedload(ClientMessage.project),
        ).filter(ClientMessage.parent_id == root.id).order_by(ClientMessage.created_at).all()
        result.append(_legacy_conversation_out(root, replies))
    return result
