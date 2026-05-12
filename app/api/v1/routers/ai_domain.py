"""
AI domain — all artificial intelligence and machine-learning stack modules.
"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    ai_chat, ai_modules, ai_providers, semantic_engine,
    ai_governance, ai_suggestions,
)

router = APIRouter()

router.include_router(ai_chat.router,        prefix="/ai-chat",        tags=["AI Assistant"])
router.include_router(ai_modules.router,     prefix="/ai-modules",     tags=["AI Modules"])
router.include_router(ai_providers.router,   prefix="/ai-providers",   tags=["AI Providers"])
router.include_router(semantic_engine.router, prefix="/semantic",      tags=["Semantic Engine"])
router.include_router(ai_governance.router,  prefix="/ai-governance",  tags=["AI Governance"])
router.include_router(ai_suggestions.router, prefix="/ai/suggestions", tags=["AI Suggestions"])

# ── Compatibility aliases ─────────────────────────────────────────────────────
# ai_chat routes embed "/ai/" in their paths (e.g. /ai/agent/history).
# When mounted at prefix="/ai-chat" the effective URL is /ai-chat/ai/... which
# the frontend never calls.  Mount again with no prefix so the frontend-facing
# paths like /ai/agent/history and /ai/conversations are reachable.
router.include_router(ai_chat.router,    prefix="", tags=["AI Assistant"])
# ai_modules routes embed their resource name (e.g. /oracle/predictions,
# /meetings, /kb).  Mount again with no prefix for frontend compatibility.
router.include_router(ai_modules.router, prefix="", tags=["AI Modules"])
