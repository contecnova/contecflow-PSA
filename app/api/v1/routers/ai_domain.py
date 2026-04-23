"""
AI domain — all artificial intelligence and machine-learning stack modules.
"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    ai_chat, ai_modules, ai_providers, semantic_engine,
    ai_governance, ai_suggestions, ai,
)

router = APIRouter()

router.include_router(ai_chat.router,        prefix="/ai-chat",        tags=["AI Assistant"])
router.include_router(ai_modules.router,     prefix="/ai-modules",     tags=["AI Modules"])
router.include_router(ai_providers.router,   prefix="/ai-providers",   tags=["AI Providers"])
router.include_router(semantic_engine.router, prefix="/semantic",      tags=["Semantic Engine"])
router.include_router(ai_governance.router,  prefix="/ai-governance",  tags=["AI Governance"])
router.include_router(ai_suggestions.router, prefix="/ai/suggestions", tags=["AI Suggestions"])
router.include_router(ai.router,             prefix="/ai",             tags=["AI"])
