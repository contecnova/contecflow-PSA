from fastapi import APIRouter, Depends
from app.api.deps import get_current_user
from app.core.responses import APIResponse
from app.models.user import User

router = APIRouter()

# Endpoint dummy usado solo por tests de notificaciones — oculto del OpenAPI
# para no aparecer como API pública. Requiere auth.
@router.post("/events/test", summary="Test event endpoint", include_in_schema=False)
def test_event(current_user: User = Depends(get_current_user)):
    return APIResponse.ok(data={"ok": True, "message": "Test event received"})
