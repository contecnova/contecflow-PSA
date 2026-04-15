from fastapi import APIRouter

from app.api.v1.router import api_router as api_v1_router
from app.api.v2.endpoints import profitability

# v2 starts as a compatibility surface while domain-specific v2 endpoints are introduced.
api_router = APIRouter()
api_router.include_router(profitability.router)
api_router.include_router(api_v1_router)
