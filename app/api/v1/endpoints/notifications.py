from fastapi import APIRouter, Depends
from app.api.deps import get_current_user
from app.core.responses import APIListResponse
from app.models.user import User

router = APIRouter()

@router.get("/notifications", summary="Get notifications")
def get_notifications(current_user: User = Depends(get_current_user)):
    # Stub: return a minimal notification list
    return APIListResponse.ok(items=[{"id": 1, "message": "Test", "read": False}])
