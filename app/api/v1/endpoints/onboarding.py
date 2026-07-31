from fastapi import APIRouter, Body, Depends
from app.api.deps import get_current_user
from app.core.responses import APIListResponse, APIResponse
from app.models.user import User

router = APIRouter()

@router.get("/progress", summary="Get onboarding progress")
def get_onboarding_progress(current_user: User = Depends(get_current_user)):
    # Stub: return minimal onboarding progress
    return APIResponse.ok(data={"step": 1, "completed": False, "tips": ["Welcome to onboarding!"]})

@router.post("/step", summary="Complete onboarding step")
def complete_onboarding_step(payload: dict = Body(...), current_user: User = Depends(get_current_user)):
    # Stub: mark step as completed
    return APIResponse.ok(data={"ok": True, "step": payload.get("step", 1)})

@router.get("/tips", summary="Get onboarding tips")
def get_onboarding_tips(current_user: User = Depends(get_current_user)):
    # Stub: return minimal tips for onboarding
    return APIListResponse.ok(items=[{"step": "profile_completed", "tip": "Complete your profile to get started!"}])
