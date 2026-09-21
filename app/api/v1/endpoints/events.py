from fastapi import APIRouter, Depends
from app.api.deps import get_current_user
from app.core.responses import APIResponse
from app.models.user import User
from app.core.deps import require_admin

router = APIRouter()

# Endpoint dummy usado solo por tests de notificaciones — oculto del OpenAPI
# para no aparecer como API pública. Requiere auth.
@router.post("/events/test", summary="Test event endpoint", include_in_schema=False)
def test_event(current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: dominio: disparo de eventos de prueba
):
    return APIResponse.ok(data={"ok": True, "message": "Test event received"})
