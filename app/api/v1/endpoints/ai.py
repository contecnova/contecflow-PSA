from fastapi import APIRouter, Depends
from app.core.deps import get_current_user
from app.models.user import User

router = APIRouter()

# AI suggestions are served by ai_suggestions.py under /ai/suggestions
# This module exposes other AI utility endpoints under /ai

@router.get("/status", summary="AI service health status")
def ai_status(current_user: User = Depends(get_current_user)):
    return {"status": "ok", "providers_configured": True}
