"""Realtime notification helpers used by non-WS endpoints."""

from app.services.ws_manager import manager


async def publish_user_notification(user_id: str, payload: dict) -> None:
    await manager.publish(user_id, payload)
