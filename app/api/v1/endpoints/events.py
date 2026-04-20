from fastapi import APIRouter, Depends, status, Body
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter()

@router.post("/events/test", summary="Test event endpoint")
def test_event(current_user: User = Depends(get_current_user)):
    return {"ok": True, "message": "Test event received"}
