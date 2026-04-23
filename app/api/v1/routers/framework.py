"""
Framework domain — infrastructure concerns: health checks, websockets,
notifications, and onboarding.
"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    health_composite, ws, onboarding, notifications,
)

router = APIRouter()

router.include_router(health_composite.router, tags=["Health Composite"])
router.include_router(ws.router,               tags=["WebSocket"])
router.include_router(onboarding.router,       prefix="/onboarding",  tags=["Onboarding"])
router.include_router(notifications.router,    tags=["Notifications"])
