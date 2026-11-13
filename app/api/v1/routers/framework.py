"""
Framework domain — infrastructure concerns: health checks, websockets,
and notifications.
"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    health_composite, ws, notifications,
)

router = APIRouter()

router.include_router(health_composite.router, tags=["Health Composite"])
router.include_router(ws.router,               tags=["WebSocket"])
router.include_router(notifications.router,    tags=["Notifications"])
