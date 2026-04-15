"""Realtime notification helpers used by non-WS endpoints."""

from app.api.v1.endpoints.ws import manager


async def publish_user_notification(user_id: str, payload: dict) -> None:
    await manager.publish(user_id, payload)
